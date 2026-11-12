"""Four read-only entities; no write callbacks, helpers or KWS polling."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShadowRuntime
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: ShadowRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ShadowSensor(runtime, kind) for kind in
                        ("status", "room", "power", "energy")])


class ShadowSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime: ShadowRuntime, kind: str) -> None:
        self.runtime, self.kind = runtime, kind
        self._attr_unique_id = f"{runtime.entry.entry_id}:{kind}"
        self._attr_name = {
            "status": "Режим контролера",
            "room": "Температура вітальні (HA)",
            "power": "Потужність котла (KWS, остання)",
            "energy": "Енергія котла (KWS, остання)",
        }[kind]
        if kind == "room":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif kind == "power":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        elif kind == "energy":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> str | float | None:
        values = self.runtime.values
        return {
            "status": "SHADOW",
            "room": values["room_c_last_known"],
            "power": values["kws_total_kw_last_known"],
            "energy": values["kws_energy_kwh_last_known"],
        }[self.kind]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        values = self.runtime.values
        if self.kind != "status":
            return {"measurement_status": "HA_last_known_not_verified_raw_sample",
                    "commands_enabled": False, "physical_ack": False}
        # The full thermal trajectory remains available via the authenticated
        # native WebSocket snapshot. Never write hundreds of forecast points
        # into a Recorder-backed HA state every two-second safety tick.
        plan = values.get("virtual_plan") or {}
        coast = values.get("coast") or {}
        coast_brief = {
            key: coast[key] for key in (
                "status", "temperature_min_c", "temperature_end_c",
                "hours_covered", "computed_at", "forecast_qualified",
                "commands_enabled", "scenario",
            ) if key in coast
        }
        plan_brief = {
            k: plan[k] for k in (
                "status", "reason", "scenario_power_kw", "projected_min_c",
                "nominal_energy_kwh", "horizon_hours", "segment_count",
                "segments", "segments_truncated", "computed_at",
                "commands_sent",
            ) if k in plan
        }
        return {
            "commands_enabled": False,
            "physical_ack": False,
            "contacts_open": None,
            "thermostat_mode": values["thermostat_mode_last_known"],
            "grid_last_known": values["grid_last_known"],
            "voltages_v_last_known": values["voltages_v_last_known"],
            "kws_phases_kw_last_known": values["kws_phases_kw_last_known"],
            "kws_stage": "UNCALIBRATED",
            "kernel_mode": values.get("kernel", {}).get("mode", "FAULT"),
            "kernel_reason": values.get("kernel", {}).get("reason", "unavailable"),
            "kernel_permit": False,
            "kernel_intents": 0,
            "v2_entry_id": self.runtime.entry.entry_id,
            "provider_summary": values.get("providers", {}),
            "coast_preview": coast_brief,
            "virtual_plan": plan_brief,
            "return_c_last_known": values["return_c_last_known"],
            "fireplace_c_last_known": values["fireplace_c_last_known"],
            "fireplace_delta_c_last_known": values["fireplace_delta_c_last_known"],
            "circulation_last_known": values["circulation_last_known"],
            "fan_mode_last_known": values["fan_mode_last_known"],
            "fan_speed_percent_last_known": values["fan_speed_percent_last_known"],
            "fan_backup_verified_last_known": values["fan_backup_verified_last_known"],
            "fan_control_enabled_last_known": values["fan_control_enabled_last_known"],
            "ventilation_last_known": values["ventilation_last_known"],
            "fan_commands_enabled": False,
            "fan_policy": values.get("fan", {}),
            "unavailable_sources": values["unavailable_sources"],
            "ha_last_reported": values["ha_last_reported"],
        }

    async def async_added_to_hass(self) -> None:
        self.runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self.runtime.listeners.discard(self.async_write_ha_state))
