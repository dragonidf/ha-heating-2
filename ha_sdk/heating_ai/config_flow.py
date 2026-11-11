"""Explicit disabled-default native test flow, HA2026.10.4 SDK."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from .const import DOMAIN
from .core.ha_native.meter import future_meter_binding

def sandbox_marker(directory: str) -> bool:
    marker = Path(directory) / ".heating-ai-isolated-test"
    return (os.environ.get("HEATING_AI_TEST_SANDBOX") == "1" and not marker.is_symlink()
            and marker.is_file() and marker.read_text() == "synthetic-only\n")

async def isolated(hass: HomeAssistant) -> bool:
    return await hass.async_add_executor_job(sandbox_marker, hass.config.config_dir)

def options(values: dict[str, Any]) -> dict[str, Any]:
    if set(values) - {"simulation_enabled", "freshness_s", "meter_source_id", "activity_window_s"}:
        raise ValueError("Unknown option")
    enabled, age, source = values.get("simulation_enabled", False), values.get("freshness_s", 30), values.get("meter_source_id", "")
    if type(enabled) is not bool or type(age) not in (int, float) or not 5 <= age <= 300:
        raise ValueError("Invalid synthetic options")
    activity = values.get("activity_window_s", 3660)
    if type(activity) not in (int, float) or not 60 <= activity <= 86400:
        raise ValueError("Invalid activity window")
    future_meter_binding(source)
    return {"simulation_enabled": enabled, "freshness_s": age, "meter_source_id": source, "activity_window_s": activity}

class HeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not await isolated(self.hass):
            return self.async_abort(reason="isolated_test_only")
        await self.async_set_unique_id("heating-ai-isolated-synthetic")
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            if set(user_input) == {"confirm_isolated"} and user_input["confirm_isolated"] is True:
                return self.async_create_entry(title="Heating AI synthetic test", data={"schema_version": 1, "synthetic": True}, options=options({}))
            errors["base"] = "confirm_isolated"
        return self.async_show_form(step_id="user", data_schema=probatio.Schema({probatio.Required("confirm_isolated", default=False): bool}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HeatingOptionsFlow:
        return HeatingOptionsFlow()

class HeatingOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not await isolated(self.hass):
            return self.async_abort(reason="isolated_test_only")
        errors = {}
        if user_input is not None:
            try:
                selected = options(dict(self.config_entry.options) | user_input)
            except (ValueError, TypeError):
                errors["base"] = "invalid_options"
            else:
                return self.async_create_entry(title="", data=selected)
        current = options(dict(self.config_entry.options))
        return self.async_show_form(step_id="init", data_schema=probatio.Schema({
            probatio.Required("simulation_enabled", default=current["simulation_enabled"]): bool,
            probatio.Optional("freshness_s", default=current["freshness_s"]): probatio.All(probatio.Coerce(float), probatio.Range(min=5, max=300)),
            probatio.Optional("activity_window_s", default=current["activity_window_s"]): probatio.All(probatio.Coerce(float), probatio.Range(min=60, max=86400)),
            probatio.Optional("meter_source_id", default=current["meter_source_id"]): str,
        }), errors=errors)
