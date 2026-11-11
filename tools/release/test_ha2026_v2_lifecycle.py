"""Disposable Home Assistant 2026.11 v2 setup/unload and failed-start lifecycle QA.

No real devices and NO Home Assistant service transport are provided.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components import heating_ai_v2 as component
from custom_components.heating_ai_v2.telemetry import ROLES, OPTIONAL_ROLES


def fake_state(role: str):
    unit = ("kW" if role in ("kws_l1", "kws_l2", "kws_l3") else
            "kWh" if role == "kws_energy" else
            "°C" if role in ("room", "fireplace") else
            "V" if role.startswith("voltage_") else
            "%" if role.startswith("fan_") and role in
            ("fan_night", "fan_standard", "fan_intense") else "")
    value = ("heat" if role == "thermostat" else
             "Наявна мережа" if role == "grid" else
             "Зупинити" if role == "fan_mode" else
             "off" if role in ("circulation", "recuperator", "bath") else
             "on" if role in ("fan_backup", "fan_control") else
             "38" if role == "fan_night" else
             "42" if role == "fan_standard" else
             "45" if role == "fan_intense" else
             "21" if role == "room" else
             "27" if role == "fireplace" else
             "230" if role.startswith("voltage_") else
             "100" if role == "kws_energy" else "0")
    return SimpleNamespace(
        state=value, attributes={"unit_of_measurement": unit, "percentage": 42},
        last_reported=datetime.now(timezone.utc),
    )


async def case(*, bad_meter: bool = False, fail_panel: bool = False):
    roles = ROLES + OPTIONAL_ROLES
    bindings = {
        role: ("climate." if role == "thermostat" else
               "fan." if role == "circulation" else
               "input_select." if role in ("grid", "fan_mode") else
               "input_number." if role in ("fan_night", "fan_standard", "fan_intense") else
               "input_boolean." if role in ("fan_backup", "fan_control") else
               "switch." if role in ("recuperator", "bath") else "sensor.") + "synthetic_" + role
        for role in roles
    }
    states = {entity_id: fake_state(role) for role, entity_id in bindings.items()}
    entry = SimpleNamespace(
        entry_id="synthetic_test_entry", data=bindings,
        async_on_unload=Mock(),
    )
    hass = SimpleNamespace(
        data={},
        states=SimpleNamespace(get=states.get),
        http=SimpleNamespace(async_register_static_paths=AsyncMock()),
        config_entries=SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        ),
    )
    registry = SimpleNamespace(async_get=lambda eid: SimpleNamespace(
        platform="tuya_local", device_id="wrong" if bad_meter and
        eid.endswith("kws_l2") else "one_physical_meter",
    ))
    unsubs = [Mock(), Mock()]
    with (
        patch.object(component.er, "async_get", return_value=registry),
        patch.object(component.panel_custom, "async_register_panel", new_callable=AsyncMock) as panel,
        patch.object(component.frontend, "async_remove_panel") as remove,
        patch.object(component, "async_track_state_change_event", return_value=unsubs[0]) as watched,
        patch.object(component, "async_track_time_interval", return_value=unsubs[1]) as timed,
    ):
        if fail_panel:
            panel.side_effect = RuntimeError("synthetic registration failure")
        if bad_meter:
            try:
                await component.async_setup_entry(hass, entry)
            except component.ConfigEntryError:
                pass
            else:
                raise AssertionError("Cross-device KWS incorrectly accepted")
            assert not hass.data.get(component.DOMAIN, {}), hass.data
            assert not watched.called and not timed.called and not panel.called
            return
        if fail_panel:
            try:
                await component.async_setup_entry(hass, entry)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Synthetic panel registration failure ignored")
            assert not hass.data[component.DOMAIN].get(entry.entry_id)
            assert not watched.called and not timed.called
            assert hass.config_entries.async_unload_platforms.await_count == 1
            return
        assert await component.async_setup_entry(hass, entry) is True
        runtime = hass.data[component.DOMAIN][entry.entry_id]
        assert runtime.values["kernel"]["permit"] is False
        assert runtime.values["kernel"]["intents"] == 0
        assert runtime.values["fan"]["percentage_proposed"] == 0
        assert runtime.values["fan"]["reason"] == "explicit_stop"
        assert runtime.values["fireplace_delta_c_last_known"] == 6
        assert runtime.values["fan_speed_percent_last_known"]["fan_standard"] == 42
        # Actual speed is a fan ATTRIBUTE, not a standalone sensor state.
        assert runtime.values["circulation_percentage_last_known"] == 42
        assert len(runtime.listeners) == 0
        assert watched.call_count == 1 and timed.call_count == 1
        assert entry.async_on_unload.call_count == 2
        assert not hasattr(hass, "services"), "Physical service transport must not exist"
        # Exercise repeated HA source changes and the periodic safety observer.
        # The subscriber count, state shape and allowed command count stay bounded.
        fields = set(runtime.values)
        state_event = watched.call_args.args[2]
        periodic_tick = timed.call_args.args[1]
        for i in range(300):
            states[bindings["grid"]].state = (
                "Відсутня мережа" if i % 3 == 0 else "Наявна мережа"
            )
            state_event(None)
            if i % 3 == 0:
                periodic_tick(None)
            assert set(runtime.values) == fields
            assert runtime.values["kernel"]["permit"] is False
            assert runtime.values["kernel"]["intents"] == 0
            assert runtime.values["fan"]["commands_sent"] == 0
            assert len(runtime.listeners) == 0
        assert watched.call_count == 1 and timed.call_count == 1
        assert entry.async_on_unload.call_count == 2
        assert await component.async_unload_entry(hass, entry)
        assert remove.call_count == 1
        assert entry.entry_id not in hass.data[component.DOMAIN]
        for callback in entry.async_on_unload.call_args_list:
            callback.args[0]()
        assert unsubs[0].call_count == 1 and unsubs[1].call_count == 1


async def main():
    await case()
    await case(bad_meter=True)
    await case(fail_panel=True)
    print("PASS: real HA2026.11 v2 shadow setup/unload, cross-device and failed-panel cleanup")


if __name__ == "__main__":
    asyncio.run(main())
