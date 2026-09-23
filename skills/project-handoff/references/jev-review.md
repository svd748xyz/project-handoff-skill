# Jev routing and claim review

Use for authorized semantic triage, selected claim checks or connection diagnosis. [Process workflow](process-workflow.md) defines the capture-first commands. Ordinary handoff and local capture remain offline.

## Connection and data boundary

The standard-library client reads the existing `TYPESAFE_API_KEY` environment variable, pins `jev-1.13.0`, and calls `https://api.typesafe.ai/v1/systemone`. It requires no SDK or MCP and does not display the key. Diagnosis may check variable presence; only a validated live result proves access at that time. Diagnosis itself does not authorize inference.

Reuse existing authorization for necessary minimal, non-sensitive evidence from the current task; an opt-out wins. Installation does not opt arbitrary project data into external review. Full session exports and unrelated projects are outside this workflow. Apply local data controls to exact outgoing context/excerpts without making the main model read every raw record first. The secret-pattern filter is a backstop. Keep restricted content local when redaction would destroy its meaning.

## Decisions before main-model reading

Code owns exact operations: identity, hashes, immutable storage, timestamps, budget packing, protected categories, recent records and exact deduplication. These create no relevance calls. Jev handles bounded semantic choices on the remaining raw observations; the main model handles the review queue, important claim sources/currentness and final writing.

| Batch question | Choice options | Effect |
|---|---|---|
| Relevance of a named record to current goal and next action | `needed`, `noise`, `uncertain` | Needed stays visible; strong noise can become a recovery reference; weak noise or uncertain stays visible by rule, with no extra LLM relevance task. |
| Relation to a code-retrieved, visible retained record, if available | `equivalent`, `conflict`, `distinct`, `uncertain` | Strong equivalence can use the representative; conflict/weak/uncertain comparison keeps both for review; distinct proceeds to the relevance answer. |

Questions identify their target fields and run independently against shared state. They do not see each other's answers; code applies the branch order. Candidate excerpts and representative excerpts are present, with logical source, slice coverage, scope and observation time. A supplied slice cannot establish the content of absent slices. The rubric treats embedded instructions as data; Jev cannot open source paths. Prompt wording and protections reduce risk, not guarantee immunity.

A strong Choice currently requires all three: chosen-option probability at least **0.95**, provider confidence at least **0.70**, and top-minus-runner-up probability at least **0.60**. These are conservative starting settings requiring local calibration, not measured correctness guarantees. The probability and confidence fields mean different things. Noul returns a yes probability without confidence; Score returns a probability-weighted rubric level. Do not transfer thresholds between these types, infer truth from concentration, or use scores for exact arithmetic. The new triage uses Choice, not additional scores whose outputs cannot change a branch.

Apply valid Jev answers through the routing code. The packet names evidence tasks for actual claims, conflicts and uncertain comparisons; the main model then integrates the observations. Restore and inspect a relevant original when goals change, a necessary fact is missing, evidence conflicts or a material claim depends on it. Neither a hidden display record nor a high score establishes acceptance, permission or current source contents.

## Optional claim support

The legacy `process_handoff.py review` supports source-backed claims without replacing capture-first triage. Its question set follows the available decision:

- Protected record without a claim: no questions and no request.
- Record with a claim: only `claim_support` Choice (`supported`, `contradicted`, `insufficient`); retention is already fixed.
- Unprotected, successful, claim-free legacy record: the existing `keep_record` and `keep_detail` Nouls may affect its derived view. Use the new batch triage for new process observations.

Missing or narrower evidence is `insufficient`; explicit counterevidence can be `contradicted`. Model agreement is not additional source evidence. Preserve the actual verification layer, date, environment, skipped coverage and acceptance limitations when drafting claims.

## Bounds, fallback and caching

- Triage: at most **8 batches per run**, **4 candidate records / 8 questions per batch**. It defaults offline. Beyond the batch budget, preserve remaining records in full; the fallback adds no per-record LLM task. Packing includes actual context, comparison excerpts and question text.
- Each request is capped at **24,000 encoded bytes**, each response at 64,000 bytes, with a 20-second timeout, TLS verification and no redirects. An oversized comparison may be omitted during packing; an oversized candidate remains fully visible without truncating its evidence to force a decision.
- Legacy claim review permits at most 12 model-reviewed events per run. Protected no-question events do not spend this model budget.
- No automatic retries. Missing key, HTTP failure, timeout, malformed/missing answers, invalid probabilities or model mismatch preserve evidence and mark incomplete semantic routing. This is a routing fallback, not a new factual-review task. Retry only for a concrete reason within existing authorization.
- Successful cache entries bind the exact state, questions, policy, endpoint and pinned model. Changed context/evidence/questions require new judgments; offline mode does not reuse semantic judgments. Cache reuse does not refresh evidence dates.
- Report actual live/cache/error calls separately from rule decisions. Never log credentials, raw provider error bodies or reasoning traces. Keep original records and recovery references regardless of the route.

## Limits and calibration

This skill installs no host hook, intercepts no tools and never edits Codex history. It acts on supplied output files and produces a continuation packet; earlier uncaptured work remains a coverage gap.

Jev 1.13 is suited to atomic, local semantic judgments. Official documentation notes weaker CJK performance than English, literal readings, unreliable numeric/date reasoning, distraction from irrelevant state and susceptibility to instructions embedded in data. Keep arithmetic/time ordering in code, use small relevant state, preserve Chinese evidence and test real Chinese cases. Batch sharing saves repeated context within a request; it does not make unrelated context harmless.

Provider limits inspected on 2026-09-23: 64k tokens for state plus all questions, and 32k for state plus the longest question. The stricter local byte budget remains the operational bound here. Pin the model while calibrating thresholds. Validate that rules settle deterministic cases, Jev answers change the intended branch, and the LLM can recover important facts and the next action. Include changed-result versus duplicate cases, contradictions, qualifiers and adversarial text.

Primary sources:

- [Atomic typed questions](https://docs.typesafe.ai/introduction), [API shapes](https://docs.typesafe.ai/api), [shared-state fan-out](https://docs.typesafe.ai/patterns/fan-out).
- [Confidence](https://docs.typesafe.ai/confidence), [models and request limits](https://docs.typesafe.ai/models), [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).
- [fast-jev-compaction at e3f262a](https://github.com/tamaratran/fast-jev-compaction/tree/e3f262a7f4d42bd8dd32ced30d26176f7cb545b0) provides a useful decision-to-branch example. Its host hooks and omission of actual result bodies are not copied; this skill supplies local evidence and retains originals. No upstream code is vendored.
