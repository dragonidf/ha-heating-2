import json, unittest, random
from dataclasses import replace
from packages.contracts import ContractError
from packages.thermal import Interval
from packages.thermal.wire import encode, decode, _decode
from packages.planner import solve, Curve, References
from packages.planner.sources import WeatherPoint, WeatherSeries
from packages.planner.evidence import recommend, CycleBudget
from packages.planner.policy import ComfortPolicy
from packages.fan_policy import FanState, FanPolicy, reduce_fan
from packages.learning import evaluate, promote
from tests.fixtures.wp1c import request, model, thermal, forcing
from tests.unit.test_learning import candidate, points, gate, backtests, stamp, TZ
from tests.unit.test_wp1c_sources import schedule


class WP1CWireTests(unittest.TestCase):
    def test_all_records_roundtrip_preserves_none_zero_and_schema(self):
        r = request()
        p = solve(r)
        c = candidate()
        q = gate(c)
        curve = Curve(
            "synthetic.curve",
            100,
            ((100, Interval(20, 21)), (200, Interval(21, 22))),
            "a" * 64,
        )
        fs = FanState(0, 0)
        policy = FanPolicy(38, 42, 50)
        qualified = evaluate(c, backtests(), ("winter/vent/fire/3",), stamp(20), TZ)
        promotion = promote(
            model(),
            c,
            qualified,
            approved=True,
            backtests=backtests(),
            regimes=("winter/vent/fire/3",),
            as_of=stamp(20),
            timezone=TZ,
        )
        records = (
            recommend(p, r),
            CycleBudget(20, 15, 0, 21),
            Interval(0, 0),
            model(),
            thermal(),
            forcing(),
            r.stamp,
            r.weather,
            r.slots[0],
            r.morning,
            r,
            p,
            curve,
            References("2026-01-05", curve, curve, None, curve),
            points()[0],
            q.metrics[0],
            c,
            q,
            promotion,
            fs,
            policy,
            reduce_fan(
                fs,
                60,
                5,
                valid=True,
                grid=True,
                armed=True,
                permitted=True,
                mode="auto",
                night=False,
                night_request=False,
                policy=policy,
            ),
            backtests()[0],
            WeatherPoint(r.state.at, Interval(0, 1)),
            WeatherSeries(r.weather, (WeatherPoint(r.state.at, Interval(0, 1)),)),
            schedule(),
            ComfortPolicy(21, 19, 25, 1380, 420),
        )
        from packages.learning import Transition

        records += (Transition("2026-01-01", 100, 400, 20, 25, -5, 3, 0, 20, 25, True),)
        for record in records:
            with self.subTest(kind=type(record).__name__):
                payload = encode(record)
                self.assertEqual(decode(payload), record)
                self.assertEqual(json.loads(payload)["version"], [1, 0])
        self.assertIsNone(decode(encode(replace(r, budget_kwh=None))).budget_kwh)
        self.assertEqual(decode(encode(replace(r, budget_kwh=0))).budget_kwh, 0)

    def test_corrupt_unknown_duplicate_nonfinite_and_type_confused_are_rejected(self):
        valid = json.loads(encode(request()))
        variants = (
            "[",
            '{"version":[1,0],"version":[1,0]}',
            encode(model()).replace("0.04", "NaN"),
            encode(model()).replace("0.04", "Infinity"),
            '"' + ("x" * 524289) + '"',
        )
        for bad in variants:
            with self.assertRaises(ContractError):
                decode(bad)
        for change in (
            dict(version=[True, 0]),
            dict(version=[2, 0]),
            dict(type="FakeActuator"),
            dict(extra="unknown"),
            dict(data=[]),
        ):
            with self.assertRaises(ContractError):
                decode(json.dumps(valid | change))
        for path, value in (
            ("armed", 1),
            ("beam", True),
            ("actual_grid", "true"),
            ("budget_kwh", "0"),
            ("unexpected", 1),
        ):
            with self.assertRaises(ContractError):
                decode(json.dumps(valid | dict(data=valid["data"] | {path: value})))
        missing = valid["data"].copy()
        del missing["state"]
        with self.assertRaises(ContractError):
            decode(json.dumps(valid | dict(data=missing)))
        bad = json.loads(encode(request()))
        bad["data"]["return_probe"]["unit"] = "not-a-unit"
        with self.assertRaises(ContractError):
            decode(json.dumps(bad))
        bad["data"]["return_probe"]["unit"] = 0
        with self.assertRaises(ContractError):
            decode(json.dumps(bad))
        with self.assertRaises(ContractError):
            encode(object())
        with self.assertRaises(ContractError):
            _decode([1] * 4097, tuple[int, ...])
        with self.assertRaises(ContractError):
            _decode([1], tuple[int, int])
        with self.assertRaises(ContractError):
            _decode(0, type(None))
        with self.assertRaises(ContractError):
            _decode(0, complex)
        bad = json.loads(encode(gate()))
        bad["data"]["outcome"] = "forced"
        with self.assertRaises(ContractError):
            decode(json.dumps(bad))
        # Default algorithm budget may be absent without removing required safety fields.
        clean = valid["data"].copy()
        del clean["beam"]
        self.assertEqual(decode(json.dumps(valid | dict(data=clean))).beam, 4)

    def test_seeded_bounded_payload_fuzz_never_produces_unvalidated_record(self):
        rng = random.Random(1103)
        payload = encode(request())
        for _ in range(120):
            where = rng.randrange(len(payload))
            mutated = payload[:where] + rng.choice('x{}[]0"') + payload[where + 1 :]
            try:
                record = decode(mutated)
            except ContractError:
                continue
            self.assertEqual(decode(encode(record)), record)

    def test_full_72h_request_and_trajectory_roundtrip_with_bounded_payload(self):
        r = request(hours=72)
        payload = encode(r)
        self.assertGreater(len(payload), 262144)
        self.assertLess(len(payload), 524288)
        self.assertEqual(decode(payload), r)
        p = solve(r)
        self.assertEqual(decode(encode(p)), p)
