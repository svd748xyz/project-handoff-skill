---
name: project-handoff
description: Distill the current session into a short 项目开发交接.md so a fresh conversation can continue without the old context, and resume from that file in a new session. Use when the context has been compacted one or more times, the session is long and attention is diluting, or the user wants to switch to a new session — e.g. "写交接", "交接一下", "开新会话", "换个会话继续", "上下文快满了", "存一下进度", "handoff" — and when a new session is asked to read 项目开发交接.md and continue.
metadata:
  version: "3.1.1"
---

# Project Handoff 3.1

Write `项目开发交接.md` in the project root: a short distillation of this session for a fresh agent that cannot see this conversation. The point of starting fresh is to escape a long, repeatedly compacted context, so the handoff carries what the next session needs to act correctly and nothing else: goal and progress, the user's standing instructions, what changed, what is actually verified, what failed, what is open, and where to start.

This is a session record, not a project database. Git, tests, issues, and source documents remain their own sources of truth; point to them instead of copying them.

**Boundary:** this skill does not finish or merge branches, write implementation plans, or audit the whole project. Whether the handoff is committed or ignored by Git is the user's choice; do not edit `.gitignore` unasked.

Runtime: Python 3.10 or newer, standard library only. Git is optional. The scripts print UTF-8 on every platform; use `python3` or `py -3` where `python` is not Python 3.

## Invocation modes

- **Default** — write or refresh the handoff at the end of a session.
- **Checkpoint** — the same procedure mid-session, at a milestone or after the first or second compaction; the session continues afterwards. Earlier is better: every compaction loses detail, and a handoff written from a heavily compacted context inherits those losses.
- **Preview** — compose and validate with `save --preview` without replacing the existing handoff.
- **Focus** — a next-session focus supplied by the user reprioritizes `下一步`.
- **Resume** — a fresh session continues from an existing handoff; follow [Resume](#resume) instead of steps 1–6.

## 1. Inspect the starting point

```text
python -B "<skill-dir>/scripts/manage_handoff.py" inspect --root "<project-root>"
```

It prints the previous handoff's metadata, the commits and tracked changes since that handoff's `source-revision`, and uncommitted files (handoff files excluded), and writes nothing. Use it as the ground truth for what changed: work committed during the session appears here even though `git status` would not show it. Then read the existing `项目开发交接.md`, if any.

## 2. Gather facts from every source

Sources, most reliable first:

1. The workspace: the inspect output, files, and checks you can re-run now.
2. The visible conversation.
3. Compaction summaries of earlier parts of this conversation. After several compactions they are often the only record of early user corrections, decisions, and dead ends, so mine them deliberately instead of relying on the recent turns. A fact found only in a summary that you cannot re-check: keep it, note `（据压缩摘要）`, and make it `[待确认]` if the next action depends on it.
4. The previous handoff.

Collect:

- The overall goal, the current position in it, and the user's corrections or scope changes.
- The user's standing instructions: what to always or never do, language and style, approval requirements, areas not to touch. Compaction loses these most easily, and a fresh session violates them most often.
- Files and areas changed, grounded in the inspect output. Do not claim changes you cannot see.
- Commands run and their actual results.
- Decisions that constrain future work, with the reason.
- Failed attempts a fresh session might repeat.
- Open questions, the first next action, the remaining steps, and the files a fresh session should read before acting.

Do not invent history you cannot see. If the goal predates everything visible, say so in `session-scope`.

## 3. Carry over and distill

For each item in the previous handoff (an older format is read the same way; map its sections onto the current ones):

- **Still in force** — a standing user instruction, a decision not reversed, a pitfall that can still bite — or **still open**: keep it, compressed, marked `（承接上次）`. Constraints, decisions, and pitfalls copied from the previous handoff must carry this marker so the reader can tell inherited items from new ones.
- **Resolved or superseded**: drop it silently; do not record corrections about the previous handoff itself ("上次写的…已过时"). If this session reversed it, record the reversal under decisions only when it constrains future work.

Closed is not obsolete. A decision made three sessions ago that still constrains the work must survive every handoff; otherwise it disappears the first time a session does not touch it.

Then keep only what changes what the next session does. Drop transcripts, chain-of-thought, repeated tool output, superseded hypotheses, and proposals the user did not approve.

- `[已验证]`: something was run or inspected and the result is known. State what was checked and the result in the same item.
- `[已实现][未验证]`: the change exists but its behavior has not been checked.
- `[待确认]`: unknown, inferred, or waiting on a decision.

These are the only labels. The validator rejects any other bracketed label such as `[已提交]`, `[已决定]`, or `[注意]` — write the same idea in plain words instead.

Never upgrade a claim because code was written. A passing local test does not prove user acceptance or deployment. Preserve skipped tests and untested paths. See [evidence patterns](references/evidence-patterns.md) for examples.

## 4. Write the candidate

```text
python -B "<skill-dir>/scripts/manage_handoff.py" prepare --root "<project-root>" --session-scope "<one line>"
```

Start `项目开发交接.md.candidate` with the printed block, unchanged, then fill in:

```markdown
<!-- project-handoff-meta
...block printed by prepare...
-->
# 项目开发交接

> 新会话先读本文件，核对仓库状态，再从“下一步”的第一个动作继续；未验证项不要当作已完成。

<!-- section: goal -->
## 目标与进度
<the overall goal, where the work stands now, and user corrections or scope changes>

<!-- section: constraints -->
## 用户偏好与约束
<standing instructions and preferences from the user that every later session must follow>

<!-- section: work -->
## 做了什么
<files or areas changed and the result; use [已实现][未验证] for changes not yet checked>

<!-- section: decisions -->
## 关键决策与理由
<decisions that constrain future work, each with its reason>

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
## 下一步
- 第一个动作：<the single first action: the work step itself, or the question to ask the user (with its options) when progress is blocked on a user decision>；验收：<the observable result that shows it worked>
- 先读：<files to read first, each with why>
- 后续步骤：<remaining steps as known now; omit this line if there are none>
```

Rules:

- Keep the eight sections in this order with these exact headings. Write `- 无` for a section with nothing to say rather than dropping it.
- Use flat bullets or numbered lists; put evidence and acceptance conditions in the same item as the claim or action.
- Write each fact once, in the section that owns it; other sections refer to it instead of repeating it. Commit hashes and "not committed" notes belong in `做了什么`, not also in the goal or open sections.
- `未决问题` holds only unresolved items. Anything already decided goes to `关键决策与理由`, never to `未决问题` with a status word.
- `session-scope` describes the work of this session, not the handoff itself — never "this handoff generated by …".
- `第一个动作` is one action, not a plan: the work step itself, or — when progress is blocked on a user decision — the specific question to ask, with its options. Re-checking the repo (`git status`, `inspect`) is Resume's job, not a first action. The remaining plan goes in `后续步骤` so the next session knows how far along the work is.
- If the next action depends on state outside Git (a running service, an environment variable, a deployed version, a file outside the project), name it and what must be re-checked.
- Target 3,000–6,000 characters. The validator warns above 8,000 and rejects above 16,000; a longer handoff reintroduces the dilution it exists to escape.

## 5. Save

```text
python -B "<skill-dir>/scripts/manage_handoff.py" save --root "<project-root>"
```

Save validates the candidate, checks that neither the candidate nor the target changed during the save, replaces the target atomically, and reads it back. On failure the target is untouched and the candidate is kept: fix the reported errors and run save again. In Preview mode run `save --preview` instead, which validates and writes nothing. Exit codes: `0` accepted, `1` invalid, or warnings under `--strict`.

The validator checks structure, labels, secrets, placeholders, and size. Its evidence check only catches `[已验证]` items that name no command, file, result, or date at all; whether the evidence is real is on you.

## 6. Report

Tell the user the path; whether the handoff was created, updated, checkpointed, or previewed; which claims are verified and which are not; and the first action. Unless project guidance already points to the handoff, give this prompt for the new session:

```text
请读取当前项目目录中的《项目开发交接.md》，先核对其中 source-revision 与当前仓库状态是否一致，再从“下一步”的第一个动作继续；未验证项不要当作已完成。
```

## Resume

When a fresh session starts from an existing handoff:

1. Run `inspect`. If there are commits or uncommitted changes the handoff does not explain, or the baseline is missing, tell the user before acting: the workspace changed after the handoff was written.
2. Read the handoff completely, then the `先读` files.
3. Cheaply re-check any `[已验证]` item the first action depends on (rerun the test, re-read the lines). Treat `[已实现][未验证]` and `[待确认]` as not done.
4. Restate in three to five lines the goal and progress, the constraints you will follow, and the first action; then take it.
5. Follow `用户偏好与约束` for the whole session, not only the first action.

Do not rewrite the handoff during resume; the next write happens at the next checkpoint or at the end of the session.

To test whether this skill's handoffs actually work, see [the consumer contract](references/consumer-contract.md). Static validation does not prove that a fresh session can continue correctly; report the forward test separately.
