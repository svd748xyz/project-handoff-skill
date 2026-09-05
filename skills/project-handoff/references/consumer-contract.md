# Consumer contract

Use this only to forward-test a generated `项目开发交接.md`.

## Isolation

Start a genuinely fresh session without the producer conversation. Disable or exclude prior-chat memory when the test surface allows it. Give the consumer read-only access to the handoff and active project workspace; do not give it the expected answer.

## Prompt

```text
只根据当前项目目录中的《项目开发交接.md》和可只读核验的工作区证据，先运行交接当前性检查，然后输出：
1. project_id
2. 当前目标与边界
3. 已验证进展及证据
4. 当前卡点或待确认项
5. 第一项可执行下一步
6. 该下一步的验收条件
7. 交接是否仍然新鲜；如果已过期，说明发生了哪类差异
8. 哪些内容只是待确认推断，不能作为继续开发的事实
不要修改任何文件。
```

## Pass criteria

- The `project_id` matches the handoff.
- Goal and boundaries do not expand beyond user-confirmed scope.
- Verified progress is not upgraded beyond its evidence layer.
- The first next step is executable and includes its acceptance condition.
- Snapshot freshness matches the validator's `--check-current` result.
- Exit 2 means stale, exit 3 means limited coverage, and exit 1 means invalid or check failed. Do not treat successful structure validation as a current snapshot. `--allow-limited` never waives stale state.
- Inherited verification dates remain attached to their original evidence; the handoff update date does not imply those checks ran again.
- The answer does not depend on producer-chat facts absent from the handoff or workspace.
- Session inference and superseded ideas are not promoted to facts or silently converted into requirements.
- The handoff contains no raw chat transcript, chain-of-thought, or repeated tool output; retained failed paths are concise and action-relevant.
- For a non-Git project, a changed or missing critical file makes the handoff stale. An empty critical baseline is reported as limited freshness, not as a confirmed-current snapshot.
- For a Git project, editing an already-dirty file again, changing staged content, or changing an untracked file makes the old snapshot stale.

Record the blind test as passed only after reviewing the consumer output against these criteria. A structural self-test or a producer-session summary is not a substitute.
