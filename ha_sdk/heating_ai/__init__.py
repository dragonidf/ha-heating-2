"""Fake-only native HA SDK wrapper. Source pin: docs/wp2c/SOURCES.md."""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from time import monotonic, time
from typing import Any, Callable, cast
import probatio
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import websocket_command, async_response
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from .config_flow import isolated, options
from .const import ASSETS, DOMAIN, EVENT_SAMPLE, PANEL
from .core.offline.codec import decode
from .core.offline.contracts import SourceEvent
from .core.ha_native.backend import NativeBackend, NativeProtocolError
from .core.ha_native.health import SourceTimingPolicy
from .core.ha_native.meter import binding_summary, future_meter_binding
from .core.ha_native.store import JSON
from .core.ha_native.voltage import decode_voltage_frame
from .core.ha_native.kws import decode_kws_frame

READS = ("status", "overview", "energy", "history", "settings/get", "diagnostics", "subscribe")
MUTATIONS = ("settings/save", "control", "model")

class Runtime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, backend: NativeBackend) -> None:
        self.hass, self.entry, self.backend = hass, entry, backend
        self.active = True
        self.lock = asyncio.Lock()
        self.listeners: set[Callable[[], None]] = set()

    @callback
    def notify(self) -> None:
        for listener in tuple(self.listeners):
            listener()

    async def request(self, operation: str, payload: dict[str, Any], admin: bool) -> JSON:
        if not self.active:
            raise NativeProtocolError("unavailable")
        if operation == "control" and payload.get("kind") == "pause":
            result = self.backend.stop_request(cast(JSON, payload), admin)
            self.notify()
            self.hass.async_create_background_task(self.flush(), "heating_ai stop audit")
            return result
        async with self.lock:
            if not self.active:
                raise NativeProtocolError("unavailable")
            result = await self.hass.async_add_executor_job(self.backend.dispatch, operation, cast(JSON, payload), admin)
        if operation in MUTATIONS:
            await self.flush()
        if operation in MUTATIONS or operation == "status":
            self.notify()
        if operation == "diagnostics" and isinstance(result, dict):
            result["meter_binding"] = cast(JSON, binding_summary(future_meter_binding(self.entry.options.get("meter_source_id", ""))))
        return result

    async def flush(self) -> None:
        before = self.backend.status(False)["seq"]
        await self.hass.async_add_executor_job(self.backend.flush_stop)
        if self.active and self.backend.status(False)["seq"] != before:
            self.notify()

    async def flush_evidence(self) -> None:
        await self.hass.async_add_executor_job(self.backend.flush_evidence)
        if self.active:
            self.notify()

    async def tick(self, now: datetime) -> None:
        if not self.active:
            return
        if self.backend.refresh(publish=True):
            self.notify()
        await self.flush()

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if not await isolated(hass):
        return False
    if DOMAIN in hass.data:
        return True
    hass.data[DOMAIN] = {"entries": {}}
    await hass.http.async_register_static_paths([StaticPathConfig(ASSETS, str(Path(__file__).parent / "assets"), cache_headers=False)])
    for operation in READS + MUTATIONS:
        register_command(hass, operation)
    return True

def register_command(hass: HomeAssistant, operation: str) -> None:
    fields: dict[Any, Any] = {"type": DOMAIN + "/" + operation, probatio.Required("entry_id"): str, probatio.Required("version"): [int]}
    if operation in MUTATIONS:
        fields.update({probatio.Required("boot_id"): str, probatio.Required("generation"): int, probatio.Required("owner_epoch"): int})
    for field in {"history": ("start", "end", "cursor", "limit"), "settings/save": ("request_id", "expected_revision", "values"), "control": ("kind", "request_id"), "model": ("kind", "request_id")}.get(operation, ()):
        fields[probatio.Optional(field)] = object

    @websocket_command(fields)
    @async_response
    async def handle(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
        user = connection.user
        if user is None:
            connection.send_error(msg["id"], "unauthorized", "Authentication required")
            return
        runtime = hass.data.get(DOMAIN, {}).get("entries", {}).get(msg["entry_id"])
        if not isinstance(runtime, Runtime) or not runtime.active:
            connection.send_error(msg["id"], "not_loaded", "Synthetic entry unavailable")
            return
        try:
            if len(json.dumps(msg, ensure_ascii=True, allow_nan=False).encode()) > 262144:
                raise NativeProtocolError("payload_too_large")
            body = {key: value for key, value in msg.items() if key not in ("type", "id")}
            result = await runtime.request(operation, body, user.is_admin)
        except (NativeProtocolError, ValueError, TypeError, RecursionError) as exc:
            connection.send_error(msg["id"], exc.code if isinstance(exc, NativeProtocolError) else "invalid_payload", "Synthetic request rejected")
            return
        if operation == "subscribe":
            @callback
            def emit() -> None:
                if runtime.active:
                    connection.send_event(msg["id"], runtime.backend.status(user.is_admin))
            runtime.listeners.add(emit)
            connection.subscriptions[msg["id"]] = lambda: runtime.listeners.discard(emit)
            connection.send_result(msg["id"])
            emit()
        else:
            connection.send_result(msg["id"], result)
    websocket_api.async_register_command(hass, handle)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await isolated(hass) or entry.data != {"schema_version": 1, "synthetic": True}:
        raise ConfigEntryError("Only the isolated synthetic schema is supported")
    if DOMAIN not in hass.data and not await async_setup(hass, {}):
        return False
    entries: dict[str, Runtime] = hass.data[DOMAIN]["entries"]
    if entries:
        raise ConfigEntryError("Only one isolated synthetic owner is supported")
    selected = options(dict(entry.options))
    def open_backend() -> NativeBackend:
        root = Path(tempfile.gettempdir()) / ("heating-wp2c-" + entry.entry_id)
        root.mkdir(mode=0o700, exist_ok=True)
        backend = NativeBackend(root, entry_id=entry.entry_id, enabled=selected["simulation_enabled"],
                                activity_window_s=selected["activity_window_s"],
                                clock=lambda: (time(), monotonic()))
        backend.configure_timing(SourceTimingPolicy(selected["freshness_s"], selected["activity_window_s"], selected["recovery_dwell_s"]))
        backend.open()
        return backend
    try:
        backend = await hass.async_add_executor_job(open_backend)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ConfigEntryNotReady("Synthetic store or runtime unavailable") from exc
    runtime = Runtime(hass, entry, backend)
    entries[entry.entry_id] = runtime
    entry.async_on_unload(entry.add_update_listener(update_options))

    async def source_event(event: Event[dict[str, Any]]) -> None:
        if not runtime.active or event.data.get("entry_id") != entry.entry_id:
            return
        user = await hass.auth.async_get_user(event.context.user_id) if event.context.user_id else None
        if user is None or not user.is_admin:
            return
        try:
            if set(event.data) not in ({"entry_id", "envelope"}, {"entry_id", "kind", "envelope"}) or len(json.dumps(event.data).encode()) > 65536:
                raise ValueError("Invalid source envelope")
            kind = event.data.get("kind", "room")
            if kind == "voltage":
                backend.accept_voltage(decode_voltage_frame(event.data["envelope"]))
            elif kind == "power":
                backend.accept_power(decode_kws_frame(event.data["envelope"]))
            elif kind == "room":
                data = decode(json.dumps(event.data["envelope"], allow_nan=False))
                if not isinstance(data, SourceEvent):
                    raise ValueError("Expected SourceEvent")
                backend.accept_source(data)
            else:
                raise ValueError("Unknown synthetic source kind")
        except (ValueError, TypeError, KeyError, RecursionError):
            backend.invalidate_source("invalid_synthetic_event")
        runtime.notify()
        await runtime.flush()
        hass.async_create_background_task(runtime.flush_evidence(), "heating_ai meter evidence")

    owned_entity_ids: set[str] = set()

    @callback
    def registry_event(event: Event[dict[str, Any]]) -> None:
        entity_id = event.data.get("entity_id", "")
        row = er.async_get(hass).async_get(entity_id)
        owned = entity_id in owned_entity_ids or row is not None and row.config_entry_id == entry.entry_id
        if owned and event.data.get("action") in ("update", "remove") and runtime.active:
            backend.invalidate_source("synthetic_registry_changed")
            runtime.notify()
            hass.async_create_background_task(runtime.flush(), "heating_ai registry audit")
        if row is not None and row.config_entry_id == entry.entry_id:
            owned_entity_ids.add(entity_id)
        if event.data.get("action") == "remove":
            owned_entity_ids.discard(entity_id)

    @callback
    def stop_runtime(event: Event[Any]) -> None:
        runtime.active = False
        backend.close()
        runtime.listeners.clear()

    entry.async_on_unload(async_track_time_interval(hass, runtime.tick, timedelta(seconds=1)))
    entry.async_on_unload(hass.bus.async_listen(EVENT_SAMPLE, source_event))
    entry.async_on_unload(hass.bus.async_listen("entity_registry_updated", registry_event))
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_runtime))
    try:
        await panel_custom.async_register_panel(hass, PANEL, "heating-ai-panel", sidebar_title="Heating AI (synthetic)", sidebar_icon="mdi:radiator", module_url=ASSETS + "/panel.js", config={"entry_id": entry.entry_id}, require_admin=False)
        await hass.config_entries.async_forward_entry_setups(entry, (Platform.SENSOR,))
        owned_entity_ids.update(row.entity_id for row in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
    except Exception:
        runtime.active = False
        backend.close()
        entries.pop(entry.entry_id, None)
        frontend.async_remove_panel(hass, PANEL, warn_if_unknown=False)
        raise
    return True

async def update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = hass.data[DOMAIN]["entries"].get(entry.entry_id)
    if runtime is None:
        return True
    runtime.active = False
    runtime.backend.close()
    runtime.listeners.clear()
    ok = await hass.config_entries.async_unload_platforms(entry, (Platform.SENSOR,))
    if ok:
        hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
        frontend.async_remove_panel(hass, PANEL, warn_if_unknown=False)
    return ok

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version != 1 or entry.minor_version > 1 or not await isolated(hass):
        return False
    if entry.minor_version < 1:
        selected = options(dict(entry.options))
        selected["simulation_enabled"] = False
        hass.config_entries.async_update_entry(entry, data={"schema_version": 1, "synthetic": True}, options=selected, minor_version=1)
    return True
