"""Read-only Heating AI v2 installation profile for real Home Assistant."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import asyncio
from functools import partial
from hashlib import sha256
from time import monotonic
import logging
from pathlib import Path
from typing import Any

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .telemetry import ROLES, OPTIONAL_ROLES, snapshot

_LOGGER = logging.getLogger(__name__)


class ShadowRuntime:
    """Plain observations; absolutely no physical service calls or commands."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self.listeners: set[Callable[[], None]] = set()
        self.values: dict[str, Any] = {}
        self._kernel_fault = False
        self._fan_fault = False
        self._fan_state = None
        self.source_monitor = None
        self.native = None
        self._observe_task = None
        self.plan_rows: dict[str, dict[str, Any] | None] = {}
        self.refresh()

    @callback
    def refresh(self) -> None:
        rows: dict[str, dict[str, Any] | None] = {}
        for role in (*ROLES, *(role for role in OPTIONAL_ROLES if role in self.entry.data)):
            entity_id = self.entry.data[role]
            state = self.hass.states.get(entity_id)
            rows[role] = ({
                "state": state.state,
                "unit": state.attributes.get("unit_of_measurement", ""),
                "last_reported": state.last_reported.isoformat(),
                "last_updated": state.last_updated.isoformat(),
                "attributes": (
                    {key: state.attributes.get(key) for key in
                     ("current_temperature", "temperature", "min_temp", "max_temp", "target_temp_step")}
                    if role == "thermostat" else
                    {"percentage": state.attributes.get("percentage")}
                    if role == "circulation" else
                    {"parameters": state.attributes.get("parameters")}
                    if role == "legacy_model" else {}
                ),
            } if state is not None else None)
        self.plan_rows = rows
        if self.source_monitor is not None:
            self.source_monitor.note_inputs(self.native.planning_rows(rows) if self.native else rows)
        self.values = snapshot(rows)
        self.values["virtual_plan"] = (
            self.source_monitor.plan if self.source_monitor and self.source_monitor.plan
            else {"status": "BLOCKED_INPUTS", "reason": "planner_not_ready",
                  "commands_sent": 0, "proposal_is_command": False}
        )
        from .forecast_sources import source_summary
        self.values["providers"] = (
            self.source_monitor.brief() if self.source_monitor
            else source_summary(None, None, 0.0)
        )
        try:
            from .shadow_kernel import shadow_decision
            self.values['kernel'] = (shadow_decision(self.values) if self.native is None
                                     else self.native.decision)
            self._kernel_fault = False
        except Exception:
            self.values['kernel'] = {'mode': 'FAULT', 'permit': False,
                                     'intents': 0, 'physical_authority': False}
            if not self._kernel_fault:
                _LOGGER.exception('V2 shadow kernel failed; no physical command authority')
            self._kernel_fault = True
        try:
            from .fan_shadow import project
            fan_values = dict(self.values)
            if self.native is not None:
                preferences = self.native.persisted['values']
                fan_values['fan_mode_last_known'] = preferences.get('fan_mode', fan_values.get('fan_mode_last_known'))
                fan_values['fan_speed_percent_last_known'] = {
                    role: preferences.get(role, fan_values['fan_speed_percent_last_known'].get(role))
                    for role in ('fan_night', 'fan_standard', 'fan_intense')}
            self._fan_state, self.values["fan"] = project(
                fan_values, self._fan_state, monotonic(), dt_util.now().hour
            )
            self._fan_fault = False
        except Exception:
            self._fan_state = None
            self.values["fan"] = {
                "percentage_proposed": None, "reason": "fault",
                "physical_authority": False, "commands_sent": 0,
            }
            if not self._fan_fault:
                _LOGGER.exception("V2 fan shadow unavailable; no fan commands")
            self._fan_fault = True
        self.values["coast"] = (
            self.source_monitor.coast
            if self.source_monitor is not None and self.source_monitor.coast is not None
            else {"status": "UNAVAILABLE", "commands_enabled": False,
                  "forecast_qualified": False}
        )
        if self.native is not None:
            try:
                import time
                self.native.tick(rows, self.values, time.time(), monotonic())
                self.values['kernel'] = self.native.decision
                self.values['native'] = self.native.overview()
                if self._observe_task is None or self._observe_task.done():
                    self._observe_task = self.hass.async_create_task(self.native.observe())
            except Exception:
                self.native.fault = 'native_safety_fault'
                self.native.gateway.stopped = True
        for notify in tuple(self.listeners):
            notify()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if any(isinstance(row, ShadowRuntime) for row in hass.data[DOMAIN].values()):
        return False
    if (not set(ROLES).issubset(entry.data)
            or not set(entry.data).issubset(set(ROLES + OPTIONAL_ROLES))
            or len(set(entry.data.values())) != len(entry.data)):
        raise ConfigEntryError("Incomplete or duplicate shadow bindings")

    registry = er.async_get(hass)
    meter_roles = ("kws_l1", "kws_l2", "kws_l3", "kws_energy")
    meter = [registry.async_get(entry.data[role]) for role in meter_roles]
    if (any(row is None or row.platform != "tuya_local" or row.device_id is None
            for row in meter)
            or len({row.device_id for row in meter if row is not None}) != 1):
        raise ConfigEntryError("KWS must be four local channels from ONE device")

    # This is a packaged UI release, not a loose source-tree installation.
    assets = Path(__file__).parent / 'assets'
    if not (assets / 'livePanel.js').is_file():
        raise ConfigEntryNotReady('Missing reviewed live UI bundle')
    if not (Path(__file__).parent / 'engine' / 'SOURCE-SHA256.json').is_file():
        raise ConfigEntryNotReady('Missing accepted deterministic control engine')

    # Stable per-build URL and element name avoid stale Android Companion
    # custom-elements after a Marketplace update. No cache flushing/restarts.
    # Hash the actual installed asset, not a separately maintained version.
    bundle_id = await hass.async_add_executor_job(
        lambda: sha256((assets / 'livePanel.js').read_bytes()).hexdigest()[:12]
    )

    runtime = ShadowRuntime(hass, entry)
    from .native_runtime import NativeController
    from .climate_gateway import ha_service, ha_readback
    def open_native():
        directory = Path(hass.config.path('.storage', 'heating_ai_v2', entry.entry_id))
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return NativeController(directory, runtime.plan_rows,
            partial(ha_service, hass), partial(ha_readback, hass))
    try:
        runtime.native = await hass.async_add_executor_job(open_native)
        runtime.native.gateway.entity_id = entry.data['thermostat']
    except Exception as exc:
        raise ConfigEntryNotReady('Native durable state unavailable; commands inhibited') from exc
    if not hass.data[DOMAIN].get('_api'):
        from .native_api import register
        register(hass)
        hass.data[DOMAIN]['_api'] = True
    hass.data[DOMAIN][entry.entry_id] = runtime

    @callback
    def changed(event: Any) -> None:
        runtime.refresh()

    @callback
    def tick(_now: Any) -> None:
        runtime.refresh()
        if runtime.source_monitor is not None:
            runtime.source_monitor.schedule()

    forwarded = False
    panel_registered = False
    try:
        if not hass.data[DOMAIN].get('_static'):
            await hass.http.async_register_static_paths([
                StaticPathConfig('/heating_ai_v2/assets', str(assets), cache_headers=False)
            ])
            hass.data[DOMAIN]['_static'] = True
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
        forwarded = True
        await panel_custom.async_register_panel(
            hass, frontend_url_path='heating-ai-v2',
            webcomponent_name=f'heating-ai-v2-panel-{bundle_id}',
            sidebar_title='Heating AI 2.0', sidebar_icon='mdi:radiator',
            module_url=f'/heating_ai_v2/assets/livePanel.js?v={bundle_id}',
            config={**dict(entry.data), 'entry_id': entry.entry_id},
            require_admin=True,
        )
        panel_registered = True
        entry.async_on_unload(async_track_state_change_event(
            hass, list(entry.data.values()), changed
        ))
        entry.async_on_unload(async_track_time_interval(
            hass, tick, timedelta(seconds=2),
            name='heating_ai_v2_shadow_monitor'
        ))
        if "weather_forecast" in entry.data or "outage_calendar" in entry.data:
            from .source_monitor import SourceMonitor
            monitor = SourceMonitor(
                hass, dict(entry.data), runtime.refresh,
                lambda: runtime.native.planning_rows(runtime.plan_rows),
            )
            monitor.start()
            runtime.source_monitor = monitor
            runtime.refresh()
            monitor.schedule()
    except Exception:
        if runtime.source_monitor is not None:
            await runtime.source_monitor.close()
        if panel_registered:
            frontend.async_remove_panel(hass, 'heating-ai-v2', warn_if_unknown=False)
        if forwarded:
            await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
        if runtime._observe_task is not None:
            await runtime._observe_task
        runtime.native.gateway.stopped = True
        runtime.listeners.clear()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR]):
        return False
    frontend.async_remove_panel(hass, 'heating-ai-v2', warn_if_unknown=False)
    runtime: ShadowRuntime | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime is not None:
        if runtime.source_monitor is not None:
            await runtime.source_monitor.close()
        runtime.native.gateway.stopped = True
        if runtime._observe_task is not None:
            await runtime._observe_task
        runtime.listeners.clear()
    return True
