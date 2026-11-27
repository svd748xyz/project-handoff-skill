# Consumer contract

Use this to test whether a generated handoff lets a fresh session continue without the previous conversation.

## Setup

1. Start a fresh session in the same project. Do not include the previous conversation.
2. Give it only: "Read 项目开发交接.md and continue from 下一步."
3. Do not explain the task or correct it during the first attempt.

For a realistic test, generate the handoff from a long session that went through at least one compaction, contained at least one user correction, and committed part of its work. Those are the conditions under which handoffs lose information.

## What the fresh session must be able to state

- the overall goal and how far along it is;
- the user's standing instructions it will follow;
- what changed and where, including committed work;
- which claims are verified and which are not;
- what is still open, and the smallest way to resolve it;
- the first action, how it will know the action worked, and what comes after.

## Pass criteria

- It checks the repository state (including branch and commit drift) against the handoff before acting, and reports drift if there is any.
- It reads only the handoff and the minimal `先读` files before taking the first action.
- It takes the first action without asking for context that the handoff should contain.
- It follows the recorded user constraints without being reminded.
- It does not treat `[已实现][未验证]` or `[待确认]` items as done, and does not assume background jobs from the previous session are still alive.
- It flags inherited items rather than presenting them as this session's work.
- It does not invent a result that the handoff does not contain.

## Counterexamples

- The handoff lists files but no command or result: the fresh session cannot tell what was verified.
- Every claim is `[已验证]` but no evidence is named: the fresh session should challenge the labels.
- `第一个动作` is a multi-step plan: the fresh session cannot tell where to start. Remaining steps belong in `后续步骤`.
- `先读` lists a dozen large files: the fresh session fills its fresh context before taking the first action.
- There is no `后续步骤` for an unfinished multi-step task: the fresh session finishes one step and believes the work is done.
- A user instruction from early in the session ("don't commit without asking") is missing because it only lived in a compaction summary.
- A decision from two sessions ago was dropped because it was no longer "open", and the fresh session reverses it.
- The handoff carries ten stale `（承接上次）` items that belong in `AGENTS.md` or belong to completed tasks, crowding out current progress.
- The handoff repeats the chat transcript: the fresh session spends context on material that does not change the next action.

## Reporting

Report the forward test separately from static validation. A passing validator only proves structure and labels; it does not prove that a fresh session can continue.
