"""Seeded synthetic invariants. No household samples or property-test dependency."""
import random
import unittest
from dataclasses import replace
from itertools import product

from packages.contracts import (
    Action, ControlMode, EventKind, QualityStatus, Unit, from_json, to_json,
)
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, policy, reading, snapshot, state


class InvariantTests(unittest.TestCase):
    def test_permission_grid_quality_matrix_has_no_unauthorized_heat(self):
        count = 0
        for armed, automatic, mode, grid, quality in product(
            (False, True), (False, True), tuple(ControlMode), (None, False, True), tuple(QualityStatus)
        ):
            r = reading(18, Unit.CELSIUS)
            r = replace(r, quality=replace(r.quality, status=quality))
            p = policy(armed=armed, allow_automatic=automatic, operating_mode=mode)
            s = snapshot(room=r, grid_actual=reading(grid, Unit.BOOLEAN), forecast_grid=True)
            result = reduce(state(), event(), s, p, clock())
            authorized = armed and automatic and mode is ControlMode.AUTO and grid is True and quality is QualityStatus.VALID
            self.assertEqual(result.permit.allowed, authorized)
            self.assertFalse(any(i.action is Action.HEAT for i in result.intents) and not authorized)
            self.assertEqual(result, reduce(state(), event(), s, p, clock()))
            if mode is ControlMode.SHADOW:
                self.assertEqual(result.intents, ())
            count += 1
        self.assertEqual(count, 300)

    def test_seeded_boundaries_are_deterministic_and_safety_dominates_min_on(self):
        rng = random.Random(20261103)
        for _ in range(2000):
            room = rng.choice((None, 0, 29.9, 30, 30.1, 80))
            return_c = rng.choice((None, 0, 44.9, 45, 45.1, 80))
            hard_stop = rng.choice((False, True))
            s = snapshot(room=reading(room, Unit.CELSIUS),
                         return_temperature=reading(return_c, Unit.CELSIUS), hard_stop=hard_stop)
            initial = state(desired_action=Action.HEAT, changed_at_monotonic=999.9)
            result = reduce(initial, event(kind=EventKind.STOP_REQUEST), s, policy(), clock())
            unsafe = hard_stop or room is None or return_c is None or room >= 30 or return_c >= 45
            self.assertEqual(result.state.desired_action is Action.STOP, unsafe)
            self.assertEqual(result, reduce(initial, event(kind=EventKind.STOP_REQUEST), s, policy(), clock()))
            self.assertEqual(from_json(to_json(result)), result)

    def test_seeded_replay_cannot_steal_manual_authority(self):
        rng = random.Random(5)
        manual = reduce(state(), event(kind=EventKind.MANUAL_CHANGE), snapshot(), policy(), clock()).state
        for _ in range(1000):
            old = event(kind=rng.choice((EventKind.TICK, EventKind.RESUME, EventKind.RECONCILE)),
                        sequence=rng.randrange(1, 100), authorized=True)
            result = reduce(manual, old, snapshot(owner_epoch=6), policy(), clock())
            self.assertTrue(result.state.manual_paused)
            self.assertEqual(result.state.owner_epoch, 6)
            self.assertFalse(result.intents)

    def test_generated_wire_corruption_cannot_become_a_valid_reading(self):
        import json
        rng = random.Random(101)
        invalid = ("unit", "physical_id", "observed_at", "quality", "provenance")
        for _ in range(500):
            payload = json.loads(to_json(reading()))
            del payload["data"][rng.choice(invalid)]
            from packages.contracts import ContractError
            with self.assertRaises(ContractError):
                from_json(json.dumps(payload))
