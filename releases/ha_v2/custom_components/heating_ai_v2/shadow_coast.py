"""Bounded diagnostic ONLY: inherited model no-boiler coasting scenario.

Never an execution forecast or an immutable original curve.
Assumptions (zero heater, no fire/ventilation/solar gain) are explicit and not
validated for accuracy. Exact real HA weather points are interpolated only
inside their known time range, with no extrapolation past a missing hour.
"""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from .engine.thermal import Coefficients, Forcing, Interval, ThermalState, step


def recently_reported(row: dict[str, Any] | None, now: float) -> bool:
    """HA source may remain cached without a new room/stored report."""
    stamp = (row or {}).get("last_reported")
    if not isinstance(stamp, str):
        return False
    try:
        reported = datetime.fromisoformat(stamp)
        return (reported.tzinfo is not None and
                0 <= now - reported.timestamp() <= 4 * 3600)
    except (ValueError, OverflowError, TypeError):
        return False


def _val(value: Any, low: float, high: float) -> float | None:
    if type(value) not in (float, int) or not isfinite(value):
        return None
    return float(value) if low <= value <= high else None


def _temperature(rows: list[dict[str, float]], at: float) -> float | None:
    for left, right in zip(rows, rows[1:]):
        if left["at"] <= at <= right["at"]:
            if right["at"] - left["at"] > 7200:
                return None  # Provider has a missing hour.
            proportion = (at - left["at"]) / (right["at"] - left["at"])
            return left["outside_c"] + (right["outside_c"] - left["outside_c"]) * proportion
    return None


def preview(room: float | None, stored: float | None,
            coefficients: dict[str, Any] | None,
            weather: dict[str, Any] | None, now: float) -> dict[str, Any]:
    """Fixed-size immutable-meaning scenario summary, not a heat plan."""
    empty = {
        "status": "UNAVAILABLE",
        "forecast_qualified": False,
        "commands_enabled": False,
        "model_calibration": "NOT_PARITY_VERIFIED",
        "temperature_min_c": None,
        "temperature_end_c": None,
        "end_at": None,
        "hours_covered": 0,
        "scenario": "no_boiler_no_fire_no_ventilation_no_external_gain",
    }
    if (room is None or stored is None or not isinstance(coefficients, dict)
            or not weather or not isfinite(now)):
        return empty
    if not -30 <= room <= 60 or not -30 <= stored <= 90:
        return empty
    if not 0 <= now - weather.get("received_at", -1) <= 7200:
        return empty
    points = weather.get("hours")
    if not isinstance(points, list) or len(points) < 2 or len(points) > 72:
        return empty
    parameters = {}
    for key, low, high in (
        ("floor_air", 0.001, 0.2), ("room_loss", 0.001, 0.15),
        ("floor_decay", 0.01, 1.5), ("heat_gain", 0.02, 3),
        ("fire_gain", 0, 0.15),
    ):
        value = _val(coefficients.get(key), low, high)
        if value is None:
            return empty
        parameters[key] = value
    revision = coefficients.get("version")
    if type(revision) is not int or revision < 0 or revision > 100000:
        return empty

    model = Coefficients(
        **parameters, revision=revision, version=1,
        calibration="NOT_PARITY_VERIFIED",
    )
    horizon = min(now + 86400, points[-1]["at"])
    if horizon <= now + 300 or _temperature(points, now) is None:
        return empty
    state = ThermalState(
        room=Interval(room, room), stored=Interval(stored, stored),
        at=now, observed_at=now, estimated=True,
    )
    minimum = room
    steps = 0
    while state.at < horizon and steps < 288:
        length = min(300, horizon - state.at)
        outside = _temperature(points, state.at + length / 2)
        if outside is None:
            break
        forcing = Forcing(
            outside=Interval(outside, outside),
            power_kw=Interval(0, 0), fire_delta=Interval(0, 0),
            ventilation_loss=Interval(0, 0),
            quality_valid=False, external_gain=Interval(0, 0),
        )
        state = step(state, forcing, model, length)
        minimum = min(minimum, state.room.low)
        steps += 1
    if steps == 0:
        return empty
    return {
        **empty,
        "status": "UNQUALIFIED_CONDITIONAL_COAST",
        "temperature_min_c": round(minimum, 2),
        "temperature_end_c": round(state.room.low, 2),
        "end_at": state.at,
        "hours_covered": round((state.at - now) / 3600, 2),
    }
