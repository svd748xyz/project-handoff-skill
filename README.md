# Project Handoff Skill 2.1.1

`project-handoff` creates or refreshes a concise, evidence-backed `项目开发交接.md` so a fresh coding-agent session can continue a project without inheriting the full previous conversation.

It preserves current goals, verified progress, costly failure lessons, blockers, next actions, acceptance conditions, and freshness evidence. It filters raw chat, repeated tool output, superseded hypotheses, and unconfirmed assistant proposals.

## Why this exists

Built-in session history and memory help an agent retrieve context. This skill serves a different purpose: it produces a portable, reviewable project-state contract whose claims have evidence levels and invalidation conditions.

It does not replace Git, tests, issues, ADRs, source documents, or an agent platform's own memory system.

Version **2.1.1** assigns determined operations to rules, local semantic decisions to Jev, and overall understanding and handoff writing to the main model. Capture raw output, run triage, then follow the packet's next step. Routing uncertainty or unavailable inference preserves text directly; only claims, conflicts and ambiguous comparisons produce evidence tasks. Original records and 2.1.0 recovery reports remain readable. The handoff document format remains **3**.

This is an explicit skill workflow. It acts on supplied output files and preserves their originals; it installs no host hook and does not replace native context management.

## 下载与跨设备安装 / Download and install

本仓库公开发布，可在不同设备或由其他使用者独立安装。只需要 Python 3.10+；核心脚本使用标准库，不依赖作者电脑、Codex 会话、业务文件或私有配置。授权采用 [MIT](LICENSE)。

- [最新源码](https://github.com/svd748xyz/project-handoff-skill)：跟随 `main`。
- [版本发布页](https://github.com/svd748xyz/project-handoff-skill/releases)：选择固定版本及下载包。
- [2.1.1 版本说明](CHANGELOG.md)：查看此次分工、流程和兼容性变化。

在目标设备下载并解压发行包，进入包含 `tools/` 和 `skills/` 的目录，然后执行：

```text
python -B tools/install.py --agent codex --scope user
python -B tools/install.py --agent codex --scope user --apply
```

第一条显示安装位置，第二条执行安装。macOS/Linux 若只有 `python3` 命令，将 `python` 换成 `python3`；Windows 也可使用 `py -3`。Claude Code 将 `--agent codex` 换为 `--agent claude --explicit-only`。其他目标及项目级安装见下表。

安装完成后，在新任务中调用 `$project-handoff`；Claude Code 使用 `/project-handoff`。需要 Jev 过程模式时，明确要求“开启过程模式，让 Jev 参与局部评定”。普通交接可直接离线使用。

**已有旧版时：**先运行第一条命令确认实际目标目录；把旧 `project-handoff` 文件夹移动到技能扫描目录之外的备份位置，再执行安装。安装器不会覆盖现有目录。升级不需要删除项目中的交接文档或过程记录，2.1.0 的恢复报告仍可读取。

**各设备独立配置 Jev：**安装包不携带密钥、账户或本机配置。需要联网评定的使用者，在自己的运行环境中配置 `TYPESAFE_API_KEY`，使启动编码代理的进程能读取它；请使用自己的凭据管理方式，不把密钥写进仓库或交接文档。没有 Jev 配置时，离线记录和交接仍可用。分发 skill 不会同时分发个人的项目记录、缓存或原始工具输出。

The package is portable and self-contained: install it on each device with Python 3.10+, choose the agent or an explicit `--dest`, and invoke the skill in a new task. Live Jev routing uses each user's own environment credential; the release contains no account or project data. Back up an existing installation before upgrading because the installer deliberately refuses to overwrite it.

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
    │   ├── manage_handoff.py
    │   ├── capture_handoff.py
    │   ├── triage_handoff.py
    │   ├── process_handoff.py
    │   └── jev_client.py
    └── references/
        ├── consumer-contract.md
        ├── evidence-patterns.md
        ├── jev-review.md
        └── process-workflow.md
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

Claude Code ignores `agents/openai.yaml`. If you require platform-enforced user-only invocation, add Claude Code's `disable-model-invocation: true` field to the frontmatter of the installed Claude-specific copy. Do not add that vendor extension to the shared package if you also want it to pass Codex's standard validator.

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

## Capture-first process mode and optional Jev

The ordinary handoff works offline. Process mode adds this path:

```text
tool output file → mechanical capture → rules / Jev routing → reading packet
                                                        → specific evidence tasks, when needed
                                                        → evidence-backed handoff
```

Use it explicitly:

```text
Use $project-handoff in process mode: capture raw tool outputs, let Jev route the reading packet, and review uncertain evidence before handoff.
Use $project-handoff without Jev.
```

An existing explicit preference continues to apply; disabling Jev takes precedence. The direct client uses `TYPESAFE_API_KEY`, the official System One endpoint and pinned `jev-1.13.0`; no SDK or MCP is needed. Installation alone does not authorize external review. Live mode sends necessary, non-sensitive context and evidence from the authorized task and may consume account usage.

The helpers have separate responsibilities:

| Helper | Responsibility |
|---|---|
| `capture_handoff.py` | Read a UTF-8 output file locally, preserve its full bytes and a range/hash manifest, and generate immutable records in mechanical slices. No generated claim or API call. |
| `triage_handoff.py` | Apply protected/recent/exact-duplicate rules, then optionally batch semantic relevance and duplicate/conflict questions. Produce a packet, audit report and measured reading sizes. Defaults offline. |
| `process_handoff.py` | Retain structured-event compatibility and optional claim-support review. Protected records without claims send no questions; claim-bearing records send only the support question. |
| `manage_handoff.py` | Preserve the existing identity, freshness, candidate validation, atomic replacement and read-back workflow. |

Rules keep user constraints/corrections, decisions, blockers, acceptance boundaries, failures, unknown outcomes and claims. Record authorization/stop conditions and external-action receipts in protected categories. Exact duplicates keep a visible representative. None of these routing decisions needs a Jev request.

For remaining records, Jev receives actual local excerpts and, where retrieved, a visible representative. Strong `noise` or `equivalent` choices can replace this record's display with a recovery reference. Claims, conflicts and uncertain comparisons create specific evidence tasks. Uncertain relevance, weak proposed omission, service failure and exceeded budgets preserve the full text directly, without a separate LLM relevance task. The main model follows the packet's next step, integrates the observations and checks important claim sources/currentness.

Live triage uses at most eight batches, each at most four candidate records, eight questions and 24,000 encoded request bytes. Its probability/confidence/margin gates are starting settings, not accuracy guarantees. Successes are cached against exact context/evidence/questions and the pinned model; failures do not retry automatically. Source archives remain available in all cases.

See [capture and triage commands](skills/project-handoff/references/process-workflow.md) and [decision contract, bounds and primary sources](skills/project-handoff/references/jev-review.md). Preserve historical test dates, skipped cases and untested paths; distinguish implemented source, uncommitted changes, installed copies, releases and deployments in the final handoff.

Audit reports retain rule/model decisions, evidence tasks and execution details. Evaluate the workflow by reliable records, correct decision ownership, evidence-backed handoffs and successful continuation. Successful routing alone does not establish business acceptance.

The existing `python -B tools/demo_process_handoff.py --out <new-directory>` demonstration is offline by default. Its explicit `--live` mode sends fictional claim-review fixtures through the existing account; it does not read real project data or establish capture-first routing accuracy.

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

2.1.1 的过程模式是“工具原始输出落盘 → 机械留档 → 规则和 Jev 前置分流 → 主模型整体理解与交接”。规则负责保护、精确去重和保守保留；Jev 的局部判断直接驱动分支；主模型处理待核实主张、冲突和比较歧义，并形成项目状态和下一步。相关性不明确或接口不可用时直接保留原文，不再制造逐条复核任务。原记录始终可恢复。

可这样调用：`使用 $project-handoff 开启过程模式，规则负责确定事项，Jev 负责局部评定并直接驱动流程，LLM 负责整体理解与交接。` 普通调用仍可离线工作。历史未覆盖项、未提交状态、安装状态和业务验收分别保留。

## License

MIT
