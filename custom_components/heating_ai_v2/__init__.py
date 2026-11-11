"""Read-only Heating AI v2 installation profile for real Home Assistant."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .telemetry import ROLES, snapshot


class ShadowRuntime:
    """Plain observations; absolutely no physical service calls or commands."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self.listeners: set[Callable[[], None]] = set()
        self.values: dict[str, Any] = {}
        self.refresh()

    @callback
    def refresh(self) -> None:
        rows: dict[str, dict[str, Any] | None] = {}
        for role in ROLES:
            entity_id = self.entry.data[role]
            state = self.hass.states.get(entity_id)
            rows[role] = ({
                "state": state.state,
                "unit": state.attributes.get("unit_of_measurement", ""),
                "last_reported": state.last_reported.isoformat(),
            } if state is not None else None)
        self.values = snapshot(rows)
        for notify in tuple(self.listeners):
            notify()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if hass.data[DOMAIN]:
        return False
    if set(entry.data) != set(ROLES) or len(set(entry.data.values())) != len(ROLES):
        return False

    runtime = ShadowRuntime(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = runtime

    @callback
    def changed(event: Any) -> None:
        runtime.refresh()

    entry.async_on_unload(async_track_state_change_event(
        hass, [entry.data[role] for role in ROLES], changed
    ))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    except Exception:
        runtime.listeners.clear()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR]):
        return False
    runtime: ShadowRuntime | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime is not None:
        runtime.listeners.clear()
    return True
