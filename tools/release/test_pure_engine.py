#!/usr/bin/env python3
"""Exercise the ACTUAL packaged v2 pure safety kernel without HA or a device."""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = ROOT / "p0-release" / "custom_components"
COMPONENT = COMPONENTS / "heating_ai_v2"
ENGINE = COMPONENT / "engine"


def _namespace(name: str, folder: Path) -> None:
    mod = ModuleType(name)
    mod.__path__ = [str(folder)]
    sys.modules[name] = mod


def main() -> None:
    _namespace("custom_components", COMPONENTS)
    _namespace("custom_components.heating_ai_v2", COMPONENT)
    _namespace("custom_components.heating_ai_v2.engine", ENGINE)

    manifest = json.loads((ENGINE / "SOURCE-SHA256.json").read_text())
    assert manifest["purpose"] == "accepted_pure_modules_only"
    assert manifest["installed_namespace"] == "custom_components.heating_ai_v2.engine"
    assert len(manifest["files"]) >= 20
    for relative, digest in manifest["files"].items():
        raw = (ROOT / "packages" / relative).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest, relative
    assert not (ENGINE / "ha_fake").exists()
    assert not (ENGINE / "simulator").exists()
    assert not (ENGINE / "ha_native").exists()

    ctl = importlib.import_module("custom_components.heating_ai_v2.engine.control")
    assert callable(ctl.reduce)
    mod = importlib.import_module("custom_components.heating_ai_v2.shadow_kernel")
    assert callable(mod.shadow_decision)
    for grid in (True, False, None):
        for room in (20.5, None):
            for return_c in (22.1, 109.9, None):
                for power in (0.0, 6.22, None):
                    values = {
                        "grid_last_known": grid,
                        "room_c_last_known": room,
                        "return_c_last_known": return_c,
                        "kws_total_kw_last_known": power,
                        "thermostat_mode_last_known": "heat",
                    }
                    response = mod.shadow_decision(values)
                    assert response["kernel"] == "accepted_control", response
                    assert response["mode"] == "shadow", response
                    assert response["reason"] == "shadow", response
                    assert response["permit"] is False
                    assert response["intents"] == 0
                    assert response["actual_commands_sent"] == 0
                    assert response["physical_authority"] is False
                    assert len(response["unverified_sources"]) == 5

    fan = importlib.import_module("custom_components.heating_ai_v2.fan_shadow")
    values = {
        "fan_mode_last_known": "Зупинити",
        "fan_speed_percent_last_known": {
            "fan_night": 38., "fan_standard": 42., "fan_intense": 45.,
        },
        "fireplace_delta_c_last_known": 6.0,
        "grid_last_known": True,
        "fan_control_enabled_last_known": True,
        "fan_backup_verified_last_known": True,
    }
    prior, reading = fan.project(values, None, 10_000.0, 14)
    assert prior is not None
    assert reading["percentage_proposed"] == 0
    assert reading["reason"] == "explicit_stop"
    assert reading["physical_authority"] is False and reading["commands_sent"] == 0
    values["fan_mode_last_known"] = "Авто"
    prior, reading = fan.project(values, prior, 10_060.0, 14)
    assert reading["percentage_proposed"] == 42.
    assert reading["reason"] == "fireplace_or_night"
    values["grid_last_known"] = False
    prior, reading = fan.project(values, prior, 10_120.0, 14)
    # A stale backup-verified helper is not proof of electricity at the fan.
    assert reading["percentage_proposed"] == 0
    assert reading["reason"] == "permission_or_grid"
    values["fireplace_delta_c_last_known"] = None
    prior, reading = fan.project(values, prior, 10_180.0, 14)
    assert reading["percentage_proposed"] == 0
    assert reading["burning_inferred"] is None

    # The old, unqualified thermal coefficients can produce a DIAGNOSTIC
    # no-heating scenario, but never a valid heat plan or a missing-data curve.
    coast = importlib.import_module("custom_components.heating_ai_v2.shadow_coast")
    now = 1_700_000_000.0
    legacy = {
        "floor_air": 0.028, "room_loss": 0.008,
        "floor_decay": 0.24, "heat_gain": 1.0, "fire_gain": 0.025,
        "version": 6,
    }
    weather = {
        "received_at": now,
        "hours": [
            {"at": now - 3600 + 3600 * i, "outside_c": 3.0}
            for i in range(6)
        ],
    }
    assert coast.recently_reported(
        {"last_reported": "2026-11-11T21:00:00+00:00"},
        1794430800.0,
    )
    assert not coast.recently_reported(
        {"last_reported": "2026-11-11T21:00:00+00:00"},
        1794430800.0 + 5 * 3600,
    )
    diagnostic = coast.preview(21.5, 24.0, legacy, weather, now)
    assert diagnostic["status"] == "UNQUALIFIED_CONDITIONAL_COAST"
    assert diagnostic["model_calibration"] == "NOT_PARITY_VERIFIED"
    assert diagnostic["forecast_qualified"] is False
    assert diagnostic["commands_enabled"] is False
    assert diagnostic["hours_covered"] >= 3
    assert diagnostic["temperature_min_c"] is not None
    assert coast.preview(21.5, 24, None, weather, now)["status"] == "UNAVAILABLE"
    assert coast.preview(21.5, 24, legacy, None, now)["status"] == "UNAVAILABLE"
    assert coast.preview(21.5, 24, legacy, weather, now + 8640)["status"] == "UNAVAILABLE"

    # The accepted real planner is executed against bounded HA-shaped inputs.
    from datetime import datetime, timedelta, timezone
    planner = importlib.import_module("custom_components.heating_ai_v2.shadow_plan")
    start = datetime(2026, 11, 11, 23, 0, tzinfo=timezone.utc).timestamp()
    stamp = datetime.fromtimestamp(start, timezone.utc).isoformat()
    def record(state, unit=""):
        return {"state": state, "unit": unit, "last_reported": stamp}
    rows = {
        "room": record("20.5", "°C"),
        "stored_heat": record("22.0", "°C"),
        "legacy_model": {
            **record("Синтетична перевірка"),
            "attributes": {"parameters": legacy},
        },
        "grid": record("Наявна мережа"),
        "day_target": record("21.5", "°C"),
        "night_target": record("21.0", "°C"),
        "day_upper": record("22.0", "°C"),
        "night_upper": record("21.5", "°C"),
        "sleep_start": record("23:00:00"),
        "sleep_end": record("06:30:00"),
        "heating_start": record("23:00:00"),
        "heating_end": record("07:00:00"),
        "strategy": record("Тільки в дозволені години"),
        "power_model": record("fixed_6"),
    }
    wx = {
        "received_at": start, "status": "RECEIVED_ISSUED_UNKNOWN",
        "hours": [
            {"at": start - 3600 + i * 3600, "outside_c": 2.0}
            for i in range(26)
        ],
    }
    outage = {
        "received_at": start, "status": "OUTAGE_EVENTS_ONLY",
        "coverage_known": False,
        "outages": [{"start": start + 2.5 * 3600,
                     "end": start + 9.5 * 3600}],
    }
    virtual = planner.conditional_plan(rows, wx, outage, start)
    assert virtual["status"] == "VIRTUAL_CONDITIONAL", virtual
    assert virtual["scenario_power_kw"] == 6.0
    assert virtual["commands_sent"] == 0
    assert virtual["proposal_is_command"] is False
    assert virtual["model_qualified"] is False
    assert virtual["physical_limits_qualified"] is False
    assert virtual["weather_issued_known"] is False
    assert virtual["grid_forecast_qualified"] is False
    assert 0 <= virtual["segment_count"]
    assert len(virtual["segments"]) <= 12
    assert virtual["work"] <= 50000
    for session in virtual["segments"]:
        assert session["conditional"] is True
        assert not (
            session["start"] < outage["outages"][0]["end"]
            and session["end"] > outage["outages"][0]["start"]
        ), session
    assert planner.conditional_plan(rows, wx, outage, start) == virtual

    # Unknown forecast, unbound config, uncalibrated AUTO, stale stored heat
    # and missing weather hours must never fabricate an executable plan.
    for changed_rows, changed_weather in (
        ({**rows, "night_upper": None}, wx),
        ({**rows, "power_model": record("AUTO")}, wx),
        ({**rows, "stored_heat": {**rows["stored_heat"], "last_reported":
            "2026-11-10T00:00:00+00:00"}}, wx),
        (rows, None),
    ):
        result = planner.conditional_plan(changed_rows, changed_weather, outage, start)
        assert result["status"] == "BLOCKED_INPUTS", result
        assert result["commands_sent"] == 0
        assert result["segments"] == []

    # Restart/load cannot keep old source ledger or invent a positive intent.
    assert mod.shadow_decision({})["intents"] == 0
    print("PASS: accepted pure source SHA256 parity, 54 real-state variations, no HEAT")


if __name__ == "__main__":
    main()
