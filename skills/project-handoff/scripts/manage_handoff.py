#!/usr/bin/env python3
"""Print session metadata and save a validated handoff safely."""

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


def _git_metadata(root: Path) -> tuple[str, str]:
    try:
        inside = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return NO_GIT, NO_GIT
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return NO_GIT, NO_GIT

    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if status.returncode != 0:
        raise ValueError("git status failed: " + status.stderr.strip())
    state = "dirty" if status.stdout.strip() else "clean"

    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if head.returncode != 0:
        return "unborn", state
    return head.stdout.strip(), state


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
            os.link(candidate, target)
        except FileExistsError as exc:
            raise ValueError(
                "handoff was created by another writer; re-read it and retry"
            ) from exc
        candidate.unlink()
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
    print(f"SAVED: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Print a format-4 metadata block without writing project files",
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
        if args.mode == "prepare":
            print(prepare(args.root, args.session_scope))
            return 0
        return save(args.root, preview=args.preview, strict=args.strict)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
