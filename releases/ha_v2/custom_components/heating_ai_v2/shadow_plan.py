"""Read-only, explicitly UNQUALIFIED planning scenario on real HA provider data.

Invokes the accepted pure planner; does not publish a Plan, dispatch an
intent, or qualify an unknown model/provider/physical safety witness.
All limits here are *virtual diagnostics*, never actuator cut-offs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

from .engine.contracts import Revisions, TimeWindow
from .engine.planner import Forecast, Morning, Request, Slot, Stamp, cycle, solve
from .engine.planner.sources import allowed_window
from .engine.thermal import Coefficients, Forcing, Interval, ThermalState
from .shadow_coast import _temperature, _val, recently_reported

KYIV = ZoneInfo("Europe/Kyiv")
MAX_STEPS = 288
MAX_SEGMENTS_UI = 12
STEP = 300
STRATEGIES = {
    "Тільки в дозволені години": "strict",
    "Переважно вночі": "night",
    "Комфорт протягом доби": "comfort",
}
POWER = {"fixed_3": 3.0, "fixed_6": 6.0, "fixed_9": 9.0}
REQUIRED = (
    "day_target", "night_target", "day_upper", "night_upper",
    "sleep_start", "sleep_end", "heating_start", "heating_end",
    "strategy", "power_model",
)


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "status": "BLOCKED_INPUTS", "reason": reason, "segments": [],
        "segment_count": 0, "segments_truncated": False,
        "nominal_energy_kwh": None, "projected_min_c": None,
        "morning_heating_minutes": None, "horizon_hours": 0,
        "model_qualified": False, "grid_forecast_qualified": False,
        "weather_issued_known": False, "physical_limits_qualified": False,
        "proposal_is_command": False, "commands_sent": 0,
    }


def _scalar(row: Any, lo: float, hi: float) -> float | None:
    if not isinstance(row, dict):
        return None
    try:
        val = float(row["state"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return val if isfinite(val) and lo <= val <= hi else None


def _minutes(row: Any) -> int | None:
    raw = row.get("state") if isinstance(row, dict) else None
    if not isinstance(raw, str):
        return None
    parts = raw.split(":")
    if len(parts) != 3 or any(not s.isdecimal() for s in parts):
        return None
    h, m, sec = map(int, parts)
    if not (0 <= h < 24 and 0 <= m < 60 and sec == 0):
        return None
    return h * 60 + m


def _model(parameters: Any) -> Coefficients | None:
    if not isinstance(parameters, dict):
        return None
    bounds = {
        "floor_air": (0.001, 0.2), "room_loss": (0.001, 0.15),
        "floor_decay": (0.01, 1.5), "heat_gain": (0.02, 3.0),
        "fire_gain": (0, 0.15),
    }
    numbers = {k: _val(parameters.get(k), *bound) for k, bound in bounds.items()}
    rev = parameters.get("version")
    if any(v is None for v in numbers.values()) or type(rev) is not int or not 0 <= rev < 100000:
        return None
    return Coefficients(**numbers, revision=rev, calibration="NOT_PARITY_VERIFIED")


def _allowed(start: float, end: float, strategy: str, start_min: int, end_min: int):
    if strategy == "comfort":
        return (TimeWindow(start=start, end=end),)
    if strategy == "night":
        start_min, end_min = 23 * 60, 7 * 60
    day = datetime.fromtimestamp(start, KYIV).date()
    result = []
    for offset in range(-1, 4):
        for span in allowed_window(day + timedelta(days=offset), start_min, end_min, KYIV):
            a, b = max(start, span.start), min(end, span.end)
            if a < b:
                result.append(TimeWindow(start=a, end=b))
    result.sort(key=lambda w: w.start)
    if not result or len(result) > 256:
        return ()
    return tuple(result)


def conditional_plan(
    rows: dict[str, dict[str, Any] | None],
    weather: dict[str, Any] | None,
    outages: dict[str, Any] | None,
    now: float,
) -> dict[str, Any]:
    """One finite scenario: never use this result as a heater decision."""
    empty = _blocked("missing_real_inputs")
    if not isinstance(now, (float, int)) or not isfinite(now) or now <= 0:
        return empty
    if not isinstance(weather, dict) or not 0 <= now - weather.get("received_at", -1) <= 3600:
        return _blocked("weather_unavailable_or_old")
    hours = weather.get("hours")
    if not isinstance(hours, list) or not 2 <= len(hours) <= 72:
        return _blocked("weather_horizon_missing")

    values = {name: rows.get(name) for name in REQUIRED}
    if any(value is None for value in values.values()):
        return _blocked("settings_not_bound")
    nums = {
        name: _scalar(values[name], 10, 32)
        for name in ("day_target", "night_target", "day_upper", "night_upper")
    }
    if (any(v is None for v in nums.values())
            or nums["day_upper"] <= nums["day_target"]
            or nums["night_upper"] <= nums["night_target"]):
        return _blocked("invalid_comfort_bands")
    times = {name: _minutes(values[name]) for name in
             ("sleep_start", "sleep_end", "heating_start", "heating_end")}
    if any(value is None for value in times.values()):
        return _blocked("invalid_local_time")
    strategy = STRATEGIES.get(values["strategy"].get("state"))
    power = POWER.get(values["power_model"].get("state"))
    if strategy is None or power is None:
        return _blocked("strategy_or_power_unqualified")
    if (not recently_reported(rows.get("room"), now)
            or not recently_reported(rows.get("stored_heat"), now)
            or not recently_reported(rows.get("legacy_model"), now)):
        return _blocked("room_stored_or_model_old")

    room = _scalar(rows["room"], -30, 60)
    stored = _scalar(rows["stored_heat"], -30, 90)
    model_attrs = (rows["legacy_model"] or {}).get("attributes") or {}
    model = _model(model_attrs.get("parameters"))
    if room is None or stored is None or model is None:
        return _blocked("thermal_inputs_unqualified")

    horizon_end = min(now + 86400, hours[-1]["at"])
    # No extrapolation: if the real weather provider has gaps, truncate there.
    slots = []
    cursor = now
    valid_outages = (
        outages if isinstance(outages, dict)
        and outages.get("status") == "OUTAGE_EVENTS_ONLY"
        and 0 <= now - outages.get("received_at", -1) <= 7200
        else None
    )
    while cursor + STEP <= horizon_end and len(slots) < MAX_STEPS:
        next_at = cursor + STEP
        outside = _temperature(hours, cursor + STEP / 2)
        if outside is None:
            break
        local = datetime.fromtimestamp(cursor, KYIV)
        minute = local.hour * 60 + local.minute
        a, b = times["sleep_start"], times["sleep_end"]
        sleeping = a <= minute < b if a < b else minute >= a or minute < b
        target = nums["night_target"] if sleeping else nums["day_target"]
        upper = nums["night_upper"] if sleeping else nums["day_upper"]
        announced_outage = bool(
            valid_outages and any(
                o["start"] < next_at and cursor < o["end"]
                for o in valid_outages["outages"]
            )
        )
        slots.append(Slot(
            window=TimeWindow(start=cursor, end=next_at),
            forcing=Forcing(
                outside=Interval(outside, outside),
                power_kw=Interval(0, 0),
                fire_delta=Interval(0, 0),
                ventilation_loss=Interval(0, 0),
                quality_valid=False,
                external_gain=Interval(0, 0),
            ),
            grid="scheduled_off" if announced_outage else "unknown",
            target=target, upper=upper, price=None,
        ))
        cursor = next_at
    if len(slots) < 6:
        return _blocked("weather_too_short_or_gapped")
    allowed = _allowed(now, cursor, strategy, times["heating_start"], times["heating_end"])
    if not allowed:
        return _blocked("no_allowed_windows")
    local_now = datetime.fromtimestamp(now, KYIV)
    _, morning = cycle(local_now)
    # A forecast with an unknown issue timestamp is ALWAYS marked unqualified.
    # "0" is an internal sentinel used only to force pure planner's
    # _weather_current() test to reject qualification, never exposed as issue.
    provider = Forecast(issue=0.0, received=weather["received_at"],
                        horizon=TimeWindow(start=now, end=cursor),
                        source_id="ha_hourly_issue_unknown")
    grid_state = (rows.get("grid") or {}).get("state")
    actual_grid = (True if grid_state == "Наявна мережа" else
                   False if grid_state == "Відсутня мережа" else None)
    content = {
        "room": room, "stored": stored, "model_rev": model.revision,
        "weather_received": weather["received_at"],
        "weather": [(p["at"], p["outside_c"]) for p in hours],
        "outages": valid_outages["outages"] if valid_outages else None,
        "settings": {key: values[key]["state"] for key in REQUIRED},
        "grid": actual_grid,
    }
    stamp = Stamp(
        input_hash=sha256(repr(content).encode()).hexdigest(),
        revisions=Revisions(config=0, model=model.revision, topology=0),
        boot_id="virtual-shape", owner_epoch=0, grid_epoch=0,
    )
    request = Request(
        stamp=stamp,
        state=ThermalState(
            room=Interval(room, room), stored=Interval(stored, stored),
            at=now, observed_at=now, estimated=True,
        ),
        model=model, slots=tuple(slots), weather=provider,
        allowed=allowed,
        morning=Morning(
            window=morning, advance_s=10800,
            confirmed_until=None, confirmed_s=0, confirmed_valid=False,
        ),
        stages_kw=(power,),
        stored_upper=50.0,
        armed=True, manual=False, actual_grid=actual_grid,
        budget_kwh=None, known_spent_kwh=0, spend_complete=False,
        return_probe=None, return_upper_c=65.0,
        return_max_age_s=1200, limits_qualified=True,
        state_max_age_s=300, beam=4, max_work=50000,
    )
    proposal = solve(request)
    if proposal.status in ("BLOCKED", "SEARCH_EXHAUSTED"):
        return {
            **_blocked("solver_" + proposal.reason),
            "work": proposal.work,
            "horizon_hours": round((cursor-now)/3600, 2),
        }
    segments = [
        {"start": round(s.start), "end": round(s.end),
         "conditional": True}
        for s in proposal.segments[:MAX_SEGMENTS_UI]
    ]
    return {
        **empty,
        "status": "VIRTUAL_CONDITIONAL",
        "reason": proposal.reason,
        "plan_status_internal": proposal.status,
        "scenario_power_kw": power,
        "nominal_energy_kwh": round(proposal.energy_kwh, 2),
        "projected_min_c": (
            round(min(s.room.low for s in proposal.trajectory), 2)
            if proposal.trajectory else None
        ),
        "morning_heating_minutes": round(proposal.morning_s / 60, 1),
        "horizon_hours": round((cursor - now) / 3600, 2),
        "segment_count": len(proposal.segments),
        "segments": segments,
        "segments_truncated": len(proposal.segments) > MAX_SEGMENTS_UI,
        "work": proposal.work,
        "conditional_reasons": [
            "weather_issue_unknown", "normal_grid_future_unverified",
            "legacy_model_not_parity_verified",
            "derived_stored_heat_not_direct", "physical_limit_not_qualified",
            "unknown_energy_budget_and_tariff",
            "future_fire_and_ventilation_assumed_zero",
        ],
    }


def diagnostics(
    rows: dict[str, dict[str, Any] | None],
    weather: dict[str, Any] | None,
    outages: dict[str, Any] | None,
    now: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Single worker request: accepted planner + existing coasting observer.

    Do not run either 24h model loop on HA's event loop on every sensor update.
    """
    from .shadow_coast import preview
    from .telemetry import _number
    room = (
        _scalar(rows.get("room"), -30, 60)
        if recently_reported(rows.get("room"), now) else None
    )
    stored = (
        _number(rows.get("stored_heat"), "°C", -30, 90)
        if recently_reported(rows.get("stored_heat"), now) else None
    )
    model_row = rows.get("legacy_model") or {}
    parameters = (model_row.get("attributes") or {}).get("parameters")
    coast = preview(room, stored, parameters, weather, now)
    return conditional_plan(rows, weather, outages, now), coast
