"""Synthetic raw-report evidence; HA state writes are never hardware measurements."""
from dataclasses import dataclass
from typing import Literal
from packages.contracts import Clock
from packages.contracts.models import number, require
from .store import JSON

Role = Literal['temperature', 'humidity', 'return_water']
Origin = Literal['synthetic_raw_report', 'ha_state_write', 'recorder', 'derived', 'ui_poll']
BINDINGS = {
    'temperature': ('synthetic.living.th', 'synthetic.native.room', 'C'),
    'humidity': ('synthetic.living.th', 'synthetic.native.humidity', '%'),
    'return_water': ('synthetic.return.probe', 'synthetic.return.water', 'C'),
}


@dataclass(frozen=True)
class DeviceReport:
    role: Role
    device_id: str
    entity_id: str
    unit: str
    boot_id: str
    sequence: int
    reported_at: float
    received_at: float
    observed_at: float | None = None
    value: float | None = None
    available: bool = True
    origin: Origin = 'synthetic_raw_report'
    mapping_verified: bool = False
    report_qualified: bool = False
    measurement_qualified: bool = False
    veto: bool = False

    def __post_init__(self) -> None:
        require(self.role in BINDINGS and self.origin in ('synthetic_raw_report', 'ha_state_write', 'recorder', 'derived', 'ui_poll'), 'Invalid report role/origin')
        require(self.device_id.startswith('synthetic.') and self.entity_id.startswith('synthetic.'), 'Synthetic identities only')
        require(type(self.sequence) is int and 0 <= self.sequence < 2**53 and bool(self.boot_id), 'Invalid sequence/boot')
        for flag in (self.available, self.mapping_verified, self.report_qualified, self.measurement_qualified, self.veto):
            require(type(flag) is bool, 'Invalid report flag')
        for t in (self.reported_at, self.received_at):
            number(t, nonnegative=True)
        if self.observed_at is not None:
            number(self.observed_at, nonnegative=True)
        if self.value is not None:
            number(self.value)
        require(not self.measurement_qualified or (self.available and self.observed_at is not None and self.value is not None), 'Missing measurement')
        require(self.role != 'humidity' or self.value is None or 0 <= self.value <= 100, 'Invalid humidity')
        require(not self.veto or self.role == 'return_water', 'Only independent probe can veto')


class SourceActivity:
    def __init__(self, window_s: float = 3660):
        number(window_s)
        require(60 <= window_s <= 86400, 'Invalid activity window')
        self.window_s = window_s
        self.reports: dict[Role, tuple[DeviceReport, Clock]] = {}
        self.measurements: dict[Role, tuple[DeviceReport, Clock]] = {}
        self.veto_latched = False

    def accept(self, report: DeviceReport, clock: Clock, max_measurement_age_s: float = 30) -> bool:
        old = self.reports.get(report.role)
        measured = self.measurements.get(report.role)
        if (report.origin != 'synthetic_raw_report' or not report.mapping_verified or not report.report_qualified
                or (report.device_id, report.entity_id, report.unit) != BINDINGS[report.role]
                or report.boot_id != clock.boot_id or not 0 <= report.reported_at <= report.received_at <= clock.utc
                or report.observed_at is not None and not 0 <= report.observed_at <= report.reported_at
                or measured is not None and report.observed_at is not None and measured[0].observed_at is not None and report.observed_at < measured[0].observed_at
                or old is not None and (report.sequence <= old[0].sequence or report.reported_at <= old[0].reported_at
                    or report.received_at < old[0].received_at or (report.observed_at is not None and old[0].observed_at is not None
                        and report.observed_at < old[0].observed_at))):
            return False
        self.reports[report.role] = (report, clock)
        if (report.available and report.measurement_qualified and (measured is None
                or report.observed_at is not None and measured[0].observed_at is not None and report.observed_at > measured[0].observed_at)):
            self.measurements[report.role] = (report, clock)
            if report.role == 'return_water':
                if report.veto:
                    self.veto_latched = True
                elif report.observed_at is not None and clock.utc - report.observed_at <= max_measurement_age_s:
                    self.veto_latched = False
        return True

    def view(self, clock: Clock, max_temperature_age_s: float, *, clock_ok: bool = True) -> dict[str, JSON]:
        def age(role: Role, observed: bool = False) -> float | None:
            pair = (self.measurements if observed else self.reports).get(role)
            if pair is None or not clock_ok:
                return None
            report, anchor = pair
            at = report.observed_at if observed else report.reported_at
            if (at is None or report.boot_id != clock.boot_id or clock.monotonic < anchor.monotonic
                    or clock.utc < anchor.utc):
                return None
            return max(clock.utc - at, clock.monotonic - anchor.monotonic + anchor.utc - at)

        activity = [(age(role), pair[0].reported_at) for role, pair in self.reports.items()
                    if role in ('temperature', 'humidity') and pair[0].available and age(role) is not None]
        latest = min(activity, key=lambda p: p[0] if p[0] is not None else float('inf')) if activity else (None, None)
        activity_age, activity_at = latest
        temp = self.measurements.get('temperature')
        probe = self.measurements.get('return_water')
        temp_report = self.reports.get('temperature')
        probe_report = self.reports.get('return_water')
        failure_age = age('temperature')
        failed = temp_report is not None and not temp_report[0].available and failure_age is not None and failure_age <= max_temperature_age_s
        temp_age, probe_age = age('temperature', True), age('return_water', True)
        temp_ok = temp is not None and temp[0].available and temp[0].measurement_qualified and temp_age is not None
        probe_ok = probe is not None and probe[0].available and probe[0].measurement_qualified and probe_age is not None
        temperature_quality = 'OFFLINE' if failed else 'UNKNOWN' if not temp_ok else 'OK' if temp_age is not None and temp_age <= max_temperature_age_s else 'STALE'
        probe_quality = 'UNKNOWN' if not probe_ok or probe_report is not None and not probe_report[0].available else 'OK' if probe_age is not None and probe_age <= max_temperature_age_s else 'STALE'
        return {
            'living_device_last_activity': activity_at, 'device_age_s': activity_age,
            'device_quality': 'UNKNOWN' if activity_age is None else 'OK' if activity_age <= self.window_s else 'DEGRADED',
            'activity_window_s': self.window_s,
            'living_temperature_last_observed': temp[0].observed_at if temp_ok and temp is not None else None,
            'temperature_age_s': temp_age if temp_ok else None, 'temperature_quality': temperature_quality,
            'return_water_last_observed': probe[0].observed_at if probe_ok and probe is not None else None,
            'return_age_s': probe_age if probe_ok else None, 'return_quality': probe_quality,
            'return_veto': self.veto_latched,
            'failure_confirmed': failed, 'physical_authority': False, 'scope': 'synthetic_only',
        }
