"""Disposable Home Assistant 2026.11 v2 setup/unload and failed-start lifecycle QA.

No real devices and NO Home Assistant service transport are provided.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components import heating_ai_v2 as component
from custom_components.heating_ai_v2.telemetry import ROLES, OPTIONAL_ROLES


def fake_state(role: str):
    unit = ("kW" if role in ("kws_l1", "kws_l2", "kws_l3") else
            "kWh" if role == "kws_energy" else
            "°C" if role in ("room", "fireplace", "return_probe") else
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
             "22.1" if role == "return_probe" else
             "27" if role == "fireplace" else
             "230" if role.startswith("voltage_") else
             "100" if role == "kws_energy" else "0")
    observed_at = datetime.now(timezone.utc)
    return SimpleNamespace(
        state=value, attributes={"unit_of_measurement": unit, "percentage": 42},
        last_reported=observed_at, last_updated=observed_at,
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
    tempdir = TemporaryDirectory(prefix="heating-v2-ha-smoke-")
    hass = SimpleNamespace(
        config=SimpleNamespace(path=lambda *parts: str(Path(tempdir.name).joinpath(*parts))),
        async_add_executor_job=lambda func, *args: asyncio.to_thread(func, *args),
        async_create_task=lambda coro, name=None: asyncio.create_task(coro, name=name),
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
        patch.object(component.websocket_api, "async_register_command") if hasattr(component, "websocket_api") else patch("homeassistant.components.websocket_api.async_register_command"),
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
            tempdir.cleanup()
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
            tempdir.cleanup()
            return
        assert await component.async_setup_entry(hass, entry) is True
        runtime = hass.data[component.DOMAIN][entry.entry_id]
        assert runtime.values["kernel"]["permit"] is False
        assert runtime.values["kernel"]["intents"] == 0
        assert runtime.values["fan"]["percentage_proposed"] == 0
        assert runtime.values["fan"]["reason"] == "explicit_stop"
        assert runtime.values["return_c_last_known"] == 22.1
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
        tempdir.cleanup()


async def providers_case():
    from custom_components.heating_ai_v2.source_monitor import SourceMonitor
    from homeassistant.components.weather.const import DATA_COMPONENT as WEATHER_ENTITIES
    from homeassistant.components.calendar.const import DATA_COMPONENT as CALENDAR_ENTITIES
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    callbacks = []
    unsub = Mock()

    def subscribe(kind, cb):
        assert kind == "hourly"
        callbacks.append(cb)
        return unsub

    async def weather_updates(kinds):
        assert kinds == {"hourly"}
        callbacks[0]([
            {"datetime": (now - timedelta(minutes=30)).isoformat(),
             "temperature": 2.1},
            {"datetime": (now + timedelta(minutes=30)).isoformat(),
             "temperature": 2.3},
        ])

    async def events(_hass, start, end):
        assert end > start
        return [SimpleNamespace(
            summary="3.1: ❌ Відключення",
            start=start + timedelta(minutes=40),
            end=start + timedelta(hours=3),
        )]

    weather_entity = SimpleNamespace(
        async_subscribe_forecast=subscribe,
        async_update_listeners=weather_updates,
    )
    calendar_entity = SimpleNamespace(async_get_events=events)
    hass = SimpleNamespace(
        data={
            WEATHER_ENTITIES: SimpleNamespace(get_entity=lambda eid: weather_entity),
            CALENDAR_ENTITIES: SimpleNamespace(get_entity=lambda eid: calendar_entity),
        },
        async_create_task=lambda coro, name: asyncio.create_task(coro, name=name),
        async_add_executor_job=lambda fn, *args: asyncio.to_thread(fn, *args),
    )
    observed = []
    plan_rows = {"room": {"state": "20.0", "unit": "°C"}}
    monitor = SourceMonitor(
        hass, {"weather_forecast": "weather.test", "outage_calendar": "calendar.test"},
        lambda: observed.append(True), lambda: plan_rows,
    )
    monitor.note_inputs(plan_rows)
    monitor.start()
    monitor.schedule()
    assert monitor._task is not None
    await monitor._task
    assert len(observed) >= 2
    result = monitor.brief()
    assert result["weather_hours_count"] == 2
    assert result["weather_issued_at"] is None
    assert result["outages_upcoming_count"] == 1
    assert result["normal_grid_forecast_qualified"] is False
    assert monitor.plan is not None
    assert monitor.plan["status"] == "BLOCKED_INPUTS"
    assert monitor.plan["commands_sent"] == 0
    # Changed temperature/settings invalidate previously computed suggestions.
    plan_rows["room"] = {"state": "20.5", "unit": "°C"}
    monitor.note_inputs(plan_rows)
    assert monitor.plan is None and monitor.coast is None
    monitor._next_replan = 0.0
    monitor.schedule()
    assert monitor._task is not None
    await monitor._task
    assert monitor.plan is not None
    assert monitor.plan["status"] == "BLOCKED_INPUTS"
    assert monitor.plan["commands_sent"] == 0
    assert not hasattr(hass, "services"), "Native entities need no service registry"
    assert monitor._task is not None
    for _ in range(300):
        monitor.schedule()
    assert len(callbacks) == 1, "No growing provider subscriptions"

    # Provider integration unload/reload swaps the entity object. The v2
    # observer must release its old callback and bind exactly one new one.
    fresh_callback = []
    fresh_unsub = Mock()
    fresh_weather = SimpleNamespace(
        async_subscribe_forecast=lambda kind, fn: (
            fresh_callback.append(fn), fresh_unsub
        )[1],
        async_update_listeners=weather_updates,
    )
    hass.data[WEATHER_ENTITIES] = SimpleNamespace(
        get_entity=lambda _id: fresh_weather
    )
    monitor.schedule()
    assert len(fresh_callback) == 1
    unsub.assert_called_once()
    assert monitor._weather_entity is fresh_weather
    assert monitor.weather is None
    assert monitor.brief()["weather_status"] == "UNKNOWN"
    await monitor.close()
    fresh_unsub.assert_called_once()
    assert monitor.brief()["weather_status"] == "UNKNOWN"


async def main():
    await case()
    await case(bad_meter=True)
    await case(fail_panel=True)
    await providers_case()
    print("PASS: native HA lifecycle + strictly read-only bounded real source monitor")


if __name__ == "__main__":
    asyncio.run(main())
