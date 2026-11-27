# Changelog

## 3.2.0 — 2026-11-27

This release optimizes the skill for rapid, low-noise handoffs after heavily compacted sessions without polluting the fresh session's context.

- **One-step save with fresh metadata (`save --session-scope`):** `manage_handoff.py save --session-scope "..."` generates and injects a fresh format-5 metadata block at save time (replacing an existing block or prepending to a body-only candidate), removing the extra `prepare` round-trip and avoiding stale `HEAD`/timestamp drift. `prepare` remains supported.
- **Opt-in user-turn recall (`recall --transcript`):** new read-only subcommand extracts only secret-redacted human user messages from local Antigravity (`USER_INPUT`), Claude Code (`type: user`), Codex (`user_message`/`response_item`), or generic chat JSONL transcripts. Keeps earliest founding constraints and latest pivots within a strict budget while dropping all tool logs and system wrappers.
- **Branch tracking and monorepo scoping:** Git metadata now emits optional `branch` (and `scope-path` when `--root` is a subdirectory of a Git repository). `inspect` scopes `git status`, `git diff --stat`, and `git log` to `.` (relative to `--root`) instead of the entire repository root `:/`, reports `repo-commits-since-baseline` when sibling commits exist, and warns on branch or scope switches. Also fixes a validator bug that rejected `source-revision: unborn` (6 chars) in freshly initialized Git repositories. Format remains **5** (backward-compatible with format-5 handoffs lacking `branch`/`scope-path`).
- **Fix false-positive label rejection in code:** `_validate_labels` now strips inline code spans and fenced code blocks before scanning for unsupported bracketed CJK labels or prose `[已验证]` tokens, so quoted logs like `` `[警告] timeout` `` and commit prefixes like `` `[重构]` `` no longer fail save.
- **Tighter fresh-session anti-pollution checks:**
  - CJK-calibrated size budget: target 2,000–4,500 chars; warn above 6,000 (was 8,000); reject above 12,000 (was 16,000).
  - Warn when `先读` is missing or lists more than 5 files.
  - Warn when `做了什么` makes `[已验证]` claims while `验证情况` records none.
  - Warn when `（承接上次）` carry-overs bloat (≥10 items or >60% of bullets when ≥8 bullets), encouraging graduation of permanent repo rules to `AGENTS.md`/`PITFALLS.md`.
  - Warn when ephemeral session-bound process states (“后台运行中”, “仍在运行”, `PID: ...`) appear without `[待确认]`.
- **SKILL.md & references:** upstreamed the `同步` shorthand mode, explicit anti-abbreviation rule (`[已实现][未验证]`, never `[未验证]`), carry-over graduation/pruning guidance, and the "session-bound state is not progress" rule.

Validation before publication: 63 regression tests (`tools/test_regressions.py`), the isolated installation smoke test (`tools/smoke_install.py`), multi-agent installer tests (`tools/test_installer.py`), release checks (`tools/check_release.py`), `py_compile`, and 17 validator self-test scenarios run locally on Windows.

## 3.1.1 — 2026-11-09

- **Fix:** the status-label check only matched a fixed list of old labels, so a real handoff using `[已提交]`, `[已决定]`, or `[注意]` passed validation. Any bracketed CJK label other than `[已验证]`, `[已实现][未验证]`, and `[待确认]` is now rejected; Markdown links such as `[文档](x.md)`, checkboxes, and ASCII brackets are unaffected. Handoff format stays **5**.
- **SKILL.md rules:** each fact is written once in the section that owns it (commit hashes and "not committed" notes belong in `做了什么`); `未决问题` holds only unresolved items — decided ones go to `关键决策与理由`; stale carry-over is dropped silently instead of annotated; inherited items must carry `（承接上次）`; `session-scope` describes the work, not the handoff.
- **`第一个动作`:** when progress is blocked on a user decision, the first action is the specific question to ask, with its options; re-checking the repo is Resume's job, not a first action.

Validation before publication: 46 regression tests, the isolated installation smoke test, installer tests, release checks, and 14 validator self-test scenarios, run locally on Windows.

## 3.1.0 — 2026-11-09

This release targets the case the skill exists for: a session that has been compacted several times and needs to hand over to a fresh one without losing what compaction has already blurred.

- **Compaction-aware gathering:** compaction summaries are a named source for early decisions, user corrections, and dead ends. Facts found only there are marked `（据压缩摘要）` and become `[待确认]` when the next action depends on them.
- **Carry-over fixed:** items still in force (standing user instructions, unreversed decisions, live pitfalls) are carried into the next handoff, not only open items. Previously a decision was dropped as soon as it was no longer open, so it vanished after one or two handoffs.
- **Template, format 5:** eight sections. `本次会话目标` becomes `目标与进度`; new `用户偏好与约束`; `下一步第一个动作` becomes `下一步`, with `第一个动作` + `验收`, `先读`, and optional `后续步骤`. Empty sections hold `- 无`.
- **New `inspect` command:** prints the previous handoff's metadata, commits and tracked changes since its `source-revision`, uncommitted files, a missing or rewritten baseline, and a leftover candidate. It grounds "what changed" (including committed work) and gives Resume its drift check.
- **New modes:** Checkpoint (write mid-session, before more compaction) and a full Resume procedure: inspect, read, re-check what the first action depends on, restate, act, and keep following the recorded constraints.
- **Simpler save:** the default flow is a single `save`; `--preview` is only for Preview mode. Successful saves print validator warnings.
- **Fix:** `working-tree-state` was always `dirty` once an untracked handoff existed; the handoff and its candidate are now excluded from Git status. Git output keeps non-ASCII paths readable.
- **Fix:** secret detection missed prefixed environment variables such as `OPENAI_API_KEY=...` and `GITHUB_TOKEN=...`; it now also detects `sk-`, `ghp_`, `github_pat_`, `xox?-`, and `AIza` tokens, and accepts references such as `$VAR`, `%VAR%`, and `<redacted>`.
- **Fix:** template placeholders that begin with a keyword (for example `<the single first action>`) or are not in the keyword list went undetected; a whole-line placeholder rule now backs up the keyword list, and a test checks every placeholder in the `SKILL.md` template.
- **Fix:** the first save failed on file systems without hard links; it now falls back to exclusive creation.
- **Fix:** scripts switch their output to UTF-8 themselves; `-X utf8` is no longer required.
- Size budget: target 3,000–6,000 characters; warn above 8,000, reject above 16,000.
- The description now names trigger phrases (`写交接`, `开新会话`, `上下文快满了`, `handoff`, …) and the resume case.
- Format-4 handoffs are still read by `inspect` and carried over by the next write.

Validation before publication: 42 regression tests, the isolated installation smoke test (now including `inspect`), installer tests, release checks, and 13 validator self-test scenarios, run locally on Windows. No forward test with a fresh session has been run for this release yet.

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
