"""Read-only weather/calendar projections for the native HA v2 SHADOW.

Only native HA WeatherEntity and CalendarEntity read APIs are used. Forecast
publication time is UNKNOWN; received_at is not mislabeled issued_at.
No service registry, controller intents, fan changes, or helper writes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Iterable


MAX_WEATHER = 72
MAX_OUTAGES = 32
MAX_HORIZON_S = 72 * 3600


def _timestamp(raw: Any) -> float:
    if isinstance(raw, str):
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    elif isinstance(raw, datetime):
        parsed = raw
    else:
        raise ValueError("Missing source timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone required")
    return parsed.timestamp()


def weather_hours(items: Any, received_at: float) -> dict[str, Any]:
    """Strict hourly weather data, bounded; never invent missing hours."""
    if (not isinstance(items, list) or not 1 <= len(items) <= MAX_WEATHER
            or not isfinite(received_at) or received_at <= 0):
        raise ValueError("Missing, oversized or invalid weather forecast")
    rows = []
    previous = -1.0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid weather row")
        at = _timestamp(item.get("datetime"))
        temp = item.get("temperature")
        if (type(temp) not in (int, float) or not isfinite(temp)
                or not -60 <= temp <= 60 or at <= previous
                or not received_at - 3600 <= at <= received_at + MAX_HORIZON_S):
            raise ValueError("Stale, unordered or invalid weather point")
        rows.append({"at": at, "outside_c": float(temp)})
        previous = at
    return {
        "status": "RECEIVED_ISSUED_UNKNOWN",
        "received_at": received_at,
        "issued_at": None,
        "horizon_end": rows[-1]["at"],
        "hours": rows,
        "source_quality": "forecast_not_independent_raw_measurement",
    }


def outage_intervals(items: Any, start: float, end: float,
                     received_at: float) -> dict[str, Any]:
    """Only explicitly labeled outages. No event != verified grid available."""
    if (not isinstance(items, (tuple, list)) or len(items) > MAX_OUTAGES
            or not 0 < start < end <= start + MAX_HORIZON_S
            or not isfinite(received_at)):
        raise ValueError("Unqualified calendar window")
    result = []
    for item in items:
        if isinstance(item, dict):
            summary = item.get("summary")
            begin_raw = item.get("start")
            finish_raw = item.get("end")
        else:
            summary = getattr(item, "summary", None)
            begin_raw = getattr(item, "start", None)
            finish_raw = getattr(item, "end", None)
        if not isinstance(summary, str):
            raise ValueError("Calendar entry type unknown")
        # A non-outage event cannot be interpreted as "electricity available".
        if "відключ" not in summary.casefold() and "outage" not in summary.casefold():
            raise ValueError("Calendar event purpose not verified")
        if (type(begin_raw) is date or type(finish_raw) is date):
            raise ValueError("All-day event cannot prove timed outage")
        a, b = _timestamp(begin_raw), _timestamp(finish_raw)
        if not 0 < a < b or b - a > 86400:
            raise ValueError("Unqualified outage interval")
        if max(start, a) < min(end, b):
            result.append({"start": max(start, a), "end": min(end, b)})
    result.sort(key=lambda item: item["start"])
    for prev, nxt in zip(result, result[1:]):
        if prev["end"] > nxt["start"]:
            raise ValueError("Overlapping source outage intervals")
    return {
        "status": "OUTAGE_EVENTS_ONLY",
        "received_at": received_at,
        "coverage_known": False,
        "outages": result,
        "source_quality": "calendar_event_no_positive_grid_coverage",
    }


def source_summary(weather: dict[str, Any] | None,
                   outages: dict[str, Any] | None,
                   now: float) -> dict[str, Any]:
    """Small HA state attributes; full future curves stay in bounded RAM only."""
    latest_weather = (
        weather if weather and 0 <= now - weather["received_at"] <= 7200 else None
    )
    latest_outages = (
        outages if outages and 0 <= now - outages["received_at"] <= 7200 else None
    )
    upcoming = [
        v for v in (latest_outages or {}).get("outages", [])
        if v["end"] > now
    ]
    return {
        "weather_status": latest_weather["status"] if latest_weather else "UNKNOWN",
        "weather_horizon_end": latest_weather["horizon_end"] if latest_weather else None,
        "weather_hours_count": len(latest_weather["hours"]) if latest_weather else 0,
        "weather_issued_at": None,
        "outage_status": latest_outages["status"] if latest_outages else "UNKNOWN",
        "outages_upcoming_count": len(upcoming),
        "next_outage_at": min((v["start"] for v in upcoming if v["start"] >= now),
                              default=None),
        "normal_grid_forecast_qualified": False,
        "commands_enabled": False,
    }
