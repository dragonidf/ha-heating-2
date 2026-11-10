"""Synthetic Tuya Local KWS consumption and empirical stage evidence only.

The cloud alias is never a fallback. One total counter contributes energy; phase
counters only cross-check deltas. Fixture signatures are not hardware ratings.
"""
from dataclasses import dataclass, field, replace
from typing import Literal, cast

from packages.contracts import Clock, Quality, QualityStatus, SourceKind
from packages.contracts.models import counter, number, require
from packages.ha_native.meter import (
    MeterBinding, MeterChannel, MeterFrame, MeterSample, SyntheticMeterVerification,
    _identity, _synthetic, counter_energy, project_meter,
)
from packages.ha_native.store import JSON
from packages.ha_native.voltage import PHASES, _object
from packages.offline.contracts import CounterPoint, EnergySlice, PowerPoint

Stage = Literal["OFF", "PUMP_ONLY", "~3kW", "~6kW", "~9kW", "UNKNOWN"]
KWSPhaseName = Literal["total", "L1", "L2", "L3"]
KWSType = Literal["active_power", "imported_energy"]
_STAGES = ("OFF", "PUMP_ONLY", "~3kW", "~6kW", "~9kW")


@dataclass(frozen=True, slots=True)
class StageSignature:
    stage: Stage
    phase_w: tuple[float, float, float]
    tolerance_w: tuple[float, float, float]

    def __post_init__(self) -> None:
        require(self.stage in _STAGES, "Invalid calibrated stage")
        for values in (self.phase_w, self.tolerance_w):
            require(type(values) is tuple and len(values) == 3, "Invalid phase signature")
            for value in values:
                number(value, nonnegative=True)

    def matches(self, watts: tuple[float, ...], extra: float = 0) -> bool:
        return all(abs(v - expected) <= tolerance + extra
                   for v, expected, tolerance in zip(watts, self.phase_w, self.tolerance_w))


@dataclass(frozen=True, slots=True)
class StageCalibration:
    signatures: tuple[StageSignature, ...] = ()
    minimum_dwell_s: float = 10
    hysteresis_w: float = 25
    max_age_s: float = 30
    max_skew_s: float = 5
    evidence_id: str = "synthetic.unverified"
    verified: bool = False
    counter_tolerance_kwh: float = 0.01

    def __post_init__(self) -> None:
        require(type(self.signatures) is tuple and len(self.signatures) <= 5
                and all(isinstance(s, StageSignature) for s in self.signatures)
                and len({s.stage for s in self.signatures}) == len(self.signatures),
                "Invalid empirical stage calibration")
        _synthetic(self.evidence_id)
        require(type(self.verified) is bool, "Invalid stage verification")
        for value in (self.minimum_dwell_s, self.hysteresis_w, self.max_age_s,
                      self.max_skew_s, self.counter_tolerance_kwh):
            number(value, nonnegative=True)
        require(self.minimum_dwell_s <= 600 and self.hysteresis_w <= 1000
                and 1 <= self.max_age_s <= 45 and self.max_skew_s <= 30
                and self.counter_tolerance_kwh <= 1, "Invalid empirical stage limits")


def synthetic_kws_calibration() -> StageCalibration:
    """Explicit fictional asymmetric test calibration; not a household profile."""
    return StageCalibration((
        StageSignature("OFF", (0, 0, 0), (5, 5, 5)),
        StageSignature("PUMP_ONLY", (40, 20, 10), (10, 10, 10)),
        StageSignature("~3kW", (200, 1000, 1750), (120, 120, 120)),
        StageSignature("~6kW", (1100, 1800, 3200), (120, 120, 120)),
        StageSignature("~9kW", (2100, 2800, 4050), (120, 120, 120)),
    ), evidence_id="synthetic.asymmetric.fixture", verified=True)


@dataclass(frozen=True, slots=True)
class KWSReading:
    source_id: str
    physical_id: str
    phase: KWSPhaseName
    quantity: KWSType
    value: float | None
    unit: Literal["kW", "kWh"]
    last_reported: float
    received_at: float
    sequence: int
    online: bool | None = None
    heartbeat_verified: bool = False
    quality: QualityStatus = QualityStatus.VALID
    origin: SourceKind = SourceKind.DIRECT
    provider: str = "tuya_local"

    def __post_init__(self) -> None:
        _synthetic(self.source_id)
        _synthetic(self.physical_id)
        require(self.phase in ("total", *PHASES) and self.quantity in ("active_power", "imported_energy"),
                "Invalid KWS channel role")
        require((self.quantity == "active_power" and self.unit == "kW" and self.phase != "total")
                or (self.quantity == "imported_energy" and self.unit == "kWh"), "Invalid KWS channel unit")
        for value in (self.last_reported, self.received_at):
            number(value, nonnegative=True)
        if self.value is not None:
            number(self.value, nonnegative=True)
        counter(self.sequence)
        require(self.online is None or type(self.online) is bool, "Invalid KWS availability")
        require(type(self.heartbeat_verified) is bool and isinstance(self.quality, QualityStatus)
                and isinstance(self.origin, SourceKind)
                and self.provider in ("tuya_local", "tuya_cloud"), "Invalid KWS provenance")


@dataclass(frozen=True, slots=True)
class KWSFrame:
    readings: tuple[KWSReading, ...] = ()
    provider: str = "tuya_local"
    meter_id: str = "synthetic.kws"
    verification: SyntheticMeterVerification | None = None
    calibration: StageCalibration | None = None
    online: bool | None = None

    def __post_init__(self) -> None:
        _synthetic(self.meter_id)
        require(type(self.readings) is tuple and len(self.readings) <= 7
                and all(isinstance(r, KWSReading) for r in self.readings), "Invalid KWS readings")
        require(len({(r.quantity, r.phase) for r in self.readings}) == len(self.readings)
                and len({r.source_id for r in self.readings}) == len(self.readings), "Duplicate KWS channel")
        require(self.provider in ("tuya_local", "tuya_cloud")
                and (self.online is None or type(self.online) is bool), "Invalid KWS frame provider")
        require(self.verification is None or isinstance(self.verification, SyntheticMeterVerification),
                "Invalid KWS verification")
        require(self.calibration is None or isinstance(self.calibration, StageCalibration),
                "Invalid KWS calibration")


@dataclass(frozen=True, slots=True)
class KWSState:
    power: PowerPoint
    counter: CounterPoint | None
    stage: Stage
    reason: str
    candidate_stage: Stage
    candidate_since_mono: float | None
    checked_mono: float
    checked_at: float
    boot_id: str
    frame: KWSFrame
    ages: tuple[tuple[str, float], ...]
    phase_w: tuple[float | None, ...]
    normalized: MeterFrame
    binding: MeterBinding


def project_kws(frame: KWSFrame, clock: Clock, prior: KWSState | None = None) -> KWSState:
    """Keep calibrated stage evidence independent of watts and single total kWh."""
    require(isinstance(frame, KWSFrame) and isinstance(clock, Clock)
            and (prior is None or isinstance(prior, KWSState)), "Invalid KWS projection")
    policy = frame.calibration or StageCalibration()
    same_boot = prior is not None and prior.boot_id == clock.boot_id
    elapsed = clock.monotonic - prior.checked_mono if same_boot and prior is not None else 0
    rollback = bool(same_boot and prior is not None and (elapsed < 0 or clock.utc < prior.checked_at))
    old_readings = {r.source_id: r for r in prior.frame.readings} if same_boot and prior is not None else {}
    old_ages = dict(prior.ages) if same_boot and prior is not None else {}
    ages: list[tuple[str, float]] = []
    samples = []
    channels = []
    valid_values: dict[str, float | None] = {}
    for r in frame.readings:
        age = clock.utc - r.last_reported
        old = old_readings.get(r.source_id)
        if old is not None and r.last_reported == old.last_reported:
            age = max(age, old_ages[r.source_id] + max(0, elapsed))
        ages.append((r.source_id, age))
        valid = (not rollback and r.value is not None and r.online is True and r.heartbeat_verified
                 and r.quality is QualityStatus.VALID and r.origin is SourceKind.DIRECT
                 and r.provider == "tuya_local" and r.physical_id == frame.meter_id
                 and 0 <= age <= policy.max_age_s and r.last_reported <= r.received_at <= clock.utc)
        if old is not None:
            valid = (valid and r.sequence >= old.sequence and r.last_reported >= old.last_reported
                     and (r.sequence != old.sequence or r == old)
                     and (r.last_reported != old.last_reported or r.value == old.value))
        value = None if r.value is None else r.value * (1000 if r.quantity == "active_power" else 1)
        valid_values[r.source_id] = value if valid else None
        unit: Literal["W", "kWh"] = "W" if r.quantity == "active_power" else "kWh"
        channels.append(MeterChannel(r.source_id, r.source_id, r.quantity, unit, r.phase))
        samples.append(MeterSample(r.source_id, value, unit, r.last_reported, r.received_at, r.sequence,
                                   Quality(status=QualityStatus.VALID if valid else QualityStatus.MISSING,
                                           age_s=max(0, age), reason="synthetic.kws.report"),
                                   r.origin, "synthetic.tuya_local.kws"))
    active = {r.phase: r for r in frame.readings if r.quantity == "active_power"}
    role_reason = ("cloud_duplicate_excluded" if frame.provider != "tuya_local"
                   or any(r.provider != "tuya_local" for r in frame.readings)
                   else "physical_identity_mismatch" if any(r.physical_id != frame.meter_id for r in frame.readings)
                   else "phase_power_incomplete" if set(active) != set(PHASES)
                   else "clock_rollback" if rollback else "")
    binding = MeterBinding(frame.meter_id, tuple(channels) if not role_reason else (),
                           (frame.meter_id,), frame.verification,
                           max_age_s=policy.max_age_s, max_skew_s=policy.max_skew_s)
    at = min((r.last_reported for r in active.values()), default=clock.utc)
    received = max((r.received_at for r in frame.readings), default=clock.utc)
    normalized = MeterFrame(at, received, tuple(samples) if not role_reason else (), online=frame.online)
    evidence = project_meter(binding, normalized, now=clock.utc)
    watts = tuple(valid_values[active[p].source_id] if p in active and not role_reason else None for p in PHASES)
    stage: Stage = "UNKNOWN"
    candidate: Stage = "UNKNOWN"
    since = None
    reason = role_reason or evidence.power.method
    if evidence.power.kw is not None and all(v is not None for v in watts):
        if not policy.verified or not policy.signatures:
            reason = "stage_calibration_unverified"
        else:
            numeric = tuple(v for v in watts if v is not None)
            matches = [s for s in policy.signatures if s.matches(numeric)]
            continuity = (same_boot and prior is not None and prior.frame.provider == "tuya_local"
                          and prior.power.kw is not None and prior.frame.calibration == frame.calibration
                          and all(0 <= age + elapsed <= policy.max_age_s for _, age in prior.ages))
            held = next((s for s in policy.signatures if continuity and prior is not None
                         and s.stage == prior.stage and s.matches(numeric, policy.hysteresis_w)), None)
            if len(matches) == 1:
                candidate = matches[0].stage
            elif not matches and held is not None:
                candidate = held.stage
            if candidate == "UNKNOWN":
                reason = "stage_ambiguous_or_signature_mismatch"
            else:
                since = (prior.candidate_since_mono if continuity and prior is not None
                         and prior.candidate_stage == candidate and prior.candidate_since_mono is not None
                         else clock.monotonic)
                if clock.monotonic - since >= policy.minimum_dwell_s:
                    stage, reason = candidate, "sustained_empirical_signature"
                else:
                    reason = "stage_transition_dwell"
    return KWSState(evidence.power, evidence.counter, stage, reason, candidate, since,
                    clock.monotonic, clock.utc, clock.boot_id, frame, tuple(ages), watts, normalized, binding)


def kws_view(state: KWSState) -> dict[str, JSON]:
    active = {r.phase: r for r in state.frame.readings if r.quantity == "active_power"}
    ages = dict(state.ages)
    return {
        "source_role": "boiler_power_energy", "source_provider": "tuya_local_kws",
        "cloud_duplicate_policy": "excluded_no_fallback", "stage": state.stage,
        "total_active_w": state.power.raw_w if state.power.kw is not None else None,
        "total_imported_kwh": state.counter.kwh if state.counter is not None else None,
        "phases": [{"phase": phase, "active_w": state.phase_w[i],
                    "age_s": ages.get(active[phase].source_id) if phase in active else None}
                   for i, phase in enumerate(PHASES)],
        "reason": state.reason, "physical_authority": False,
        "physical_heat": None, "scope": "synthetic_only",
    }


def kws_counter_energy(left: KWSFrame, right: KWSFrame, clock: Clock, continuity: str) -> EnergySlice:
    """One total-counter contribution, never total+phase/cloud copies or guessed gaps."""
    _synthetic(continuity)
    at = max((r.received_at for r in left.readings), default=clock.utc)
    elapsed = clock.utc - at
    require(0 <= elapsed <= clock.monotonic, "KWS counter pair crosses monotonic epoch")
    a = project_kws(left, Clock(utc=at, monotonic=clock.monotonic - elapsed, boot_id=clock.boot_id))
    b = project_kws(right, clock, a)
    start, end = a.normalized.at, b.normalized.at
    require(start < end, "KWS counter frame order mismatch")
    reason = "counter_unqualified"
    if a.counter is not None and b.counter is not None:
        delta = b.counter.kwh - a.counter.kwh
        policy = right.calibration or StageCalibration()
        if delta == 0 and b.counter.at - a.counter.at > policy.max_age_s:
            reason = "counter_unchanged_without_continuous_heartbeat"
        else:
            result = counter_energy(b.binding, a.normalized, b.normalized,
                                    now=clock.utc, continuity=continuity)
            phase_left = {r.phase: r for r in left.readings if r.quantity == "imported_energy" and r.phase != "total"}
            phase_right = {r.phase: r for r in right.readings if r.quantity == "imported_energy" and r.phase != "total"}
            if not phase_left and not phase_right:
                return result
            if set(phase_left) != set(PHASES) or set(phase_right) != set(PHASES):
                reason = "phase_counter_incomplete"
            else:
                deltas = []
                for phase in PHASES:
                    x, y = phase_left[phase], phase_right[phase]
                    if (valid := dict(a.ages).get(x.source_id)) is None or valid > policy.max_age_s:
                        break
                    if (x.value is None or y.value is None or x.source_id != y.source_id
                            or y.sequence <= x.sequence or y.last_reported <= x.last_reported
                            or not x.heartbeat_verified or not y.heartbeat_verified
                            or x.quality is not QualityStatus.VALID or y.quality is not QualityStatus.VALID
                            or x.online is not True or y.online is not True
                            or not 0 <= clock.utc - y.last_reported <= policy.max_age_s
                            or not x.last_reported <= x.received_at <= at
                            or not y.last_reported <= y.received_at <= clock.utc
                            or y.value < x.value):
                        break
                    deltas.append(y.value - x.value)
                if len(deltas) == 3 and abs(sum(deltas) - delta) <= policy.counter_tolerance_kwh:
                    return result
                reason = "phase_counter_contradiction"
    return EnergySlice(_identity((left, right, continuity, reason)), right.meter_id, continuity,
                       start, end, "unknown", None, (), reason)


def decode_kws_frame(raw: object) -> KWSFrame:
    """Closed synthetic JSON roles; no inferred real device mapping or calibration."""
    value = _object(raw, {"readings", "provider", "meter_id", "verification", "calibration", "online"}, {"readings"})
    rows = value["readings"]
    require(type(rows) is list and len(cast(list[object], rows)) <= 7, "Invalid KWS source list")
    readings = []
    for row in cast(list[object], rows):
        r = _object(row, {"source_id", "physical_id", "phase", "quantity", "value", "unit", "last_reported",
                          "received_at", "sequence", "online", "heartbeat_verified", "quality", "origin", "provider"},
                         {"source_id", "physical_id", "phase", "quantity", "value", "unit", "last_reported", "received_at", "sequence"})
        readings.append(KWSReading(cast(str, r["source_id"]), cast(str, r["physical_id"]),
            cast(KWSPhaseName, r["phase"]), cast(KWSType, r["quantity"]), cast(float | None, r["value"]),
            cast(Literal["kW", "kWh"], r["unit"]), cast(float, r["last_reported"]), cast(float, r["received_at"]),
            cast(int, r["sequence"]), cast(bool | None, r.get("online")), cast(bool, r.get("heartbeat_verified", False)),
            QualityStatus(cast(str, r.get("quality", "valid"))), SourceKind(cast(str, r.get("origin", "direct"))),
            cast(str, r.get("provider", "tuya_local"))))
    verification = None
    if value.get("verification") is not None:
        proof = _object(value["verification"], {"evidence_ids", "boiler_only", "auxiliaries_included",
                        "phase_mapping", "import_direction", "counter_accuracy"}, {"evidence_ids"})
        require(type(proof["evidence_ids"]) is list, "Invalid KWS proof identifiers")
        verification = SyntheticMeterVerification(tuple(cast(list[str], proof["evidence_ids"])),
            cast(bool, proof.get("boiler_only", False)), cast(bool, proof.get("auxiliaries_included", False)),
            cast(bool, proof.get("phase_mapping", False)), cast(bool, proof.get("import_direction", False)),
            cast(bool, proof.get("counter_accuracy", False)))
    calibration = None
    if value.get("calibration") is not None:
        c = _object(value["calibration"], {"signatures", "minimum_dwell_s", "hysteresis_w", "max_age_s",
                    "max_skew_s", "evidence_id", "verified", "counter_tolerance_kwh"}, {"signatures"})
        require(type(c["signatures"]) is list and len(cast(list[object], c["signatures"])) <= 5,
                "Invalid stage signature list")
        signatures = []
        for row in cast(list[object], c["signatures"]):
            s = _object(row, {"stage", "phase_w", "tolerance_w"}, {"stage", "phase_w", "tolerance_w"})
            require(type(s["phase_w"]) is list and type(s["tolerance_w"]) is list, "Invalid stage phase list")
            signatures.append(StageSignature(cast(Stage, s["stage"]),
                cast(tuple[float, float, float], tuple(cast(list[float], s["phase_w"]))),
                cast(tuple[float, float, float], tuple(cast(list[float], s["tolerance_w"])))))
        calibration = StageCalibration(tuple(signatures), cast(float, c.get("minimum_dwell_s", 10)),
            cast(float, c.get("hysteresis_w", 25)), cast(float, c.get("max_age_s", 30)),
            cast(float, c.get("max_skew_s", 5)), cast(str, c.get("evidence_id", "synthetic.unverified")),
            cast(bool, c.get("verified", False)), cast(float, c.get("counter_tolerance_kwh", 0.01)))
    return KWSFrame(tuple(readings), cast(str, value.get("provider", "tuya_local")),
                    cast(str, value.get("meter_id", "synthetic.kws")), verification, calibration,
                    cast(bool | None, value.get("online")))
