import sqlite3
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from packages.contracts import Action, ControlMode, EventKind, ReceiptStage
from packages.control_store.qualification import SQLiteInfo
from packages.control_store.store import ControlStore, StoreFailure
from packages.simulator.engine import FakeActuator, FakeAuthority, Simulator
from tests.fixtures.synthetic import clock, event, policy, snapshot, state
from tests.unit.test_recovery import fresh
from tests.unit.test_simulator import ready_simulator


class SimulatorFaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def ready(self):
        sim, s, c = ready_simulator(self.root)
        self.addCleanup(sim.close)
        return sim, s, c

    def stop_event(self, sim, c, sequence=0):
        return event(kind=EventKind.SAFETY_STOP, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch,
                     authorized=True, sequence=sequence, at=99, expires_at=99.5)

    def test_stop_bypasses_hung_prepare_and_late_worker_cannot_emit_heat(self):
        sim, s, c = self.ready()
        entered, release = Event(), Event()
        def hang(point):
            if point == "before_prepare":
                entered.set()
                release.wait(3)
        sim.store.hook = hang
        result = []
        worker = Thread(target=lambda: result.append(sim.pump(s, c)))
        worker.start()
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(1))
        stop = self.stop_event(sim, c)
        start = time.perf_counter()
        sim.emergency(stop, s, c, proof=sim.authority.attest(stop))
        latency = time.perf_counter()-start
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertLess(latency, 0.250)
        self.assertEqual(sim.actuator.calls[-1].action, Action.STOP)
        self.assertFalse(any(call.action is Action.HEAT for call in sim.actuator.calls))
        self.assertEqual(result, [False])
        sim.store.hook = None
        self.assertEqual(sim.flush_audit(), 1)
        self.assertEqual(sim.store.view().state.last_safety_stop_sequence, 0)

    def test_stop_never_calls_database_even_under_actual_sqlite_write_lock(self):
        sim, s, c = self.ready()
        stop = self.stop_event(sim, c)
        with sqlite3.connect(sim.store.path, isolation_level=None) as con:
            con.execute("BEGIN IMMEDIATE")
            with patch.object(sim.store, "view", side_effect=AssertionError("STOP used database")):
                sim.emergency(stop, s, c, proof=sim.authority.attest(stop))
            con.rollback()
        self.assertEqual(sim.actuator.calls[-1].action, Action.STOP)
        self.assertFalse(sim.pump(s, c))

    def test_slow_durable_prepare_is_not_permission_to_send(self):
        for point in ("before_prepare", "after_prepare"):
            with self.subTest(point=point):
                tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
                self.addCleanup(tmp.cleanup)
                sim, s, c = ready_simulator(Path(tmp.name))
                self.addCleanup(sim.close)
                def slow(stage):
                    if stage == point:
                        time.sleep(0.270)
                sim.store.hook = slow
                self.assertFalse(sim.pump(s, c))
                self.assertFalse(any(call.action is Action.HEAT for call in sim.actuator.calls))

    def test_readonly_full_and_sync_errors_never_emit_heat(self):
        for failure in ("readonly", "full", "sync"):
            with self.subTest(failure=failure):
                tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
                self.addCleanup(tmp.cleanup)
                sim, s, c = ready_simulator(Path(tmp.name))
                self.addCleanup(sim.close)
                if failure == "readonly":
                    sim.store.readonly = True
                else:
                    def fail(point):
                        if point == "before_commit":
                            if failure == "full":
                                raise sqlite3.OperationalError("synthetic database or disk is full")
                            raise OSError(5, "synthetic sync error")
                    sim.store.hook = fail
                self.assertFalse(sim.pump(s, c))
                self.assertFalse(any(call.action is Action.HEAT for call in sim.actuator.calls))
                self.assertEqual(sim.state.desired_action, Action.STOP)

    def test_virtual_time_and_grid_are_rechecked_after_prepare(self):
        for failure in ("expiry", "grid", "rollback"):
            with self.subTest(failure=failure):
                tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
                self.addCleanup(tmp.cleanup)
                sim, s, c = ready_simulator(Path(tmp.name))
                self.addCleanup(sim.close)
                def update(point):
                    if point == "before_send":
                        if failure == "expiry":
                            sim.update_inputs(fresh(111, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch),
                                              replace(c, utc=111, monotonic=1011))
                        elif failure == "grid":
                            sim.update_inputs(replace(s, grid_actual=None), c)
                        else:
                            sim.update_inputs(s, replace(c, monotonic=1000))
                sim.hook = update
                self.assertFalse(sim.pump(s, c))
                self.assertFalse(any(call.action is Action.HEAT for call in sim.actuator.calls))

    def test_persisted_settings_change_between_prepare_and_send_is_fenced(self):
        sim, s, c = self.ready()
        def change(point):
            if point == "after_claim":
                current = sim.store.view()
                sim.store.configure(replace(current.policy, config_revision=2, armed=False),
                                    current.revision, current.state)
        sim.store.hook = change
        self.assertFalse(sim.pump(s, c))
        self.assertFalse(any(call.action is Action.HEAT for call in sim.actuator.calls))

    def test_bounded_latest_desire_queue_and_no_duplicate_ack_echo(self):
        sim, s, c = self.ready()
        for sequence in range(3, 33):
            sim.apply(event(boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch, sequence=sequence,
                            at=106, expires_at=107), s, c)
            self.assertEqual(sim.pending_count, 1)
        self.assertTrue(sim.pump(s, c))
        self.assertTrue(sim.ack(c))
        self.assertFalse(sim.ack(c))
        self.assertTrue(sim.echo(c))
        self.assertFalse(sim.echo(c))
        self.assertFalse(sim.ack(c))
        self.assertEqual(sim.store.receipt(sim.state.last_intent.intent_id).stage, ReceiptStage.ECHOED)
        self.assertEqual(sum(call.action is Action.HEAT for call in sim.actuator.calls), 1)

    def test_manual_intervention_cancels_pending_and_survives_reboot(self):
        sim, s, c = self.ready()
        e = event(kind=EventKind.MANUAL_CHANGE, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch,
                  sequence=3, at=106, expires_at=107)
        self.assertIsNone(sim.apply(e, s, c))
        sim.apply(e, s, c, observation=sim.actuator.feedback(Action.HEAT, c, manual=True))
        self.assertTrue(sim.state.manual_paused)
        self.assertFalse(sim.pump(s, c))
        sim.close()
        reboot = Simulator(ControlStore(self.root), sim.actuator, "synthetic.manual-reboot")
        self.addCleanup(reboot.close)
        self.assertTrue(reboot.state.manual_paused)
        resume = event(kind=EventKind.RESUME, authorized=True, boot_id=reboot.state.boot_id,
                       owner_epoch=reboot.state.owner_epoch, at=106, expires_at=107)
        reboot.apply(resume, replace(s, boot_id=reboot.state.boot_id, owner_epoch=reboot.state.owner_epoch),
                     replace(c, boot_id=reboot.state.boot_id))
        self.assertTrue(reboot.state.manual_paused)

    def test_untrusted_unknown_stale_feedback_cannot_reconcile_or_rearm(self):
        sim, s, c = self.ready()
        sim.close()
        reboot = Simulator(ControlStore(self.root), sim.actuator, "synthetic.evidence-reboot")
        self.addCleanup(reboot.close)
        c = replace(c, boot_id=reboot.state.boot_id)
        s = replace(s, boot_id=c.boot_id, owner_epoch=reboot.state.owner_epoch)
        e = event(kind=EventKind.RECONCILE, boot_id=c.boot_id, owner_epoch=reboot.state.owner_epoch,
                  at=106, expires_at=107)
        cases = (None, FakeActuator().feedback(Action.STOP, c),
                 reboot.actuator.feedback(None, c), reboot.actuator.feedback(Action.STOP, c, writers_known=False),
                 reboot.actuator.feedback(Action.STOP, replace(c, utc=90)))
        for observation in cases:
            self.assertIsNone(reboot.apply(e, s, c, observation=observation))
            self.assertFalse(reboot.state.reconciled)

    def test_async_freshness_survives_durable_prepare_and_frozen_room_fails(self):
        sim, s, c = self.ready()
        mixed = replace(s, room=replace(s.room, observed_at=100, received_at=100),
                        thermostat=replace(s.thermostat, observed_at=102, received_at=102),
                        return_temperature=replace(s.return_temperature, observed_at=104, received_at=104))
        self.assertTrue(sim.pump(mixed, c))
        sim.close()
        tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
        self.addCleanup(tmp.cleanup)
        other, s, c = ready_simulator(Path(tmp.name))
        self.addCleanup(other.close)
        self.assertFalse(other.pump(replace(s, room=replace(s.room, observed_at=70, received_at=106)), c))

    def test_shadow_and_foreign_capability_have_no_actuator_authority(self):
        store = ControlStore.create(self.root, state(), policy(operating_mode=ControlMode.SHADOW))
        sim = Simulator(store, FakeActuator(), "synthetic.shadow-boot")
        self.addCleanup(sim.close)
        c = clock(boot_id=sim.state.boot_id)
        s = snapshot(boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch)
        stop = self.stop_event(sim, c)
        sim.emergency(stop, s, c, proof=FakeAuthority().attest(stop))
        sim.emergency(stop, s, c, proof=sim.authority.attest(stop))
        self.assertEqual(sim.actuator.calls, ())
        self.assertEqual(sim.pending_count, 0)

    def test_unqualified_sqlite_is_blocked_and_never_creates_a_database(self):
        with patch("packages.control_store.store.inspect_sqlite", return_value=SQLiteInfo("3.46.1", "synthetic", False)):
            with self.assertRaises(StoreFailure):
                ControlStore.create(self.root, state(), policy())
        self.assertFalse((self.root / "control.sqlite3").exists())

    def test_late_worker_cannot_touch_new_writer_after_close_and_restart(self):
        sim, s, c = self.ready()
        entered, release = Event(), Event()
        errors = []
        def hang(point):
            if point == "before_prepare":
                entered.set()
                release.wait(3)
        sim.store.hook = hang
        def pump():
            try:
                sim.pump(s, c)
            except BaseException as error:
                errors.append(error)
        worker = Thread(target=pump)
        worker.start()
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(1))
        sim.close()
        reboot = Simulator(ControlStore(self.root), sim.actuator, "synthetic.worker-restart")
        self.addCleanup(reboot.close)
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertFalse(any(call.action is Action.HEAT for call in reboot.actuator.calls))

    def test_audit_overload_retains_latest_frontier_and_reports_coalesced_records(self):
        sim, s, c = self.ready()
        for sequence in range(20):
            stop = self.stop_event(sim, c, sequence)
            sim.emergency(stop, s, c, proof=sim.authority.attest(stop))
        self.assertEqual(sim.audit_missing, 4)
        self.assertEqual(sim.flush_audit(), 16)
        self.assertEqual(sim.store.view().state.last_safety_stop_sequence, 19)
        self.assertEqual(sim.store.view().revision, sim._view.revision)
        self.assertFalse(any(call.action is Action.HEAT for call in sim.actuator.calls))

    def test_failed_audit_is_explicit_and_invalid_emergency_route_rejected(self):
        sim, s, c = self.ready()
        with self.assertRaises(ValueError):
            sim.emergency(event(boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch), s, c)
        stop = self.stop_event(sim, c)
        sim.apply(stop, s, c, proof=sim.authority.attest(stop))
        sim.store.readonly = True
        self.assertEqual(sim.flush_audit(), 0)
        self.assertEqual(sim.audit_missing, 1)
        self.assertEqual(sim.actuator.calls[-1].action, Action.STOP)

    def test_only_exact_fake_adapter_and_no_ack_without_a_current_send(self):
        class UnsupportedAdapter(FakeActuator):
            pass
        store = ControlStore.create(self.root, state(), policy())
        with self.assertRaises(TypeError):
            Simulator(store, UnsupportedAdapter(), "synthetic.unsupported")
        adapter = FakeActuator()
        with self.assertRaises(StoreFailure):
            Simulator(store, adapter, "synthetic.boot")
        token = adapter.reserve()  # Failed constructor released its fake writer.
        adapter.release(token)
        sim = Simulator(store, adapter, "synthetic.no-send")
        self.addCleanup(sim.close)
        with self.assertRaises(StoreFailure):
            sim.ack(clock(boot_id=sim.state.boot_id))
