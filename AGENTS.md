# AGENTS.md — Heating AI 2.0

Read in this order:
1. `docs/spec/heating-ai-2.0/HANDOFF.md` and `APPROVAL-2026-11-03.md`
2. `docs/wp0/07-gate-G1-readiness.md` and `06-open-questions-and-blockers.md`
3. `docs/wp1a/WP1A-TASK.md` (**current work scope**)
4. `docs/spec/heating-ai-2.0/02-Architecture.md` and `03-Codex-specification.md`
5. `docs/spec/heating-ai-2.0/04-Test-strategy.md`, `requirements.csv`, `test-scenarios.csv`
6. `docs/spec/heating-ai-2.0/06-Migration-and-acceptance.md`

## Current phase and authorization

- **G0:** architecture ADR01–07 and owner clarifications approved 2026-11-03.
- **WP0:** read-only audit documents merged as PR #2; **G1 remains BLOCKED**, per docs/wp0/07 and [issue #3](https://github.com/dragonidf/ha-heating-2/issues/3).
- **WP1A:** following owner's request to continue after reviewing WP0, **only synthetic pure typed contracts and safety reducer with tests** are authorized. Follow `docs/wp1a/WP1A-TASK.md` exactly.
- **WP1B and later:** not authorized. Do not create running integration, command gateway, compute daemon, live bindings, installation, migration, physical tests or cutover.
- WP1A is *not* a waiver of G1 blockers and does not mark any future G3–G9 gate passed.

## Hard boundaries

- Never modify the production Home Assistant installation, settings, files, helpers, automations, services, running add-ons, devices, telemetry or network.
- Never issue control commands, start/stop/restart/update Home Assistant/AppDaemon, or run physical failure tests.
- Never modify `dragonidf/ha-heating-ai`; it is immutable read-only source baseline unless separately authorized in the future.
- No production backup creation or private runtime export/replay without explicit scoped authorization.
- Do not place credentials, access tokens, private IP/addresses, identifying private data, full configuration, state/history/telemetry, or device identities in GitHub, PRs, CI or test fixtures.
- Use only synthetic test data in WP1A. Unverified premises are BLOCKED, not default values or fake PASS.
- Work in a dedicated branch/PR with tests, traceability, and evidence. Leave WP1A PR open for review; do not auto-merge or proceed to WP1B.

If this file conflicts with old pre-approval wording in original specification, the explicit later approval and the narrow current phase scope take precedence **only within their authorized boundaries**.
