#!/usr/bin/env python3
"""Validate a project-handoff Markdown candidate using deterministic checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath


FORMAT_VERSION = "3"
REQUIRED_METADATA = {
    "format-version",
    "project-id",
    "project-key",
    "project-root",
    "workspace",
    "updated-at",
    "evidence-scope",
    "history-coverage",
    "source-revision",
    "source-branch",
    "working-tree-state",
    "working-tree-fingerprint",
}
ALLOWED_HISTORY_COVERAGE = {
    "visible-only",
    "retrieved",
    "user-confirmed-complete",
}
REQUIRED_SECTIONS = {
    "goal",
    "sources",
    "current-status",
    "verified-progress",
    "blockers",
    "next-steps",
    "entrypoints",
}
OPTIONAL_SECTIONS = {"decisions", "discarded", "baselines"}

META_BLOCK_RE = re.compile(
    r"<!--\s*project-handoff-meta\s*\r?\n(?P<body>.*?)\r?\n-->",
    re.DOTALL,
)
SECTION_RE = re.compile(r"<!--\s*section:\s*([a-z0-9-]+)\s*-->")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
PLACEHOLDER_RE = re.compile(
    r"<[^>\n]*(?:stable project|actual current|local date|the original|"
    r"only current|items that|ordered next|minimum exact|replace me|"
    r"fill in|填写|项目名称|工作目录|更新时间)[^>\n]*>",
    re.IGNORECASE,
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|"
    r"cookie|client[_-]?secret|secret)\b\s*[:=]\s*([^\s`]+)",
)
BEARER_RE = re.compile(r"(?im)\bauthorization\s*:\s*bearer\s+([^\s`]+)")
AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE)
CN_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
SAFE_SECRET_VALUES = {
    "[redacted]",
    "<redacted>",
    "redacted",
    "已脱敏",
    "未记录",
    "not-recorded",
}
ALLOWED_WORKING_TREE_STATES = {
    "clean",
    "dirty",
    "not-a-git-repository",
}
NO_GIT_VALUE = "not-a-git-repository"
CRITICAL_FILES_KEY = "critical-files"
CRITICAL_FINGERPRINT_KEY = "critical-files-fingerprint"
NO_CRITICAL_FILES_VALUE = "none"
HANDOFF_FILENAMES = {"项目开发交接.md", "项目开发交接.md.candidate", "项目开发交接.md.lock"}
ANY_STATUS_RE = re.compile(
    r"\[(?:拟定|进行中|已实现\]\[未验证|已验证|用户验收|已部署-已回读|受阻|待确认)\]"
)
STRONG_STATUS_RE = re.compile(r"\[(?:已验证|用户验收|已部署-已回读)\]")
TIME_HINT_RE = re.compile(
    r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)",
    re.IGNORECASE,
)
ACCEPTANCE_HINT_RE = re.compile(
    r"(?:验收条件|完成条件|通过条件|退出条件|可观察结果|acceptance|done when|passes when|observable result)",
    re.IGNORECASE,
)
CLEARING_HINT_RE = re.compile(
    r"(?:解除条件|解阻|清除条件|下一动作|待.+后|需要.+才|unblock|clears when|next action|requires)",
    re.IGNORECASE,
)
SESSION_INFERENCE_RE = re.compile(
    r"(?:助手推测|模型推测|会话推断|assistant inference|session inference)",
    re.IGNORECASE,
)
RAW_CONTEXT_RE = re.compile(
    r"(?:完整对话记录|原始聊天记录|完整聊天记录|思维链|chain[ -]of[ -]thought|"
    r"^\s*(?:user|assistant|tool)\s*:)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    limited: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def exit_code(self, *, strict: bool = False, allow_limited: bool = False) -> int:
        if self.errors:
            return 1
        if self.stale:
            return 2
        if strict and self.warnings:
            return 1
        if self.limited and not allow_limited:
            return 3
        return 0


@dataclass(frozen=True)
class GitSnapshot:
    revision: str
    branch: str
    tree_state: str
    tree_fingerprint: str

    def as_metadata(self) -> dict[str, str]:
        return {
            "source-revision": self.revision,
            "source-branch": self.branch,
            "working-tree-state": self.tree_state,
            "working-tree-fingerprint": self.tree_fingerprint,
        }


def _normalise_critical_file(value: str) -> str:
    candidate = value.strip().replace("\\", "/")
    if not candidate:
        raise ValueError("critical file path must not be empty")
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        raise ValueError(f"critical file path must be relative: {value!r}")
    path = PurePosixPath(candidate)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"critical file path must be normalized and remain inside the project: {value!r}")
    normalized = path.as_posix()
    if normalized in HANDOFF_FILENAMES:
        raise ValueError(f"handoff file cannot be its own critical baseline: {value!r}")
    return normalized


def _parse_critical_files(
    metadata: dict[str, str],
    report: Report,
) -> list[str] | None:
    has_files = CRITICAL_FILES_KEY in metadata
    has_fingerprint = CRITICAL_FINGERPRINT_KEY in metadata
    if not has_files and not has_fingerprint:
        return None
    if has_files != has_fingerprint:
        report.errors.append(
            f"{CRITICAL_FILES_KEY} and {CRITICAL_FINGERPRINT_KEY} must appear together"
        )
        return None

    try:
        decoded = json.loads(metadata[CRITICAL_FILES_KEY])
    except json.JSONDecodeError:
        report.errors.append(f"{CRITICAL_FILES_KEY} must be a JSON array of relative paths")
        return None
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        report.errors.append(f"{CRITICAL_FILES_KEY} must be a JSON array of relative paths")
        return None
    if len(decoded) > 20:
        report.errors.append(f"{CRITICAL_FILES_KEY} must contain at most 20 paths")
        return None

    normalized: list[str] = []
    for item in decoded:
        try:
            normalized.append(_normalise_critical_file(item))
        except ValueError as exc:
            report.errors.append(str(exc))
    if len(set(path.casefold() for path in normalized)) != len(normalized):
        report.errors.append(f"{CRITICAL_FILES_KEY} contains duplicate paths")
    if normalized != sorted(normalized, key=str.casefold):
        report.errors.append(f"{CRITICAL_FILES_KEY} must be sorted for stable output")

    fingerprint = metadata.get(CRITICAL_FINGERPRINT_KEY, "")
    if normalized:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint):
            report.errors.append(
                f"non-empty {CRITICAL_FILES_KEY} requires a sha256 fingerprint"
            )
    elif fingerprint != NO_CRITICAL_FILES_VALUE:
        report.errors.append(
            f"empty {CRITICAL_FILES_KEY} must use fingerprint {NO_CRITICAL_FILES_VALUE!r}"
        )
    return normalized


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _critical_files_fingerprint(root: Path, relative_paths: list[str]) -> str:
    if not relative_paths:
        return NO_CRITICAL_FILES_VALUE

    resolved_root = root.resolve()
    aggregate = hashlib.sha256()
    for relative_path in sorted(relative_paths, key=str.casefold):
        normalized = _normalise_critical_file(relative_path)
        candidate = (resolved_root / Path(*PurePosixPath(normalized).parts)).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"critical file escapes project root: {normalized!r}") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"critical file is missing or not a file: {normalized}")
        size = candidate.stat().st_size
        file_digest = _file_sha256(candidate)
        aggregate.update(normalized.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(size).encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(file_digest.encode("ascii"))
        aggregate.update(b"\n")
    return "sha256:" + aggregate.hexdigest()


def _critical_files_metadata(root: Path, paths: list[str]) -> dict[str, str]:
    normalized = sorted((_normalise_critical_file(path) for path in paths), key=str.casefold)
    if len(set(path.casefold() for path in normalized)) != len(normalized):
        raise ValueError("critical file list contains duplicate paths")
    if len(normalized) > 20:
        raise ValueError("critical file list must contain at most 20 paths")
    return {
        CRITICAL_FILES_KEY: json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
        CRITICAL_FINGERPRINT_KEY: _critical_files_fingerprint(root, normalized),
    }


def _clean_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _normalise_path(value: str) -> str:
    # Resolve symlinks and Windows 8.3 aliases before comparing locations.
    return os.path.normcase(str(Path(os.path.expandvars(_clean_value(value))).expanduser().resolve()))


def _run_git(root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        text=text,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
        env={**os.environ, "LC_ALL": "C", "LANG": "C", "GIT_OPTIONAL_LOCKS": "0"},
        timeout=30,
    )


def _git_snapshot(root: Path) -> GitSnapshot:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"project root is not an existing directory: {root}")
    try:
        probe = _run_git(root, "rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        return GitSnapshot(NO_GIT_VALUE, NO_GIT_VALUE, NO_GIT_VALUE, NO_GIT_VALUE)
    if probe.returncode != 0:
        if "not a git repository" in probe.stderr.lower():
            return GitSnapshot(NO_GIT_VALUE, NO_GIT_VALUE, NO_GIT_VALUE, NO_GIT_VALUE)
        raise RuntimeError("git repository probe failed: " + probe.stderr.strip())
    if probe.stdout.strip() != "true":
        raise RuntimeError("project root is not a Git working tree")

    revision_result = _run_git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    if revision_result.returncode not in (0, 1):
        raise RuntimeError("git HEAD lookup failed: " + revision_result.stderr.strip())
    revision = revision_result.stdout.strip() if revision_result.returncode == 0 else "unborn"

    branch_result = _run_git(root, "branch", "--show-current")
    if branch_result.returncode != 0:
        raise RuntimeError("git branch lookup failed: " + branch_result.stderr.strip())
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    if not branch:
        branch = "detached" if revision != "unborn" else "unborn"

    status_result = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
        "--",
        ".",
        ":(exclude,literal)项目开发交接.md",
        ":(exclude,literal)项目开发交接.md.candidate",
        ":(exclude,literal)项目开发交接.md.lock",
        text=False,
    )
    if status_result.returncode != 0:
        raise RuntimeError(
            "git status failed: "
            + status_result.stderr.decode("utf-8", errors="replace").strip()
        )
    status_bytes = status_result.stdout
    if not status_bytes:
        return GitSnapshot(revision, branch, "clean", "clean")
    # Status alone is unchanged when an already-dirty file is edited again.
    # Index object IDs cover staged content; hash actual bytes of dirty/untracked
    # working files separately, including changes within dirty submodules.
    digest = hashlib.sha256(b"project-handoff-content-v2\0" + status_bytes)
    index = _run_git(root, "ls-files", "--stage", "-z", "--", ".",
                     ":(exclude,literal)项目开发交接.md",
                     ":(exclude,literal)项目开发交接.md.candidate",
                     ":(exclude,literal)项目开发交接.md.lock", text=False)
    top = _run_git(root, "rev-parse", "--show-toplevel")
    if index.returncode or top.returncode:
        raise RuntimeError("could not read Git index or repository root")
    digest.update(index.stdout)
    repository_root = Path(top.stdout.strip()).resolve()
    entries = iter(status_bytes.split(b"\0"))
    for entry in entries:
        if not entry:
            continue
        state, raw_path = entry[:2], entry[3:]
        if b"R" in state or b"C" in state:
            next(entries, None)  # porcelain -z has a second, original path
        candidate = repository_root / os.fsdecode(raw_path)
        digest.update(b"\0" + raw_path + b"\0")
        if candidate.is_symlink():
            digest.update(b"symlink\0" + os.fsencode(os.readlink(candidate)))
        elif not candidate.exists():
            digest.update(b"missing")
        else:
            candidate.resolve().relative_to(root)
            if candidate.is_file():
                digest.update(_file_sha256(candidate).encode("ascii"))
            elif candidate.is_dir():
                nested = _git_snapshot(candidate)
                if nested.tree_state == NO_GIT_VALUE:
                    raise RuntimeError(f"cannot fingerprint directory: {raw_path!r}")
                digest.update(json.dumps(nested.as_metadata(), sort_keys=True).encode("utf-8"))
            else:
                raise RuntimeError(f"unsupported working-tree file: {raw_path!r}")
    fingerprint = "sha256:" + digest.hexdigest()
    return GitSnapshot(revision, branch, "dirty", fingerprint)


def _parse_metadata(text: str, report: Report) -> dict[str, str]:
    blocks = list(META_BLOCK_RE.finditer(text))
    if len(blocks) != 1:
        report.errors.append(
            f"expected exactly one project-handoff-meta block, found {len(blocks)}"
        )
        return {}

    metadata: dict[str, str] = {}
    for raw_line in blocks[0].group("body").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            report.errors.append(f"invalid metadata line: {line!r}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = _clean_value(value)
        if key in metadata:
            report.errors.append(f"duplicate metadata key: {key}")
        metadata[key] = value

    missing = sorted(REQUIRED_METADATA - metadata.keys())
    if missing:
        report.errors.append(f"missing metadata keys: {', '.join(missing)}")
    for key in sorted(REQUIRED_METADATA & metadata.keys()):
        if not metadata[key]:
            report.errors.append(f"metadata value is empty: {key}")
    return metadata


def _validate_metadata(
    metadata: dict[str, str],
    report: Report,
    *,
    expected_workspace: str | None,
    expected_project_id: str | None,
    expected_project_key: str | None,
    expected_project_root: str | None,
) -> None:
    if not metadata:
        return

    if metadata.get("format-version") != FORMAT_VERSION:
        report.errors.append(
            f"format-version must be {FORMAT_VERSION}, got "
            f"{metadata.get('format-version')!r}"
        )

    coverage = metadata.get("history-coverage")
    if coverage and coverage not in ALLOWED_HISTORY_COVERAGE:
        report.errors.append(
            "history-coverage must be one of: "
            + ", ".join(sorted(ALLOWED_HISTORY_COVERAGE))
        )

    project_id = metadata.get("project-id")
    if project_id:
        try:
            parsed_project_id = uuid.UUID(project_id)
            if str(parsed_project_id) != project_id.casefold():
                report.errors.append("project-id must use canonical UUID form")
        except ValueError:
            report.errors.append("project-id must be a UUID")

    tree_state = metadata.get("working-tree-state")
    if tree_state and tree_state not in ALLOWED_WORKING_TREE_STATES:
        report.errors.append(
            "working-tree-state must be one of: "
            + ", ".join(sorted(ALLOWED_WORKING_TREE_STATES))
        )
    fingerprint = metadata.get("working-tree-fingerprint")
    if tree_state == "clean" and fingerprint != "clean":
        report.errors.append("clean working tree must use fingerprint 'clean'")
    elif tree_state == "dirty" and not re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint or ""):
        report.errors.append("dirty working tree must use a sha256 fingerprint")
    elif tree_state == NO_GIT_VALUE and fingerprint != NO_GIT_VALUE:
        report.errors.append("non-git working tree must use not-a-git-repository fingerprint")
    if tree_state == NO_GIT_VALUE:
        for key in ("source-revision", "source-branch"):
            if metadata.get(key) != NO_GIT_VALUE:
                report.errors.append(f"non-git snapshot must use {NO_GIT_VALUE!r} for {key}")

    _parse_critical_files(metadata, report)

    updated_at = metadata.get("updated-at")
    if updated_at:
        try:
            parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                report.errors.append("updated-at must include a timezone")
        except ValueError:
            report.errors.append("updated-at must be an ISO-8601 date-time")

    if expected_project_key is not None:
        actual = metadata.get("project-key", "").casefold()
        if actual != expected_project_key.strip().casefold():
            report.errors.append(
                f"project-key mismatch: expected {expected_project_key!r}, "
                f"got {metadata.get('project-key')!r}"
            )

    if expected_project_id is not None:
        actual_id = metadata.get("project-id", "").casefold()
        if actual_id != expected_project_id.strip().casefold():
            report.errors.append(
                f"project-id mismatch: expected {expected_project_id!r}, "
                f"got {metadata.get('project-id')!r}"
            )

    path_expectations = (
        ("workspace", expected_workspace),
        ("project-root", expected_project_root),
    )
    for key, expected in path_expectations:
        actual = metadata.get(key)
        if expected is not None and actual:
            if _normalise_path(actual) != _normalise_path(expected):
                report.errors.append(
                    f"{key} mismatch: expected {expected!r}, got {actual!r}"
                )

    for key in ("workspace", "project-root"):
        value = metadata.get(key)
        if value and not Path(_clean_value(value)).exists():
            report.warnings.append(f"{key} does not currently exist: {value}")


def _validate_sections(text: str, report: Report) -> None:
    markers = list(SECTION_RE.finditer(text))
    counts = Counter(marker.group(1) for marker in markers)

    for section in sorted(REQUIRED_SECTIONS):
        count = counts.get(section, 0)
        if count != 1:
            report.errors.append(
                f"required section marker {section!r} must appear once, found {count}"
            )

    unknown = sorted(set(counts) - REQUIRED_SECTIONS - OPTIONAL_SECTIONS)
    if unknown:
        report.warnings.append(f"unknown section markers: {', '.join(unknown)}")

    for section, count in sorted(counts.items()):
        if count > 1:
            report.errors.append(
                f"section marker {section!r} appears {count} times"
            )

    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        body = text[marker.end() : end]
        body = HTML_COMMENT_RE.sub("", body)
        body = re.sub(r"(?m)^#{1,6}\s+.*$", "", body).strip()
        if not body:
            report.errors.append(f"section {marker.group(1)!r} is empty")

    startup_count = len(re.findall(r"<!--\s*new-session-start\s*-->", text))
    if startup_count != 1:
        report.errors.append(
            f"new-session-start marker must appear once, found {startup_count}"
        )

    headings = [
        heading.strip().casefold()
        for heading in re.findall(r"(?m)^##\s+(.+?)\s*$", text)
    ]
    duplicate_headings = sorted(
        heading for heading, count in Counter(headings).items() if count > 1
    )
    if duplicate_headings:
        report.errors.append(
            "duplicate level-2 headings: " + ", ".join(duplicate_headings)
        )


def _section_bodies(text: str) -> dict[str, str]:
    markers = list(SECTION_RE.finditer(text))
    bodies: dict[str, str] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        bodies[marker.group(1)] = text[marker.end() : end]
    return bodies


def _list_items(body: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if re.match(r"^(?:[-*+]|\d+[.)])\s+", line):
            if current:
                items.append(" ".join(current))
            current = [line]
        elif line and not line.startswith("#") and not line.startswith("<!--"):
            current.append(line)
        elif not line and current:
            items.append(" ".join(current))
            current = []
    if current:
        items.append(" ".join(current))
    return items


def _checked_items(body: str, section: str, report: Report) -> list[str]:
    """Require flat lists in mechanically checked sections; never skip prose."""
    active = False
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            active = False
            continue
        if re.match(r"^(?:[-*+]|\d+[.)])\s+", line) and not raw[:1].isspace():
            active = True
        elif active and raw[:1].isspace() and not re.match(r"^(?:[-*+]|\d+[.)])\s+", line):
            continue
        else:
            report.errors.append(f"{section} must use flat list items with indented continuations; unsupported line: {line[:60]}")
    return _list_items(body)


def _has_value(pattern: re.Pattern, text: str) -> bool:
    match = pattern.search(text)
    if not match:
        return False
    value = text[match.end():].strip(" :：;；.。-`")
    return bool(value) and value.casefold() not in {"todo", "tbd", "待填写", "待补充"}


def _validate_semantics(
    text: str,
    metadata: dict[str, str],
    report: Report,
) -> None:
    bodies = {key: HTML_COMMENT_RE.sub("", value) for key, value in _section_bodies(text).items()}
    checked = {
        section: _checked_items(bodies.get(section, ""), section, report)
        for section in ("sources", "current-status", "verified-progress", "blockers", "next-steps")
    }
    for line in HTML_COMMENT_RE.sub("", text).splitlines():
        if line.lstrip().startswith("#") and STRONG_STATUS_RE.search(line):
            report.errors.append("put strong verification claims in the body, not a heading")

    # Strong assertions have the same requirements wherever they occur.
    for body in bodies.values():
        for item in _list_items(body):
            if SESSION_INFERENCE_RE.search(item) and "[待确认]" not in item:
                report.errors.append("session inference must be marked [待确认]")
            if not STRONG_STATUS_RE.search(item):
                continue
            for claim in re.split(r"(?=\[(?:已验证|用户验收|已部署-已回读)\])", item)[1:]:
                claim = STRONG_STATUS_RE.sub("", claim)
                if not re.search(r"`[^`]+`|https?://\S+|\[[^\]]+\]\([^)]+\)", claim):
                    report.errors.append("strong verification claim is missing a concrete evidence reference (code span or link)")
                dates = TIME_HINT_RE.findall(claim)
                if not dates:
                    report.errors.append("strong verification claim needs an explicit verification date (YYYY-MM-DD)")
                for value in dates:
                    try:
                        datetime.strptime(value, "%Y-%m-%d")
                    except ValueError:
                        report.errors.append(f"invalid verification date: {value}")
                if not re.search(r"范围|scope", claim, re.IGNORECASE):
                    report.errors.append("strong verification claim is missing its evidence scope")

    sources = HTML_COMMENT_RE.sub("", bodies.get("sources", ""))
    if not re.search(r"(?:冲突|优先级|precedence|conflict)", sources, re.IGNORECASE):
        report.errors.append("sources section must state a conflict or precedence rule")
    if not checked["sources"]:
        report.errors.append("sources section must contain at least one source mapping item")

    verified_items = checked["verified-progress"]
    for item in verified_items:
        if not ANY_STATUS_RE.search(item):
            report.errors.append("verified-progress item is missing a recognized state label")

    current_items = checked["current-status"]
    for item in current_items:
        if not ANY_STATUS_RE.search(item):
            report.errors.append("current-status item is missing a recognized state label")

    next_items = checked["next-steps"]
    for item in next_items:
        if not _has_value(ACCEPTANCE_HINT_RE, item):
            report.errors.append("next-step item is missing an observable acceptance condition")

    blocker_items = checked["blockers"]
    for item in blocker_items:
        if "[受阻]" not in item and "[待确认]" not in item:
            report.errors.append("blocker item must be marked [受阻] or [待确认]")
        if "[受阻]" in item and not _has_value(CLEARING_HINT_RE, item):
            report.errors.append("blocked item is missing a clearing condition or next action")

    scratch = Report()
    critical_files = _parse_critical_files(metadata, scratch)
    if critical_files:
        baseline_body = HTML_COMMENT_RE.sub("", bodies.get("baselines", ""))
        if not baseline_body.strip():
            report.errors.append("critical files require a baselines section")
        else:
            for relative_path in critical_files:
                if relative_path not in baseline_body.replace("\\", "/"):
                    report.errors.append(
                        f"baselines section does not explain critical file: {relative_path}"
                    )

    discarded_items = _list_items(HTML_COMMENT_RE.sub("", bodies.get("discarded", "")))
    for item in discarded_items:
        missing = [
            label
            for label in ("现象", "证据", "根因", "避免", "重试条件")
            if label not in item
        ]
        if missing:
            report.warnings.append(
                "discarded-path item should use 现象/证据/根因/避免/重试条件; missing: "
                + ", ".join(missing)
            )


def _validate_current_snapshot(
    metadata: dict[str, str],
    report: Report,
    *,
    current_root: Path,
) -> None:
    if not metadata:
        return
    try:
        current = _git_snapshot(current_root)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        report.errors.append(f"could not capture current project snapshot: {exc}")
        return

    recorded_root = metadata.get("project-root")
    if recorded_root and _normalise_path(recorded_root) != _normalise_path(str(current_root)):
        report.stale.append("handoff project-root differs from current root; refresh location metadata")

    for key, current_value in current.as_metadata().items():
        recorded = metadata.get(key)
        if recorded != current_value:
            report.stale.append(
                f"handoff is stale: {key} changed from {recorded!r} to {current_value!r}"
            )

    scratch = Report()
    critical_files = _parse_critical_files(metadata, scratch)
    if scratch.errors:
        return
    if critical_files is None:
        if current.tree_state == NO_GIT_VALUE:
            report.limited.append(
                "non-git handoff has no critical-files baseline; freshness is limited"
            )
        return
    if not critical_files:
        if current.tree_state == NO_GIT_VALUE:
            report.limited.append(
                "non-git handoff tracks no critical files; freshness is limited"
            )
        return
    try:
        current_fingerprint = _critical_files_fingerprint(current_root, critical_files)
    except (OSError, ValueError) as exc:
        report.stale.append(f"handoff is stale: {exc}")
        return
    recorded_fingerprint = metadata.get(CRITICAL_FINGERPRINT_KEY)
    if recorded_fingerprint != current_fingerprint:
        report.stale.append(
            "handoff is stale: critical-files-fingerprint changed from "
            f"{recorded_fingerprint!r} to {current_fingerprint!r}"
        )


def _validate_content(text: str, report: Report) -> None:
    visible = HTML_COMMENT_RE.sub("", text)

    placeholders = sorted(set(PLACEHOLDER_RE.findall(visible)))
    if placeholders:
        report.errors.append(
            "unresolved template placeholders: " + ", ".join(placeholders)
        )

    if AWS_KEY_RE.search(text):
        report.errors.append("possible AWS access key found")
    if PRIVATE_KEY_RE.search(text):
        report.errors.append("private-key material found")

    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        value = match.group(2).strip("'\".,;").casefold()
        if value not in SAFE_SECRET_VALUES:
            report.errors.append(
                f"possible secret assignment found for {match.group(1)!r}"
            )

    for match in BEARER_RE.finditer(text):
        value = match.group(1).strip("'\".,;").casefold()
        if value not in SAFE_SECRET_VALUES:
            report.errors.append("possible bearer token found")

    if EMAIL_RE.search(visible):
        report.warnings.append("possible email address found; retain only if essential")
    if CN_MOBILE_RE.search(visible):
        report.warnings.append("possible mobile number found; retain only if essential")
    if RAW_CONTEXT_RE.search(visible):
        report.warnings.append(
            "handoff appears to contain raw conversation or chain-of-thought content; summarize only continuation-relevant facts"
        )

    bullets = [
        re.sub(r"\s+", " ", line.strip()).casefold()
        for line in visible.splitlines()
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line)
    ]
    duplicate_bullets = sorted(
        bullet for bullet, count in Counter(bullets).items() if count > 1
    )
    if duplicate_bullets:
        report.warnings.append(
            f"duplicate bullet content found ({len(duplicate_bullets)} item(s))"
        )

    length = len(visible)
    if length > 30_000:
        report.errors.append(f"handoff is too large for a concise snapshot: {length} chars")
    elif length > 12_000:
        report.warnings.append(f"handoff is long for a concise snapshot: {length} chars")


def validate_text(
    text: str,
    *,
    expected_workspace: str | None = None,
    expected_project_id: str | None = None,
    expected_project_key: str | None = None,
    expected_project_root: str | None = None,
    current_root: Path | None = None,
) -> Report:
    report = Report()
    metadata = _parse_metadata(text, report)
    _validate_metadata(
        metadata,
        report,
        expected_workspace=expected_workspace,
        expected_project_id=expected_project_id,
        expected_project_key=expected_project_key,
        expected_project_root=expected_project_root,
    )
    _validate_sections(text, report)
    _validate_content(text, report)
    _validate_semantics(text, metadata, report)
    if current_root is not None:
        _validate_current_snapshot(metadata, report, current_root=current_root)
    return report


def validate_file(
    path: Path,
    *,
    expected_workspace: str | None = None,
    expected_project_id: str | None = None,
    expected_project_key: str | None = None,
    expected_project_root: str | None = None,
    current_root: Path | None = None,
) -> Report:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Report(errors=[f"file not found: {path}"])
    except UnicodeDecodeError:
        return Report(errors=[f"file is not valid UTF-8: {path}"])
    return validate_text(
        text,
        expected_workspace=expected_workspace,
        expected_project_id=expected_project_id,
        expected_project_key=expected_project_key,
        expected_project_root=expected_project_root,
        current_root=current_root,
    )


def _sample_document(
    workspace: Path,
    critical_paths: list[str] | None = None,
) -> str:
    critical_metadata = _critical_files_metadata(workspace, critical_paths or [])
    return f"""<!-- project-handoff-meta
format-version: 3
project-id: 11111111-1111-4111-8111-111111111111
project-key: example-parser
project-root: {workspace}
workspace: {workspace}
updated-at: 2026-08-31T14:00:00+08:00
evidence-scope: current-visible-conversation; existing-handoff; workspace-evidence
history-coverage: visible-only
source-revision: not-a-git-repository
source-branch: not-a-git-repository
working-tree-state: not-a-git-repository
working-tree-fingerprint: not-a-git-repository
critical-files: {critical_metadata[CRITICAL_FILES_KEY]}
critical-files-fingerprint: {critical_metadata[CRITICAL_FINGERPRINT_KEY]}
-->
# 项目开发交接

<!-- new-session-start -->
> 新会话先读本文件，再核验待确认项和下一步验收条件。

<!-- section: goal -->
## 项目目标与边界
- 实现本地解析器，不包含云端部署。

<!-- section: sources -->
## 事实来源与冲突规则
- 项目目标：用户当前明确要求；冲突时以用户最新更正和当前工作区证据优先。

<!-- section: current-status -->
## 当前状态
- [已实现][未验证] 解析入口已经存在。

<!-- section: verified-progress -->
## 已确认进展与证据
- [已验证] `src/parser.py` 存在；证据范围为入口文件检查，本次核验日期 2026-08-31。

<!-- section: blockers -->
## 当前卡点、风险与待确认项
- [待确认] 尚未验证非法输入。

<!-- section: next-steps -->
## 下一步推进目标与验收条件
1. 补充输入测试；验收条件：正常、空值和非法输入均有可复现结果。

<!-- section: baselines -->
## 关键基线文件
- `requirements.md`：支撑当前目标与输入边界；内容变化后重新核验目标和测试范围。

<!-- section: entrypoints -->
## 关键文件、入口与命令
- `src/parser.py`
""".replace("`", chr(96))


def run_self_test() -> int:
    scenarios: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="project-handoff-validator-") as tmp:
        workspace = Path(tmp)
        requirements = workspace / "requirements.md"
        requirements.write_text("local parser requirements\n", encoding="utf-8")
        valid = _sample_document(workspace, ["requirements.md"])
        valid_path = workspace / "项目开发交接.md"
        valid_path.write_text(valid, encoding="utf-8")

        scenarios.append(("valid UTF-8 file", validate_file(
            valid_path,
            expected_workspace=str(workspace),
            expected_project_id="11111111-1111-4111-8111-111111111111",
            expected_project_key="example-parser",
            expected_project_root=str(workspace),
        ).ok))
        scenarios.append(("project mismatch rejected", not validate_text(
            valid,
            expected_project_key="different-project",
        ).ok))
        scenarios.append(("invalid project ID rejected", not validate_text(
            valid.replace(
                "project-id: 11111111-1111-4111-8111-111111111111",
                "project-id: not-a-uuid",
            )
        ).ok))
        scenarios.append(("secret rejected", not validate_text(
            valid + "\napi_key=super-secret-value\n"
        ).ok))
        scenarios.append(("metadata secret rejected", not validate_text(
            valid.replace(
                "evidence-scope: current-visible-conversation; existing-handoff; workspace-evidence",
                "evidence-scope: api_key=hidden-secret-value",
            )
        ).ok))
        scenarios.append(("duplicate section rejected", not validate_text(
            valid + "\n<!-- section: goal -->\n## Duplicate\n- duplicate\n"
        ).ok))
        scenarios.append(("placeholder rejected", not validate_text(
            valid.replace("实现本地解析器，不包含云端部署。", "<the original goal>")
        ).ok))
        scenarios.append(("missing startup rejected", not validate_text(
            valid.replace("<!-- new-session-start -->", "")
        ).ok))
        scenarios.append(("verification without evidence rejected", not validate_text(
            valid.replace(
                "[已验证] `src/parser.py` 存在；证据范围为入口文件检查，本次核验日期 2026-08-31。",
                "[已验证] 功能完成，本轮核验。",
            )
        ).ok))
        scenarios.append(("next step without acceptance rejected", not validate_text(
            valid.replace(
                "补充输入测试；验收条件：正常、空值和非法输入均有可复现结果。",
                "补充输入测试。",
            )
        ).ok))
        scenarios.append(("non-git snapshot remains current", validate_file(
            valid_path,
            current_root=workspace,
        ).ok and not validate_file(valid_path, current_root=workspace).warnings))
        requirements.write_text("changed requirements\n", encoding="utf-8")
        non_git_stale = validate_file(valid_path, current_root=workspace)
        scenarios.append((
            "non-git critical change marks handoff stale",
            non_git_stale.ok and any(
                "critical-files-fingerprint changed" in item
                for item in non_git_stale.stale
            ),
        ))
        requirements.write_text("local parser requirements\n", encoding="utf-8")
        legacy_non_git = re.sub(
            rf"(?m)^(?:{CRITICAL_FILES_KEY}|{CRITICAL_FINGERPRINT_KEY}):.*\r?\n?",
            "",
            valid,
        ).replace(
            "<!-- section: baselines -->\n## 关键基线文件\n- `requirements.md`：支撑当前目标与输入边界；内容变化后重新核验目标和测试范围。\n\n",
            "",
        )
        legacy_report = validate_text(legacy_non_git, current_root=workspace)
        scenarios.append((
            "legacy non-git handoff warns about limited freshness",
            legacy_report.ok and any("freshness is limited" in item for item in legacy_report.limited),
        ))
        scenarios.append(("absolute critical path rejected", not validate_text(
            valid.replace('critical-files: ["requirements.md"]', 'critical-files: ["C:/outside.txt"]')
        ).ok))
        raw_context_report = validate_text(valid + "\nAssistant: copied old reasoning\n")
        scenarios.append((
            "raw conversation content warned",
            raw_context_report.ok and any("raw conversation" in item for item in raw_context_report.warnings),
        ))
        scenarios.append(("unlabelled current status rejected", not validate_text(
            valid.replace("[已实现][未验证] 解析入口已经存在。", "解析入口已经存在。")
        ).ok))
        scenarios.append(("session inference must remain unconfirmed", not validate_text(
            valid.replace(
                "[已实现][未验证] 解析入口已经存在。",
                "[进行中] 助手推测解析入口已经存在。",
            )
        ).ok))

        if shutil.which("git"):
            repo = workspace / "repo"
            repo.mkdir()
            _run_git(repo, "init", "--quiet")
            _run_git(repo, "config", "user.email", "handoff-test@example.invalid")
            _run_git(repo, "config", "user.name", "Project Handoff Test")
            tracked = repo / "tracked.txt"
            tracked.write_text("baseline\n", encoding="utf-8")
            _run_git(repo, "add", "tracked.txt")
            _run_git(repo, "commit", "--quiet", "-m", "baseline")
            snapshot = _git_snapshot(repo)
            git_doc = _sample_document(repo, ["tracked.txt"])
            git_doc = git_doc.replace(
                "`requirements.md`：支撑当前目标与输入边界；内容变化后重新核验目标和测试范围。",
                "`tracked.txt`：支撑当前基线；内容变化后重新核验实现与测试范围。",
            )
            for key, value in snapshot.as_metadata().items():
                git_doc = re.sub(
                    rf"(?m)^{re.escape(key)}: .+$",
                    f"{key}: {value}",
                    git_doc,
                )
            git_path = repo / "项目开发交接.md"
            git_path.write_text(git_doc, encoding="utf-8")
            current_report = validate_file(git_path, current_root=repo)
            scenarios.append((
                "git snapshot remains current",
                current_report.ok and not current_report.warnings,
            ))
            tracked.write_text("changed\n", encoding="utf-8")
            stale_report = validate_file(git_path, current_root=repo)
            scenarios.append((
                "git change marks handoff stale",
                stale_report.ok and any("handoff is stale" in item for item in stale_report.stale),
            ))
        pii_report = validate_text(valid + "\n联系人：person@example.com\n")
        scenarios.append((
            "possible PII warned",
            pii_report.ok and any("email address" in item for item in pii_report.warnings),
        ))

    for name, passed in scenarios:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    return 0 if all(passed for _, passed in scenarios) else 1


def _print_report(path: Path, report: Report, *, strict: bool = False, allow_limited: bool = False) -> None:
    for error in report.errors:
        print(f"ERROR: {error}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for reason in report.stale:
        print(f"STALE: {reason}")
    for reason in report.limited:
        print(f"LIMITED: {reason}")
    code = report.exit_code(strict=strict, allow_limited=allow_limited)
    if code == 1:
        label = "FAIL"
    elif code == 2:
        label = "STALE"
    elif report.limited:
        label = "VALID-LIMITED" if code == 0 else "LIMITED"
    else:
        label = "PASS"
    print(f"{label}: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a project-handoff Markdown candidate."
    )
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--expected-workspace")
    parser.add_argument("--expected-project-id")
    parser.add_argument("--expected-project-key")
    parser.add_argument("--expected-project-root")
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        help="Print read-only Git and critical-file snapshot metadata for a project root.",
    )
    parser.add_argument(
        "--critical-file",
        action="append",
        default=[],
        help="Relative project file to include in the critical baseline; repeat as needed.",
    )
    parser.add_argument(
        "--check-current",
        action="store_true",
        help="Compare recorded snapshot metadata with the current project state.",
    )
    parser.add_argument(
        "--current-root",
        type=Path,
        help="Current project root used with --check-current.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return failure when warnings are present.",
    )
    parser.add_argument(
        "--allow-limited",
        action="store_true",
        help="Accept limited snapshot coverage; does not waive errors, stale state, or strict warnings.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run isolated built-in validation scenarios.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if args.snapshot_root is not None:
        try:
            snapshot = _git_snapshot(args.snapshot_root)
            snapshot_metadata = snapshot.as_metadata()
            snapshot_metadata.update(
                _critical_files_metadata(args.snapshot_root, args.critical_file)
            )
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            print(f"ERROR: could not capture project snapshot: {exc}")
            return 1
        for key, value in snapshot_metadata.items():
            print(f"{key}: {value}")
        return 0
    if args.critical_file:
        parser.error("--critical-file requires --snapshot-root")
    if args.path is None:
        parser.error("path is required unless --self-test or --snapshot-root is used")
    if args.check_current and args.current_root is None:
        parser.error("--current-root is required with --check-current")

    report = validate_file(
        args.path,
        expected_workspace=args.expected_workspace,
        expected_project_id=args.expected_project_id,
        expected_project_key=args.expected_project_key,
        expected_project_root=args.expected_project_root,
        current_root=args.current_root if args.check_current else None,
    )
    _print_report(args.path, report, strict=args.strict, allow_limited=args.allow_limited)
    return report.exit_code(strict=args.strict, allow_limited=args.allow_limited)


if __name__ == "__main__":
    sys.exit(main())
