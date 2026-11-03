"""100k synthetic snapshot microbenchmark. Never a physical-host acceptance gate."""
import json
import platform
import statistics
from time import perf_counter_ns

from packages.contracts import ControlMode, Unit
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, policy, reading, snapshot, state


def main():
    initial, tick, now = state(), event(), clock()
    cases = ((snapshot(), policy()), (snapshot(hard_stop=True), policy()),
             (snapshot(grid_actual=reading(None, Unit.BOOLEAN)), policy()),
             (snapshot(), policy(operating_mode=ControlMode.SHADOW)))
    for i in range(1000):
        snap, config = cases[i % len(cases)]
        reduce(initial, tick, snap, config, now)
    elapsed = []
    for i in range(100_000):
        snap, config = cases[i % len(cases)]
        start = perf_counter_ns()
        reduce(initial, tick, snap, config, now)
        elapsed.append((perf_counter_ns() - start) / 1_000_000)
    elapsed.sort()
    print(json.dumps(dict(python=platform.python_version(), machine=platform.machine(),
                          host="isolated cloud sandbox; not N100", snapshots=len(elapsed),
                          cases="equal safe/hard-stop/unknown-grid/shadow; constructed outside timing",
                          p50_ms=statistics.median(elapsed), p95_ms=elapsed[94_999],
                          p99_ms=elapsed[98_999], max_ms=elapsed[-1]), sort_keys=True))


if __name__ == "__main__":
    main()
