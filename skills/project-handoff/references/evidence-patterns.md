# Evidence patterns

Use the claim-review and actionable-unknown guidance below, and read only the row that matches the active project's deliverable. Evidence proves the stated layer only: artifact presence, implementation, verification, acceptance, and deployment are different claims.

| Deliverable | Useful evidence | Do not infer |
|---|---|---|
| Source code or library | Relevant diff, entrypoint, configuration, targeted tests, build/type-check result | A file or passing unit test does not prove user acceptance, integration behavior, or production readiness |
| Spreadsheet or Office artifact | Source inputs, formulas/structure, recalculation, rendered visual inspection, downstream reconciliation | A workbook opening successfully does not prove formulas, totals, layout, or business definitions are correct |
| EXE, CLI, or RPA workflow | Exact packaged path, complete inputs, smoke run, output/log inspection, value reconciliation, failure-path evidence | A normal-path recording or successful launch does not prove retries, deduplication, resumability, or exception handling |
| External API, SaaS, database, or smart table | Active tenant/profile, real object IDs, current permission, write/read-back or equivalent live verification | Documentation, administrator identity, an AppKey, or a successful unrelated API call does not prove target-object access |
| Website or deployment | Build result, deployed revision, stable URL, HTTP/browser behavior, data freshness or backend read-back | A local build or deployment command does not prove the public page is current and usable |
| Research, specification, or decision document | Locked source boundary, dated authoritative sources, explicit unsupported claims, decision owner or user confirmation | Document existence does not prove the recommendation was accepted or implemented |

## Review a material claim

For claims that can change the goal, next action, acceptance, or material risk, separate statements whose evidence differs. For example, implementation, local test success, deployment, and user acceptance each need their own support. Locate and read the relevant source context before judging it; a path, exact quotation, or valid evidence field alone does not establish support.

| Relation to the inspected evidence | Handoff treatment |
|---|---|
| Supported: the source establishes the claim within its stated scope | Retain the claim at that evidence layer, with its original date and applicable revision/environment; check freshness separately |
| Contradicted: applicable evidence establishes the opposite | Correct or remove the claim; retain the observed failure or conflict only when useful for continuation |
| Insufficient: the source is absent, unreadable, silent, narrower than the claim, or the material conflict remains unresolved | Preserve only the supported part; put the decision-changing gap under `[待确认]` with a resolution path |

Apply the source-of-truth conflict order before choosing between sources. Compare like revisions and environments; a past success and a current failure can both be valid observations. A requirement states the intended behavior, not proof of its implementation. If the applicable evidence cannot resolve a conflict, do not select the convenient source or infer success from silence.

These are evidence relations, not additional document status labels. Record the concise outcome and reference, not an internal review transcript. `[已验证]` may describe an observed failure: if the relevant run reports three failed tests, record that result instead of retaining “all tests passed.” Passing local tests alone leaves user acceptance unestablished; it does not prove the user rejected the work. Do not invent confidence percentages or use an overall score to compensate for a missing required check. The validator checks structure and evidence fields; the agent must judge what the sources actually establish.

## Make a material unknown actionable

For each retained `[待确认]` that changes continuation, state the missing evidence or decision, the smallest concrete check or source that can resolve it, and how the possible result affects the dependent action or completion claim. Describe the observable result needed, rather than writing only “investigate” or “confirm later.” Use concise prose in the existing flat item; no additional schema is needed.

Example (illustrative, not a project requirement):

```markdown
- [待确认] 空输入是否被拒绝；缺证据：空输入用例结果；核验：运行该用例，检查约定的错误返回且无输出写入；影响：通过后可确认此异常路径，失败则修复后复测；其他独立用例可继续。
```

Route a resolvable technical gap to an in-scope, authorized check. Consult existing user decisions before requesting a missing preference or permission. When the source is unavailable, name the owner or event that can supply it. Only dependent work is blocked; irrelevant unknowns should be omitted under the context-hygiene rule. A proposed check is a next action, not evidence that the check ran, and no evidence judgment grants authorization.

## Time-sensitive evidence

Treat permissions, tenant IDs, external record IDs, prices, versions, deployments, URLs, and account entitlements as stale unless the current run verifies them. Retain the durable rule or architecture, then mark the live value for revalidation.

## Evidence wording

- Use `[已实现][未验证]` when an artifact exists but behavior has not been checked.
- Use `[已验证]` only with the check, result, an explicit `YYYY-MM-DD` verification date, a concrete code-span or linked evidence reference, and the scope actually covered. This applies to strong claims in every section. Preserve old evidence dates across handoff updates; replace unknown session-relative dates with `[待确认]`, not today's date.
- Use `[用户验收]` only after explicit user acceptance.
- Use `[已部署-已回读]` only after checking the live target; deployment is independent of user acceptance.
- Use `[受阻]` with the blocking condition and the next action or event that can clear it.

## Invalidation conditions

Add one when evidence is tied to mutable state. Typical invalidators are a new source revision, a changed input workbook, expired permission, different tenant or account, deployment replacement, external-record update, or elapsed business date. Durable architecture decisions usually point to their ADR instead of receiving an artificial expiry.

## Critical-file baseline

For a non-Git project, fingerprint only files whose content can change the continuation decision, acceptance, or material risk. Prefer the authoritative requirement, active workbook, RPA package, source deck, or accepted deliverable. Exclude temporary exports, logs, caches, duplicate copies, credentials, and large folders.

For each selected path, state in the handoff what conclusion it supports and what must be revalidated when the fingerprint changes. A matching fingerprint proves only that the selected bytes are unchanged; it does not prove that the business fact remains true or that untracked external state is current.

Git snapshots include staged object IDs and changed/untracked file contents. Ignored artifacts still need explicit critical-file selection. A missing Git executable uses the non-Git baseline; a Git access error stops the check. An empty non-Git baseline returns `LIMITED` (exit 3); `--allow-limited` accepts the document while preserving the `VALID-LIMITED` distinction. A stale snapshot is exit 2 even without `--strict`.
