"""Offline measurements only; no N100, real relay or power-loss gate claim."""
import json
import math
import os
import platform
import sqlite3
import statistics
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path
from time import perf_counter_ns

from packages.contracts import EventKind
from packages.control_store.qualification import inspect_sqlite
from tests.fixtures.synthetic import event
from tests.unit.test_simulator import ready_simulator


def distribution(values):
    values = sorted(values)
    return dict(samples=len(values), p50_ms=statistics.median(values),
                p95_ms=values[math.ceil(len(values)*.95)-1], p99_ms=values[math.ceil(len(values)*.99)-1],
                max_ms=values[-1])


def measure():
    bootstrap, heat, stop, checkpoint = [], [], [], []
    admitted = 0
    for _ in range(100):
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
            start = perf_counter_ns()
            sim, s, c = ready_simulator(Path(directory))
            bootstrap.append((perf_counter_ns()-start)/1_000_000)
            try:
                start = perf_counter_ns()
                admitted += sim.pump(s, c)
                heat.append((perf_counter_ns()-start)/1_000_000)
                e = event(kind=EventKind.SAFETY_STOP, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch,
                          sequence=0, at=99, expires_at=99.5)
                proof = sim.authority.attest(e)
                with closing(sqlite3.connect(sim.store.path, isolation_level=None)) as con:
                    con.execute("BEGIN IMMEDIATE")
                    start = perf_counter_ns()
                    sim.emergency(e, s, c, proof=proof)
                    stop.append((perf_counter_ns()-start)/1_000_000)
                    con.rollback()
                start = perf_counter_ns()
                sim.store.checkpoint()
                checkpoint.append((perf_counter_ns()-start)/1_000_000)
            finally:
                sim.close()
    with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
        root = Path(directory)
        with (root / "synthetic-sync-probe").open("wb") as stream:
            stream.write(b"synthetic")
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    info = inspect_sqlite()
    fs = subprocess.check_output(["findmnt", "-T", tempfile.gettempdir(), "-n", "-o", "FSTYPE"], text=True).strip()
    return dict(python=platform.python_version(), machine=platform.machine(), filesystem=fs,
                sqlite=info.version, sqlite_source_id=info.source_id, linked_minimum_qualified=info.qualified,
                file_and_directory_fsync_acknowledged=True,
                scope="disposable sandbox; process-crash proof only; no physical power-loss/N100 qualification",
                cold_bootstrap=distribution(bootstrap), prepare_claim_fake_send_and_sent_receipt=distribution(heat),
                trusted_stop_while_sqlite_write_locked=distribution(stop), checkpoint=distribution(checkpoint),
                admitted_heat=admitted, prepare_budget_ms=250,
                injected_stalls="unit tests separately hold/fail prepare and exceed 250ms; no HEAT admitted")


if __name__ == "__main__":
    print(json.dumps(measure(), sort_keys=True, indent=2))
