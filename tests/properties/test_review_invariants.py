"""Synthetic boundaries for asynchronous sources, emergency trust and recovery."""
import random
import json
import unittest
from dataclasses import replace
from itertools import product
from math import inf, nextafter

from packages.contracts import Action, ContractError, EventKind, PlanSegment, from_json, to_json
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, plan, policy, snapshot, state
from tests.unit.test_recovery import fresh
from tests.unit.test_review_regressions import asynchronous_case


class ReviewInvariantTests(unittest.TestCase):
    def test_emergency_trust_scope_time_and_dedup_matrix(self):
        heated = reduce(state(), event(), snapshot(), policy(), clock()).state
        heated = replace(heated, last_event_sequence=100, last_safety_stop_sequence=5)
        count = 0
        for authorized, current_boot, current_owner, sequence, times in product(
            (False, True), (False, True), (False, True), (4, 5, 6, 101),
            ((98, 99), (98, 108), (102, 103), (102.001, 103))
        ):
            stop = event(kind=EventKind.SAFETY_STOP, authorized=authorized,
                         boot_id=heated.boot_id if current_boot else "synthetic.old",
                         owner_epoch=5 if current_owner else 4, sequence=sequence,
                         at=times[0], expires_at=times[1])
            result = reduce(heated, stop, snapshot(), policy(), clock())
            expected_stop = authorized and current_boot and current_owner and sequence > 5 and times[0] <= 102
            self.assertEqual(result.state.desired_action is Action.STOP, expected_stop)
            self.assertEqual(result.state.last_event_sequence, 100)
            self.assertEqual(result.state.owner_epoch, 5)
            if expected_stop:
                self.assertEqual(result.state.last_safety_stop_sequence, sequence)
                duplicate = reduce(result.state, stop, snapshot(), policy(), clock())
                self.assertEqual(duplicate.state, result.state)
                self.assertEqual(duplicate.intents, ())
            else:
                self.assertEqual(result.state, heated)
                self.assertEqual(result.intents, ())
            self.assertEqual(result, reduce(heated, stop, snapshot(), policy(), clock()))
            count += 1
        self.assertEqual(count, 128)

    def test_seeded_async_ages_use_each_source_budget_without_rewriting_quality(self):
        rng = random.Random(6605790334)
        initial, e, base, p, now = asynchronous_case()
        limits = dict(room=14_400, return_temperature=20, thermostat=30, grid_actual=3)
        for _ in range(500):
            ages = {role: rng.uniform(0, limit * 1.1) for role, limit in limits.items()}
            values = {}
            for role, age in ages.items():
                source = getattr(base, role)
                values[role] = replace(source, observed_at=now.utc-age, received_at=now.utc,
                                       quality=replace(source.quality, age_s=0))
            result = reduce(initial, e, replace(base, **values), p, now)
            self.assertEqual(result.permit.allowed, all(ages[r] <= limits[r] for r in ages))
            self.assertEqual(p.max_skew_s, 2)

    def test_recovery_time_and_stability_matrix_requires_both(self):
        fallback = reduce(state(plan=None, accepted_input_hash=None), event(), snapshot(), policy(), clock()).state
        count = 0
        for issued, at in product((99, 100, nextafter(100, inf), 101), (102, 103, 105)):
            proposal = plan(issued_at=issued, valid_from=issued, segments=(PlanSegment(start=101, end=110),))
            result = reduce(fallback, event(kind=EventKind.PLAN, plan=proposal, sequence=2, at=at, expires_at=at+1),
                            fresh(at), policy(), clock(utc=at, monotonic=900+at))
            self.assertEqual(result.permit.allowed, issued > 100 and at >= 103)
            count += 1
        self.assertEqual(count, 12)

    def test_emergency_frontier_is_validated_roundtripped_and_resets_with_ownership(self):
        original = state(last_safety_stop_sequence=4)
        self.assertEqual(from_json(to_json(original)), original)
        old_shape = json.loads(to_json(original))
        del old_shape["data"]["last_safety_stop_sequence"]
        self.assertEqual(from_json(json.dumps(old_shape)).last_safety_stop_sequence, -1)
        for invalid in (-2, True, 2**63):
            with self.subTest(value=invalid), self.assertRaises(ContractError):
                replace(original, last_safety_stop_sequence=invalid)
        for kind in (EventKind.MANUAL_CHANGE, EventKind.OFF, EventKind.RESUME):
            result = reduce(original, event(kind=kind, authorized=True), snapshot(), policy(), clock())
            self.assertEqual(result.state.owner_epoch, original.owner_epoch+1)
            self.assertEqual(result.state.last_safety_stop_sequence, -1)
