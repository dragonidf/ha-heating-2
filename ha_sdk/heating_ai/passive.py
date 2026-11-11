"""Optional read-only source listener, callable ONLY inside the isolated HA sandbox."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any
from collections.abc import Callable
from homeassistant.core import Event, State, callback
from homeassistant.helpers import entity_registry as er
from .config_flow import isolated
from .core.ha_native.passive_bridge import PassiveBinding, PassiveSourceBridge, HAObservation
if TYPE_CHECKING:
    from . import Runtime


async def async_attach_passive(runtime: Runtime, bindings: tuple[PassiveBinding, ...]) -> Callable[[], None]:
    """Bindings are externally supplied, never shipped household configuration."""
    if not await isolated(runtime.hass):
        raise ValueError('Passive bridge requires isolated sandbox')
    runtime.backend.invalidate_source('passive_startup_requires_qualified_measurement')
    await runtime.flush()
    bridge = PassiveSourceBridge(bindings, started_clock=runtime.backend.trusted_clock())
    configured = {b.entity_id for b in bindings}
    registry = er.async_get(runtime.hass)

    @callback
    def observed(event: Event[dict[str, Any]]) -> None:
        if not runtime.active:
            return
        entity_id = event.data.get('entity_id')
        if not isinstance(entity_id, str) or entity_id not in configured:
            return
        state = event.data.get('new_state')
        row = registry.async_get(entity_id)
        if not isinstance(state, State) or row is None or row.device_id is None:
            runtime.backend.invalidate_source('passive_registry_or_state_missing')
        else:
            try:
                available = state.state not in ('unavailable', 'unknown')
                value = float(state.state) if available else None
                unit = state.attributes.get('unit_of_measurement', '')
                unit = 'C' if unit == '°C' else unit
                observation = HAObservation(entity_id, row.device_id, row.platform, unit, value,
                    state.last_reported.timestamp(), state.last_updated.timestamp(), state.last_changed.timestamp(),
                    registry_verified=True, available=available, restored=state.attributes.get('restored', False))
                bridge.observe(observation, runtime.backend, runtime.backend.trusted_clock(), live_event=True)
            except (ValueError, TypeError):
                runtime.backend.invalidate_source('passive_invalid_state')
        runtime.notify()
        runtime.hass.async_create_background_task(runtime.flush(), 'heating_ai passive audit')

    # State-reported includes unchanged integration writes; still NOT physical samples.
    # HA requires a bounded filter and immediate callback for this high-volume event.
    return runtime.hass.bus.async_listen('state_reported', observed,
        event_filter=lambda data: isinstance(data.get('entity_id'), str) and data.get('entity_id') in configured, run_immediately=True)
