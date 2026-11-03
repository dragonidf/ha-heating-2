# AGENTS.md — Heating AI 2.0

## Current authorized phase (2026-11-03)

**WP2A is APPROVED FOR ISOLATED OFFLINE DEVELOPMENT AND SYNTHETIC TESTS ONLY**, following explicit owner approval in `docs/wp2a/APPROVAL-2026-11-03.md`. Read, in order:

1. `docs/wp2a/APPROVAL-2026-11-03.md`, `docs/wp2a/WP2A-TASK.md` and full [Issue #14](https://github.com/dragonidf/ha-heating-2/issues/14).
2. Canonical owner-approved `docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md`, `02-Architecture.md`, `03-Codex-specification.md`, `04-Test-strategy.md`, `06-Migration-and-acceptance.md`, and the full 86 requirement / 38 test-scenario CSV registers.
3. `docs/wp0/06-open-questions-and-blockers.md`, `docs/wp0/07-gate-G1-readiness.md`, [Issue #3](https://github.com/dragonidf/ha-heating-2/issues/3).
4. Previously accepted WP1A/B/C implementation, reports and regression tests; `docs/ROADMAP-TO-LAUNCH.md`.

## State / phase authorization

- **G0** architecture ADR01–07 and owner clarifications approved; **WP0** baseline read-only audit reviewed, but **G1 BLOCKED: B01–B08** in Issue #3.
- **WP1A accepted** in PR #6 — immutable typed contracts and pure safety reducer.
- **WP1B accepted** in PR #9 — isolated SQLite critical store, fake gateway and crash/restart fault simulation.
- **WP1C accepted** in PR #13 — synthetic thermal model, robust planner, learning gates and pure fan arbitration; 219 reported tests, nine final-head CI checks Python 3.12/3.13/3.14. WP1C main merge `9525e46d2c8155155aac513b95f49e30ca6ee749`.
- **WP2A explicitly approved OFFLINE ONLY (2026-11-03)** — fake HA-facing typed integration seam, separate evidence/energy archive, **synthetic-only** legacy migration dry-run, fault/replay/CI tests. Full scope in Issue #14.
- **WP2B and later NOT AUTHORIZED**. A live HA adapter, actual device writer, production installation, real shadow operation, private data import/export, OEM/physical tests, actual cutover and release require separate approvals and verified gate evidence.

## WP2A deliverable

- Complete **all offline WP2A** sections of Issue #14 as one cohesive implementation in `feature/wp2a-offline-integration-ledger`. Use synthetic inputs only. New modules for fake HA client/contracts, independent SQLite evidence ledger and synthetic migration rehearsal are allowed.
- No actual `custom_components/heating_ai` enabled component, HA URL/token/connection, real MQTT/HTTP/WebSocket/device transport, real HA services or physical command path. Fake adapters must not be connectable to real devices by supplying a URL or token.
- Preserve pure WP1A kernel, WP1C planner/thermal/fan boundaries and WP1B STOP/one-writer fencing. Integration outputs are **proposals**, synthetic state and provenance; actual HEAT remains unauthorized outside verified safety runtime.
- Keep all 219 prior tests and negative regressions. Implement evidence idempotency, signed/overlapping metering, quality coverage vs zero, frozen original-12h comparison, history bounded queries, date-aware tariff, crash/restart and failure boundaries.
- Run strict mypy and CI on Python 3.12/3.13/3.14, qualify *test* SQLite, preserve quality limits, document sources/checksums and honest 86/38 traceability; never treat a simulated success as actual ON/OFF or G1 PASS.
- Create **one OPEN / UNMERGED code PR** with report, ADR, test outputs, source SHA and blockers. Fix ordinary sandbox defects autonomously before review; report a concise final handoff; don't start WP2B or self-merge.

## Hard safety, privacy and project boundaries

- **Do not read, modify or deploy anything in production Home Assistant** during WP2A. No HA config, entity/helper/automation/service, sensors, Recorder, database, add-ons, HACS, Zigbee2MQTT, Sky Radar, AppDaemon, Deye, network/router, dashboard, host/OS or scheduled job changes; no reloads, restarts, device operations, backups, imports or live-HA observation from code.
- Legacy `dragonidf/ha-heating-ai` remains **read-only reference**; no edits, PRs, live production state, historical private export or installed application change.
- This repository is **public**: no actual household entity IDs, locations, IPs, power topology, meters, credentials, raw live sensor states, user logs, configs, filenames revealing secrets, home history, backups or other private data in code/CI/issues/reports.
- No real device command route or second writer. Manual priority, boot/owner epoch fencing, trusted emergency STOP, unknown-vs-zero, stale-input denial, one-shot durability, independent failure containment and safe fallback are mandatory. WP1B evidence-store delays cannot block STOP.
- Do **not** infer the physical 3/6/9 kW mode, a verified signed Deye measurement, exact pump behavior or a valid home calibration from synthetic tests.
- **B08** remains unresolved: preserve legacy `HEAT_AFTER_GRID_RESTORE` one-shot semantics and **do not invent a global 180-minute heating-session cap**.
- Never claim G1/G2–G9, actual HA compatibility, production N100/SQLite durability, actual physical ON/OFF evidence, seven-day shadow, migration or household energy parity PASS from offline tests.

## Precedence

This is later **phase-specific** authorization and supersedes older statements saying `WP1C only` / `WP2A not authorized` **solely for sandbox WP2A development**. It does not supersede owner architectural ADRs, any P0/P1 safety rule, G1/B01–B08, physical-access bans, privacy rules or later staging/activation gates.
