"""Immutable, validated values. No clocks, bindings or device defaults are read."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite


class ContractError(ValueError):
    """Invalid data at a contract boundary; messages never include the payload."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def number(value: object, *, nonnegative: bool = False) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ContractError("Expected a finite number, not a boolean")
    try:
        valid = isfinite(value) and (not nonnegative or value >= 0)
    except OverflowError:
        valid = False
    require(valid, "Number outside finite range")


def text(value: object) -> None:
    require(isinstance(value, str) and 0 < len(value) <= 128
            and all(ord(c) >= 32 for c in value), "Invalid identifier/reason")


def counter(value: object) -> None:
    require(type(value) is int and 0 <= value < 2**63, "Invalid sequence/revision")


def identifiers(values: tuple[str, ...]) -> None:
    require(type(values) is tuple and len(values) <= 64, "Expected bounded immutable identifiers")
    for value in values:
        text(value)
    require(len(set(values)) == len(values), "Duplicate identifiers")


class Missing(Enum):
    VALUE = "absent"


class Unit(str, Enum):
    CELSIUS = "°C"
    WATT = "W"
    KILOWATT = "kW"
    KWH = "kWh"
    BOOLEAN = "bool"


class QualityStatus(str, Enum):
    VALID = "valid"
    ESTIMATED = "estimated"
    STALE = "stale"
    MISSING = "missing"
    CONFLICTING = "conflicting"


class SourceKind(str, Enum):
    DIRECT = "direct"
    DERIVED = "derived"
    HELD = "held"
    FORECAST = "forecast"


@dataclass(frozen=True, slots=True, kw_only=True)
class Quality:
    status: QualityStatus
    age_s: float
    reason: str
    lower: float | None = None
    upper: float | None = None

    def __post_init__(self) -> None:
        require(isinstance(self.status, QualityStatus), "Invalid quality status")
        number(self.age_s, nonnegative=True)
        text(self.reason)
        require((self.lower is None) == (self.upper is None), "Incomplete bounds")
        if self.lower is not None and self.upper is not None:
            number(self.lower)
            number(self.upper)
            require(self.lower <= self.upper, "Inverted bounds")


@dataclass(frozen=True, slots=True, kw_only=True)
class Provenance:
    kind: SourceKind
    independent: bool
    components: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(isinstance(self.kind, SourceKind), "Invalid source kind")
        require(type(self.independent) is bool, "Invalid independence flag")
        require(not self.independent or self.kind is SourceKind.DIRECT,
                "Derived/held/forecast sources are not independent")
        identifiers(self.components)


@dataclass(frozen=True, slots=True, kw_only=True)
class Reading:
    physical_id: str
    source_id: str
    value: int | float | bool | None
    unit: Unit
    observed_at: float
    received_at: float
    quality: Quality
    provenance: Provenance
    evidence_ids: tuple[str, ...]
    signed: bool = False
    source_sequence: int | None | Missing = Missing.VALUE

    def __post_init__(self) -> None:
        text(self.physical_id)
        text(self.source_id)
        require(isinstance(self.unit, Unit), "Invalid unit")
        number(self.observed_at, nonnegative=True)
        number(self.received_at, nonnegative=True)
        require(isinstance(self.quality, Quality) and isinstance(self.provenance, Provenance),
                "Invalid quality/provenance")
        require(type(self.signed) is bool, "Invalid signed flag")
        identifiers(self.evidence_ids)
        if self.source_sequence is not None and self.source_sequence is not Missing.VALUE:
            counter(self.source_sequence)
        require(self.value is not None or self.quality.status is not QualityStatus.VALID,
                "Missing value cannot be valid")
        if self.value is not None:
            if self.unit is Unit.BOOLEAN:
                require(type(self.value) is bool, "Expected boolean reading")
            else:
                number(self.value)
                if self.unit in (Unit.WATT, Unit.KILOWATT, Unit.KWH):
                    require(self.value >= 0 or self.signed and self.unit is not Unit.KWH,
                            "Negative unsigned power/energy")
                if self.unit is Unit.CELSIUS:
                    require(self.value >= -273.15, "Below absolute zero")


def power_to_watts(reading: Reading) -> float | None:
    require(reading.unit in (Unit.WATT, Unit.KILOWATT), "Power unit required")
    if reading.value is None:
        return None
    result = float(reading.value) * (1000 if reading.unit is Unit.KILOWATT else 1)
    number(result)
    return result


def independent_measurements(readings: tuple[Reading, ...]) -> bool:
    seen: set[str] = set()
    for reading in readings:
        footprint = {reading.physical_id, *reading.provenance.components}
        if not reading.provenance.independent or seen & footprint:
            return False
        seen.update(footprint)
    return bool(readings)


def power_to_kilowatts(reading: Reading) -> float | None:
    require(reading.unit in (Unit.WATT, Unit.KILOWATT), "Power unit required")
    if reading.value is None:
        return None
    return float(reading.value) / (1000 if reading.unit is Unit.WATT else 1)


@dataclass(frozen=True, slots=True, kw_only=True)
class Clock:
    utc: float
    monotonic: float
    boot_id: str

    def __post_init__(self) -> None:
        number(self.utc, nonnegative=True)
        number(self.monotonic, nonnegative=True)
        text(self.boot_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class Revisions:
    config: int
    model: int
    topology: int

    def __post_init__(self) -> None:
        for value in (self.config, self.model, self.topology):
            counter(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class TimeWindow:
    start: float
    end: float

    def __post_init__(self) -> None:
        number(self.start, nonnegative=True)
        number(self.end, nonnegative=True)
        require(self.start < self.end, "Window must have positive UTC duration")

    def contains(self, at: float) -> bool:
        return self.start <= at < self.end


def utc_window(start: datetime, end: datetime) -> TimeWindow:
    """Caller supplies timezone objects; never load a timezone database here."""
    for boundary in (start, end):
        require(boundary.tzinfo is not None and boundary.utcoffset() is not None,
                "Timezone-aware boundary required")
        back = datetime.fromtimestamp(boundary.timestamp(), boundary.tzinfo)
        require(back.replace(tzinfo=None) == boundary.replace(tzinfo=None)
                and back.fold == boundary.fold, "Nonexistent/invalid local boundary")
    return TimeWindow(start=start.timestamp(), end=end.timestamp())


def digest(value: str) -> None:
    require(isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value), "Invalid SHA-256 identifier")


@dataclass(frozen=True, slots=True, kw_only=True)
class ControlSnapshot:
    snapshot_id: str
    input_hash: str
    boot_id: str
    revisions: Revisions
    grid_epoch: int
    owner_epoch: int
    captured_at: float
    room: Reading | None
    return_temperature: Reading | None
    thermostat: Reading | None
    grid_actual: Reading | None
    forecast_grid: bool | None
    power: Reading | None
    compute_available: bool
    hard_stop: bool
    scheduled_outage: bool

    def __post_init__(self) -> None:
        text(self.snapshot_id)
        text(self.boot_id)
        digest(self.input_hash)
        require(isinstance(self.revisions, Revisions), "Invalid revisions")
        counter(self.grid_epoch)
        counter(self.owner_epoch)
        number(self.captured_at, nonnegative=True)
        for flag in (self.compute_available, self.hard_stop, self.scheduled_outage):
            require(type(flag) is bool, "Invalid snapshot flag")
        require(self.forecast_grid is None or type(self.forecast_grid) is bool,
                "Invalid forecast grid state")
        for value, units in ((self.room, (Unit.CELSIUS,)),
                             (self.return_temperature, (Unit.CELSIUS,)),
                             (self.thermostat, (Unit.CELSIUS,)),
                             (self.grid_actual, (Unit.BOOLEAN,)),
                             (self.power, (Unit.WATT, Unit.KILOWATT))):
            require(value is None or isinstance(value, Reading) and value.unit in units,
                    "Invalid sensor role/unit")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanSegment(TimeWindow):
    conditional: bool = False

    def __post_init__(self) -> None:
        TimeWindow.__post_init__(self)
        require(type(self.conditional) is bool, "Invalid conditional flag")


@dataclass(frozen=True, slots=True, kw_only=True)
class Plan:
    plan_id: str
    boot_id: str
    revisions: Revisions
    grid_epoch: int
    owner_epoch: int
    input_hash: str
    issued_at: float
    valid_from: float
    valid_until: float
    expires_at: float
    segments: tuple[PlanSegment, ...]

    def __post_init__(self) -> None:
        text(self.plan_id)
        text(self.boot_id)
        require(isinstance(self.revisions, Revisions), "Invalid plan revisions")
        counter(self.grid_epoch)
        counter(self.owner_epoch)
        digest(self.input_hash)
        for value in (self.issued_at, self.valid_from, self.valid_until, self.expires_at):
            number(value, nonnegative=True)
        require(self.issued_at <= self.valid_from < self.valid_until <= self.expires_at,
                "Invalid plan lifetime")
        require(type(self.segments) is tuple and len(self.segments) <= 256,
                "Expected bounded immutable segments")
        previous = self.valid_from
        for segment in self.segments:
            require(isinstance(segment, PlanSegment), "Invalid segment")
            require(previous <= segment.start < segment.end <= self.valid_until,
                    "Unsorted/overlapping/out-of-horizon segments")
            previous = segment.end

    def heats_at(self, at: float) -> bool:
        return any(segment.contains(at) for segment in self.segments)
