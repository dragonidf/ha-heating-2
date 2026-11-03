import random
import unittest
from dataclasses import replace, FrozenInstanceError
from packages.contracts import ContractError
from packages.thermal import Interval, step, observe
from packages.fan_policy import FanState, FanPolicy, reduce_fan
from tests.fixtures.wp1c import model, forcing, thermal


class ThermalTests(unittest.TestCase):
    def test_pinned_legacy_equations_at_synthetic_points(self):
        rng = random.Random(11)
        m = model()
        for _ in range(100):
            r = rng.uniform(10, 30)
            f = rng.uniform(15, 40)
            o = rng.uniform(-25, 30)
            kw = rng.choice((0, 3, 6, 9))
            fire = rng.uniform(-2, 12)
            result = step(
                thermal(room=r, stored=f),
                forcing(
                    outside=Interval(o, o),
                    power_kw=Interval(kw, kw),
                    fire_delta=Interval(fire, fire),
                ),
                m,
                300,
            )
            self.assertAlmostEqual(
                result.room.low,
                r + (0.04 * (f - r) - 0.02 * (r - o) + 0.02 * max(0, fire)) / 12,
            )
            self.assertAlmostEqual(
                result.stored.low, f + (0.6 * kw - 0.1 * (f - r)) / 12
            )
            self.assertTrue(result.room.exact)

    def test_uncertainty_encloses_all_corners_and_never_manufactures_validity(self):
        s = thermal(room=19, stored=24)
        wide = replace(s, room=Interval(18, 20), stored=Interval(23, 25))
        force = forcing(
            outside=Interval(-10, 0),
            power_kw=Interval(0, 9),
            ventilation_loss=Interval(0, 1),
            quality_valid=False,
        )
        out = step(wide, force, model(), 300)
        self.assertTrue(out.estimated)
        self.assertLess(out.room.low, out.room.high)
        for r in (18, 20):
            for f in (23, 25):
                for o in (-10, 0):
                    for p in (0, 9):
                        point = step(
                            thermal(room=r, stored=f),
                            forcing(outside=Interval(o, o), power_kw=Interval(p, p)),
                            model(),
                            300,
                        )
                        self.assertLessEqual(out.room.low, point.room.low)
                        self.assertGreaterEqual(out.room.high, point.room.high)
        coast = observe(s, force, model(), s.at + 7200)
        self.assertEqual(coast.observed_at, s.observed_at)
        self.assertTrue(coast.estimated)
        self.assertEqual(observe(s, force, model(), s.at).at, s.at)

    def test_invalid_ranges_and_schema_never_clip(self):
        for low, high in ((2, 1), (float("nan"), 1), (0, float("inf"))):
            with self.assertRaises(ContractError):
                Interval(low, high)
        for key, value in (
            ("floor_air", 0),
            ("room_loss", 1),
            ("floor_decay", 2),
            ("heat_gain", 0),
            ("fire_gain", 0.2),
            ("version", 2),
            ("calibration", "verified_house"),
        ):
            with self.subTest(key=key), self.assertRaises(ContractError):
                model(**{key: value})
        for seconds in (0, 301, -1, float("nan")):
            with self.assertRaises(ContractError):
                step(thermal(), forcing(), model(), seconds)
        for until in (99999, 100000 + 259201):
            with self.assertRaises(ContractError):
                observe(thermal(), forcing(), model(), until)
        for kwargs in (
            dict(power_kw=Interval(-1, 0)),
            dict(ventilation_loss=Interval(-1, 0)),
            dict(quality_valid=1),
        ):
            with self.assertRaises(ContractError):
                forcing(**kwargs)
        for kwargs in (
            dict(estimated=1),
            dict(observed_at=100001),
            dict(room=Interval(-300, -299)),
        ):
            with self.assertRaises(ContractError):
                thermal(**kwargs)
        with self.assertRaises(FrozenInstanceError):
            model().revision = 99


class FanTests(unittest.TestCase):
    def call(self, previous=None, at=60, delta=6, **changes):
        values = dict(
            valid=True,
            grid=True,
            armed=True,
            permitted=True,
            mode="auto",
            night=False,
            night_request=False,
            policy=FanPolicy(38, 42, 50),
        )
        return reduce_fan(previous or FanState(0, 0), at, delta, **(values | changes))

    def test_ignition_start_intense_and_night_cap(self):
        a = self.call(delta=2)
        self.assertTrue(a.ignition)
        self.assertEqual(a.percentage, 0)
        b = self.call(a.state, 120, 5)
        self.assertEqual(b.percentage, 42)
        c = self.call(b.state, 180, 10)
        self.assertEqual(c.percentage, 50)
        self.assertEqual(self.call(c.state, 240, 11, night=True).percentage, 38)
        self.assertEqual(
            self.call(c.state, 240, 10, mode="manual", grid=None).percentage, None
        )

    def test_cooldown_fast_off_and_gap_reset(self):
        s = FanState(0, 3, True)
        for at in range(60, 361, 60):
            result = self.call(s, at, 2.9)
            s = result.state
        self.assertFalse(s.burning)
        self.assertFalse(self.call(FanState(0, 6, True), 60, 3.9).state.burning)
        gap = self.call(FanState(100, 2.9, True, 0), 200, 2.9)
        self.assertEqual(gap.state.below_since, 200)
        keep = self.call(FanState(0, 3, True, 0), 60, 3)
        self.assertTrue(keep.state.burning)
        self.assertIsNone(keep.state.below_since)

    def test_night_dedup_and_fire_arbitration(self):
        a = self.call(at=1, delta=0, night_request=True)
        self.assertEqual(a.state.night_until, 901)
        b = self.call(a.state, 500, 0, night_request=True)
        self.assertEqual(b.state.night_until, 901)
        c = self.call(b.state, 902, 0, night_request=True)
        self.assertEqual(c.percentage, 0)
        d = self.call(c.state, 903, 6, night_request=False)
        self.assertEqual(d.percentage, 42)
        self.assertEqual(
            self.call(d.state, 1000, 6, night_request=True).state.night_until, 1900
        )
        stop = self.call(d.state, 1000, 6, mode="stop")
        self.assertEqual(stop.percentage, 0)
        self.assertFalse(stop.state.burning)

    def test_permissions_unknown_and_bad_input(self):
        for values in (
            dict(grid=None),
            dict(grid=False),
            dict(armed=False),
            dict(permitted=False),
        ):
            self.assertEqual(self.call(**values).percentage, 0)
        invalid = self.call(FanState(0, 6, True), valid=False)
        self.assertEqual(invalid.percentage, 0)
        self.assertFalse(invalid.state.sensor_valid)
        self.assertTrue(
            invalid.state.burning
        )  # unknown does not claim physical extinguishing
        self.assertEqual(self.call(delta=None).percentage, 0)
        self.assertEqual(self.call(FanState(0, 10, True), 100, 10).percentage, 42)
        self.assertEqual(self.call(FanState(0, 11, True), 60, 10).percentage, 42)
        for values in (
            dict(at=0),
            dict(mode="invalid"),
            dict(valid=1),
            dict(grid=1),
            dict(delta=float("nan")),
        ):
            with self.assertRaises(ContractError):
                self.call(**values)
        with self.assertRaises(ContractError):
            FanPolicy(50, 42, 38)
        with self.assertRaises(ContractError):
            FanState(-1, 0)

    def test_exact_hysteresis_edges_and_stale_sensor_recovery(self):
        self.assertFalse(
            self.call(FanState(0, 1.2), 60, 2).ignition
        )  # strict slope > .8
        self.assertTrue(self.call(FanState(0, 1.19), 60, 2).ignition)
        self.assertTrue(
            self.call(FanState(0, 6, True), 60, 4).state.burning
        )  # fast-off only below 4
        self.assertFalse(self.call(FanState(0, 5.9, True), 60, 3.9).state.burning)
        self.assertEqual(self.call(FanState(0, 10, True), 90, 10).percentage, 50)
        self.assertEqual(self.call(FanState(0, 10, True), 91, 10).percentage, 42)
        stale = self.call(FanState(0, 6, True), 60, None)
        recovered = self.call(stale.state, 120, 10)
        self.assertEqual(
            recovered.percentage, 42
        )  # no invented trend across missing sample
        self.assertEqual(self.call(recovered.state, 180, 10).percentage, 50)
        with self.assertRaises(ContractError):
            FanState(0, 3, True, 1)


class ExternalGainTests(unittest.TestCase):
    def test_unknown_external_gain_is_an_interval_not_invented_solar_measurement(self):
        s = thermal()
        f = forcing(external_gain=Interval(-0.2, 0.5), quality_valid=False)
        p = step(s, f, model(), 300)
        low = step(s, forcing(external_gain=Interval(-0.2, -0.2)), model(), 300)
        high = step(s, forcing(external_gain=Interval(0.5, 0.5)), model(), 300)
        self.assertEqual(p.room.low, low.room.low)
        self.assertEqual(p.room.high, high.room.high)
        self.assertTrue(p.estimated)
