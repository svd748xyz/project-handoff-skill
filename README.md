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
        ├── evidence-patterns.md
        └── jev-review.md
```

## Requirements

- Python 3.10 or newer
- Git is optional
- A coding agent that supports Agent Skills-style `SKILL.md` packages, or can follow the instructions manually

The validator uses only the Python standard library and performs no network requests.

If Git is not installed, selected critical-file fingerprints remain available. Git repository access failures are reported instead of being mistaken for non-Git projects.

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

Decision-changing claims are reviewed separately as supported, contradicted, or insufficiently evidenced. Critical unknowns identify the missing evidence, a concrete verification path, and how the result changes the next action. See [evidence patterns](skills/project-handoff/references/evidence-patterns.md).

## Optional Jev evidence review

The complete base workflow works without Jev. Optional review is disabled by default and uses a compatible Jev tool already configured in the user's agent environment. This skill supplies review instructions; the host manages the connection and model settings. Access and credentials belong to that user; this repository supplies no account, hosted service, credentials, network client, model configuration, or mandatory MCP dependency. Installing the skill does not set up a Jev connection.

Example requests (natural-language skill instructions, not Python command-line flags):

```text
Use $project-handoff with Jev evidence review.
Use $project-handoff without Jev review.
```

An established user preference for this skill can also enable review; explicitly disabling it overrides that preference. Tool availability alone does not opt a project in. When enabled, the agent submits only selected non-sensitive claims and necessary source context within the user's authorized scope. The configured service may send those snippets to TypeSafe and incur usage on the user's account.

Jev supplies advisory `supported`, `contradicted`, or `insufficient` judgments. The agent retains responsibility for the evidence and final result. Missing or incompatible tools, errors, timeouts, and invalid responses fall back to the base workflow; unresolved facts remain unresolved. Disagreement prompts a source recheck, not a confidence threshold or vote.

See the [tool contract and synthetic example](skills/project-handoff/references/jev-review.md). The tool's exposed schema determines compatibility; a particular tool name or model version is not required. The two existing Python scripts remain local and unchanged, and the v3 handoff format is shared by both modes.

Discovery and diagnosis run only when review is enabled or a connection check is requested. The agent distinguishes review being off, tools not discovered in the current task, saved configuration/local readiness, and a validated live result. Missing tools or an absent project configuration entry do not establish that the machine has no Jev setup; relevant user settings or an active host profile may differ. A local `ready` result does not verify provider access. A diagnosis request alone does not enable review or send a test inference. See [discovery and status](skills/project-handoff/references/jev-review.md#discovery-and-status).

## Validate

Run the built-in test suite:

```bash
python skills/project-handoff/scripts/validate_handoff.py --self-test
```

Run the snapshot and safe-save regression suite:

```bash
python -B tools/test_regressions.py
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

Result codes: `0` accepted, `1` invalid/check failed, `2` stale snapshot, `3` limited coverage. `--strict` additionally rejects review warnings. For an understood empty non-Git baseline, `--allow-limited` returns success with `VALID-LIMITED`; it never suppresses errors or stale state.

Dirty Git fingerprints now include staged object IDs and changed/untracked file contents, so repeated edits to the same dirty file are detected. Existing handoffs with the earlier status-only dirty fingerprint need evidence review and regeneration. Ignored deliverables still require explicit `--critical-file` selection.

## Generate metadata and save safely

After inspecting project identity and evidence, print the candidate metadata without writing project files:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py prepare --root /path/to/project --workspace /path/to/project --project-key my-project --evidence-scope "requirements and targeted test results" --critical-file requirements.md
```

Use the entire returned metadata block when composing the adjacent `项目开发交接.md.candidate`. The helper preserves an existing project ID and records the previous handoff's hash. It defaults history coverage to `visible-only`; higher coverage must be supported by the actual session evidence. It does not refresh the dates of old verification claims.

Preview or save the reviewed candidate:

```bash
python -B skills/project-handoff/scripts/manage_handoff.py save --root /path/to/project --workspace /path/to/project --preview
python -B skills/project-handoff/scripts/manage_handoff.py save --root /path/to/project --workspace /path/to/project
```

Preview writes nothing. Saving validates the candidate, checks current source state and previous target hash, acquires an exclusive cooperative lock, replaces the target atomically, then reads back and revalidates it. It consumes the candidate on success and retains it on pre-save failure. Inspect an existing candidate or lock before starting; do not overwrite another writer's work. The checks are optimistic: unrelated editors can still race, and a post-save revalidation failure must be inspected rather than reported as completed.

Evidence statements in every section require an explicit verification date, a concrete evidence reference (code span or link), and scope. Mechanically checked sections use flat lists with indented continuation lines; unsupported prose, tables, and nested lists fail explicitly.

## Verification boundary

Static validation checks structure, evidence formatting, identity consistency, and the selected snapshot coverage. It does not prove the truth of cited evidence or successful continuation by a new agent. For behavioral acceptance, follow `references/consumer-contract.md` in an isolated fresh session.

The [consumer contract](skills/project-handoff/references/consumer-contract.md) includes focused evidence counterexamples and optional-Jev scenarios. Use simulated tool responses to check enablement, fallback, and disagreement without credentials or network calls. These simulations do not establish live Jev connectivity, model accuracy, or an improvement over the base workflow; evaluate those separately on the user's authorized inputs.

## Security and privacy

- The validator is local and read-only except for its isolated temporary self-test workspace.
- Critical-file hashing reads only explicitly selected files and stores an aggregate fingerprint, not their content.
- The skill rejects common credential patterns and warns about likely email addresses and Chinese mobile numbers.
- Review the generated handoff before committing or sharing it.

## 中文说明

这个 Skill 的目标不是复制旧会话，而是把旧会话中仍然影响项目推进的内容压缩成一个“最小充分状态包”。它保留目标、证据、进展、卡点、踩坑结论、下一步和验收条件，同时过滤原始聊天、重复日志、已推翻假设和未经确认的模型建议。

非 Git 项目可以选择少量关键文件生成内容指纹。文件发生变化后，严格校验会将交接标记为过期，避免新会话继续使用旧结论。

基础功能无需 Jev，默认不启用 Jev 复核。已经获得 Jev 访问资格并配置兼容工具的使用者，可以要求“使用 project-handoff，并启用 Jev 证据复核”；调用使用其自己的服务配置和账户。本仓库不包含作者密钥或本机配置。接口不可用时继续基础流程，存在证据缺口的结论仍保留为待确认；额外复核不等于用户验收或准确率保证。

本技能提供调用规则，连接与模型配置由宿主管理，安装技能不会自动接入 Jev。仅在启用复核或明确要求诊断时检查相关状态；“当前任务未发现工具”不等于“本机没有配置”，“本地配置就绪”也不等于“真实调用成功”。单纯诊断不会自动发送测试推理请求。

## License

MIT
