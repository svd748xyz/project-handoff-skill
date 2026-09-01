#!/usr/bin/env python3
"""Copy the skill to an isolated directory and verify it remains self-contained."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "project-handoff"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="project-handoff-install-") as temporary:
        installed = Path(temporary) / "skills" / "project-handoff"
        shutil.copytree(SOURCE, installed)

        skill_text = (installed / "SKILL.md").read_text(encoding="utf-8")
        linked_paths = {
            match.group(1)
            for match in re.finditer(r"\[[^\]]+\]\(([^):]+\.md)\)", skill_text)
        }
        missing_links = sorted(
            relative_path
            for relative_path in linked_paths
            if not (installed / relative_path).is_file()
        )
        if missing_links:
            for relative_path in missing_links:
                print(f"ERROR: missing linked skill resource: {relative_path}")
            return 1

        validator = installed / "scripts" / "validate_handoff.py"
        result = subprocess.run(
            [sys.executable, str(validator), "--self-test"],
            cwd=temporary,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            return result.returncode

    print("PASS: isolated skill installation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
