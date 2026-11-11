"""Read-only HA-state counterpart for isolated runtime; no services or transports."""
from dataclasses import dataclass
from typing import Protocol
from packages.contracts import Clock
from packages.contracts.models import number, require
from .source_activity import Role, BINDINGS


@dataclass(frozen=True)
class PassiveBinding:
    role: Role
    entity_id: str
    device_id: str
    integration: str
    unit: str


@dataclass(frozen=True)
class HAObservation:
    entity_id: str
    device_id: str
    integration: str
    unit: str
    value: float | None
    last_reported: float
    last_updated: float
    last_changed: float
    registry_verified: bool = False
    available: bool = True
    restored: bool = False


@dataclass(frozen=True)
class IntegrationReport:
    """Integration write evidence, with NO hardware sequence or measurement assertion."""
    role: Role
    boot_id: str
    reported_at: float
    received_at: float
    last_updated: float
    last_changed: float
    value: float | None
    available: bool

    def __post_init__(self) -> None:
        require(self.role in BINDINGS and bool(self.boot_id) and type(self.available) is bool, 'Invalid integration report')
        for t in (self.reported_at, self.received_at, self.last_updated, self.last_changed):
            number(t, nonnegative=True)
        require(self.last_changed <= self.last_updated <= self.reported_at <= self.received_at, 'Invalid integration chronology')
        if self.value is not None:
            number(self.value)
        require(not self.available or self.value is not None, 'Missing integration value')
        require(self.role != 'humidity' or self.value is None or 0 <= self.value <= 100, 'Invalid humidity')


class PassiveReceiver(Protocol):
    def accept_integration_report(self, report: IntegrationReport) -> bool: ...


class PassiveSourceBridge:
    physical_commands_enabled = False

    def __init__(self, bindings: tuple[PassiveBinding, ...], *, physical_commands_enabled: bool = False, started_clock: Clock | None = None):
        require(physical_commands_enabled is False, 'Passive only')
        require(len(bindings) == 3 and {b.role for b in bindings} == set(BINDINGS), 'Incomplete passive roles')
        require(len({b.entity_id for b in bindings}) == 3, 'Ambiguous passive mapping')
        self.bindings = {b.entity_id: b for b in bindings}
        roles = {b.role: b for b in bindings}
        for b in bindings:
            require(bool(b.entity_id) and bool(b.device_id) and bool(b.integration) and b.unit == BINDINGS[b.role][2], 'Invalid passive binding')
        require(roles['temperature'].device_id == roles['humidity'].device_id
                and roles['temperature'].integration == roles['humidity'].integration, 'T&H must share verified device/integration')
        require(roles['return_water'].device_id != roles['temperature'].device_id, 'Probe must be independent')
        self.boot_id = started_clock.boot_id if started_clock is not None else None
        self.started_at = started_clock.utc if started_clock is not None else None

    def observe(self, observation: HAObservation, receiver: PassiveReceiver, clock: Clock, *, live_event: bool = False) -> bool:
        """Cached reads/restores and unverified mappings never become a new report."""
        if self.boot_id != clock.boot_id:
            self.boot_id, self.started_at = clock.boot_id, clock.utc
        binding = self.bindings.get(observation.entity_id)
        if (binding is None or observation.registry_verified is not True or observation.restored is not False
                or live_event is not True or (observation.device_id, observation.integration, observation.unit)
                != (binding.device_id, binding.integration, binding.unit)
                or self.started_at is None or not self.started_at <= observation.last_reported <= clock.utc):
            return False
        try:
            report = IntegrationReport(binding.role, clock.boot_id, observation.last_reported, clock.utc,
                observation.last_updated, observation.last_changed, observation.value, observation.available)
        except ValueError:
            return False
        return receiver.accept_integration_report(report)
