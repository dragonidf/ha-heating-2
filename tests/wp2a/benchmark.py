"""Measured disposable-host workload. No target N100/physical acceptance claim."""

import platform, tempfile, time, unittest, json
from pathlib import Path
from packages.evidence.store import EvidenceStore, record
from packages.offline.contracts import Origin, PowerPoint
from tests.wp2a.helpers import harness, planned


def run():
    result = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "scope": "synthetic disposable host; G1/B01-B08 BLOCKED",
    }
    with tempfile.TemporaryDirectory(prefix="heating-wp2a-") as root:
        store = EvidenceStore.create(Path(root))
        store.origin(Origin("synthetic.heat", "synthetic.continuity", 100, 10))
        points = tuple(
            PowerPoint(
                f"synthetic.bench.{i}",
                "synthetic.heat",
                100 + i * 30,
                100 + i * 30,
                3,
                "derived",
                ("synthetic.meter",),
                "left_hold",
            )
            for i in range(1025)
        )
        started = time.perf_counter()
        for start in range(0, len(points), 512):
            store.append_batch(
                tuple(
                    record(p.identity, p, p.at, p.stream)
                    for p in points[start : start + 512]
                )
            )
        result["raw_1025_append_s"] = time.perf_counter() - started
        started = time.perf_counter()
        store.finalize("synthetic.heat", points[-1].at, as_of=points[-1].at)
        result["finalize_1024_intervals_s"] = time.perf_counter() - started
        started = time.perf_counter()
        summary = store.summary("synthetic.heat")
        result["summary_s"] = time.perf_counter() - started
        assert abs(summary.actual_total_kwh - 35.6) < 1e-9 and summary.unknown_s == 0
        started = time.perf_counter()
        page = store.query("synthetic.heat", "PowerPoint", 100, 40000, limit=256)
        result["indexed_page_256_s"] = time.perf_counter() - started
        assert len(page.rows) == 256 and page.cursor is not None
        result["archive_records"] = store.verify()
        result["actual_total_kwh"] = summary.actual_total_kwh
    case = unittest.TestCase()
    try:
        runtime, _ = harness(case)
        clock, _ = planned(runtime)
        runtime.pump(clock)
        started = time.perf_counter()
        runtime.trusted_stop(clock)
        result["fake_stop_s"] = time.perf_counter() - started
    finally:
        case.doCleanups()
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    run()
