"""Synthetic reproductions of PR #6 review comment 6605790334."""
import unittest
from dataclasses import replace
from math import inf, nextafter

from packages.contracts import (
    Action, ControlMode, EventKind, PlanSegment, QualityStatus, Reason, TimeWindow, Unit,
    from_json, to_json,
)
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, plan, policy, reading, snapshot, state
from tests.unit.test_recovery import fresh


def asynchronous_case(at=20_000, room_age=60):
    """Independent clocks/cadences are invented premises, not household settings."""
    values = {}
    for role, value, unit, age in (("room", 18, Unit.CELSIUS, room_age),
                                   ("return_temperature", 25, Unit.CELSIUS, 10),
                                   ("thermostat", 19, Unit.CELSIUS, 20),
                                   ("grid_actual", True, Unit.BOOLEAN, 0)):
        r = reading(value, unit, physical_id=f"synthetic.{role}",
                    observed_at=at-age, received_at=at-age)
        values[role] = replace(r, quality=replace(r.quality, age_s=age))
    s = snapshot(captured_at=at, **values)
    p = policy(room_max_age_s=14_400, return_max_age_s=20, thermostat_max_age_s=30,
               grid_max_age_s=3, snapshot_max_age_s=5, max_skew_s=2,
               strict_windows=(TimeWindow(start=at-100, end=at+200),))
    candidate = plan(issued_at=at-100, valid_from=at-100, valid_until=at+200,
                     expires_at=at+300, segments=(PlanSegment(start=at, end=at+200),))
    initial = state(last_event_at=at-1, plan=candidate)
    e = event(at=at, expires_at=at+1)
    return initial, e, s, p, clock(utc=at)


class ReviewRegressionTests(unittest.TestCase):
    def test_valid_slow_room_and_fast_grid_use_independent_freshness(self):
        args = asynchronous_case()
        result = reduce(*args)
        self.assertTrue(result.permit.allowed)
        self.assertEqual(result.intents[0].action, Action.HEAT)
        self.assertEqual(args[3].max_skew_s, 2)
        self.assertEqual(result, reduce(*args))

    def test_trusted_expired_reordered_safety_stop_overrides_current_heat(self):
        heated = reduce(state(), event(), snapshot(), policy(), clock()).state
        heated = replace(heated, last_event_sequence=20, changed_at_monotonic=999.9)
        stop = event(kind=EventKind.SAFETY_STOP, authorized=True, sequence=2, at=99, expires_at=99.5)
        result = reduce(heated, stop, snapshot(hard_stop=False), policy(), clock())
        self.assertEqual(result.state.desired_action, Action.STOP)
        self.assertEqual(result.permit.reason, Reason.HARD_STOP)
        self.assertEqual(result.intents[0].action, Action.STOP)
        self.assertIsNone(result.state.plan)
        self.assertEqual(result.state.owner_epoch, heated.owner_epoch)

    def test_failure_time_plan_cannot_be_readmitted_as_new(self):
        fallback = reduce(state(plan=None, accepted_input_hash=None), event(), snapshot(), policy(), clock()).state
        coincident = plan(issued_at=100, valid_from=100)
        proposed = event(kind=EventKind.PLAN, plan=coincident, sequence=2, at=105, expires_at=106)
        result = reduce(fallback, proposed, fresh(105), policy(), clock(utc=105, monotonic=1005))
        self.assertFalse(result.permit.allowed)
        self.assertEqual(result.permit.reason, Reason.RECOVERY)
        self.assertFalse(any(i.action is Action.HEAT for i in result.intents))

    def test_each_source_freshness_boundary_is_independent_of_clock_skew(self):
        roles = (("room", "room_max_age_s", 14_400),
                 ("return_temperature", "return_max_age_s", 20),
                 ("thermostat", "thermostat_max_age_s", 30),
                 ("grid_actual", "grid_max_age_s", 3))
        for role, limit_name, limit in roles:
            for age in (limit, limit + 0.001):
                with self.subTest(role=role, age=age):
                    initial, e, s, p, now = asynchronous_case()
                    source = getattr(s, role)
                    frozen_metadata = replace(source.quality, age_s=0)
                    source = replace(source, observed_at=now.utc-age, received_at=now.utc,
                                     quality=frozen_metadata)
                    result = reduce(initial, e, replace(s, **{role: source}), p, now)
                    self.assertEqual(getattr(p, limit_name), limit)
                    self.assertEqual(result.permit.allowed, age == limit)
                    self.assertEqual(p.max_skew_s, 2)

    def test_future_clock_tolerance_does_not_expand_for_slow_sources(self):
        for ahead in (2, 2.001):
            with self.subTest(ahead=ahead):
                initial, e, s, p, now = asynchronous_case()
                source = replace(s.room, observed_at=now.utc+ahead, received_at=now.utc+ahead,
                                 quality=replace(s.room.quality, age_s=0))
                result = reduce(initial, e, replace(s, room=source), p, now)
                self.assertEqual(result.permit.allowed, ahead == 2)

    def test_snapshot_cut_cannot_include_a_measurement_from_its_future(self):
        initial, e, s, p, now = asynchronous_case()
        s = replace(s, captured_at=now.utc-3,
                    grid_actual=replace(s.grid_actual, received_at=now.utc-1))
        # Clock-fresh grid data still lies beyond this snapshot's as-of tolerance.
        self.assertFalse(reduce(initial, e, s, p, now).permit.allowed)

    def test_frozen_observation_is_not_freshened_by_a_new_snapshot_or_receipt(self):
        _, _, old, _, _ = asynchronous_case()
        initial, e, current, p, now = asynchronous_case(at=20_100)
        frozen = replace(old.room, received_at=now.utc, quality=replace(old.room.quality, age_s=0))
        result = reduce(initial, e, replace(current, room=frozen), replace(p, room_max_age_s=120), now)
        self.assertEqual(result.permit.reason, Reason.READING)
        self.assertFalse(result.permit.allowed)
        self.assertEqual(frozen.observed_at, old.room.observed_at)

    def test_async_valid_readings_still_enforce_actual_grid_and_upper_limits(self):
        initial, e, s, p, now = asynchronous_case()
        cases = ((replace(s, grid_actual=replace(s.grid_actual, value=False), forecast_grid=True), Reason.GRID),
                 (replace(s, room=replace(s.room, value=30)), Reason.UPPER),
                 (replace(s, return_temperature=replace(s.return_temperature, value=45)), Reason.RETURN_UPPER))
        for snap, reason in cases:
            with self.subTest(reason=reason):
                result = reduce(initial, e, snap, p, now)
                self.assertFalse(result.permit.allowed)
                self.assertEqual(result.permit.reason, reason)

    def test_estimated_reading_is_not_promoted_to_valid_to_enable_heat(self):
        initial, e, s, p, now = asynchronous_case()
        estimate = replace(s.room, quality=replace(s.room.quality, status=QualityStatus.ESTIMATED))
        result = reduce(initial, e, replace(s, room=estimate), p, now)
        self.assertFalse(result.permit.allowed)
        self.assertEqual(estimate.quality.status, QualityStatus.ESTIMATED)

    def test_untrusted_stop_cannot_stop_safe_heat_or_advance_any_frontier(self):
        heated = reduce(state(), event(), snapshot(), policy(), clock()).state
        untrusted = event(kind=EventKind.SAFETY_STOP, sequence=1_000_000, authorized=False)
        result = reduce(heated, untrusted, snapshot(), policy(), clock())
        self.assertEqual(result.state, heated)
        self.assertEqual(result.intents, ())
        self.assertEqual(result.permit.reason.value, "safety_stop_not_authorized")

    def test_trusted_stop_requires_current_boot_owner_and_nonfuture_assertion(self):
        heated = reduce(state(), event(), snapshot(), policy(), clock()).state
        for changes in (dict(boot_id="synthetic.old"), dict(owner_epoch=4), dict(at=103, expires_at=104)):
            with self.subTest(changes=changes):
                stop = event(kind=EventKind.SAFETY_STOP, authorized=True, sequence=2, **changes)
                result = reduce(heated, stop, snapshot(), policy(), clock())
                self.assertEqual(result.state, heated)
                self.assertEqual(result.intents, ())

    def test_trusted_stop_replay_after_recovery_cannot_reassert_authority(self):
        heated = reduce(state(), event(), snapshot(), policy(), clock()).state
        stop = event(kind=EventKind.SAFETY_STOP, authorized=True, sequence=0, at=99, expires_at=99.5)
        stopped = reduce(heated, stop, snapshot(), policy(), clock()).state
        self.assertEqual(stopped.last_safety_stop_sequence, 0)
        healthy = reduce(stopped, event(sequence=2, at=101, expires_at=102), fresh(101),
                         policy(), clock(utc=101, monotonic=1001)).state
        during_recovery = reduce(healthy, stop, fresh(101), policy(), clock(utc=101, monotonic=1001))
        self.assertEqual(during_recovery.state, healthy)
        new_plan = plan(issued_at=101, valid_from=101, segments=(PlanSegment(start=101, end=110),))
        resumed = reduce(healthy, event(kind=EventKind.PLAN, plan=new_plan, sequence=3, at=105, expires_at=106),
                         fresh(105), policy(), clock(utc=105, monotonic=1005))
        self.assertTrue(resumed.permit.allowed)
        replay = reduce(resumed.state, stop, fresh(105), policy(), clock(utc=105, monotonic=1005))
        self.assertEqual(replay.state, resumed.state)
        self.assertEqual(replay.intents, ())

    def test_current_safety_still_applies_when_an_untrusted_stop_is_rejected(self):
        heated = reduce(state(), event(), snapshot(), policy(), clock()).state
        result = reduce(heated, event(kind=EventKind.SAFETY_STOP, authorized=False),
                        snapshot(hard_stop=True), policy(), clock())
        self.assertEqual(result.state.desired_action, Action.STOP)
        self.assertEqual(result.permit.reason, Reason.HARD_STOP)

    def test_trusted_emergency_in_shadow_has_no_intent_and_preserves_manual_latch(self):
        initial = state(manual_paused=True)
        stop = event(kind=EventKind.SAFETY_STOP, authorized=True, sequence=0, at=99, expires_at=99.5)
        result = reduce(initial, stop, snapshot(), policy(operating_mode=ControlMode.SHADOW), clock())
        self.assertTrue(result.state.manual_paused)
        self.assertEqual(result.intents, ())
        self.assertEqual(result.state.last_safety_stop_sequence, 0)
        self.assertEqual(from_json(to_json(result)), result)

    def test_old_owner_stop_cannot_affect_new_manual_authority(self):
        manual = reduce(state(), event(kind=EventKind.MANUAL_CHANGE), snapshot(), policy(), clock()).state
        old_stop = event(kind=EventKind.SAFETY_STOP, authorized=True, sequence=100)
        ignored = reduce(manual, old_stop, snapshot(owner_epoch=6), policy(), clock())
        self.assertEqual(ignored.state, manual)
        self.assertEqual(ignored.intents, ())
        current_stop = replace(old_stop, owner_epoch=6, sequence=0)
        stopped = reduce(manual, current_stop, snapshot(owner_epoch=6), policy(), clock())
        self.assertTrue(stopped.state.manual_paused)
        self.assertEqual(stopped.state.owner_epoch, 6)
        self.assertEqual(stopped.state.desired_action, Action.STOP)

    def test_recovery_issue_time_boundary_uses_strictly_later_timestamp(self):
        fallback = reduce(state(plan=None, accepted_input_hash=None), event(), snapshot(), policy(), clock()).state
        for issued in (nextafter(100, -inf), 100, nextafter(100, inf), 101):
            with self.subTest(issued=issued):
                proposal = plan(issued_at=issued, valid_from=issued, segments=(PlanSegment(start=101, end=110),))
                result = reduce(fallback, event(kind=EventKind.PLAN, plan=proposal, sequence=2, at=105, expires_at=106),
                                fresh(105), policy(), clock(utc=105, monotonic=1005))
                self.assertEqual(result.permit.allowed, issued > 100)
                if issued <= 100:
                    self.assertEqual(result.permit.reason, Reason.RECOVERY)
