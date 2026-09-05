# Evidence patterns

Read only the row that matches the active project's deliverable. Evidence proves the stated layer only: artifact presence, implementation, verification, acceptance, and deployment are different claims.

| Deliverable | Useful evidence | Do not infer |
|---|---|---|
| Source code or library | Relevant diff, entrypoint, configuration, targeted tests, build/type-check result | A file or passing unit test does not prove user acceptance, integration behavior, or production readiness |
| Spreadsheet or Office artifact | Source inputs, formulas/structure, recalculation, rendered visual inspection, downstream reconciliation | A workbook opening successfully does not prove formulas, totals, layout, or business definitions are correct |
| EXE, CLI, or RPA workflow | Exact packaged path, complete inputs, smoke run, output/log inspection, value reconciliation, failure-path evidence | A normal-path recording or successful launch does not prove retries, deduplication, resumability, or exception handling |
| External API, SaaS, database, or smart table | Active tenant/profile, real object IDs, current permission, write/read-back or equivalent live verification | Documentation, administrator identity, an AppKey, or a successful unrelated API call does not prove target-object access |
| Website or deployment | Build result, deployed revision, stable URL, HTTP/browser behavior, data freshness or backend read-back | A local build or deployment command does not prove the public page is current and usable |
| Research, specification, or decision document | Locked source boundary, dated authoritative sources, explicit unsupported claims, decision owner or user confirmation | Document existence does not prove the recommendation was accepted or implemented |

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
