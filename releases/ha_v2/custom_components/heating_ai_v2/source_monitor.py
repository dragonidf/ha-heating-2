"""Bounded native read-only HA weather and outage-calendar subscription.

Does NOT call hass.services, HA writes, or any device. The domain entities
are read through HA Core's documented entity lifecycle interfaces.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.components.calendar.const import DATA_COMPONENT as CALENDAR_ENTITIES
from homeassistant.components.weather.const import DATA_COMPONENT as WEATHER_ENTITIES
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .forecast_sources import outage_intervals, source_summary, weather_hours

_LOGGER = logging.getLogger(__name__)
POLL_SECONDS = 1800


class SourceMonitor:
    def __init__(self, hass: HomeAssistant, bindings: dict[str, str],
                 notify: Callable[[], None],
                 read_rows: Callable[[], dict[str, dict[str, Any] | None]]) -> None:
        self.hass = hass
        self.bindings = bindings
        self.notify = notify
        self.read_rows = read_rows
        self.plan: dict[str, Any] | None = None
        self.weather: dict[str, Any] | None = None
        self.outages: dict[str, Any] | None = None
        self._weather_entity: Any = None
        self._calendar_entity: Any = None
        self._unsub: Callable[[], None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._next_pull = 0.0
        self._closed = False
        self._faults: set[str] = set()

    def start(self) -> None:
        """Discover providers. Later ticks also recover from HA reloads."""
        self._bind_sources()

    @callback
    def _bind_sources(self) -> None:
        if self._closed:
            return
        def find(component_id: str, role: str) -> Any:
            entity_id = self.bindings.get(role)
            component = self.hass.data.get(component_id)
            return (component.get_entity(entity_id)
                    if entity_id and component is not None else None)

        weather = find(WEATHER_ENTITIES, "weather_forecast")
        if weather is not self._weather_entity:
            if self._unsub is not None:
                self._unsub()
                self._unsub = None
            self._weather_entity = weather
            self.weather = None
            self.plan = None
            self._next_pull = 0.0
            if weather is not None:
                try:
                    self._unsub = weather.async_subscribe_forecast(
                        "hourly", self._weather_listener
                    )
                    self._faults.discard("weather")
                except (ValueError, TypeError, RuntimeError):
                    self._weather_entity = None
                    self._warn_once("weather")

        calendar = find(CALENDAR_ENTITIES, "outage_calendar")
        if calendar is not self._calendar_entity:
            self._calendar_entity = calendar
            self.outages = None
            self.plan = None
            self._next_pull = 0.0

    @callback
    def _weather_listener(self, points: list[dict[str, Any]] | None) -> None:
        if self._closed:
            return
        try:
            self.weather = weather_hours(points, time.time())
            self._faults.discard("weather")
        except (ValueError, TypeError, OverflowError):
            self.weather = None
            self._warn_once("weather")
        self.plan = None
        self.notify()

    def _warn_once(self, source: str) -> None:
        if source not in self._faults:
            _LOGGER.warning("V2 SHADOW external %s source unavailable; no heat authority", source)
            self._faults.add(source)

    @callback
    def schedule(self) -> None:
        """Coalesce all 60-s ticks into at most one provider read per 30 min."""
        if self._closed or (self._task is not None and not self._task.done()):
            return
        self._bind_sources()
        if self._weather_entity is None and self._calendar_entity is None:
            return
        now = time.monotonic()
        if now < self._next_pull:
            return
        self._next_pull = now + POLL_SECONDS
        self._task = self.hass.async_create_task(
            self._poll(), "heating_ai_v2_read_only_providers"
        )

    async def _poll(self) -> None:
        if self._weather_entity is not None:
            try:
                await asyncio.wait_for(
                    self._weather_entity.async_update_listeners({"hourly"}),
                    timeout=20,
                )
            except (Exception, asyncio.TimeoutError):
                self.weather = None
                self._warn_once("weather")
        if self._calendar_entity is not None and not self._closed:
            now = dt_util.now()
            end = now + timedelta(hours=48)
            try:
                events = await asyncio.wait_for(
                    self._calendar_entity.async_get_events(self.hass, now, end),
                    timeout=20,
                )
                self.outages = outage_intervals(
                    events, now.timestamp(), end.timestamp(), time.time()
                )
                self._faults.discard("calendar")
            except (Exception, asyncio.TimeoutError):
                self.outages = None
                self._warn_once("calendar")
        if not self._closed:
            try:
                from .shadow_plan import conditional_plan
                self.plan = await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        conditional_plan, self.read_rows(),
                        self.weather, self.outages, time.time(),
                    ),
                    timeout=25,
                )
                self._faults.discard("planner")
            except Exception:
                self.plan = {
                    "status": "BLOCKED_INPUTS", "reason": "planner_fault",
                    "proposal_is_command": False, "commands_sent": 0,
                }
                self._warn_once("planner")
            if not self._closed:
                self.notify()

    def brief(self) -> dict[str, Any]:
        return source_summary(self.weather, self.outages, time.time())

    async def close(self) -> None:
        self._closed = True
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self.weather = self.outages = self.plan = None
