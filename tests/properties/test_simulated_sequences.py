import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from packages.contracts import Action, EventKind, OneShot, OneShotKind, OneShotOutcome, ReceiptStage
from packages.control_store.store import ControlStore, StoreConflict, StoreFailure
from packages.simulator.engine import Simulator
from tests.fixtures.synthetic import event
from tests.unit.test_simulator import ready_simulator


class SimulatedSequenceProperties(unittest.TestCase):
    def test_seeded_current_guard_failure_before_fake_send_never_heats(self):
        rng = random.Random(2026110307)
        for index in range(40):
            with self.subTest(index=index), tempfile.TemporaryDirectory(prefix="heating-wp1b-") as temp:
                sim, s, c = ready_simulator(Path(temp))
                try:
                    fault = rng.choice(("grid", "room", "return", "upper", "clock", "expiry"))
                    def inject(point):
                        if point != "before_send":
                            return
                        changed, now = s, c
                        if fault == "grid":
                            changed = replace(s, grid_actual=None, forecast_grid=True)
                        elif fault in ("room", "return"):
                            changed = replace(s, **{fault if fault == "room" else "return_temperature": None})
                        elif fault == "upper":
                            changed = replace(s, room=replace(s.room, value=30))
                        elif fault == "clock":
                            now = replace(c, monotonic=900)
                        else:
                            now = replace(c, utc=111, monotonic=1011)
                        sim.update_inputs(changed, now)
                    sim.hook = inject
                    self.assertFalse(sim.pump(s, c))
                    self.assertEqual(sum(call.action is Action.HEAT for call in sim.actuator.calls), 0)
                finally:
                    sim.close()

    def test_seeded_emergency_replays_cannot_reclaim_or_duplicate_commands(self):
        rng = random.Random(7)
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as temp:
            sim, s, c = ready_simulator(Path(temp))
            try:
                self.assertTrue(sim.pump(s, c))
                stop = event(kind=EventKind.SAFETY_STOP, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch,
                             sequence=50, at=99, expires_at=99.5)
                sim.emergency(stop, s, c, proof=sim.authority.attest(stop))
                stopped = sim.state
                calls = sim.actuator.calls
                for _ in range(200):
                    stale = replace(stop, sequence=rng.randrange(0, 51))
                    sim.emergency(stale, s, c, proof=sim.authority.attest(stale))
                    self.assertEqual(sim.state, stopped)
                    self.assertEqual(sim.actuator.calls, calls)
                    self.assertFalse(sim.pump(s, c))
                sim.flush_audit()
                self.assertEqual(sim.store.view().state.last_safety_stop_sequence, 50)
            finally:
                sim.close()

    def test_one_shot_failure_paths_are_atomic_and_immutable(self):
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as temp:
            sim, s, c = ready_simulator(Path(temp))
            try:
                shot = OneShot(intent_id="synthetic.property-once", kind=OneShotKind.HEAT_AFTER_GRID_RESTORE,
                               created_at=100, expires_at=200, armed_grid_epoch=4, consumed_at=None,
                               outcome=OneShotOutcome.PENDING)
                sim.store.register_one_shot(shot)
                sim.store.register_one_shot(shot)
                with self.assertRaises(StoreConflict):
                    sim.store.register_one_shot(replace(shot, expires_at=201))
                with self.assertRaises(StoreConflict):
                    sim.store.register_one_shot(replace(shot, outcome=OneShotOutcome.CANCELLED))
                with self.assertRaises(StoreFailure):
                    sim.store.one_shot("synthetic.missing")
                intent = sim.state.last_intent
                for identity in ("synthetic.missing",):
                    with self.assertRaises(StoreConflict):
                        sim.store.prepare(intent, s, c, sim.store.view().revision, one_shot_id=identity)
                self.assertEqual(sim.store.one_shot(shot.intent_id).outcome, OneShotOutcome.PENDING)
                sim.store.prepare(intent, s, c, sim.store.view().revision, one_shot_id=shot.intent_id)
                sim.store.claim(intent, sim.state, s, c)
                self.assertEqual(sim.store.receipt(intent.intent_id).stage, ReceiptStage.UNKNOWN)
                with self.assertRaises(StoreConflict):
                    sim.store.register_one_shot(shot)
                sim.close()
                reboot = Simulator(ControlStore(Path(temp)), sim.actuator, "synthetic.property-reboot")
                try:
                    self.assertEqual(reboot.store.one_shot(shot.intent_id).outcome, OneShotOutcome.UNKNOWN)
                    self.assertFalse(reboot.pump(s, c))
                finally:
                    reboot.close()
            finally:
                sim.close()
