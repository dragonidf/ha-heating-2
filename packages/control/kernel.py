"""Deterministic safety and ownership reduction over explicitly injected inputs."""
from dataclasses import replace
from hashlib import sha256

from packages.contracts import (
    Action, Clock, CommandIntent, ControlEvent, ControlMode, ControlPolicy,
    ControlSnapshot, ControlState, Decision, EventKind, HeatPermit, Plan,
    QualityStatus, Reading, Reason, ReceiptStage, RuntimeMode, SourceKind,
)


def _reading_ok(reading: Reading | None, max_age: float, snapshot: ControlSnapshot,
                policy: ControlPolicy, clock: Clock) -> bool:
    if reading is None or reading.value is None or reading.quality.status is not QualityStatus.VALID:
        return False
    if reading.provenance.kind in (SourceKind.HELD, SourceKind.FORECAST):
        return False
    skew = policy.max_skew_s
    return (-skew <= clock.utc - reading.observed_at <= max_age
            and reading.quality.age_s <= max_age
            and reading.observed_at - skew <= reading.received_at <= clock.utc + skew
            and reading.observed_at <= snapshot.captured_at + skew
            and reading.received_at <= snapshot.captured_at + skew)


def _safety_reason(state: ControlState, snapshot: ControlSnapshot,
                   policy: ControlPolicy, clock: Clock) -> Reason:
    if snapshot.hard_stop:
        return Reason.HARD_STOP
    if clock.boot_id != state.boot_id or snapshot.boot_id != state.boot_id:
        return Reason.CLOCK
    if clock.monotonic < state.last_monotonic or snapshot.owner_epoch != state.owner_epoch:
        return Reason.CLOCK
    if clock.utc + policy.max_skew_s < state.last_event_at:
        return Reason.CLOCK
    if state.off_latched or policy.operating_mode is ControlMode.OFF:
        return Reason.OFF
    if state.manual_paused or policy.operating_mode is ControlMode.OBSERVATION:
        return Reason.MANUAL
    if not policy.armed or not policy.allow_automatic:
        return Reason.PERMISSION
    if not policy.configuration_valid or policy.config_revision != snapshot.revisions.config:
        return Reason.CONFIGURATION
    if not policy.limits_qualified or policy.room_upper_c is None or policy.return_upper_c is None:
        return Reason.LIMIT_UNQUALIFIED
    if not -policy.max_skew_s <= clock.utc - snapshot.captured_at <= policy.snapshot_max_age_s:
        return Reason.SNAPSHOT
    if not _reading_ok(snapshot.grid_actual, policy.grid_max_age_s, snapshot, policy, clock):
        return Reason.GRID
    if snapshot.grid_actual is None or snapshot.grid_actual.value is not True:
        return Reason.GRID
    roles = ((snapshot.room, policy.room_max_age_s),
             (snapshot.return_temperature, policy.return_max_age_s),
             (snapshot.thermostat, policy.thermostat_max_age_s))
    if not all(_reading_ok(r, age, snapshot, policy, clock) for r, age in roles):
        return Reason.READING
    # Latest observations have independent age budgets, not a simultaneous sample time.
    # Units and scalar kinds are validated by ControlSnapshot/Reading constructors.
    if (snapshot.room is not None and snapshot.room.value is not None
            and float(snapshot.room.value) >= policy.room_upper_c):
        return Reason.UPPER
    if (snapshot.return_temperature is not None
            and snapshot.return_temperature.value is not None
            and float(snapshot.return_temperature.value) >= policy.return_upper_c):
        return Reason.RETURN_UPPER
    if snapshot.scheduled_outage:
        return Reason.OUTAGE
    if policy.strict_windows is not None and not any(w.contains(clock.utc) for w in policy.strict_windows):
        return Reason.WINDOW
    if policy.operating_mode is ControlMode.NATIVE_AUTO:
        return Reason.NATIVE_UNQUALIFIED
    return Reason.ALLOWED


def _plan_reason(plan: Plan | None, accepted_hash: str | None,
                 snapshot: ControlSnapshot, clock: Clock) -> Reason:
    if plan is None:
        return Reason.PLAN
    if (plan.boot_id != clock.boot_id or plan.owner_epoch != snapshot.owner_epoch
            or plan.grid_epoch != snapshot.grid_epoch or plan.revisions != snapshot.revisions
            or plan.input_hash != accepted_hash):
        return Reason.PLAN
    if clock.utc >= min(plan.valid_until, plan.expires_at):
        return Reason.PLAN_EXPIRED
    if clock.utc < plan.valid_from or not plan.heats_at(clock.utc):
        return Reason.NO_SEGMENT
    return Reason.ALLOWED


def evaluate(state: ControlState, snapshot: ControlSnapshot,
             policy: ControlPolicy, clock: Clock) -> HeatPermit:
    """All HEAT eligibility checks; no command dispatch or physical success."""
    reason = _safety_reason(state, snapshot, policy, clock)
    if policy.operating_mode is ControlMode.SHADOW:
        reason = Reason.SHADOW
    elif reason is Reason.ALLOWED:
        if not state.reconciled:
            reason = Reason.STARTING
        else:
            reason = _plan_reason(state.plan, state.accepted_input_hash, snapshot, clock)
            if reason is Reason.ALLOWED and state.recovery_at is not None:
                if (state.healthy_since is None
                        or clock.monotonic - state.healthy_since < policy.recovery_stable_s
                        or state.plan is None or state.plan.issued_at <= state.recovery_at):
                    reason = Reason.RECOVERY
            if reason is Reason.ALLOWED and state.desired_action is Action.STOP:
                if (state.changed_at_monotonic is None
                        or clock.monotonic - state.changed_at_monotonic < policy.min_off_s):
                    reason = Reason.MIN_OFF
            if (reason is Reason.ALLOWED and state.last_intent is not None
                    and state.last_intent.action is Action.HEAT
                    and clock.utc >= state.last_intent.expires_at):
                reason = Reason.INTENT_EXPIRED
    return HeatPermit(allowed=reason is Reason.ALLOWED, reason=reason,
                      snapshot_id=snapshot.snapshot_id, revisions=snapshot.revisions)


def assess_intent(intent: CommandIntent, clock: Clock, owner_epoch: int,
                  last_sequence: int, snapshot_id: str) -> Reason:
    """Pure admission predicate, not a gateway, queue, retry or execution."""
    if intent.boot_id != clock.boot_id or intent.owner_epoch != owner_epoch:
        return Reason.CLOCK
    if not intent.not_before <= clock.utc < intent.expires_at:
        return Reason.INTENT_EXPIRED
    if intent.sequence <= last_sequence:
        return Reason.DUPLICATE
    if intent.snapshot_id != snapshot_id:
        return Reason.SNAPSHOT
    return Reason.ALLOWED


def _decision(state: ControlState, snapshot: ControlSnapshot, policy: ControlPolicy,
              clock: Clock, reason: Reason, action: Action, mode: RuntimeMode,
              *, suppress: bool = False) -> Decision:
    permit = HeatPermit(allowed=reason in (Reason.ALLOWED, Reason.MIN_ON), reason=reason,
                        snapshot_id=snapshot.snapshot_id, revisions=snapshot.revisions)
    previous = state.desired_action
    updated = replace(state, mode=mode, desired_action=action)
    if previous is not action:
        updated = replace(updated, changed_at_monotonic=clock.monotonic)
    if suppress or (previous is action and state.last_intent is not None):
        return Decision(state=updated, permit=permit, intents=())
    sequence = state.command_sequence + 1
    expiry = clock.utc + policy.intent_ttl_s
    if action is Action.HEAT and state.plan is not None:
        expiry = min(expiry, state.plan.valid_until, state.plan.expires_at,
                     next(s.end for s in state.plan.segments if s.contains(clock.utc)))
    identity = sha256(f"{clock.boot_id}:{state.owner_epoch}:{sequence}".encode()).hexdigest()
    intent = CommandIntent(intent_id=identity, boot_id=clock.boot_id, owner_epoch=state.owner_epoch,
                           sequence=sequence, action=action, not_before=clock.utc, expires_at=expiry,
                           snapshot_id=snapshot.snapshot_id,
                           plan_id=state.plan.plan_id if state.plan else None, reason=reason)
    updated = replace(updated, last_intent=intent, command_sequence=sequence)
    return Decision(state=updated, permit=permit, intents=(intent,))


def _force_stop(state: ControlState, snapshot: ControlSnapshot, policy: ControlPolicy,
                clock: Clock, reason: Reason) -> Decision:
    updated = replace(state, plan=None, accepted_input_hash=None,
                      recovery_at=state.recovery_at if state.recovery_at is not None else clock.utc,
                      healthy_since=None,
                      manual_paused=state.manual_paused or reason is Reason.MANUAL,
                      off_latched=state.off_latched or reason is Reason.OFF)
    mode = (RuntimeMode.MANUAL_PAUSE if reason is Reason.MANUAL else RuntimeMode.OFF
            if reason is Reason.OFF else RuntimeMode.SAFE_HOLD)
    return _decision(updated, snapshot, policy, clock, reason, Action.STOP, mode,
                     suppress=reason is Reason.MANUAL)


def _ignore(state: ControlState, snapshot: ControlSnapshot, policy: ControlPolicy,
            clock: Clock, reason: Reason) -> Decision:
    # Rejected events cannot mask a newly unsafe current snapshot/expired intent.
    current = evaluate(state, snapshot, policy, clock)
    if state.desired_action is Action.HEAT and not current.allowed:
        return _force_stop(state, snapshot, policy, clock, current.reason)
    return _decision(state, snapshot, policy, clock, reason,
                     state.desired_action, state.mode, suppress=True)


def reduce(state: ControlState, event: ControlEvent, snapshot: ControlSnapshot,
           policy: ControlPolicy, clock: Clock) -> Decision:
    """One event in, immutable state/intent descriptions out. All clocks are injected."""
    emergency = event.kind is EventKind.SAFETY_STOP
    trusted_stop = (emergency and event.authorized
                    and event.boot_id == clock.boot_id == state.boot_id
                    and event.owner_epoch == state.owner_epoch
                    and event.sequence > state.last_safety_stop_sequence
                    and event.at <= clock.utc + policy.max_skew_s)
    # Emergency assertions have a separate replay frontier; ordinary queue TTL/order cannot drop them.
    event_ok = (not emergency and event.boot_id == clock.boot_id == state.boot_id
                and event.owner_epoch == state.owner_epoch
                and event.sequence > state.last_event_sequence
                and state.last_event_at <= event.at <= clock.utc + policy.max_skew_s
                and clock.utc < event.expires_at
                and clock.monotonic >= state.last_monotonic)
    updated = (replace(state, last_event_sequence=event.sequence, last_event_at=event.at,
                       last_monotonic=clock.monotonic) if event_ok else state)
    if trusted_stop:
        updated = replace(updated, last_safety_stop_sequence=event.sequence,
                          last_monotonic=max(state.last_monotonic, clock.monotonic))
    manual_event = event_ok and event.kind in (EventKind.MANUAL_CHANGE, EventKind.UNKNOWN_CHANGE, EventKind.OFF)
    if manual_event:
        updated = replace(updated, owner_epoch=state.owner_epoch + 1,
                          manual_paused=event.kind is not EventKind.OFF,
                          off_latched=event.kind is EventKind.OFF, plan=None,
                          accepted_input_hash=None, last_intent=None, last_receipt=None,
                          healthy_since=None, last_safety_stop_sequence=-1)
    if policy.operating_mode is ControlMode.SHADOW:
        shadow = replace(updated, reconciled=False, plan=None, accepted_input_hash=None)
        return _decision(shadow, snapshot, policy, clock, Reason.SHADOW,
                         Action.STOP, RuntimeMode.SHADOW, suppress=True)
    if snapshot.hard_stop or trusted_stop:
        return _force_stop(updated, snapshot, policy, clock, Reason.HARD_STOP)
    if emergency:
        return _ignore(state, snapshot, policy, clock,
                       Reason.STOP_DENIED if not event.authorized else Reason.STALE_EVENT)
    if not event_ok:
        return _ignore(state, snapshot, policy, clock, Reason.STALE_EVENT)
    if manual_event:
        mode = RuntimeMode.OFF if event.kind is EventKind.OFF else RuntimeMode.MANUAL_PAUSE
        reason = Reason.OFF if mode is RuntimeMode.OFF else Reason.MANUAL
        return _decision(updated, snapshot, policy, clock, reason, Action.STOP, mode,
                         suppress=event.kind is not EventKind.OFF)
    if event.kind is EventKind.RESUME:
        if not event.authorized:
            return _ignore(updated, snapshot, policy, clock, Reason.RESUME_DENIED)
        updated = replace(updated, owner_epoch=state.owner_epoch + 1, manual_paused=False,
                          off_latched=False, reconciled=False, plan=None, accepted_input_hash=None,
                          last_intent=None, last_receipt=None, healthy_since=None, recovery_at=clock.utc,
                          last_safety_stop_sequence=-1)
        return _decision(updated, snapshot, policy, clock, Reason.STARTING,
                         Action.STOP, RuntimeMode.STARTING, suppress=True)
    if event.kind is EventKind.RECONCILE:
        updated = replace(updated, reconciled=True, plan=None, accepted_input_hash=None,
                          last_intent=None, last_receipt=None, changed_at_monotonic=clock.monotonic)
    if event.kind is EventKind.PLAN and event.plan is not None:
        # Admission hashes bind the original input; later live readings may change.
        candidate = _plan_reason(event.plan, snapshot.input_hash, snapshot, clock)
        if candidate in (Reason.ALLOWED, Reason.NO_SEGMENT) and event.plan.issued_at <= clock.utc:
            updated = replace(updated, plan=event.plan, accepted_input_hash=snapshot.input_hash)
        else:
            return _ignore(updated, snapshot, policy, clock, candidate)
    if event.kind is EventKind.OWN_ECHO and event.receipt is not None:
        receipt = event.receipt
        intent = updated.last_intent
        if intent is None or (receipt.intent_id, receipt.boot_id, receipt.owner_epoch, receipt.sequence) != (
                intent.intent_id, intent.boot_id, intent.owner_epoch, intent.sequence):
            return _ignore(updated, snapshot, policy, clock, Reason.STALE_EVENT)
        updated = replace(updated, last_receipt=receipt)
        if receipt.action is not intent.action or receipt.stage in (ReceiptStage.FAILED, ReceiptStage.UNKNOWN):
            updated = replace(updated, plan=None, accepted_input_hash=None,
                              recovery_at=state.recovery_at if state.recovery_at is not None else clock.utc,
                              healthy_since=None)
            return _decision(updated, snapshot, policy, clock, Reason.ECHO_MISMATCH,
                             Action.STOP, RuntimeMode.SAFE_HOLD)
    safety = _safety_reason(updated, snapshot, policy, clock)
    if updated.recovery_at is not None:
        updated = replace(updated, healthy_since=(updated.healthy_since if updated.healthy_since is not None
                          else clock.monotonic) if safety is Reason.ALLOWED else None)
    permit = evaluate(updated, snapshot, policy, clock)
    if not permit.allowed:
        reason = permit.reason
        if reason in (Reason.MANUAL, Reason.OFF):
            updated = replace(updated, manual_paused=reason is Reason.MANUAL,
                              off_latched=reason is Reason.OFF)
        if reason in (Reason.CLOCK, Reason.GRID, Reason.READING, Reason.SNAPSHOT, Reason.CONFIGURATION,
                      Reason.LIMIT_UNQUALIFIED, Reason.UPPER, Reason.RETURN_UPPER, Reason.OUTAGE,
                      Reason.PLAN, Reason.PLAN_EXPIRED, Reason.INTENT_EXPIRED, Reason.NATIVE_UNQUALIFIED):
            updated = replace(updated, plan=None, accepted_input_hash=None,
                              recovery_at=updated.recovery_at if updated.recovery_at is not None
                              else clock.utc, healthy_since=None if safety is not Reason.ALLOWED
                              else updated.healthy_since if updated.healthy_since is not None else clock.monotonic)
        mode = (RuntimeMode.MANUAL_PAUSE if reason is Reason.MANUAL else RuntimeMode.OFF if reason is Reason.OFF
                else RuntimeMode.STARTING if reason is Reason.STARTING
                else RuntimeMode.FALLBACK if reason in (Reason.PLAN, Reason.PLAN_EXPIRED, Reason.INTENT_EXPIRED,
                                                        Reason.NATIVE_UNQUALIFIED, Reason.RECOVERY)
                else RuntimeMode.SAFE_HOLD)
        return _decision(updated, snapshot, policy, clock, reason, Action.STOP, mode,
                         suppress=reason is Reason.MANUAL)
    if event.kind is EventKind.STOP_REQUEST:
        if (state.desired_action is Action.HEAT and state.changed_at_monotonic is not None
                and clock.monotonic - state.changed_at_monotonic < policy.min_on_s):
            return _decision(updated, snapshot, policy, clock, Reason.MIN_ON, Action.HEAT, RuntimeMode.AUTO_PLAN)
        return _decision(updated, snapshot, policy, clock, Reason.NO_SEGMENT, Action.STOP, RuntimeMode.SAFE_HOLD)
    updated = replace(updated, recovery_at=None, healthy_since=None)
    mode = RuntimeMode.AUTO_PLAN if snapshot.compute_available else RuntimeMode.AUTO_HOLD
    return _decision(updated, snapshot, policy, clock, Reason.ALLOWED, Action.HEAT, mode)
