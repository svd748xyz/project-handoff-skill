#!/usr/bin/env python3
"""Perform dependency-free checks on the publishable skill package."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "project-handoff"
REQUIRED = (
    ROOT / "README.md",
    ROOT / "LICENSE",
    ROOT / "tools" / "install.py",
    ROOT / "tools" / "test_installer.py",
    ROOT / "tools" / "smoke_install.py",
    ROOT / "tools" / "test_regressions.py",
    SKILL / "SKILL.md",
    SKILL / "agents" / "openai.yaml",
    SKILL / "scripts" / "validate_handoff.py",
    SKILL / "scripts" / "manage_handoff.py",
    SKILL / "scripts" / "process_handoff.py",
    SKILL / "scripts" / "jev_client.py",
    SKILL / "scripts" / "capture_handoff.py",
    SKILL / "scripts" / "triage_handoff.py",
    ROOT / "tools" / "test_process_handoff.py",
    ROOT / "tools" / "test_jev_client.py",
    ROOT / "tools" / "test_capture_handoff.py",
    ROOT / "tools" / "test_triage_handoff.py",
    SKILL / "references" / "consumer-contract.md",
    SKILL / "references" / "evidence-patterns.md",
    SKILL / "references" / "jev-review.md",
    SKILL / "references" / "process-workflow.md",
)
FORBIDDEN_TEXT = (
    "C:" + "\\Users\\",
    "AppData" + "\\Local\\Temp",
    "/Users/" + "Bob/",
)


def main() -> int:
    errors: list[str] = []

    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")

    forbidden_artifacts = sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and (path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts)
    )
    if forbidden_artifacts:
        errors.append("generated Python artifacts found: " + ", ".join(forbidden_artifacts))

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".py", ".yaml", ".yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"not valid UTF-8: {path.relative_to(ROOT)}")
            continue
        for needle in FORBIDDEN_TEXT:
            if needle in text:
                errors.append(
                    f"machine-specific path {needle!r} found in {path.relative_to(ROOT)}"
                )

    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8") if (SKILL / "SKILL.md").is_file() else ""
    frontmatter = re.match(r"^---\n(?P<body>.*?)\n---\n", skill_text, re.DOTALL)
    if not frontmatter:
        errors.append("SKILL.md is missing YAML frontmatter")
    else:
        body = frontmatter.group("body")
        if not re.search(r"(?m)^name:\s*project-handoff\s*$", body):
            errors.append("SKILL.md name must be project-handoff")
        if not re.search(r"(?m)^description:\s*\S.+$", body):
            errors.append("SKILL.md must contain a non-empty description")

    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("PASS: release package")
    return 0


if __name__ == "__main__":
    sys.exit(main())
