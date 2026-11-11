"""Heating AI v2 shadow snapshot, pure and permanently read-only.

HA state changes are NOT physical samples, dry-contact ACKs, or authorization.
In particular unchanged KWS 0 kW phase values remain valid *last-known*
display values; an old last_changed must never by itself block heating.
"""
from __future__ import annotations
from math import isfinite
from typing import Any, Mapping

ROLES = (
    "thermostat", "room", "grid",
    "voltage_l1", "voltage_l2", "voltage_l3",
    "kws_l1", "kws_l2", "kws_l3", "kws_energy",
)
OPTIONAL_ROLES = ("return_probe", "fireplace", "circulation", "fan_mode", "fan_night", "fan_standard", "fan_intense", "fan_backup", "fan_control", "recuperator", "bath",)

_UNITS = {
    "room": "°C",
    "voltage_l1": "V", "voltage_l2": "V", "voltage_l3": "V",
    "kws_l1": "kW", "kws_l2": "kW", "kws_l3": "kW",
    "kws_energy": "kWh",
}


def _number(row: Mapping[str, Any] | None, unit: str,
            minimum: float, maximum: float) -> float | None:
    if row is None or row.get("unit") != unit:
        return None
    try:
        value = float(row.get("state"))
    except (ValueError, TypeError, OverflowError):
        return None
    return value if isfinite(value) and minimum <= value <= maximum else None


def snapshot(rows: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]:
    """Last-known HA display; nothing here authorizes or confirms heat."""
    room = _number(rows.get("room"), "°C", -30, 60)
    phase = {
        name: _number(rows.get(name), "kW", 0, 12)
        for name in ("kws_l1", "kws_l2", "kws_l3")
    }
    total = (round(sum(phase.values()), 3)
             if all(v is not None for v in phase.values()) else None)
    energy = _number(rows.get("kws_energy"), "kWh", 0, 1e9)
    volts = {
        name: _number(rows.get(name), "V", 0, 400)
        for name in ("voltage_l1", "voltage_l2", "voltage_l3")
    }
    tstate = (rows.get("thermostat") or {}).get("state")
    tmode = tstate if tstate in ("heat", "auto", "off") else None
    grid = (rows.get("grid") or {}).get("state")
    grid_ok = True if grid == "Наявна мережа" else False if grid == "Відсутня мережа" else None
    unavailable = [name for name in ROLES
                   if rows.get(name) is None
                   or rows[name].get("state") in ("unavailable", "unknown", None)]
    return_c = _number(rows.get("return_probe"), "°C", -30, 110)
    fireplace = _number(rows.get("fireplace"), "°C", -30, 65)
    delta = round(fireplace - room, 2) if fireplace is not None and room is not None else None
    fan_state = (rows.get("circulation") or {}).get("state")
    if fan_state not in ("on", "off"):
        fan_state = None
    fan_attrs = (rows.get("circulation") or {}).get("attributes") or {}
    fan_pct = fan_attrs.get("percentage")
    fan_pct = float(fan_pct) if type(fan_pct) in (int, float) and 0 <= fan_pct <= 100 else None
    mode = (rows.get("fan_mode") or {}).get("state")
    if mode not in ("Авто", "Ручний запуск", "Зупинити"):
        mode = None
    speeds = {role: _number(rows.get(role), "%", 0, 100) for role in
              ("fan_night", "fan_standard", "fan_intense")}
    def binary(role: str) -> bool | None:
        state = (rows.get(role) or {}).get("state")
        return True if state == "on" else False if state == "off" else None
    vent = {role: binary(role) for role in ("recuperator", "bath")}
    return {
        "mode": "SHADOW", "commands_enabled": False,
        "physical_ack": False, "contacts_open": None,
        "room_c_last_known": room,
        "thermostat_mode_last_known": tmode,
        "grid_last_known": grid_ok,
        "voltages_v_last_known": volts,
        "kws_phases_kw_last_known": phase,
        "kws_total_kw_last_known": total,
        "kws_energy_kwh_last_known": energy,
        "kws_stage": "UNCALIBRATED",
        "return_c_last_known": return_c,
        "fireplace_c_last_known": fireplace, "fireplace_delta_c_last_known": delta,
        "circulation_last_known": fan_state, "circulation_percentage_last_known": fan_pct,
        "fan_mode_last_known": mode, "fan_speed_percent_last_known": speeds,
        "fan_backup_verified_last_known": binary("fan_backup"),
        "fan_control_enabled_last_known": binary("fan_control"),
        "ventilation_last_known": vent,
        "fireplace_heat_proven": False, "fan_commands_enabled": False,
        "kws_value_semantics": "HA_last_known_not_verified_raw_sample",
        "unavailable_sources": unavailable,
        "ha_last_reported": {
            name: (rows.get(name) or {}).get("last_reported")
            for name in ROLES + OPTIONAL_ROLES
        },
    }
