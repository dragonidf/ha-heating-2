"""Disposable subprocess only; fault at named transaction checkpoints."""

import os, sys
from pathlib import Path
from packages.evidence.store import EvidenceStore
from packages.offline.contracts import PowerPoint
from tests.wp2a.test_migration import legacy
from packages.migration.rehearsal import dry_run, stage

root = Path(sys.argv[1])
operation = sys.argv[2]
checkpoint = sys.argv[3]
store = EvidenceStore(root)


def crash(point):
    if point == checkpoint:
        os._exit(77)


store.hook = crash
if operation == "power":
    store.power(
        PowerPoint(
            "synthetic.crash",
            "synthetic.heat",
            100,
            100,
            3,
            "derived",
            ("synthetic.meter",),
            "left_hold",
        )
    )
elif operation == "finalize":
    store.finalize("synthetic.heat", 130, as_of=130)
elif operation == "schema":
    store.migrate()
elif operation == "migration":
    stage(dry_run(legacy()), store)
elif operation == "checkpoint":
    store.checkpoint()
else:
    raise AssertionError("Unknown test operation")
