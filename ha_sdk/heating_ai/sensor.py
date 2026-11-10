"""Read-only, disabled-default synthetic entities. Never a relay or actuator."""
from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import Runtime
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities([SyntheticSensor(runtime, kind) for kind in ("status", "active_power", "active_energy")])

class SyntheticSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(self, runtime: Runtime, kind: str) -> None:
        self.runtime, self.kind = runtime, kind
        self._attr_unique_id = runtime.entry.entry_id + ":" + kind
        self._attr_name = {"status": "Synthetic controller status", "active_power": "Unverified dedicated boiler active power", "active_energy": "Unverified dedicated boiler imported energy"}[kind]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, runtime.entry.entry_id)}, name="Heating AI isolated synthetic instance", manufacturer="Synthetic test", model="No physical hardware")
        if kind == "active_power":
            self._attr_device_class, self._attr_native_unit_of_measurement = SensorDeviceClass.POWER, UnitOfPower.WATT
        elif kind == "active_energy":
            self._attr_device_class, self._attr_native_unit_of_measurement = SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR

    @property
    def available(self) -> bool:
        return self.runtime.active

    @property
    def native_value(self) -> str | None:
        return ("synthetic_observation" if self.runtime.backend.enabled else "disabled") if self.kind == "status" else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"synthetic": True, "physical_verified": False, "physical_authority": False, "G1": "B01-B08 BLOCKED", "meter_model": "unverified", "meter_mapping": "unbound", "generation": self.runtime.backend.status(False)["generation"]}

    async def async_added_to_hass(self) -> None:
        self.runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self.runtime.listeners.discard(self.async_write_ha_state))
