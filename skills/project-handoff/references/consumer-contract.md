# Consumer contract

Use this to test whether a generated handoff lets a fresh session continue without the previous conversation.

## Setup

1. Start a fresh session in the same project. Do not include the previous conversation.
2. Give it only: "Read 项目开发交接.md and continue from 下一步第一个动作."
3. Do not explain the task or correct it during the first attempt.

## What the fresh session must be able to state

- the goal of the previous session;
- what changed and where;
- which claims are verified and which are not;
- what is still open, and the smallest way to resolve it;
- the first action, and how it will know the action worked.

## Pass criteria

- It takes the next action without asking for context that the handoff should contain.
- It does not treat `[已实现][未验证]` or `[待确认]` items as done.
- It flags inherited items rather than presenting them as this session's work.
- It does not invent a result that the handoff does not contain.

## Counterexamples

- The handoff lists files but no command or result: the fresh session cannot tell what was verified.
- Every claim is `[已验证]` but no evidence is named: the fresh session should challenge the labels.
- The next section is a multi-step plan: the fresh session cannot tell where to start.
- The handoff repeats the chat transcript: the fresh session spends context on material that does not change the next action.

## Reporting

Report the forward test separately from static validation. A passing validator only proves structure and labels; it does not prove that a fresh session can continue.
