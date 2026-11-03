"""Synthetic event-order and authority regressions; no device or sender."""
import unittest
from dataclasses import replace

from packages.contracts import (
    Action, CommandReceipt, EventKind, ReceiptStage, Reason, RuntimeMode, Unit,
)
from packages.control import assess_intent, reduce
from tests.fixtures.synthetic import clock, event, plan, policy, reading, snapshot, state


def step(s, e, snap=None, now=None, p=None):
    return reduce(s, e, snap or snapshot(), p or policy(), now or clock())


def receipt(intent, **changes):
    values = dict(intent_id=intent.intent_id, boot_id=intent.boot_id,
                  owner_epoch=intent.owner_epoch, sequence=intent.sequence,
                  action=intent.action, stage=ReceiptStage.ECHOED,
                  requested_at=100, device_echo_at=100)
    return CommandReceipt(**(values | changes))


class OwnershipTests(unittest.TestCase):
    def test_manual_change_during_pending_command_has_no_automatic_stop_or_reclaim(self):
        heated = step(state(), event()).state
        paused = step(heated, event(kind=EventKind.MANUAL_CHANGE, sequence=2)).state
        self.assertTrue(paused.manual_paused)
        self.assertEqual(paused.owner_epoch, 6)
        old = receipt(heated.last_intent)
        late = step(paused, event(kind=EventKind.OWN_ECHO, receipt=old, sequence=3),
                    snapshot(owner_epoch=6))
        self.assertEqual(late.state.mode, RuntimeMode.MANUAL_PAUSE)
        self.assertTrue(late.state.manual_paused)
        self.assertFalse(late.intents)
        tick = step(paused, event(owner_epoch=6, sequence=4), snapshot(owner_epoch=6))
        self.assertTrue(tick.state.manual_paused)
        self.assertFalse(tick.intents)

    def test_old_echo_is_ignored_without_false_manual_pause(self):
        heated = step(state(), event()).state
        old = receipt(heated.last_intent, intent_id="synthetic.old-intent")
        result = step(heated, event(kind=EventKind.OWN_ECHO, receipt=old, sequence=2))
        self.assertFalse(result.state.manual_paused)
        self.assertEqual(result.state.owner_epoch, heated.owner_epoch)
        self.assertFalse(result.intents)

    def test_explicit_off_latches_and_unauthorized_resume_cannot_release_it(self):
        off = step(state(), event(kind=EventKind.OFF)).state
        self.assertTrue(off.off_latched)
        denied = step(off, event(kind=EventKind.RESUME, owner_epoch=6, sequence=2),
                      snapshot(owner_epoch=6))
        self.assertTrue(denied.state.off_latched)
        resumed = step(off, event(kind=EventKind.RESUME, owner_epoch=6, sequence=2, authorized=True),
                       snapshot(owner_epoch=6))
        self.assertFalse(resumed.state.off_latched)
        self.assertFalse(resumed.state.reconciled)
        self.assertIsNone(resumed.state.plan)
        self.assertEqual(resumed.state.owner_epoch, 7)
        self.assertFalse(resumed.intents)

    def test_unknown_actuator_causation_pauses_instead_of_inventing_an_own_echo(self):
        result = step(state(), event(kind=EventKind.UNKNOWN_CHANGE))
        self.assertTrue(result.state.manual_paused)
        self.assertFalse(result.intents)

    def test_ack_and_echo_never_become_physical_success(self):
        heated = step(state(), event()).state
        ack = receipt(heated.last_intent, stage=ReceiptStage.ACKNOWLEDGED,
                      device_echo_at=None, ha_ack_at=100)
        result = step(heated, event(kind=EventKind.OWN_ECHO, sequence=2, receipt=ack))
        self.assertEqual(result.state.last_receipt.stage, ReceiptStage.ACKNOWLEDGED)
        self.assertIsNone(result.state.last_receipt.physical_effect_at)
        echo = step(result.state, event(kind=EventKind.OWN_ECHO, sequence=3,
                                       receipt=receipt(heated.last_intent)))
        self.assertEqual(echo.state.last_receipt.stage, ReceiptStage.ECHOED)
        self.assertIsNone(echo.state.last_receipt.physical_effect_at)

    def test_failed_or_mismatched_current_echo_stops_and_invalidates_plan(self):
        heated = step(state(), event()).state
        for change in (dict(stage=ReceiptStage.FAILED), dict(stage=ReceiptStage.UNKNOWN),
                       dict(action=Action.STOP)):
            result = step(heated, event(kind=EventKind.OWN_ECHO, sequence=2,
                                       receipt=receipt(heated.last_intent, **change)))
            self.assertEqual(result.state.desired_action, Action.STOP)
            self.assertIsNone(result.state.plan)
            self.assertEqual(result.permit.reason, Reason.ECHO_MISMATCH)

    def test_duplicate_not_due_expired_and_wrong_epoch_intents_are_rejected(self):
        intent = step(state(), event()).intents[0]
        self.assertEqual(assess_intent(intent, clock(), 5, 0, snapshot().snapshot_id), Reason.ALLOWED)
        self.assertEqual(assess_intent(intent, clock(), 5, 1, snapshot().snapshot_id), Reason.DUPLICATE)
        for bad in (replace(intent, boot_id="synthetic.old"), replace(intent, owner_epoch=4)):
            self.assertEqual(assess_intent(bad, clock(), 5, 0, snapshot().snapshot_id), Reason.CLOCK)
        for bad in (replace(intent, not_before=101), replace(intent, expires_at=100.5)):
            self.assertEqual(assess_intent(bad, clock(utc=100.5), 5, 0, snapshot().snapshot_id),
                             Reason.INTENT_EXPIRED)

    def test_invalid_plan_or_stale_echo_cannot_mask_current_safety_stop(self):
        heated = step(state(), event()).state
        bad_plan = replace(plan(), owner_epoch=4)
        old_echo = receipt(heated.last_intent, intent_id="synthetic.old-intent")
        for e in (event(kind=EventKind.PLAN, plan=bad_plan, sequence=2),
                  event(kind=EventKind.OWN_ECHO, receipt=old_echo, sequence=2),
                  event(kind=EventKind.RESUME, sequence=2), event(sequence=0)):
            result = step(heated, e, snapshot(room=reading(30, Unit.CELSIUS)))
            self.assertEqual(result.state.desired_action, Action.STOP)
            self.assertEqual([i.action for i in result.intents], [Action.STOP])

    def test_current_hard_stop_overrides_even_manual_event_processing(self):
        heated = step(state(), event()).state
        result = step(heated, event(kind=EventKind.MANUAL_CHANGE, sequence=2),
                      snapshot(hard_stop=True))
        self.assertEqual([i.action for i in result.intents], [Action.STOP])

    def test_repeated_safe_tick_does_not_duplicate_an_intent(self):
        first = step(state(), event())
        again = step(first.state, event(sequence=2))
        self.assertEqual(again.intents, ())
        self.assertEqual(first.state.last_intent, again.state.last_intent)

    def test_live_input_hash_can_change_but_new_plan_admission_must_match(self):
        heated = step(state(), event()).state
        updated = snapshot(input_hash="c"*64)
        held = step(heated, event(sequence=2), updated)
        self.assertTrue(held.permit.allowed)
        invalid = step(heated, event(kind=EventKind.PLAN, plan=plan(), sequence=2), updated)
        self.assertEqual(invalid.permit.reason, Reason.PLAN)
