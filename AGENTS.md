# AGENTS.md — Heating AI 2.0

## What to read first (current instructions)

1. **Current phase**: `docs/wp1b/APPROVAL-2026-11-03.md` and `docs/wp1b/WP1B-TASK.md`.
2. **Current safety blockers**: `docs/wp0/07-gate-G1-readiness.md`, `docs/wp0/06-open-questions-and-blockers.md`, GitHub Issue #3.
3. **Completed foundation**: `docs/wp1a/REPORT.md`, `docs/wp1a/ADR-WP1A.md`, all `packages/contracts/` and `packages/control/`.
4. **Architecture and scope**: `docs/spec/heating-ai-2.0/HANDOFF.md`, `APPROVAL-2026-11-03.md`, `02-Architecture.md`, `03-Codex-specification.md`, `04-Test-strategy.md`, `06-Migration-and-acceptance.md`.
5. `docs/spec/heating-ai-2.0/requirements.csv` and `test-scenarios.csv`, and `docs/ROADMAP-TO-LAUNCH.md`.

## Current authorization, superseding obsolete earlier phase labels

- G0: architecture ADR01–07 and four owner clarifications approved.
- WP0: read-only audit accepted in PR #2. **G1 remains BLOCKED: B01–B08** in Issue #3.
- WP1A: pure contract/safety reducer implemented and reviewed/merged in PR #6; retain all its regression tests.
- **WP1B: explicitly approved 2026-11-03, OFFLINE ONLY**, for isolated SQLite state durability, a fake non-HA command gateway, synthetic crash/restart/queue and failure tests, and associated docs. See `docs/wp1b/WP1B-TASK.md` and Issue #7.
- WP1C, real HA adapters, running integration, physical tests and deployment/cutover **NOT AUTHORIZED**. Do not auto-start after WP1B.
- Future gates G2–G9 require evidence and stage-specific approvals. Offline test success does **not** close G1/G3 or certify N100/real hardware safety.

## Hard boundaries (never bypass)

- Never modify or deploy to production Home Assistant: no settings, files, helpers, automations, services, add-ons, dashboards, HA database, entities, devices, HACS, Z2M, Deye, Sky Radar, AppDaemon lifecycle, network or OS changes.
- No device actuation of any kind. No HA service call, fan/thermostat/MQTT/Tuya/Deye control, real network device connector, physical test or restart.
- Legacy `dragonidf/ha-heating-ai` is immutable **read-only reference**; do not change it.
- No private production backups/exports/replay without separate specific authorization. No household telemetry, real entity/device IDs, IPs, location, credentials, unredacted logs or config in this **public** GitHub repository, CI, PR or fixtures.
- Only synthetic/fake actuator adapters on disposable sandbox DB/filesystem/processes. **Never create an actually dispatchable gateway or enabled Home Assistant integration in WP1B.**
- Keep `packages/contracts/` and `packages/control/` **pure**, with no database/network/HA/clock imports or I/O. All I/O confined to `packages/control_store/` and local fake simulator adapters.
- Verify actual test-host linked SQLite, WAL/FULL and crash behavior; do not infer production qualification. Unverified evidence = BLOCKED, never PASS.
- Don't reinterpret legacy one-shot to OFF-on-grid-return; B08 180-minute cap scope unresolved, no global cap invention.
- Manual priority, proper current-grid freshness, trusted emergency stop, stale event fencing and 92 WP1A tests are invariants, not optional regressions.
- All work in dedicated `feature/wp1b-offline-store-simulator` branch, open PR **without merge**, run CI, report tests/faults and exact requirement IDs; no WP1C work. Stop for independent review.

## Precedence

This is a new owner-approved phase. It supersedes only outdated "WP0 only" / "WP1A only" text in prior docs; it **does not** change architecture, manual priority, blocklists, reliability gates or operational permissions.
