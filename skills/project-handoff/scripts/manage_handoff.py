#!/usr/bin/env python3
"""Inspect session state, recover user turns, print metadata, and save handoffs safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
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
USER_REQUEST_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
SKIP_USER_TURN_PREFIXES = (
    "<SYSTEM_MESSAGE>",
    "<environment_context>",
    "<permissions",
    "<INSTRUCTIONS>",
    "# AGENTS.md instructions",
    "<turn_aborted>",
)


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
    """Return `git status --short` scoped to root, minus handoff files."""
    status = _git(root, "status", "--porcelain", "--", ".", *HANDOFF_EXCLUDES)
    if status.returncode != 0:
        raise ValueError("git status failed: " + status.stderr.strip())
    return [line for line in status.stdout.splitlines() if line.strip()]


def _git_info(root: Path) -> tuple[str, str, str, str]:
    """Return (revision, working_tree_state, branch, scope_path) for root."""
    try:
        inside = _git(root, "rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        return NO_GIT, NO_GIT, NO_GIT, ""
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return NO_GIT, NO_GIT, NO_GIT, ""

    state = "dirty" if _status_lines(root) else "clean"
    prefix_proc = _git(root, "rev-parse", "--show-prefix")
    scope_path = (
        prefix_proc.stdout.strip().replace("\\", "/").strip("/")
        if prefix_proc.returncode == 0
        else ""
    )
    sym = _git(root, "symbolic-ref", "--short", "HEAD")
    branch = sym.stdout.strip() if sym.returncode == 0 and sym.stdout.strip() else "detached"
    head = _git(root, "rev-parse", "HEAD")
    if head.returncode != 0:
        return "unborn", state, branch, scope_path
    return head.stdout.strip(), state, branch, scope_path


def _git_metadata(root: Path) -> tuple[str, str]:
    revision, state, _, _ = _git_info(root)
    return revision, state


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
        for key in validator.OPTIONAL_METADATA:
            if key in previous:
                out.append(f"previous-{key}: {previous[key]}")
    if candidate.exists():
        out.append(
            "WARNING: a leftover candidate exists from an earlier save; "
            "overwrite it or delete it after review"
        )

    revision, state, branch, scope_path = _git_info(root)
    out.append(f"current-revision: {revision}")
    out.append(f"current-working-tree-state: {state} (handoff files excluded)")
    if revision == NO_GIT:
        return "\n".join(out)

    out.append(f"current-branch: {branch}")
    if scope_path:
        out.append(f"current-scope-path: {scope_path}")

    prev_branch = (previous or {}).get("branch", "")
    if prev_branch and prev_branch != NO_GIT and prev_branch != branch:
        out.append(
            f"WARNING: branch changed since previous handoff ({prev_branch} -> {branch})"
        )
    prev_scope = (previous or {}).get("scope-path", "")
    if previous and "error" not in previous and prev_scope != scope_path:
        if prev_scope or scope_path:
            out.append(
                f"WARNING: scope-path changed since previous handoff "
                f"({prev_scope or '<repo-root>'} -> {scope_path or '<repo-root>'})"
            )

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
        scoped_log = _git(root, "log", "--oneline", f"{base}..HEAD", "--", ".").stdout.splitlines()
        out.append(f"commits-since-baseline: {len(scoped_log)}")
        if scope_path:
            all_log = _git(root, "log", "--oneline", f"{base}..HEAD").stdout.splitlines()
            if len(all_log) != len(scoped_log):
                out.append(
                    f"repo-commits-since-baseline: {len(all_log)} "
                    f"({len(scoped_log)} touching {scope_path})"
                )
        out.extend("  " + line for line in _limit(scoped_log, MAX_LOG_LINES))
        stat = _git(root, "diff", "--stat", base, "--", ".", *HANDOFF_EXCLUDES)
        stat_lines = stat.stdout.splitlines()
        out.append("tracked-changes-since-baseline:" + ("" if stat_lines else " none"))
        out.extend("  " + line for line in _limit(stat_lines, MAX_STATUS_LINES))
    elif revision != "unborn":
        log = _git(root, "log", "--oneline", "-10", "--", ".").stdout.splitlines()
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

    revision, state, branch, scope_path = _git_info(root)
    metadata: list[tuple[str, str]] = [
        ("format-version", validator.FORMAT_VERSION),
        ("updated-at", datetime.now().astimezone().isoformat(timespec="seconds")),
        ("session-scope", scope),
        ("source-revision", revision),
        ("working-tree-state", state),
    ]
    if revision != NO_GIT:
        metadata.append(("branch", branch))
        if scope_path:
            metadata.append(("scope-path", scope_path))

    block = "<!-- project-handoff-meta\n" + "\n".join(
        f"{key}: {value}" for key, value in metadata
    ) + "\n-->"
    report = validator.validate_metadata_block(block)
    if report.errors:
        raise ValueError("generated metadata is invalid: " + "; ".join(report.errors))
    return block


def _compose_with_metadata(body_text: str, metadata_block: str) -> str:
    """Replace an existing metadata block or prepend a freshly generated one."""
    if validator.META_BLOCK_RE.search(body_text):
        return validator.META_BLOCK_RE.sub(lambda _: metadata_block, body_text, count=1)
    return metadata_block + "\n" + body_text.lstrip("\r\n")


def _create_exclusively(target: Path, source: Path, data: bytes) -> None:
    """Create the target without ever replacing a file another writer created."""
    try:
        os.link(source, target)
    except FileExistsError:
        raise
    except OSError:
        # Some file systems (FAT, exFAT, certain network shares) lack hard links.
        with open(target, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    source.unlink()


def save(
    root: Path,
    *,
    preview: bool = False,
    strict: bool = False,
    session_scope: str | None = None,
) -> int:
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
    if session_scope is not None:
        fresh_block = prepare(root, session_scope)
        composed_text = _compose_with_metadata(text, fresh_block)
        payload = composed_text.encode("utf-8")
    else:
        composed_text = text
        payload = data

    report = validator.validate_text(composed_text)
    if preview:
        return validator._print_report(candidate, report, strict=strict)
    if report.exit_code(strict=strict):
        validator._print_report(candidate, report, strict=strict)
        return 1

    if _digest(target) != target_before:
        raise ValueError("handoff changed while saving; re-read it and retry")
    if candidate.read_bytes() != data:
        raise ValueError("candidate changed while saving; retry from the current file")

    if session_scope is None:
        if target_before == "missing":
            try:
                _create_exclusively(target, candidate, payload)
            except FileExistsError as exc:
                raise ValueError(
                    "handoff was created by another writer; re-read it and retry"
                ) from exc
        else:
            os.replace(candidate, target)
    else:
        staging = root / f".{TARGET_NAME}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
        try:
            with open(staging, "xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if target_before == "missing":
                try:
                    _create_exclusively(target, staging, payload)
                except FileExistsError as exc:
                    raise ValueError(
                        "handoff was created by another writer; re-read it and retry"
                    ) from exc
            else:
                os.replace(staging, target)
        finally:
            if staging.exists():
                staging.unlink()
        candidate.unlink()

    saved = target.read_bytes()
    if saved != payload:
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


def _text_from_content(content: object) -> str:
    """Extract human-written text from string or content-block list, skipping tool results."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                kind = str(item.get("type", "")).lower()
                if kind in {"tool_result", "tool_use", "function_call", "function_call_output"}:
                    continue
                for key in ("text", "input_text", "content", "message"):
                    val = item.get(key)
                    if isinstance(val, str) and val.strip():
                        parts.append(val)
                        break
        return "\n".join(parts)
    if isinstance(content, dict):
        return _text_from_content(content.get("text") or content.get("content") or "")
    return ""


def _extract_user_turn(record: object) -> str | None:
    """Extract a single user message from common coding-agent JSONL transcript schemas."""
    if not isinstance(record, dict):
        return None

    rec_type = str(record.get("type", ""))
    raw = ""

    # Antigravity transcript.jsonl
    if rec_type == "USER_INPUT":
        raw = _text_from_content(record.get("content"))
    # Claude Code session JSONL
    elif rec_type == "user":
        if record.get("isMeta") or record.get("isCompactSummary"):
            return None
        message = record.get("message")
        raw = _text_from_content(
            message.get("content") if isinstance(message, dict) else record.get("content")
        )
    # Codex rollout JSONL
    elif rec_type == "event_msg" and isinstance(record.get("payload"), dict):
        payload = record["payload"]
        if payload.get("type") == "user_message":
            raw = _text_from_content(payload.get("message"))
    elif rec_type == "response_item" and isinstance(record.get("payload"), dict):
        payload = record["payload"]
        if payload.get("type") == "message" and payload.get("role") == "user":
            raw = _text_from_content(payload.get("content"))
    # Generic chat JSONL
    elif record.get("role") == "user":
        raw = _text_from_content(record.get("content"))

    raw = raw.strip()
    if not raw:
        return None

    wrapped = USER_REQUEST_RE.search(raw)
    if wrapped:
        raw = wrapped.group(1).strip()

    if not raw or any(raw.startswith(prefix) for prefix in SKIP_USER_TURN_PREFIXES):
        return None
    return raw


def _shorten_turn(text: str, max_per_turn: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    compact = validator.redact_secrets(compact)
    if len(compact) <= max_per_turn:
        return compact
    if max_per_turn < 20:
        return compact[:max_per_turn]
    head = int(max_per_turn * 0.65)
    tail = max_per_turn - head - 3
    return compact[:head].rstrip() + " … " + compact[-tail:].lstrip()


def recall(
    transcript: Path,
    *,
    max_turns: int = 40,
    max_per_turn: int = 300,
    max_chars: int = 4_000,
) -> str:
    """Extract only human user messages from a local JSONL transcript, secret-redacted."""
    path = transcript.expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"transcript must be an existing file: {path}")
    if max_turns < 1 or max_per_turn < 20 or max_chars < 200:
        raise ValueError("recall limits must be positive (max-per-turn >= 20, max-chars >= 200)")

    turns: list[str] = []
    malformed = 0
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                malformed += 1
                continue
            turn = _extract_user_turn(record)
            if not turn:
                continue
            shortened = _shorten_turn(turn, max_per_turn)
            if turns and turns[-1] == shortened:
                continue
            turns.append(shortened)

    total = len(turns)
    numbered = [f"[{idx}] {item}" for idx, item in enumerate(turns, start=1)]

    # Keep earliest (founding constraints) + latest (recent pivots) within budget.
    selected_head: list[str] = []
    selected_tail: list[str] = []
    omitted = 0

    if numbered:
        head_cap = max(1, int(max_turns * 0.4))
        tail_cap = max(1, max_turns - head_cap)
        head_budget = int(max_chars * 0.4)
        tail_budget = max_chars - head_budget

        used_head = 0
        head_index = 0
        while head_index < len(numbered) and len(selected_head) < head_cap:
            line = numbered[head_index]
            cost = len(line) + 1
            if selected_head and used_head + cost > head_budget:
                break
            selected_head.append(line)
            used_head += cost
            head_index += 1

        remaining = numbered[head_index:]
        used_tail = 0
        tail_take = 0
        for line in reversed(remaining):
            if tail_take >= tail_cap:
                break
            cost = len(line) + 1
            if selected_tail and used_tail + cost > tail_budget:
                break
            selected_tail.append(line)
            used_tail += cost
            tail_take += 1
        selected_tail.reverse()
        omitted = len(remaining) - len(selected_tail)

    out = [
        f"transcript: {path.name}",
        f"total-user-turns: {total}",
        f"shown-user-turns: {len(selected_head) + len(selected_tail)}",
    ]
    if malformed:
        out.append(f"skipped-malformed-lines: {malformed}")
    out.extend(selected_head)
    if omitted > 0:
        out.append(f"... ({omitted} middle user turn(s) omitted) ...")
    out.extend(selected_tail)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    validator.use_utf8_output()
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Report the previous handoff, scoped Git changes since it, and drift",
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
    save_parser.add_argument(
        "--session-scope",
        help="Auto-generate and inject a fresh format-5 metadata block at save time",
    )
    save_parser.add_argument("--preview", action="store_true")
    save_parser.add_argument("--strict", action="store_true")
    save_parser.add_argument("--root", type=Path, default=Path("."))

    recall_parser = subparsers.add_parser(
        "recall",
        help="Extract only secret-redacted human user turns from a local JSONL transcript",
    )
    recall_parser.add_argument("--transcript", type=Path, required=True)
    recall_parser.add_argument("--max-turns", type=int, default=40)
    recall_parser.add_argument("--max-per-turn", type=int, default=300)
    recall_parser.add_argument("--max-chars", type=int, default=4_000)

    args = parser.parse_args(argv)
    try:
        if args.mode == "inspect":
            print(inspect(args.root))
            return 0
        if args.mode == "prepare":
            print(prepare(args.root, args.session_scope))
            return 0
        if args.mode == "recall":
            print(
                recall(
                    args.transcript,
                    max_turns=args.max_turns,
                    max_per_turn=args.max_per_turn,
                    max_chars=args.max_chars,
                )
            )
            return 0
        return save(
            args.root,
            preview=args.preview,
            strict=args.strict,
            session_scope=args.session_scope,
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
