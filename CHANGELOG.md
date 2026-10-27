# Changelog

## 3.0.0 — 2026-10-27

This release recenters the skill on its intended purpose: distilling one session into a handoff that a fresh conversation can pick up quickly. It is a breaking rewrite, not an extension of the 2.x project-state workflow.

- Replace the eight-section project-state template with seven session sections: goal, work, decisions, verification, pitfalls, open questions, next action.
- Reduce the metadata block to `format-version`, `updated-at`, `session-scope`, `source-revision`, and `working-tree-state`. Handoff format is now **4**.
- Remove project identity, workspace/project keys, history coverage, critical-file fingerprints, freshness snapshots, and the stale-handoff exit codes.
- Remove the Jev/process pipeline and its scripts, references, tests, and demo: `capture_handoff.py`, `triage_handoff.py`, `process_handoff.py`, `jev_client.py`, `jev-review.md`, `process-workflow.md`. No network calls remain.
- Keep two scripts: `validate_handoff.py` checks structure, headings, labels, secrets, placeholders, and size; `manage_handoff.py` prints format-4 metadata and saves the candidate atomically with change detection and read-back.
- Keep three evidence labels: `[已验证]`, `[已实现][未验证]`, `[待确认]`. `[已验证]` items must name a command, result, file, or date.
- Keep the safe installer and its platform targets. The release check now verifies version consistency across `SKILL.md`, this changelog, the README title, and `agents/openai.yaml`.
- Existing format-3 handoffs are not migrated or read by 3.0. Keep them only as history.

Validation before publication: 26 regression tests on Windows covering the validator and the safe-save helper, the isolated installation smoke test, installer tests, release checks, and 10 validator self-test scenarios. GitHub CI is configured for Windows, Linux, and macOS across Python 3.10, 3.12, and the current 3.x release. Consult the actual workflow results for platform status; local tests alone do not establish cross-platform acceptance.

### Upgrade

Download and extract the release, run `python -B tools/install.py --agent codex --scope user` to inspect the destination, move the previous installed skill to a backup outside the skill discovery directory, then add `--apply`. Use `python3` or `py -3` where appropriate. The installer does not overwrite an existing installation.

## 2.1.1 — 2026-09-23

This release adds a portable process-recording workflow to the existing evidence-backed project handoff.

- **Rules own determined operations:** immutable capture, source identity and hashes, protected constraints/failures, exact duplicates and conservative fallback.
- **Jev owns local semantic choices:** evaluate actual excerpts for relevance and observation equivalence/conflict; validated answers directly change the reading route.
- **The main model owns overall understanding and handoff:** resolve explicit evidence tasks, preserve source/date/scope, and describe the supported state and next action.
- Capture complete UTF-8 tool output before selecting material. Originals remain recoverable by a verified reading label.
- Uncertain relevance, offline mode, unavailable inference and budget fallback retain complete records without creating a relevance-review task for each one.
- Claims, conflicts and ambiguous comparisons generate concrete tasks naming the observations and the resolution needed.
- Keep handoff document format **3**, existing freshness and safe-save checks, explicit invocation and offline use. Recovery reports from 2.1.0 remain readable.
- Include installation instructions for other devices and agents. Live Jev calls require each user's own `TYPESAFE_API_KEY`; no credentials or personal process records are distributed.

### Iteration history

- **2.0:** introduced immutable process records, an optional direct Jev client and recoverable reading packets.
- **2.1:** moved capture and routing ahead of main-model reading; strengthened original-source and recovery integrity.
- **2.1.1:** clarified decision ownership and removed redundant per-record fallback reviews; added explicit continuation tasks.
