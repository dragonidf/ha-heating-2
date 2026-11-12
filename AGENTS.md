# AGENTS.md — Heating AI 2.0

## Current owner authorization (2026-11-04): WP2C isolated HA sandbox ONLY

Owner explicitly approved **WP2C development, provisioning a new disposable independent Home Assistant Core TEST instance, and synthetic-only native integration/browser tests** under [Issue #20](https://github.com/dragonidf/ha-heating-2/issues/20). The test HA must live **solely inside a separate Codex sandbox or ephemeral CI runner**, with fake identities and data. **No production HA access, even read-only; no existing user-host/Proxmox/LAN access; no physical equipment contact.** No WP2D/real shadow/deployment permission.

## Context loading — new phase vs. resumed incremental work

**Always read this current `AGENTS.md` first.** Its authorization, safety and privacy rules are mandatory regardless of task size. This change adjusts context-loading and execution efficiency only, not permissions.

- **First task of a newly authorized work package:** read that phase's approval and task, the active GitHub issue, and the canonical architecture/safety/specification sections actually needed for the assigned implementation. For WP2C, the full reference set remains available in `docs/wp2c/APPROVAL-2026-11-04.md`, `docs/wp2c/WP2C-TASK.md`, `docs/spec/heating-ai-2.0/`, `docs/wp0/`, and Issue #3; consult the applicable files, not all as an automatic reread.
- **Resuming an interrupted Codex task or a small PR follow-up:** continue the **same task and existing branch**. Read the latest issue addendum, PR review comments, affected source files/contracts and directly relevant tests. Do **not** restart the architecture review, reread every report/ADR/CSV, rebuild the whole project or repeat a completed audit unless evidence specifically requires it.
- Before editing after a pause, check `git status`, the current branch/HEAD and any local work. **Preserve in-progress edits and commits.** Sync remote branch changes without destructive `reset --hard`, `clean`, forced pushes or silent overwrite; if conflicts or unknown local changes cannot be resolved safely, report the blocker and stop.
- For safety-sensitive control changes (voltage guard, freshness/time, owner fencing, STOP/manual, permissions, one-shot, real-device boundaries), reread only the relevant canonical P0/P1 safety invariants and their regression tests. For schema/SDK/DB changes, reread the specific affected contract, migration and integration tests.

## Codex execution budget and stop rules

1. The technical architect owns architectural analysis, GitHub review, requirements synthesis and overall prioritization. **Codex implements only the bounded task actually assigned.** Do not independently launch cross-repository audits or new work packages.
2. Prefer small, independent implementation slices, with explicit file/component scope, definition of done, risk and stop conditions. The existing ongoing WP2C correction remains one logical task; **do not discard work or demand a new task because these rules were updated**.
3. For each incremental slice: first create a minimal failing regression, apply the narrow fix, run targeted unit/type/integration tests. Run full CI at final PR-head checkpoints or when change impact requires it for safety. **Never relax or disable safety/coverage/type checks or skip critical tests.**
4. Do not repeat already accepted WP1A/B/C, WP2A/B analysis or reimplement their code without a demonstrable regression. Preserve tests, version contracts and immutable evidence.
5. If a new issue is outside the current assigned scope, record it instead of expanding indefinitely, except when necessary to prevent an immediate safety regression. If sandbox, permissions, dependency or time/token budget is exhausted, leave a reproducible partial result plus exact remaining blocker; never invent PASS evidence.
6. Keep the current implementation PR **OPEN and UNMERGED** for independent review. Full end-to-end CI only after targeted fixes pass; no WP2D or automatic follow-on deployment.

## Current interrupted work — WP2C PR #22

Continue the ongoing PR #22 from its **existing local/remote state**, not a new branch or fresh implementation. Latest owner addendum is in Issue #20 and the consolidated review comment on PR #22. Only **synthetic/offline** behavior is authorized:
- Boiler active power and cumulative energy: proposed future **KWS through Tuya Local**, three-phase active power and a single total kWh ledger; cloud and local views are the same physical meter and must not be double-counted. Do not assume equal phase loading.
- Voltage guard: three input-grid voltage channels from **Zigbee2MQTT input-220**, **not KWS voltage**. Input-side observation is not boiler-terminal voltage. Threshold/hysteresis/continuous recovery and stale/missing phase decisions must fail closed, while never operating real relays/pumps.
- Address the native backend's frozen snapshot clock so source validity expires during event silence, with injectable time and focused regressions.
- No real entity IDs, private telemetry, real home mappings or hardware access in repository/CI. No real bindings or actuator writer; **G1/B01–B08 BLOCKED**.


## Accepted phases and unresolved gates

- G0 ADR01–07 approved, WP0 reviewed. **G1/B01–B08 remain BLOCKED** in Issue #3; G2–G9 production gates not qualified.
- **WP1A accepted** PR #6: pure typed controller/safety kernel.
- **WP1B accepted** PR #9: isolated SQLite critical store, fake gateway, crash/restart tests.
- **WP1C accepted** PR #13: synthetic thermal model, planner, learning and pure fan policy.
- **WP2A accepted** PR #16: synthetic fake HA contracts, energy/evidence archive, migration rehearsal; 351 Python tests.
- **WP2B accepted** PR #19 (main merge `33d8ba57ac9bf369bee5720fe9d42660d1b6f399`): complete offline UI, typed mock CAS, honest 12h history, energy and browser QA; **351 Python +202 frontend +80 browser** tests; final CI 14/14.
- **WP2C owner-approved (2026-11-04), ISOLATED TEST HA ONLY**: native HA packaging/config/registry/panel/auth compatibility test inside a **new disposable sandbox instance** plus synthetic migration/fault tests; no existing HA, real device, user host or live source.
- **WP2D or later, real-home read-only zero-write shadow, private migration, physical qualification, install/cutover/deployment: NOT AUTHORIZED.**

## WP2C deliverable — one reviewable code PR

- Work in `feature/wp2c-isolated-ha-packaging`, one coherent **unmerged** PR. Cover all Issue #20 and `docs/wp2c/WP2C-TASK.md`; do not substitute a mock screenshot for actual native HA compatibility.
- Create/test an actual pin-version HA Core **inside Codex sandbox/CI only**, separately namespaced, disposable storage, synthetic auth and fake sensor/meter entities. Bind test UI to test-only backend with disabled-by-default mock state, no real actuator route.
- Security: test HA runtime should be isolated from home/owner networks, no public listener, no ZeroConf/device discovery, no cloud client. Allow official pinned dependency/image retrieval during environment setup as needed; prohibit runtime egress to real devices. Record test-host proof of network isolation, bindings, version/digest, teardown; if genuine isolated HA cannot be safely launched mark native evidence **BLOCKED** instead of accessing user's HA or claiming fake CI validates it.
- HA config/options, entity-registry lifecycle, panel assets, test instance auth/session flow, restart/unload/reload, startup failure, invalid/unavailable input and data-store migrations/recovery with synthetic-only fixtures. Backend safety/permissions remain authoritative; fake ACK or HA service/registry registration is **not** proof of actual device operation.
- Preserve all accepted **351 Python, 202 frontend and 80 browser** regressions and safety invariants. Add genuine isolated HA SDK integration/QA, real browser tests against the disposable instance, Python3.12/3.13/3.14, strict mypy/TS, CI (at least baseline 14 jobs), coverage and checksum/86–38 traceability without lowering thresholds.
- Package user-facing WP2B `Дім · Історія · Налаштування` and nested diagnostics; 12h original issued **and archived before cutoff** or MISSING, no false measured gaps, no unqualified kWh/physical statuses, correct UTC/Kyiv/DST, persisted mock settings with verified readback.
- Maintain the **synthetic-only source-binding contract for the installed KWS meter through Tuya Local (boiler power/total imported kWh) and the separate input-220 Zigbee2MQTT 3-phase voltage source**, as revised in Issue #20. Physical mappings/accuracy are still unverified; no model/entity-ID guess, cloud double-counting, real integration, pairing or electrical changes. **B03 remains BLOCKED** and the relay is never a software actuator.
- `docs/wp2c/REPORT.md`, ADR, HA native version matrix, isolation proof, QA/fault/perf, 86/38 mappings and SHA manifest; one OPEN PR and final SHA/tests/CI evidence; independent QA before merge. No automatic WP2D.

## Absolute safety, privacy and scope stops

- **Do not read, contact, edit, back up, install to, restart or otherwise interact with production Home Assistant**, any existing HA account/host, user's local network/Proxmox/N100, HACS, AppDaemon, Zigbee2MQTT, Sky Radar, Deye, Tuya, thermostats/fans/boiler, cloud services or private history. No production dashboard/automation/helper/configuration, Recorder/SQLite, gateway/router or physical command changes.
- Legacy `dragonidf/ha-heating-ai` is **read-only baseline**, never edit repo or installed controller. Public repository: no home entity IDs, household topology, real logs/timestamps, location, IP address, authentication details, private telemetry, backup or secrets.
- **No real device command gateway, authenticated production session, MQTT/Tuya/Modbus service sender or second thermostat/fan writer.** Only test HA's synthetic identity and dummy actions. HA-native registration/test APIs are allowed within disposable test only; executing real physical-device services is not.
- Keep unknown-vs-zero, fail-safe STOP, manual priority, owner-epoch one-writer fence, one-shot durable state, source freshness, energy provenance and original-12h read/receipt safety. An unverified stage 3/6/9kW is an **estimate**, not actual power. **B08 unresolved**: no invented global 180min heater cap from one-shot behavior.
- **G1/B01–B08 BLOCKED** and G2–G9 **NOT_TESTED/BLOCKED** until separately verified. Native compatibility inside a fake HA is not physical/metrology/OEM/N100/7d-shadow validation.

## Precedence

This later **WP2C isolated test-only permission** supersedes prior phase-timing prohibition `WP2C not authorized` **solely for bounded test work**. It does not override canonical architecture, P0/P1 safety requirements, G1, privacy, physical access prohibition or independent acceptance gates.
