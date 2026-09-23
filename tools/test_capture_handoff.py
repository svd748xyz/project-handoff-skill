#!/usr/bin/env python3
"""Offline acceptance checks for lossless, recoverable raw tool capture."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "project-handoff" / "scripts"))
import capture_handoff as c
import process_handoff as p

PROJECT = "82d52569-6838-4fb1-aa5e-c05425713211"
OTHER_PROJECT = "7cd6432d-f8c8-4e80-8b9c-9bd80f058fe7"


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="capture-handoff-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.input = self.root / "工具输出.txt"
        self.context = {"project_id": PROJECT, "goal": "Repair parser", "boundaries": ["Local verification only"],
                        "next_action": "Read relevant failures and repeat local parser validation"}

    def capture(self, text="Local tool process completed.", **kwargs):
        self.input.write_bytes(text.encode("utf-8"))
        return c.capture_file(self.store, self.input, self.context, **kwargs)

    def manifest(self, result):
        return json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))

    def events(self, result):
        manifest = self.manifest(result)
        return [p.read_json(self.store / "events" / (part["event_id"] + ".json")) for part in manifest["chunks"]]

    def snapshot(self):
        return {str(path.relative_to(self.store)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.store.rglob("*") if path.is_file()}

    def assert_roundtrip(self, text, result):
        manifest = self.manifest(result)
        self.assertEqual(Path(result["source_path"]).read_bytes(), text.encode("utf-8"))
        recovered = []
        end = 0
        for part, event in zip(manifest["chunks"], self.events(result)):
            self.assertEqual(part["start_char"], end)
            end = part["end_char"]
            raw = json.loads(event["excerpt"]) if part["excerpt_encoding"] == "json-string" else event["excerpt"]
            self.assertEqual(raw, text[part["start_char"]:end])
            self.assertEqual(part["content_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
            self.assertEqual(part["event_sha256"], hashlib.sha256(p.canonical(event)).hexdigest())
            self.assertLessEqual(len(event["excerpt"]), 6000)
            self.assertNotIn("claim", event)
            self.assertIn(f"#chars={part['start_char']}:{end};", event["source"])
            self.assertIn(f"total={len(text)};", event["source"])
            self.assertEqual(event["scope"], manifest["scope"])
            recovered.append(raw)
        self.assertEqual(end, len(text))
        self.assertEqual("".join(recovered), text)

    def test_preserves_full_middle_tail_and_line_boundaries_without_model(self):
        text = "BEGIN\r\n" + ("routine output\r\n" * 800) + "MIDDLE IMPORTANT ERROR\r\n" + ("later output\n" * 650) + "END RECOVERY ID"
        with patch.object(p, "ask") as network:
            result = self.capture(text)
        network.assert_not_called()
        self.assertGreater(result["event_count"], 2)
        self.assert_roundtrip(text, result)
        self.assertTrue(all(event["excerpt"].endswith("\n") for event in self.events(result)[:-1]))

    def test_unicode_bom_long_line_and_local_filename_remain_recoverable(self):
        text = "\ufeff" + "中文😀e\u0301" * 2100 + "终点"
        result = self.capture(text)
        self.assert_roundtrip(text, result)
        manifest = self.manifest(result)
        self.assertEqual(manifest["source"], self.input.name)
        self.assertNotIn(str(self.root), json.dumps(manifest, ensure_ascii=False))
        self.assertNotIn(str(self.root), json.dumps(self.events(result), ensure_ascii=False))

    def test_whitespace_blocks_are_lossless_and_within_existing_schema(self):
        text = "START\n" + "\x1c\t\n " * 6000 + "TAIL"
        result = self.capture(text)
        self.assert_roundtrip(text, result)
        self.assertIn("json-string", {chunk["excerpt_encoding"] for chunk in self.manifest(result)["chunks"]})

    def test_all_whitespace_output_is_preserved(self):
        text = "\t\n " * 5000
        result = self.capture(text)
        self.assert_roundtrip(text, result)

    def test_repeat_does_not_change_content_timestamp_or_file_mtime(self):
        result = self.capture("Identical output\n" * 900)
        before = self.snapshot()
        repeated = c.capture_file(self.store, self.input, self.context)
        self.assertEqual(result["capture_id"], repeated["capture_id"])
        self.assertEqual(repeated["recorded_count"], 0)
        self.assertEqual(repeated["unchanged_count"], result["event_count"])
        self.assertEqual(before, self.snapshot())

    def test_context_goal_change_does_not_rewrite_same_observation(self):
        result = self.capture()
        before = self.snapshot()
        changed_context = {**self.context, "goal": "New continuation goal"}
        repeated = c.capture_file(self.store, self.input, changed_context)
        self.assertEqual(result["capture_id"], repeated["capture_id"])
        self.assertEqual(before, self.snapshot())

    def test_changed_scope_creates_separate_immutable_observation(self):
        first = self.capture(scope="First local execution")
        first_source = Path(first["source_path"]).read_bytes()
        second = c.capture_file(self.store, self.input, self.context, scope="Second local execution")
        self.assertNotEqual(first["capture_id"], second["capture_id"])
        self.assertEqual(Path(first["source_path"]).read_bytes(), first_source)

    def test_modified_saved_source_is_never_overwritten(self):
        result = self.capture()
        Path(result["source_path"]).write_text("corrupted saved source", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, self.input, self.context)
        self.assertEqual(before, self.snapshot())

    def test_modified_manifest_is_never_overwritten(self):
        result = self.capture()
        manifest = self.manifest(result)
        manifest["chunks"][0]["end_char"] += 1
        Path(result["manifest_path"]).write_text(json.dumps(manifest), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, self.input, self.context)
        self.assertEqual(before, self.snapshot())

    def test_modified_event_is_detected_before_any_capture_write(self):
        result = self.capture()
        event = self.events(result)[0]
        path = self.store / "events" / (event["id"] + ".json")
        event["excerpt"] = "Changed evidence"
        path.write_bytes(p.canonical(event))
        before = self.snapshot()
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, self.input, self.context)
        self.assertEqual(before, self.snapshot())

    def test_sensitive_input_crossing_chunk_boundary_is_refused_before_copies(self):
        text = "a" * 5980 + "\npassword=must-not-be-copied\nTAIL"
        with self.assertRaises(p.ProcessError):
            self.capture(text)
        self.assertFalse(self.store.exists())
        self.assertEqual(self.input.read_text(encoding="utf-8"), text)

    def test_configured_key_is_refused_without_echo(self):
        marker = "configured-test-value-123456789"
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": marker}):
            with self.assertRaises(p.ProcessError) as error:
                self.capture("output contains " + marker)
        self.assertNotIn(marker, str(error.exception))
        self.assertFalse(self.store.exists())

    def test_wrong_project_is_refused_without_changes(self):
        self.capture()
        before = self.snapshot()
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, self.input, {**self.context, "project_id": OTHER_PROJECT})
        self.assertEqual(before, self.snapshot())

    def test_nonempty_store_without_identity_is_not_adopted(self):
        self.store.mkdir()
        (self.store / "existing.txt").write_text("owned content", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(p.ProcessError):
            self.capture()
        self.assertEqual(before, self.snapshot())

    def test_invalid_metadata_and_context_are_rejected_before_writes(self):
        for arguments in ({"kind": "claim"}, {"stage": "invented"}, {"outcome": "accepted"},
                          {"scope": ""}, {"scope": "s" * 3501}, {"source": "../private.txt"},
                          {"source": "C:\\private\\tool.txt"}, {"source": "/private/tool.txt"}):
            with self.subTest(arguments=arguments):
                with self.assertRaises(p.ProcessError):
                    self.capture(**arguments)
                self.assertFalse(self.store.exists())
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, self.input, {**self.context, "project_id": "not-a-uuid"})
        self.assertFalse(self.store.exists())

    def test_invalid_utf8_empty_nul_and_oversize_input_are_rejected(self):
        for data in (b"\xff", b"", b"A\x00B"):
            with self.subTest(data=data):
                self.input.write_bytes(data)
                with self.assertRaises(p.ProcessError):
                    c.capture_file(self.store, self.input, self.context)
                self.assertFalse(self.store.exists())
        self.input.write_bytes(b"a" * 101)
        with patch.object(c, "MAX_CAPTURE_BYTES", 100):
            with self.assertRaises(p.ProcessError):
                c.capture_file(self.store, self.input, self.context)
        self.assertFalse(self.store.exists())

    def test_failure_and_unknown_outcomes_are_preserved(self):
        for outcome in ("failure", "unknown"):
            result = self.capture("Diagnostic output\n" * 1000, outcome=outcome)
            self.assertTrue(all(event["outcome"] == outcome for event in self.events(result)))

    def test_event_failure_retry_fills_missing_without_retimestamping(self):
        self.input.write_text("long tool output\n" * 1200, encoding="utf-8")
        actual_record = c.record_event
        count = 0
        def fail_second(store, event):
            nonlocal count
            count += 1
            if count == 2:
                raise p.ProcessError("injected event write failure")
            return actual_record(store, event)
        with patch.object(c, "record_event", side_effect=fail_second):
            with self.assertRaises(p.ProcessError):
                c.capture_file(self.store, self.input, self.context)
        first_event_path = next((self.store / "events").glob("*.json"))
        first_event = first_event_path.read_bytes()
        manifest_path = next((self.store / "captured").glob("*/manifest.json"))
        first_manifest = manifest_path.read_bytes()
        result = c.capture_file(self.store, self.input, self.context)
        self.assertEqual(result["unchanged_count"], 1)
        self.assertEqual(result["recorded_count"], result["event_count"] - 1)
        self.assertEqual(first_event_path.read_bytes(), first_event)
        self.assertEqual(manifest_path.read_bytes(), first_manifest)
        self.assert_roundtrip(self.input.read_bytes().decode("utf-8"), result)

    def test_publication_failure_exposes_no_partial_source_and_can_retry(self):
        self.input.write_text("tool output\n", encoding="utf-8")
        actual_write = c._write_new
        def fail_source(path, data):
            if path.name == "source.txt":
                raise p.ProcessError("injected source write failure")
            return actual_write(path, data)
        with patch.object(c, "_write_new", side_effect=fail_source):
            with self.assertRaises(p.ProcessError):
                c.capture_file(self.store, self.input, self.context)
        self.assertEqual(list((self.store / "captured").iterdir()), [])
        self.assertFalse((self.store / ".capture.lock").exists())
        result = c.capture_file(self.store, self.input, self.context)
        self.assertEqual(result["recorded_count"], 1)

    def test_manifest_above_general_json_limit_can_be_reused(self):
        result = self.capture("z" * 2_500_000)
        self.assertGreater(Path(result["manifest_path"]).stat().st_size, p.MAX_JSON_BYTES)
        repeated = c.capture_file(self.store, self.input, self.context)
        self.assertEqual(repeated["unchanged_count"], result["event_count"])
        self.assertEqual(repeated["recorded_count"], 0)

    def test_parent_traversal_is_rejected_without_creating_store(self):
        self.input.write_text("tool output", encoding="utf-8")
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, self.root / "child" / ".." / self.input.name, self.context)
        self.assertFalse(self.store.exists())

    def test_hardlinked_input_is_rejected(self):
        self.input.write_text("tool output", encoding="utf-8")
        link = self.root / "hardlink.txt"
        try:
            os.link(self.input, link)
        except OSError:
            self.skipTest("filesystem does not allow file hardlinks")
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, link, self.context)
        self.assertFalse(self.store.exists())

    def test_existing_capture_symlink_is_rejected(self):
        result = self.capture()
        source = Path(result["source_path"])
        saved = source.read_bytes()
        source.unlink()
        try:
            source.symlink_to(self.input)
        except OSError:
            source.write_bytes(saved)
            self.skipTest("filesystem does not allow symlinks")
        with self.assertRaises(p.ProcessError):
            c.capture_file(self.store, self.input, self.context)

    def test_cli_outputs_only_recovery_metadata_and_sanitized_failure(self):
        sentinel = "SENTINEL RAW TEXT NOT FOR STDOUT"
        self.input.write_text(sentinel, encoding="utf-8")
        context_path = self.root / "context.json"
        context_path.write_text(json.dumps(self.context), encoding="utf-8")
        arguments = ["--store", str(self.store), "--input", str(self.input), "--context", str(context_path)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(c.main(arguments), 0)
        self.assertNotIn(sentinel, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["event_count"], 1)
        self.input.write_text("password=do-not-echo-this", encoding="utf-8")
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(c.main(arguments), 1)
        self.assertNotIn("do-not-echo-this", error.getvalue())


if __name__ == "__main__":
    unittest.main()
