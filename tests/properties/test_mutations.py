"""Six explicit in-memory guard deletions must be killed by independent witnesses.

No source files are modified. This is focused safety mutation evidence, not a
claim of exhaustive mutation coverage or physical testing.
"""
import pathlib
import unittest

from packages.contracts import Action, Unit
from packages.control import evaluate, reduce
from tests.fixtures.synthetic import clock, event, policy, reading, snapshot, state


class MutationTests(unittest.TestCase):
    def test_each_removed_guard_exposes_a_heat_regression(self):
        source = (pathlib.Path(__file__).resolve().parents[2] / "packages/control/kernel.py").read_text()
        cases = (
            ("if snapshot.hard_stop:", snapshot(hard_stop=True), policy(), state()),
            ("if not policy.armed or not policy.allow_automatic:", snapshot(), policy(armed=False), state()),
            ("if snapshot.grid_actual is None or snapshot.grid_actual.value is not True:",
             snapshot(grid_actual=reading(False, Unit.BOOLEAN)), policy(), state()),
            ("if (snapshot.room is not None and snapshot.room.value is not None\n            and float(snapshot.room.value) >= policy.room_upper_c):",
             snapshot(room=reading(30, Unit.CELSIUS)), policy(), state()),
            ("if (snapshot.return_temperature is not None\n            and snapshot.return_temperature.value is not None\n            and float(snapshot.return_temperature.value) >= policy.return_upper_c):",
             snapshot(return_temperature=reading(45, Unit.CELSIUS)), policy(), state()),
            ("if clock.monotonic < state.last_monotonic or snapshot.owner_epoch != state.owner_epoch:",
             snapshot(), policy(), state(last_monotonic=1001)),
        )
        for target, snap, config, initial in cases:
            with self.subTest(guard=target):
                self.assertIn(target, source)
                baseline = reduce(initial, event(), snap, config, clock())
                self.assertFalse(any(i.action is Action.HEAT for i in baseline.intents))
                self.assertFalse(evaluate(initial, snap, config, clock()).allowed)
                namespace = {"__name__": "wp1a_memory_mutant"}
                exec(compile(source.replace(target, "if False:"), "<synthetic-mutant>", "exec"), namespace)
                mutated = namespace["evaluate"](initial, snap, config, clock())
                self.assertTrue(mutated.allowed, "Witness did not kill policy mutation")
