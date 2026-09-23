"""Small, bounded TypeSafe transport. No credential files, retries, or redirects."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
PROMPT_VERSION = "handoff-process-2.0.0"
MAX_REQUEST_BYTES = 24_000
MAX_RESPONSE_BYTES = 64_000


class JevError(ValueError):
    """Contains only a safe diagnostic, never the provider body or request data."""


def _json(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise JevError("Input is not finite UTF-8 JSON") from None


def request_digest(state: object, questions: dict) -> str:
    return hashlib.sha256(_json({"endpoint": ENDPOINT, "model": MODEL,
                                "prompt_version": PROMPT_VERSION,
                                "state": state, "questions": questions})).hexdigest()


def _probability(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise JevError("Invalid probability type")
    if not 0 <= value <= 1 or not math.isfinite(value):
        raise JevError("Probability outside finite [0,1]")
    return float(value)


def validate_questions(questions: object) -> dict:
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 8:
        raise JevError("Expected 1 to 8 named questions")
    for key, question in questions.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", key):
            raise JevError("Invalid question ID")
        if not isinstance(question, dict) or question.get("type") not in {"noul", "choice"}:
            raise JevError("Unsupported question type")
        if not isinstance(question.get("instructions"), (str, list, dict)) or not question["instructions"]:
            raise JevError("Question instructions are required")
        criteria = question.get("criteria", {})
        if not isinstance(criteria, dict):
            raise JevError("Question criteria must be a map")
        if question["type"] == "choice" and (not 2 <= len(criteria) <= 255 or
                                               not all(isinstance(k, str) and k for k in criteria)):
            raise JevError("Choice criteria must define 2 to 255 named options")
        if question["type"] == "noul" and not set(criteria) <= {"true", "false"}:
            raise JevError("Noul criteria may only define true and false")
    return questions


def validate_answers(answers: object, questions: dict) -> dict:
    validate_questions(questions)
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise JevError("Response question IDs do not match")
    clean = {}
    for key, question in questions.items():
        answer = answers[key]
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise JevError("Response answer type does not match")
        if question["type"] == "noul":
            clean[key] = {"type": "noul", "noul": _probability(answer.get("noul"))}
            continue
        choice, probabilities = answer.get("choice"), answer.get("probabilities")
        if not isinstance(choice, str) or choice not in question["criteria"]:
            raise JevError("Response contains an unknown choice")
        if not isinstance(probabilities, dict) or set(probabilities) != set(question["criteria"]):
            raise JevError("Response distribution options do not match")
        probabilities = {k: _probability(v) for k, v in probabilities.items()}
        if abs(sum(probabilities.values()) - 1.0) > 0.001:
            raise JevError("Response probabilities do not sum to one")
        if probabilities[choice] + 0.000001 < max(probabilities.values()):
            raise JevError("Response choice is not a highest-probability option")
        clean[key] = {"type": "choice", "choice": choice,
                      "probabilities": probabilities,
                      "confidence": _probability(answer.get("confidence"))}
    return clean


def validate_result(result: object, questions: dict) -> dict:
    if not isinstance(result, dict) or "error" in result or "errors" in result:
        raise JevError("Provider returned an error or malformed envelope")
    if "status" in result and result["status"] not in {"ok", "success"}:
        raise JevError("Provider returned a non-success envelope")
    if result.get("model") != MODEL:
        raise JevError("Provider model does not match the pinned model")
    usage = result.get("usage")
    if not isinstance(usage, dict):
        raise JevError("Provider response lacks usage")
    clean_usage = {}
    for name in ("input_tokens", "output_tokens"):
        value = usage.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise JevError("Provider response has invalid usage")
        clean_usage[name] = value
    return {"model": MODEL, "answers": validate_answers(result.get("answers"), questions),
            "usage": clean_usage}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if fp is not None:
            fp.close()
        raise JevError("Provider redirect refused")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JevError("Duplicate JSON response key")
        result[key] = value
    return result


def ask(state: object, questions: dict, timeout: float = 20.0) -> dict:
    """One authorized request. A failed/uncertain submission is never retried here."""
    validate_questions(questions)
    if not isinstance(state, (str, list, dict)) or not state:
        raise JevError("State is required")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
        raise JevError("Timeout must be within (0,30] seconds")
    data = _json({"model": MODEL, "state": state, "questions": questions})
    if len(data) > MAX_REQUEST_BYTES:
        raise JevError("Request exceeds the 24000-byte local budget; split evidence without losing caveats")
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise JevError("TYPESAFE_API_KEY is unavailable in this process")
    if key.encode("utf-8") in data:
        raise JevError("Configured credential detected in input; request refused")
    request = urllib.request.Request(ENDPOINT, data=data, method="POST",
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json",
                                              "Accept": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            if response.status != 200:
                raise JevError("Provider returned a non-200 status")
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise JevError("Provider response exceeds the local budget")
        result = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
        return validate_result(result, questions)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise JevError(f"Provider HTTP {code}; not retried") from None
    except JevError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError):
        raise JevError("Provider connection, timeout, or response validation failed; not retried") from None
