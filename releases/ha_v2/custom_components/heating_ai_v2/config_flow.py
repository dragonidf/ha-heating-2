"""One-time entity mapping, selected in UI; no public household identifiers."""
from __future__ import annotations

from typing import Any

import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import DOMAIN
from .telemetry import ROLES, OPTIONAL_ROLES


def mapping_schema() -> probatio.Schema:
    fields: dict[Any, Any] = {}
    for role in ROLES + OPTIONAL_ROLES:
        domain = ("weather" if role == "weather_forecast" else
                  "calendar" if role == "outage_calendar" else
                  "climate" if role == "thermostat" else
                  "input_select" if role in ("grid", "fan_mode", "strategy") else
                  "input_datetime" if role in ("sleep_start", "sleep_end", "heating_start", "heating_end") else
                  "input_number" if role in ("fan_night", "fan_standard", "fan_intense", "day_target", "night_target", "day_upper", "night_upper") else
                  "input_boolean" if role in ("fan_backup", "fan_control") else
                  "fan" if role == "circulation" else
                  "switch" if role in ("recuperator", "bath") else "sensor")
        fields[(probatio.Required if role in ROLES else probatio.Optional)(role)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=domain)
        )
    return probatio.Schema(fields)


class HeatingAIV2Flow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (not set(ROLES).issubset(user_input)
                    or not set(user_input).issubset(set(ROLES + OPTIONAL_ROLES))
                    or any(not isinstance(value, str) or "." not in value
                           for value in user_input.values())
                    or len(set(user_input.values())) != len(user_input)):
                errors["base"] = "invalid_mapping"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Heating AI 2.0 — спостереження", data=dict(user_input)
                )
        return self.async_show_form(step_id="user", data_schema=mapping_schema(), errors=errors)
