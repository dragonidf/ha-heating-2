# Issue29 — independent T&H activity and temperature freshness

Base: merged PR28, main `77642890148e68749693e6c6c9c9224849a1ce7d`.
Owner decision: https://github.com/dragonidf/ha-heating-2/issues/29#issuecomment-6793683799 . Synthetic implementation only; no production inspection or physical bindings were used. This note intentionally omits household entity IDs, values and telemetry.

## Evidence and authority

| Evidence | Meaning | Permission effect |
| --- | --- | --- |
| Qualified raw temperature OR humidity report from the verified same synthetic T&H device | Device activity, aged by report timestamp and independent monotonic clock | Never refreshes a temperature measurement by itself |
| Qualified temperature measurement with its own observed timestamp | Sole room/model/chart measurement | Existing source max age, owner, STOP, voltage/KWS and persistence gates still apply |
| Independent external return-water probe | Auxiliary freshness/plausibility evidence | May veto; never substitutes room or thermostat temperature and never authorizes heat |
| HA last_reported / integration state write | Integration wrote state; hardware sampling unknown | Rejected as qualified raw evidence |
| Recorder, derived/controller state or UI poll | State persistence/publication/request | Rejected as raw report/measurement evidence |

No genuinely repeated unchanged Tuya hardware report was verified. HA last_changed concerns value changes; last_updated concerns value/attribute updates; last_reported concerns integration writes, including unchanged writes. None independently proves a new hardware temperature measurement. A future qualified transport/sequence/timestamp contract is commissioning work, not inferred from state history. The synthetic tests can represent a genuinely repeated same-value report with a new independently qualified observed timestamp. A new report carrying an old observed timestamp only updates activity, not temperature age or recovery report identity.

`DeviceReport` is a typed, trusted Python fixture seam. It is **not** a client-supplied privilege flag on a new websocket/event API. Only artificial IDs and explicit synthetic provenance are accepted; exact T&H companion-device identity, role, unit, qualification, boot, chronological timestamps and per-role sequence are checked. Unrelated humidity, probe-body temperature, replays, old boots, future timestamps and HA republications cannot refresh it. Native HA has no new real Tuya binding/writer; unbound provenance remains UNKNOWN. The existing generic SourceEvent adapter is reused for qualified synthetic room samples, never for humidity or return water. Existing model/history values are not rewritten.

## Policy and status

- `living_device_last_activity` is the latest qualified raw T/H activity, with its own age and OK / DEGRADED / UNKNOWN quality.
- `living_temperature_last_observed` retains the last independently qualified measurement, even after an unavailable report. Its age/quality remains separate: OK / STALE / UNKNOWN / source OFFLINE. OFFLINE here describes qualified source unavailability, not proven physical-device failure.
- `return_water_last_observed` retains independent probe evidence; missing/unavailable probe never displays false OK. No water-temperature alarm limit or OEM calibration was invented.
- Native test HA options expose `activity_window_s`, default **3660s**, bounded60–86400s. This is an experimental diagnostic setting, not a calibrated disconnection threshold or a temperature-age override. Existing options get the default and partial options preserve it. The panel shows the threshold and three separate ages/qualities inside the existing six-component status block.
- Beyond61m, including a two-hour no-change gap, activity becomes uncertain. It never automatically proposes AUTO from this threshold. The typed T&H path also disables uncalibrated prolonged-silence inference; fallback requires fresh qualified temperature-source unavailability plus the existing cold grace, electrical/KWS, thermostat, STOP and ownership fences. The prior generic SourceEvent synthetic scenarios retain their explicit HealthPolicy timeout semantics; those are not new physical Tuya qualification.
- Temperature max age remains **30s by default**, configurable only in the existing5–300s source policy. Humidity/return-water cannot enlarge it or turn invalid room data into eligible heat. Recovery still requires a new qualified room report, plan/one-shot gates and the original dwell. AUTO/HEAT remain proposals without physical ACK.
- A return-water veto is an explicitly supplied synthetic plausibility result, not a guessed numerical threshold. It suppresses demand and planned recovery, latches across stale/unavailable probe data and critical-store restart, and clears only on a new qualified fresh probe observation. The additive critical snapshot field defaults safely for old records; no schema/version or accepted source/settings schema was replaced. Raw activity/temperature observations are deliberately not restored as fresh evidence after restart.

## Remaining blockers

**30s/30s remains BLOCKED.** The single-report backend regression again shows a temperature becoming stale at30.1s, resetting recovery without HEAT proposal. No safe physical report provenance or calibrated longer source-age policy was established, so neither source age nor recovery dwell was changed.

Physical Tuya repeat-report/measurement discrimination, real same-device bindings, source cadence/temperature safety calibration, real return-probe/OEM limits, thermostat ACK/readback and watchdog arbitration remain unqualified. G1/B01–B08 remain BLOCKED. No production, equipment, legacy repository, network binding, real actuator, notification sender or WP2D work.

## Focused verification

- `python -m mypy`:40 source files PASS.
- `python -m unittest tests.wp2c_revision.test_source_activity tests.wp2c_revision.test_health tests.wp2c_revision.test_health_backend tests.wp2c_backend.test_backend.NativeFenceTests -q`:40 PASS, including14 new source-activity tests.
- Focused branch coverage of `packages.ha_native.source_activity`:100% statements/branches, unchanged95% threshold.
- Frontend TypeScript check PASS; `vitest run tests/systemHealth.test.tsx tests/native.test.ts`:50 PASS (three new UI/contract tests).
- Prior tests retained; no manual full suite/CI run and no broad audit. Full matrix/native compatibility remains for the automatically triggered PR checks and independent review.
