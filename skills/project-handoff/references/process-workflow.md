# Process capture, triage and handoff

Use for requested ongoing records. Keep the identity, evidence, freshness and atomic-save contract in `SKILL.md`. Ordinary handoff needs neither process capture nor Jev.

## Decision ownership

| Owner | Responsibility | Finished when |
|---|---|---|
| Rules / scripts | Capture complete output, check identity and hashes, protect boundaries and failures, handle exact duplicates, apply thresholds, preserve fallback text and produce the next-step plan. | Each supplied record has a route and a recovery reference; missing or corrupt material is reported. These decisions require no model vote. |
| Jev | Answer a bounded relevance or observation-comparison question using the actual local evidence. | The validated answer changes retain/reference/review through code. It is not an advisory score awaiting the LLM's approval. |
| LLM | Set the goal and context, understand the selected observations together, resolve material evidence questions, and compose the handoff with an executable next step. | Claims keep their source/date/scope, unresolved gaps have a clearing action, and continuation is possible without inventing project state. |

Keep a question with its owner. For example, hashes determine whether two same-source excerpts are byte-identical; Jev determines whether two differently worded observations describe the same event; the LLM reconciles conflicting observations with project history. A routing fallback already has a rule: preserve the original. It needs no separate relevance decision from the LLM.

## Working order

1. **Start/resume:** establish project identity, goal, boundaries and next action. Reuse the handoff UUID; for a new project generate one once and pass it later to `manage_handoff.py prepare --project-id`. Freshness-check an existing handoff. State when capture starts and what earlier evidence is unavailable.
2. **Capture before reading:** where the tool supports an output file, write its complete relevant textual result directly to UTF-8, retaining the command/tool locator and execution outcome. Call `capture_handoff.py` with that file. The helper copies the original bytes, records mechanical slices and writes a recovery manifest; the main model does not first read the whole output, summarize it, manufacture a claim or choose excerpts. Supply the known stage, category and actual scope. Tool-process success is not test or business acceptance.
3. **Record boundaries:** capture user constraints/corrections, decisions, blockers and acceptance boundaries with their protected category as they occur. Preserve corrections as new records. Place authorization/stop conditions and external-action receipts under `decision` or `acceptance`. Preserve failures and unknown outcomes. A category does not confer approval or `[用户验收]`.
4. **Triage at a stage boundary:** run `triage_handoff.py` with current context before reading the stored output. Default offline mode applies protection and exact deduplication. With existing Jev authorization, `--mode live` routes the remaining observations in bounded batches. Do not preselect a few claims for Jev after already doing its reading work.
5. **Continue from the packet:** read `packet.md`, including its coverage and next step. The script lists concrete evidence tasks for claims, conflicts and ambiguous comparisons. Resolve those tasks, or reuse an unchanged source-backed resolution, then synthesize; with no evidence tasks, synthesize directly. Keep source/date/scope/currentness checks for important claims. Read `report.json` or `metrics.json` only when diagnosing routing or auditing coverage. Open a reference-only original when a needed fact is absent, goals change, evidence conflicts or a material decision depends on it. On a new goal, update context and rerun triage into a new directory.
6. **Handoff:** write the concise state contract from selected material and resolved gaps. Include actual protected objects, historical skipped/untested paths, and distinct source/uncommitted/installed/released/deployed states. Finish supporting-file writes, then `prepare → candidate → preview → save`. Writes after `prepare` require evidence reconciliation and new metadata.

No helper intercepts tools or replaces native context compaction. If a tool only returns visible output, capture its actual result without claiming it was filtered before reading. Coverage is all supplied records, not all project activity.

## Inputs and commands

Choose an authorized local store such as `.project-handoff`. It may contain project data; publishing the skill does not authorize publishing its records. Helpers do not edit `.gitignore` or `AGENTS.md`.

`context.json` has exactly these fields (synthetic example; use the real stable UUID and task):

```json
{
  "project_id": "46c59f07-c3b7-4e27-9c2c-ec91ad223dee",
  "goal": "Complete the CSV parser with invalid-input diagnostics.",
  "boundaries": ["Local tests only; production acceptance is pending."],
  "next_action": "Run the empty-input test before preparing the handoff."
}
```

Substitute actual paths below. Use `python -X utf8 -B` on Windows. Keep supplied input files outside reserved store subdirectories; use a logical `--source` label rather than an absolute local path. The credential filter is a local backstop, not an anonymization guarantee.

```text
python -B "<skill-dir>/scripts/capture_handoff.py" --store "<project-root>/.project-handoff" --input "<tool-output.txt>" --context "<context.json>" --stage verification --kind tool_result --outcome success --scope "Local parser test execution; not business acceptance" --source "parser-test-run"
python -B "<skill-dir>/scripts/triage_handoff.py" --store "<project-root>/.project-handoff" --context "<context.json>" --out "<new-triage-directory>"
python -B "<skill-dir>/scripts/triage_handoff.py" --store "<project-root>/.project-handoff" --context "<context.json>" --out "<another-new-triage-directory>" --mode live
```

Capture is offline and generates no claims. It stores `captured/<capture-id>/source.txt`, a manifest with hashes/ranges, and immutable `events/*.json`; slices are at most 6,000 characters. A slice is not the full source. An identical capture reuses verified content; conflicting or corrupt records fail instead of overwriting. Inspect capture completion before triage. Hashes prove byte identity, not source truth or currentness.

Triage output directories must be new and on the same volume as the store for recovery references. Its three outputs are `packet.md` (reading entrypoint and next step), `metrics.json` (audit counts) and `report.json` (decisions, `workflow.next_step`, `workflow.evidence_tasks` and audit hashes). Reading labels such as R001 identify the observations in each task. Recover one exact original with `python -B "<skill-dir>/scripts/triage_handoff.py" --report "<triage-directory>/report.json" --restore R001`; this is local, read-only and verifies its identity/hash, including reports from 2.1.0. A successful triage exit may include incomplete semantic routing: those unassessed records remain visible. This status is separate from factual review and does not block synthesis.

## Routing contract

| Path | Action and main-model work |
|---|---|
| Protected category, failed/unknown outcome, explicit problem marker or recent tool result | Keep the full record by rule; no relevance request. Inspect important evidence when it supports a handoff claim. |
| Supplied claim | Keep both claim and excerpt in the review queue; use optional claim support or source inspection, with no redundant retention question. |
| Exact duplicate with the same logical source, type, stage, scope and outcome | Keep a visible full representative and both recovery references; no Jev request. |
| Remaining record, `needed` answer | Keep its original excerpt; a lower confidence on conservative retention alone creates no extra review task. |
| Strong `noise` answer, or strong `equivalent` comparison with a visible retained representative | Move only this record's display to a recovery reference. Originals remain unchanged. |
| Uncertain relevance, weak proposed omission, unavailable model, exceeded budget or offline semantic candidate | Keep the full original by rule. Continue synthesis without an extra per-record relevance review. |
| Recognizable embedded route instructions | Preserve as source data; the rule fixes its lack of instruction authority. A separate claim still needs its evidence check. |
| Conflict or uncertain comparison | Keep both observations and create an LLM evidence task with both labels and a concrete resolution instruction. |

The default recent protection is two tool-result records. Use `--recent` only for a reason supported by the task. Similarity retrieval proposes a comparison in the same stage/scope; it never proves equivalence. Jev sees actual candidate and representative excerpts, logical source labels and slice coverage. Distinct sources are not merged even when the returned comparison says equivalent. Triage refuses active or incomplete captures and verifies saved source/event hashes. The code handles answer dependencies and gives conflict/uncertain comparison precedence over hiding a record. Strong routing uses the policy and limits in [Jev routing](jev-review.md); it is not verified accuracy.

A protected record may still need claim-support review, source currentness or business acceptance. These are separate from whether its text stays visible. Ask a semantic question only when its answer can change an unresolved branch.

Finish evidence tasks with a supported conclusion or an explicit gap and smallest clearing action. Put material resolutions in the handoff or a protected decision with the original evidence references; keep both observations when equivalence is unresolved. A decision about text routing never clears a business blocker or grants authorization. Only dependent actions wait on an unresolved gap; independent in-scope work can continue.

## Optional claim check and legacy records

Use `process_handoff.py record` for an existing structured event or a material claim that needs explicit evidence review. The event fields are `id`, `project_id`, `stage`, `kind`, `source`, timezone-bearing `observed_at`, `scope`, `excerpt`, `outcome`, and optional `claim`. Stages are `requirements`, `discovery`, `implementation`, `verification`, `handoff`, `resume`; kinds are `tool_result`, `user_constraint`, `user_correction`, `decision`, `blocker`, `acceptance`, `claim`; outcomes are `success`, `failure`, `unknown`. IDs are stable, at most 80 letters/digits/underscores/hyphens and immutable for different content. Capture generates these mechanically for ordinary results.

```text
python -B "<skill-dir>/scripts/process_handoff.py" record --store "<store>" --event "<event.json>"
python -B "<skill-dir>/scripts/process_handoff.py" review --store "<store>" --context "<context.json>" --out "<new-claim-review-directory>" --mode live --event-id "<claim-event-id>"
```

Legacy review defaults to offline and retains records. In live mode, a protected record without a claim sends no questions; a claim-bearing record sends only `claim_support`. An unprotected claim-free legacy record can still use its two retention questions, but new process work uses batch triage as the entrypoint. This avoids duplicating the same judgment across both paths.

For claim support, apply its branch: `supported` supplies a candidate conclusion limited to the cited source/date/scope; `contradicted` triggers correction or a source recheck; `insufficient` keeps an explicit gap and smallest clearing action. The LLM integrates that result with project context and current evidence, rather than routinely repeating the same semantic vote. Keep unresolved material gaps as `[待确认]` with their clearing condition. Retain historical evidence dates.

## Report what changed

Report the resulting project state, material corrections, unresolved evidence tasks and the next action with its acceptance condition. Evaluate this workflow by complete records, correct responsibility boundaries, evidence-backed handoffs and successful continuation. Operational counts remain in the audit files; resource benchmarking is separate work only when requested. Distinguish static checks, simulated branches, real Jev results and real-project acceptance. Any unrecorded interval, skipped test or unverified external result stays a named gap.
