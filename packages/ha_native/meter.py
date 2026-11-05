"""Future boiler-meter seam. Every binding and observation here is synthetic only.

No model, wiring, accuracy class or device transport is assumed. Explicit fixture
verification permits synthetic evidence selection, never physical qualification.
"""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import Literal

from packages.contracts import Quality, QualityStatus, SourceKind
from packages.contracts.models import counter, identifiers, number, require, text
from packages.evidence.energy import counter_delta
from packages.offline.contracts import CounterPoint, EnergySlice, PowerPoint

Quantity = Literal["active_power", "imported_energy", "voltage", "current", "apparent_power"]
Phase = Literal["total", "L1", "L2", "L3"]
MeterUnit = Literal["W", "kWh", "V", "A", "VA"]
Protection = Literal["unknown", "normal", "tripped"]
_UNITS = {"active_power": "W", "imported_energy": "kWh", "voltage": "V",
          "current": "A", "apparent_power": "VA"}


def _synthetic(value: str) -> None:
    text(value)
    require(value.startswith("synthetic.") and len(value) > 10,
            "Only artificial synthetic identifiers are supported")


def _synthetic_ids(values: tuple[str, ...]) -> None:
    identifiers(values)
    for value in values:
        _synthetic(value)


def _identity(value: object) -> str:
    return "synthetic." + sha256(repr(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MeterChannel:
    source_id: str
    entity_id: str
    quantity: Quantity
    unit: MeterUnit
    phase: Phase = "total"

    def __post_init__(self) -> None:
        _synthetic(self.source_id)
        _synthetic(self.entity_id)
        require(isinstance(self.quantity, str) and self.quantity in _UNITS
                and self.unit == _UNITS[self.quantity],
                "Meter quantity/unit mismatch")
        require(self.phase in ("total", "L1", "L2", "L3"), "Invalid meter phase")


@dataclass(frozen=True, slots=True)
class SyntheticMeterVerification:
    """Assertions about an artificial fixture, never claims about delivered hardware."""

    evidence_ids: tuple[str, ...]
    boiler_only: bool = False
    auxiliaries_included: bool = False
    phase_mapping: bool = False
    import_direction: bool = False
    counter_accuracy: bool = False

    def __post_init__(self) -> None:
        _synthetic_ids(self.evidence_ids)
        require(0 < len(self.evidence_ids) <= 16, "Missing synthetic verification")
        for flag in (self.boiler_only, self.auxiliaries_included, self.phase_mapping,
                     self.import_direction, self.counter_accuracy):
            require(type(flag) is bool, "Invalid synthetic verification flag")

    @property
    def qualified(self) -> bool:
        return all((self.boiler_only, self.auxiliaries_included, self.phase_mapping,
                    self.import_direction, self.counter_accuracy))


@dataclass(frozen=True, slots=True)
class MeterBinding:
    meter_id: str = "synthetic.unbound"
    channels: tuple[MeterChannel, ...] = ()
    coverage: tuple[str, ...] = ()
    verification: SyntheticMeterVerification | None = None
    max_age_s: float = 45
    max_skew_s: float = 5
    max_kw: float = 12
    phase_tolerance_w: float = 20
    version: int = 1

    def __post_init__(self) -> None:
        _synthetic(self.meter_id)
        require(type(self.version) is int and self.version == 1, "Unsupported meter schema")
        require(type(self.channels) is tuple and len(self.channels) <= 16
                and all(isinstance(c, MeterChannel) for c in self.channels),
                "Invalid meter channels")
        _synthetic_ids(self.coverage)
        require(not self.channels or bool(self.coverage), "Bound meter needs accounting coverage")
        require(self.verification is None or isinstance(self.verification, SyntheticMeterVerification),
                "Invalid synthetic verification")
        for values in ((c.source_id for c in self.channels), (c.entity_id for c in self.channels),
                       ((c.quantity, c.phase) for c in self.channels)):
            require(len(set(values)) == len(self.channels), "Duplicate meter channel")
        phases = {c.phase for c in self.channels if c.quantity == "active_power" and c.phase != "total"}
        require(not phases or phases == {"L1", "L2", "L3"}, "Incomplete active phase mapping")
        for value in (self.max_age_s, self.max_skew_s, self.max_kw, self.phase_tolerance_w):
            number(value, nonnegative=True)
        require(self.max_age_s <= 45 and self.max_kw > 0, "Invalid meter limits")

    @property
    def physical_qualification(self) -> Literal["unverified"]:
        return "unverified"

    @property
    def physical_authority(self) -> Literal[False]:
        return False


def future_meter_binding(source_id: str = "") -> MeterBinding:
    """Options placeholder only: a fake source ID never supplies capability/proof."""
    if source_id == "":
        return MeterBinding()
    _synthetic(source_id)
    return MeterBinding(meter_id=source_id)


def binding_summary(binding: MeterBinding) -> dict[str, str | bool | None]:
    """Bounded public diagnostics; fixture verification never closes a physical gate."""
    return {
        "source_id": None if binding.meter_id == "synthetic.unbound" else binding.meter_id,
        "bound": bool(binding.channels),
        "synthetic_verified": binding.verification is not None and binding.verification.qualified,
        "active_power_supported": any(c.quantity == "active_power" for c in binding.channels),
        "imported_energy_supported": any(c.quantity == "imported_energy" and c.phase == "total"
                                         for c in binding.channels),
        "physical_model": "unknown", "physical_wiring": "unknown", "physical_accuracy": "unknown",
        "physical_authority": False, "scope": "synthetic_only", "B03": "BLOCKED",
    }


@dataclass(frozen=True, slots=True)
class MeterSample:
    source_id: str
    value: float | None
    unit: MeterUnit
    observed_at: float
    received_at: float
    sequence: int
    quality: Quality
    origin: SourceKind = SourceKind.DIRECT
    origin_id: str = "synthetic.fixture"
    components: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _synthetic(self.source_id)
        _synthetic(self.origin_id)
        _synthetic_ids(self.components)
        require(self.unit in _UNITS.values(), "Unsupported meter unit")
        number(self.observed_at, nonnegative=True)
        number(self.received_at, nonnegative=True)
        counter(self.sequence)
        require(isinstance(self.quality, Quality) and isinstance(self.origin, SourceKind),
                "Invalid meter quality/origin")
        require(self.value is not None or self.quality.status is not QualityStatus.VALID,
                "Missing meter value cannot be valid")
        if self.value is not None:
            number(self.value, nonnegative=True)


@dataclass(frozen=True, slots=True)
class MeterFrame:
    """Timestamped online/protection metadata does not prove heater operation."""

    at: float
    received_at: float
    samples: tuple[MeterSample, ...] = ()
    online: bool | None = None
    relay_on: bool | None = None
    protection: Protection = "unknown"
    quality: Quality = field(default_factory=lambda: Quality(
        status=QualityStatus.VALID, age_s=0, reason="synthetic.metadata"))

    def __post_init__(self) -> None:
        number(self.at, nonnegative=True)
        number(self.received_at, nonnegative=True)
        require(type(self.samples) is tuple and len(self.samples) <= 16
                and all(isinstance(s, MeterSample) for s in self.samples), "Invalid meter samples")
        require(len({s.source_id for s in self.samples}) == len(self.samples), "Duplicate source sample")
        for flag in (self.online, self.relay_on):
            require(flag is None or type(flag) is bool, "Invalid meter state flag")
        require(self.protection in ("unknown", "normal", "tripped")
                and isinstance(self.quality, Quality), "Invalid meter metadata")


@dataclass(frozen=True, slots=True)
class MeterEvidence:
    power: PowerPoint
    counter: CounterPoint | None
    counter_reason: str
    physical_authority: Literal[False] = field(default=False, init=False)
    physical_heat: None = field(default=None, init=False)


def _frame_reason(binding: MeterBinding, frame: MeterFrame, now: float,
                  excluded: tuple[str, ...]) -> str:
    if not binding.channels:
        return "meter_unbound"
    footprint = {binding.meter_id, *binding.coverage,
                 *(part for s in frame.samples for part in s.components)}
    if footprint.intersection(excluded):
        return "meter_accounting_overlap"
    if binding.verification is None or not binding.verification.qualified:
        return "meter_unverified"
    if frame.online is not True:
        return "meter_offline_or_unknown"
    if (not 0 <= now - frame.at <= binding.max_age_s
            or not frame.at <= frame.received_at <= now
            or frame.quality.status is not QualityStatus.VALID
            or frame.quality.age_s > binding.max_age_s):
        return "meter_metadata_stale_or_invalid"
    if any(s.received_at > frame.received_at for s in frame.samples):
        return "meter_sample_after_frame"
    if any(s.source_id not in {c.source_id for c in binding.channels} for s in frame.samples):
        return "unbound_meter_source"
    return ""


def _lineage(binding: MeterBinding, samples: tuple[MeterSample, ...]) -> tuple[str, ...]:
    return tuple(sorted({binding.meter_id, *binding.coverage,
                         *(binding.verification.evidence_ids if binding.verification else ()),
                         *(v for s in samples for v in (s.source_id, s.origin_id, *s.components))}))


def _sample_reason(binding: MeterBinding, channel: MeterChannel, sample: MeterSample | None,
                   now: float, previous: MeterFrame | None) -> str:
    if sample is None or sample.value is None:
        return "meter_sample_missing"
    if sample.unit != channel.unit or sample.origin is not SourceKind.DIRECT:
        return "meter_unit_or_origin_unqualified"
    if (sample.quality.status is not QualityStatus.VALID
            or sample.quality.age_s > binding.max_age_s
            or not 0 <= now - sample.observed_at <= binding.max_age_s
            or not sample.observed_at <= sample.received_at <= now):
        return "meter_sample_stale_or_invalid"
    old = next((s for s in previous.samples if s.source_id == sample.source_id), None) if previous else None
    if old is not None:
        if sample.origin_id != old.origin_id:
            return "meter_origin_changed"
        if sample.sequence < old.sequence or sample.observed_at < old.observed_at:
            return "meter_sample_reordered"
        if ((sample.sequence == old.sequence and sample != old)
                or (sample.observed_at == old.observed_at and sample.value != old.value)):
            return "meter_sample_conflicting_duplicate"
    return ""


def project_meter(binding: MeterBinding, frame: MeterFrame, *, now: float,
                  previous: MeterFrame | None = None, stage_kw: float | None = None,
                  excluded_coverage: tuple[str, ...] = ()) -> MeterEvidence:
    """Select one synthetic meter source or an explicit lower-confidence stage assumption.

    The accepted evidence integrator alone may integrate these timestamped points;
    this function never backfills energy or rounds active watts to a nominal stage.
    """
    number(now, nonnegative=True)
    _synthetic_ids(excluded_coverage)
    require(isinstance(binding, MeterBinding) and isinstance(frame, MeterFrame)
            and (previous is None or isinstance(previous, MeterFrame)), "Invalid meter projection")
    if stage_kw is not None:
        number(stage_kw)
        require(stage_kw in (3, 6, 9), "Invalid unverified stage assumption")
    reason = _frame_reason(binding, frame, now, excluded_coverage)
    samples = {s.source_id: s for s in frame.samples}

    def selected(channel: MeterChannel) -> tuple[MeterSample | None, str]:
        sample = samples.get(channel.source_id)
        issue = reason or _sample_reason(binding, channel, sample, now, previous)
        return (None if issue else sample), issue

    active = [c for c in binding.channels if c.quantity == "active_power"]
    used: list[MeterSample] = []
    watts: float | None = None
    method = "synthetic_active_power"
    power_reason = reason or "active_power_unsupported"
    if active and not reason:
        power_reason = ""
        for channel in active:
            s, issue = selected(channel)
            if s is None:
                power_reason = issue
                break
            used.append(s)
        if not power_reason:
            total = next((s for c, s in zip(active, used) if c.phase == "total"), None)
            phases = [s for c, s in zip(active, used) if c.phase != "total"]
            if max(s.observed_at for s in used) - min(s.observed_at for s in used) > binding.max_skew_s:
                power_reason = "meter_phase_skew"
            elif (total is not None and phases and total.value is not None
                  and abs(total.value - sum(s.value for s in phases if s.value is not None))
                  > binding.phase_tolerance_w):
                power_reason = "meter_phase_contradiction"
            else:
                watts = total.value if total else sum(s.value for s in phases if s.value is not None)
                method = "synthetic_active_power" if total else "synthetic_phase_sum"
                if watts is not None and watts > binding.max_kw * 1000:
                    watts = None
                    power_reason = "meter_power_out_of_bounds"
    lineage = _lineage(binding, tuple(used))
    if len(lineage) > 64:
        watts = None
        power_reason = "meter_lineage_capacity"
    if reason == "meter_accounting_overlap":
        stage_kw = None
    category: Literal["confirmed", "estimated", "unknown"]
    kw: float | None
    if watts is not None:
        at, received = min(s.observed_at for s in used), max(s.received_at for s in used)
        kw, category, sources = watts / 1000, "confirmed", lineage
    else:
        at = received = now
        kw, category = stage_kw, "estimated" if stage_kw is not None else "unknown"
        sources = ("synthetic.stage_assumption",) if stage_kw is not None else ()
        method = ("stage_estimate_after_" if stage_kw is not None else "") + power_reason
    power = PowerPoint(_identity((binding.meter_id, at, received, kw, category, sources, method)),
                       binding.meter_id, at, received, kw, category, sources, method, watts)
    counter_channel = next((c for c in binding.channels
                            if c.quantity == "imported_energy" and c.phase == "total"), None)
    counter_point = None
    counter_reason = reason or "imported_energy_unsupported"
    if power_reason == "meter_phase_contradiction":
        counter_reason = power_reason
    elif counter_channel is not None:
        s, counter_reason = selected(counter_channel)
        if s is not None and s.value is not None:
            if len(_lineage(binding, (s,))) > 64:
                counter_reason = "meter_lineage_capacity"
            else:
                counter_point = CounterPoint(_identity((binding.meter_id, s)), binding.meter_id,
                                             s.observed_at, s.value, s.source_id)
                counter_reason = "synthetic_imported_energy"
    return MeterEvidence(power, counter_point, counter_reason)


def counter_energy(binding: MeterBinding, left: MeterFrame, right: MeterFrame, *,
                   now: float, continuity: str,
                   excluded_coverage: tuple[str, ...] = ()) -> EnergySlice:
    """Qualify actual counter endpoints, then reuse accepted reset/jump math.

    Reset/jump/origin changes stay unknown. No automatic gap recovery or ledger
    mutation occurs; callers retain the accepted single-contribution ledger.
    """
    _synthetic(continuity)
    require(left.at < right.at, "Counter frame order mismatch")
    a = project_meter(binding, left, now=left.received_at, excluded_coverage=excluded_coverage)
    b = project_meter(binding, right, now=now, previous=left, excluded_coverage=excluded_coverage)
    if a.counter is not None and b.counter is not None and a.counter.at < b.counter.at:
        lineage = _lineage(binding, tuple(s for f in (left, right) for s in f.samples
                                         if s.source_id == a.counter.source))
        if len(lineage) <= 64:
            return replace(counter_delta(a.counter, b.counter, binding.max_kw, continuity), sources=lineage)
        reason = "meter_lineage_capacity"
    else:
        reason = a.counter_reason if a.counter is None else b.counter_reason
    return EnergySlice(_identity((binding.meter_id, left.at, right.at, reason, continuity)),
                       binding.meter_id, continuity, left.at, right.at,
                       "unknown", None, (), "counter_unqualified:" + reason)
