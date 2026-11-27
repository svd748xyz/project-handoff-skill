# Evidence patterns

Three labels are enough for a session handoff:

| Label | Use when |
|---|---|
| `[已验证]` | A command, test, build, inspection or live check was run and its result is known. |
| `[已实现][未验证]` | The change exists but its behavior has not been checked. |
| `[待确认]` | The fact is unknown, inferred, stale, or waiting on a decision. |

Do not add other status labels in prose. Brackets inside inline code spans or fenced code blocks (such as `` `[警告] timeout` ``) are treated as code, not status labels. Never abbreviate `[已实现][未验证]` to `[未验证]`. Do not use a percentage or confidence score in place of a check.

## What counts as evidence

| Deliverable | Useful evidence | Do not infer |
|---|---|---|
| Code | Exact command and result, failing/passing test names, diff or file path | Writing the code does not prove it runs |
| Document or spec | Section read, quoted line, rendered output | File existence does not prove the content is correct |
| UI or website | Build result, URL, screenshot or browser check | A local render does not prove the deployed page |
| External service or deployment | Real target ID, read-back, current permission | A successful unrelated call does not prove access |

An evidence item names what was checked and what came back. For example:

- `[已验证]` `python -m pytest tests/test_parser.py -q` → 42 passed; 2026-11-27.
- `[已验证]` Read `src/parser.py` lines 40-88; empty input is rejected by the `if not raw` branch.
- `[已实现][未验证]` Added the retry branch in `src/client.py`; no test run yet.
- `[待确认]` Whether the staging deployment picked up this build; check the deployed revision read-back.

The validator only rejects `[已验证]` items that name no command, file, result, or date, and warns if `做了什么` claims `[已验证]` while `验证情况` records no verified check. It cannot tell whether the named evidence was really produced, so `[已验证]` `parser.py` 没问题 passes the validator and is still a weak claim. Name what came back.

## Session-bound state is not progress

Background jobs, in-flight runs, open dev servers, and unlanded artifacts die when a session ends. Never write “后台运行中” or “仍在运行” as progress. Instead:

- Mark it `[待确认]（未落盘，需重查）`.
- Put the verification step in `下一步` using a landed artifact (file `mtime` and the last log line), never "check whether PID X is still alive".

## Facts from compaction summaries and transcript recall

A compaction summary is a lossy record written by the previous model. Use it, because it is often the only record of early decisions, but do not treat it as observation. If a local JSONL transcript is available after multiple compactions, `manage_handoff.py recall --transcript <path>` can recover the user's own instructions without pulling in noisy tool logs. If a fact exists only in a summary and the workspace cannot confirm it, note `（据压缩摘要）`; if the next action depends on it, label it `[待确认]` and name the check that would confirm it.

## Keep failures

Record a failed path only when a fresh session might repeat it. Compress it to symptom, cause, avoidance, and retry condition. If the cause is not proven, mark it `[待确认]`.

## Time-sensitive facts

Permissions, tenant IDs, URLs, versions, prices and deployment state go stale. State when they were checked and what must be re-checked before relying on them.

## Unknowns must be actionable

For each `[待确认]` that changes the next action, name the missing evidence or decision, the smallest check that resolves it, and what changes depending on the result. "Investigate later" is not enough.

## Size and pre-read budget

A handoff is a reading aid, not a transcript. Aim for **2,000–4,500 characters**; the validator warns above 6,000 and rejects above 12,000. Keep `先读` to 5 or fewer minimal files (with line ranges for large files) so the next session does not spend its fresh context on unnecessary reads.
