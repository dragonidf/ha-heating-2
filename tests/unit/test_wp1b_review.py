"""Regressions for independent review 6610149771; synthetic inputs only."""
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3

from packages.contracts import Action, EventKind, PlanSegment, ReceiptStage
from packages.control import reduce
from packages.control_store.store import ControlStore, StoreConflict, StoreFailure
from packages.simulator.engine import FakeActuator, Simulator
from tests.fixtures.synthetic import clock, event, plan, policy, reading, snapshot, state
from tests.unit.test_recovery import fresh
from tests.unit.test_simulator import ready_simulator


class ReviewRegressions(unittest.TestCase):
    def test_restart_preserves_each_historical_receipt_and_fences_delivery(self):
        for stage in (ReceiptStage.PREPARED, ReceiptStage.SENT, ReceiptStage.ACKNOWLEDGED,
                      ReceiptStage.ECHOED, ReceiptStage.PHYSICAL_EVIDENCE, ReceiptStage.FAILED, ReceiptStage.UNKNOWN):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
                root = Path(directory)
                store = ControlStore.create(root, state(), policy())
                d = reduce(state(), event(), snapshot(), policy(), clock())
                saved = store.transition(event(), d, 0)
                intent = d.intents[0]
                store.prepare(intent, snapshot(), clock(), saved.revision)
                if stage is not ReceiptStage.PREPARED:
                    store.claim(intent, saved.state, snapshot(), clock())
                    if stage is not ReceiptStage.UNKNOWN:
                        r = replace(store.receipt(intent.intent_id), stage=stage, sent_at=100,
                                    ha_ack_at=100 if stage in (ReceiptStage.ACKNOWLEDGED, ReceiptStage.ECHOED, ReceiptStage.PHYSICAL_EVIDENCE) else None,
                                    device_echo_at=100 if stage in (ReceiptStage.ECHOED, ReceiptStage.PHYSICAL_EVIDENCE) else None,
                                    physical_effect_at=100 if stage is ReceiptStage.PHYSICAL_EVIDENCE else None,
                                    evidence=(reading(),) if stage is ReceiptStage.PHYSICAL_EVIDENCE else ())
                        store.record_receipt(r, saved.state)
                before = store.receipt(intent.intent_id)
                with closing(sqlite3.connect(store.path)) as con:
                    bytes_before = con.execute("SELECT receipt,receipt_hash FROM outbox").fetchone()
                new = store.restart("synthetic.review-reboot")
                self.assertEqual(store.receipt(intent.intent_id), before)
                with closing(sqlite3.connect(store.path)) as con:
                    self.assertEqual(con.execute("SELECT receipt,receipt_hash FROM outbox").fetchone(), bytes_before)
                expected = "confirmed" if stage in (ReceiptStage.ACKNOWLEDGED, ReceiptStage.ECHOED, ReceiptStage.PHYSICAL_EVIDENCE) else "failed" if stage is ReceiptStage.FAILED else "unknown"
                self.assertEqual(store.delivery_status(intent.intent_id), expected)
                self.assertFalse(new.state.reconciled)
                self.assertEqual(new.state.desired_action, Action.STOP)
                self.assertIsNone(new.state.last_receipt)
                with self.assertRaises(StoreConflict):
                    store.claim(intent, new.state, snapshot(), clock())
                store.restart("synthetic.review-reboot-2")
                self.assertEqual(ControlStore(root).receipt(intent.intent_id), before)
                with closing(sqlite3.connect(store.path)) as con:
                    with con:
                        con.execute("UPDATE outbox SET receipt_hash='corrupt'")
                with self.assertRaises(StoreFailure):
                    ControlStore(root)

    def test_restart_active_heat_cannot_reconcile_or_accept_a_new_heat_plan(self):
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
            sim, s, c = ready_simulator(Path(directory))
            sim.pump(s, c)
            sim.close()
            reboot = Simulator(ControlStore(Path(directory)), sim.actuator, "synthetic.review-boot")
            try:
                c = replace(c, boot_id=reboot.state.boot_id)
                s = replace(s, boot_id=c.boot_id, owner_epoch=reboot.state.owner_epoch)
                e = event(kind=EventKind.RECONCILE, boot_id=c.boot_id, owner_epoch=reboot.state.owner_epoch,
                          sequence=1, at=106, expires_at=107)
                calls = reboot.actuator.calls
                mismatch = reboot.apply(e, s, c, observation=reboot.actuator.feedback(Action.HEAT, c))
                self.assertFalse(mismatch.state.reconciled)
                self.assertTrue(mismatch.state.manual_paused)
                self.assertFalse(reboot.state.reconciled)
                self.assertEqual(reboot.actuator.calls, calls)
                s = replace(s, owner_epoch=reboot.state.owner_epoch)
                proposal = plan(boot_id=c.boot_id, owner_epoch=reboot.state.owner_epoch, issued_at=107,
                                valid_from=107, segments=(PlanSegment(start=107, end=150),))
                c2 = replace(c, utc=112, monotonic=1012)
                s2 = fresh(112, boot_id=c.boot_id, owner_epoch=reboot.state.owner_epoch)
                reboot.apply(replace(e, kind=EventKind.PLAN, owner_epoch=reboot.state.owner_epoch,
                                     sequence=2, at=112, expires_at=113, plan=proposal), s2, c2)
                self.assertFalse(reboot.pump(s2, c2))
                self.assertEqual(reboot.actuator.calls, calls)
                self.assertFalse(reboot.state.reconciled)
            finally:
                reboot.close()

    def test_reconciliation_observation_matrix_and_no_external_heat_override(self):
        for action, manual, known, age in ((Action.HEAT, False, True, 0), (Action.HEAT, False, False, 0),
                                          (Action.HEAT, True, True, 0), (Action.HEAT, True, False, 0),
                                          (Action.STOP, False, False, 0), (Action.STOP, False, True, 11),
                                          (Action.STOP, False, True, 0)):
            with self.subTest(case=(action,manual,known,age)), tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
                sim = Simulator(ControlStore.create(Path(directory), state(), policy()), FakeActuator(), "synthetic.matrix")
                try:
                    c = clock(boot_id=sim.state.boot_id)
                    s = fresh(100, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch)
                    e = event(kind=EventKind.RECONCILE, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch)
                    obs = sim.actuator.feedback(action, replace(c, utc=100-age), manual=manual, writers_known=known)
                    sim.apply(e, s, c, observation=obs)
                    self.assertEqual(sim.state.reconciled, action is Action.STOP and known and age == 0)
                    if action is Action.HEAT:
                        self.assertTrue(sim.state.manual_paused)
                        self.assertTrue(sim.store.view().state.manual_paused)
                        self.assertEqual(sim.actuator.calls, ())
                    self.assertFalse(any(call.action is Action.HEAT for call in sim.actuator.calls))
                finally:
                    sim.close()

    def test_mismatch_requires_explicit_resume_fresh_stop_and_new_plan(self):
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
            sim = Simulator(ControlStore.create(Path(directory), state(), policy()), FakeActuator(), "synthetic.procedure")
            try:
                def step(kind, at, seq, action=None, authorize=False, candidate=None):
                    c = clock(boot_id=sim.state.boot_id, utc=at, monotonic=900+at)
                    s = fresh(at, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch)
                    e = event(kind=kind, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch,
                              sequence=seq, at=at, expires_at=at+1, plan=candidate, authorized=True)
                    return sim.apply(e,s,c,proof=sim.authority.attest(e) if authorize else None,
                                     observation=sim.actuator.feedback(action,c) if kind is EventKind.RECONCILE else None),s,c
                step(EventKind.RECONCILE,100,1,Action.HEAT)
                step(EventKind.RECONCILE,101,2,Action.STOP)
                self.assertTrue(sim.state.manual_paused)
                step(EventKind.RESUME,102,3)
                self.assertTrue(sim.state.manual_paused)
                step(EventKind.RESUME,103,4,authorize=True)
                self.assertFalse(sim.state.reconciled)
                step(EventKind.RECONCILE,104,5,Action.STOP)
                candidate=plan(boot_id=sim.state.boot_id,owner_epoch=sim.state.owner_epoch,issued_at=105,
                               valid_from=105,segments=(PlanSegment(start=105,end=150),))
                _,s,c=step(EventKind.PLAN,110,6,candidate=candidate)
                self.assertTrue(sim.pump(s,c))
                self.assertEqual(sum(call.action is Action.HEAT for call in sim.actuator.calls),1)
            finally:
                sim.close()

    def test_unresolved_current_delivery_is_distinct_from_historical_stage(self):
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
            sim,s,c=ready_simulator(Path(directory))
            try:
                intent=sim.state.last_intent
                sim.store.prepare(intent,s,c,sim.store.view().revision)
                self.assertEqual(sim.store.delivery_status(intent.intent_id),"in_flight")
                sim.store.restart("synthetic.fenced")
                self.assertEqual(sim.store.receipt(intent.intent_id).stage,ReceiptStage.PREPARED)
                self.assertEqual(sim.store.delivery_status(intent.intent_id),"unknown")
            finally:
                sim.close()
