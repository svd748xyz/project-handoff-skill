#!/usr/bin/env python3
"""Regression tests for the format-4 session handoff validator and safe save."""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "project-handoff" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import manage_handoff  # noqa: E402
import validate_handoff as validator  # noqa: E402


def sample_document(
    *,
    revision: str = "not-a-git-repository",
    state: str = "not-a-git-repository",
    scope: str = "Recenter the handoff skill on single-session distillation.",
) -> str:
    return f"""<!-- project-handoff-meta
format-version: 4
updated-at: 2026-10-27T10:00:00+08:00
session-scope: {scope}
source-revision: {revision}
working-tree-state: {state}
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


class ValidatorTests(unittest.TestCase):
    def test_valid_document_passes(self):
        report = validator.validate_text(sample_document())
        self.assertEqual([], report.errors)
        self.assertEqual(0, report.exit_code())

    def test_missing_section_fails(self):
        head, blocks = validator._split_sections(sample_document())
        text = validator._join_sections(
            head, [block for block in blocks if block[0] != "verification"]
        )
        report = validator.validate_text(text)
        self.assertTrue(any("verification" in error for error in report.errors))

    def test_section_order_is_enforced(self):
        text = validator._swap_sections(sample_document(), "goal", "work")
        report = validator.validate_text(text)
        self.assertTrue(any("in order" in error for error in report.errors))

    def test_duplicate_section_fails(self):
        head, blocks = validator._split_sections(sample_document())
        text = validator._join_sections(head, blocks + [blocks[0]])
        report = validator.validate_text(text)
        self.assertTrue(any("must appear once" in error for error in report.errors))

    def test_empty_section_fails(self):
        text = validator._empty_section(sample_document(), "goal")
        report = validator.validate_text(text)
        self.assertTrue(any("'goal' is empty" in error for error in report.errors))

    def test_wrong_format_version_fails(self):
        text = sample_document().replace("format-version: 4", "format-version: 3")
        report = validator.validate_text(text)
        self.assertTrue(any("format-version" in error for error in report.errors))

    def test_missing_metadata_key_fails(self):
        text = sample_document().replace("session-scope: ", "unused-scope: ")
        report = validator.validate_text(text)
        self.assertTrue(any("session-scope" in error for error in report.errors))

    def test_updated_at_requires_timezone(self):
        text = sample_document().replace(
            "2026-10-27T10:00:00+08:00", "2026-10-27T10:00:00"
        )
        report = validator.validate_text(text)
        self.assertTrue(any("timezone" in error for error in report.errors))

    def test_verified_claim_requires_evidence(self):
        text = sample_document().replace(
            "`python -m pytest tools -q` 在 2026-10-27 通过，18 passed。", "测试通过。"
        )
        report = validator.validate_text(text)
        self.assertTrue(any("needs a command" in error for error in report.errors))

    def test_verified_claim_with_command_passes(self):
        report = validator.validate_text(sample_document())
        self.assertFalse(any("needs a command" in error for error in report.errors))

    def test_legacy_status_label_rejected(self):
        text = sample_document().replace("[待确认]", "[进行中]")
        report = validator.validate_text(text)
        self.assertTrue(
            any("unsupported status label" in error for error in report.errors)
        )

    def test_secret_is_rejected(self):
        text = sample_document().replace(
            "把技能从项目状态档案改成会话提炼。", "password: hunter2"
        )
        report = validator.validate_text(text)
        self.assertTrue(any("secret assignment" in error for error in report.errors))

    def test_oversized_document_is_rejected(self):
        text = sample_document() + "\n" + "x" * (validator.LENGTH_LIMIT + 100)
        report = validator.validate_text(text)
        self.assertTrue(any("too large" in error for error in report.errors))

    def test_wrong_heading_fails(self):
        text = sample_document().replace("## 验证情况", "## 别的标题")
        report = validator.validate_text(text)
        self.assertTrue(any("must start with" in error for error in report.errors))


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="project-handoff-save-")
        self.root = Path(self.temp.name)
        self.target = self.root / validator.TARGET_NAME
        self.candidate = self.root / (validator.TARGET_NAME + ".candidate")

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = manage_handoff.main(list(args))
        return code, output.getvalue()

    def test_prepare_prints_metadata_without_writing(self):
        code, output = self._run(
            "prepare", "--root", str(self.root), "--session-scope", "test scope"
        )
        self.assertEqual(0, code)
        self.assertIn("format-version: 4", output)
        self.assertIn("session-scope: test scope", output)
        self.assertIn("source-revision: not-a-git-repository", output)
        self.assertFalse(self.target.exists())

    def test_prepare_rejects_multiline_scope(self):
        with self.assertRaises(ValueError):
            manage_handoff.prepare(self.root, "line one\nline two")

    def test_preview_writes_nothing(self):
        self.candidate.write_text(sample_document(), encoding="utf-8")
        code, output = self._run("save", "--root", str(self.root), "--preview")
        self.assertEqual(0, code)
        self.assertIn("PASS", output)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.candidate.exists())

    def test_save_creates_and_reads_back(self):
        self.candidate.write_text(sample_document(), encoding="utf-8")
        code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(0, code)
        self.assertIn("SAVED", output)
        self.assertEqual(sample_document(), self.target.read_text(encoding="utf-8"))
        self.assertFalse(self.candidate.exists())

    def test_save_updates_existing(self):
        self.target.write_text(sample_document(scope="old scope"), encoding="utf-8")
        self.candidate.write_text(sample_document(scope="new scope"), encoding="utf-8")
        code, _ = self._run("save", "--root", str(self.root))
        self.assertEqual(0, code)
        self.assertIn("new scope", self.target.read_text(encoding="utf-8"))

    def test_invalid_candidate_preserves_target_and_candidate(self):
        self.target.write_text(sample_document(scope="old scope"), encoding="utf-8")
        broken = sample_document(scope="new scope").replace(
            "## 验证情况", "## 错误标题"
        )
        self.candidate.write_text(broken, encoding="utf-8")
        code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(1, code)
        self.assertIn("must start with", output)
        self.assertIn("old scope", self.target.read_text(encoding="utf-8"))
        self.assertTrue(self.candidate.exists())

    def test_target_change_during_save_aborts(self):
        self.target.write_text(sample_document(scope="old scope"), encoding="utf-8")
        self.candidate.write_text(sample_document(scope="new scope"), encoding="utf-8")
        original = validator.validate_text
        calls = {"count": 0}

        def racing_validate(text, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                self.target.write_text(
                    sample_document(scope="concurrent writer"), encoding="utf-8"
                )
            return original(text, *args, **kwargs)

        with mock.patch.object(
            manage_handoff.validator, "validate_text", side_effect=racing_validate
        ):
            code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(1, code)
        self.assertIn("changed while saving", output)
        self.assertIn("concurrent writer", self.target.read_text(encoding="utf-8"))

    def test_candidate_not_utf8_fails(self):
        self.candidate.write_bytes(b"\xff\xfe")
        code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(1, code)
        self.assertIn("UTF-8", output)

    def test_missing_candidate_fails(self):
        code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(1, code)
        self.assertIn("candidate not found", output)

    def test_directory_target_is_rejected(self):
        self.target.mkdir()
        self.candidate.write_text(sample_document(), encoding="utf-8")
        code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(1, code)
        self.assertIn("regular files", output)

    def test_strict_warnings_block_save(self):
        text = sample_document() + "\n- example@example.com\n"
        self.candidate.write_text(text, encoding="utf-8")
        code, output = self._run("save", "--root", str(self.root), "--strict")
        self.assertEqual(1, code)
        self.assertIn("possible email", output)
        self.assertFalse(self.target.exists())

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_prepare_reads_git_revision_and_state(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "a.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=test@example.com",
                "-c",
                "user.name=test",
                "commit",
                "-qm",
                "init",
            ],
            cwd=self.root,
            check=True,
        )
        block = manage_handoff.prepare(self.root, "git session")
        self.assertRegex(block, r"source-revision: [0-9a-f]{40}")
        self.assertIn("working-tree-state: clean", block)

        (self.root / "a.txt").write_text("changed", encoding="utf-8")
        block = manage_handoff.prepare(self.root, "git session")
        self.assertIn("working-tree-state: dirty", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
