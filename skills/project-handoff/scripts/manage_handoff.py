#!/usr/bin/env python3
"""Generate checkpoint metadata and save a validated handoff with conflict checks."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import validate_handoff as validator


TARGET_NAME = "项目开发交接.md"
BASE_KEY = "previous-handoff-sha256"


def _paths(root: Path) -> tuple[Path, Path, Path]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project root must be an existing directory")
    paths = tuple(root / (TARGET_NAME + suffix) for suffix in ("", ".candidate", ".lock"))
    for path in paths:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"handoff paths must be regular files, not links or directories: {path}")
    return paths


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _target_digest(target: Path) -> str:
    try:
        return _digest(target.read_bytes())
    except FileNotFoundError:
        return "missing"


def _metadata(text: str) -> dict[str, str]:
    report = validator.Report()
    metadata = validator._parse_metadata(text, report)
    if report.errors:
        raise ValueError("invalid metadata: " + "; ".join(report.errors))
    return metadata


def prepare(root: Path, workspace: Path, project_key: str, evidence_scope: str,
            critical_files: list[str], history_coverage: str = "visible-only",
            project_id: str | None = None) -> str:
    """Read-only: emit a complete metadata block; never invent evidence or history."""
    root, workspace = root.resolve(strict=True), workspace.resolve(strict=True)
    workspace.relative_to(root)
    target, _, _ = _paths(root)
    previous = _target_digest(target)
    if target.exists():
        old = _metadata(target.read_text(encoding="utf-8"))
        if old.get("format-version") != validator.FORMAT_VERSION:
            raise ValueError("legacy handoff requires an identity-reviewed migration before using this helper")
        if old["project-key"].casefold() != project_key.casefold():
            raise ValueError("existing project-key differs; resolve project identity first")
        if project_id and old["project-id"].casefold() != project_id.casefold():
            raise ValueError("existing project-id differs; resolve project identity first")
        project_id = old["project-id"]
    project_id = str(uuid.UUID(project_id)) if project_id else str(uuid.uuid4())
    metadata = {
        "format-version": validator.FORMAT_VERSION,
        "project-id": project_id,
        "project-key": project_key,
        "project-root": str(root),
        "workspace": str(workspace),
        "updated-at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "evidence-scope": evidence_scope,
        "history-coverage": history_coverage,
        **validator._git_snapshot(root).as_metadata(),
        **validator._critical_files_metadata(root, critical_files),
        BASE_KEY: previous,
    }
    if history_coverage not in validator.ALLOWED_HISTORY_COVERAGE:
        raise ValueError("unsupported history coverage")
    for key, value in metadata.items():
        if not value.strip() or any(part in value for part in ("\n", "\r", "<!--", "-->")):
            raise ValueError(f"invalid metadata value for {key}")
    report = validator.Report()
    validator._validate_content("\n".join(f"{k}: {v}" for k, v in metadata.items()), report)
    if report.errors:
        raise ValueError("metadata contains rejected content: " + "; ".join(report.errors))
    if previous != _target_digest(target):
        raise ValueError("handoff changed while preparing metadata; re-read it and retry")
    return "<!-- project-handoff-meta\n" + "\n".join(f"{k}: {v}" for k, v in metadata.items()) + "\n-->"


def save(root: Path, workspace: Path, *, preview: bool = False,
         allow_limited: bool = False) -> int:
    root, workspace = root.resolve(strict=True), workspace.resolve(strict=True)
    workspace.relative_to(root)
    target, candidate, lock = _paths(root)
    data = candidate.read_bytes()
    text = data.decode("utf-8")
    metadata = _metadata(text)
    expected_base = metadata.get(BASE_KEY, "")
    if expected_base != "missing" and not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_base):
        raise ValueError("candidate lacks a valid previous-handoff-sha256; run prepare before drafting")

    def check() -> validator.Report:
        _paths(root)
        if _target_digest(target) != expected_base:
            raise ValueError("handoff changed since prepare; re-read and reconcile it before saving")
        if target.exists():
            old = _metadata(target.read_text(encoding="utf-8"))
            for key in ("project-id", "project-key"):
                if old[key].casefold() != metadata[key].casefold():
                    raise ValueError(f"candidate {key} differs from the existing handoff")
        return validator.validate_text(
            text, expected_project_root=str(root), expected_workspace=str(workspace),
            expected_project_id=metadata["project-id"], expected_project_key=metadata["project-key"],
            current_root=root,
        )

    if preview:
        report = check()
        validator._print_report(candidate, report, strict=True, allow_limited=allow_limited)
        return report.exit_code(strict=True, allow_limited=allow_limited)

    # Cooperative writers use this same exclusive lock. Existing locks are never
    # silently stolen; a crashed writer's lock must be inspected before removal.
    with lock.open("x", encoding="utf-8") as handle:
        try:
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            report = check()
            code = report.exit_code(strict=True, allow_limited=allow_limited)
            if code:
                validator._print_report(candidate, report, strict=True, allow_limited=allow_limited)
                return code
            if candidate.read_bytes() != data or _target_digest(target) != expected_base:
                raise ValueError("candidate or handoff changed before replacement; nothing was saved")
            if expected_base == "missing":
                # Atomic no-clobber creation if another writer creates the target.
                os.link(candidate, target)
                candidate.unlink()
            else:
                os.replace(candidate, target)
            saved = target.read_bytes()
            if saved != data:
                raise RuntimeError("saved file differs from the validated candidate; inspect the target")
            report = validator.validate_text(
                saved.decode("utf-8"), expected_project_root=str(root),
                expected_workspace=str(workspace), current_root=root,
            )
            validator._print_report(target, report, strict=True, allow_limited=allow_limited)
            code = report.exit_code(strict=True, allow_limited=allow_limited)
            print("SAVED" if code == 0 else "SAVED BUT REVALIDATION FAILED; inspect current state")
            return code
        finally:
            # Close before unlink on Windows. Remove only the lock we created.
            handle.close()
            lock.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    prep = subparsers.add_parser("prepare", help="Print metadata without writing any project files")
    prep.add_argument("--project-key", required=True)
    prep.add_argument("--evidence-scope", required=True)
    prep.add_argument("--project-id")
    prep.add_argument("--critical-file", action="append", default=[])
    prep.add_argument("--history-coverage", choices=sorted(validator.ALLOWED_HISTORY_COVERAGE), default="visible-only")
    saver = subparsers.add_parser("save", help="Validate and atomically save the adjacent candidate")
    saver.add_argument("--preview", action="store_true")
    saver.add_argument("--allow-limited", action="store_true")
    for sub in (prep, saver):
        sub.add_argument("--root", type=Path, required=True)
        sub.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "prepare":
            print(prepare(args.root, args.workspace, args.project_key, args.evidence_scope,
                          args.critical_file, args.history_coverage, args.project_id))
            return 0
        return save(args.root, args.workspace, preview=args.preview, allow_limited=args.allow_limited)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
