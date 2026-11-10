"""Pure synthetic INPUT-220 voltage eligibility, never electrical protection.

Outer limits are inclusive while NORMAL. Startup, faults and configuration/boot
changes require the inclusive inward band continuously for monotonic recovery
dwell. Eligibility cannot issue HEAT, resume manual control, or operate a pump.
"""
from dataclasses import dataclass
from typing import Literal, cast

from packages.contracts import Clock, QualityStatus, SourceKind
from packages.contracts.models import counter, number, require
from packages.ha_native.meter import _synthetic
from packages.ha_native.store import JSON

VoltageStatus = Literal["LOW", "HIGH", "MISSING_OR_STALE", "STABILIZING", "NORMAL"]
VoltagePhaseName = Literal["L1", "L2", "L3"]
PHASES: tuple[VoltagePhaseName, ...] = ("L1", "L2", "L3")
INPUT_PROVIDER = "synthetic.zigbee2mqtt.input220"


@dataclass(frozen=True, slots=True)
class VoltagePolicy:
    # Fixture defaults only; no household thresholds or hardware ratings implied.
    min_voltage_v: float = 190
    max_voltage_v: float = 250
    hysteresis_v: float = 5
    stable_recovery_s: float = 30
    voltage_max_age_s: float = 30
    max_skew_s: float = 5

    def __post_init__(self) -> None:
        for value in (self.min_voltage_v, self.max_voltage_v, self.hysteresis_v,
                      self.stable_recovery_s, self.voltage_max_age_s, self.max_skew_s):
            number(value)
        require(80 <= self.min_voltage_v <= 280 and 120 <= self.max_voltage_v <= 300
                and self.min_voltage_v < self.max_voltage_v, "Invalid synthetic voltage limits")
        require(0 <= self.hysteresis_v <= 30
                and 2 * self.hysteresis_v < self.max_voltage_v - self.min_voltage_v,
                "Invalid voltage recovery band")
        require(0 <= self.stable_recovery_s <= 600 and 1 <= self.voltage_max_age_s <= 300
                and 0 <= self.max_skew_s <= 30, "Invalid voltage timing limits")


@dataclass(frozen=True, slots=True)
class VoltagePhase:
    phase: VoltagePhaseName
    source_id: str
    value_v: float | None
    last_reported: float
    received_at: float
    sequence: int
    quality: QualityStatus = QualityStatus.VALID
    provider: str = INPUT_PROVIDER
    phase_verified: bool = False
    online: bool | None = None
    origin: SourceKind = SourceKind.DIRECT
    unit: Literal["V"] = "V"

    def __post_init__(self) -> None:
        require(self.phase in PHASES and self.unit == "V", "Invalid voltage phase/unit")
        _synthetic(self.source_id)
        _synthetic(self.provider)
        for value in (self.last_reported, self.received_at):
            number(value, nonnegative=True)
        if self.value_v is not None:
            number(self.value_v, nonnegative=True)
        counter(self.sequence)
        require(isinstance(self.quality, QualityStatus) and isinstance(self.origin, SourceKind),
                "Invalid voltage provenance/quality")
        require(type(self.phase_verified) is bool
                and (self.online is None or type(self.online) is bool), "Invalid voltage source flags")


@dataclass(frozen=True, slots=True)
class VoltageFrame:
    phases: tuple[VoltagePhase, ...] = ()
    mapping_verified: bool = False
    grid_available: bool | None = None
    protection_trip: bool | None = None
    protection_last_reported: float | None = None
    protection_qualified: bool = False

    def __post_init__(self) -> None:
        require(type(self.phases) is tuple and len(self.phases) <= 3
                and all(isinstance(p, VoltagePhase) for p in self.phases), "Invalid voltage frame")
        require(len({p.phase for p in self.phases}) == len(self.phases)
                and len({p.source_id for p in self.phases}) == len(self.phases),
                "Ambiguous voltage phase/source mapping")
        for flag in (self.mapping_verified, self.protection_qualified):
            require(type(flag) is bool, "Invalid voltage verification flag")
        for availability in (self.grid_available, self.protection_trip):
            require(availability is None or type(availability) is bool, "Invalid voltage availability/protection")
        if self.protection_last_reported is not None:
            number(self.protection_last_reported, nonnegative=True)


@dataclass(frozen=True, slots=True)
class VoltageState:
    status: VoltageStatus
    eligible: bool
    affected_phases: tuple[VoltagePhaseName, ...]
    ages: tuple[tuple[VoltagePhaseName, float | None], ...]
    reason: str
    recovery_since_mono: float | None
    boot_id: str
    checked_at: float
    checked_mono: float
    policy: VoltagePolicy
    frame: VoltageFrame
    protection_age_s: float | None
    qualified_phases: tuple[VoltagePhaseName, ...]


def evaluate_voltage(policy: VoltagePolicy, frame: VoltageFrame, clock: Clock,
                     prior: VoltageState | None = None) -> VoltageState:
    """Re-evaluate cached reports with advancing UTC AND monotonic elapsed time."""
    require(isinstance(policy, VoltagePolicy) and isinstance(frame, VoltageFrame)
            and isinstance(clock, Clock) and (prior is None or isinstance(prior, VoltageState)),
            "Invalid voltage evaluation")
    same_boot = prior is not None and prior.boot_id == clock.boot_id
    elapsed = clock.monotonic - prior.checked_mono if same_boot and prior is not None else 0
    rollback = bool(same_boot and prior is not None
                    and (elapsed < 0 or clock.utc < prior.checked_at))
    previous = {p.phase: p for p in prior.frame.phases} if same_boot and prior is not None else {}
    previous_ages = dict(prior.ages) if same_boot and prior is not None else {}
    current = {p.phase: p for p in frame.phases}
    ages: list[tuple[VoltagePhaseName, float | None]] = []
    missing: list[VoltagePhaseName] = []
    qualified: list[VoltagePhaseName] = []
    low: list[VoltagePhaseName] = []
    high: list[VoltagePhaseName] = []
    reasons: list[str] = []
    for name in PHASES:
        p, old = current.get(name), previous.get(name)
        age = None if p is None else clock.utc - p.last_reported
        old_age = previous_ages.get(name)
        if (p is not None and old is not None and old_age is not None
                and p.source_id == old.source_id and p.last_reported == old.last_reported):
            age = max(cast(float, age), old_age + max(0, elapsed))
        ages.append((name, age))
        valid = (p is not None and p.value_v is not None and p.provider == INPUT_PROVIDER
                 and p.origin is SourceKind.DIRECT and p.quality is QualityStatus.VALID
                 and p.phase_verified and p.online is True and age is not None
                 and 0 <= age <= policy.voltage_max_age_s
                 and p.last_reported <= p.received_at <= clock.utc)
        if valid and p is not None and old is not None:
            valid = (p.source_id == old.source_id and p.provider == old.provider
                     and p.sequence >= old.sequence and p.last_reported >= old.last_reported
                     and (p.sequence != old.sequence or p == old)
                     and (p.last_reported != old.last_reported or p.value_v == old.value_v))
        if not valid or rollback:
            missing.append(name)
        elif p is not None and p.value_v is not None:
            qualified.append(name)
            if p.value_v < policy.min_voltage_v:
                low.append(name)
            if p.value_v > policy.max_voltage_v:
                high.append(name)
    protection_age = (None if frame.protection_last_reported is None
                      else clock.utc - frame.protection_last_reported)
    if (same_boot and prior is not None and protection_age is not None
            and frame.protection_last_reported == prior.frame.protection_last_reported
            and prior.protection_age_s is not None):
        protection_age = max(protection_age, prior.protection_age_s + max(0, elapsed))
    if rollback:
        reasons.append("clock_rollback")
    if not frame.mapping_verified:
        reasons.append("phase_mapping_unverified")
    if frame.grid_available is not True:
        reasons.append("grid_input_unavailable")
    if (not frame.protection_qualified or frame.protection_trip is None
            or protection_age is None or not 0 <= protection_age <= policy.voltage_max_age_s):
        reasons.append("protection_unknown_or_stale")
    elif frame.protection_trip:
        reasons.append("protection_trip")
    if missing:
        reasons.append("phase_missing_stale_or_unqualified")
    if len(current) == 3 and max(p.last_reported for p in frame.phases) - min(
            p.last_reported for p in frame.phases) > policy.max_skew_s:
        reasons.append("phase_skew")
    status: VoltageStatus
    eligible = False
    since = None
    affected = tuple(p for p in PHASES if p in (*missing, *low, *high))
    if reasons:
        status, reason = "MISSING_OR_STALE", ";".join(reasons)
        affected = affected or PHASES
    elif low or high:
        status = "LOW" if low else "HIGH"
        reason = "low_and_high_phases" if low and high else "phase_below_min" if low else "phase_above_max"
    else:
        continuity = (same_boot and prior is not None and prior.policy == policy
                      and all(v is not None and 0 <= v + elapsed <= policy.voltage_max_age_s
                              for _, v in prior.ages)
                      and prior.protection_age_s is not None
                      and 0 <= prior.protection_age_s + elapsed <= policy.voltage_max_age_s)
        if continuity and prior is not None and prior.eligible:
            eligible, status, reason = True, "NORMAL", "within_inclusive_limits"
        else:
            inward = all(p.value_v is not None and policy.min_voltage_v + policy.hysteresis_v
                         <= p.value_v <= policy.max_voltage_v - policy.hysteresis_v
                         for p in frame.phases)
            if inward:
                since = (prior.recovery_since_mono if continuity and prior is not None
                         and prior.recovery_since_mono is not None else clock.monotonic)
                eligible = clock.monotonic - since >= policy.stable_recovery_s
            status = "NORMAL" if eligible else "STABILIZING"
            reason = "stable_recovery_complete" if eligible else "recovery_dwell" if inward else "outside_recovery_band"
    return VoltageState(status, eligible, affected, tuple(ages), reason, since, clock.boot_id,
                        clock.utc, clock.monotonic, policy, frame, protection_age, tuple(qualified))


def voltage_view(state: VoltageState, policy: VoltagePolicy) -> dict[str, JSON]:
    """Sanitized three-phase projection; no private source mapping or command."""
    ages = dict(state.ages)
    phases = {p.phase: p for p in state.frame.phases}
    return {
        "status": state.status, "eligible": state.eligible,
        "affected_phases": list(state.affected_phases), "reason": state.reason,
        "ages": {name: ages[name] for name in PHASES},
        "phases": [{"phase": name, "voltage_v": phases[name].value_v if name in phases else None,
                    "age_s": ages[name], "online": phases[name].online if name in phases else None,
                    "qualified": name in state.qualified_phases} for name in PHASES],
        "limits": {"min_voltage_v": policy.min_voltage_v, "max_voltage_v": policy.max_voltage_v,
                   "hysteresis_v": policy.hysteresis_v, "stable_recovery_s": policy.stable_recovery_s,
                   "voltage_max_age_s": policy.voltage_max_age_s},
        "source_role": "grid_input_voltage", "source_provider": "zigbee2mqtt_input220",
        "physical_authority": False, "scope": "synthetic_only",
    }


def _object(value: object, allowed: set[str], required: set[str]) -> dict[str, object]:
    require(type(value) is dict, "Expected synthetic source object")
    result = cast(dict[str, object], value)
    require(set(result) <= allowed and required <= set(result), "Invalid synthetic source fields")
    return result


def decode_voltage_frame(raw: object) -> VoltageFrame:
    """Strict fixture JSON boundary; incoming report fields never imply real authority."""
    value = _object(raw, {"phases", "mapping_verified", "grid_available", "protection_trip",
                         "protection_last_reported", "protection_qualified"}, {"phases"})
    rows = value["phases"]
    require(type(rows) is list and len(cast(list[object], rows)) <= 3, "Invalid voltage source list")
    phases = []
    for row in cast(list[object], rows):
        p = _object(row, {"phase", "source_id", "value_v", "last_reported", "received_at", "sequence",
                          "quality", "provider", "phase_verified", "online", "origin", "unit"},
                         {"phase", "source_id", "value_v", "last_reported", "received_at", "sequence"})
        phases.append(VoltagePhase(
            cast(VoltagePhaseName, p["phase"]), cast(str, p["source_id"]), cast(float | None, p["value_v"]),
            cast(float, p["last_reported"]), cast(float, p["received_at"]), cast(int, p["sequence"]),
            QualityStatus(cast(str, p.get("quality", "valid"))), cast(str, p.get("provider", INPUT_PROVIDER)),
            cast(bool, p.get("phase_verified", False)), cast(bool | None, p.get("online")),
            SourceKind(cast(str, p.get("origin", "direct"))), cast(Literal["V"], p.get("unit", "V"))))
    return VoltageFrame(tuple(phases), cast(bool, value.get("mapping_verified", False)),
                        cast(bool | None, value.get("grid_available")), cast(bool | None, value.get("protection_trip")),
                        cast(float | None, value.get("protection_last_reported")),
                        cast(bool, value.get("protection_qualified", False)))
