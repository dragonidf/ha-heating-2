# Issue27 — compact health and proposed fallback (synthetic only)

Base: current main after merged PR26. Existing Snapshot/SourceAdapter, native monotonic clock/timer, VoltagePolicy/feed readiness, STOP/owner fencing, separate evidence/critical stores and #26 thermostat-local withdrawal remain authoritative. No room-model, forecast, fireplace policy or physical actuation implementation was replaced.

Added: one six-component typed health projection on the existing native Snapshot, a compact expandable Home card, transition/reason/age metadata, source-report provenance, durable fallback/operator latch and inspectable idempotent proposal receipt and synthetic proposed AUTO/HEAT intents. The exact living-room source remains model/chart authority. Thermostat metadata is only for contact-demand qualification; fireplace metadata only describes fireplace/circulation. Neither replaces missing living-room observations. An accepted direct report/heartbeat proves reporting activity separately from measurement freshness; a stale observation cannot become a fresh model measurement solely from that heartbeat.

HealthPolicy defaults are synthetic:10800s room report silence,30s recovery,60s cold grace,30s notification cooldown, with bounded constructor configuration.10800s is the conservative proposal from Issue27's limited sample, not a physically validated timeout. It only applies to confirmed report-age provenance. Existing model/source freshness configuration is not silently overwritten. Missing provenance is WAITING/UNKNOWN; same temperature is not a disconnect. A single new verified usable report plus recovery time suffices; two hourly reports are not required.

Priority: STOP/operator override/revocation latches first; known electrical/KWS inhibit next; source failover last. Room silence and qualified supply/thermostat/owner produce one idempotent proposed AUTO without modifying weekly programming. Fault/unknown supply never produces AUTO; a qualified #26 HEAT withdrawal is preserved, otherwise CRITICAL cannot-confirm is visible. Qualified recovery, plan/one-shot/owner gates and continuous stability produce a proposed HEAT takeover. Restart preserves ownership/alarm/latch, while restarting recovery dwell. Notifications are transition-only, deduplicated, cooldown-queued and persisted; UI retains the last notice. No Telegram or other real notification is sent.

**Explicit gap:** there is no commissioned thermostat owner/ACK/readback source for these transitions. HealthInputs is a trusted synthetic evidence injection seam; native defaults keep thermostat, fireplace, owner and plan qualification unknown rather than inventing them. AUTO/HEAT are therefore **proposed intents only**, not executed commands or proof of thermostat mode/contact state. The existing native room/electrical guards still decide eligibility independently; this health feature cannot authorize physical heat. Real bindings, validated per-source reporting policy, acknowledgement/execution and explicit operator-reset handoff require independent review/commissioning. The general independent controller-crash watchdog AUTO policy is unchanged; its arbitration with voltage safety remains B04/B05 handoff work. G1/B03/B04/B05 remain BLOCKED; no WP2D.

Focused validation:
- `python -m unittest tests.wp2c_revision.test_health tests.wp2c_revision.test_health_backend tests.wp2c_backend.test_clock tests.wp2c_backend.test_voltage_integration tests.wp2c_backend.test_settings_revision -q`:31 PASS.
- `npm run typecheck`:PASS.
- `npx vitest run tests/systemHealth.test.tsx tests/native-ui.test.tsx --reporter=dot`:11 PASS.
- `git diff --check`:PASS.

No general audit or manual full-CI execution/polling. Draft implementation/self-tests only; independent acceptance pending.
