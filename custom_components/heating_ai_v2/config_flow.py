"""One-time entity mapping, selected in UI; no public household identifiers."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import DOMAIN
from .telemetry import ROLES


def mapping_schema() -> vol.Schema:
    fields: dict[Any, Any] = {}
    for role in ROLES:
        domain = "climate" if role == "thermostat" else (
            "binary_sensor" if role == "grid" else "sensor"
        )
        fields[vol.Required(role)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=domain)
        )
    return vol.Schema(fields)


class HeatingAIV2Flow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (set(user_input) != set(ROLES)
                    or any(not isinstance(value, str) or "." not in value
                           for value in user_input.values())
                    or len(set(user_input.values())) != len(ROLES)):
                errors["base"] = "invalid_mapping"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Heating AI 2.0 — спостереження", data=dict(user_input)
                )
        return self.async_show_form(step_id="user", data_schema=mapping_schema(), errors=errors)
