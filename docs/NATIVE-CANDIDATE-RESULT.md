# Native controller candidate — PR43, 2026-11-12

Repository-only integration; no HA installation, household connection, legacy shutdown or device commands occurred. This is a native code candidate with a hard-OFF physical gate, not evidence of physical commissioning or a fully qualified autonomous launch.

## Connected execution path

- Native setup opens private WAL/FULL settings/history storage and the existing critical journal off the event loop. Journal reopen reads its checksummed identity; boot reconciliation fences outstanding work without a second owner metadata file. A failed store never falls back to defaults/demo data.
- Actual HA rows retain source timestamps and thermostat capabilities. A separate 2-second memory-only safety pass invokes the accepted stateful control reducer, records grid changes and reports cached/stale/unqualified voltages independently of weather work. HA cache/report timestamps never become raw measurement or KWS output-ready proof.
- The existing bounded source worker invokes the accepted planner/thermal model, using persisted user settings or explicitly bound legacy helpers and real provider data. It publishes its conditional 24h trajectory; missing models/weather/budget coverage remain BLOCKED. It never invents weather issuance, coefficients, verified future grid or historical spend.
- Versioned `heating_ai_v2/backend` over native authenticated HA WebSocket serves snapshots/history and admin-only boot/owner/CAS mutations. SQLite commit/readback precedes success; repeated request identities are checked. STOP is memory-first and durably latches on the current revision even if settings CAS changed. Resume changes planning preference only, never the physical gate or journal fence.
- The three-tab live React panel now consumes that backend: controller/source/journal/one-shot/fan state, conditional model trajectory, persisted settings with conflict-preserving form, independent Recorder and energy archive reads, model provenance and explicit unavailable originals. Backend timeout/fault disables mutations; there is no DemoAPI fallback.
- One hardware KWS kWh cursor supplies counter differences, with duplicate suppression, missing-interval recovery and counter-decrease inhibition. Three direct local phase values remain observations, never an additional integrated energy counter. History uses source report times, not safety-tick time. Unknown original forecast issuance cannot enter the original archive.
- A single native climate boundary uses the accepted final thermostat limiter and durable intent stages. Its HA service/readback callbacks are separated and bounded; HA_ECHO never claims contact ACK. The installed runtime supplies no authority witness and `physical_commands_enabled` unconditionally remains false. Setup/reload/UI cannot activate its future send path. No fan writer is installed; accepted fan policy produces proposals only.
- The existing packaging workflow remains the distribution path. Only five required accepted `ha_native` dependency files are added to its existing vendored engine; synthetic backend/executor/fake transports remain excluded. Accepted `packages`, `ha_sdk`, AGENTS and sealed manifests are unchanged.

## Focused evidence

- `python -m unittest tests.wp2c_revision.test_native_controller_v2 tests.wp2c_revision.test_live_shadow_v2 -v`: 18/18 PASS (six critical transition groups +12 SHADOW guards).
- An added stale-settings STOP case first failed: persisted manual pause became false after CAS conflict. The narrow fix uses the current durable revision for authorized STOP. Only the affected native module was rerun:6/6 PASS.
- `npm run typecheck`: PASS. `npx vitest run tests/live-backend.test.ts`:1/1 PASS, including versioned CAS/history, draft retention, hard-OFF and hung-backend timeout. Only that affected frontend contract file/typecheck was repeated after timeout/fault handling changed.
- No full local test discovery, browser matrix, dependency installation or manual GitHub Actions execution. Automatic final-head CI is authoritative for the existing wider checks; no pending CI is represented as PASS.

## Concrete remaining gates

1. No trusted signed activation/exclusive-writer witness exists. Legacy thermostat/watchdog/updater/fan authors are still active. Physical commands cannot activate; a SQLite reservation is not authority. Controller-only handoff/rollback and independent output/OEM proof have not occurred.
2. Raw room/thermostat/upstream-voltage measurement provenance and KWS supply/protection readiness are unqualified. Last-known values and unchanged zero power are display observations, not electrical or sensor ACKs. Stage calibration remains unqualified rather than fabricated 3/6/9 physical modes.
3. Actual private legacy state/history/original-forecast files are absent from this checkout. Old one-shot outcome, history parity and complete cycle budget cannot be reconstructed. Originals remain MISSING; training/promotion/AI-provider operations without qualified data/provider remain denied or explicitly unavailable. The native worker can use bound real legacy coefficients but does not claim calibration or train on invented records.
4. This run does not qualify installed Core2026.11 lifecycle, household mappings, at least7 days/3 real heating cycles, installation/Marketplace consent, physical safety gates or a real supervised cutover. G1–G9 remain unqualified as applicable. Automatic CI and independent review still determine code acceptance.

No immediate follow-on implementation, publication, install or actuation is authorized by this result.
