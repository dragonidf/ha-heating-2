import unittest
from packages.evidence.energy import integrate, counter_delta
from packages.offline.contracts import PowerPoint, CounterPoint


def point(at, kw=3, kind="derived", identity=None):
    return PowerPoint(
        identity or f"synthetic.p{at}",
        "synthetic.heat",
        at,
        at,
        kw,
        kind,
        ("synthetic.meter",),
        "left_hold",
    )


class EnergyTests(unittest.TestCase):
    def test_actual_timestamp_hold_is_45s_and_rest_is_unknown(self):
        result = integrate((point(100), point(400)), 100, 400, "synthetic.continuity")
        self.assertAlmostEqual(sum(s.kwh or 0 for s in result), 3 * 45 / 3600)
        self.assertEqual(
            sum(s.end - s.start for s in result if s.category == "unknown"), 255
        )
        self.assertEqual(result[0].category, "derived")

    def test_present_reading_cannot_create_past_energy(self):
        result = integrate((point(400),), 100, 400, "synthetic.continuity")
        self.assertTrue(all(s.kwh is None for s in result))

    def test_counter_reset_does_not_become_negative_energy(self):
        a = CounterPoint("synthetic.a", "synthetic.heat", 100, 50, "synthetic.meter")
        b = CounterPoint("synthetic.b", "synthetic.heat", 400, 1, "synthetic.meter")
        self.assertEqual(
            counter_delta(a, b, 12, "synthetic.continuity").category, "unknown"
        )

    def test_reordering_duplicate_alias_and_conflicting_same_time_math(self):
        from dataclasses import replace

        ordered = (point(100, 3), point(130, 6), point(160, 0))
        self.assertEqual(
            integrate(ordered, 100, 190, "x"), integrate(ordered[::-1], 100, 190, "x")
        )
        duplicate = replace(ordered[0], identity="synthetic.duplicate")
        self.assertAlmostEqual(
            sum(s.kwh or 0 for s in integrate(ordered + (duplicate,), 100, 190, "x")),
            0.075,
        )
        conflict = replace(duplicate, kw=9)
        result = integrate(ordered + (conflict,), 100, 190, "x")
        self.assertEqual(result[0].category, "unknown")
        self.assertEqual(result[0].method, "conflicting_same_time")

    def test_empty_points_and_hold_expiry_are_not_confirmed_zero(self):
        result = integrate((), 100, 200, "x", stream="synthetic.heat")
        self.assertEqual(result[0].category, "unknown")
        result = integrate((point(50),), 100, 200, "x")
        self.assertTrue(all(s.kwh is None for s in result))
        self.assertTrue(
            all(
                s.kwh is None for s in integrate((point(100),), 100, 200, "x", hold_s=0)
            )
        )

    def test_integration_is_exact_for_seeded_piecewise_constant_trajectories(self):
        import random

        rng = random.Random(20261103)
        for _ in range(50):
            points = tuple(point(100 + i * 30, rng.uniform(0, 12)) for i in range(101))
            result = integrate(points, 100, 3100, "x")
            expected = sum(p.kw * 30 / 3600 for p in points[:-1])
            self.assertAlmostEqual(sum(s.kwh or 0 for s in result), expected, places=11)
            self.assertEqual(sum(s.end - s.start for s in result), 3000)
            self.assertFalse(any(s.category == "unknown" for s in result))

    def test_stage_estimates_do_not_round_pump_or_actual_energy(self):
        from packages.evidence.energy import stage_estimate

        pulses = (point(100, 0.05), point(105, 0.05))
        self.assertIsNone(stage_estimate(pulses, (3, 6, 9), 60, 0.5))
        points = tuple(point(100 + i * 30, 9.237) for i in range(4))
        self.assertEqual(stage_estimate(points, (3, 6, 9), 60, 0.5), 9)
        self.assertAlmostEqual(
            sum(s.kwh or 0 for s in integrate(points, 100, 190, "x")), 9.237 * 90 / 3600
        )
        for samples in (
            (),
            (point(100),),
            pulses,
            (point(100, 3), point(200, 3)),
            (point(100), point(100)),
            (point(100, None, "unknown"), point(130, 3)),
            (point(100, 6), point(130, 6)),
        ):
            self.assertIsNone(stage_estimate(samples, (), 60, 0.5))
        self.assertIsNone(stage_estimate((point(100, 3), point(200, 3)), (3,), 60, 0.5))
        self.assertIsNone(
            stage_estimate((point(100, 3), point(130, 3, "estimated")), (3,), 0, 0.5)
        )
        self.assertIsNone(stage_estimate((point(100, 5), point(130, 5)), (3,), 0, 0.5))

    def test_counter_jumps_resets_and_continuity_are_explicit(self):
        from dataclasses import replace
        from packages.contracts import ContractError

        a = CounterPoint("a", "s", 100, 100, "m")
        b = replace(a, identity="b", at=400, kwh=100.5)
        self.assertEqual(counter_delta(a, b, 12, "x").kwh, 0.5)
        self.assertEqual(
            counter_delta(a, replace(b, kwh=200), 12, "x").method, "counter_jump"
        )
        for other in (
            replace(b, stream="other"),
            replace(b, source="other"),
            replace(b, at=100),
        ):
            with self.assertRaises(ContractError):
                counter_delta(a, other, 12, "x")

    def test_tariff_boundaries_missing_prices_and_estimates_are_separate(self):
        from packages.offline.contracts import Tariff, EnergySlice
        from packages.evidence.energy import dated_cost
        from dataclasses import replace

        s = EnergySlice("x", "s", "c", 100, 200, "derived", 1, ("m",), "left_hold")
        tariffs = (
            Tariff("cheap", 100, 150, 1, "SYN"),
            Tariff("dear", 150, 200, 3, "SYN"),
        )
        cost = dated_cost((s,), tariffs)
        self.assertEqual(cost.known_cost, 2)
        self.assertEqual(cost.unpriced_kwh, 0)
        self.assertEqual(dated_cost((s,), tariffs[:1]).unpriced_kwh, 0.5)
        self.assertEqual(
            dated_cost((replace(s, category="estimated"),), tariffs).estimated_cost, 2
        )
        self.assertEqual(
            dated_cost((replace(s, category="unknown", kwh=None),), tariffs).unknown_s,
            100,
        )
        self.assertEqual(
            dated_cost((replace(s, method="counter_delta"),), tariffs).known_cost, 0
        )
        self.assertEqual(
            dated_cost((replace(s, method="counter_delta"),), tariffs).estimated_cost, 2
        )
        self.assertIsNone(dated_cost((s,), ()).currency)
        from packages.contracts import ContractError

        for bad in (
            tariffs + (tariffs[0],),
            (tariffs[0], replace(tariffs[1], currency="OTHER")),
        ):
            with self.assertRaises(ContractError):
                dated_cost((s,), bad)

    def test_dst_day_split_never_invents_counter_distribution(self):
        from packages.offline.contracts import EnergySlice
        from packages.evidence.energy import local_day_slices, clip
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from dataclasses import replace

        tz = ZoneInfo("Europe/Kyiv")
        for month, day, duration in ((3, 29, 23), (10, 25, 25)):
            start = datetime(2026, month, day, tzinfo=tz).timestamp()
            end = datetime(2026, month, day + 1, tzinfo=tz).timestamp()
            self.assertEqual(end - start, duration * 3600)
            s = EnergySlice(
                "x",
                "s",
                "c",
                start - 1800,
                end + 1800,
                "confirmed",
                10,
                ("m",),
                "counter_delta",
            )
            parts = local_day_slices((s,), tz)
            self.assertEqual(len(parts), 3)
            self.assertAlmostEqual(sum(p.kwh for p in parts), 10)
            self.assertTrue(all(p.category == "estimated" for p in parts))
            self.assertEqual(clip(s, s.start, s.end).category, "confirmed")
            self.assertIsNone(clip(s, s.end, s.end + 1))

    def test_bad_numeric_scopes_and_unknown_category_cannot_be_smuggled_as_zero(self):
        from dataclasses import replace
        from packages.contracts import ContractError

        for changes in (
            dict(kw=-1),
            dict(kw=0, category="unknown"),
            dict(kw=None),
            dict(received=0),
            dict(category="recovered"),
        ):
            with self.assertRaises(ContractError):
                replace(point(100), **changes)
        for values in ((100, 100, 45), (100, 200, 46)):
            with self.assertRaises(ContractError):
                integrate((point(100),), values[0], values[1], "x", hold_s=values[2])
        with self.assertRaises(ContractError):
            integrate((), 100, 200, "x")
        with self.assertRaises(ContractError):
            integrate((point(100), replace(point(130), stream="other")), 100, 200, "x")

    def test_integrated_direct_power_is_derived_energy_not_a_direct_kwh_meter(self):
        result = integrate(
            (point(100, 3, "confirmed"), point(130, 3, "confirmed")), 100, 130, "x"
        )
        self.assertEqual(result[0].category, "derived")
        self.assertAlmostEqual(result[0].kwh, 0.025)
