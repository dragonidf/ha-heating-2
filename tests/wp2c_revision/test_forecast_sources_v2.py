"""Native provider contracts: read-only, bounded, no invented future values."""
from datetime import datetime, timezone
from pathlib import Path
import runpy
import unittest

module = runpy.run_path(str(Path("releases/ha_v2/custom_components/heating_ai_v2/forecast_sources.py")))
weather_hours = module["weather_hours"]
outage_intervals = module["outage_intervals"]
source_summary = module["source_summary"]


class ForecastSourceTests(unittest.TestCase):
    def test_real_ha_weather_format_no_forged_issue_and_no_extrapolation(self):
        now = datetime(2026, 11, 11, 21, 24, tzinfo=timezone.utc).timestamp()
        forecast = [
            {"datetime": "2026-11-11T21:00:00Z", "temperature": 3.0},
            {"datetime": "2026-11-11T22:00:00Z", "temperature": 2.9},
            {"datetime": "2026-11-11T23:00:00Z", "temperature": 2.8},
        ]
        result = weather_hours(forecast, now)
        self.assertEqual(result["status"], "RECEIVED_ISSUED_UNKNOWN")
        self.assertIsNone(result["issued_at"])
        self.assertEqual(len(result["hours"]), 3)
        self.assertEqual(result["hours"][1]["outside_c"], 2.9)
        self.assertEqual(result["horizon_end"],
                         datetime(2026, 11, 11, 23, tzinfo=timezone.utc).timestamp())
        self.assertEqual(source_summary(result, None, now)["weather_hours_count"], 3)
        self.assertEqual(source_summary(result, None, now + 7201)["weather_status"], "UNKNOWN")

    def test_weather_rejects_duplicate_unordered_bad_and_oversized(self):
        now = datetime(2026, 11, 11, 21, tzinfo=timezone.utc).timestamp()
        good = {"datetime": "2026-11-11T22:00:00Z", "temperature": 4}
        bad = [
            [good, good], [{**good, "temperature": 500}],
            [{**good, "temperature": float("nan")}],
            [{**good, "datetime": "2026-11-12T22:00:00"}],
            [{**good, "datetime": "2026-12-30T22:00:00Z"}],
            [good] * 73, [], None,
        ]
        for samples in bad:
            with self.subTest(samples=repr(samples)[:60]):
                with self.assertRaises((ValueError, TypeError)):
                    weather_hours(samples, now)

    def test_provider_can_include_last_two_hourly_rows_without_forging_issue(self):
        now = datetime(2026, 11, 11, 23, 45, tzinfo=timezone.utc).timestamp()
        weather = [
            {"datetime": "2026-11-11T22:00:00Z", "temperature": 2.6},
            {"datetime": "2026-11-11T23:00:00Z", "temperature": 2.3},
            {"datetime": "2026-11-12T00:00:00Z", "temperature": 2.2},
        ]
        result = weather_hours(weather, now)
        self.assertEqual(result["status"], "RECEIVED_ISSUED_UNKNOWN")
        self.assertEqual(len(result["hours"]), 3)
        with self.assertRaises(ValueError):
            weather_hours(weather[:-1], now)

    def test_real_outage_events_are_never_positive_power_availability(self):
        now = datetime(2026, 11, 11, 21, tzinfo=timezone.utc).timestamp()
        end = now + 48 * 3600
        data = [
            {"summary": "3.1: ❌ Відключення",
             "start": {"dateTime": "2026-11-12T03:30:00+02:00"},
             "end": {"dateTime": "2026-11-12T10:30:00+02:00"}},
        ]
        # HA native CalendarEvent uses aware datetimes, not REST dict wrappers.
        from types import SimpleNamespace
        raw = [SimpleNamespace(
            summary="3.1: ❌ Відключення",
            start=datetime.fromisoformat(data[0]["start"]["dateTime"]),
            end=datetime.fromisoformat(data[0]["end"]["dateTime"]),
        )]
        result = outage_intervals(raw, now, end, now)
        self.assertEqual(result["status"], "OUTAGE_EVENTS_ONLY")
        self.assertEqual(result["coverage_known"], False)
        self.assertEqual(len(result["outages"]), 1)
        self.assertEqual(source_summary(None, result, now)["normal_grid_forecast_qualified"], False)
        self.assertEqual(source_summary(None, result, now)["outages_upcoming_count"], 1)
        empty = outage_intervals([], now, end, now)
        self.assertFalse(empty["coverage_known"])
        self.assertEqual(source_summary(None, empty, now)["outage_status"], "OUTAGE_EVENTS_ONLY")

    def test_calendar_untrusted_events_fail_closed(self):
        now = datetime(2026, 11, 11, 21, tzinfo=timezone.utc).timestamp()
        end = now + 24 * 3600
        rows = [
            {"summary": "Без відключення, графік скасовано",
             "start": "2026-11-11T22:00:00Z",
             "end": "2026-11-11T23:00:00Z"},
            {"summary": "Зустріч", "start": "2026-11-11T22:00:00Z",
             "end": "2026-11-11T23:00:00Z"},
            {"summary": "Відключення", "start": "2026-11-11T22:00:00",
             "end": "2026-11-11T23:00:00Z"},
        ]
        for item in rows:
            with self.assertRaises((ValueError, TypeError)):
                outage_intervals([item], now, end, now)
        overlapping = [
            {"summary": "Відключення", "start": "2026-11-11T22:00:00Z",
             "end": "2026-11-12T00:00:00Z"},
            {"summary": "Outage", "start": "2026-11-11T23:00:00Z",
             "end": "2026-11-12T01:00:00Z"},
        ]
        with self.assertRaises(ValueError):
            outage_intervals(overlapping, now, end, now)


if __name__ == "__main__":
    unittest.main()
