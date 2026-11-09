# Project Handoff Skill 3.1.1

`project-handoff` distills the session that just happened into a short `项目开发交接.md`, so a fresh coding-agent session can continue without reading the previous conversation.

The handoff carries the goal and progress, the user's standing instructions, what changed, decisions that constrain future work, what was actually verified, failed paths worth remembering, open questions, and where to start. It deliberately leaves out transcripts, repeated tool output, superseded hypotheses, and unapproved proposals.

## Why this exists

A long session that has been compacted several times dilutes the model's attention and silently loses early details. Starting a fresh session fixes the dilution, but the new session starts with nothing. This skill produces a small, portable session record that the next session can read in one pass, and tells that session how to check it against the workspace before acting.

It is not a project wiki, a long-term architecture register, or a replacement for Git, tests, issues, or source documents. It records the working state and the next action.

## What changed in 3.1.1

- The validator now rejects every unsupported bracketed label (`[已提交]`, `[已决定]`, `[注意]`, …), not just a fixed list of old ones; Markdown links like `[文档](x.md)`, checkboxes, and ASCII brackets are unaffected.
- `SKILL.md` writing rules tightened: each fact is written once in the section that owns it; `未决问题` holds only unresolved items; stale carry-over is dropped silently; inherited items must carry `（承接上次）`; `session-scope` describes the work, not the handoff; and `第一个动作` names the user-decision question when progress is blocked instead of re-checking the repo.

## What changed in 3.1

- Built around the compaction case: compaction summaries are treated as a source for early decisions and user corrections, and facts that only exist there are marked.
- Decisions, constraints, and pitfalls that are still in force are carried over between handoffs, not only open items, so they no longer disappear after a few sessions.
- New `用户偏好与约束` section; `下一步` now holds the first action plus files to read first and the remaining steps.
- New `inspect` command: commits and changes since the previous handoff, plus drift detection when resuming.
- New Checkpoint and Resume modes in `SKILL.md`.
- Fixes: the handoff file no longer keeps the tree permanently `dirty`; `OPENAI_API_KEY=...`-style and common token formats are detected; template placeholders are reliably caught; saving works on file systems without hard links; scripts print UTF-8 without `-X utf8`.
- Handoff document format is now **5**.

## Download and install

The repository is public and can be installed independently on any device. It needs Python 3.10+; the scripts use only the standard library. Licensed under [MIT](LICENSE).

- [Latest source](https://github.com/svd748xyz/project-handoff-skill): follows `main`.
- [Releases](https://github.com/svd748xyz/project-handoff-skill/releases): pick a fixed version.
- [3.1.1 notes](CHANGELOG.md): what changed in this release.

Download and extract the release, then from the directory containing `tools/` and `skills/`:

```text
python -B tools/install.py --agent codex --scope user
python -B tools/install.py --agent codex --scope user --apply
```

The first command prints the destination; the second installs. On macOS/Linux use `python3` if `python` is unavailable; on Windows `py -3` also works. For Claude Code, use `--agent claude --explicit-only`.

After installing, invoke `$project-handoff` in a new task, or `/project-handoff` in Claude Code.

**Upgrading:** run the first command to confirm the target path, move the existing `project-handoff` folder to a backup outside the skill discovery directory, then install. The installer never overwrites an existing directory. A format-4 handoff from 3.0 is still read by `inspect` and carried over by the next write, which produces format 5. Format-3 documents from 2.x are not migrated.

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
- Git is optional; when present, the metadata records `HEAD` and whether the working tree is clean
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

The core `SKILL.md`, scripts, and references are platform-neutral. Install the `skills/project-handoff` directory wherever the target agent loads skills, then verify its invocation syntax and script execution policy.

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
updated-at: 2026-11-09T18:40:00+08:00
session-scope: Rework the handoff skill around compacted sessions.
source-revision: 3d70d58...
working-tree-state: dirty
-->
```

`working-tree-state` ignores the handoff file and its candidate, so it reflects the project, not the handoff itself.

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
| 下一步 | `第一个动作` with its `验收` condition, then `先读` (files to read first) and `后续步骤` (remaining steps). |

Items that are still in force (constraints, unreversed decisions, live pitfalls) or still open are carried into the next handoff and marked `（承接上次）`. A section with nothing to say holds `- 无`.

Evidence labels:

- `[已验证]`: a command, test, build, inspection, or live check ran and the result is known.
- `[已实现][未验证]`: the change exists but its behavior has not been checked.
- `[待确认]`: unknown, inferred, stale, or waiting on a decision.

See [evidence patterns](skills/project-handoff/references/evidence-patterns.md) for examples and failure modes.

## Inspect, validate, and save

Report the previous handoff, the commits and tracked changes since its `source-revision`, and uncommitted files. Used both when writing (to ground "what changed", including work committed during the session) and when resuming (to detect drift). It writes nothing:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py inspect --root /path/to/project
```

Print the metadata block for the current project:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py prepare --root /path/to/project --session-scope "one line describing this session"
```

Write the rest of the document to `项目开发交接.md.candidate`, then save:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py save --root /path/to/project
```

Save validates, checks that neither the candidate nor the target changed during the save, replaces the target atomically, and reads the saved file back. On failure the target is left untouched and the candidate is kept for repair. Add `--preview` to validate without writing. Exit codes: `0` accepted, `1` invalid or warnings under `--strict`.

Validate an existing handoff directly:

```bash
python -B skills/project-handoff/scripts/validate_handoff.py 项目开发交接.md
```

The validator checks the metadata block, section order and headings, the first action and acceptance condition in `下一步`, status labels (any other bracketed label such as `[已决定]` is rejected), obvious secrets, placeholders, and size. It warns above 8,000 characters and rejects above 16,000; the target is 3,000–6,000. Its evidence check only rejects `[已验证]` items that name no command, file, result, or date; it cannot tell whether the evidence is real.

## Verification boundary

Static validation proves structure, labels, and that no obvious secret or placeholder remains. It does not prove that the claims are true, nor that a fresh session can continue from the handoff. For behavioral acceptance, run the [consumer contract](skills/project-handoff/references/consumer-contract.md) in an isolated fresh session and report that result separately.

## Security and privacy

- The scripts are local and read only the handoff candidate and the target; `prepare` and `inspect` read Git state (revision, status, commit subjects, and diff statistics), not file contents.
- The validator rejects common credential patterns, including prefixed environment variables such as `OPENAI_API_KEY=...` and well-known token formats (`sk-`, `ghp_`, `github_pat_`, `xox?-`, `AIza`), and warns about likely email addresses and Chinese mobile numbers.
- The handoff is written to the project directory; review it before committing or sharing.

## 中文说明

这个 Skill 面向的场景是：同一个工作区里，一个会话经历过几次上下文压缩后，模型注意力被稀释、早期细节在压缩中丢失，需要开新会话继续。它不复制旧会话，也不维护长期项目档案，而是把当前会话提炼成一个“新会话够用的短交接”：目标与进度、用户偏好与约束、改动内容、关键决策、验证结果、踩坑、未决问题和下一步，同时过滤原始聊天、重复日志、已被推翻的假设和用户没有确认的方案。

写交接时，压缩摘要被当作早期决策和用户纠正的来源，仅存在于摘要中的事实会标注 `（据压缩摘要）`；上一份交接中仍然生效的约束、决策和坑会被承接（标 `（承接上次）`），而不只是未完成项，避免多轮交接后关键决策丢失。`inspect` 命令会列出上次交接以来的提交和改动，作为“做了什么”的依据；新会话接手时也先运行它，核对仓库是否在交接后发生过变化。

交接文件固定八节，顺序不变；每条结论用三种标签之一标注：`[已验证]` 表示真的运行或检查过并知道结果，`[已实现][未验证]` 表示代码写了但行为还没验证，`[待确认]` 表示未知、推断中或等待决定。写代码本身不会把条目升级为已验证。文档格式为 **5**。

调用方式：执行 `$project-handoff`（Claude Code 为 `/project-handoff`）；只想看结果不覆盖旧文件时加 `preview`；会话中途到达里程碑或压缩一两次后可以先做一次 checkpoint，越早写丢的越少。写完后把技能给出的提示词交给新会话即可。

## License

MIT
