import unittest
from dataclasses import replace

from packages.contracts import Action, QualityStatus, SourceKind, Unit
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, policy, reading, snapshot, state


class ConsistencyTests(unittest.TestCase):
    def test_grid_has_its_own_age_limit_instead_of_matching_temperature_timestamps(self):
        # Review #6: a 3-second grid/temperature spread is valid within each source TTL.
        for observed, allowed in ((97, True), (89.999, False)):
            result = reduce(state(), event(), snapshot(grid_actual=reading(True, Unit.BOOLEAN,
                            observed_at=observed, received_at=100)), policy(), clock())
            self.assertEqual(result.permit.allowed, allowed)
            self.assertEqual(any(i.action is Action.HEAT for i in result.intents), allowed)

    def test_future_stale_conflicting_held_and_estimated_sources_fail_closed(self):
        base = reading(18, Unit.CELSIUS)
        invalid = (replace(base, observed_at=103), replace(base, received_at=103),
                   replace(base, quality=replace(base.quality, age_s=11)),
                   replace(base, quality=replace(base.quality, status=QualityStatus.CONFLICTING)),
                   replace(base, provenance=replace(base.provenance, kind=SourceKind.HELD, independent=False)),
                   replace(base, provenance=replace(base.provenance, kind=SourceKind.FORECAST, independent=False)))
        for bad in invalid:
            with self.subTest(reading=bad):
                result = reduce(state(), event(), snapshot(room=bad), policy(), clock())
                self.assertFalse(result.permit.allowed)

    def test_received_before_observation_and_future_snapshot_are_rejected(self):
        for snap in (snapshot(room=reading(18, Unit.CELSIUS, received_at=90)), snapshot(captured_at=103)):
            self.assertFalse(reduce(state(), event(), snap, policy(), clock()).permit.allowed)

    def test_utc_rollback_beyond_explicit_skew_stops_existing_demand(self):
        result = reduce(state(last_event_at=110, desired_action=Action.HEAT), event(),
                        snapshot(), policy(), clock())
        self.assertFalse(result.permit.allowed)
        self.assertEqual(result.state.desired_action, Action.STOP)
        self.assertIsNone(result.state.plan)
