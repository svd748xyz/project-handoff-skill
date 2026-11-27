# Project Handoff Skill 3.2.0

`project-handoff` distills the session that just happened into a short `项目开发交接.md`, so a fresh coding-agent session can continue without reading the previous conversation.

The handoff carries the goal and progress, the user's standing instructions, what changed, decisions that constrain future work, what was actually verified, failed paths worth remembering, open questions, and where to start. It deliberately leaves out transcripts, repeated tool output, superseded hypotheses, and unapproved proposals.

## Why this exists

A long session that has been compacted several times dilutes the model's attention and silently loses early details. Starting a fresh session fixes the dilution, but the new session starts with nothing. This skill produces a small, portable session record that the next session can read in one pass, and tells that session how to check it against the workspace before acting.

It is not a project wiki, a long-term architecture register, or a replacement for Git, tests, issues, or source documents. It records the working state and the next action.

## What changed in 3.2.0

- **Faster 2-step sync (`save --session-scope`):** `manage_handoff.py save --session-scope "..."` now computes and injects fresh format-5 metadata directly at save time, eliminating the separate `prepare` round-trip and avoiding `HEAD`/timestamp drift between preparing and saving. `prepare` remains available for manual use.
- **Opt-in user-turn recovery (`recall`):** `manage_handoff.py recall --transcript <path>` extracts only secret-redacted human user messages from local Antigravity, Claude Code, Codex, or generic JSONL transcripts (keeping earliest founding constraints and latest pivots within a tight character budget, with zero tool logs) to rescue early constraints lost to multiple compactions.
- **Branch tracking and monorepo subdirectory scoping:** Git metadata now records `branch` (and `scope-path` when `--root` is a subdirectory of a Git repository). `inspect` scopes `git status`, `git diff --stat`, and `git log` to `--root` so sibling monorepo projects no longer pollute handoffs, and warns on branch switches or scope drift.
- **Stronger anti-pollution guardrails in the validator:**
  - Ignores brackets inside inline code spans and fenced code blocks so quoted logs or commit prefixes like `` `[警告] timeout` `` are no longer rejected as invalid status labels.
  - Tighter CJK-friendly size budget: target **2,000–4,500 characters**, warn above **6,000**, reject above **12,000**.
  - Warns when `先读` is missing or lists more than 5 files (preventing fresh-session pre-read bloat), when `做了什么` claims `[已验证]` while `验证情况` records none, when `（承接上次）` carry-overs accumulate excessively (prompting graduation to `AGENTS.md`/`PITFALLS.md`), or when ephemeral session-bound process states (“后台运行中” / “仍在运行” / `PID: ...`) appear without `[待确认]`.
- **Battle-tested session rules upstreamed to `SKILL.md`:** adds the `同步` shorthand mode, explicit reminder not to abbreviate `[已实现][未验证]` to `[未验证]`, graduation/pruning rules for carry-overs, and the "session-bound state is not progress" rule. Handoff format remains **5** (optional `branch` and `scope-path` metadata keys are backward-compatible).

## What changed in 3.1.1

- The validator rejects every unsupported bracketed CJK label (`[已提交]`, `[已决定]`, `[注意]`, …), not just a fixed list of old ones; Markdown links like `[文档](x.md)`, checkboxes, and ASCII brackets are unaffected.
- `SKILL.md` writing rules tightened: each fact is written once in the section that owns it; `未决问题` holds only unresolved items; stale carry-over is dropped silently; inherited items must carry `（承接上次）`; `session-scope` describes the work, not the handoff; and `第一个动作` names the user-decision question when progress is blocked instead of re-checking the repo.

## Download and install

The repository is public and can be installed independently on any device. It needs Python 3.10+; the scripts use only the standard library. Licensed under [MIT](LICENSE).

- [Latest source](https://github.com/svd748xyz/project-handoff-skill): follows `main`.
- [Releases](https://github.com/svd748xyz/project-handoff-skill/releases): pick a fixed version.
- [3.2.0 notes](CHANGELOG.md): what changed in this release.

Download and extract the release, then from the directory containing `tools/` and `skills/`:

```text
python -B tools/install.py --agent codex --scope user
python -B tools/install.py --agent codex --scope user --apply
```

The first command prints the destination; the second installs. On macOS/Linux use `python3` if `python` is unavailable; on Windows `py -3` also works. For Claude Code, use `--agent claude --explicit-only`.

After installing, invoke `$project-handoff` in a new task, or `/project-handoff` in Claude Code.

**Upgrading:** run the first command to confirm the target path, move the existing `project-handoff` folder to a backup outside the skill discovery directory, then install. The installer never overwrites an existing directory. Existing format-5 and format-4 handoffs are read cleanly by `inspect` and carried over by the next write. Format-3 documents from 2.x are not migrated.

## Repository layout

```text
project-handoff-skill/
├── .github/workflows/ci.yml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── tools/
│   ├── install.py
│   ├── test_installer.py
│   ├── test_regressions.py
│   ├── smoke_install.py
│   └── check_release.py
└── skills/project-handoff/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── scripts/
    │   ├── validate_handoff.py
    │   └── manage_handoff.py
    └── references/
        ├── consumer-contract.md
        └── evidence-patterns.md
```

## Requirements

- Python 3.10 or newer
- Git is optional; when present, the metadata records `HEAD`, `branch`, working-tree state, and monorepo `scope-path` when inside a subdirectory
- A coding agent that supports Agent Skills-style `SKILL.md` packages, or can follow the instructions manually

The scripts use only the Python standard library and make no network requests. They read and write UTF-8 and switch their own output to UTF-8, so Chinese paths and content work without `-X utf8` on Windows.

## Safe multi-agent installer

The installer defaults to a dry run and never overwrites an existing destination.

Preview:

```bash
python tools/install.py --agent codex --scope user
```

Apply after reviewing the destination:

```bash
python tools/install.py --agent codex --scope user --apply
```

Supported targets:

| Agent | User scope | Project scope |
|---|---|---|
| Codex | `$CODEX_HOME/skills` when set; otherwise existing `~/.codex/skills`, then `~/.agents/skills` | `<project>/.agents/skills` |
| Claude Code | `~/.claude/skills` | `<project>/.claude/skills` |
| GitHub Copilot | `~/.copilot/skills` | `<project>/.github/skills` |
| Generic Agent Skills | `~/.agents/skills` | `<project>/.agents/skills` |

Use `--dest /exact/skill/directory` to override the default. The destination is the final `project-handoff` directory, not its parent.

## Install in Codex

Ask Codex to install the published skill:

```text
Use $skill-installer to install:
https://github.com/svd748xyz/project-handoff-skill/tree/main/skills/project-handoff
```

Or copy `skills/project-handoff` into the user skill directory used by your Codex installation, such as `~/.agents/skills/project-handoff` or `$CODEX_HOME/skills/project-handoff`.

From a cloned repository:

```bash
python tools/install.py --agent codex --scope user --apply
```

Invoke it explicitly:

```text
$project-handoff
```

Preview without replacing an existing handoff:

```text
$project-handoff preview
```

`agents/openai.yaml` keeps implicit invocation disabled in Codex.

## Install in Claude Code

Copy the skill directory to:

```text
~/.claude/skills/project-handoff
```

Then invoke:

```text
/project-handoff
```

Claude Code ignores `agents/openai.yaml`. If you require platform-enforced user-only invocation, add `disable-model-invocation: true` to the frontmatter of the installed Claude-specific copy. The installer can do that without changing the shared source:

```bash
python tools/install.py --agent claude --scope user --explicit-only --apply
```

## Other agents

The core `SKILL.md`, scripts, and references are platform-neutral. Install the `skills/project-handoff` directory wherever the target agent loads skills (for example with `--dest` for Antigravity or custom skill directories), then verify its invocation syntax and script execution policy.

Project-scoped GitHub Copilot example:

```bash
python tools/install.py --agent copilot --scope project --project-root /path/to/project --apply
```

Platform references:

- [Codex Skills documentation](https://developers.openai.com/codex/skills)
- [Claude Code Skills documentation](https://code.claude.com/docs/en/skills)

## What the skill writes

One file in the project root:

```text
项目开发交接.md
```

It starts with a small metadata block:

```markdown
<!-- project-handoff-meta
format-version: 5
updated-at: 2026-11-27T21:20:00+08:00
session-scope: Tighten compaction handoff flow and anti-pollution checks.
source-revision: 3d70d58...
working-tree-state: dirty
branch: main
-->
```

`working-tree-state` ignores the handoff file and its candidate, and is scoped to `--root` inside monorepos (recording `scope-path` when `--root` is a subdirectory of a Git repository).

Then eight sections in a fixed order:

| Section | Content |
|---|---|
| 目标与进度 | The overall goal, where the work stands, and user corrections or scope changes. |
| 用户偏好与约束 | Standing instructions the next session must follow: always/never rules, language, approvals, areas not to touch. |
| 做了什么 | Files and areas changed, with results and status labels. |
| 关键决策与理由 | Decisions that constrain future work, each with its reason. |
| 验证情况 | What was run, the actual result, and what remains unchecked. |
| 踩坑与失败路径 | Failures worth remembering: symptom, cause, avoidance, retry condition. |
| 未决问题 | Open `[待确认]` items and the smallest check or decision that resolves each. |
| 下一步 | `第一个动作` with its `验收` condition, then `先读` (<=5 minimal files to read first) and `后续步骤` (remaining steps). |

Items that are still in force (constraints, unreversed decisions, live pitfalls) or still open are carried into the next handoff and marked `（承接上次）`. Permanent project-wide rules that survive multiple handoffs should be promoted into `AGENTS.md`, `CLAUDE.md`, or `PITFALLS.md` rather than carried indefinitely. A section with nothing to say holds `- 无`.

Evidence labels:

- `[已验证]`: a command, test, build, inspection, or live check ran and the result is known.
- `[已实现][未验证]`: the change exists but its behavior has not been checked.
- `[待确认]`: unknown, inferred, stale, or waiting on a decision.

See [evidence patterns](skills/project-handoff/references/evidence-patterns.md) for examples and failure modes.

## Inspect, recall, validate, and save

Report the previous handoff, branch/scope drift, commits and tracked changes since `source-revision`, and uncommitted files scoped to `--root`. Writes nothing:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py inspect --root /path/to/project
```

Optional — when a heavily compacted session has a local JSONL transcript, extract only secret-redacted human user messages (no tool outputs) to recover early instructions:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py recall --transcript /path/to/transcript.jsonl
```

Write the 8-section body to `项目开发交接.md.candidate` (starting at `# 项目开发交接`), then inject fresh metadata, validate, and save atomically in one step:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py save --root /path/to/project --session-scope "one line describing this session"
```

(`prepare --root /path/to/project --session-scope "..."` remains available when generating metadata manually.)

Save validates, checks that neither the candidate nor the target changed during the save, replaces the target atomically, and reads the saved file back. On failure the target is left untouched and the candidate is kept for repair. Add `--preview` to validate without writing. Exit codes: `0` accepted, `1` invalid or warnings under `--strict`.

Validate an existing handoff directly:

```bash
python -B skills/project-handoff/scripts/validate_handoff.py 项目开发交接.md
```

The validator checks the metadata block (including optional `branch` and `scope-path`), section order and headings, the first action and acceptance condition in `下一步`, `先读` file count (warns above 5), prose status labels (ignoring code spans and fenced code blocks), cross-section `[已验证]` consistency, ephemeral session-bound process phrasing, carry-over bloat, obvious secrets, placeholders, and size (target 2,000–4,500 chars; warns above 6,000; rejects above 12,000). Its evidence check only rejects `[已验证]` items that name no command, file, result, or date; it cannot tell whether the evidence is real.

## Verification boundary

Static validation proves structure, labels, and that no obvious secret or placeholder remains. It does not prove that the claims are true, nor that a fresh session can continue from the handoff. For behavioral acceptance, run the [consumer contract](skills/project-handoff/references/consumer-contract.md) in an isolated fresh session and report that result separately.

## Security and privacy

- The scripts are local and make no network requests. `prepare` and `inspect` read Git state (revision, branch, scope-path, status, commit subjects, and diff statistics), not file contents.
- `recall` is strictly opt-in (only reads an explicitly passed `--transcript` file), extracts only human user turns, skips system/tool blocks, and runs secret redaction before printing.
- The validator rejects common credential patterns, including prefixed environment variables such as `OPENAI_API_KEY=...` and well-known token formats (`sk-`, `ghp_`, `github_pat_`, `xox?-`, `AIza`), and warns about likely email addresses and Chinese mobile numbers.
- The handoff is written to the project directory; review it before committing or sharing.

## 中文说明

这个 Skill 面向的场景是：同一个工作区里，一个会话经历过几次上下文压缩后，模型注意力被稀释、早期细节在压缩中丢失，需要快速开新会话继续，同时尽量不丢进展、也不污染新会话上下文。它不复制旧会话，也不维护长期项目档案，而是把当前会话提炼成一个“新会话够用的短交接”：目标与进度、用户偏好与约束、改动内容、关键决策、验证结果、踩坑、未决问题和下一步，同时过滤原始聊天、重复日志、已被推翻的假设、未落盘的瞬时进程态和用户没有确认的方案。

在 3.2.0 中，交接链路进一步围绕“快、准、轻”做了优化：
- **两步快同步**：写完八节正文到 `.candidate` 后，直接用 `save --session-scope "..."` 一次完成最新元数据注入、校验和原子保存，省掉单独的 `prepare` 往返；支持说“同步”直接原地重写。
- **压缩后用户原话回溯（可选）**：多轮压缩后如果本地有对话 JSONL transcript，可用 `recall --transcript <path>` 只提取脱敏后的用户原话（不含工具日志），找回最早期的约束与纠偏。
- **分支追踪与 Monorepo 子目录隔离**：自动记录 `branch` 和子目录 `scope-path`，`inspect` 只统计 `--root` 范围内的变更并在切分支时告警，避免大仓里其他子项目干扰。
- **更严的新会话防污染护栏**：中文友好体积控制（建议 2,000–4,500 字，>6,000 警告，>12,000 拒绝）、限制 `先读` 不超过 5 个最小必要文件、忽略代码块里的中文方括号避免误杀、检测 `（承接上次）` 过度堆积并提醒晋升至 `AGENTS.md`/`PITFALLS.md`，以及拦截把“后台运行中 / PID”当进展的瞬时状态写法。

调用方式：执行 `$project-handoff`（Claude Code 为 `/project-handoff`，或直接说“同步”/“写交接”）；只想看结果不覆盖旧文件时加 `preview`；会话中途到达里程碑或压缩一两次后可以先做一次 checkpoint，越早写丢的越少。写完后把技能给出的提示词交给新会话即可。

## License

MIT
