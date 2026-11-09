#!/usr/bin/env python3
"""Inspect session state, print handoff metadata, and save a validated handoff safely."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import validate_handoff as validator


TARGET_NAME = validator.TARGET_NAME
CANDIDATE_SUFFIX = ".candidate"
NO_GIT = validator.NO_GIT
HANDOFF_EXCLUDES = (
    f":(exclude){TARGET_NAME}",
    f":(exclude){TARGET_NAME}{CANDIDATE_SUFFIX}",
)
MAX_LOG_LINES = 30
MAX_STATUS_LINES = 40


def _resolve_root(root: Path) -> Path:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project root must be an existing directory")
    return root


def _handoff_path(root: Path, suffix: str = "") -> Path:
    path = root / (TARGET_NAME + suffix)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(
            f"handoff paths must be regular files, not links or directories: {path}"
        )
    return path


def _digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return "missing"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _status_lines(root: Path) -> list[str]:
    """Return `git status --short` for the whole repository, minus handoff files."""
    status = _git(root, "status", "--porcelain", "--", ":/", *HANDOFF_EXCLUDES)
    if status.returncode != 0:
        raise ValueError("git status failed: " + status.stderr.strip())
    return [line for line in status.stdout.splitlines() if line.strip()]


def _git_metadata(root: Path) -> tuple[str, str]:
    try:
        inside = _git(root, "rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        return NO_GIT, NO_GIT
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return NO_GIT, NO_GIT

    state = "dirty" if _status_lines(root) else "clean"
    head = _git(root, "rev-parse", "HEAD")
    if head.returncode != 0:
        return "unborn", state
    return head.stdout.strip(), state


def _limit(lines: list[str], maximum: int) -> list[str]:
    if len(lines) <= maximum:
        return lines
    return lines[:maximum] + [f"... ({len(lines) - maximum} more)"]


def _previous_metadata(target: Path) -> dict[str, str] | None:
    """Read the existing handoff's metadata leniently, whatever its format version."""
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        return {"error": "existing handoff is not valid UTF-8"}
    match = validator.META_BLOCK_RE.search(text)
    if not match:
        return {"error": "existing handoff has no project-handoff-meta block"}
    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, sep, value = line.partition(":")
        if sep:
            metadata[key.strip()] = value.strip()
    return metadata


def inspect(root: Path) -> str:
    """Report the previous handoff and what changed since; never write project files."""
    root = _resolve_root(root)
    target = _handoff_path(root)
    candidate = _handoff_path(root, CANDIDATE_SUFFIX)
    out: list[str] = []

    previous = _previous_metadata(target)
    if previous is None:
        out.append("previous-handoff: none")
    elif "error" in previous:
        out.append(f"previous-handoff: unreadable ({previous['error']})")
    else:
        out.append(f"previous-handoff: {target}")
        for key in validator.REQUIRED_METADATA:
            out.append(f"previous-{key}: {previous.get(key, 'missing')}")
    if candidate.exists():
        out.append(
            "WARNING: a leftover candidate exists from an earlier save; "
            "overwrite it or delete it after review"
        )

    revision, state = _git_metadata(root)
    out.append(f"current-revision: {revision}")
    out.append(f"current-working-tree-state: {state} (handoff files excluded)")
    if revision == NO_GIT:
        return "\n".join(out)

    base = (previous or {}).get("source-revision", "")
    usable = (
        base not in {"", NO_GIT, "unborn"}
        and revision != "unborn"
        and _git(root, "cat-file", "-e", f"{base}^{{commit}}").returncode == 0
    )
    if base and base not in {NO_GIT, "unborn"} and not usable:
        out.append(
            "baseline: previous source-revision is not in this repository "
            "(rebased, reset, or another clone); compare manually"
        )
    if usable:
        out.append(f"baseline: {base}")
        if _git(root, "merge-base", "--is-ancestor", base, "HEAD").returncode != 0:
            out.append("WARNING: HEAD does not descend from the baseline (history rewritten)")
        log = _git(root, "log", "--oneline", f"{base}..HEAD").stdout.splitlines()
        out.append(f"commits-since-baseline: {len(log)}")
        out.extend("  " + line for line in _limit(log, MAX_LOG_LINES))
        stat = _git(root, "diff", "--stat", base, "--", ":/", *HANDOFF_EXCLUDES)
        stat_lines = stat.stdout.splitlines()
        out.append("tracked-changes-since-baseline:" + ("" if stat_lines else " none"))
        out.extend("  " + line for line in _limit(stat_lines, MAX_STATUS_LINES))
    elif revision != "unborn":
        log = _git(root, "log", "--oneline", "-10").stdout.splitlines()
        out.append("baseline: none; recent commits:")
        out.extend("  " + line for line in log)

    status = _status_lines(root)
    out.append("uncommitted:" + ("" if status else " none"))
    out.extend("  " + line for line in _limit(status, MAX_STATUS_LINES))
    return "\n".join(out)


def prepare(root: Path, session_scope: str) -> str:
    """Print a complete metadata block; never write project files."""
    root = _resolve_root(root)
    scope = session_scope.strip()
    if not scope:
        raise ValueError("session-scope must not be empty")
    if len(scope) > 300:
        raise ValueError("session-scope must be 300 characters or fewer")
    if any(character in scope for character in "\r\n"):
        raise ValueError("session-scope must be a single line")
    if "<!--" in scope or "-->" in scope:
        raise ValueError("session-scope must not contain HTML comment markers")

    revision, state = _git_metadata(root)
    metadata = (
        ("format-version", validator.FORMAT_VERSION),
        ("updated-at", datetime.now().astimezone().isoformat(timespec="seconds")),
        ("session-scope", scope),
        ("source-revision", revision),
        ("working-tree-state", state),
    )
    block = "<!-- project-handoff-meta\n" + "\n".join(
        f"{key}: {value}" for key, value in metadata
    ) + "\n-->"
    report = validator.validate_metadata_block(block)
    if report.errors:
        raise ValueError("generated metadata is invalid: " + "; ".join(report.errors))
    return block


def _create_exclusively(target: Path, candidate: Path, data: bytes) -> None:
    """Create the target without ever replacing a file another writer created."""
    try:
        os.link(candidate, target)
    except FileExistsError:
        raise
    except OSError:
        # Some file systems (FAT, exFAT, certain network shares) lack hard links.
        with open(target, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    candidate.unlink()


def save(root: Path, *, preview: bool = False, strict: bool = False) -> int:
    root = _resolve_root(root)
    target = _handoff_path(root)
    candidate = _handoff_path(root, CANDIDATE_SUFFIX)
    if not candidate.is_file():
        raise ValueError(f"candidate not found: {candidate}")

    data = candidate.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("candidate is not valid UTF-8") from exc

    target_before = _digest(target)
    report = validator.validate_text(text)
    if preview:
        return validator._print_report(candidate, report, strict=strict)
    if report.exit_code(strict=strict):
        validator._print_report(candidate, report, strict=strict)
        return 1

    if _digest(target) != target_before:
        raise ValueError("handoff changed while saving; re-read it and retry")
    if candidate.read_bytes() != data:
        raise ValueError("candidate changed while saving; retry from the current file")

    if target_before == "missing":
        try:
            _create_exclusively(target, candidate, data)
        except FileExistsError as exc:
            raise ValueError(
                "handoff was created by another writer; re-read it and retry"
            ) from exc
    else:
        os.replace(candidate, target)

    saved = target.read_bytes()
    if saved != data:
        raise RuntimeError(
            "saved file differs from the validated candidate; inspect the target"
        )
    check = validator.validate_text(saved.decode("utf-8"))
    if check.exit_code(strict=strict):
        print("SAVED BUT REVALIDATION FAILED; inspect the target")
        validator._print_report(target, check, strict=strict)
        return 1
    for warning in check.warnings:
        print(f"WARNING: {warning}")
    print(f"SAVED: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    validator.use_utf8_output()
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Report the previous handoff, Git changes since it, and drift",
    )
    inspect_parser.add_argument("--root", type=Path, default=Path("."))

    prepare_parser = subparsers.add_parser(
        "prepare",
        help=f"Print a format-{validator.FORMAT_VERSION} metadata block without writing project files",
    )
    prepare_parser.add_argument("--session-scope", required=True)
    prepare_parser.add_argument("--root", type=Path, default=Path("."))

    save_parser = subparsers.add_parser(
        "save",
        help="Validate and atomically save the adjacent candidate",
    )
    save_parser.add_argument("--preview", action="store_true")
    save_parser.add_argument("--strict", action="store_true")
    save_parser.add_argument("--root", type=Path, default=Path("."))

    args = parser.parse_args(argv)
    try:
        if args.mode == "inspect":
            print(inspect(args.root))
            return 0
        if args.mode == "prepare":
            print(prepare(args.root, args.session_scope))
            return 0
        return save(args.root, preview=args.preview, strict=args.strict)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
