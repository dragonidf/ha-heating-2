"""Reproducible host observation, not target hardware qualification."""

import platform, time
from dataclasses import replace
from packages.planner import solve
from packages.thermal import Interval
from tests.fixtures.wp1c import request, thermal, forcing


def run():
    print(
        platform.python_version(),
        platform.system(),
        platform.release(),
        platform.machine(),
    )
    for hours in (24, 72):
        req = request(hours=hours)
        for kind in ("cold", "warm", "fire"):
            r = req
            if kind == "cold":
                r = replace(
                    req,
                    slots=tuple(
                        replace(s, forcing=forcing(outside=Interval(-35, -35)))
                        for s in req.slots
                    ),
                )
            if kind == "warm":
                r = replace(
                    req,
                    state=thermal(req.state.at, 22, 22),
                    slots=tuple(
                        replace(s, target=19, forcing=forcing(outside=Interval(22, 22)))
                        for s in req.slots
                    ),
                )
            if kind == "fire":
                r = replace(
                    req,
                    slots=tuple(
                        replace(s, forcing=forcing(fire_delta=Interval(5, 5)))
                        for s in req.slots
                    ),
                )
            start = time.perf_counter()
            p = solve(r)
            elapsed = time.perf_counter() - start
            assert p.work <= r.max_work + 1
            assert len(p.trajectory) == hours * 12 or p.status in (
                "BLOCKED",
                "SEARCH_EXHAUSTED",
            )
            if kind == "warm":
                assert p.energy_kwh == 0
            print(
                f"{hours}h {kind}: {elapsed:.6f}s work={p.work} status={p.status} energy={p.energy_kwh:.6f}"
            )


if __name__ == "__main__":
    run()
