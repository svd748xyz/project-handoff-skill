---
name: project-handoff
description: Distill the current session into a short 项目开发交接.md so a fresh conversation can continue without the old context, and resume from that file in a new session. Use when the context has been compacted one or more times, the session is long and attention is diluting, or the user wants to switch to a new session — e.g. "写交接", "交接一下", "同步", "开新会话", "换个会话继续", "上下文快满了", "存一下进度", "handoff" — and when a new session is asked to read 项目开发交接.md and continue.
metadata:
  version: "3.2.0"
---

# Project Handoff 3.2

Write `项目开发交接.md` in the project root: a short distillation of this session for a fresh agent that cannot see this conversation. The point of starting fresh is to escape a long, repeatedly compacted context, so the handoff carries what the next session needs to act correctly and nothing else: goal and progress, the user's standing instructions, what changed, what is actually verified, what failed, what is open, and where to start.

This is a session record, not a project database. Git, tests, issues, and source documents remain their own sources of truth; point to them instead of copying them.

**Boundary:** this skill does not finish or merge branches, write implementation plans, or audit the whole project. Whether the handoff is committed or ignored by Git is the user's choice; do not edit `.gitignore` unasked.

Runtime: Python 3.10 or newer, standard library only. Git is optional. The scripts print UTF-8 on every platform; use `python3` or `py -3` where `python` is not Python 3.

## Invocation modes

- **Default** — write or refresh the handoff at the end of a session.
- **同步** — shorthand for Default: when the user says “同步”, rewrite the handoff in place immediately with no extra confirmation.
- **Checkpoint** — the same procedure mid-session, at a milestone or after the first or second compaction; the session continues afterwards. Earlier is better: every compaction loses detail, and a handoff written from a heavily compacted context inherits those losses.
- **Preview** — compose and validate with `save --preview` without replacing the existing handoff.
- **Focus** — a next-session focus supplied by the user reprioritizes `下一步`.
- **Resume** — a fresh session continues from an existing handoff; follow [Resume](#resume) instead of steps 1–6.

## 1. Inspect the starting point

Run `inspect` and read the existing `项目开发交接.md` (if present) in the same turn:

```text
python -B "<skill-dir>/scripts/manage_handoff.py" inspect --root "<project-root>"
```

It prints the previous handoff's metadata, the current branch and subdirectory scope (when `--root` is a monorepo subdirectory), the scoped commits and tracked changes since `source-revision`, and uncommitted files (handoff files excluded), and writes nothing. Use it as the ground truth for what changed: work committed during the session appears here even though `git status` would not show it.

**Optional — recover lost user instructions after multiple compactions:** if this session went through multiple compactions and you know the local JSONL transcript path for this conversation, run `recall` in the same turn to pull back only the user's own messages (secret-redacted, no tool logs):

```text
python -B "<skill-dir>/scripts/manage_handoff.py" recall --transcript "<transcript-jsonl>"
```

Skip `recall` on short, uncompacted sessions or when no transcript path is available.

## 2. Gather facts from every source

Sources, most reliable first:

1. The workspace: the inspect output, files, and checks you can re-run now.
2. The visible conversation (and `recall` user turns, if used).
3. Compaction summaries of earlier parts of this conversation. After several compactions they are often the only record of early user corrections, decisions, and dead ends, so mine them deliberately instead of relying on the recent turns. A fact found only in a summary that you cannot re-check: keep it, note `（据压缩摘要）`, and make it `[待确认]` if the next action depends on it.
4. The previous handoff.

Collect:

- The overall goal, the current position in it, and the user's corrections or scope changes.
- The user's standing instructions: what to always or never do, language and style, approval requirements, areas not to touch. Compaction loses these most easily, and a fresh session violates them most often.
- Files and areas changed, grounded in the inspect output. Do not claim changes you cannot see.
- Commands run and their actual results.
- Decisions that constrain future work, with the reason.
- Failed attempts a fresh session might repeat.
- Open questions, the first next action, the minimal files a fresh session should read first, and the remaining steps.

Do not invent history you cannot see. If the goal predates everything visible, say so in `session-scope`.

## 3. Carry over and distill

For each item in the previous handoff (an older format is read the same way; map its sections onto the current ones):

- **Still in force** — a standing user instruction, a decision not reversed, a pitfall that can still bite — or **still open**: keep it, compressed, marked `（承接上次）`. Constraints, decisions, and pitfalls copied from the previous handoff must carry this marker so the reader can tell inherited items from new ones.
- **Resolved or superseded**: drop it silently; do not record corrections about the previous handoff itself ("上次写的…已过时"). If this session reversed it, record the reversal under decisions only when it constrains future work.
- **Graduate permanent rules instead of hoarding them**: closed is not obsolete, so an active constraint must survive handoffs — but if a repo-wide rule or pitfall has survived multiple handoffs and belongs to the whole project permanently, suggest promoting it into `AGENTS.md`, `CLAUDE.md`, or `PITFALLS.md` in your report so the handoff does not accumulate zombie carry-overs. Drop task-scoped decisions and pitfalls once their task finishes.

Keep only what changes what the next session does. Drop transcripts, chain-of-thought, repeated tool output, superseded hypotheses, and proposals the user did not approve.

- `[已验证]`: something was run or inspected and the result is known. State what was checked and the result in the same item.
- `[已实现][未验证]`: the change exists but its behavior has not been checked.
- `[待确认]`: unknown, inferred, or waiting on a decision.

These are the only status labels. The validator rejects any other bracketed CJK label in prose such as `[已提交]`, `[已决定]`, or `[注意]` — write the same idea in plain words instead (brackets inside inline code spans or fenced code blocks are ignored). Never abbreviate: implemented-but-unchecked is `[已实现][未验证]`, not `[未验证]`; the short form makes the save fail only after the whole file has been written.

Session-bound state is not progress. Background jobs, runs in flight, and artifacts that have not landed yet die with the session, so a recorded “进行中” or “后台运行中” becomes a false claim the next session trusts. Write it as `[待确认]（未落盘，需重查）` and put the check itself into `下一步` — report mtime and the last log line, never “is the process still alive”.

Never upgrade a claim because code was written. A passing local test does not prove user acceptance or deployment. Preserve skipped tests and untested paths. See [evidence patterns](references/evidence-patterns.md) for examples.

## 4. Write the candidate

Write `项目开发交接.md.candidate` directly starting at `# 项目开发交接` — `save --session-scope` automatically generates and prepends the fresh `project-handoff-meta` block at save time, so you do not need a separate `prepare` call (`prepare` remains available when composing manually).

```markdown
<!-- project-handoff-meta
...auto-filled by save --session-scope (or printed by prepare)...
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
<failed attempts worth remembering: symptom, cause, avoidance, retry condition>

<!-- section: open -->
## 未决问题
<each [待确认] item and the smallest check or decision that resolves it>

<!-- section: next -->
## 下一步
- 第一个动作：<the single first action: the work step itself, or the question to ask the user (with its options) when progress is blocked on a user decision>；验收：<the observable result that shows it worked>
- 先读：<files to read first (<=5 minimal files, with line ranges for large files), each with why>
- 后续步骤：<remaining steps as known now; omit this line if there are none>
```

Rules:

- Keep the eight sections in this order with these exact headings. Write `- 无` for a section with nothing to say rather than dropping it.
- Use flat bullets or numbered lists; put evidence and acceptance conditions in the same item as the claim or action.
- Write each fact once, in the section that owns it; other sections refer to it instead of repeating it. Commit hashes and "not committed" notes belong in `做了什么`, not also in the goal or open sections.
- `未决问题` holds only unresolved items. Anything already decided goes to `关键决策与理由`, never to `未决问题` with a status word.
- `session-scope` describes the work of this session, not the handoff itself — never "this handoff generated by …".
- `第一个动作` is one action, not a plan: the work step itself, or — when progress is blocked on a user decision — the specific question to ask, with its options. Re-checking the repo (`git status`, `inspect`) is Resume's job, not a first action. The remaining plan goes in `后续步骤` so the next session knows how far along the work is.
- Keep `先读` to **5 or fewer** minimal files (name line ranges or sections for large files) so the fresh session does not blow its context budget before acting.
- If the next action depends on state outside Git (a running service, an environment variable, a deployed version, a file outside the project), name it and what must be re-checked.
- Target **2,000–4,500 characters**. The validator warns above 6,000 and rejects above 12,000; a longer handoff reintroduces the dilution it exists to escape.

## 5. Save

```text
python -B "<skill-dir>/scripts/manage_handoff.py" save --root "<project-root>" --session-scope "<one line>"
```

Save injects fresh metadata (including `source-revision`, `working-tree-state`, `branch`, and `scope-path` for monorepo subdirectories), validates the composed handoff, checks that neither the candidate nor the target changed during the save, replaces the target atomically, and reads it back. On failure the target is untouched and the candidate is kept: fix the reported errors and run save again. In Preview mode run `save --preview --session-scope "<one line>"` instead, which validates and writes nothing. Exit codes: `0` accepted, `1` invalid, or warnings under `--strict`.

The validator checks structure, labels, secrets, placeholders, `先读` count, ephemeral-state phrasing, carry-over bloat, and size. Its evidence check only catches `[已验证]` items that name no command, file, result, or date at all; whether the evidence is real is on you.

## 6. Report

Tell the user the path; whether the handoff was created, updated, checkpointed, or previewed; which claims are verified and which are not; any permanent carry-over rules worth promoting to project docs; and the first action. Unless project guidance already points to the handoff, give this prompt for the new session:

```text
请读取当前项目目录中的《项目开发交接.md》，先核对其中 source-revision、branch 与当前仓库状态是否一致，再从“下一步”的第一个动作继续；未验证项不要当作已完成。
```

## Resume

When a fresh session starts from an existing handoff:

1. Run `inspect`. If the branch changed, or there are commits or uncommitted changes the handoff does not explain, or the baseline is missing, tell the user before acting: the workspace changed after the handoff was written.
2. Read the handoff completely, then only the `先读` files (and line ranges) listed.
3. Cheaply re-check any `[已验证]` item the first action depends on (rerun the test, re-read the lines). Treat `[已实现][未验证]` and `[待确认]` as not done.
4. Restate in three to five lines the goal and progress, the constraints you will follow, and the first action; then take it.
5. Follow `用户偏好与约束` for the whole session, not only the first action.

Do not rewrite the handoff during resume; the next write happens at the next checkpoint or at the end of the session.

To test whether this skill's handoffs actually work, see [the consumer contract](references/consumer-contract.md). Static validation does not prove that a fresh session can continue correctly; report the forward test separately.
