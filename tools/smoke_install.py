#!/usr/bin/env python3
"""Copy the skill to an isolated directory and verify it remains self-contained."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "project-handoff"


def _run(command: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


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
        result = _run([sys.executable, "-B", str(validator), "--self-test"], temporary)
        if result.returncode != 0:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            return result.returncode

        helper = installed / "scripts" / "manage_handoff.py"
        result = _run([sys.executable, "-B", str(helper), "--help"], temporary)
        if result.returncode != 0:
            print(result.stderr, end="", file=sys.stderr)
            return result.returncode

        result = _run(
            [
                sys.executable,
                "-B",
                str(helper),
                "prepare",
                "--root",
                temporary,
                "--session-scope",
                "isolated install smoke test",
            ],
            temporary,
        )
        if result.returncode != 0 or "format-version: 5" not in result.stdout:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            print("ERROR: prepare did not produce format-5 metadata")
            return 1

        result = _run([sys.executable, "-B", str(helper), "inspect", "--root", temporary], temporary)
        if result.returncode != 0 or "previous-handoff: none" not in result.stdout:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            print("ERROR: inspect did not run in the isolated installation")
            return 1

        transcript = Path(temporary) / "session.jsonl"
        transcript.write_text(
            json.dumps({"type": "USER_INPUT", "content": "<USER_REQUEST>Reply in Chinese</USER_REQUEST>"})
            + "\n",
            encoding="utf-8",
        )
        result = _run(
            [sys.executable, "-B", str(helper), "recall", "--transcript", str(transcript)],
            temporary,
        )
        if result.returncode != 0 or "[1] Reply in Chinese" not in result.stdout:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            print("ERROR: recall did not extract user turn in the isolated installation")
            return 1

        body_only = Path(temporary) / "项目开发交接.md.candidate"
        body_only.write_text(
            """# 项目开发交接

> 新会话先读本文件，核对仓库状态，再从“下一步”的第一个动作继续；未验证项不要当作已完成。

<!-- section: goal -->
## 目标与进度
- 烟雾测试。

<!-- section: constraints -->
## 用户偏好与约束
- 无

<!-- section: work -->
## 做了什么
- 无

<!-- section: decisions -->
## 关键决策与理由
- 无

<!-- section: verification -->
## 验证情况
- 无

<!-- section: pitfalls -->
## 踩坑与失败路径
- 无

<!-- section: open -->
## 未决问题
- 无

<!-- section: next -->
## 下一步
- 第一个动作：运行测试；验收：全部通过。
- 先读：无
""",
            encoding="utf-8",
        )
        result = _run(
            [
                sys.executable,
                "-B",
                str(helper),
                "save",
                "--root",
                temporary,
                "--session-scope",
                "isolated save smoke test",
                "--preview",
            ],
            temporary,
        )
        if result.returncode != 0 or "PASS:" not in result.stdout:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            print("ERROR: save --session-scope --preview failed in isolated installation")
            return 1

    print("PASS: isolated skill installation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
