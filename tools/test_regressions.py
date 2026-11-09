#!/usr/bin/env python3
"""Regression tests for the format-5 session handoff validator and helper."""

from __future__ import annotations

import contextlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "project-handoff"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import manage_handoff  # noqa: E402
import validate_handoff as validator  # noqa: E402

SAMPLE_SCOPE = "Recenter the handoff skill on single-session distillation."
VERIFIED_EVIDENCE = "`python -m pytest tools -q` 在 2026-11-09 通过，18 passed。"
CONSTRAINT_TEXT = "回复用中文；"


def sample_document(
    *,
    revision: str = "not-a-git-repository",
    state: str = "not-a-git-repository",
    scope: str = SAMPLE_SCOPE,
) -> str:
    return (
        validator._sample_document()
        .replace(f"session-scope: {SAMPLE_SCOPE}", f"session-scope: {scope}")
        .replace("source-revision: not-a-git-repository", f"source-revision: {revision}")
        .replace(
            "working-tree-state: not-a-git-repository", f"working-tree-state: {state}"
        )
    )


def skill_template() -> str:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"```markdown\n(<!-- project-handoff-meta.*?)```", text, re.DOTALL)
    assert match, "SKILL.md must contain the markdown template"
    return match.group(1)


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


class ValidatorTests(unittest.TestCase):
    def assertError(self, text: str, fragment: str) -> None:
        errors = validator.validate_text(text).errors
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_valid_document_passes(self):
        report = validator.validate_text(sample_document())
        self.assertEqual([], report.errors)
        self.assertEqual([], report.warnings)
        self.assertEqual(0, report.exit_code())

    def test_missing_section_fails(self):
        head, blocks = validator._split_sections(sample_document())
        text = validator._join_sections(
            head, [block for block in blocks if block[0] != "constraints"]
        )
        self.assertError(text, "constraints")

    def test_section_order_is_enforced(self):
        text = validator._swap_sections(sample_document(), "goal", "constraints")
        self.assertError(text, "in order")

    def test_duplicate_section_fails(self):
        head, blocks = validator._split_sections(sample_document())
        self.assertError(validator._join_sections(head, blocks + [blocks[0]]), "must appear once")

    def test_empty_section_fails(self):
        self.assertError(validator._empty_section(sample_document(), "goal"), "'goal' is empty")

    def test_none_marker_fills_a_section(self):
        text = sample_document().replace("- 回复用中文；未经确认不要提交或推送（承接上次）。", "- 无")
        self.assertEqual([], validator.validate_text(text).errors)

    def test_wrong_format_version_fails(self):
        self.assertError(
            sample_document().replace("format-version: 5", "format-version: 4"),
            "format-version",
        )

    def test_missing_metadata_key_fails(self):
        self.assertError(
            sample_document().replace("session-scope: ", "unused-scope: "), "session-scope"
        )

    def test_updated_at_requires_timezone(self):
        text = sample_document().replace("2026-11-09T10:00:00+08:00", "2026-11-09T10:00:00")
        self.assertError(text, "timezone")

    def test_verified_claim_requires_evidence(self):
        self.assertError(sample_document().replace(VERIFIED_EVIDENCE, "测试通过。"), "needs a command")

    def test_legacy_status_label_rejected(self):
        self.assertError(
            sample_document().replace("[待确认]", "[进行中]"), "unsupported status label"
        )

    def test_next_requires_first_action_and_acceptance(self):
        self.assertError(sample_document().replace("第一个动作：", ""), "第一个动作")
        self.assertError(sample_document().replace("验收：", "然后"), "验收")

    def test_wrong_heading_fails(self):
        self.assertError(sample_document().replace("## 验证情况", "## 别的标题"), "must start with")

    def test_oversized_document_is_rejected(self):
        self.assertError(sample_document() + "\n" + "x" * (validator.LENGTH_LIMIT + 100), "too large")

    def test_long_document_warns(self):
        report = validator.validate_text(sample_document() + "\n" + "x" * validator.LENGTH_WARNING)
        self.assertEqual([], report.errors)
        self.assertTrue(any("long" in warning for warning in report.warnings))


class SecretTests(unittest.TestCase):
    def errors_for(self, line: str) -> list[str]:
        text = sample_document().replace(CONSTRAINT_TEXT, line + "；")
        return validator.validate_text(text).errors

    def test_plain_assignment_rejected(self):
        self.assertTrue(self.errors_for("password: hunter2"))

    def test_prefixed_env_var_rejected(self):
        self.assertTrue(self.errors_for("OPENAI_API_KEY=abc123def456ghi789"))
        self.assertTrue(self.errors_for("GITHUB_TOKEN=abcdef123456"))

    def test_known_token_shapes_rejected(self):
        for token in (
            "sk-proj-" + "a" * 32,
            "ghp_" + "a" * 36,
            "github_pat_" + "a" * 40,
            "xoxb-1234567890-abcdef",
            "AIza" + "a" * 35,
        ):
            with self.subTest(token=token[:8]):
                self.assertTrue(
                    any("API token" in error for error in self.errors_for(f"见 {token}"))
                )

    def test_references_and_redactions_accepted(self):
        for line in (
            "OPENAI_API_KEY=$OPENAI_API_KEY",
            "api_key: <redacted>",
            "token: 已过期",
            "max_tokens=4096",
            "password: %DB_PASSWORD%",
        ):
            with self.subTest(line=line):
                self.assertEqual([], self.errors_for(line))


class TemplateTests(unittest.TestCase):
    def test_skill_template_matches_validator_sections(self):
        template = skill_template()
        ids = re.findall(r"<!-- section: ([a-z0-9-]+) -->", template)
        self.assertEqual(list(validator.SECTION_IDS), ids)
        for section, title in validator.SECTIONS:
            self.assertIn(f"## {title}", template)
        quote = lambda text: next(line for line in text.splitlines() if line.startswith("> "))  # noqa: E731
        self.assertEqual(quote(sample_document()), quote(template))

    def test_unfilled_template_reports_every_placeholder(self):
        block = manage_handoff.prepare(Path(tempfile.gettempdir()), "template check")
        template = re.sub(
            r"<!-- project-handoff-meta.*?-->", lambda _: block, skill_template(), flags=re.DOTALL
        )
        errors = validator.validate_text(template).errors
        placeholder_errors = " ".join(e for e in errors if "placeholder" in e)
        body = re.sub(r"<!--.*?-->", "", template, flags=re.DOTALL)
        placeholders = re.findall(r"<[^<>\n]+>", body)
        self.assertGreaterEqual(len(placeholders), 11)
        for placeholder in placeholders:
            self.assertIn(placeholder, placeholder_errors)

    def test_whole_line_placeholder_rejected(self):
        text = sample_document().replace(
            "- 重写 `SKILL.md` 为八节会话模板。", "<each changed area and its result>"
        )
        self.assertTrue(any("placeholder" in e for e in validator.validate_text(text).errors))


class HelperTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="project-handoff-save-")
        self.root = Path(self.temp.name).resolve()
        self.target = self.root / validator.TARGET_NAME
        self.candidate = self.root / (validator.TARGET_NAME + ".candidate")

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = manage_handoff.main(list(args))
        return code, output.getvalue()


class SaveTests(HelperTestCase):
    def test_prepare_prints_metadata_without_writing(self):
        code, output = self._run("prepare", "--root", str(self.root), "--session-scope", "test scope")
        self.assertEqual(0, code)
        self.assertIn("format-version: 5", output)
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

    def test_save_without_hard_links_falls_back(self):
        self.candidate.write_text(sample_document(), encoding="utf-8")
        with mock.patch.object(manage_handoff.os, "link", side_effect=OSError("no links")):
            code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(0, code, output)
        self.assertEqual(sample_document(), self.target.read_text(encoding="utf-8"))
        self.assertFalse(self.candidate.exists())

    def test_save_reports_warnings_on_success(self):
        self.candidate.write_text(sample_document() + "\n- example@example.com\n", encoding="utf-8")
        code, output = self._run("save", "--root", str(self.root))
        self.assertEqual(0, code)
        self.assertIn("WARNING: possible email", output)

    def test_save_updates_existing(self):
        self.target.write_text(sample_document(scope="old scope"), encoding="utf-8")
        self.candidate.write_text(sample_document(scope="new scope"), encoding="utf-8")
        code, _ = self._run("save", "--root", str(self.root))
        self.assertEqual(0, code)
        self.assertIn("new scope", self.target.read_text(encoding="utf-8"))

    def test_invalid_candidate_preserves_target_and_candidate(self):
        self.target.write_text(sample_document(scope="old scope"), encoding="utf-8")
        broken = sample_document(scope="new scope").replace("## 验证情况", "## 错误标题")
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
                self.target.write_text(sample_document(scope="concurrent writer"), encoding="utf-8")
            return original(text, *args, **kwargs)

        with mock.patch.object(manage_handoff.validator, "validate_text", side_effect=racing_validate):
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
        self.candidate.write_text(sample_document() + "\n- example@example.com\n", encoding="utf-8")
        code, output = self._run("save", "--root", str(self.root), "--strict")
        self.assertEqual(1, code)
        self.assertIn("possible email", output)
        self.assertFalse(self.target.exists())


class InspectTests(HelperTestCase):
    def test_inspect_without_git_or_handoff(self):
        code, output = self._run("inspect", "--root", str(self.root))
        self.assertEqual(0, code)
        self.assertIn("previous-handoff: none", output)
        self.assertIn("current-revision: not-a-git-repository", output)
        self.assertFalse(self.target.exists())

    def test_inspect_warns_about_leftover_candidate(self):
        self.candidate.write_text("x", encoding="utf-8")
        _, output = self._run("inspect", "--root", str(self.root))
        self.assertIn("leftover candidate", output)

    def test_inspect_reads_older_format_metadata(self):
        self.target.write_text(
            sample_document(scope="old session").replace("format-version: 5", "format-version: 4"),
            encoding="utf-8",
        )
        _, output = self._run("inspect", "--root", str(self.root))
        self.assertIn("previous-format-version: 4", output)
        self.assertIn("previous-session-scope: old session", output)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitTests(HelperTestCase):
    def setUp(self):
        super().setUp()
        git(self.root, "init", "-q")
        (self.root / "a.txt").write_text("x", encoding="utf-8")
        git(self.root, "add", "a.txt")
        git(self.root, "commit", "-qm", "init")
        self.base = manage_handoff._git_metadata(self.root)[0]

    def test_prepare_reads_git_revision_and_state(self):
        block = manage_handoff.prepare(self.root, "git session")
        self.assertRegex(block, r"source-revision: [0-9a-f]{40}")
        self.assertIn("working-tree-state: clean", block)

        (self.root / "a.txt").write_text("changed", encoding="utf-8")
        block = manage_handoff.prepare(self.root, "git session")
        self.assertIn("working-tree-state: dirty", block)

    def test_handoff_files_do_not_make_tree_dirty(self):
        self.target.write_text(sample_document(), encoding="utf-8")
        self.candidate.write_text(sample_document(), encoding="utf-8")
        self.assertEqual("clean", manage_handoff._git_metadata(self.root)[1])

    def test_inspect_reports_commits_and_changes_since_baseline(self):
        self.target.write_text(sample_document(revision=self.base, state="clean"), encoding="utf-8")
        (self.root / "b.txt").write_text("y", encoding="utf-8")
        git(self.root, "add", "b.txt")
        git(self.root, "commit", "-qm", "add b during session")
        (self.root / "新文件.txt").write_text("n", encoding="utf-8")

        _, output = self._run("inspect", "--root", str(self.root))
        self.assertIn(f"baseline: {self.base}", output)
        self.assertIn("commits-since-baseline: 1", output)
        self.assertIn("add b during session", output)
        self.assertIn("b.txt", output)
        self.assertIn("?? 新文件.txt", output)
        self.assertNotIn(f"?? {validator.TARGET_NAME}", output)

    def test_inspect_flags_unknown_baseline(self):
        self.target.write_text(sample_document(revision="f" * 40, state="clean"), encoding="utf-8")
        _, output = self._run("inspect", "--root", str(self.root))
        self.assertIn("not in this repository", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
