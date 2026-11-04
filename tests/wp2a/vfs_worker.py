"""Path-restricted SQLite EIO/ENOSPC, never a production process."""

import sys, json
from pathlib import Path
from packages.evidence.store import EvidenceStore, EvidenceFailure
from packages.offline.contracts import Origin, PowerPoint
from packages.contracts import Action, EventKind
from tests.unit.test_simulator import ready_simulator
from tests.fixtures.synthetic import event

root = Path(sys.argv[1])
critical = Path(sys.argv[2])
store = EvidenceStore.create(root)
store.origin(Origin("synthetic.heat", "synthetic.continuity", 100, 0))
sim, s, c = ready_simulator(critical)
marker = root / "vfs-fault.enabled"
marker.touch()
failed = False
try:
    try:
        store.power(
            PowerPoint(
                "synthetic.fault",
                "synthetic.heat",
                100,
                100,
                3,
                "derived",
                ("synthetic.meter",),
                "left_hold",
            )
        )
    except EvidenceFailure:
        failed = True
    stop = event(
        kind=EventKind.SAFETY_STOP,
        sequence=99,
        boot_id=c.boot_id,
        owner_epoch=sim.state.owner_epoch,
        at=c.utc,
        expires_at=c.utc + 1,
    )
    sim.emergency(stop, s, c, proof=sim.authority.attest(stop))
    assert sim.actuator.calls[-1].action is Action.STOP
    assert all(call.action is not Action.HEAT for call in sim.actuator.calls)
finally:
    marker.unlink()
    sim.close()
try:
    restarted = EvidenceStore(root)
    restarted.verify()
    outcome = "valid_prefix"
except EvidenceFailure:
    outcome = "blocked_no_reset"
print(json.dumps(dict(archive_failed=failed, heat=0, stop=True, recovery=outcome)))
