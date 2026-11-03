"""Only launched in a disposable child with the path-restricted test preload."""
import json
import sys
from pathlib import Path

from packages.contracts import Action
from packages.control_store.store import ControlStore, StoreFailure
from packages.simulator.engine import FakeActuator, Simulator
from tests.unit.test_simulator import ready_simulator


def run(root):
    sim, s, c = ready_simulator(root)
    marker = root / "vfs-fault.enabled"
    marker.touch()
    try:
        emitted = sim.pump(s, c)
        calls = [call.action.value for call in sim.actuator.calls]
    finally:
        marker.unlink()
        sim.close()
    assert not emitted and Action.HEAT.value not in calls
    try:
        reboot = Simulator(ControlStore(root), FakeActuator(), "synthetic.vfs-reboot")
        try:
            assert reboot.state.desired_action is Action.STOP and not reboot.state.reconciled
            assert not reboot.pump(s, c)
        finally:
            reboot.close()
        recovery = "STARTING_STOP_no_replay"
    except StoreFailure:
        recovery = "BLOCKED_corrupt_or_unknown_store_no_reset"
    print(json.dumps(dict(fake_heat_emitted=False, calls=calls, recovery=recovery)))


if __name__ == "__main__":
    run(Path(sys.argv[1]))
