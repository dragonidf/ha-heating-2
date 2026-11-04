# AGENTS.md — Heating AI 2.0

## Current authority — owner-approved WP2B offline only (2026-11-04)

**WP2B is explicitly approved for isolated synthetic frontend development and tests only.** This is *not* approval to connect to Home Assistant, deploy, operate a heater/fan, import personal data, or start WP2C.

**Read first, in order:**
1. `docs/wp2b/APPROVAL-2026-11-04.md`, `docs/wp2b/WP2B-TASK.md`, full [Issue #17](https://github.com/dragonidf/ha-heating-2/issues/17).
2. `docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md`, `05-UI-design.md`, `02-Architecture.md`, `03-Codex-specification.md`, `04-Test-strategy.md`, `06-Migration-and-acceptance.md`, `requirements.csv` (86), `test-scenarios.csv` (38).
3. `docs/wp0/06-open-questions-and-blockers.md`, `07-gate-G1-readiness.md`, [Issue #3](https://github.com/dragonidf/ha-heating-2/issues/3).
4. Accepted WP1A/B/C and WP2A sources, reports, tests and `docs/ROADMAP-TO-LAUNCH.md`.

## Phase and evidence

- **G0 approved; WP0 reviewed; G1/B01–B08 BLOCKED** (Issue #3).
- **WP1A accepted** PR #6: immutable contracts and pure safety reducer.
- **WP1B accepted** PR #9: isolated critical SQLite, fake gateway, fault/crash handling.
- **WP1C accepted** PR #13: synthetic thermal model, planner, learning and pure fan policy.
- **WP2A accepted** PR #16 (main merge `6ba17e078863280c481c165be57035ac6d01165a`): fake HA contracts, independent evidence/energy archive and synthetic migration rehearsal; **351 regression tests**, final CI 12/12 across Python 3.12/3.13/3.14.
- **WP2B approved OFFLINE/SYNTHETIC ONLY on 2026-11-04:** full operator UI and browser QA under Issue #17. Approval covers only UI code, synthetic fixtures and local browser tests, and explicitly excludes any real HA/backend transport.
- **WP2C and beyond, native integration, real test HA, home shadow, production migration, device control, installation, activation and cutover: NOT AUTHORIZED.** Later gates require separate owner approval and G1 evidence.

## Active WP2B implementation

- Create `feature/wp2b-offline-frontend` and deliver **one complete, functional, unmerged frontend PR** under Issue #17 and `docs/wp2b/WP2B-TASK.md`; not a screenshot or partial prototype.
- Build **Дім · Історія · Налаштування** as primary tabs, with advanced **Модель і діагностика** nested. Use design tokens `05-UI-design.md`; clear Ukrainian mobile/desktop UX.
- Use **only** synthetic/mock read/status/history/settings flows compatible with WP2A typed contracts; no live HA URL, login/token, MQTT, live WebSocket or device service. Locally browsable offline demo, no internet/CDN/analytics dependency.
- UI faithfully separates actual physical observation, desired action, synthetic/fake ACK and unknown. Never label fake ACK `physical success`, never render unknown as zero. Mock controls must be marked simulation-only and cannot reach physical devices.
- **Original12h forecast** must be immutable, genuinely covered, and both source-issued **and received/archived by** reference−12h, or display MISSING. Distinguish latest from original; preserve actual gaps and timezone/DST. Energy graphs must preserve scope, interval quality and unknown coverage, never retro-fill.
- Typed mock CAS setting saves show saved only after persisted simulated revision/readback; handle denial/revoke/conflict/retry/old ACK and offline disabled controls, without changing actual HA settings.
- Preserve all **351 inherited Python regressions** and previous source contracts. Add JS/TS unit, browser E2E, accessibility, long Ukrainian copy, light/dark, 200% zoom, DST, missing/stale/manual/safety/fan/error state tests. Keep all Python 3.12/3.13/3.14 CI, strict types, checksums; no lowered thresholds or hidden critical skips.
- Provide `docs/wp2b/REPORT.md`, ADR, UI tokens, contract fixtures, browser QA matrix, 86/38 honest coverage, SHA manifest. One code PR **OPEN/UNMERGED**, final SHA and test evidence. Self-test offline before handoff, independent ChatGPT review before merge; **do not start WP2C**.

## Mandatory hard boundaries

- **Do not read, contact, modify or install to production Home Assistant**: no entities, helpers, automations, services, dashboards, HACS, AppDaemon, Zigbee2MQTT, Sky Radar, Deye, Recorder DB, backups, host/network, updates, restarts, physical tests or live telemetry access.
- Legacy `dragonidf/ha-heating-ai` is **read-only reference**; never edit its code or files. This is a **public** repo: no real entity IDs, household data, street/address/coordinates, private IP, settings, credentials, backups, logs, user-specific telemetry or screenshots in code/fixtures/CI/PR/issues.
- **No real device command sender, real enabled HA custom component, second thermostat/fan writer or authenticated HA session**. Browser controls connect only to fake in-memory/local synthetic operations with no route to live devices.
- Preserve safety, manual priority, STOP, boot/owner fencing, one-shot durability, zero vs unknown and uncertainty/provenance. The UI never grants backend authority or bypasses guards.
- Physical 3/6/9 kW remain **unverified planning scenarios**, not remotely controllable output stages. **B08 remains unresolved**: no invented global 180-minute session cap; preserve old one-shot semantics.
- **G1/B01–B08 and G2–G9 remain BLOCKED/NOT_TESTED**. Green synthetic/browser CI is *not* proof of real HA compatibility, OEM physical safety, actual grid metrology, future N100 durability, seven-day/three-cycle shadow or launch readiness.

## Precedence

This later **phase-specific WP2B offline permission** replaces historic “WP2A only / WP2B not authorized” **timing statements only**. Existing owner architecture ADR01–07, canonical P0/P1 requirements, hard privacy/device boundaries, gate checks and independent review remain fully binding. No implementation PR can self-merge or start the next stage.
