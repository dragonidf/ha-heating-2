# AGENTS.md — Heating AI 2.0

## Start here — current authority (2026-11-03)

1. Read `docs/wp1c/APPROVAL-2026-11-03.md` and `docs/wp1c/WP1C-TASK.md`, then the full [Issue #11](https://github.com/dragonidf/ha-heating-2/issues/11). They control the **currently authorized offline-only WP1C** work.
2. Review the approved `docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md`, `02-Architecture.md`, `03-Codex-specification.md` (D/P/M/F requirements), `04-Test-strategy.md`, `06-Migration-and-acceptance.md`, `requirements.csv` and `test-scenarios.csv`.
3. Read `docs/wp0/06-open-questions-and-blockers.md`, `07-gate-G1-readiness.md` and [Issue #3](https://github.com/dragonidf/ha-heating-2/issues/3).
4. Read WP1A and WP1B reports, ADRs, all accepted contracts/kernel/store/simulator source and their complete regression tests; see `docs/ROADMAP-TO-LAUNCH.md`.

## Current phase / approval

- **G0:** architecture ADR01–07 and owner clarifications APPROVED.
- **WP0:** read-only baseline audit REVIEWED (PR #2). **G1 remains BLOCKED: B01–B08** (Issue #3).
- **WP1A:** immutable contracts + pure safety reducer ACCEPTED (PR #6).
- **WP1B:** offline transactional control store + fake gateway ACCEPTED (PR #9); 155 reported tests / six cross-Python final checks.
- **WP1C:** owner **explicitly APPROVED OFFLINE ONLY**, 2026-11-03, for synthetic thermal/model/observer/planner/learning and pure fan policy under Issue #11. New phase-specific instructions override obsolete older "WP1B only", "WP1C not authorized" wording **only for WP1C synthetic development**. The architecture/safety rules and G1/G2–G9 gates remain binding.
- **WP2A and beyond, live HA integration, actual gateway, shadow deployment, real-device tests, backup/migration and cutover:** NOT AUTHORIZED by WP1C approval.

## WP1C engineering execution

- Build one complete coherent package in `feature/wp1c-offline-model-planner` per `docs/wp1c/WP1C-TASK.md` and full Issue #11; implement **all offline aspects**, not a prototype. Pure typed planner outputs are **proposals**, never commands.
- Required module groups: `packages/thermal/` (two-state baseline/observer with qualified provenance and uncertainty), `packages/planner/` (feasible deterministic schedule, 07:00 preheat, blackout/time/energy budget, stable frozen 12h reference), optional `packages/learning/` (champion/challenger with independent days, no leakage), `packages/fan_policy/` (fireplace and night demand arbitration).
- No physical 3/6/9 kW stage selection; candidate power scenarios only. Preserve validated baseline coefficient units or report `NOT_PARITY_VERIFIED`. Unknown sensors/energy/outages remain uncertain, not zero. No missing/fake 12h historical forecast. Safety/manual/actual-grid priority cannot be bypassed by planner or AI.
- Preserve all WP1A+WP1B behavior and 155 existing regression tests. Add substantive synthetic negative/fault/property tests, CI Python 3.12/3.13/3.14, type checks and traceability for 86 requirements/38 scenarios; never weaken critical tests to pass.
- Output `docs/wp1c/REPORT.md`, ADR and reproducible evidence; single **open/unmerged PR** for independent review. Do not auto-merge, deploy or proceed to WP2A. Keep final chat handoff concise (PR URL/SHA/tests/critical blockers).

## Hard safety and privacy boundaries — mandatory

- **Never change production Home Assistant:** no files, entities, helpers, automations, services, dashboards, HACS, Zigbee2MQTT, Sky Radar, Deye, AppDaemon, database, OS/network, reload, restart, installs, actual backups, migrations or device commands.
- No HA/MQTT/HTTP device connectivity, thermostat/fan actions, physical tests or live source reads in WP1C. No enabled integration, actual gateway or background heating scheduler.
- Legacy `dragonidf/ha-heating-ai` may be inspected as **read-only reference** to verify historical thermal equations and units, but cannot be modified. Pin any cited source commit.
- **Public repository:** synthetic/test data only. No user-specific live configuration, states/history, logs, entity IDs, physical address/location, private IP, credentials, access tokens or private backup in code, PR, CI or issues.
- Preserve pure `packages/contracts`/`packages/control` boundaries; WP1C pure packages must not import I/O, store, simulated actuator, network or system-time operations. SQLite and FakeActuator remain WP1B-only test mechanisms, not a live transport.
- Test-runtime linked SQLite proof does not qualify target host, real filesystem power loss, physical OFF timing or ownership. Such cases remain BLOCKED/NOT_TESTED.
- Manual priority, emergency STOP, stale sensor/event fencing, one-writer invariant and consent gates are non-negotiable.
- Legacy one-shot means `HEAT_AFTER_GRID_RESTORE`, **not** automatic OFF-on-return. **B08 is undecided; do not introduce a global 180-min cap or reinterpret session policy.**
- **G1/B01–B08 remain BLOCKED**, regardless of passing synthetic tests; G2–G9 and any live integration require separate explicit approval.

## Precedence

This later owner's offline WP1C approval changes **only the permitted development phase**. It does not supersede ADR01–07, canonical P0/P1 requirements, device restrictions, private evidence gates or the rule that each new code PR stops for independent review.
