import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from packages.contracts import Action, EventKind, PlanSegment, ReceiptStage
from packages.control_store.store import ControlStore
from packages.simulator.engine import FakeActuator, Simulator
from tests.fixtures.synthetic import clock, event, plan, policy, state
from tests.unit.test_recovery import fresh


def ready_simulator(root, *, adapter=None, hook=None):
    store = ControlStore.create(root, state(), policy())
    sim = Simulator(store, adapter or FakeActuator(), "synthetic.sim-boot", hook=hook)
    epoch = sim.state.owner_epoch
    c = clock(boot_id=sim.state.boot_id)
    s = fresh(100, boot_id=c.boot_id, owner_epoch=epoch)
    reconcile = event(kind=EventKind.RECONCILE, boot_id=c.boot_id, owner_epoch=epoch)
    sim.apply(reconcile, s, c, observation=sim.actuator.feedback(Action.STOP, c))
    c = clock(utc=106, monotonic=1006, boot_id=sim.state.boot_id)
    s = fresh(106, boot_id=c.boot_id, owner_epoch=epoch)
    candidate = plan(boot_id=c.boot_id, owner_epoch=epoch, issued_at=101, valid_from=101,
                     segments=(PlanSegment(start=106, end=150),))
    sim.apply(event(kind=EventKind.PLAN, boot_id=c.boot_id, owner_epoch=epoch, sequence=2,
                    at=106, expires_at=107, plan=candidate), s, c)
    return sim, s, c


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_heat_requires_prepare_and_distinct_sent_ack_echo_evidence(self):
        sim, s, c = ready_simulator(self.root)
        self.addCleanup(sim.close)
        self.assertTrue(sim.pump(s, c))
        intent = sim.state.last_intent
        self.assertEqual(sim.store.receipt(intent.intent_id).stage, ReceiptStage.SENT)
        self.assertIsNone(sim.store.receipt(intent.intent_id).physical_effect_at)
        sim.ack(c)
        sim.echo(c)
        self.assertEqual(sim.store.receipt(intent.intent_id).stage, ReceiptStage.ECHOED)
        self.assertEqual(sum(call.action is Action.HEAT for call in sim.actuator.calls), 1)
        self.assertFalse(sim.pump(s, c))

    def test_serialized_authorized_flag_is_not_simulator_authentication(self):
        sim, s, c = ready_simulator(self.root)
        self.addCleanup(sim.close)
        sim.pump(s, c)
        stop = event(kind=EventKind.SAFETY_STOP, authorized=True, boot_id=c.boot_id,
                     owner_epoch=sim.state.owner_epoch, sequence=0, at=99, expires_at=99.5)
        before = sim.actuator.calls
        sim.emergency(stop, s, c)
        self.assertEqual(sim.actuator.calls, before)
        proof = sim.authority.attest(stop)
        result = sim.emergency(stop, s, c, proof=proof)
        self.assertEqual(result.state.desired_action, Action.STOP)
        self.assertEqual(sim.actuator.calls[-1].action, Action.STOP)
        self.assertFalse(sim.pump(s, c))

    def test_restart_clears_pending_heat_and_requires_new_trusted_observation(self):
        sim, s, c = ready_simulator(self.root)
        self.assertTrue(sim.pump(s, c))
        adapter = sim.actuator
        sim.close()
        reboot = Simulator(ControlStore(self.root), adapter, "synthetic.second-boot")
        self.addCleanup(reboot.close)
        self.assertFalse(reboot.state.reconciled)
        self.assertIsNone(reboot.state.plan)
        self.assertEqual(reboot.state.desired_action, Action.STOP)
        self.assertFalse(reboot.pump(s, c))
        self.assertEqual(sum(call.action is Action.HEAT for call in adapter.calls), 1)

    def test_fake_device_failure_is_unknown_and_never_retried(self):
        adapter = FakeActuator()
        sim, s, c = ready_simulator(self.root, adapter=adapter)
        self.addCleanup(sim.close)
        adapter.fail_send = True
        self.assertFalse(sim.pump(s, c))
        self.assertFalse(sim.pump(s, c))
        self.assertEqual(sim.store.receipt(sim.state.last_intent.intent_id).stage, ReceiptStage.UNKNOWN)

    def test_second_writer_cannot_bind_the_same_fake_actuator(self):
        sim, _, _ = ready_simulator(self.root)
        self.addCleanup(sim.close)
        with self.assertRaises(RuntimeError):
            Simulator(sim.store, sim.actuator, "synthetic.illegal-second")
