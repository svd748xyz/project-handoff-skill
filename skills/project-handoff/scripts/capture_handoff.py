#!/usr/bin/env python3
"""Mechanically capture one UTF-8 tool-output file, without reading it with an LLM.

Source is a logical observation label, not a command to execute. The caller's
outcome describes the tool process within scope; success is not business
acceptance. Each event explicitly identifies its slice of the complete source.
The byte-for-byte source and a range manifest remain available for recovery.
This explicit, offline CLI does not intercept tools or inspect session folders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from process_handoff import (
    KINDS, STAGES, ProcessError, _identity, _mkdir, _no_duplicates,
    _reject_constant, _secret_gate, _text, _write_new, canonical, read_json,
    record_event, safe_path, validate_context, validate_event,
)

MAX_CAPTURE_BYTES = 8_000_000
MAX_MANIFEST_BYTES = 8_000_000
MAX_EXCERPT_CHARS = 6000
FORMAT_VERSION = 1


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_label(value: str) -> str:
    _text(value, limit=2000)
    if (Path(value).is_absolute() or PureWindowsPath(value).is_absolute() or PureWindowsPath(value).root
            or PureWindowsPath(value).drive or ".." in value.replace("\\", "/").split("/")):
        raise ProcessError("source must be a logical label without absolute paths or traversal")
    _secret_gate(value)
    return value


def _read_source(path: Path) -> tuple[bytes, str]:
    target = safe_path(path)
    try:
        if not stat.S_ISREG(target.stat().st_mode):
            raise ProcessError("capture input must be a regular file")
        with target.open("rb") as stream:
            data = stream.read(MAX_CAPTURE_BYTES + 1)
        if not data or len(data) > MAX_CAPTURE_BYTES:
            raise ProcessError("capture input is empty or exceeds the byte limit")
        text = data.decode("utf-8")
    except (OSError, UnicodeError):
        raise ProcessError("cannot read capture input as UTF-8") from None
    _secret_gate(text)
    return data, text


def _chunks(text: str):
    """Yield exact, consecutive Unicode code-point ranges and reversible excerpts."""
    start = 0
    while start < len(text):
        end = min(start + MAX_EXCERPT_CHARS, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + MAX_EXCERPT_CHARS // 2, end)
            if newline >= 0:
                end = newline + 1
        fragment = text[start:end]
        encoding = "verbatim"
        excerpt = fragment
        # The existing event schema disallows a whitespace-only excerpt. JSON
        # string encoding preserves every whitespace character without a claim.
        if not fragment.strip():
            encoding = "json-string"
            excerpt = json.dumps(fragment, ensure_ascii=False)
            if len(excerpt) > MAX_EXCERPT_CHARS:
                low, high = 1, len(fragment)
                while low < high:
                    middle = (low + high + 1) // 2
                    if len(json.dumps(fragment[:middle], ensure_ascii=False)) <= MAX_EXCERPT_CHARS:
                        low = middle
                    else:
                        high = middle - 1
                end = start + low
                fragment = text[start:end]
                excerpt = json.dumps(fragment, ensure_ascii=False)
        yield start, end, fragment, excerpt, encoding
        start = end


def _plan(text: str, metadata: dict, capture_id: str, observed_at: str) -> tuple[list[dict], list[dict]]:
    events, ranges = [], []
    chunks = list(_chunks(text))
    for index, (start, end, fragment, excerpt, encoding) in enumerate(chunks):
        event_id = f"cap-{capture_id}-{index:06d}"
        source_ref = (f"captured/{capture_id}/source.txt#chars={start}:{end}; "
                      f"total={len(text)}; part={index + 1}/{len(chunks)}")
        event = validate_event({
            "id": event_id, "project_id": metadata["project_id"], "stage": metadata["stage"],
            "kind": metadata["kind"], "source": source_ref, "observed_at": observed_at,
            "scope": metadata["scope"], "excerpt": excerpt, "outcome": metadata["outcome"],
        })
        ranges.append({
            "start_char": start, "end_char": end, "event_id": event_id,
            "content_sha256": _digest(fragment.encode("utf-8")),
            "excerpt_sha256": _digest(excerpt.encode("utf-8")), "excerpt_encoding": encoding,
            "event_sha256": _digest(canonical(event)),
        })
        events.append(event)
    return events, ranges


def _read_manifest(path: Path) -> dict:
    target = safe_path(path)
    try:
        with target.open("rb") as stream:
            data = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(data) > MAX_MANIFEST_BYTES:
            raise ProcessError("capture manifest exceeds the byte limit")
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates,
                            parse_constant=_reject_constant)
        if not isinstance(result, dict):
            raise ProcessError("capture manifest must be an object")
        return result
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ProcessError("cannot read valid capture manifest") from None


def _check_identity(store: Path, project_id: str) -> None:
    if store.exists():
        if not store.is_dir():
            raise ProcessError("store must be a directory")
        if (store / "project.json").exists():
            _identity(store, project_id)
        elif any(store.iterdir()):
            raise ProcessError("nonempty store has no project identity")


def _check_events(store: Path, events: list[dict]) -> set[str]:
    directory = safe_path(store / "events")
    if directory.exists() and not directory.is_dir():
        raise ProcessError("events path must be a directory")
    existing_names = {path.name.casefold(): path.name for path in directory.iterdir()} if directory.exists() else {}
    verified = set()
    for event in events:
        name = event["id"] + ".json"
        if name.casefold() in existing_names and existing_names[name.casefold()] != name:
            raise ProcessError("event id has a case-insensitive collision")
        path = safe_path(directory / name)
        if path.exists():
            if validate_event(read_json(path)) != event:
                raise ProcessError("capture event differs from immutable saved content")
            verified.add(event["id"])
    return verified


def _publish_capture(directory: Path, manifest: dict, data: bytes) -> None:
    """Publish complete source + manifest together; never replace an old capture."""
    parent = _mkdir(directory.parent)
    staging = _mkdir(parent / (".pending-" + uuid.uuid4().hex), exclusive=True)
    try:
        _write_new(staging / "manifest.json", canonical(manifest) + b"\n")
        _write_new(staging / "source.txt", data)
        safe_path(directory)
        if directory.exists():
            raise ProcessError("capture directory appeared during publication; retry to verify it")
        # A completed capture directory is nonempty; rename cannot replace it on
        # Windows or POSIX. The store capture lock serializes cooperating writers.
        os.rename(staging, directory)
    except OSError:
        raise ProcessError("capture publication failed; retry after checking the store") from None
    finally:
        # Only clean files created in this invocation's unique staging directory.
        if staging.exists():
            for name in ("manifest.json", "source.txt"):
                path = safe_path(staging / name)
                if path.exists():
                    path.unlink()
            safe_path(staging).rmdir()


def capture_file(store: Path, input_file: Path, context: dict, stage: str = "implementation",
                 kind: str = "tool_result", outcome: str = "success",
                 scope: str = "captured tool output", source: str | None = None) -> dict:
    """Capture full source offline and record immutable, mechanically cut events.

    No claim or summary is generated. Scope stays exactly as supplied; source
    annotations and the manifest express partial-source coverage. A success
    outcome denotes the scoped tool process, never business acceptance.
    Repeat calls reuse the initial timestamp.
    A failure after publication leaves its manifest/source and completed events
    intact; retrying fills missing events after verifying all existing content.
    Corruption is reported, never overwritten or silently treated as completion.
    """
    context = validate_context(context)
    store = safe_path(store)
    input_file = safe_path(input_file)
    label = _source_label(input_file.name if source is None else source)
    _text(scope, limit=3500)
    metadata = {"format_version": FORMAT_VERSION, "project_id": context["project_id"],
                "stage": stage, "kind": kind, "outcome": outcome, "scope": scope, "source": label}
    _secret_gate(metadata)
    data, text = _read_source(input_file)
    metadata.update({"source_sha256": _digest(data), "source_bytes": len(data), "source_chars": len(text)})
    capture_id = _digest(canonical(metadata))
    directory = safe_path(store / "captured" / capture_id)
    manifest_path = safe_path(directory / "manifest.json")
    source_path = safe_path(directory / "source.txt")
    _check_identity(store, context["project_id"])
    if directory.exists():
        existing = _read_manifest(manifest_path)
        observed_at = existing.get("observed_at")
    else:
        existing = None
        observed_at = datetime.now(timezone.utc).isoformat()
    events, ranges = _plan(text, metadata, capture_id, observed_at)
    manifest = {**metadata, "capture_id": capture_id, "observed_at": observed_at,
                "offset_unit": "Unicode code points, half-open [start_char,end_char)",
                "source_file": "source.txt", "chunks": ranges}
    if len(canonical(manifest)) + 1 > MAX_MANIFEST_BYTES:
        raise ProcessError("capture manifest exceeds the byte limit")
    if existing is not None:
        if existing != manifest:
            raise ProcessError("capture manifest differs from immutable expected content")
        saved_data, _ = _read_source(source_path)
        if saved_data != data:
            raise ProcessError("capture source differs from immutable expected content")
    verified = _check_events(store, events)
    # All input/schema/path/identity checks above precede any persistent writes.
    _mkdir(store)
    lock = store / ".capture.lock"
    _write_new(lock, b"process-handoff capture\n")
    try:
        _identity(store, context["project_id"], create=True)
        if existing is None:
            _publish_capture(directory, manifest, data)
        recorded = 0
        for event in events:
            if event["id"] in verified:
                continue
            if record_event(store, event) == "recorded":
                recorded += 1
        return {"capture_id": capture_id, "manifest_path": str(manifest_path),
                "source_path": str(source_path), "event_count": len(events),
                "recorded_count": recorded, "unchanged_count": len(events) - recorded,
                "source_bytes": len(data), "source_chars": len(text), "source_sha256": metadata["source_sha256"]}
    except ProcessError:
        raise
    except OSError:
        raise ProcessError("capture failed; retry to verify and fill missing events") from None
    finally:
        safe_path(lock).unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--stage", default="implementation", choices=STAGES)
    parser.add_argument("--kind", default="tool_result", choices=sorted(KINDS - {"claim"}))
    parser.add_argument("--outcome", default="success", choices=("success", "failure", "unknown"))
    parser.add_argument("--scope", default="captured tool output")
    parser.add_argument("--source", help="Logical observation label; defaults to the input filename")
    args = parser.parse_args(argv)
    try:
        result = capture_file(args.store, args.input, read_json(args.context), args.stage,
                              args.kind, args.outcome, args.scope, args.source)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ProcessError as error:
        print(f"capture refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
