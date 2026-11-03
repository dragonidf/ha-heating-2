"""Fake-only writer and bounded latest-wins scheduler; STOP never calls SQLite."""
from dataclasses import dataclass, replace
from hashlib import sha256
from threading import RLock
from typing import Callable

from packages.contracts import (
    Action, Clock, CommandIntent, CommandReceipt, ControlEvent, ControlMode, ControlSnapshot,
    ControlState, Decision, EventKind, ReceiptStage, RuntimeMode, to_json,
)
from packages.control import assess_intent, evaluate, reduce
from packages.control_store.store import ControlStore, StoreFailure, StoreView


@dataclass(frozen=True, slots=True)
class FakeCall:
    action: Action
    boot_id: str
    owner_epoch: int
    sequence: int
    at: float


@dataclass(frozen=True, slots=True)
class FakeProof:
    issuer: object
    digest: str


class FakeAuthority:
    """In-process test capability. It is not an authentication implementation."""
    def __init__(self) -> None:
        self._seal = object()

    def attest(self, event: ControlEvent) -> FakeProof:
        return FakeProof(self._seal, sha256(to_json(event).encode()).hexdigest())

    def accepts(self, event: ControlEvent, proof: FakeProof | None) -> bool:
        return (type(proof) is FakeProof and proof.issuer is self._seal
                and proof.digest == sha256(to_json(event).encode()).hexdigest())


@dataclass(frozen=True, slots=True)
class FakeObservation:
    issuer: object
    boot_id: str
    owner_epoch: int
    action: Action | None
    manual: bool
    writers_known: bool
    at: float


class FakeActuator:
    """Only records desired actions in RAM. Echo is explicitly injected, never power."""
    def __init__(self) -> None:
        self._lock = RLock()
        self._writer: object | None = None
        self._seal = object()
        self._boot = "synthetic.unbound"
        self._owner = 0
        self._generation = 0
        self._calls: list[FakeCall] = []
        self.fail_send = False

    @property
    def calls(self) -> tuple[FakeCall, ...]:
        with self._lock:
            return tuple(self._calls)

    def reserve(self) -> object:
        with self._lock:
            if self._writer is not None:
                raise RuntimeError("Fake actuator already has a writer")
            self._writer = object()
            return self._writer

    def release(self, writer: object) -> None:
        with self._lock:
            if self._writer is writer:
                self._writer = None

    def fence(self, writer: object, state: ControlState, generation: int) -> None:
        with self._lock:
            if self._writer is not writer:
                raise RuntimeError("Stale fake writer")
            self._boot, self._owner, self._generation = state.boot_id, state.owner_epoch, generation

    def send(self, writer: object, generation: int, action: Action, sequence: int, clock: Clock) -> bool:
        with self._lock:
            if self._writer is not writer or generation != self._generation or clock.boot_id != self._boot:
                return False
            if action is Action.HEAT and self.fail_send:
                raise RuntimeError("Injected fake service failure; outcome unknown")
            self._calls.append(FakeCall(action, self._boot, self._owner, sequence, clock.utc))
            return True

    def feedback(self, action: Action | None, clock: Clock, *, manual: bool = False,
                 writers_known: bool = True) -> FakeObservation:
        return FakeObservation(self._seal, self._boot, self._owner, action, manual, writers_known, clock.utc)

    def accepts(self, observation: FakeObservation | None, state: ControlState, clock: Clock, age: float,
                skew: float) -> bool:
        return (type(observation) is FakeObservation and observation.issuer is self._seal
                and (observation.boot_id, observation.owner_epoch) == (state.boot_id, state.owner_epoch)
                and clock.boot_id == state.boot_id and -skew <= clock.utc-observation.at <= age)


class Simulator:
    def __init__(self, store: ControlStore, actuator: FakeActuator, new_boot: str,
                 *, hook: Callable[[str], None] | None = None):
        if type(actuator) is not FakeActuator:
            raise TypeError("Only the in-memory FakeActuator is supported")
        self.actuator = actuator
        self._writer = actuator.reserve()
        try:
            self._view = store.restart(new_boot)
        except BaseException:
            actuator.release(self._writer)
            raise
        self.store = store
        self.authority = FakeAuthority()
        self.hook = hook
        self._lock = RLock()
        self._generation = 0
        self._pending: tuple[CommandIntent, str | None] | None = None
        self._audit: list[tuple[ControlEvent, Decision]] = []
        self.audit_missing = 0
        self.last_error: str | None = None
        self._sent: CommandIntent | None = None
        self._closed = False
        self._inputs: tuple[ControlSnapshot, Clock] | None = None
        self.actuator.fence(self._writer, self.state, self._generation)

    @property
    def state(self) -> ControlState:
        return self._view.state

    @property
    def pending_count(self) -> int:
        return int(self._pending is not None)

    def _point(self, point: str) -> None:
        if self.hook is not None:
            self.hook(point)

    def update_inputs(self, snapshot: ControlSnapshot, clock: Clock) -> None:
        """Advance explicitly injected virtual inputs; never read a system clock."""
        with self._lock:
            if self._inputs is not None:
                previous_snapshot, previous_clock = self._inputs
                if (clock.boot_id != self.state.boot_id or clock.monotonic < previous_clock.monotonic
                        or clock.utc + self._view.policy.max_skew_s < previous_clock.utc
                        or snapshot.grid_epoch < previous_snapshot.grid_epoch
                        or snapshot.captured_at < previous_snapshot.captured_at):
                    self._halt(clock, "input_clock_or_epoch_rollback")
                    return
            self._inputs = (snapshot, clock)
            if self.state.desired_action is Action.HEAT and not evaluate(self.state, snapshot, self._view.policy, clock).allowed:
                self._halt(clock, "current_input_permission_denied")

    def _install(self, decision: Decision, clock: Clock, one_shot_id: str | None = None) -> None:
        self._view = StoreView(self._view.revision, decision.state, self._view.policy)
        self._generation += 1
        self.actuator.fence(self._writer, self.state, self._generation)
        if self.state.mode is RuntimeMode.SHADOW:
            self._pending = None
        elif decision.intents:
            intent = decision.intents[0]
            self._pending = (intent, one_shot_id) if intent.action is Action.HEAT else None
            if intent.action is Action.STOP:
                self.actuator.send(self._writer, self._generation, Action.STOP, intent.sequence, clock)
        elif self.state.desired_action is Action.STOP:
            self._pending = None

    def emergency(self, event: ControlEvent, snapshot: ControlSnapshot, clock: Clock,
                  *, proof: FakeProof | None = None) -> Decision:
        if event.kind is not EventKind.SAFETY_STOP:
            raise ValueError("Emergency assertion required")
        with self._lock:
            self.update_inputs(snapshot, clock)
            trusted = replace(event, authorized=self.authority.accepts(event, proof))
            decision = reduce(self.state, trusted, snapshot, self._view.policy, clock)
            if decision.state != self.state or decision.intents:
                self._install(decision, clock)
                if len(self._audit) < 16:
                    self._audit.append((trusted, decision))
                else:
                    self.audit_missing += 1
                    self._audit[-1] = (trusted, decision)  # Retain the newest replay frontier when audit coalesces.
            return decision

    def apply(self, event: ControlEvent, snapshot: ControlSnapshot, clock: Clock,
              *, proof: FakeProof | None = None, observation: FakeObservation | None = None,
              one_shot_id: str | None = None) -> Decision | None:
        if event.kind is EventKind.SAFETY_STOP:
            return self.emergency(event, snapshot, clock, proof=proof)
        with self._lock:
            self.update_inputs(snapshot, clock)
            p = self._view.policy
            if event.kind in (EventKind.RECONCILE, EventKind.MANUAL_CHANGE, EventKind.UNKNOWN_CHANGE):
                if observation is None or not self.actuator.accepts(observation, self.state, clock, p.snapshot_max_age_s, p.max_skew_s):
                    self.last_error = "untrusted_or_stale_fake_observation"
                    return None
                if event.kind is EventKind.RECONCILE and (observation.action is None or not observation.writers_known):
                    self.last_error = "unknown_external_state_or_writers"
                    return None
                if observation.manual:
                    event = replace(event, kind=EventKind.MANUAL_CHANGE)
            if event.kind is EventKind.RESUME:
                event = replace(event, authorized=self.authority.accepts(event, proof))
            previous = self._view
            decision = reduce(self.state, event, snapshot, p, clock)
            self._install(decision, clock, one_shot_id)
            generation = self._generation
        try:
            committed = self.store.transition(event, decision, previous.revision)
            with self._lock:
                if generation == self._generation:
                    self._view = committed
        except StoreFailure:
            self._halt(clock, "state_commit_failed")
        return decision

    def _halt(self, clock: Clock, reason: str) -> None:
        with self._lock:
            self.last_error = reason
            if self._closed:
                return
            self.audit_missing += 1
            self._pending = None
            self._generation += 1
            mode = self.state.mode if self.state.mode in (RuntimeMode.SHADOW, RuntimeMode.MANUAL_PAUSE, RuntimeMode.OFF) else RuntimeMode.SAFE_HOLD
            self._view = StoreView(self._view.revision, replace(self.state, desired_action=Action.STOP, mode=mode,
                                  plan=None, accepted_input_hash=None, reconciled=False), self._view.policy)
            self.actuator.fence(self._writer, self.state, self._generation)
            if self.state.mode not in (RuntimeMode.SHADOW, RuntimeMode.MANUAL_PAUSE):
                self.actuator.send(self._writer, self._generation, Action.STOP, 0, clock)

    def pump(self, snapshot: ControlSnapshot, clock: Clock) -> bool:
        with self._lock:
            if self._closed or self._pending is None:
                return False
            self.update_inputs(snapshot, clock)
            if self._pending is None:
                return False
            intent, shot = self._pending
            self._pending = None
            generation, view = self._generation, self._view
        try:
            self.store.prepare(intent, snapshot, clock, view.revision, one_shot_id=shot)
            self._point("before_send")
            self.store.claim(intent, view.state, snapshot, clock)
            durable = self.store.view()
            with self._lock:
                if self._closed or generation != self._generation:
                    return False
                if durable.revision != view.revision or durable.state != view.state or durable.policy != view.policy:
                    self._halt(clock, "durable_generation_changed")
                    return False
                if self._inputs is not None:
                    snapshot, clock = self._inputs
                if (not evaluate(self.state, snapshot, self._view.policy, clock).allowed
                        or assess_intent(intent, clock, self.state.owner_epoch, -1, snapshot.snapshot_id).value != "allowed"):
                    self._halt(clock, "fresh_boundary_permission_denied")
                    return False
                if not self.actuator.send(self._writer, generation, Action.HEAT, intent.sequence, clock):
                    return False
                self._sent = intent
            self._point("after_fake_send")
            prepared = self.store.receipt(intent.intent_id)
            receipt = replace(prepared, stage=ReceiptStage.SENT, sent_at=clock.utc)
            self.store.record_receipt(receipt, view.state)
            self._point("after_sent")
            return True
        except (StoreFailure, RuntimeError):
            self._halt(clock, "prepare_or_send_failed_unknown")
            return False

    def _evidence(self, clock: Clock, stage: ReceiptStage) -> bool:
        with self._lock:
            intent, fence = self._sent, self.state
        if intent is None:
            raise StoreFailure("No current fake send")
        old = self.store.receipt(intent.intent_id)
        receipt = (replace(old, stage=stage, ha_ack_at=clock.utc) if stage is ReceiptStage.ACKNOWLEDGED
                   else replace(old, stage=stage, device_echo_at=clock.utc))
        self._point("before_echo_receipt" if stage is ReceiptStage.ECHOED else "before_ack_receipt")
        result = self.store.record_receipt(receipt, fence)
        self._point("after_echo" if stage is ReceiptStage.ECHOED else "after_ack")
        return result

    def ack(self, clock: Clock) -> bool:
        return self._evidence(clock, ReceiptStage.ACKNOWLEDGED)

    def echo(self, clock: Clock) -> bool:
        return self._evidence(clock, ReceiptStage.ECHOED)

    def flush_audit(self) -> int:
        with self._lock:
            pending, self._audit = self._audit, []
        committed = 0
        for event, decision in pending:
            try:
                current = self.store.view()
                saved = self.store.transition(event, decision, current.revision)
                with self._lock:
                    if self.state == decision.state:
                        self._view = saved
                committed += 1
            except StoreFailure:
                self.audit_missing += 1
        return committed

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._pending = None
            self.actuator.release(self._writer)
