#!/usr/bin/env python3
"""Behavioral regressions for snapshot, validation, and optimistic saving."""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "project-handoff" / "scripts"))
import validate_handoff as v
import manage_handoff as manager


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="handoff-regression-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.requirements = self.root / "requirements.md"
        self.requirements.write_text("baseline\n", encoding="utf-8")
        self.valid = v._sample_document(self.root, ["requirements.md"])
        self.target = self.root / manager.TARGET_NAME
        self.candidate = self.root / (manager.TARGET_NAME + ".candidate")

    def git(self, *args):
        result = v._run_git(self.root, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def repo(self):
        if not shutil.which("git"):
            self.skipTest("Git is unavailable")
        self.git("init", "--quiet")
        self.git("config", "user.name", "Handoff Test")
        self.git("config", "user.email", "handoff@example.invalid")
        self.git("config", "core.hooksPath", str(self.root / "no-hooks"))
        self.git("config", "commit.gpgsign", "false")
        self.git("add", "requirements.md")
        self.git("commit", "--quiet", "-m", "baseline")

    def draft(self, critical=None):
        block = manager.prepare(self.root, self.root, "example-parser", "workspace inspected",
                                ["requirements.md"] if critical is None else critical)
        text = v.META_BLOCK_RE.sub(lambda _: block, self.valid, count=1)
        self.candidate.write_text(text, encoding="utf-8")
        return text

    def save(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return manager.save(self.root, self.root, **kwargs)

    def test_dirty_file_edited_again_is_stale(self):
        self.repo()
        self.requirements.write_text("first dirty", encoding="utf-8")
        text = self.draft(critical=[])
        self.requirements.write_text("second dirty", encoding="utf-8")
        report = v.validate_text(text, current_root=self.root)
        self.assertEqual(report.exit_code(), 2)

    def test_staged_content_changes_with_same_working_bytes(self):
        self.repo()
        self.requirements.write_text("stage A", encoding="utf-8")
        self.git("add", "requirements.md")
        self.requirements.write_text("working", encoding="utf-8")
        first = v._git_snapshot(self.root)
        self.requirements.write_text("stage B", encoding="utf-8")
        self.git("add", "requirements.md")
        self.requirements.write_text("working", encoding="utf-8")
        self.assertNotEqual(first, v._git_snapshot(self.root))

    def test_untracked_file_content_and_nested_membership(self):
        self.repo()
        folder = self.root / "new files"
        folder.mkdir()
        path = folder / "中文.txt"
        path.write_bytes(b"one")
        first = v._git_snapshot(self.root)
        path.write_bytes(b"two")
        second = v._git_snapshot(self.root)
        self.assertNotEqual(first, second)
        (folder / "extra.txt").write_bytes(b"new")
        self.assertNotEqual(second, v._git_snapshot(self.root))

    def test_rename_and_deletion(self):
        self.repo()
        self.git("mv", "requirements.md", "renamed file.md")
        first = v._git_snapshot(self.root)
        (self.root / "renamed file.md").unlink()
        self.assertNotEqual(first, v._git_snapshot(self.root))

    def test_unborn_repository(self):
        if not shutil.which("git"):
            self.skipTest("Git is unavailable")
        self.git("init", "--quiet")
        result = v._git_snapshot(self.root)
        self.assertEqual(result.revision, "unborn")
        self.assertEqual(result.tree_state, "dirty")

    def test_subdirectory_scope(self):
        self.repo()
        nested = self.root / "subproject"
        nested.mkdir()
        (nested / "app.txt").write_bytes(b"first")
        first = v._git_snapshot(nested)
        self.requirements.write_bytes(b"unrelated outside scope")
        self.assertEqual(first, v._git_snapshot(nested))
        (nested / "app.txt").write_bytes(b"second")
        self.assertNotEqual(first, v._git_snapshot(nested))

    def test_handoff_artifacts_excluded_but_nested_handoff_included(self):
        self.repo()
        first = v._git_snapshot(self.root)
        for suffix in ("", ".candidate", ".lock"):
            (self.root / (manager.TARGET_NAME + suffix)).write_bytes(b"handoff")
        self.assertEqual(first, v._git_snapshot(self.root))
        nested = self.root / "nested"
        nested.mkdir()
        (nested / manager.TARGET_NAME).write_bytes(b"another project")
        self.assertNotEqual(first, v._git_snapshot(self.root))

    def test_missing_git_uses_critical_files(self):
        with patch.object(v, "_run_git", side_effect=FileNotFoundError("no git")):
            report = v.validate_text(self.valid, current_root=self.root)
        self.assertEqual(report.exit_code(strict=True), 0)

    def test_git_permission_error_is_not_non_git(self):
        error = subprocess.CompletedProcess(["git"], 128, "", "fatal: detected dubious ownership")
        with patch.object(v, "_run_git", return_value=error):
            report = v.validate_text(self.valid, current_root=self.root)
        self.assertEqual(report.exit_code(), 1)
        self.assertTrue(report.errors)

    def test_nonexistent_root_rejected(self):
        with self.assertRaises(ValueError):
            v._git_snapshot(self.root / "missing")

    def test_plain_prose_table_and_nested_list_cannot_bypass(self):
        original = "1. 补充输入测试；验收条件：正常、空值和非法输入均有可复现结果。"
        for replacement in ("继续开发。", "| 继续开发 |", "1. 继续开发；验收条件：测试通过。\n   - 未定义验收的第二项"):
            with self.subTest(replacement=replacement):
                self.assertFalse(v.validate_text(self.valid.replace(original, replacement)).ok)

    def test_current_and_other_section_strong_claims_need_evidence(self):
        for label in ("[已验证]", "[用户验收]", "[已部署-已回读]"):
            text = self.valid.replace("[已实现][未验证] 解析入口已经存在。", label + " 全部功能完成。")
            self.assertFalse(v.validate_text(text).ok)
            text = self.valid.replace("实现本地解析器，不包含云端部署。", label + " 全部功能完成。")
            self.assertFalse(v.validate_text(text).ok)

    def test_session_relative_and_invalid_dates_rejected(self):
        for replacement in ("当前会话", "2026-99-31"):
            text = self.valid.replace("本次核验日期 2026-08-31", "核验日期 " + replacement)
            self.assertFalse(v.validate_text(text).ok)

    def test_scope_and_nonempty_acceptance_required(self):
        self.assertFalse(v.validate_text(self.valid.replace("证据范围为入口文件检查，", "")).ok)
        text = self.valid.replace("验收条件：正常、空值和非法输入均有可复现结果。", "验收条件：")
        self.assertFalse(v.validate_text(text).ok)

    def test_heading_cannot_hide_strong_claim(self):
        self.assertFalse(v.validate_text(self.valid + "\n## [已验证] 全部通过\n").ok)

    def test_indented_continuation_is_supported(self):
        text = self.valid.replace("1. 补充输入测试；验收条件：", "1. 补充输入测试；\n   验收条件：")
        self.assertTrue(v.validate_text(text).ok)

    def test_symlink_hashes_link_without_following_external_content(self):
        self.repo()
        with tempfile.TemporaryDirectory(prefix="handoff-external-") as external:
            source = Path(external) / "outside.txt"
            source.write_bytes(b"outside")
            link = self.root / "link.txt"
            try:
                link.symlink_to(source)
            except OSError:
                self.skipTest("symlinks require an unavailable OS permission")
            first = v._git_snapshot(self.root)
            source.write_bytes(b"changed outside")
            self.assertEqual(first, v._git_snapshot(self.root))
            link.unlink()
            link.symlink_to(Path(external) / "different.txt")
            self.assertNotEqual(first, v._git_snapshot(self.root))

    def test_dirty_submodule_content_changes(self):
        self.repo()
        with tempfile.TemporaryDirectory(prefix="handoff-submodule-") as external:
            source = Path(external)
            for args in (("init", "--quiet"), ("config", "user.name", "Handoff Test"),
                         ("config", "user.email", "handoff@example.invalid"),
                         ("config", "commit.gpgsign", "false"),
                         ("config", "core.hooksPath", str(source / "no-hooks"))):
                result = v._run_git(source, *args)
                self.assertEqual(result.returncode, 0, result.stderr)
            (source / "file.txt").write_bytes(b"base")
            self.assertEqual(v._run_git(source, "add", "file.txt").returncode, 0)
            self.assertEqual(v._run_git(source, "commit", "--quiet", "-m", "base").returncode, 0)
            self.git("-c", "protocol.file.allow=always", "submodule", "add", "--quiet", str(source), "nested")
            self.git("commit", "--quiet", "-am", "add local submodule")
            path = self.root / "nested" / "file.txt"
            path.write_bytes(b"dirty first")
            first = v._git_snapshot(self.root)
            path.write_bytes(b"dirty second")
            self.assertNotEqual(first, v._git_snapshot(self.root))

    def test_strict_failure_never_prints_pass(self):
        self.target.write_text(self.valid + "\n联系：person@example.com\n", encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = v.main([str(self.target), "--strict"])
        self.assertEqual(code, 1)
        self.assertNotIn("PASS:", output.getvalue())

    def test_limited_is_distinct_and_allow_limited_does_not_waive_stale(self):
        self.draft(critical=[])
        report = v.validate_file(self.candidate, current_root=self.root)
        self.assertEqual(report.exit_code(strict=True), 3, report)
        self.assertEqual(report.exit_code(strict=True, allow_limited=True), 0)
        report.stale.append("changed")
        self.assertEqual(report.exit_code(strict=True, allow_limited=True), 2)

    def test_prepare_read_only_and_preserves_identity_without_refreshing_claim_dates(self):
        before = sorted(self.root.iterdir())
        block = manager.prepare(self.root, self.root, "example-parser", "workspace", ["requirements.md"])
        self.assertEqual(before, sorted(self.root.iterdir()))
        self.target.write_text(v.META_BLOCK_RE.sub(lambda _: block, self.valid), encoding="utf-8")
        old_id = manager._metadata(block)["project-id"]
        text = self.draft()
        self.assertEqual(manager._metadata(text)["project-id"], old_id)
        self.assertIn("本次核验日期 2026-08-31", text)

    def test_preview_changes_no_files(self):
        self.draft()
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        self.assertEqual(self.save(preview=True), 0)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})

    def test_atomic_create_then_update_and_readback(self):
        text = self.draft()
        self.assertEqual(self.save(), 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), text)
        self.assertFalse(self.candidate.exists())
        text = self.draft().replace("尚未验证非法输入。", "等待确认新的输入边界。")
        self.candidate.write_text(text, encoding="utf-8")
        self.assertEqual(self.save(), 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), text)
        self.assertFalse((self.root / (manager.TARGET_NAME + ".lock")).exists())

    def test_git_save_does_not_invalidate_its_own_snapshot(self):
        self.repo()
        self.requirements.write_bytes(b"dirty")
        self.draft()
        self.assertEqual(self.save(), 0)
        report = v.validate_file(self.target, current_root=self.root)
        self.assertEqual(report.exit_code(strict=True), 0, report)

    def test_concurrent_target_change_preserved(self):
        self.target.write_text(self.valid, encoding="utf-8")
        self.draft()
        changed = self.valid + "\nConcurrent editor\n"
        self.target.write_text(changed, encoding="utf-8")
        with self.assertRaises(ValueError):
            self.save()
        self.assertEqual(self.target.read_text(encoding="utf-8"), changed)
        self.assertTrue(self.candidate.exists())

    def test_project_change_blocks_save_and_preserves_target(self):
        self.target.write_text(self.valid, encoding="utf-8")
        old = self.target.read_bytes()
        self.draft()
        self.requirements.write_bytes(b"new requirement")
        self.assertEqual(self.save(), 2)
        self.assertEqual(self.target.read_bytes(), old)

    def test_bad_candidate_and_identity_change_preserve_target(self):
        self.target.write_text(self.valid, encoding="utf-8")
        old = self.target.read_bytes()
        self.draft()
        text = self.candidate.read_text(encoding="utf-8").replace("[已实现][未验证]", "[已验证]")
        self.candidate.write_text(text, encoding="utf-8")
        self.assertEqual(self.save(), 1)
        self.assertEqual(self.target.read_bytes(), old)
        with self.assertRaises(ValueError):
            manager.prepare(self.root, self.root, "different-project", "workspace", [])

    def test_existing_lock_preserved(self):
        self.draft()
        lock = self.root / (manager.TARGET_NAME + ".lock")
        lock.write_bytes(b"another writer")
        with self.assertRaises(FileExistsError):
            self.save()
        self.assertEqual(lock.read_bytes(), b"another writer")
        self.assertFalse(self.target.exists())

    def test_replace_failure_preserves_target_and_candidate(self):
        self.target.write_text(self.valid, encoding="utf-8")
        old = self.target.read_bytes()
        self.draft()
        with patch.object(manager.os, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                self.save()
        self.assertEqual(self.target.read_bytes(), old)
        self.assertTrue(self.candidate.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
