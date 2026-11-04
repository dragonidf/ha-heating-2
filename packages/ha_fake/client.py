"""Deterministic fake event source; cannot be configured with a real HA endpoint."""

from dataclasses import dataclass, replace
from datetime import tzinfo
from packages.contracts import TimeWindow
from packages.thermal import Interval
from packages.planner.sources import WeatherSeries, OutageSchedule, weather_at
from packages.contracts.models import require, ContractError
from packages.offline.contracts import Registry, SourceEvent, Principal, ProviderEvent


@dataclass(frozen=True, slots=True)
class FakeSession:
    issuer: object
    principal: Principal


class FakeHAClient:
    def __init__(self, registry: Registry):
        require(type(registry) is Registry, "Typed fake registry required")
        self.registry = registry
        self.connected = False
        self.generation = 0
        self._providers: dict[str, ProviderEvent] = {}
        self._seal = object()
        self._grants: dict[str, Principal] = {}
        self._events: dict[str, SourceEvent] = {}
        self._pending: list[SourceEvent] = []

    def connect(self) -> None:
        self.connected = True
        self.generation += 1
        self._pending = []
        self._providers = {}

    def disconnect(self) -> None:
        self.connected = False
        self.generation += 1
        self._pending = []
        self._providers = {}

    def grant(self, principal: Principal) -> FakeSession:
        old = self._grants.get(principal.identity)
        require(
            old is None or principal.epoch > old.epoch, "Grant epoch cannot be reused"
        )
        self._grants[principal.identity] = principal
        return FakeSession(self._seal, principal)

    def revoke(self, identity: str) -> None:
        old = self._grants[identity]
        self._grants[identity] = replace(old, permissions=(), epoch=old.epoch + 1)

    def permits(self, session: FakeSession | None, permission: str) -> bool:
        return (
            type(session) is FakeSession
            and session.issuer is self._seal
            and self._grants.get(session.principal.identity) == session.principal
            and permission in session.principal.permissions
        )

    def push(self, event: SourceEvent) -> bool:
        require(self.connected, "Fake event source disconnected")
        binding = next(
            (b for b in self.registry.bindings if b.entity == event.entity), None
        )
        require(binding is not None, "No binding; no guessed entity")
        if binding is not None and event.reading is not None:
            require(
                (event.reading.physical_id, event.reading.source_id, event.reading.unit)
                == (binding.physical_id, binding.source_id, binding.unit),
                "Event binding/unit mismatch",
            )
        old = self._events.get(event.identity)
        if old is not None:
            require(old == event, "Conflicting duplicate event")
            return False
        normal = [i for i, e in enumerate(self._pending) if e.author == "sensor"]
        if (
            len(self._events) >= 4096
            or event.author != "sensor"
            and len(self._pending) - len(normal) >= 128
        ):
            self.connected = False
            raise ContractError(
                "Source replay capacity exhausted; fake input unavailable"
            )
        if event.author == "sensor" and len(normal) >= 128:
            index = next(
                (
                    i
                    for i in reversed(normal)
                    if self._pending[i].entity == event.entity
                ),
                normal[0],
            )
            self._pending.pop(
                index
            )  # All raw source facts remain in the separate bounded journal.

        self._events[event.identity] = event
        self._pending.append(event)
        return True

    @property
    def raw_count(self) -> int:
        return len(self._events)

    def raw_page(self, after: int, limit: int = 256) -> tuple[SourceEvent, ...]:
        require(
            type(after) is int
            and 0 <= after <= len(self._events)
            and type(limit) is int
            and 1 <= limit <= 256,
            "Invalid raw journal cursor",
        )
        return tuple(list(self._events.values())[after : after + limit])

    def drain(self, order: tuple[int, ...] | None = None) -> tuple[SourceEvent, ...]:
        if order is None:
            order = tuple(range(len(self._pending)))
        require(
            type(order) is tuple
            and all(type(i) is int for i in order)
            and sorted(order) == list(range(len(self._pending))),
            "Invalid deterministic replay order",
        )
        result = tuple(self._pending[i] for i in order)
        self._pending = []
        return result

    def publish(self, event: ProviderEvent) -> bool:
        require(self.connected, "Fake provider disconnected")
        binding = next(
            (b for b in self.registry.bindings if b.entity == event.entity), None
        )
        role = "weather" if isinstance(event.forecast, WeatherSeries) else "outage"
        require(
            binding is not None
            and binding.role == role
            and binding.source_id == event.forecast.header.source_id,
            "Provider binding mismatch",
        )
        previous = self._providers.get(event.entity)
        if previous is not None:
            if event.identity == previous.identity:
                require(event == previous, "Provider identity conflict")
                return False
            if (
                event.sequence <= previous.sequence
                or event.received_at < previous.received_at
            ):
                return False
        self._providers[event.entity] = event
        return True

    def weather(self, at: float, now: float) -> Interval | None:
        if not self.connected:
            return None
        for b in sorted(
            (b for b in self.registry.bindings if b.role == "weather"),
            key=lambda b: b.priority,
        ):
            event = self._providers.get(b.entity)
            if event and isinstance(event.forecast, WeatherSeries):
                value = weather_at(event.forecast, at, now, b.max_age_s)
                if value is not None:
                    return value
        return None

    def grid_forecast(
        self, window: TimeWindow, now: float, region: str, queue: str, zone: tzinfo
    ) -> str:
        if not self.connected:
            return "unknown"
        statuses = []
        for b in self.registry.bindings:
            event = self._providers.get(b.entity)
            if (
                b.role == "outage"
                and event
                and isinstance(event.forecast, OutageSchedule)
            ):
                statuses.append(
                    event.forecast.status(window, region, queue, now, zone, b.max_age_s)
                )
        if "emergency" in statuses:
            return "emergency"
        if "scheduled_off" in statuses:
            return "scheduled_off"
        return "normal" if "normal" in statuses else "unknown"
