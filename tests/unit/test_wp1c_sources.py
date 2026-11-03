import unittest
from dataclasses import replace
from datetime import datetime, date
from zoneinfo import ZoneInfo
from packages.contracts import ContractError, TimeWindow
from packages.thermal import Interval
from packages.planner import Forecast
from packages.planner.sources import (
    WeatherPoint,
    WeatherSeries,
    weather_at,
    OutageSchedule,
    day_span,
    allowed_window,
    next_available,
)
from packages.planner.policy import ComfortPolicy, windows, planning_horizon

TZ = ZoneInfo("Europe/Kyiv")
DAY = date(2026, 1, 5)


def schedule():
    span = day_span(DAY, TZ)
    return OutageSchedule(
        Forecast(span.start - 1, span.start, span, "synthetic.outages"),
        "synthetic.region",
        "synthetic.queue",
        DAY.isoformat(),
        (TimeWindow(start=span.start, end=span.start + 3600),),
        True,
        False,
    )


def status(s, w=None, **kwargs):
    return s.status(
        w or TimeWindow(start=s.header.horizon.start, end=s.header.horizon.start + 300),
        kwargs.get("region", "synthetic.region"),
        kwargs.get("queue", "synthetic.queue"),
        kwargs.get("now", s.header.received),
        TZ,
        kwargs.get("max_age", 3600),
    )


class SourceTests(unittest.TestCase):
    def test_weather_interpolation_not_extrapolation_and_issue_metadata(self):
        h = Forecast(100, 110, TimeWindow(start=110, end=1000), "synthetic.weather")
        s = WeatherSeries(
            h, (WeatherPoint(200, Interval(-10, -8)), WeatherPoint(800, Interval(0, 2)))
        )
        self.assertEqual(weather_at(s, 200, 120, 20), Interval(-10, -8))
        self.assertEqual(weather_at(s, 500, 120, 20), Interval(-5, -3))
        for at, now, age in (
            (900, 120, 20),
            (110, 120, 20),
            (1001, 120, 20),
            (500, 121, 20),
            (500, 99, 20),
            (500, 105, 20),
        ):
            self.assertIsNone(weather_at(s, at, now, age))
        self.assertEqual(s.header.horizon.end, 1000)
        for points in ((), s.points[::-1], (WeatherPoint(1001, Interval(0, 0)),)):
            with self.assertRaises(ContractError):
                replace(s, points=points)
        with self.assertRaises(ContractError):
            WeatherPoint(1, 0)

    def test_outage_empty_unknown_scope_stale_emergency_and_content_dedup(self):
        s = schedule()
        start = s.header.horizon.start
        self.assertEqual(status(s), "scheduled_off")
        self.assertEqual(status(replace(s, outages=())), "normal")
        self.assertEqual(
            status(replace(s, outages=(), coverage_known=False)), "unknown"
        )
        self.assertEqual(status(replace(s, emergency=True)), "emergency")
        for altered, kwargs in (
            (s, dict(region="other")),
            (s, dict(queue="other")),
            (s, dict(now=start + 4000)),
            (s, dict(now=start - 2)),
            (replace(s, local_day="2026-01-06"), {}),
            (replace(s, header=replace(s.header, received=start + 1)), dict(now=start)),
        ):
            self.assertEqual(status(altered, **kwargs), "unknown")
        self.assertEqual(status(s, TimeWindow(start=start - 300, end=start)), "unknown")
        self.assertEqual(
            status(
                s,
                TimeWindow(
                    start=s.header.horizon.end - 150, end=s.header.horizon.end + 150
                ),
            ),
            "unknown",
        )
        # A changed publication timestamp alone is not a changed schedule.
        self.assertEqual(
            s.content_key,
            replace(
                s, header=replace(s.header, issue=start, received=start + 1)
            ).content_key,
        )
        self.assertNotEqual(s.content_key, replace(s, outages=()).content_key)
        with self.assertRaises(ContractError):
            replace(s, coverage_known=1)
        with self.assertRaises(ContractError):
            replace(s, outages=s.outages * 2)
        with self.assertRaises(ValueError):
            replace(s, local_day="bad")
        self.assertEqual(
            next_available(
                (s,), start, "synthetic.region", "synthetic.queue", start, TZ, 3600
            ),
            start + 3600,
        )
        self.assertIsNone(
            next_available(
                (replace(s, coverage_known=False),),
                start,
                "synthetic.region",
                "synthetic.queue",
                start,
                TZ,
                3600,
            )
        )
        self.assertIsNone(
            next_available(
                (replace(s, emergency=True),),
                start,
                "synthetic.region",
                "synthetic.queue",
                start,
                TZ,
                3600,
            )
        )
        with self.assertRaises(ContractError):
            next_available((s,) * 5, start, "r", "q", start, TZ, 3600)

    def test_dst_day_windows_repeated_hour_and_strict_night_comfort(self):
        self.assertEqual(
            day_span(date(2026, 3, 29), TZ).end - day_span(date(2026, 3, 29), TZ).start,
            23 * 3600,
        )
        self.assertEqual(
            day_span(date(2026, 10, 25), TZ).end
            - day_span(date(2026, 10, 25), TZ).start,
            25 * 3600,
        )
        self.assertEqual(allowed_window(DAY, 0, 0, TZ), ())
        self.assertEqual(
            allowed_window(DAY, 1380, 420, TZ)[0].end
            - allowed_window(DAY, 1380, 420, TZ)[0].start,
            8 * 3600,
        )
        with self.assertRaises(ContractError):
            allowed_window(DAY, True, 100, TZ)
        # Nonexistent spring local hour fails instead of silently changing the window.
        with self.assertRaises(ContractError):
            allowed_window(date(2026, 3, 29), 210, 270, TZ)
        span = day_span(DAY, TZ)
        strict = (TimeWindow(start=span.start - 600, end=span.start + 600),)
        self.assertEqual(
            windows(DAY, TZ, "strict", strict),
            (TimeWindow(start=span.start, end=span.start + 600),),
        )
        self.assertEqual(
            windows(DAY, TZ, "strict", (TimeWindow(start=span.end, end=span.end + 1),)),
            (),
        )
        self.assertEqual(windows(DAY, TZ, "comfort", ()), (span,))
        self.assertEqual(
            sum(w.end - w.start for w in windows(DAY, TZ, "night", ())), 8 * 3600
        )
        with self.assertRaises(ContractError):
            windows(DAY, TZ, "unknown", ())

    def test_comfort_sleep_cross_midnight_and_horizon_reserve(self):
        p = ComfortPolicy(21, 19, 25, 1380, 420)
        for hour, target in ((23, 19), (0, 19), (6, 19), (7, 21), (12, 21)):
            self.assertEqual(p.target(datetime(2026, 1, 5, hour, tzinfo=TZ)), target)
        daytime = replace(p, sleep_start_minute=600, sleep_end_minute=660)
        self.assertEqual(daytime.target(datetime(2026, 1, 5, 10, tzinfo=TZ)), 19)
        self.assertEqual(
            replace(p, sleep_start_minute=420).target(
                datetime(2026, 1, 5, 6, tzinfo=TZ)
            ),
            21,
        )
        with self.assertRaises(ContractError):
            p.target(datetime(2026, 1, 5))
        with self.assertRaises(ContractError):
            replace(p, upper=19)
        with self.assertRaises(ContractError):
            replace(p, sleep_start_minute=1440)
        for available, reserve, duration, conditional in (
            (1000, 300, 86400, False),
            (200000, 300, 199300, False),
            (None, 300, 259200, True),
            (300000, 300, 259200, True),
        ):
            horizon, uncertain = planning_horizon(1000, available, reserve)
            self.assertEqual(horizon.end - horizon.start, duration)
            self.assertEqual(uncertain, conditional)
        for available, reserve in ((999, 0), (1000, 259201)):
            with self.assertRaises(ContractError):
                planning_horizon(1000, available, reserve)

    def test_auto_effective_power_requires_explicit_calibration(self):
        from packages.planner.policy import power_scenarios

        self.assertEqual(power_scenarios("AUTO", None, False), ())
        self.assertEqual(power_scenarios("AUTO", 5, False), ())
        self.assertEqual(power_scenarios("AUTO", 5, True), (5,))
        self.assertEqual(power_scenarios("compare", None, False), (3, 6, 9))
        for choice in ("3", "6", "9"):
            self.assertEqual(power_scenarios(choice, None, False), (float(choice),))
        for choice, kw, cal in (
            ("real-stage", None, False),
            ("AUTO", 0, True),
            ("AUTO", 5, 1),
        ):
            with self.assertRaises(ContractError):
                power_scenarios(choice, kw, cal)
