# Evidence patterns

Three labels are enough for a session handoff:

| Label | Use when |
|---|---|
| `[已验证]` | A command, test, build, inspection or live check was run and its result is known. |
| `[已实现][未验证]` | The change exists but its behavior has not been checked. |
| `[待确认]` | The fact is unknown, inferred, stale, or waiting on a decision. |

Do not add other status labels. Do not use a percentage or confidence score in place of a check.

## What counts as evidence

| Deliverable | Useful evidence | Do not infer |
|---|---|---|
| Code | Exact command and result, failing/passing test names, diff or file path | Writing the code does not prove it runs |
| Document or spec | Section read, quoted line, rendered output | File existence does not prove the content is correct |
| UI or website | Build result, URL, screenshot or browser check | A local render does not prove the deployed page |
| External service or deployment | Real target ID, read-back, current permission | A successful unrelated call does not prove access |

An evidence item names what was checked and what came back. For example:

- `[已验证]` `python -m pytest tests/test_parser.py -q` → 42 passed; 2026-11-09.
- `[已验证]` Read `src/parser.py` lines 40-88; empty input is rejected by the `if not raw` branch.
- `[已实现][未验证]` Added the retry branch in `src/client.py`; no test run yet.
- `[待确认]` Whether the staging deployment picked up this build; check the deployed revision read-back.

The validator only rejects `[已验证]` items that name no command, file, result, or date. It cannot tell whether the named evidence was really produced, so `[已验证]` `parser.py` 没问题 passes the validator and is still a weak claim. Name what came back.

## Facts from compaction summaries

A compaction summary is a lossy record written by the previous model. Use it, because it is often the only record of early decisions, but do not treat it as observation. If a fact exists only in a summary and the workspace cannot confirm it, note `（据压缩摘要）`; if the next action depends on it, label it `[待确认]` and name the check that would confirm it.

## Keep failures

Record a failed path only when a fresh session might repeat it. Compress it to symptom, cause, avoidance, and retry condition. If the cause is not proven, mark it `[待确认]`.

## Time-sensitive facts

Permissions, tenant IDs, URLs, versions, prices and deployment state go stale. State when they were checked and what must be re-checked before relying on them.

## Unknowns must be actionable

For each `[待确认]` that changes the next action, name the missing evidence or decision, the smallest check that resolves it, and what changes depending on the result. "Investigate later" is not enough.

## Size

A handoff is a reading aid, not a transcript. Aim for 3,000–6,000 characters; the validator warns above 8,000 and rejects above 16,000.
