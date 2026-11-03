"""Pure slices of T-S01/S03-S09/S11-S14, T-P02/P07/P10/P12."""
import unittest
from dataclasses import replace

from packages.contracts import (
    Action, ControlMode, ControlState, EventKind, Quality, QualityStatus,
    Reason, RuntimeMode, Unit,
)
from packages.control import assess_intent, reduce
from tests.fixtures.synthetic import clock, event, plan, policy, reading, snapshot, state


class SafetyTests(unittest.TestCase):
    def decide(self, s=None, e=None, snap=None, p=None, now=None):
        return reduce(s or state(), e or event(), snap or snapshot(),
                      p or policy(), now or clock())

    def test_valid_plan_creates_a_description_not_a_physical_receipt(self):
        result = self.decide()
        self.assertTrue(result.permit.allowed)
        self.assertEqual(result.state.mode, RuntimeMode.AUTO_PLAN)
        self.assertEqual([i.action for i in result.intents], [Action.HEAT])
        self.assertIsNone(result.state.last_receipt)
        self.assertEqual(self.decide(), result)

    def test_permissions_modes_and_unqualified_limits_deny_new_heat(self):
        cases = [dict(armed=False), dict(allow_automatic=False),
                 dict(configuration_valid=False), dict(limits_qualified=False),
                 dict(room_upper_c=None), dict(return_upper_c=None),
                 *[dict(operating_mode=m) for m in ControlMode if m is not ControlMode.AUTO]]
        for changes in cases:
            with self.subTest(changes=changes):
                result = self.decide(p=policy(**changes))
                self.assertFalse(result.permit.allowed)
                self.assertNotIn(Action.HEAT, [i.action for i in result.intents])

    def test_unknown_grid_is_not_authorized_by_forecast(self):
        for actual in (None, reading(False, Unit.BOOLEAN), reading(None, Unit.BOOLEAN)):
            for forecast in (None, True, False):
                with self.subTest(actual=actual, forecast=forecast):
                    result = self.decide(snap=snapshot(grid_actual=actual, forecast_grid=forecast))
                    self.assertFalse(result.permit.allowed)

    def test_required_readings_cannot_be_refreshed_by_receipt_time(self):
        for role in ("room", "return_temperature", "thermostat", "grid_actual"):
            original = getattr(snapshot(), role)
            for bad in (None, replace(original, observed_at=1, received_at=100),
                        replace(original, observed_at=103),
                        replace(original, quality=Quality(status=QualityStatus.STALE,
                                                         age_s=0, reason="stale"))):
                with self.subTest(role=role, bad=bad):
                    self.assertFalse(self.decide(snap=snapshot(**{role: bad})).permit.allowed)

    def test_upper_and_qualified_return_safety_stop_bypass_min_on(self):
        heated = self.decide().state
        for changes in (dict(room=reading(30, Unit.CELSIUS)),
                        dict(return_temperature=reading(45, Unit.CELSIUS)),
                        dict(grid_actual=reading(False, Unit.BOOLEAN)), dict(hard_stop=True),
                        dict(scheduled_outage=True)):
            result = self.decide(heated, event(sequence=2), snapshot(**changes))
            self.assertEqual(result.state.desired_action, Action.STOP)
            self.assertEqual([i.action for i in result.intents], [Action.STOP])

    def test_min_off_and_soft_stop_hold_do_not_override_safety(self):
        self.assertEqual(self.decide(s=state(changed_at_monotonic=999)).permit.reason, Reason.MIN_OFF)
        heated = self.decide().state
        held = self.decide(heated, event(sequence=2, kind=EventKind.STOP_REQUEST))
        self.assertEqual(held.state.desired_action, Action.HEAT)
        stopped = self.decide(heated, event(sequence=2, kind=EventKind.SAFETY_STOP, authorized=True))
        self.assertEqual(stopped.state.desired_action, Action.STOP)

    def test_segment_end_and_plan_expiry_do_not_wait_for_min_on(self):
        for at in (110.0, 200.0):
            heated = self.decide().state
            now = clock(utc=at, monotonic=1000 + at - 100)
            snap = snapshot(captured_at=at, room=reading(18, Unit.CELSIUS, observed_at=at),
                            return_temperature=reading(25, Unit.CELSIUS, observed_at=at),
                            thermostat=reading(19, Unit.CELSIUS, observed_at=at),
                            grid_actual=reading(True, Unit.BOOLEAN, observed_at=at))
            result = self.decide(heated, event(sequence=2, at=at, expires_at=at+1), snap, now=now)
            self.assertEqual(result.state.desired_action, Action.STOP)

    def test_plan_hash_revisions_and_epochs_must_all_match(self):
        candidates = [replace(plan(), input_hash="b"*64), replace(plan(), owner_epoch=6),
                      replace(plan(), grid_epoch=10), replace(plan(), boot_id="synthetic.other"),
                      replace(plan(), revisions=replace(plan().revisions, topology=9))]
        for p in candidates:
            with self.subTest(plan=p):
                self.assertFalse(self.decide(s=state(plan=p)).permit.allowed)

    def test_replay_clock_rollback_and_boot_mismatch_cannot_create_heat(self):
        for e, now in ((event(sequence=0), clock()),
                       (event(at=98), clock()),
                       (event(), clock(monotonic=989)),
                       (event(boot_id="synthetic.old"), clock()),
                       (event(owner_epoch=4), clock()),
                       (event(expires_at=100), clock())):
            result = self.decide(e=e, now=now)
            self.assertFalse(result.permit.allowed)
            self.assertFalse(result.intents)

    def test_startup_requires_explicit_reconciliation(self):
        cold = ControlState(boot_id=clock().boot_id, owner_epoch=5)
        self.assertFalse(self.decide(s=cold).permit.allowed)
        reconciled = self.decide(s=cold, e=event(kind=EventKind.RECONCILE),
                                p=policy(min_off_s=0))
        self.assertEqual(reconciled.state.desired_action, Action.STOP)
        self.assertIsNone(reconciled.state.plan)

    def test_shadow_has_zero_intents_even_on_explicit_safety_stop(self):
        result = self.decide(e=event(kind=EventKind.SAFETY_STOP, authorized=True),
                             p=policy(operating_mode=ControlMode.SHADOW))
        self.assertEqual(result.state.mode, RuntimeMode.SHADOW)
        self.assertEqual(result.intents, ())
