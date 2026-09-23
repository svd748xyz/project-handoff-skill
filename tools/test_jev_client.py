"""Offline contract and transport tests; no real TypeSafe requests are made."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "skills" / "project-handoff" / "scripts" / "jev_client.py"
SPEC = importlib.util.spec_from_file_location("handoff_jev_client_under_test", CLIENT_PATH)
assert SPEC and SPEC.loader
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)

FAKE_KEY = "test-only-credential-never-a-real-key-0123456789"
QUESTIONS = {
    "keep": {
        "type": "noul",
        "instructions": "Does `event.text` need to stay verbatim?",
        "criteria": {"true": "Exact text is needed", "false": "Exact text is unnecessary"},
    },
    "support": {
        "type": "choice",
        "instructions": "How does `event.evidence` relate to `event.claim`?",
        "criteria": {
            "supports": "The source supports the claim",
            "contradicts": "The source contradicts the claim",
            "insufficient": "The source cannot determine the claim",
        },
    },
}


def valid_result():
    return {
        "model": "jev-1.13.0",
        "answers": {
            "keep": {"type": "noul", "noul": 0.95},
            "support": {
                "type": "choice", "choice": "supports", "confidence": 0.88,
                "probabilities": {"supports": 0.9, "contradicts": 0.04, "insufficient": 0.06},
            },
        },
        "usage": {"input_tokens": 312, "output_tokens": 46},
    }


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class FakeResponse:
    def __init__(self, body=None, status=200):
        self.status = status
        self.data = io.BytesIO(body if body is not None else encoded(valid_result()))
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        self.read_sizes.append(size)
        return self.data.read(size)


class ResultContractTests(unittest.TestCase):
    def test_valid_noul_and_choice_response(self):
        result = client.validate_result(valid_result(), QUESTIONS)
        self.assertEqual(result, valid_result())
        self.assertNotIn("confidence", result["answers"]["keep"])

    def test_missing_extra_and_replaced_question_ids(self):
        for mutate in (
            lambda answers: answers.pop("keep"),
            lambda answers: answers.update(extra={"type": "noul", "noul": 1}),
            lambda answers: answers.update(renamed=answers.pop("keep")),
        ):
            with self.subTest(mutation=mutate):
                result = valid_result()
                mutate(result["answers"])
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_answer_types_must_match_requested_types(self):
        for key, value in (("keep", {"type": "score", "noul": 0.95}),
                           ("support", {"type": "noul", "noul": 0.9}),
                           ("keep", None), ("support", [])):
            with self.subTest(key=key, value=value):
                result = valid_result()
                result["answers"][key] = value
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_invalid_noul_values_are_rejected(self):
        for value in (True, False, "0.95", None, float("nan"), float("inf"), -0.01, 1.01, 10 ** 1000):
            with self.subTest(value=value):
                result = valid_result()
                result["answers"]["keep"]["noul"] = value
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_noul_boundary_values_are_valid(self):
        for value in (0, 1, 0.0, 1.0):
            with self.subTest(value=value):
                result = valid_result()
                result["answers"]["keep"]["noul"] = value
                self.assertEqual(client.validate_result(result, QUESTIONS)["answers"]["keep"]["noul"], value)

    def test_invalid_confidence_values_are_rejected(self):
        for value in (True, "0.8", None, float("nan"), float("inf"), -0.1, 1.1, 10 ** 1000):
            with self.subTest(value=value):
                result = valid_result()
                result["answers"]["support"]["confidence"] = value
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_unknown_or_non_string_choice_is_rejected(self):
        for value in ("unknown", None, True, [], {}):
            with self.subTest(value=value):
                result = valid_result()
                result["answers"]["support"]["choice"] = value
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_distribution_requires_all_and_only_known_options(self):
        for probabilities in (
            {"supports": 1.0},
            {"supports": 0.9, "contradicts": 0.04, "insufficient": 0.05, "other": 0.01},
            [0.9, 0.04, 0.06], None,
        ):
            with self.subTest(probabilities=probabilities):
                result = valid_result()
                result["answers"]["support"]["probabilities"] = probabilities
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_invalid_distribution_values_are_rejected(self):
        for value in (True, "0.9", None, float("nan"), float("inf"), -0.1, 1.1, 10 ** 1000):
            with self.subTest(value=value):
                result = valid_result()
                result["answers"]["support"]["probabilities"]["supports"] = value
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_distribution_sum_must_be_one(self):
        result = valid_result()
        result["answers"]["support"]["probabilities"]["supports"] = 0.5
        with self.assertRaises(client.JevError):
            client.validate_result(result, QUESTIONS)

    def test_choice_must_match_a_highest_probability_option(self):
        result = valid_result()
        result["answers"]["support"]["choice"] = "contradicts"
        with self.assertRaises(client.JevError):
            client.validate_result(result, QUESTIONS)

    def test_tied_highest_probability_is_accepted(self):
        result = valid_result()
        result["answers"]["support"]["probabilities"] = {
            "supports": 0.5, "contradicts": 0.5, "insufficient": 0.0,
        }
        self.assertEqual(client.validate_result(result, QUESTIONS)["answers"]["support"]["choice"], "supports")

    def test_error_envelope_cannot_hide_behind_valid_answers(self):
        for field, value in (("error", {"message": "secret"}), ("errors", []),
                             ("status", "failed"), ("status", "error")):
            with self.subTest(field=field, value=value):
                result = valid_result()
                result[field] = value
                with self.assertRaises(client.JevError) as error:
                    client.validate_result(result, QUESTIONS)
                self.assertNotIn("secret", str(error.exception))

    def test_missing_model_alias_and_version_drift_are_rejected(self):
        for model in (None, "jev-latest", "jev-preview", "jev-1.14.0", "jev-1.13"):
            with self.subTest(model=model):
                result = valid_result()
                result["model"] = model
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_usage_must_contain_nonnegative_integer_counts(self):
        for field in ("input_tokens", "output_tokens"):
            for value in (None, True, -1, 1.5, "312", float("nan")):
                with self.subTest(field=field, value=value):
                    result = valid_result()
                    result["usage"][field] = value
                    with self.assertRaises(client.JevError):
                        client.validate_result(result, QUESTIONS)
        for usage in (None, [], {}, {"input_tokens": 3}):
            with self.subTest(usage=usage):
                result = valid_result()
                result["usage"] = usage
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)

    def test_non_object_envelopes_are_rejected(self):
        for result in (None, [], "ok", 1, True):
            with self.subTest(result=result):
                with self.assertRaises(client.JevError):
                    client.validate_result(result, QUESTIONS)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"TYPESAFE_API_KEY": FAKE_KEY})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.opener = Mock()
        self.builder = patch.object(client.urllib.request, "build_opener", return_value=self.opener)
        self.build = self.builder.start()
        self.addCleanup(self.builder.stop)
        self.response = FakeResponse()
        self.opener.open.return_value = self.response

    def ask(self, state=None, **kwargs):
        return client.ask(state if state is not None else {"event": "A bounded observation"}, QUESTIONS, **kwargs)

    def assert_not_sent(self):
        self.build.assert_not_called()
        self.opener.open.assert_not_called()

    def test_only_official_endpoint_post_and_authorization_header(self):
        self.assertEqual(self.ask(), valid_result())
        self.opener.open.assert_called_once()
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + FAKE_KEY)
        self.assertNotIn(FAKE_KEY.encode(), request.data)
        self.assertEqual(json.loads(request.data)["model"], "jev-1.13.0")
        self.assertEqual(self.opener.open.call_args.kwargs, {"timeout": 20.0})
        self.assertEqual(self.response.read_sizes, [client.MAX_RESPONSE_BYTES + 1])

    def test_timeout_has_one_attempt_and_safe_error(self):
        self.opener.open.side_effect = TimeoutError("upstream detail " + FAKE_KEY)
        with self.assertRaises(client.JevError) as error:
            self.ask()
        self.opener.open.assert_called_once()
        self.assertNotIn(FAKE_KEY, str(error.exception))
        self.assertIn("not retried", str(error.exception))

    def test_http_errors_have_one_attempt_without_provider_body(self):
        for status in (401, 422, 429, 529):
            with self.subTest(status=status):
                self.opener.open.reset_mock()
                body = io.BytesIO(FAKE_KEY.encode())
                upstream_error = urllib.error.HTTPError(
                    client.ENDPOINT, status, "private " + FAKE_KEY, {}, body)
                self.addCleanup(upstream_error.close)
                self.opener.open.side_effect = upstream_error
                with self.assertRaises(client.JevError) as error:
                    self.ask()
                self.opener.open.assert_called_once()
                self.assertIn(str(status), str(error.exception))
                self.assertNotIn(FAKE_KEY, str(error.exception))
                self.assertTrue(body.closed, "HTTPError body must close to avoid leaking resource warnings")

    def test_redirect_handler_refuses_followup_and_credential_forwarding(self):
        redirected_requests = []
        redirect_body = io.BytesIO(b"redirect body")
        self.addCleanup(redirect_body.close)

        def simulated_open(request, **kwargs):
            handler = self.build.call_args.args[0]
            self.assertIsInstance(handler, client._NoRedirect)
            redirected = handler.redirect_request(request, redirect_body, 302, "Found", {}, "https://other.invalid/collect")
            redirected_requests.append(redirected)
            return self.response

        self.opener.open.side_effect = simulated_open
        with self.assertRaisesRegex(client.JevError, "redirect refused"):
            self.ask()
        self.opener.open.assert_called_once()
        self.assertEqual(redirected_requests, [])
        self.assertTrue(redirect_body.closed, "Rejected redirect response must be closed")

    def test_exact_24000_byte_request_allowed_and_next_byte_refused(self):
        empty_size = len(client._json({"model": client.MODEL, "state": {"payload": ""}, "questions": QUESTIONS}))
        padding = "x" * (24_000 - empty_size)
        self.ask({"payload": padding})
        self.assertEqual(len(self.opener.open.call_args.args[0].data), 24_000)
        self.build.reset_mock()
        self.opener.open.reset_mock()
        with self.assertRaisesRegex(client.JevError, "24000-byte"):
            self.ask({"payload": padding + "x"})
        self.assert_not_sent()

    def test_budget_counts_utf8_bytes_for_chinese_text(self):
        with self.assertRaisesRegex(client.JevError, "24000-byte"):
            self.ask({"payload": "中" * 8_000})
        self.assert_not_sent()

    def test_configured_secret_in_state_or_question_is_not_sent(self):
        for location in ("state", "question"):
            with self.subTest(location=location):
                questions = copy.deepcopy(QUESTIONS)
                state = {"event": "safe"}
                if location == "state":
                    state["debug"] = "Bearer " + FAKE_KEY
                else:
                    questions["keep"]["instructions"] += " " + FAKE_KEY
                with self.assertRaises(client.JevError) as error:
                    client.ask(state, questions)
                self.assertNotIn(FAKE_KEY, str(error.exception))
                self.assert_not_sent()

    def test_missing_key_refuses_network(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "   "}):
            with self.assertRaises(client.JevError):
                self.ask()
        self.assert_not_sent()

    def test_invalid_state_and_nonfinite_input_refuse_network(self):
        for state in ("", [], {}, 1, True, {"measurement": float("nan")}, {"bad": object()}):
            with self.subTest(state=type(state).__name__):
                with self.assertRaises(client.JevError):
                    client.ask(state, QUESTIONS)
                self.assert_not_sent()

    def test_invalid_timeout_refuses_network(self):
        for timeout in (True, 0, -1, 31, float("nan"), float("inf"), "20"):
            with self.subTest(timeout=timeout):
                with self.assertRaises(client.JevError):
                    self.ask(timeout=timeout)
                self.assert_not_sent()

    def test_oversized_response_is_rejected_with_bounded_read(self):
        self.response = FakeResponse(b"x" * (client.MAX_RESPONSE_BYTES + 100))
        self.opener.open.return_value = self.response
        with self.assertRaisesRegex(client.JevError, "response exceeds"):
            self.ask()
        self.assertEqual(self.response.read_sizes, [client.MAX_RESPONSE_BYTES + 1])

    def test_duplicate_json_key_rejected_at_top_and_nested_levels(self):
        normal = encoded(valid_result())
        for raw in (
            b'{"model":"jev-1.13.0","model":"jev-1.14.0"}',
            normal.replace(b'"noul": 0.95', b'"noul": 0.95,"noul": 0.01'),
        ):
            with self.subTest(raw_length=len(raw)):
                self.opener.open.return_value = FakeResponse(raw)
                with self.assertRaisesRegex(client.JevError, "Duplicate JSON"):
                    self.ask()

    def test_nan_provider_json_is_rejected(self):
        self.opener.open.return_value = FakeResponse(encoded(valid_result()).replace(b'"noul": 0.95', b'"noul": NaN'))
        with self.assertRaises(client.JevError):
            self.ask()

    def test_invalid_utf8_and_non_json_are_safe_failures(self):
        for raw in (b"\xff\xfe", b"<html>" + FAKE_KEY.encode(), b"null", b"[]"):
            with self.subTest(raw_length=len(raw)):
                self.opener.open.return_value = FakeResponse(raw)
                with self.assertRaises(client.JevError) as error:
                    self.ask()
                self.assertNotIn(FAKE_KEY, str(error.exception))

    def test_non_200_response_rejected_even_with_valid_body(self):
        self.opener.open.return_value = FakeResponse(status=202)
        with self.assertRaises(client.JevError):
            self.ask()

    def test_invalid_questions_never_reach_network(self):
        invalid = [None, {}, {"bad id": QUESTIONS["keep"]},
                   {"q": {"type": "score", "instructions": "Rate"}},
                   {"q": {"type": "noul", "instructions": ""}},
                   {"q": {"type": "choice", "instructions": "Choose", "criteria": {"one": None}}},
                   {"q": {"type": "noul", "instructions": "Judge", "criteria": {"yes": "yes"}}},
                   {str(i): QUESTIONS["keep"] for i in range(9)}]
        for questions in invalid:
            with self.subTest(questions_type=type(questions).__name__):
                with self.assertRaises(client.JevError):
                    client.ask({"event": "safe"}, questions)
                self.assert_not_sent()


class DigestTests(unittest.TestCase):
    def test_digest_is_stable_for_key_order_and_changes_with_evidence(self):
        a = client.request_digest({"event": "a", "goal": "resume"}, QUESTIONS)
        b = client.request_digest({"goal": "resume", "event": "a"}, QUESTIONS)
        self.assertEqual(a, b)
        self.assertNotEqual(a, client.request_digest({"event": "b", "goal": "resume"}, QUESTIONS))

    def test_digest_changes_with_model_and_prompt_version(self):
        original = client.request_digest({"event": "a"}, QUESTIONS)
        with patch.object(client, "MODEL", "jev-1.14.0"):
            self.assertNotEqual(original, client.request_digest({"event": "a"}, QUESTIONS))
        with patch.object(client, "PROMPT_VERSION", "different-rubric"):
            self.assertNotEqual(original, client.request_digest({"event": "a"}, QUESTIONS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
