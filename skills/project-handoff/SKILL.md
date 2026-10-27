---
name: project-handoff
description: Distill the current session into a concise handoff so a fresh conversation can continue where this one left off.
metadata:
  version: "3.0.0"
---

# Project Handoff 3.0

Write `项目开发交接.md` as a short distillation of the session that just happened. The reader is a fresh agent that cannot see this conversation: it needs the goal, what changed, what was verified, what failed, what is still open, and the first action to take.

This is a session record, not a project database. Do not fingerprint files, assign project IDs, maintain a long-term architecture register, or copy project documentation. Git, tests, issues, and source documents remain their own sources of truth.

**Boundary:** this skill does not finish or merge branches, write implementation plans, or audit the whole project. It only writes the session handoff.

Runtime: Python 3.10 or newer, standard library only. Git is optional. On Windows, use `python -X utf8 -B`.

## Invocation modes

- Default: write or refresh the handoff from the current session.
- Preview: compose and validate without replacing the existing handoff.
- Focus: a supplied next-session focus reprioritizes `下一步第一个动作`.
- Resume: read an existing handoff and continue from its next action; verify its claims instead of trusting labels.

## 1. Fix the session window

- Cover the work visible in this conversation, from the user's current goal to the latest state.
- If the context was compacted, or the goal predates the visible conversation, say so in `session-scope`; do not invent the missing history.
- Read the existing `项目开发交接.md` first. Carry over an item only when it is still open and still relevant, and mark it `（承接上次）`.
- Include earlier project context only when the next action depends on it, and label it as inherited.

## 2. Collect facts

- The goal the user actually pursued, including corrections and scope changes.
- Files and areas changed. In a Git repository, ground this with `git status --short` and `git diff --stat`; do not claim changes you cannot see.
- Commands run and their actual results: tests, builds, checks, deployments, and failures.
- Decisions that constrain the next session, with the reason.
- Failed attempts worth remembering.
- Unresolved questions and the first next action.

Classify each statement as user-confirmed, observed in the workspace, or inferred. Keep inferences as `[待确认]`.

## 3. Distill

Keep only what changes what the next session does. Drop raw transcripts, chain-of-thought, repeated tool output, superseded hypotheses, and assistant proposals the user did not approve.

- `[已验证]`: something was run or inspected and the result is known. State what was checked and the result in the same item.
- `[已实现][未验证]`: the change exists but behavior has not been checked.
- `[待确认]`: unknown, inferred, or waiting on a decision.

Never upgrade a claim because code was written. A passing local test does not prove user acceptance or deployment. Preserve skipped tests and untested paths.

## 4. Write the handoff

Print the metadata block with the helper, then compose the adjacent candidate:

```text
python -B "<skill-dir>/scripts/manage_handoff.py" prepare --root "<project-root>" --session-scope "<one line>"
```

Use the returned block unchanged, including `updated-at` and the Git revision. Then write `项目开发交接.md.candidate`:

```markdown
<!-- project-handoff-meta
format-version: 4
updated-at: <ISO-8601 date-time with timezone>
session-scope: <one line: what this session covered>
source-revision: <Git HEAD|unborn|not-a-git-repository>
working-tree-state: <clean|dirty|not-a-git-repository>
-->
# 项目开发交接

> 新会话先读本文件，从“下一步第一个动作”继续；未验证项不要当作已完成。

<!-- section: goal -->
## 本次会话目标
<the goal this session pursued, in one to three bullets>

<!-- section: work -->
## 做了什么
<files or areas changed, and the result; use [已实现][未验证] for changes not yet checked>

<!-- section: decisions -->
## 关键决策与理由
<decisions that constrain the next session, each with its reason>

<!-- section: verification -->
## 验证情况
<what was run, the actual result, and what was not verified>

<!-- section: pitfalls -->
## 踩坑与失败路径
<failed attempts worth remembering: symptom, cause, avoid, retry condition>

<!-- section: open -->
## 未决问题
<each [待确认] item and the smallest check or decision that resolves it>

<!-- section: next -->
## 下一步第一个动作
<one first action, then its observable acceptance condition>
```

Rules:

- Keep the seven sections in this order. Use flat bullets or numbered lists; put evidence and acceptance conditions in the same item as the claim or action.
- Aim for a few high-signal items per section. The whole file should stay under about 10,000 characters.
- `下一步第一个动作` starts with one action, not a plan. Follow it with the result that shows the action succeeded.
- If the next action depends on a file or external state that is not in Git, name it and say what must be re-checked.

## 5. Validate and save

```text
python -B "<skill-dir>/scripts/manage_handoff.py" save --root "<project-root>" --preview
python -B "<skill-dir>/scripts/manage_handoff.py" save --root "<project-root>"
```

Preview validates the candidate and writes nothing. Save validates again, checks that neither the candidate nor the target changed during the save, replaces the target atomically, and reads the saved file back. On failure the target is left untouched and the candidate is kept for repair. Exit codes: `0` accepted, `1` invalid or warning under `--strict`.

## 6. Report

Tell the user the path, whether the handoff was created, updated, or previewed, which claims are verified and which are not, and the next action. Provide this prompt when no project guidance already points to the handoff:

```text
请先读取当前项目目录中的《项目开发交接.md》，从“下一步第一个动作”继续；未验证项不要当作已完成。
```

For a real acceptance run, read [the consumer contract](references/consumer-contract.md). Static validation does not prove that a fresh session can continue correctly; report the forward test separately.
