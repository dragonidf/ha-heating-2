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
            for power in (0.0, 6.22, None):
                values = {
                    "grid_last_known": grid,
                    "room_c_last_known": room,
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

    # Restart/load cannot keep old source ledger or invent a positive intent.
    assert mod.shadow_decision({})["intents"] == 0
    print("PASS: accepted pure source SHA256 parity, 18 real-state variations, no HEAT")


if __name__ == "__main__":
    main()
