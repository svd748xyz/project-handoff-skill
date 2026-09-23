#!/usr/bin/env python3
"""Offline regressions for immutable process records and conservative views."""

from __future__ import annotations

import contextlib
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
import process_handoff as p

PROJECT = "82d52569-6838-4fb1-aa5e-c05425713211"
OTHER_PROJECT = "7cd6432d-f8c8-4e80-8b9c-9bd80f058fe7"


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="process-handoff-")
        self.addCleanup(self.temp.cleanup)
        # macOS exposes its temporary root through /var -> /private/var.
        self.root = Path(self.temp.name).resolve()
        self.store = self.root / "store"
        self.context = {"project_id": PROJECT, "goal": "Implement parser", "boundaries": ["Local parser only"], "next_action": "Verify invalid input"}
        self.run_number = 0

    def event(self, **changes):
        value = {"id": "e01", "project_id": PROJECT, "stage": "implementation", "kind": "tool_result",
                 "source": "reports/parser-check.txt", "observed_at": "2026-09-23T09:00:00+08:00",
                 "scope": "local unit tests only", "excerpt": "All selected parser tests passed.", "outcome": "success"}
        value.update(changes)
        return value

    def result(self, keep=0.5, detail=0.5, claim=None):
        answers = {} if claim else {"keep_record": {"type": "noul", "noul": keep}, "keep_detail": {"type": "noul", "noul": detail}}
        if claim:
            answers["claim_support"] = {"type": "choice", "choice": claim, "confidence": 0.95,
                                        "probabilities": {key: 0.96 if key == claim else 0.02 for key in ("supported", "contradicted", "insufficient")}}
        return {"answers": answers, "model": p.MODEL, "usage": {"input_tokens": 100, "output_tokens": 3}}

    def record(self, **changes):
        event = self.event(**changes)
        p.record_event(self.store, event)
        return event

    def review(self, mode="live", **kwargs):
        self.run_number += 1
        return p.review_events(self.store, kwargs.pop("context", self.context), self.root / ("output-" + str(self.run_number)), mode=mode, **kwargs)

    def test_offline_retains_and_never_calls_model(self):
        event = self.record()
        with patch.object(p, "ask") as ask:
            report = self.review("offline")
        ask.assert_not_called()
        self.assertTrue(report["model_review_incomplete"])
        item = report["decisions"][0]
        self.assertEqual((item["decision"], item["decision_source"], item["excerpt"]), ("retain", "offline", event["excerpt"]))
        self.assertIn("verification", report["stage_gaps"])
        self.assertFalse(report["source_files_inspected"])

    def test_low_scores_omit_only_derived_view_and_send_actual_excerpt(self):
        event = self.record()
        path = self.store / "events" / "e01.json"
        before = path.read_bytes()
        with patch.object(p, "ask", return_value=self.result(0.1, 0.0)) as ask:
            report = self.review()
        state, questions = ask.call_args.args
        self.assertEqual(state["event"]["excerpt"], event["excerpt"])
        self.assertEqual(state["context"], self.context)
        self.assertIn("state.event.excerpt", questions["keep_detail"]["instructions"])
        self.assertEqual(path.read_bytes(), before)
        item = report["decisions"][0]
        self.assertEqual(item["decision"], "archive")
        self.assertIsNone(item["excerpt"])
        self.assertEqual(len(report["omissions"]), 1)
        recovery = self.root / "output-1" / item["original_event_ref"]
        self.assertEqual(recovery.resolve(), path.resolve())

    def test_protected_records_skip_model_and_retain_originals(self):
        for number, kind in enumerate(sorted(p.PROTECTED_KINDS)):
            self.record(id=f"e{number}", kind=kind)
        self.record(id="failure", outcome="failure")
        before = {path.name: path.read_bytes() for path in (self.store / "events").glob("*.json")}
        with patch.object(p, "ask") as ask, patch.object(p, "request_digest") as digest:
            report = self.review()
        ask.assert_not_called()
        digest.assert_not_called()
        self.assertTrue(all(item["decision"] == "retain" and item["reason"] == "protected_record"
                            and item["decision_source"] == "rule" and item["request_sha256"] is None
                            and item["answers"] is None and item["usage"] == {} for item in report["decisions"]))
        self.assertEqual(report["review_counts"]["rule"], len(p.PROTECTED_KINDS) + 1)
        self.assertEqual(report["selection"]["model_review_count"], 0)
        self.assertFalse(report["model_review_incomplete"])
        self.assertFalse((self.store / "cache").exists())
        self.assertEqual(before, {path.name: path.read_bytes() for path in (self.store / "events").glob("*.json")})

    def test_unknown_outcome_is_retained_without_model_review(self):
        self.record(outcome="unknown")
        with patch.object(p, "ask") as ask:
            item = self.review()["decisions"][0]
        ask.assert_not_called()
        self.assertEqual((item["decision"], item["reason"]), ("retain", "unknown_outcome"))
        self.assertEqual(item["decision_source"], "rule")

    def test_offline_fixed_retention_is_complete_without_model(self):
        self.record(kind="user_constraint")
        self.record(id="failure", outcome="failure")
        self.record(id="unknown", outcome="unknown")
        with patch.object(p, "ask") as ask:
            report = self.review("offline")
        ask.assert_not_called()
        self.assertFalse(report["model_review_incomplete"])
        self.assertEqual(report["review_counts"], {"rule": 3, "live": 0, "cache": 0, "offline": 0, "error": 0})

    def test_uncertain_or_conflicting_scores_are_retained(self):
        self.record()
        for keep, detail in ((0.1, 0.9), (0.5, 0), (0.10001, 0.1), (0.9, 0.5)):
            with self.subTest(keep=keep, detail=detail):
                context = {**self.context, "next_action": f"Case {keep} and {detail}"}
                with patch.object(p, "ask", return_value=self.result(keep, detail)):
                    self.assertEqual(self.review(context=context)["decisions"][0]["decision"], "retain")

    def test_truncation_preserves_head_tail_and_source(self):
        text = "BEGIN" + "m" * 1800 + "END"
        self.record(excerpt=text)
        with patch.object(p, "ask", return_value=self.result(0.9, 0.1)):
            report = self.review()
        item = report["decisions"][0]
        self.assertEqual(item["decision"], "truncate")
        self.assertTrue(item["excerpt"].startswith(text[:400]))
        self.assertTrue(item["excerpt"].endswith(text[-400:]))
        self.assertIn("omitted", item["excerpt"])
        self.assertEqual(json.loads((self.store / "events" / "e01.json").read_text())["excerpt"], text)

    def test_claim_advice_never_upgrades_evidence_or_removes_excerpt(self):
        self.record(kind="claim", claim="Production deployment is accepted.")
        with patch.object(p, "ask", return_value=self.result(0, 0, "supported")) as ask:
            item = self.review()["decisions"][0]
        self.assertEqual(item["decision"], "retain")
        self.assertEqual(item["claim_review"]["choice"], "supported")
        self.assertTrue(item["evidence_status_change"].startswith("none"))
        self.assertEqual(set(ask.call_args.args[1]), {"claim_support"})
        self.assertEqual(ask.call_args.args[1]["claim_support"]["instructions"]["targetText"], "Production deployment is accepted.")

    def test_protected_claims_still_review_only_support(self):
        for number, changes in enumerate(({"kind": "user_correction"}, {"outcome": "failure"}, {"outcome": "unknown"})):
            self.record(id=f"e{number}", claim="Production deployment is accepted.", **changes)
        with patch.object(p, "ask", return_value=self.result(claim="contradicted")) as ask:
            report = self.review()
        self.assertEqual(ask.call_count, 3)
        self.assertTrue(all(set(call.args[1]) == {"claim_support"} for call in ask.call_args_list))
        self.assertTrue(all(item["decision"] == "retain" and item["claim_review"]["choice"] == "contradicted"
                            for item in report["decisions"]))
        self.assertEqual(report["selection"]["model_review_count"], 3)

    def test_offline_claim_needs_review_even_with_fixed_retention(self):
        self.record(kind="user_correction", claim="Production deployment is accepted.")
        with patch.object(p, "ask") as ask:
            report = self.review("offline")
        ask.assert_not_called()
        self.assertTrue(report["model_review_incomplete"])
        self.assertEqual(report["review_counts"]["offline"], 1)
        self.assertEqual(report["decisions"][0]["decision"], "retain")

    def test_claim_support_cache_reuses_exact_single_question(self):
        self.record(claim="Production deployment is accepted.")
        with patch.object(p, "ask", return_value=self.result(claim="insufficient")) as ask:
            first = self.review()
            second = self.review()
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(second["review_counts"]["cache"], 1)
        self.assertEqual(first["decisions"][0]["request_sha256"], second["decisions"][0]["request_sha256"])
        self.assertEqual(second["decisions"][0]["claim_review"]["choice"], "insufficient")

    def test_cache_reuses_exact_request_and_context_change_invalidates(self):
        self.record()
        with patch.object(p, "ask", return_value=self.result(0, 0)) as ask:
            first = self.review()
            second = self.review()
            third = self.review(context={**self.context, "next_action": "Revisit the source result"})
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(second["decisions"][0]["decision_source"], "cache")
        self.assertEqual(first["decisions"][0]["request_sha256"], second["decisions"][0]["request_sha256"])
        self.assertNotEqual(first["decisions"][0]["request_sha256"], third["decisions"][0]["request_sha256"])

    def test_offline_ignores_even_valid_low_score_cache(self):
        self.record()
        with patch.object(p, "ask", return_value=self.result(0, 0)) as ask:
            self.review()
            report = self.review("offline")
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(report["decisions"][0]["decision"], "retain")

    def test_corrupt_cache_fails_closed_without_retry(self):
        self.record()
        with patch.object(p, "ask", return_value=self.result(0, 0)):
            self.review()
        cache = next((self.store / "cache").glob("*.json"))
        value = json.loads(cache.read_text())
        value["result"]["answers"]["keep_record"]["noul"] = True
        cache.write_text(json.dumps(value), encoding="utf-8")
        with patch.object(p, "ask") as ask:
            report = self.review()
        ask.assert_not_called()
        self.assertTrue(report["model_review_incomplete"])
        self.assertEqual(report["decisions"][0]["decision"], "retain")
        self.assertEqual(report["decisions"][0]["decision_source"], "error")

    def test_wrong_cached_model_cannot_be_used(self):
        self.record()
        with patch.object(p, "ask", return_value=self.result(0, 0)):
            self.review()
        cache = next((self.store / "cache").glob("*.json"))
        value = json.loads(cache.read_text())
        value["result"]["model"] = "different-model"
        cache.write_text(json.dumps(value), encoding="utf-8")
        with patch.object(p, "ask") as ask:
            item = self.review()["decisions"][0]
        ask.assert_not_called()
        self.assertEqual((item["decision"], item["decision_source"]), ("retain", "error"))

    def test_cached_error_envelope_or_missing_usage_cannot_archive(self):
        self.record()
        with patch.object(p, "ask", return_value=self.result(0, 0)):
            self.review()
        cache = next((self.store / "cache").glob("*.json"))
        original = cache.read_text(encoding="utf-8")
        for change in ("error", "errors", "status", "missing_usage", "invalid_usage"):
            with self.subTest(change=change):
                value = json.loads(original)
                if change in {"error", "errors"}:
                    value["result"][change] = "provider-error-body-not-to-display"
                elif change == "status":
                    value["result"]["status"] = "error"
                elif change == "missing_usage":
                    del value["result"]["usage"]
                else:
                    value["result"]["usage"]["input_tokens"] = True
                cache.write_text(json.dumps(value), encoding="utf-8")
                with patch.object(p, "ask") as ask:
                    report = self.review()
                ask.assert_not_called()
                self.assertTrue(report["model_review_incomplete"])
                item = report["decisions"][0]
                self.assertEqual((item["decision"], item["decision_source"]), ("retain", "error"))
                self.assertNotIn("provider-error-body-not-to-display", json.dumps(report))

    def test_failed_model_retains_and_does_not_leak_or_retry(self):
        self.record()
        with patch.object(p, "ask", side_effect=RuntimeError("provider-body-private-value")) as ask:
            report = self.review()
        self.assertEqual(ask.call_count, 1)
        self.assertTrue(report["model_review_incomplete"])
        self.assertNotIn("provider-body-private-value", json.dumps(report))
        self.assertEqual(report["decisions"][0]["decision"], "retain")

    def test_idempotent_record_and_changed_content_rejected(self):
        event = self.record()
        target = self.store / "events" / "e01.json"
        before = target.read_bytes()
        self.assertEqual(p.record_event(self.store, event), "unchanged")
        with self.assertRaises(p.ProcessError):
            p.record_event(self.store, {**event, "excerpt": "Changed result"})
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.store / ".record.lock").exists())

    def test_case_colliding_id_rejected(self):
        self.record(id="Event")
        with self.assertRaises(p.ProcessError):
            self.record(id="event")

    def test_invalid_ids_and_parent_traversal_rejected(self):
        for bad_id in ("../escape", "a/b", "a\\b", ".", "..", "CON", "name:stream", "e01.json", ""):
            with self.subTest(id=bad_id), self.assertRaises(p.ProcessError):
                self.record(id=bad_id)
        with self.assertRaises(p.ProcessError):
            p.record_event(self.root / "outside" / ".." / "store", self.event())
        self.assertFalse(self.store.exists())

    def test_missing_unknown_empty_fields_and_naive_time_rejected(self):
        cases = [self.event(extra="not-allowed"), self.event(excerpt=" "), self.event(observed_at="2026-09-23T09:00:00"), self.event(project_id="not-a-uuid"), self.event(kind="claim")]
        for key in p.EVENT_FIELDS:
            event = self.event()
            del event[key]
            cases.append(event)
        for event in cases:
            with self.subTest(keys=list(event)), self.assertRaises(p.ProcessError):
                p.record_event(self.store, event)
        self.assertFalse(self.store.exists())

    def test_project_identity_guard_applies_to_record_and_review(self):
        self.record()
        with self.assertRaises(p.ProcessError):
            self.record(id="other", project_id=OTHER_PROJECT)
        with self.assertRaises(p.ProcessError):
            self.review("offline", context={**self.context, "project_id": OTHER_PROJECT})
        self.assertFalse((self.store / "events" / "other.json").exists())

    def test_credentials_rejected_before_storage_or_model(self):
        for excerpt in ("api_key=not-public", "Authorization: Bearer not-public", '{"api_key": "not-public"}', '{"Authorization": "Bearer not-public"}', "-----BEGIN PRIVATE KEY-----", "https://user:password@example.invalid", "ghp_" + "a" * 24):
            with self.subTest(excerpt=excerpt), self.assertRaises(p.ProcessError):
                self.record(excerpt=excerpt)
        self.assertFalse(self.store.exists())
        self.record(excerpt="api_key=[REDACTED]")
        with patch.object(p, "ask") as ask, self.assertRaises(p.ProcessError):
            self.review(context={**self.context, "goal": "password=never-transmit"})
        ask.assert_not_called()

    def test_configured_key_is_rejected_even_without_credential_label(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "unlabelled-configured-value"}), self.assertRaises(p.ProcessError):
            self.record(excerpt="Debug value: unlabelled-configured-value")
        self.assertFalse(self.store.exists())

    def test_sensitive_tampered_event_rejected_before_model(self):
        self.record()
        path = self.store / "events" / "e01.json"
        path.write_text(json.dumps(self.event(excerpt="access_token=private")), encoding="utf-8")
        with patch.object(p, "ask") as ask, self.assertRaises(p.ProcessError):
            self.review()
        ask.assert_not_called()

    def test_live_budget_rejects_before_calls_and_explicit_selection_works(self):
        for number in range(13):
            self.record(id=f"e{number:02d}")
        with patch.object(p, "ask") as ask, self.assertRaises(p.ProcessError):
            self.review()
        ask.assert_not_called()
        with patch.object(p, "ask", return_value=self.result()) as ask:
            report = self.review(event_ids=["e00", "e12"])
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(report["selection"]["selected_count"], 2)
        self.assertEqual(len(report["selection"]["unselected_ids"]), 11)

    def test_live_budget_ignores_rule_only_records(self):
        for number in range(15):
            self.record(id=f"protected{number:02d}", kind="decision")
        for number in range(p.MAX_LIVE_EVENTS):
            self.record(id=f"review{number:02d}")
        with patch.object(p, "ask", return_value=self.result()) as ask:
            report = self.review()
        self.assertEqual(ask.call_count, p.MAX_LIVE_EVENTS)
        self.assertEqual(report["selection"]["selected_count"], 15 + p.MAX_LIVE_EVENTS)
        self.assertEqual(report["selection"]["model_review_count"], p.MAX_LIVE_EVENTS)
        self.assertEqual(report["review_counts"]["rule"], 15)

    def test_protected_claims_count_toward_model_review_budget(self):
        for number in range(p.MAX_LIVE_EVENTS + 1):
            self.record(id=f"claim{number:02d}", kind="decision", claim="Production deployment is accepted.")
        with patch.object(p, "ask") as ask, self.assertRaises(p.ProcessError):
            self.review()
        ask.assert_not_called()
        self.assertFalse((self.root / "output-1").exists())

    def test_existing_output_is_not_overwritten_or_sent(self):
        self.record()
        out = self.root / "existing"
        out.mkdir()
        (out / "keep").write_text("original")
        with patch.object(p, "ask") as ask, self.assertRaises(p.ProcessError):
            p.review_events(self.store, self.context, out, "live")
        ask.assert_not_called()
        self.assertEqual((out / "keep").read_text(), "original")

    def test_output_cannot_pollute_immutable_event_store(self):
        self.record()
        for out in (self.store, self.root, self.store / "events" / "output", self.store / "cache" / "output"):
            with self.subTest(out=out), self.assertRaises(p.ProcessError):
                p.review_events(self.store, self.context, out)

    def test_cross_volume_recovery_failure_is_checked_before_network_or_output(self):
        self.record()
        out = self.root / "cross-volume-output"
        with patch.object(p.os.path, "relpath", side_effect=ValueError("different mounts")), patch.object(p, "ask") as ask:
            with self.assertRaisesRegex(p.ProcessError, "share a volume"):
                p.review_events(self.store, self.context, out, "live")
        ask.assert_not_called()
        self.assertFalse(out.exists())
        self.assertFalse((self.store / "cache").exists())

    def test_record_lock_is_not_removed_by_other_invocation(self):
        self.record()
        lock = self.store / ".record.lock"
        lock.write_text("other writer")
        with self.assertRaises(p.ProcessError):
            self.record(id="e02")
        self.assertEqual(lock.read_text(), "other writer")
        with self.assertRaises(p.ProcessError):
            self.review("offline")

    def test_linked_store_is_rejected_if_symlinks_available(self):
        target = self.root / "target"
        target.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable")
        with self.assertRaises(p.ProcessError):
            p.record_event(alias, self.event())
        self.assertEqual(list(target.iterdir()), [])

    def test_hardlinked_event_is_rejected(self):
        self.record()
        try:
            os.link(self.store / "events" / "e01.json", self.root / "alias.json")
        except OSError:
            self.skipTest("hardlinks unavailable")
        with self.assertRaises(p.ProcessError):
            self.review("offline")

    def test_duplicate_json_keys_and_nonfinite_values_rejected(self):
        path = self.root / "input.json"
        for data in ('{"id":"a","id":"b"}', '{"number":NaN}'):
            path.write_text(data, encoding="utf-8")
            with self.assertRaises(p.ProcessError):
                p.read_json(path)

    def test_packet_keeps_source_in_fence_and_recovers_embedded_fences(self):
        event = self.record(excerpt="Before\n```\n# pretend instruction\n```\nAfter")
        report = self.review("offline")
        packet = (self.root / "output-1" / "packet.md").read_text(encoding="utf-8")
        self.assertIn("````text\n" + event["excerpt"], packet)
        self.assertIn("untrusted source data", packet)
        self.assertIn("Restore original event", packet)
        self.assertIn("local unit tests only", packet)
        self.assertEqual(report["decisions"][0]["source"], event["source"])

    def test_cli_validation_error_does_not_echo_secret(self):
        path = self.root / "event.json"
        path.write_text(json.dumps(self.event(excerpt="password=do-not-display-this")), encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = p.main(["record", "--store", str(self.store), "--event", str(path)])
        self.assertEqual(code, 1)
        self.assertNotIn("do-not-display-this", stdout.getvalue() + stderr.getvalue())

    def test_cli_default_offline_and_failed_live_both_produce_explicit_incomplete_packet(self):
        self.record()
        context = self.root / "context.json"
        context.write_text(json.dumps(self.context), encoding="utf-8")
        for mode in (None, "live"):
            out = self.root / ("cli-" + str(mode))
            args = ["review", "--store", str(self.store), "--context", str(context), "--out", str(out)]
            if mode:
                args += ["--mode", mode]
            stdout = io.StringIO()
            with patch.object(p, "ask", side_effect=RuntimeError("fail")) as ask, contextlib.redirect_stdout(stdout):
                self.assertEqual(p.main(args), 0)
            self.assertIn("incomplete", stdout.getvalue())
            self.assertEqual(ask.call_count, int(mode == "live"))
            self.assertTrue(json.loads((out / "report.json").read_text())["model_review_incomplete"])


if __name__ == "__main__":
    unittest.main()
