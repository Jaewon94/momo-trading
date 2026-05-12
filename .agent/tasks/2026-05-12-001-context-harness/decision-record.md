# Decision Record

## Decision

Adopt a lightweight file-based self-harness for momo-trading.

## Options Considered

1. Copy hellforge harness wholesale.
2. Add only documentation.
3. Add project/task artifacts plus a small validator and CLI.

## Chosen Option

Option 3.

## Rationale

- momo-trading needs stable operating context because trading, broker state, LLM providers, and admin UI changes interact.
- A full external runtime harness is premature.
- Documentation alone would drift; a validator makes missing task context visible.
- Python stdlib scripts fit the existing repo and avoid new dependencies.

## Deferred

- GitHub Actions wiring.
- Discord/OpenACP integration.
- Agent Council automation.
- SQLite/Postgres task store.

## Risks

- Artifact maintenance can become busywork if every tiny task is forced through it.
- The validator checks structure, not whether the trading decision itself is correct.

## Mitigations

- Use the harness for substantial or risky work.
- Keep strict mode focused on the current task.
- Continue using focused domain tests for trading behavior.
