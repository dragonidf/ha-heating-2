# Heating AI 2.0

Replacement heating controller for Home Assistant.

## Project status (2026-11-03)
- **G0**: Architecture ADR01–07 and four owner clarifications approved.
- **WP0**: Review completed and merged as [PR #2](https://github.com/dragonidf/ha-heating-2/pull/2). **G1 remains BLOCKED** — [eight evidence issues](https://github.com/dragonidf/ha-heating-2/issues/3).
- **WP1A only**: Pure typed contracts and safety reducer, synthetic/offline tests, with **no control authority**. Work is scoped by [WP1A task](docs/wp1a/WP1A-TASK.md) and root [AGENTS.md](AGENTS.md).
- WP1B, HA integration, command gateway, compute runtime, deployment, physical tests and migration: **NOT AUTHORIZED**.

## Documentation
- [Project handoff](docs/spec/heating-ai-2.0/HANDOFF.md)
- [Owner approval](docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md)
- [Full architecture](docs/spec/heating-ai-2.0/02-Architecture.md)
- [Full engineering specification](docs/spec/heating-ai-2.0/03-Codex-specification.md)
- [Tests](docs/spec/heating-ai-2.0/04-Test-strategy.md)
- [Requirements](docs/spec/heating-ai-2.0/requirements.csv)
- [Scenarios](docs/spec/heating-ai-2.0/test-scenarios.csv)
- [Migration gates](docs/spec/heating-ai-2.0/06-Migration-and-acceptance.md)
- [WP0 audit readiness](docs/wp0/07-gate-G1-readiness.md)
- [WP0 blockers](docs/wp0/06-open-questions-and-blockers.md)

The legacy application `dragonidf/ha-heating-ai` is a read-only baseline. **No secrets, addresses, production config, runtime state, telemetry or backups may be committed to this repository.**
