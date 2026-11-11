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
                 notify: Callable[[], None]) -> None:
        self.hass = hass
        self.bindings = bindings
        self.notify = notify
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
        """Register ONE subscription to a selected WeatherEntity if present."""
        if self._closed:
            return
        if entity_id := self.bindings.get("weather_forecast"):
            component = self.hass.data.get(WEATHER_ENTITIES)
            if component is not None:
                entity = component.get_entity(entity_id)
                if entity is not None:
                    self._weather_entity = entity
                    self._unsub = entity.async_subscribe_forecast(
                        "hourly", self._weather_listener
                    )
        if entity_id := self.bindings.get("outage_calendar"):
            component = self.hass.data.get(CALENDAR_ENTITIES)
            if component is not None:
                self._calendar_entity = component.get_entity(entity_id)

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
        self.weather = self.outages = None
