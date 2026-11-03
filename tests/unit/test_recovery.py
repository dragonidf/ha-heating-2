"""Bounded pure state recovery; no timers, retries, storage or native-auto sender."""
import unittest
from dataclasses import replace

from packages.contracts import Action, ControlMode, EventKind, PlanSegment, Reason, RuntimeMode, Unit
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, plan, policy, reading, snapshot, state


def fresh(at=100, **changes):
    values = dict(captured_at=at)
    for name, value, unit in (("room", 18, Unit.CELSIUS), ("return_temperature", 25, Unit.CELSIUS),
                              ("thermostat", 19, Unit.CELSIUS), ("grid_actual", True, Unit.BOOLEAN)):
        values[name] = reading(value, unit, observed_at=at, received_at=at)
    return snapshot(**(values | changes))


class RecoveryTests(unittest.TestCase):
    def run_step(self, s, at, seq, **changes):
        return reduce(s, event(at=at, expires_at=at+1, sequence=seq, **changes),
                      fresh(at), policy(), clock(utc=at, monotonic=900+at))

    def test_compute_loss_uses_only_an_unexpired_accepted_plan(self):
        result = reduce(state(), event(), snapshot(compute_available=False), policy(), clock())
        self.assertEqual(result.state.mode, RuntimeMode.AUTO_HOLD)
        self.assertEqual(result.intents[0].action, Action.HEAT)
        expired = self.run_step(result.state, 200, 2)
        self.assertFalse(expired.permit.allowed)
        self.assertEqual(expired.state.desired_action, Action.STOP)

    def test_intent_expiry_is_not_automatically_renewed(self):
        first = reduce(state(), event(), snapshot(), policy(), clock()).state
        stopped = self.run_step(first, 106, 2)
        self.assertEqual(stopped.permit.reason, Reason.INTENT_EXPIRED)
        self.assertEqual(stopped.state.desired_action, Action.STOP)
        again = self.run_step(stopped.state, 107, 3)
        self.assertFalse(again.permit.allowed)
        self.assertFalse(any(i.action is Action.HEAT for i in again.intents))

    def test_recovery_needs_stable_inputs_and_a_new_admitted_plan(self):
        fallback = reduce(state(plan=None, accepted_input_hash=None), event(), snapshot(), policy(), clock()).state
        self.assertEqual(fallback.mode, RuntimeMode.FALLBACK)
        old = self.run_step(fallback, 104, 2)
        self.assertFalse(old.permit.allowed)
        new_plan = plan(issued_at=101, valid_from=101, segments=(PlanSegment(start=101, end=110),))
        admitted = self.run_step(old.state, 104, 3, kind=EventKind.PLAN, plan=new_plan)
        self.assertTrue(admitted.permit.allowed)
        self.assertEqual(admitted.state.mode, RuntimeMode.AUTO_PLAN)

    def test_repeated_failure_does_not_reset_original_recovery_incident(self):
        s = state(plan=None, accepted_input_hash=None)
        first = self.run_step(s, 100, 1)
        second = self.run_step(first.state, 101, 2)
        self.assertEqual(second.state.recovery_at, 100)
        self.assertEqual(second.state.healthy_since, 1000)

    def test_new_plan_before_stability_deadline_remains_blocked(self):
        first = self.run_step(state(plan=None, accepted_input_hash=None, changed_at_monotonic=1000), 100, 1)
        candidate = plan(issued_at=101, valid_from=101, segments=(PlanSegment(start=101, end=110),))
        early = self.run_step(first.state, 101, 2, kind=EventKind.PLAN, plan=candidate)
        self.assertEqual(early.permit.reason, Reason.RECOVERY)
        ready = self.run_step(early.state, 103, 3)
        self.assertFalse(ready.permit.allowed)  # five-second minimum OFF still applies
        self.assertEqual(ready.permit.reason, Reason.MIN_OFF)
        ready = self.run_step(ready.state, 105, 4)
        self.assertTrue(ready.permit.allowed)

    def test_shadow_records_manual_authority_and_cannot_silently_rearm(self):
        shadow = reduce(state(), event(kind=EventKind.MANUAL_CHANGE), snapshot(),
                        policy(operating_mode=ControlMode.SHADOW), clock())
        self.assertEqual(shadow.state.mode, RuntimeMode.SHADOW)
        self.assertTrue(shadow.state.manual_paused)
        result = reduce(shadow.state, event(owner_epoch=6, sequence=2), snapshot(owner_epoch=6),
                        policy(), clock())
        self.assertEqual(result.state.mode, RuntimeMode.MANUAL_PAUSE)
        self.assertFalse(result.intents)

    def test_plan_issued_at_failure_time_still_needs_fresh_admission_after_fault(self):
        coincident = plan(issued_at=100, valid_from=100)
        initial = state(plan=coincident)
        failed = reduce(initial, event(), fresh(grid_actual=reading(False, Unit.BOOLEAN)), policy(), clock())
        self.assertIsNone(failed.state.plan)
        healthy = self.run_step(failed.state, 101, 2)
        later = self.run_step(healthy.state, 106, 3)
        self.assertFalse(later.permit.allowed)
        self.assertIsNone(later.state.plan)

    def test_monotonic_clock_failure_also_invalidates_previous_plan(self):
        failed = reduce(state(last_monotonic=1001, desired_action=Action.HEAT), event(),
                        snapshot(), policy(), clock())
        self.assertIsNone(failed.state.plan)
        self.assertEqual(failed.state.desired_action, Action.STOP)

    def test_inconsistent_snapshot_epoch_invalidates_previous_plan(self):
        failed = reduce(state(), event(), snapshot(boot_id="synthetic.old"), policy(), clock())
        self.assertIsNone(failed.state.plan)
