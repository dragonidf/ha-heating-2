import unittest
from dataclasses import replace

from packages.contracts import Action, ControlMode, ControlState, EventKind, PlanSegment, RuntimeMode
from packages.control import evaluate, reduce
from tests.fixtures.synthetic import clock, event, plan, policy, snapshot, state


class TransitionTests(unittest.TestCase):
    def test_every_runtime_mode_is_reachable_in_the_pure_slice(self):
        cases = (
            (ControlState(boot_id="synthetic.boot", owner_epoch=5), event(), snapshot(), policy()),
            (state(), event(), snapshot(), policy(operating_mode=ControlMode.SHADOW)),
            (state(), event(), snapshot(), policy()),
            (state(), event(), snapshot(compute_available=False), policy()),
            (state(plan=None), event(), snapshot(), policy()),
            (state(), event(kind=EventKind.MANUAL_CHANGE), snapshot(), policy()),
            (state(), event(kind=EventKind.OFF), snapshot(), policy()),
            (state(), event(), snapshot(hard_stop=True), policy()),
        )
        modes = {reduce(s, e, snap, p, clock()).state.mode for s, e, snap, p in cases}
        self.assertEqual(modes, set(RuntimeMode))

    def test_snapshot_boot_mismatch_denies_and_missing_switch_time_needs_min_off(self):
        self.assertFalse(evaluate(state(), snapshot(boot_id="synthetic.old"), policy(), clock()).allowed)
        self.assertFalse(evaluate(state(changed_at_monotonic=None), snapshot(), policy(), clock()).allowed)

    def test_future_segment_and_expired_plan_never_issue_heat(self):
        for candidate in (plan(segments=(PlanSegment(start=101, end=110),)),
                          plan(valid_until=100, expires_at=100, segments=())):
            result = reduce(state(plan=candidate), event(), snapshot(), policy(), clock())
            self.assertFalse(result.permit.allowed)
            self.assertEqual(result.state.desired_action, Action.STOP)

    def test_soft_stop_after_minimum_on_stops_immediately(self):
        result = reduce(state(desired_action=Action.HEAT), event(kind=EventKind.STOP_REQUEST),
                        snapshot(), policy(), clock())
        self.assertEqual(result.state.desired_action, Action.STOP)
        self.assertFalse(result.permit.allowed)
