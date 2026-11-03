import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from packages.contracts import Action, OneShotOutcome, ReceiptStage
from packages.control_store.store import ControlStore, StoreFailure
from packages.simulator.engine import FakeActuator, Simulator
from tests.fixtures.synthetic import clock, snapshot


class CrashMatrixTests(unittest.TestCase):
    def kill_at(self, point):
        tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        child = subprocess.Popen([sys.executable, "-B", "-m", "tests.fixtures.crash_worker", str(root), point],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        deadline = time.monotonic()+10
        while not (root / "cut.json").exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        if not (root / "cut.json").exists():
            child.kill()
            out, err = child.communicate(timeout=5)
            self.fail(f"Crash point not reached: {point}: {out} {err}")
        # Child fsyncs and closes its trace before blocking; wait for complete JSON.
        for _ in range(100):
            try:
                trace = json.loads((root / "cut.json").read_text())
                break
            except (json.JSONDecodeError, OSError):
                time.sleep(0.001)
        os.kill(child.pid, signal.SIGKILL)
        child.communicate(timeout=5)
        self.assertEqual(child.returncode, -signal.SIGKILL)
        return root, trace

    def test_sigkill_command_boundaries_never_replay_heat_or_one_shot(self):
        points = ("before_prepare", "after_prepare", "before_send", "after_claim", "after_fake_send",
                  "after_sent", "before_ack_receipt", "after_ack", "before_echo_receipt", "after_echo")
        for index, point in enumerate(points):
            with self.subTest(point=point):
                root, trace = self.kill_at(point)
                heat_count = trace["calls"].count(Action.HEAT.value)
                self.assertEqual(heat_count, int(index >= 4))
                store = ControlStore(root)
                intent = store.view().state.last_intent
                historical = store.receipt(intent.intent_id) if index > 0 else None
                sim = Simulator(store, FakeActuator(), "synthetic.parent-reboot")
                self.addCleanup(sim.close)
                self.assertEqual(sim.state.desired_action, Action.STOP)
                self.assertFalse(sim.state.reconciled)
                self.assertIsNone(sim.state.plan)
                self.assertFalse(sim.pump(snapshot(), clock()))
                self.assertEqual(sum(c.action is Action.HEAT for c in sim.actuator.calls), 0)
                shot = store.one_shot("synthetic.crash-once")
                if index == 0:
                    self.assertEqual(shot.outcome, OneShotOutcome.PENDING)
                    with self.assertRaises(StoreFailure):
                        store.receipt(intent.intent_id)
                else:
                    self.assertEqual(shot.outcome, OneShotOutcome.UNKNOWN)
                    self.assertIsNotNone(shot.consumed_at)
                    self.assertEqual(store.receipt(intent.intent_id), historical)
                    self.assertEqual(store.delivery_status(intent.intent_id), "confirmed" if index >= 7 else "unknown")

    def test_sigkill_owner_transaction_migration_and_checkpoint_preserve_safe_restart(self):
        for point in ("owner_before_commit", "migration_before_commit", "checkpoint_during"):
            with self.subTest(point=point):
                root, _ = self.kill_at(point)
                store = ControlStore(root)
                reboot = store.restart("synthetic.control-restart")
                self.assertEqual(reboot.state.desired_action, Action.STOP)
                self.assertFalse(reboot.state.reconciled)
                if point != "owner_before_commit":
                    self.assertTrue(reboot.state.manual_paused)
                self.assertEqual(store.pragmas(), ("wal", 2))
