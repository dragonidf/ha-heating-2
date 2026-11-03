import ast, random, subprocess, sys, time, unittest
from pathlib import Path
from dataclasses import replace
from packages.planner import solve, replan
from packages.thermal import Interval
from tests.fixtures.wp1c import request, forcing

ROOT = Path(__file__).resolve().parents[2]
PURE = {
    "packages.contracts",
    "packages.contracts.models",
    "packages.contracts.codec",
    "packages.thermal",
    "packages.planner",
    "packages.planner.sources",
    "packages.planner.policy",
    "packages.planner.evidence",
    "packages.learning",
    "packages.fan_policy",
}
STDLIB = {
    "dataclasses",
    "datetime",
    "enum",
    "hashlib",
    "itertools",
    "json",
    "math",
    "types",
    "typing",
}
BANNED = {
    "open",
    "exec",
    "eval",
    "__import__",
    "now",
    "today",
    "utcnow",
    "timestamp_now",
    "sleep",
    "connect",
    "call_service",
}


def violations(source):
    result = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            result.extend(x.name for x in node.names if x.name not in STDLIB)
        if isinstance(node, ast.ImportFrom) and node.module not in PURE | STDLIB:
            result.append(node.module)
        if isinstance(node, ast.Call):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name in BANNED:
                result.append(name)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            result.append("mutable global")
    return result


class WP1CProperties(unittest.TestCase):
    def test_closed_graph_and_external_effect_denial(self):
        paths = sorted(
            p
            for group in ("thermal", "planner", "learning", "fan_policy")
            for p in (ROOT / "packages" / group).glob("*.py")
        )
        self.assertEqual(len(paths), 8)
        for path in paths:
            self.assertEqual(violations(path.read_text()), [], str(path))
        for text in (
            "import socket",
            "from packages.control_store import Store",
            "from packages.simulator import FakeActuator",
            "from pathlib import Path",
            "__import__('os')",
            "datetime.now()",
            "global state",
            "hass.call_service('x')",
        ):
            self.assertTrue(violations(text))
        result = subprocess.run(
            [sys.executable, "-B", "-m", "tests.properties.wp1c_probe"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_seeded_scenarios_deterministic_safe_absolute_and_no_hidden_authority(self):
        rng = random.Random(11032026)
        for _ in range(40):
            req = request(
                hours=2,
                stages_kw=(rng.choice((3.0, 6.0, 9.0)),),
                actual_grid=rng.choice((None, False, True)),
            )
            f = forcing(
                outside=Interval(-rng.randrange(40), 0),
                ventilation_loss=Interval(0, rng.random()),
                quality_valid=False,
            )
            slots = tuple(
                replace(
                    s,
                    forcing=f,
                    grid=rng.choice(
                        ("normal", "unknown", "scheduled_off", "emergency")
                    ),
                )
                for s in req.slots
            )
            req = replace(req, slots=slots)
            p = solve(req)
            self.assertEqual(p, solve(req))
            self.assertLessEqual(p.work, req.max_work + 1)
            for segment in p.segments:
                self.assertLess(segment.start, segment.end)
                self.assertTrue(segment.conditional)
                for slot in slots:
                    if segment.start <= slot.window.start < segment.end:
                        self.assertNotIn(slot.grid, ("scheduled_off", "emergency"))
                        self.assertLessEqual(slot.window.end, segment.end)
                        self.assertTrue(
                            any(
                                w.start <= slot.window.start
                                and slot.window.end <= w.end
                                for w in req.allowed
                            )
                        )
            if req.actual_grid is not True:
                self.assertFalse(
                    any(s.start <= req.state.at < s.end for s in p.segments)
                )
            for state, slot in zip(p.trajectory, slots):
                if any(s.start < state.at <= s.end for s in p.segments):
                    self.assertLess(state.room.high, slot.upper)
                    self.assertLess(state.stored.high, req.stored_upper)

    def test_full_24_72h_cold_warm_and_hard_deadline(self):
        # Timeout is an external test harness, never a wall clock read in the planner.
        code = "from tests.properties.benchmark_planner import run; run()"
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("72h", result.stdout)
        req = request(hours=72, max_work=900)
        p = solve(req)
        self.assertEqual(p.status, "SEARCH_EXHAUSTED")
        self.assertEqual(p.segments, ())
        deadline = time.monotonic() + 0.01
        p = solve(request(hours=72), lambda: time.monotonic() >= deadline)
        self.assertEqual(p.status, "SEARCH_EXHAUSTED")
        self.assertEqual(p.segments, ())

    def test_material_outage_moved_removed_and_unqualified_limits_override_retention(
        self,
    ):
        req = request()
        p = solve(req)
        moved = replace(
            req, slots=tuple(replace(s, grid="scheduled_off") for s in req.slots)
        )
        self.assertEqual(replan(moved, p).segments, ())
        self.assertGreater(
            len(replan(req, solve(moved), material_change=True).segments), 0
        )
        self.assertEqual(
            replan(replace(req, limits_qualified=False), p).status, "BLOCKED"
        )
