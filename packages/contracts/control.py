"""Control records only. A requested action is never a physical outcome."""
from dataclasses import dataclass
from enum import Enum

from .models import (
    Plan, QualityStatus, Reading, Revisions, TimeWindow, counter, digest,
    independent_measurements, number, require, text,
)


class Action(str, Enum):
    HEAT = "heat"
    STOP = "stop_demand"


class ControlMode(str, Enum):
    AUTO = "auto"
    OBSERVATION = "observation"
    NATIVE_AUTO = "native_auto"
    OFF = "off"
    SHADOW = "shadow"


class RuntimeMode(str, Enum):
    STARTING = "starting"
    SHADOW = "shadow"
    AUTO_PLAN = "auto_plan"
    AUTO_HOLD = "auto_hold"
    FALLBACK = "fallback"
    MANUAL_PAUSE = "manual_pause"
    OFF = "off"
    SAFE_HOLD = "safe_hold"


class Reason(str, Enum):
    ALLOWED = "allowed"
    HARD_STOP = "hard_stop"
    SHADOW = "shadow"
    OFF = "off"
    MANUAL = "manual_pause"
    PERMISSION = "permission_denied"
    CONFIGURATION = "invalid_configuration"
    LIMIT_UNQUALIFIED = "limit_unqualified"
    GRID = "grid_off_or_unknown"
    READING = "invalid_required_reading"
    CLOCK = "invalid_clock_or_epoch"
    SNAPSHOT = "stale_or_inconsistent_snapshot"
    UPPER = "room_upper"
    RETURN_UPPER = "return_upper"
    OUTAGE = "scheduled_outage"
    WINDOW = "outside_strict_window"
    STARTING = "reconcile_required"
    PLAN = "plan_missing_or_mismatch"
    PLAN_EXPIRED = "plan_expired"
    NO_SEGMENT = "no_active_segment"
    MIN_OFF = "minimum_off"
    MIN_ON = "minimum_on_hold"
    RECOVERY = "recovery_requires_stability_and_new_plan"
    NATIVE_UNQUALIFIED = "native_fallback_not_qualified"
    STALE_EVENT = "stale_event"
    RESUME_DENIED = "resume_not_authorized"
    INTENT_EXPIRED = "intent_expired_or_not_due"
    DUPLICATE = "duplicate_sequence"
    ECHO_MISMATCH = "unconfirmed_echo"


class EventKind(str, Enum):
    TICK = "tick"
    RECONCILE = "reconcile"
    PLAN = "plan"
    MANUAL_CHANGE = "manual_change"
    UNKNOWN_CHANGE = "uncorrelated_change"
    RESUME = "resume"
    OFF = "off"
    OWN_ECHO = "own_echo"
    STOP_REQUEST = "soft_stop_request"
    SAFETY_STOP = "safety_stop"


class ReceiptStage(str, Enum):
    REQUESTED = "requested"
    PREPARED = "prepared"
    SENT = "sent"
    ACKNOWLEDGED = "ha_acknowledged"
    ECHOED = "device_echoed"
    PHYSICAL_EVIDENCE = "external_physical_evidence"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, kw_only=True)
class ControlPolicy:
    config_revision: int
    operating_mode: ControlMode
    armed: bool
    allow_automatic: bool
    configuration_valid: bool
    limits_qualified: bool
    room_upper_c: float | None
    return_upper_c: float | None
    room_max_age_s: float
    return_max_age_s: float
    thermostat_max_age_s: float
    grid_max_age_s: float
    snapshot_max_age_s: float
    max_skew_s: float
    min_on_s: float
    min_off_s: float
    intent_ttl_s: float
    recovery_stable_s: float
    strict_windows: tuple[TimeWindow, ...] | None

    def __post_init__(self) -> None:
        counter(self.config_revision)
        require(isinstance(self.operating_mode, ControlMode), "Invalid operating mode")
        for flag in (self.armed, self.allow_automatic, self.configuration_valid, self.limits_qualified):
            require(type(flag) is bool, "Invalid permission/qualification flag")
        for limit in (self.room_upper_c, self.return_upper_c):
            if limit is not None:
                number(limit)
                require(limit > -273.15, "Invalid Celsius limit")
        for duration in (self.room_max_age_s, self.return_max_age_s, self.thermostat_max_age_s,
                         self.grid_max_age_s, self.snapshot_max_age_s, self.max_skew_s,
                         self.min_on_s, self.min_off_s, self.intent_ttl_s, self.recovery_stable_s):
            number(duration, nonnegative=True)
        require(self.intent_ttl_s > 0, "Positive intent lifetime required")
        if self.strict_windows is not None:
            require(type(self.strict_windows) is tuple and len(self.strict_windows) <= 256,
                    "Invalid immutable strict windows")
            previous = 0.0
            for window in self.strict_windows:
                require(isinstance(window, TimeWindow) and previous <= window.start,
                        "Overlapping/unsorted strict windows")
                previous = window.end


@dataclass(frozen=True, slots=True, kw_only=True)
class HeatPermit:
    allowed: bool
    reason: Reason
    snapshot_id: str
    revisions: Revisions

    def __post_init__(self) -> None:
        require(type(self.allowed) is bool and isinstance(self.reason, Reason), "Invalid permit")
        require(self.allowed == (self.reason in (Reason.ALLOWED, Reason.MIN_ON)),
                "Conflicting permit reason")
        text(self.snapshot_id)
        require(isinstance(self.revisions, Revisions), "Invalid permit revisions")


@dataclass(frozen=True, slots=True, kw_only=True)
class CommandIntent:
    intent_id: str
    boot_id: str
    owner_epoch: int
    sequence: int
    action: Action
    not_before: float
    expires_at: float
    snapshot_id: str
    plan_id: str | None
    reason: Reason

    def __post_init__(self) -> None:
        for value in (self.intent_id, self.boot_id, self.snapshot_id):
            text(value)
        if self.plan_id is not None:
            text(self.plan_id)
        counter(self.owner_epoch)
        counter(self.sequence)
        require(isinstance(self.action, Action) and isinstance(self.reason, Reason), "Invalid action/reason")
        number(self.not_before, nonnegative=True)
        number(self.expires_at, nonnegative=True)
        require(self.not_before < self.expires_at, "Invalid intent lifetime")


@dataclass(frozen=True, slots=True, kw_only=True)
class CommandReceipt:
    intent_id: str
    boot_id: str
    owner_epoch: int
    sequence: int
    action: Action
    stage: ReceiptStage
    requested_at: float
    prepared_at: float | None = None
    sent_at: float | None = None
    ha_ack_at: float | None = None
    device_echo_at: float | None = None
    physical_effect_at: float | None = None
    evidence: tuple[Reading, ...] = ()

    def __post_init__(self) -> None:
        text(self.intent_id)
        text(self.boot_id)
        counter(self.owner_epoch)
        counter(self.sequence)
        require(isinstance(self.action, Action) and isinstance(self.stage, ReceiptStage), "Invalid receipt")
        number(self.requested_at, nonnegative=True)
        for at in (self.prepared_at, self.sent_at, self.ha_ack_at,
                   self.device_echo_at, self.physical_effect_at):
            if at is not None:
                number(at, nonnegative=True)
                require(at >= self.requested_at, "Receipt precedes request")
        for stage, at in ((ReceiptStage.PREPARED, self.prepared_at), (ReceiptStage.SENT, self.sent_at),
                          (ReceiptStage.ACKNOWLEDGED, self.ha_ack_at),
                          (ReceiptStage.ECHOED, self.device_echo_at),
                          (ReceiptStage.PHYSICAL_EVIDENCE, self.physical_effect_at)):
            require(self.stage is not stage or at is not None, "Missing stage evidence time")
        require(type(self.evidence) is tuple and len(self.evidence) <= 64
                and all(isinstance(r, Reading) for r in self.evidence), "Invalid receipt evidence")
        require(self.physical_effect_at is None or bool(self.evidence), "Physical claim needs external evidence")
        if self.physical_effect_at is not None:
            require(independent_measurements(self.evidence)
                    and all(r.value is not None and r.quality.status is QualityStatus.VALID
                            for r in self.evidence), "Physical evidence must be valid and independent")


class OneShotKind(str, Enum):
    HEAT_AFTER_GRID_RESTORE = "heat_after_grid_restore"


class OneShotOutcome(str, Enum):
    PENDING = "pending"
    CONSUMED = "consumed"
    UNKNOWN = "unknown_outcome"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class OneShot:
    intent_id: str
    kind: OneShotKind
    created_at: float
    expires_at: float
    armed_grid_epoch: int
    consumed_at: float | None
    outcome: OneShotOutcome

    def __post_init__(self) -> None:
        text(self.intent_id)
        require(isinstance(self.kind, OneShotKind) and isinstance(self.outcome, OneShotOutcome),
                "Unsupported one-shot kind/outcome")
        number(self.created_at, nonnegative=True)
        number(self.expires_at, nonnegative=True)
        require(self.created_at < self.expires_at, "Invalid one-shot lifetime")
        counter(self.armed_grid_epoch)
        if self.consumed_at is not None:
            number(self.consumed_at)
            require(self.created_at <= self.consumed_at < self.expires_at, "Invalid consumption time")
        require(self.outcome is not OneShotOutcome.PENDING or self.consumed_at is None,
                "Pending one-shot already consumed")
        require(self.outcome not in (OneShotOutcome.CONSUMED, OneShotOutcome.COMPLETED)
                or self.consumed_at is not None, "Missing consumption marker")


@dataclass(frozen=True, slots=True, kw_only=True)
class ControlState:
    boot_id: str
    owner_epoch: int
    mode: RuntimeMode = RuntimeMode.STARTING
    manual_paused: bool = False
    off_latched: bool = False
    reconciled: bool = False
    last_event_sequence: int = -1
    last_event_at: float = 0.0
    last_monotonic: float = 0.0
    changed_at_monotonic: float | None = None
    command_sequence: int = 0
    desired_action: Action = Action.STOP
    plan: Plan | None = None
    accepted_input_hash: str | None = None
    last_intent: CommandIntent | None = None
    last_receipt: CommandReceipt | None = None
    recovery_at: float | None = None
    healthy_since: float | None = None

    def __post_init__(self) -> None:
        text(self.boot_id)
        counter(self.owner_epoch)
        counter(self.command_sequence)
        require(type(self.last_event_sequence) is int and -1 <= self.last_event_sequence < 2**63,
                "Invalid event sequence")
        require(isinstance(self.mode, RuntimeMode) and isinstance(self.desired_action, Action),
                "Invalid control state")
        for flag in (self.manual_paused, self.off_latched, self.reconciled):
            require(type(flag) is bool, "Invalid state flag")
        for at in (self.last_event_at, self.last_monotonic, self.changed_at_monotonic,
                   self.recovery_at, self.healthy_since):
            if at is not None:
                number(at, nonnegative=True)
        for value, cls in ((self.plan, Plan), (self.last_intent, CommandIntent),
                           (self.last_receipt, CommandReceipt)):
            require(value is None or isinstance(value, cls), "Invalid stored contract")
        if self.accepted_input_hash is not None:
            digest(self.accepted_input_hash)


@dataclass(frozen=True, slots=True, kw_only=True)
class ControlEvent:
    kind: EventKind
    boot_id: str
    owner_epoch: int
    sequence: int
    at: float
    expires_at: float
    authorized: bool = False
    plan: Plan | None = None
    receipt: CommandReceipt | None = None

    def __post_init__(self) -> None:
        text(self.boot_id)
        counter(self.owner_epoch)
        counter(self.sequence)
        require(isinstance(self.kind, EventKind) and type(self.authorized) is bool, "Invalid event")
        number(self.at, nonnegative=True)
        number(self.expires_at, nonnegative=True)
        require(self.at <= self.expires_at, "Invalid event lifetime")
        require(self.plan is None or isinstance(self.plan, Plan), "Invalid event plan")
        require(self.receipt is None or isinstance(self.receipt, CommandReceipt), "Invalid event receipt")
        require((self.kind is EventKind.PLAN) == isinstance(self.plan, Plan), "Invalid plan event")
        require((self.kind is EventKind.OWN_ECHO) == isinstance(self.receipt, CommandReceipt),
                "Invalid receipt event")


@dataclass(frozen=True, slots=True, kw_only=True)
class Decision:
    state: ControlState
    permit: HeatPermit
    intents: tuple[CommandIntent, ...]

    def __post_init__(self) -> None:
        require(isinstance(self.state, ControlState) and isinstance(self.permit, HeatPermit),
                "Invalid decision")
        require(type(self.intents) is tuple and len(self.intents) <= 1
                and all(isinstance(i, CommandIntent) for i in self.intents), "Invalid intent descriptions")
