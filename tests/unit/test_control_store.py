"""All database files are disposable synthetic sandbox artifacts."""
import tempfile
import unittest
from pathlib import Path

from packages.contracts import Action, EventKind, OneShot, OneShotKind, OneShotOutcome
from packages.control import reduce
from packages.control_store.store import ControlStore, StoreConflict, StoreFailure
from tests.fixtures.synthetic import clock, event, policy, snapshot, state


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ControlStore.create(self.root, state(), policy())

    def test_state_settings_and_transaction_receipt_survive_reopen(self):
        before = self.store.view()
        decision = reduce(before.state, event(), snapshot(), before.policy, clock())
        committed = self.store.transition(event(), decision, before.revision)
        reopened = ControlStore(self.root).view()
        self.assertEqual(committed, reopened)
        self.assertEqual(reopened.state.desired_action, Action.HEAT)
        self.assertEqual(self.store.pragmas(), ("wal", 2))

    def test_stale_revision_and_owner_cannot_overwrite_manual_pause(self):
        before = self.store.view()
        manual_event = event(kind=EventKind.MANUAL_CHANGE)
        manual = reduce(before.state, manual_event, snapshot(), before.policy, clock())
        saved = self.store.transition(manual_event, manual, before.revision)
        with self.assertRaises(StoreConflict):
            self.store.transition(event(), reduce(before.state, event(), snapshot(), policy(), clock()), before.revision)
        restarted = self.store.restart("synthetic.new-boot")
        self.assertTrue(restarted.state.manual_paused)
        self.assertFalse(restarted.state.reconciled)
        self.assertEqual(restarted.state.desired_action, Action.STOP)
        self.assertGreater(restarted.state.owner_epoch, saved.state.owner_epoch)

    def test_prepare_claim_is_once_and_restart_never_replays_heat(self):
        before = self.store.view()
        decision = reduce(before.state, event(), snapshot(), policy(), clock())
        saved = self.store.transition(event(), decision, before.revision)
        intent = decision.intents[0]
        self.store.prepare(intent, snapshot(), clock(), saved.revision)
        self.store.claim(intent, saved.state, snapshot(), clock())
        with self.assertRaises(StoreConflict):
            self.store.claim(intent, saved.state, snapshot(), clock())
        reboot = self.store.restart("synthetic.reboot")
        self.assertIsNone(reboot.state.plan)
        self.assertEqual(reboot.state.desired_action, Action.STOP)
        self.assertEqual(self.store.receipt(intent.intent_id).stage.value, "unknown")

    def test_one_shot_consumption_precedes_send_and_unknown_cannot_be_consumed_twice(self):
        shot = OneShot(intent_id="synthetic.once", kind=OneShotKind.HEAT_AFTER_GRID_RESTORE,
                       created_at=90, expires_at=200, armed_grid_epoch=4, consumed_at=None,
                       outcome=OneShotOutcome.PENDING)
        self.store.register_one_shot(shot)
        before = self.store.view()
        decision = reduce(before.state, event(), snapshot(), policy(), clock())
        saved = self.store.transition(event(), decision, before.revision)
        self.store.prepare(decision.intents[0], snapshot(), clock(), saved.revision, one_shot_id=shot.intent_id)
        self.assertEqual(self.store.one_shot(shot.intent_id).outcome, OneShotOutcome.CONSUMED)
        self.store.restart("synthetic.once-reboot")
        self.assertEqual(self.store.one_shot(shot.intent_id).outcome, OneShotOutcome.UNKNOWN)
        self.assertEqual(self.store.one_shot(shot.intent_id).consumed_at, 100)

    def test_no_silent_creation_or_non_sandbox_path(self):
        with self.assertRaises(StoreFailure):
            ControlStore(Path("/workspace"))
        with self.assertRaises(StoreFailure):
            ControlStore(self.root / "missing")
