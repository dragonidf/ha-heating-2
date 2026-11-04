# WP2C — complete Codex engineering task, AUTHORIZED isolated test only

**Owner approved 2026-11-04: new disposable independent Home Assistant test instance plus code/tests, synthetic-only.** Normative feature list and boundaries: [Issue #20](https://github.com/dragonidf/ha-heating-2/issues/20).

## First reads

- Current `AGENTS.md`, [owner authorization](APPROVAL-2026-11-04.md), full [Issue #20](https://github.com/dragonidf/ha-heating-2/issues/20).
- Canonical `docs/spec/heating-ai-2.0/` architecture `02`, full Codex specification `03`, test strategy `04`, approved UI `05`, migration/acceptance `06`, 86 requirements and 38 scenarios, approved ADR01–07 and `docs/ROADMAP-TO-LAUNCH.md`.
- G1 Issue #3 and WP0 audited blockers B01–B08. Accepted WP1A/B/C, WP2A/B contracts, reports, code and test suites, including original-12h issue+receipt evidence, manual/STOP priority, synthetic ledger recovery, energy overlap and UI 200% responsive/failure cases.

## Implement as ONE cohesive PR

Branch `feature/wp2c-isolated-ha-packaging` from latest `main`; **do not make a second implementation PR or self-merge**.

**1 — sandbox & native HA compatibility:** Provision a new disposable **real HA Core test instance only inside Codex's separate sandbox/ephemeral CI**. Pin its version/digest and provision synthetic credentials, fake entities and disposable SQLite. Disable discovery and external integrations; enforce loopback-only endpoint and no route to any existing production/home LAN/devices. Do not access host Proxmox or owner's HA. If actual HA cannot be safely provisioned, implement mock/static tests and document native tests as BLOCKED, never reroute to production or claim native PASS. Record proveable isolation, repeatable setup/teardown and test-host limitations.

**2 — disabled-by-default integration:** HA-native package and config/options flows with strong typed entity/source validation, failure isolation, registry, version migrations, lifecycle/load/unload/reload. Use accepted WP1A/B/C and WP2A contracts without weakening safety. **No real actuator writer, no operational HA service calls to heaters/fans/Deye/Tuya, no real physical command route.** Empty/unverified bindings fail closed; fake command receipts cannot assert a physical state. Reconnect/boot/permissions/owner-epoch, independent STOP/manual one-writer semantics must remain correct.

**3 — packaged standalone WP2B UI:** Serve the accepted `Дім · Історія · Налаштування` UI from the isolated test instance (test-only panel/view). Validate actual test-instance registration/auth lifecycle, constrained session scopes, dark/light, mobile/desktop, locale, accessibility and Chromium/WebKit. Keep synthetic labels, accurate measured/desired/ack distinction, immutable qualified original-12h vs actual with gaps, honest energy/cost quality and CAS readback. Do not modify user production dashboard/theme.

**4 — data and migration:** Reversible disposable synthetic DB/store schema upgrades, versioned manifest, rollback/backup **only of synthetic test instance data**. Failure injections on restart, read-only/locked SQLite, invalid config, missed events, stale/duplicate, G1 blockers, broken archive, unknown source. Real Recorder and legacy data are forbidden.

**5 — future Tuya 3-phase boiler protective meter:** Design typed fake binding for a future boiler-only source measuring **total/per-phase active W and cumulative imported kWh where model actually supports them**; absent/unavailable/unknown is not 0. Test reset/jump, freshness, contradictory phase sums, overlapping physical meters, source privilege, counter accuracy and fallback estimated 3/6/9kW. Do not guess model/entity IDs, link Zigbee2MQTT, touch physical protection, pair relay or assert B03 closed. A protective relay is not guaranteed to be an accuracy-class energy meter.

**6 — QA/reports:** Keep **351 Python +202 frontend +80 browser baseline** (all previous regressions intact). Add real **isolated native HA** startup/config-entry/panel/auth lifecycle and browser E2E tests; preserve Python 3.12/3.13/3.14/strict mypy and Chromium/WebKit 14-job baseline; add isolation, security, fault, compatibility, perf evidence with unchanged quality gates. Produce `docs/wp2c/REPORT.md`, `ADR-WP2C.md`, HA version matrix, network-isolation verification, test logs/checksums and honest 86/38 traceability. Explicit PASS_ISOLATED vs MOCK_ONLY vs BLOCKED for real HA, physical/production and N100 evidence.

**Deliver:** one OPEN/unmerged code PR. Self-fix normal synthetic bugs without intermediate reports. Final handoff **only PR URL, final SHA, Python/frontend/browser/new HA test counts, CI job summary, any blockers**.

## Hard stop

**Never connect to/read/write production HA or old controller/repo**, personal LAN or host, real devices, private config/history, or power meter. Do not deploy anywhere outside new isolated ephemeral test HA. No real device service senders or second writer. No production telemetry in this public repository. **G1/B01–B08 BLOCKED; WP2D and beyond NOT AUTHORIZED**. If infrastructure cannot host an isolated instance, mark genuine native proof BLOCKED and ask no permission to use owner's production equipment.
