# Project Handoff Skill 3.0.0

`project-handoff` distills the session that just happened into a short `项目开发交接.md`, so a fresh coding-agent session can continue without reading the previous conversation.

The handoff carries the session goal, what changed, decisions that constrain the next session, what was actually verified, failed paths worth remembering, open questions, and the first next action. It deliberately leaves out transcripts, repeated tool output, superseded hypotheses, and unapproved proposals.

## Why this exists

Built-in session history and memory help an agent retrieve context, but a new conversation often starts without it. This skill produces a small, portable session record that the next session can read in one pass.

It is not a project wiki, a long-term architecture register, or a replacement for Git, tests, issues, or source documents. It records one session's working state and the next action.

## What changed in 3.0

- Recentered on single-session distillation instead of maintaining a project-state contract.
- Replaced the eight-section project template with seven session sections: goal, work, decisions, verification, pitfalls, open questions, next action.
- Removed project identity, workspace IDs, critical-file fingerprints, freshness snapshots, and the Jev/process pipeline.
- Reduced the scripts to two: `validate_handoff.py` and `manage_handoff.py`.
- Kept three evidence labels: `[已验证]`, `[已实现][未验证]`, `[待确认]`.
- Handoff document format is now **4**.

## Download and install

The repository is public and can be installed independently on any device. It needs Python 3.10+; the scripts use only the standard library. Licensed under [MIT](LICENSE).

- [Latest source](https://github.com/svd748xyz/project-handoff-skill): follows `main`.
- [Releases](https://github.com/svd748xyz/project-handoff-skill/releases): pick a fixed version.
- [3.0.0 notes](CHANGELOG.md): what changed in this rewrite.

Download and extract the release, then from the directory containing `tools/` and `skills/`:

```text
python -B tools/install.py --agent codex --scope user
python -B tools/install.py --agent codex --scope user --apply
```

The first command prints the destination; the second installs. On macOS/Linux use `python3` if `python` is unavailable; on Windows `py -3` also works. For Claude Code, use `--agent claude --explicit-only`.

After installing, invoke `$project-handoff` in a new task, or `/project-handoff` in Claude Code.

**Upgrading from 2.x:** run the first command to confirm the target path, move the existing `project-handoff` folder to a backup outside the skill discovery directory, then install. The installer never overwrites an existing directory. Old handoff documents are not read by 3.0; keep them only if you need their history.

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

The scripts use only the Python standard library and make no network requests. On Windows, run Python with `-X utf8` so Chinese paths and content are encoded correctly.

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
format-version: 4
updated-at: 2026-10-27T18:40:00+08:00
session-scope: Recenter the handoff skill on single-session distillation.
source-revision: 3d70d58...
working-tree-state: dirty
-->
```

Then seven sections in a fixed order:

| Section | Content |
|---|---|
| 本次会话目标 | The goal this session pursued, including scope changes and corrections. |
| 做了什么 | Files and areas changed, with results and status labels. |
| 关键决策与理由 | Decisions that constrain the next session, each with its reason. |
| 验证情况 | What was run, the actual result, and what remains unchecked. |
| 踩坑与失败路径 | Failures worth remembering: symptom, cause, avoidance, retry condition. |
| 未决问题 | Open `[待确认]` items and the smallest check or decision that resolves each. |
| 下一步第一个动作 | One first action plus the observable result that shows it worked. |

Evidence labels:

- `[已验证]`: a command, test, build, inspection, or live check ran and the result is known.
- `[已实现][未验证]`: the change exists but its behavior has not been checked.
- `[待确认]`: unknown, inferred, stale, or waiting on a decision.

See [evidence patterns](skills/project-handoff/references/evidence-patterns.md) for examples and failure modes.

## Validate and save

Print the metadata block for the current project:

```bash
python -X utf8 -B skills/project-handoff/scripts/manage_handoff.py prepare --root /path/to/project --session-scope "one line describing this session"
```

Write the rest of the document to `项目开发交接.md.candidate`, then preview:

```bash
python -X utf8 -B skills/project-handoff/scripts/manage_handoff.py save --root /path/to/project --preview
```

Save for real:

```bash
python -X utf8 -B skills/project-handoff/scripts/manage_handoff.py save --root /path/to/project
```

Preview validates and writes nothing. Save validates again, checks that neither the candidate nor the target changed during the save, replaces the target atomically, and reads the saved file back. On failure the target is left untouched and the candidate is kept for repair. Exit codes: `0` accepted, `1` invalid or warnings under `--strict`.

Validate an existing handoff directly:

```bash
python -X utf8 -B skills/project-handoff/scripts/validate_handoff.py 项目开发交接.md
```

The validator checks the metadata block, section order and headings, label rules, obvious secrets, placeholders, and size. It warns above roughly 10,000 characters and rejects above 20,000.

## Verification boundary

Static validation proves structure, labels, and that no obvious secret or placeholder remains. It does not prove that the claims are true, nor that a fresh session can continue from the handoff. For behavioral acceptance, run the [consumer contract](skills/project-handoff/references/consumer-contract.md) in an isolated fresh session and report that result separately.

## Security and privacy

- The scripts are local and read only the handoff candidate and the target; `prepare` reads Git state, not file contents.
- The validator rejects common credential patterns and warns about likely email addresses and Chinese mobile numbers.
- The handoff is written to the project directory; review it before committing or sharing.

## 中文说明

这个 Skill 的目标不是复制旧会话，也不是维护一份长期项目档案，而是把刚刚结束的这个会话压缩成一个“新会话够用的短交接”。它保留本次目标、改动内容、关键决策、验证结果、踩坑、未决问题和下一步第一个动作，同时过滤原始聊天、重复日志、已被推翻的假设和用户没有确认的方案。

交接文件固定七节，顺序不变；每条结论用三种标签之一标注：`[已验证]` 表示真的运行或检查过并知道结果，`[已实现][未验证]` 表示代码写了但行为还没验证，`[待确认]` 表示未知、推断中或等待决定。写代码本身不会把条目升级为已验证。

3.0 去掉了项目 ID、工作区指纹、关键文件指纹、快照过期检查和 Jev 处理流程，只保留两个脚本：`validate_handoff.py` 负责结构、标签、敏感信息和长度校验；`manage_handoff.py` 负责生成元数据并在校验通过后原子保存。文档格式为 **4**。

调用方式：在新会话中执行 `$project-handoff`（Claude Code 为 `/project-handoff`）；只想看结果不覆盖旧文件时加 `preview`。写完后把 `项目开发交接.md` 交给下一个会话，并提醒它未验证项不要当作已完成。

## License

MIT
