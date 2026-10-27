#!/usr/bin/env python3
"""Validate a session handoff Markdown document."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


FORMAT_VERSION = "4"
TARGET_NAME = "项目开发交接.md"
REQUIRED_METADATA = (
    "format-version",
    "updated-at",
    "session-scope",
    "source-revision",
    "working-tree-state",
)
ALLOWED_TREE_STATES = {"clean", "dirty", "not-a-git-repository"}
NO_GIT = "not-a-git-repository"
SECTIONS = (
    ("goal", "本次会话目标"),
    ("work", "做了什么"),
    ("decisions", "关键决策与理由"),
    ("verification", "验证情况"),
    ("pitfalls", "踩坑与失败路径"),
    ("open", "未决问题"),
    ("next", "下一步第一个动作"),
)
SECTION_IDS = tuple(section for section, _ in SECTIONS)
SECTION_TITLES = dict(SECTIONS)

META_BLOCK_RE = re.compile(
    r"<!--\s*project-handoff-meta\s*\r?\n(?P<body>.*?)\r?\n-->",
    re.DOTALL,
)
SECTION_RE = re.compile(r"<!--\s*section:\s*([a-z0-9-]+)\s*-->")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
STATUS_TOKEN_RE = re.compile(
    r"\[(?:拟定|进行中|已实现|未验证|已验证|用户验收|已部署-已回读|受阻|待确认)\]"
)
ALLOWED_STATUS_TOKENS = {"[已验证]", "[待确认]"}
VERIFIED_TOKEN = "[已验证]"
EVIDENCE_HINT_RE = re.compile(
    r"`[^`\n]+`"
    r"|20\d{2}-\d{2}-\d{2}"
    r"|(?i:\b(?:python|pytest|npm|pnpm|yarn|node|cargo|dotnet|go|make|cmake|bash|powershell|curl|git)\b)"
    r"|\d+\s*(?:passed|failed|通过|失败|tests?|项)"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|"
    r"cookie|client[_-]?secret|secret)\b\s*[:=]\s*([^\s`]+)"
)
BEARER_RE = re.compile(r"(?im)\bauthorization\s*:\s*bearer\s+([^\s`]+)")
AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])",
    re.IGNORECASE,
)
CN_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
SAFE_SECRET_VALUES = {
    "[redacted]",
    "<redacted>",
    "redacted",
    "已脱敏",
    "未记录",
    "not-recorded",
}
RAW_CONTEXT_RE = re.compile(
    r"(?im)(?:完整对话记录|原始聊天记录|完整聊天记录|思维链|chain[ -]of[ -]thought|"
    r"^\s*(?:user|assistant|tool)\s*[:：])"
)
PLACEHOLDER_RE = re.compile(
    r"<[^>\n]{1,160}(?:the goal|the single|changes made|files or areas|"
    r"decisions that|what was run|unresolved|failed attempts|one line|"
    r"observable|acceptance condition|actual result|填写|待填|替换)[^>\n]*>",
    re.IGNORECASE,
)
LENGTH_WARNING = 10_000
LENGTH_LIMIT = 20_000


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def exit_code(self, *, strict: bool = False) -> int:
        if self.errors:
            return 1
        if strict and self.warnings:
            return 1
        return 0


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
        key, value = key.strip(), value.strip()
        if key in metadata:
            report.errors.append(f"duplicate metadata key: {key}")
        if "<!--" in value or "-->" in value:
            report.errors.append(f"metadata value contains an HTML comment marker: {key}")
        metadata[key] = value

    missing = [key for key in REQUIRED_METADATA if key not in metadata]
    if missing:
        report.errors.append("missing metadata keys: " + ", ".join(missing))
    for key in REQUIRED_METADATA:
        if key in metadata and not metadata[key]:
            report.errors.append(f"metadata value is empty: {key}")

    unknown = sorted(set(metadata) - set(REQUIRED_METADATA))
    if unknown:
        report.warnings.append("unknown metadata keys: " + ", ".join(unknown))
    return metadata


def _validate_metadata(metadata: dict[str, str], report: Report) -> None:
    if not metadata:
        return

    if metadata.get("format-version") != FORMAT_VERSION:
        report.errors.append(
            f"format-version must be {FORMAT_VERSION}, got "
            f"{metadata.get('format-version')!r}"
        )

    updated_at = metadata.get("updated-at")
    if updated_at:
        try:
            parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError:
            report.errors.append("updated-at must be an ISO-8601 date-time")
        else:
            if parsed.tzinfo is None:
                report.errors.append("updated-at must include a timezone")

    scope = metadata.get("session-scope", "")
    if scope:
        if len(scope) > 300:
            report.errors.append("session-scope must be 300 characters or fewer")
        if scope.startswith("<") and scope.endswith(">"):
            report.errors.append("session-scope still contains the template placeholder")

    revision = metadata.get("source-revision", "")
    state = metadata.get("working-tree-state", "")
    if state and state not in ALLOWED_TREE_STATES:
        report.errors.append(
            "working-tree-state must be one of: "
            + ", ".join(sorted(ALLOWED_TREE_STATES))
        )
    if state == NO_GIT and revision and revision != NO_GIT:
        report.errors.append(
            "a non-git handoff must use 'not-a-git-repository' for source-revision"
        )
    if state in {"clean", "dirty"} and revision == NO_GIT:
        report.errors.append("a git handoff must record the actual source revision")
    if revision and revision != NO_GIT and len(revision) < 7:
        report.errors.append(
            "source-revision looks too short; record the full commit or a unique prefix"
        )


def _validate_sections(text: str, report: Report) -> None:
    if len(re.findall(r"(?m)^# 项目开发交接\s*$", text)) != 1:
        report.errors.append(
            "document must contain exactly one '# 项目开发交接' heading"
        )

    markers = list(SECTION_RE.finditer(text))
    ids = [marker.group(1) for marker in markers]
    counts = Counter(ids)

    for section in SECTION_IDS:
        count = counts.get(section, 0)
        if count != 1:
            report.errors.append(
                f"required section marker {section!r} must appear once, found {count}"
            )
    for section in sorted(set(ids) - set(SECTION_IDS)):
        report.errors.append(f"unknown section marker: {section!r}")
    if set(ids) == set(SECTION_IDS) and ids != list(SECTION_IDS):
        report.errors.append(
            "sections must appear in order: " + " -> ".join(SECTION_IDS)
        )

    for index, marker in enumerate(markers):
        section = marker.group(1)
        if section not in SECTION_TITLES:
            continue
        expected = f"## {SECTION_TITLES[section]}"
        tail = text[marker.end():]
        heading = next((line.strip() for line in tail.splitlines() if line.strip()), "")
        if heading != expected:
            report.errors.append(f"section {section!r} must start with {expected!r}")

        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        body = HTML_COMMENT_RE.sub("", text[marker.end():end])
        body = re.sub(r"(?m)^##\s+.*$", "", body, count=1).strip()
        if not body:
            report.errors.append(f"section {section!r} is empty")


def _validate_labels(text: str, report: Report) -> None:
    for line in text.splitlines():
        if VERIFIED_TOKEN in line and not EVIDENCE_HINT_RE.search(line):
            report.errors.append(
                "[已验证] item needs a command, result, file or date: "
                + line.strip()[:80]
            )

    remaining = text.replace("[已实现][未验证]", "")
    seen: set[str] = set()
    for token in STATUS_TOKEN_RE.findall(remaining):
        if token not in ALLOWED_STATUS_TOKENS and token not in seen:
            seen.add(token)
            report.errors.append(
                f"unsupported status label {token}; use [已验证], "
                "[已实现][未验证], or [待确认]"
            )


def _validate_content(text: str, report: Report) -> None:
    visible = HTML_COMMENT_RE.sub("", text)

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
            "handoff appears to contain raw conversation or chain-of-thought content"
        )

    placeholders = sorted(set(PLACEHOLDER_RE.findall(visible)))
    if placeholders:
        report.errors.append(
            "unresolved template placeholders: " + ", ".join(placeholders)
        )

    bullets = [
        re.sub(r"\s+", " ", line.strip()).casefold()
        for line in visible.splitlines()
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line)
    ]
    duplicates = sorted(
        bullet for bullet, count in Counter(bullets).items() if count > 1
    )
    if duplicates:
        report.warnings.append(
            f"duplicate bullet content found ({len(duplicates)} item(s))"
        )

    length = len(visible)
    if length > LENGTH_LIMIT:
        report.errors.append(
            f"handoff is too large for a session record: {length} chars"
        )
    elif length > LENGTH_WARNING:
        report.warnings.append(
            f"handoff is long for a session record: {length} chars"
        )


def validate_text(text: str) -> Report:
    report = Report()
    metadata = _parse_metadata(text, report)
    _validate_metadata(metadata, report)
    _validate_sections(text, report)
    _validate_labels(text, report)
    _validate_content(text, report)
    return report


def validate_metadata_block(block: str) -> Report:
    report = Report()
    metadata = _parse_metadata(block, report)
    _validate_metadata(metadata, report)
    return report


def validate_file(path: Path) -> Report:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Report(errors=[f"file not found: {path}"])
    except UnicodeDecodeError:
        return Report(errors=[f"file is not valid UTF-8: {path}"])
    return validate_text(text)


def _split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    markers = list(SECTION_RE.finditer(text))
    if not markers:
        return text, []
    head = text[: markers[0].start()]
    blocks: list[tuple[str, str]] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        blocks.append((marker.group(1), text[marker.start():end]))
    return head, blocks


def _join_sections(head: str, blocks: list[tuple[str, str]]) -> str:
    return head + "".join(block for _, block in blocks)


def _empty_section(text: str, target: str) -> str:
    head, blocks = _split_sections(text)
    parts = []
    for section, block in blocks:
        if section == target:
            parts.append(f"<!-- section: {section} -->\n## {SECTION_TITLES[section]}\n")
        else:
            parts.append(block)
    return head + "".join(parts)


def _swap_sections(text: str, first: str, second: str) -> str:
    head, blocks = _split_sections(text)
    ids = [section for section, _ in blocks]
    a, b = ids.index(first), ids.index(second)
    blocks[a], blocks[b] = blocks[b], blocks[a]
    return _join_sections(head, blocks)


def _sample_document() -> str:
    return """<!-- project-handoff-meta
format-version: 4
updated-at: 2026-10-27T10:00:00+08:00
session-scope: Recenter the handoff skill on single-session distillation.
source-revision: not-a-git-repository
working-tree-state: not-a-git-repository
-->
# 项目开发交接

> 新会话先读本文件，从“下一步第一个动作”继续；未验证项不要当作已完成。

<!-- section: goal -->
## 本次会话目标
- 把技能从项目状态档案改成会话提炼。

<!-- section: work -->
## 做了什么
- 重写 `SKILL.md` 为七节会话模板。

<!-- section: decisions -->
## 关键决策与理由
- 去掉 Jev 和项目身份，因为本次目标是会话提炼。

<!-- section: verification -->
## 验证情况
- [已验证] `python -m pytest tools -q` 在 2026-10-27 通过，18 passed。
- [已实现][未验证] 新的安装器尚未在 Claude Code 中实测。

<!-- section: pitfalls -->
## 踩坑与失败路径
- 旧模板要求 project-id，导致每次都要维护项目身份；新格式不再要求。

<!-- section: open -->
## 未决问题
- [待确认] 是否保留旧格式文档的读取兼容；影响：决定是否增加迁移提示。

<!-- section: next -->
## 下一步第一个动作
- 在隔离会话中做一次消费测试；验收条件：新会话能复述目标并执行第一个动作。
"""


def run_self_test() -> int:
    valid = _sample_document()
    scenarios = [
        ("valid document", validate_text(valid).exit_code() == 0),
        (
            "format 3 rejected",
            not validate_text(valid.replace("format-version: 4", "format-version: 3")).ok,
        ),
        (
            "missing scope rejected",
            not validate_text(valid.replace("session-scope: ", "unused-scope: ")).ok,
        ),
        ("empty section rejected", not validate_text(_empty_section(valid, "goal")).ok),
        (
            "out of order rejected",
            not validate_text(_swap_sections(valid, "goal", "work")).ok,
        ),
        (
            "legacy label rejected",
            not validate_text(valid.replace("[待确认]", "[进行中]")).ok,
        ),
        (
            "verified without evidence rejected",
            not validate_text(
                valid.replace(
                    "`python -m pytest tools -q` 在 2026-10-27 通过，18 passed。",
                    "测试通过。",
                )
            ).ok,
        ),
        (
            "secret rejected",
            not validate_text(
                valid.replace("把技能从项目状态档案改成会话提炼。", "password: hunter2")
            ).ok,
        ),
        (
            "oversized rejected",
            not validate_text(valid + "\n" + "x" * (LENGTH_LIMIT + 1_000)).ok,
        ),
        ("warnings remain accepted", validate_text(valid).exit_code() == 0),
    ]
    for name, passed in scenarios:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    return 0 if all(passed for _, passed in scenarios) else 1


def _print_report(path: Path, report: Report, *, strict: bool = False) -> int:
    for error in report.errors:
        print(f"ERROR: {error}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    code = report.exit_code(strict=strict)
    print(f"{'PASS' if code == 0 else 'FAIL'}: {path}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a session handoff Markdown document."
    )
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when warnings are present.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run isolated validation scenarios.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if args.path is None:
        parser.error("path is required unless --self-test is used")
    return _print_report(args.path, validate_file(args.path), strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
