# Changelog

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

Validation before publication: 154 regression tests on Windows (151 passed, 3 skipped because symbolic-link creation was unavailable), isolated installation, release checks, 20 validator self-tests, installed capture/triage/recovery and older-report recovery. GitHub CI is configured for Windows, Linux and macOS across Python 3.10, 3.12 and the current 3.x release. Consult the actual workflow results for platform status; local tests alone do not establish cross-platform acceptance.

### Upgrade

Download and extract the release, run `python -B tools/install.py --agent codex --scope user` to inspect the destination, move the previous installed skill to a backup outside the skill discovery directory, then add `--apply`. Use `python3` or `py -3` where appropriate. Keep project handoffs and process records; upgrading the skill does not require removing them.

### Iteration history

- **2.0:** introduced immutable process records, an optional direct Jev client and recoverable reading packets.
- **2.1:** moved capture and routing ahead of main-model reading; strengthened original-source and recovery integrity.
- **2.1.1:** clarified decision ownership and removed redundant per-record fallback reviews; added explicit continuation tasks.

这些迭代保留了原有交接文档的证据、当前性和安全保存要求，主要重构记录与判断过程。完整原文保留，分流或模型结果不会自动升级业务验收状态。
