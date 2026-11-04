"""Frozen WP2A schema. Identifiers in fixtures are artificial; units are explicit."""

from dataclasses import dataclass
from typing import Literal
from packages.contracts import (
    Reading,
    Unit,
    TimeWindow,
    ControlPolicy,
    ControlState,
    Plan,
    OneShot,
    Action,
    ReceiptStage,
    QualityStatus,
)
from packages.contracts.models import (
    text,
    number,
    require,
    counter,
    identifiers,
    digest,
)
from packages.thermal import Coefficients
from packages.planner import Curve
from packages.fan_policy import FanState, FanPolicy
from packages.planner.sources import WeatherSeries, OutageSchedule

Category = Literal["confirmed", "derived", "estimated", "unknown", "recovered"]
ROLES = (
    "room",
    "return",
    "thermostat",
    "grid",
    "inlet",
    "group",
    "load",
    "deye_grid",
    "deye_load",
    "phase",
    "weather",
    "outage",
    "calendar",
    "fan",
    "fireplace",
    "helper",
    "counter",
)


@dataclass(frozen=True, slots=True)
class Binding:
    entity: str
    role: str
    physical_id: str
    source_id: str
    unit: Unit
    max_age_s: float
    priority: int
    capabilities: tuple[str, ...]
    coverage: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None

    def __post_init__(self) -> None:
        for v in (self.entity, self.physical_id, self.source_id):
            text(v)
        require(
            self.entity.startswith("synthetic."), "Only synthetic handles are supported"
        )
        require(
            self.role in ROLES and isinstance(self.unit, Unit),
            "Invalid binding role/unit",
        )
        number(self.max_age_s, nonnegative=True)
        counter(self.priority)
        identifiers(self.capabilities)
        identifiers(self.coverage)
        require(
            "read" in self.capabilities
            and set(self.capabilities)
            <= {
                "read",
                "temperature",
                "power",
                "counter",
                "propose",
                "percentage",
                "setpoint",
            },
            "Invalid capabilities",
        )
        expected = (
            (Unit.CELSIUS,)
            if self.role in ("room", "return", "thermostat", "weather", "fireplace")
            else (
                (Unit.KWH,)
                if self.role == "counter"
                else (
                    (Unit.WATT, Unit.KILOWATT)
                    if self.role
                    in ("inlet", "group", "load", "deye_grid", "deye_load", "phase")
                    else (Unit.BOOLEAN,)
                )
            )
        )
        require(self.unit in expected, "Binding unit mismatch")
        for bound in (self.minimum, self.maximum, self.step):
            if bound is not None:
                number(bound)
        require(
            (self.minimum is None) == (self.maximum is None),
            "Incomplete capability bounds",
        )
        if self.minimum is not None and self.maximum is not None:
            require(self.minimum < self.maximum, "Invalid capability bounds")
        if self.step is not None:
            require(
                self.step > 0 and self.minimum is not None, "Invalid capability step"
            )
        if self.role == "fan" and self.minimum is not None and self.maximum is not None:
            require(
                0 <= self.minimum < self.maximum <= 100, "Fan percentage bounds invalid"
            )
        if "propose" in self.capabilities:
            require(
                self.role in ("thermostat", "fan")
                and self.minimum is not None
                and self.step is not None,
                "Unqualified fake actuator capability",
            )


@dataclass(frozen=True, slots=True)
class Registry:
    revision: int
    bindings: tuple[Binding, ...]
    max_skew_s: float
    alias_policy: Literal["prefer_priority", "conflict_unknown"]
    conflict_tolerance: float
    version: int = 1

    def __post_init__(self) -> None:
        counter(self.revision)
        number(self.max_skew_s, nonnegative=True)
        number(self.conflict_tolerance, nonnegative=True)
        require(
            type(self.version) is int and self.version == 1,
            "Unsupported mapping schema",
        )
        require(
            self.alias_policy in ("prefer_priority", "conflict_unknown"),
            "Invalid alias policy",
        )
        require(
            type(self.bindings) is tuple
            and len(self.bindings) <= 128
            and all(isinstance(b, Binding) for b in self.bindings),
            "Invalid binding set",
        )
        require(
            len({b.source_id for b in self.bindings}) == len(self.bindings),
            "Duplicate source identity",
        )
        require(
            len({b.entity for b in self.bindings}) == len(self.bindings),
            "Duplicate entity binding",
        )
        for i, b in enumerate(self.bindings):
            for other in self.bindings[:i]:
                if b.role == other.role:
                    require(
                        b.physical_id == other.physical_id
                        or b.role in ("phase", "load", "group", "helper", "counter"),
                        "Role has multiple physical devices",
                    )
                    if b.physical_id == other.physical_id:
                        require(
                            b.priority != other.priority, "Ambiguous alias precedence"
                        )
                if b.physical_id == other.physical_id:
                    require(
                        b.role == other.role
                        and b.unit == other.unit
                        and b.coverage == other.coverage,
                        "Physical alias mismatch",
                    )


@dataclass(frozen=True, slots=True)
class SourceEvent:
    identity: str
    entity: str
    sequence: int
    received_at: float
    reading: Reading | None
    author: Literal["sensor", "manual", "unknown", "automatic_echo"] = "sensor"
    observed_action: Action | None = None

    def __post_init__(self) -> None:
        text(self.identity)
        text(self.entity)
        counter(self.sequence)
        number(self.received_at, nonnegative=True)
        require(
            self.author in ("sensor", "manual", "unknown", "automatic_echo"),
            "Invalid event author",
        )
        require(
            self.reading is None or isinstance(self.reading, Reading),
            "Invalid event measurement",
        )
        require(
            self.observed_action is None or isinstance(self.observed_action, Action),
            "Invalid observed action",
        )
        if self.reading is not None:
            require(
                self.reading.received_at == self.received_at,
                "Event/source receive mismatch",
            )


@dataclass(frozen=True, slots=True)
class Principal:
    identity: str
    permissions: tuple[str, ...]
    epoch: int

    def __post_init__(self) -> None:
        text(self.identity)
        identifiers(self.permissions)
        counter(self.epoch)
        require(
            set(self.permissions) <= {"read", "control", "admin"}, "Invalid permissions"
        )


@dataclass(frozen=True, slots=True)
class SaveRequest:
    identity: str
    expected_revision: int
    policy: ControlPolicy

    def __post_init__(self) -> None:
        text(self.identity)
        counter(self.expected_revision)
        require(isinstance(self.policy, ControlPolicy), "Invalid settings")


@dataclass(frozen=True, slots=True)
class APIReceipt:
    request_id: str
    status: Literal[
        "saved", "denied", "conflict", "unavailable", "accepted_fake", "observed_fake"
    ]
    revision: int
    persisted_revision: int | None
    reason: str

    def __post_init__(self) -> None:
        text(self.request_id)
        text(self.reason)
        counter(self.revision)
        require(
            self.status
            in (
                "saved",
                "denied",
                "conflict",
                "unavailable",
                "accepted_fake",
                "observed_fake",
            ),
            "Invalid receipt",
        )
        if self.persisted_revision is not None:
            counter(self.persisted_revision)
        require(
            (self.status == "saved") == (self.persisted_revision is not None),
            "Saved receipt needs durable revision",
        )


@dataclass(frozen=True, slots=True)
class PowerPoint:
    identity: str
    stream: str
    at: float
    received: float
    kw: float | None
    category: Category
    sources: tuple[str, ...]
    method: str
    raw_w: float | None = None

    def __post_init__(self) -> None:
        for v in (self.identity, self.stream, self.method):
            text(v)
        number(self.at, nonnegative=True)
        number(self.received, nonnegative=True)
        require(self.received >= self.at, "Power receive predates observation")
        require(
            self.category in ("confirmed", "derived", "estimated", "unknown"),
            "Invalid power category",
        )
        if self.kw is not None:
            number(self.kw, nonnegative=True)
        if self.raw_w is not None:
            number(self.raw_w)
        require(
            (self.category == "unknown") == (self.kw is None),
            "Unknown power must remain null",
        )
        identifiers(self.sources)
        require(self.kw is None or bool(self.sources), "Known power needs lineage")


@dataclass(frozen=True, slots=True)
class CounterPoint:
    identity: str
    stream: str
    at: float
    kwh: float
    source: str

    def __post_init__(self) -> None:
        for v in (self.identity, self.stream, self.source):
            text(v)
        number(self.at, nonnegative=True)
        number(self.kwh, nonnegative=True)


@dataclass(frozen=True, slots=True)
class EnergySlice:
    identity: str
    stream: str
    continuity: str
    start: float
    end: float
    category: Category
    kwh: float | None
    sources: tuple[str, ...]
    method: str

    def __post_init__(self) -> None:
        for v in (self.identity, self.stream, self.continuity, self.method):
            text(v)
        TimeWindow(start=self.start, end=self.end)
        require(
            self.category
            in ("confirmed", "derived", "estimated", "unknown", "recovered"),
            "Invalid energy category",
        )
        if self.kwh is not None:
            number(self.kwh, nonnegative=True)
        require(
            (self.category == "unknown") == (self.kwh is None),
            "Unknown energy must remain null",
        )
        identifiers(self.sources)
        require(self.kwh is None or bool(self.sources), "Known energy needs lineage")


@dataclass(frozen=True, slots=True)
class Origin:
    stream: str
    continuity: str
    at: float
    initial_kwh: float

    def __post_init__(self) -> None:
        text(self.stream)
        text(self.continuity)
        number(self.at, nonnegative=True)
        number(self.initial_kwh, nonnegative=True)


@dataclass(frozen=True, slots=True)
class Tariff:
    identity: str
    start: float
    end: float
    per_kwh: float
    currency: str

    def __post_init__(self) -> None:
        text(self.identity)
        text(self.currency)
        TimeWindow(start=self.start, end=self.end)
        number(self.per_kwh, nonnegative=True)


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    identity: str
    cycle_id: str
    role: Literal["initial", "prestart", "latest", "original"]
    reference: float
    curve: Curve | None
    recorded_at: float
    planned_kwh: float | None
    energy_scope: TimeWindow | None = None

    def __post_init__(self) -> None:
        text(self.identity)
        text(self.cycle_id)
        number(self.reference, nonnegative=True)
        require(
            self.role in ("initial", "prestart", "latest", "original"),
            "Invalid forecast role",
        )
        number(self.recorded_at, nonnegative=True)
        require(
            self.curve is None
            and self.role == "original"
            or isinstance(self.curve, Curve)
            and self.curve.issued <= self.recorded_at,
            "Invalid forecast evidence",
        )
        if self.planned_kwh is not None:
            number(self.planned_kwh, nonnegative=True)
        if self.energy_scope is not None:
            require(
                isinstance(self.energy_scope, TimeWindow)
                and self.energy_scope.start == self.reference,
                "Invalid forecast energy scope",
            )
        if self.role in ("original", "initial", "prestart"):
            require(
                self.recorded_at <= self.reference, "Cannot backfill frozen forecast"
            )
        if self.role == "original" and self.curve is not None:
            require(
                self.curve.issued <= self.reference - 43200
                and self.curve.points[0][0]
                <= self.reference
                <= self.curve.points[-1][0],
                "Original forecast has no actual lead/coverage",
            )


@dataclass(frozen=True, slots=True)
class ArchiveRecord:
    identity: str
    kind: str
    at: float
    stream: str
    payload: str

    def __post_init__(self) -> None:
        for v in (self.identity, self.kind, self.stream):
            text(v)
        number(self.at, nonnegative=True)
        require(
            type(self.payload) is str and 0 < len(self.payload.encode()) <= 524288,
            "Invalid archive payload",
        )


@dataclass(frozen=True, slots=True)
class Cursor:
    watermark: int
    last_at: float
    last_seq: int
    query_hash: str

    def __post_init__(self) -> None:
        counter(self.watermark)
        counter(self.last_seq)
        number(self.last_at)
        digest(self.query_hash)
        require(self.last_seq <= self.watermark, "Invalid cursor frontier")


@dataclass(frozen=True, slots=True)
class RecoveryProof:
    """Content-addressed claim checked against two immutable direct meter readings."""

    stream: str
    continuity: str
    unknown_ids: tuple[str, ...]
    window: TimeWindow
    source_id: str
    physical_id: str
    left_id: str
    right_id: str
    kwh: float
    quality: QualityStatus
    method: Literal["counter_difference"] = "counter_difference"

    def __post_init__(self) -> None:
        for value in (
            self.stream,
            self.continuity,
            self.source_id,
            self.physical_id,
            self.left_id,
            self.right_id,
        ):
            text(value)
        identifiers(self.unknown_ids)
        require(
            bool(self.unknown_ids) and self.left_id != self.right_id,
            "Missing recovery evidence",
        )
        require(
            isinstance(self.window, TimeWindow)
            and isinstance(self.quality, QualityStatus)
            and self.method == "counter_difference",
            "Invalid recovery proof",
        )
        number(self.kwh, nonnegative=True)


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    identity: str
    unknown_ids: tuple[str, ...]
    kwh: float
    expected_total: float
    backup_hash: str
    evidence_hash: str

    def __post_init__(self) -> None:
        text(self.identity)
        identifiers(self.unknown_ids)
        require(bool(self.unknown_ids), "No recovery coverage")
        number(self.kwh, nonnegative=True)
        number(self.expected_total, nonnegative=True)
        digest(self.backup_hash)
        digest(self.evidence_hash)


@dataclass(frozen=True, slots=True)
class RecoveryReceipt:
    identity: str
    dry_run: bool
    total_before: float
    total_after: float
    recovered_s: float
    revision: int

    def __post_init__(self) -> None:
        text(self.identity)
        require(type(self.dry_run) is bool, "Invalid dry-run flag")
        for v in (self.total_before, self.total_after, self.recovered_s):
            number(v, nonnegative=True)
        counter(self.revision)
        require(self.total_after >= self.total_before, "Recovery cannot lower total")


@dataclass(frozen=True, slots=True)
class CounterMapping:
    source_key: str
    target_key: str
    value: float
    continuity: str
    unit: Unit = Unit.KWH

    def __post_init__(self) -> None:
        for v in (self.source_key, self.target_key, self.continuity):
            text(v)
        number(self.value, nonnegative=True)
        require(self.unit is Unit.KWH, "Counter must use kWh")


@dataclass(frozen=True, slots=True)
class LegacyBundle:
    identity: str
    captured_at: float
    counters: tuple[CounterMapping, ...]
    coefficients: Coefficients
    plan: Plan | None
    one_shots: tuple[OneShot, ...]
    fan: FanState
    fan_policy: FanPolicy
    curves: tuple[ForecastRecord, ...]
    policy: ControlPolicy
    state: ControlState
    version: int = 1

    def __post_init__(self) -> None:
        text(self.identity)
        number(self.captured_at, nonnegative=True)
        require(
            type(self.version) is int and self.version == 1,
            "Unknown synthetic legacy schema",
        )
        require(
            type(self.counters) is tuple and 0 < len(self.counters) <= 64,
            "Invalid migration counters",
        )
        require(
            len({c.target_key for c in self.counters}) == len(self.counters)
            and len({c.source_key for c in self.counters}) == len(self.counters),
            "Duplicate counter mapping",
        )
        require(
            type(self.one_shots) is tuple
            and len(self.one_shots) <= 64
            and type(self.curves) is tuple
            and len(self.curves) <= 64,
            "Unbounded legacy evidence",
        )
        require(
            len({c.continuity for c in self.counters}) == len(self.counters),
            "Duplicate counter continuity",
        )
        require(
            self.fan.at <= self.captured_at
            and all(s.created_at <= self.captured_at for s in self.one_shots)
            and all(c.recorded_at <= self.captured_at for c in self.curves),
            "Future legacy evidence",
        )
        require(
            len({s.intent_id for s in self.one_shots}) == len(self.one_shots),
            "Duplicate one-shot identity",
        )


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    source_key: str
    target_key: str
    source_version: str
    target_version: str
    unit: str
    continuity_key: str
    checksum: str

    def __post_init__(self) -> None:
        for v in (
            self.source_key,
            self.target_key,
            self.source_version,
            self.target_version,
            self.unit,
            self.continuity_key,
        ):
            text(v)
        digest(self.checksum)


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    identity: str
    source_hash: str
    bundle: LegacyBundle
    manifest: tuple[ManifestEntry, ...]

    def __post_init__(self) -> None:
        text(self.identity)
        digest(self.source_hash)
        require(
            type(self.manifest) is tuple and len(self.manifest) <= 256,
            "Invalid manifest",
        )
        require(
            all(isinstance(entry, ManifestEntry) for entry in self.manifest),
            "Invalid manifest entry",
        )
        require(
            len({entry.target_key for entry in self.manifest}) == len(self.manifest),
            "Duplicate manifest target",
        )


@dataclass(frozen=True, slots=True)
class BalanceTopology:
    inlet: Binding
    grid: Binding
    subtract: tuple[Binding, ...]
    qualified: bool
    max_kw: float
    max_age_s: float
    max_skew_s: float

    def __post_init__(self) -> None:
        require(
            isinstance(self.inlet, Binding)
            and self.inlet.role == "inlet"
            and isinstance(self.grid, Binding)
            and self.grid.role == "deye_grid",
            "Invalid balance inlet/GRID",
        )
        require(
            type(self.qualified) is bool
            and type(self.subtract) is tuple
            and len(self.subtract) <= 32,
            "Invalid balance qualification",
        )
        for v in (self.max_kw, self.max_age_s, self.max_skew_s):
            number(v, nonnegative=True)
        require(self.max_kw > 0, "Invalid physical bound")
        seen = {self.inlet.physical_id, self.grid.physical_id}
        require(len(seen) == 2, "Inlet/GRID aliases overlap")
        loads: set[str] = set()
        for b in self.subtract:
            require(
                isinstance(b, Binding)
                and b.role in ("group", "load", "phase")
                and b.physical_id not in seen,
                "Invalid or repeated subtraction",
            )
            footprint = set(b.coverage or (b.physical_id,))
            require(not footprint & loads, "Phase/group/load overlap")
            loads |= footprint
            seen.add(b.physical_id)


@dataclass(frozen=True, slots=True)
class ArchivePage:
    rows: tuple[tuple[int, ArchiveRecord], ...]
    cursor: Cursor | None
    watermark: int

    def __post_init__(self) -> None:
        counter(self.watermark)
        require(
            type(self.rows) is tuple and len(self.rows) <= 256, "Invalid archive page"
        )
        for seq, record in self.rows:
            counter(seq)
            require(
                seq <= self.watermark and isinstance(record, ArchiveRecord),
                "Invalid page row",
            )


@dataclass(frozen=True, slots=True)
class EnergySummary:
    stream: str
    initial_kwh: float
    confirmed_kwh: float
    derived_kwh: float
    estimated_kwh: float
    recovered_kwh: float
    unknown_s: float
    actual_total_kwh: float
    watermark: int

    def __post_init__(self) -> None:
        text(self.stream)
        counter(self.watermark)
        for v in (
            self.initial_kwh,
            self.confirmed_kwh,
            self.derived_kwh,
            self.estimated_kwh,
            self.recovered_kwh,
            self.unknown_s,
            self.actual_total_kwh,
        ):
            number(v, nonnegative=True)
        require(
            abs(
                self.actual_total_kwh
                - self.initial_kwh
                - self.confirmed_kwh
                - self.derived_kwh
                - self.recovered_kwh
            )
            < 1e-8,
            "Actual total category mismatch",
        )


@dataclass(frozen=True, slots=True)
class MigrationReceipt:
    identity: str
    source_hash: str
    first_seq: int
    last_seq: int
    automatic_armed: bool = False

    def __post_init__(self) -> None:
        text(self.identity)
        digest(self.source_hash)
        counter(self.first_seq)
        counter(self.last_seq)
        require(
            self.first_seq <= self.last_seq and self.automatic_armed is False,
            "Import cannot activate control",
        )


@dataclass(frozen=True, slots=True)
class RollbackResult:
    bundle: LegacyBundle
    source_hash: str
    copied_seq: int
    artifact_hash: str

    def __post_init__(self) -> None:
        digest(self.source_hash)
        digest(self.artifact_hash)
        counter(self.copied_seq)
        require(
            not self.bundle.policy.armed
            and not self.bundle.policy.allow_automatic
            and not self.bundle.state.reconciled,
            "Rollback copy must remain disarmed",
        )


@dataclass(frozen=True, slots=True)
class CostSummary:
    known_cost: float
    estimated_cost: float
    unpriced_kwh: float
    unknown_s: float
    currency: str | None

    def __post_init__(self) -> None:
        for v in (
            self.known_cost,
            self.estimated_cost,
            self.unpriced_kwh,
            self.unknown_s,
        ):
            number(v, nonnegative=True)
        if self.currency is not None:
            text(self.currency)


@dataclass(frozen=True, slots=True)
class StatusView:
    status_seq: int
    boot_id: str
    owner_epoch: int
    actual: Action | None
    desired: Action
    mode: str
    snapshot_id: str
    snapshot_at: float
    archive_pending: int
    archive_lost: int
    receipt_stage: ReceiptStage | None
    physical_verified: bool = False

    def __post_init__(self) -> None:
        for v in (
            self.status_seq,
            self.owner_epoch,
            self.archive_pending,
            self.archive_lost,
        ):
            counter(v)
        for value in (self.boot_id, self.mode, self.snapshot_id):
            text(value)
        number(self.snapshot_at, nonnegative=True)
        require(
            self.actual is None or isinstance(self.actual, Action),
            "Invalid actual action",
        )
        require(
            isinstance(self.desired, Action)
            and (
                self.receipt_stage is None
                or isinstance(self.receipt_stage, ReceiptStage)
            ),
            "Invalid status receipt",
        )
        require(
            self.physical_verified is False,
            "Fake status cannot verify a physical device",
        )


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    identity: str
    entity: str
    sequence: int
    received_at: float
    forecast: WeatherSeries | OutageSchedule

    def __post_init__(self) -> None:
        text(self.identity)
        text(self.entity)
        counter(self.sequence)
        number(self.received_at, nonnegative=True)
        require(
            isinstance(self.forecast, (WeatherSeries, OutageSchedule))
            and self.forecast.header.received == self.received_at,
            "Invalid provider event",
        )


@dataclass(frozen=True, slots=True)
class BudgetReceipt:
    cycle_id: str
    stream: str
    reference_kwh: float | None
    known_spent_kwh: float
    unknown_s: float
    latest_projected_kwh: float
    known_remaining_kwh: float | None
    projected_overrun_kwh: float | None
    watermark: int
    scope: TimeWindow | None = None
    actual_until: float | None = None

    def __post_init__(self) -> None:
        text(self.cycle_id)
        text(self.stream)
        counter(self.watermark)
        for v in (self.known_spent_kwh, self.unknown_s, self.latest_projected_kwh):
            number(v, nonnegative=True)
        if self.reference_kwh is not None:
            number(self.reference_kwh, nonnegative=True)
            require(
                isinstance(self.scope, TimeWindow), "Known budget reference needs scope"
            )
        if self.actual_until is not None:
            number(self.actual_until, nonnegative=True)
            require(
                self.scope is None
                or self.scope.start < self.actual_until <= self.scope.end,
                "Invalid budget actual scope",
            )
        if self.known_remaining_kwh is not None:
            number(self.known_remaining_kwh)
        if self.projected_overrun_kwh is not None:
            number(self.projected_overrun_kwh, nonnegative=True)
