# Issue33 — dynamic final HEAT backup ceiling

Base: main `e1b6cdc0b1a36c5973b704c2a9c63410858c6803`, after merged PR32.
Owner specification: https://github.com/dragonidf/ha-heating-2/issues/33 . Synthetic intents only; no production reads/writes, actuator, physical ACK or legacy changes.

## Effective limit, not a second comfort controller

`ActiveRoomLimit` is a trusted effective-planner context: source mode, actual selected room upper, separate comfort/plan target, qualification and owner-configurable reserve margin (default2.5°C). NativeBackend reads its `effective_room_limit` provider on every evaluation. It must come from the effective planner selection (e.g. active Slot.upper/target), including day/night/allowed-hours/override, rather than raw wall-clock inference or the UI's comfort target masquerading as an upper limit. The default provider is unknown; no physical helper/entity binding is guessed. Upper and margin changes are visible on the next evaluation without reboot; margin is not learned/adapted from uncertain temperature pairs.

`raw_ceiling = Decimal(active_upper) + Decimal(reserve_margin)`. The supported ceiling is floored to the qualified thermostat0.5°C lattice anchored at its minimum and capped by its maximum. Decimal arithmetic prevents boundary rounding above the limit. Unknown/incompatible bounds, unrepresentable ceiling and unsupported step produce a diagnostic, never a target claimed safe.

The final native formatting seam is `heat_setpoint_intent`. Every positive intent is floored/capped at that ceiling and must still exceed the thermostat's **uncorrected** own temperature. It requires independent planner demand, valid living-room source, owner epoch/ownership, current plan and persistence, one-shot eligibility, voltage/KWS/grid and manual/override guards. The ceiling supplies no permission itself. No `current_temperature+2.5 >= target` rule or thermostat-to-room correction exists.

When the room reaches its separate comfort target/upper, planner withdraws demand, an electrical/KWS gate inhibits, or no supported ON target exists, the finalizer proposes withdrawal through the **same extracted helper already used by voltage withdrawal**. Its setpoint must be supported and at least one full step below thermostat-local temperature, while also respecting the ceiling. If this is impossible or thermostat evidence is stale/missing, there is no invented OFF: a cannot-confirm diagnostic has no setpoint/ACK. STOP/override/unowned/stale-epoch requests produce no competing command. Vendor AUTO is diagnostic-only here; its independent weekly program is not claimed to obey a manual HEAT ceiling. The existing fallback/watchdog policy is unchanged.

## Dynamics, persistence and one writer

A changed effective context invalidates the previous proposal and advances the existing owner/durability fence. The view immediately recalculates the limit, but a stale pre-change intent cannot be reused; new positive demand waits for the current critical snapshot to reconcile. This also covers a lower upper while HEAT was pending. No second writer, service route, public client-controlled qualification flag, plan selector or alternative settings schema was added.

The optional snapshot view shows effective mode/upper, configured margin, raw/supported ceiling, current proposal, thermostat freshness and source of withdrawal. A proposal is **not an applied thermostat target**: acknowledged_setpoint is always null; physical_ack/physical_authority are always false. Superseded/stale/STOP proposals are hidden. Restart clears cached thermostat/proposal evidence and still requires new source qualification. The view is additive to the existing six-component panel and never replaces living-room model/history/forecast measurements.

## Focused verification

- Strict mypy:42 source files PASS.
-26 Python tests PASS: `tests.wp2c_revision.test_thermostat_ceiling`, `tests.wp2c_backend.test_voltage_integration`, `tests.wp2c_boundaries.test_boundary` (14 new ceiling tests).
- Frontend TypeScript PASS;52 related tests PASS: `systemHealth.test.tsx`, `native.test.ts` (one new diagnostic/contract test).
- Covers22.0→24.5,21.5→24.0, live day22→23/max24.5→25.5 and night21.5→22/max24→24.5; day/night/allowed-hour switching; target-vs-upper distinction; configurable margin;0.1°C upper and device bounds; lowered pending target; local bias/at-ceiling behavior; safe/no-safe withdrawal; humidity/stale primary; STOP, KWS delay, low voltage, stale thermostat/AUTO, one-shot, restart, persistence failure and rollback; no physical ACK or contact assertion. Prior voltage withdrawal regressions retained unchanged.
- No broad audit, manual full suite/workflow trigger or automatic merge. Full automatic PR checks remain independent evidence.

## Remaining physical blockers

Effective active-upper/plan and thermostat metadata must be privately bound and qualified before live use. The synthetic provider seam demonstrates live updates; it is not a commissioned subscription to household helpers and adds no public HA mapping. The margin is a configurable owner design input, not a certified bound on sensor bias. Device capability/current-temperature provenance, real setpoint writer/permissions/ACK/readback, single-writer legacy/watchdog/fan handoff, OEM/KWS independent limits, rollback and native2026.11.0/physical acceptance remain unqualified. G1/B01–B08 remain BLOCKED. An owned, physically verified backup path on stale room data is not authorized by this ceiling; stale room remains fail-closed. No vendor AUTO ceiling guarantee is made.
