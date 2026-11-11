# Issue31 — passive source bridge and bounded one-report recovery

Base: main `945ad59a6ffe83a35185393bf299f9648de171e9`, after merged PR30.
Scope: https://github.com/dragonidf/ha-heating-2/issues/31 . This owner-authorized build/test step does not authorize installation, real-home connection, commands, legacy changes or G1 waiver. Prior reports remain historical evidence.

## Existing vs missing

Reuse SourceActivity/DeviceReport, SourceAdapter, native clock, health recovery/ownership, independent critical store, STOP, VoltagePolicy/KWS readiness and six-component UI. Added only the missing passive integration-write contract/optional sandbox listener, validated timing profile and timing/provenance display. No second planner, authority, watchdog or command writer.

## Passive monitoring, never physical qualification

`PassiveSourceBridge` takes an externally supplied complete three-role mapping: room temperature, companion humidity, independent external return-water probe. Mapping identities never enter the published source view. Role/unit/registry/device/integration matching is mandatory; T&H share one device/integration, the external probe is independent. No household mappings, values or telemetry were retrieved or committed.

`HAObservation` distinguishes current HA value, last_reported, last_updated and last_changed. `IntegrationReport` deliberately has **no hardware sequence, measurement timestamp or measurement-qualified flag**. Cached reads/restores are rejected as new reports. Live integration writes must be credible for this bridge boot/start, monotonically ordered per role and have valid chronological timestamps. The bridge does not create synthetic hardware sequences. SourceActivity stores integration writes separately from its already qualified measurement records and combines only legitimate T/H activity for liveness. It never turns integration writes, humidity or return-water values into room observations/model/chart data. Unknown physical measurement provenance stays UNKNOWN/BLOCKED. A raw sensor unavailable report is source failure evidence, not proof of a physical thermostat action.

The optional `ha_sdk/heating_ai/passive.py::async_attach_passive` listener reads only state_reported plus entity-registry identity/unit metadata for externally selected roles. The filtered immediate callback also sees unchanged HA integration writes; these still cannot prove a new hardware sample. It requires the existing isolation marker, clears startup room assertions and reuses Runtime.flush/notify. It is **not attached by default** and has no production installation, network client, service caller, actuator or physical command route. Existing synthetic sample transport is not repurposed to self-certify HA measurements.

The source view exposes integration timing, monitoring value, activity provenance and **physical_measurement=BLOCKED**, with no binding IDs. SourceActivity still owns all activity/freshness state. The prior six-component panel now shows separate HA timing and accepted measurement/recovery policy without claiming physical heat or ACK. Return-water HA values only corroborate monitoring; they do not become a calibrated thermal veto or positive heating permission. Existing independently qualified synthetic return-water veto remains authoritative and unchanged.

## 30/30 deadlock resolved for qualified offline recovery

`SourceTimingPolicy` validates independent parameters:

- measurement_authorization_age_s: existing5–300s range, default30s. HA options continue using the existing `freshness_s` name; no duplicate setting/authority.
- device_activity_window_s:60–86400s, default3660s, via existing `activity_window_s`. Diagnostic only; no61m AUTO switch.
- recovery_dwell_s: strictly positive and **strictly shorter** than accepted measurement age. Default15s for the30s window; a legacy smaller age derives a half-window default. Explicit incompatible options are rejected, never silently accepted.

`configure_timing` feeds the existing source-age, SourceActivity window and HealthPolicy recovery fields. Native SDK startup uses this validated profile. Default backend recovery is15s; source measurement validity remains30s. Legacy explicitly supplied incompatible HealthPolicy test scenarios remain fail-closed and their accepted regressions are retained: the source view marks recovery_policy_ready=false and planned recovery is blocked. No actual measurement age was expanded to61m or3h.

One newly qualified synthetic room temperature sample after an eligible source-failure AUTO proposal completes the existing dwell after15s without another temperature, humidity, voltage report or phantom heartbeat. At31s the sample still expires and demand fails closed. This repairs the offline timing contradiction, **not the missing physical Tuya measurement provenance**. With only HA state writes, recovery/heat authorization remains BLOCKED regardless of valid timing. Recovery is HEAT_PROPOSED with retained ownership, never physical ACK or NORMAL handoff. STOP, invalid/revoked owner, one-shot, voltage and KWS-delay fences continue to take precedence.

## Focused evidence and limits

- Strict mypy:41 source files PASS.
- Targeted Python:54 PASS (`test_passive_bridge`, `test_source_activity`, `test_health`, `test_health_backend`, `test_voltage_integration`). Ten new tests cover binding/provenance, unchanged integration values, humidity-only,61m diagnostic, unavailable, one-report recovery, expiration, restart/rollback, STOP/owner/voltage/KWS and timing validation.
- Frontend TypeScript PASS;51 targeted tests PASS (`systemHealth.test.tsx`, `native.test.ts`), including new timing/passive-origin/false-ACK validation.
- Existing regressions retained. No broad audit, manual full test suite or workflow trigger/polling.
- Native **Core2026.11.0 compatibility is BLOCKED/NOT_TESTED**: the available local image/harness is2026.10.4, with no2026.11.0 image. The existing SDK EventBus filter signature was inspected and the listener uses its data-filter contract. A local isolated SDK typecheck attempt could not run because that retained image lacks mypy. This is not native acceptance evidence. No broad image/workflow/version rewrite was made; automatic PR CI uses its existing pinned SDK checks. The passive SDK listener needs genuine native event/registry/lifecycle validation on the intended2026.11.0 runtime before any installation.

## Before safe physical activation

1. Privately qualify each role binding, same physical T&H association, raw report vs integration-cache semantics and actual measurement timestamps. Choose/calibrate accepted measurement age/cadence; until then real measurement authorization is BLOCKED. Verify external-probe role/calibration and OEM limits without substituting room or thermostat temperature.
2. Independently qualify upstream three-phase voltage, utility signal, KWS output readiness/power/counter provenance and OEM/electrical/pump protections (G1/B01–B08 unchanged).
3. Implement/review/test the distinct one-writer thermostat transport, permissions, command/ACK/readback, outage/rollback and watchdog arbitration in isolated/staging. No such transport exists here; no real physical command is possible.
4. Validate a controller-only handoff: quiesce the old heating writer plus external watchdog/fan writers under an approved owner/cutover/rollback plan. Never stop the shared AppDaemon add-on or unrelated apps. Rehearse private data/history/state migration and recovery; no production backup/install/change is authorized by this PR.
5. Qualify Core2026.11.0 native lifecycle/event/auth/browser compatibility, then separately authorized shadow/staging and physical acceptance gates. G1 remains BLOCKED; deployment/cutover requires separate authorization and independent review.

## PR32 focused CI compatibility correction

The strict SDK file allowlist now explicitly includes passive.py, while retaining the exact list and all existing AST/service/external-transport/token restrictions. No climate/fan/switch platform or unexpected file is allowed.

The native expiry fixture now uses the coherent synthetic pair freshness_s=5/recovery_dwell_s=2. On the same actual options form it first submits5/15 and requires form/invalid_options, unchanged boot/generation and unchanged measurement-age/dwell/activity policy; it then submits the valid pair atomically and verifies the resulting5/2 ready policy. Pure timing regressions also reject5/15,5/5 and5/-1. Explicit persisted dwell is deliberately preserved: changing age alone to an incompatible value is a validation error, not permission to silently replace an operator's dwell. No options-flow defect was established, so config_flow.py and all safety/source/controller code are unchanged.

Focused local verification:5 tests PASS (four boundary tests plus the timing-policy regression). No manual full CI trigger. Final automatic CI evidence is recorded in the PR description/checks. Physical qualification and2026.11.0 acceptance blockers remain unchanged.
