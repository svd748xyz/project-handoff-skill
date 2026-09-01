# Project Handoff Skill

`project-handoff` creates or refreshes a concise, evidence-backed `项目开发交接.md` so a fresh coding-agent session can continue a project without inheriting the full previous conversation.

It preserves current goals, verified progress, costly failure lessons, blockers, next actions, acceptance conditions, and freshness evidence. It filters raw chat, repeated tool output, superseded hypotheses, and unconfirmed assistant proposals.

## Why this exists

Built-in session history and memory help an agent retrieve context. This skill serves a different purpose: it produces a portable, reviewable project-state contract whose claims have evidence levels and invalidation conditions.

It does not replace Git, tests, issues, ADRs, source documents, or an agent platform's own memory system.

## Repository layout

```text
project-handoff-skill/
├── .github/workflows/ci.yml
├── README.md
├── LICENSE
├── tools/
│   ├── install.py
│   ├── test_installer.py
│   ├── smoke_install.py
│   └── check_release.py
└── skills/project-handoff/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── scripts/validate_handoff.py
    └── references/
        ├── consumer-contract.md
        └── evidence-patterns.md
```

## Requirements

- Python 3.10 or newer
- Git is optional
- A coding agent that supports Agent Skills-style `SKILL.md` packages, or can follow the instructions manually

The validator uses only the Python standard library and performs no network requests.

## Safe multi-agent installer

The repository includes a dependency-free installer. It defaults to a dry run and never overwrites an existing destination.

Preview an installation:

```bash
python tools/install.py --agent codex --scope user
```

Apply it only after reviewing the destination:

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

For a manual installation, copy `skills/project-handoff` into the user skill directory used by your Codex installation, such as `~/.agents/skills/project-handoff` or `$CODEX_HOME/skills/project-handoff`.

From a cloned repository, the safe installer equivalent is:

```bash
python tools/install.py --agent codex --scope user --apply
```

Invoke it explicitly:

```text
$project-handoff
```

Preview without replacing the target:

```text
$project-handoff preview
```

The included `agents/openai.yaml` keeps implicit invocation disabled in Codex.

## Install in Claude Code

Copy the skill directory to:

```text
~/.claude/skills/project-handoff
```

Then invoke:

```text
/project-handoff
```

Claude Code ignores `agents/openai.yaml`. The shared skill description asks for explicit invocation, but if you require platform-enforced user-only invocation, add Claude Code's `disable-model-invocation: true` field to the frontmatter of the installed Claude-specific copy. Do not add that vendor extension to the shared package if you also want it to pass Codex's standard validator.

The installer can perform that adaptation without modifying the shared source:

```bash
python tools/install.py --agent claude --scope user --explicit-only --apply
```

## Other agents

The core `SKILL.md`, Python validator, and references are platform-neutral. Install the `skills/project-handoff` directory in the location supported by the target agent. Invocation syntax, implicit-selection controls, filesystem permissions, and script execution policies remain platform-specific and should be verified on that agent.

Project-scoped GitHub Copilot example:

```bash
python tools/install.py --agent copilot --scope project --project-root /path/to/project --apply
```

Current platform references:

- [Codex Skills documentation](https://developers.openai.com/codex/skills)
- [Claude Code Skills documentation](https://code.claude.com/docs/en/skills)

## What the skill writes

The skill maintains one file in the active project root:

```text
项目开发交接.md
```

It includes:

- stable project identity independent of absolute location;
- goal, boundaries, and source precedence;
- precisely labelled implementation and verification states;
- blockers and clearing conditions;
- ordered next steps with observable acceptance conditions;
- Git snapshot metadata when available;
- selected critical-file fingerprints for non-Git and binary-heavy projects;
- concise failed-path records using symptom, evidence, cause, avoidance, and retry conditions.

## Context hygiene

Each candidate statement is classified as user-confirmed, workspace-observed, or session inference. Session inference remains `[待确认]`. Content is omitted when removing it would not change the goal, next action, acceptance, material risk, or likelihood of repeating a costly failure.

The handoff must not contain raw transcripts, chain-of-thought, secrets, repeated tool output, or superseded assistant proposals.

## Validate

Run the built-in test suite:

```bash
python skills/project-handoff/scripts/validate_handoff.py --self-test
```

Capture a read-only project snapshot:

```bash
python skills/project-handoff/scripts/validate_handoff.py \
  --snapshot-root /path/to/project \
  --critical-file requirements.md
```

Check whether an existing handoff is still current:

```bash
python skills/project-handoff/scripts/validate_handoff.py \
  /path/to/project/项目开发交接.md \
  --check-current \
  --current-root /path/to/project \
  --strict
```

Windows PowerShell users can place the same arguments on one line.

## Verification boundary

Static validation proves structure, evidence labels, identity consistency, and snapshot freshness. It does not prove business truth or successful continuation by a new agent. For behavioral acceptance, follow `references/consumer-contract.md` in an isolated fresh session.

## Security and privacy

- The validator is local and read-only except for its isolated temporary self-test workspace.
- Critical-file hashing reads only explicitly selected files and stores an aggregate fingerprint, not their content.
- The skill rejects common credential patterns and warns about likely email addresses and Chinese mobile numbers.
- Review the generated handoff before committing or sharing it.

## 中文说明

这个 Skill 的目标不是复制旧会话，而是把旧会话中仍然影响项目推进的内容压缩成一个“最小充分状态包”。它保留目标、证据、进展、卡点、踩坑结论、下一步和验收条件，同时过滤原始聊天、重复日志、已推翻假设和未经确认的模型建议。

非 Git 项目可以选择少量关键文件生成内容指纹。文件发生变化后，严格校验会将交接标记为过期，避免新会话继续使用旧结论。

## License

MIT
