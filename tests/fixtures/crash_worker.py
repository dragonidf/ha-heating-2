"""Disposable child killed by tests; never runs outside an explicit sandbox root."""
import json
import os
import sqlite3
import sys
from pathlib import Path
from threading import Event

from packages.contracts import Action, EventKind, OneShot, OneShotKind, OneShotOutcome
from packages.control_store.store import ControlStore
from tests.fixtures.synthetic import event, policy, state
from tests.unit.test_simulator import ready_simulator


def run(root: Path, target: str) -> None:
    sim = None
    def cut(point):
        if point != target:
            return
        calls = [] if sim is None else [c.action.value for c in sim.actuator.calls]
        trace = dict(point=point, calls=calls)
        with (root / "cut.json").open("w") as f:
            json.dump(trace, f)
            f.flush()
            os.fsync(f.fileno())
        Event().wait(30)
        raise RuntimeError("Parent did not kill disposable child")
    if target in ("migration_before_commit", "checkpoint_during"):
        store = ControlStore.create(root, state(manual_paused=True), policy())
        anchor = sqlite3.connect(store.path)
        if target == "migration_before_commit":
            anchor.execute("DROP TABLE outbox")
            anchor.execute("DROP TABLE oneshots")
            anchor.execute("PRAGMA user_version=1")
            anchor.commit()
            ControlStore(root, hook=cut)
        else:
            store.hook = cut
            store.checkpoint()
        anchor.close()
        return
    sim, snapshot, clock = ready_simulator(root)
    shot = OneShot(intent_id="synthetic.crash-once", kind=OneShotKind.HEAT_AFTER_GRID_RESTORE,
                   created_at=90, expires_at=200, armed_grid_epoch=4, consumed_at=None,
                   outcome=OneShotOutcome.PENDING)
    sim.store.register_one_shot(shot)
    sim._pending = (sim.state.last_intent, shot.intent_id)  # Test harness injects a pending logical marker.
    sim.store.hook = cut
    sim.hook = cut
    if target == "owner_before_commit":
        sim.pump(snapshot, clock)
        e = event(kind=EventKind.MANUAL_CHANGE, boot_id=clock.boot_id, owner_epoch=sim.state.owner_epoch,
                  sequence=3, at=106, expires_at=107)
        sim.apply(e, snapshot, clock, observation=sim.actuator.feedback(Action.HEAT, clock, manual=True))
    else:
        sim.pump(snapshot, clock)
        sim.ack(clock)
        sim.echo(clock)
    raise RuntimeError("Unknown/unreached crash point")


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
