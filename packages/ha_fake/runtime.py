"""Offline orchestration over accepted contracts. Archive work is explicitly drained."""

from dataclasses import replace
from pathlib import Path
from hashlib import sha256
from typing import Literal
from packages.contracts import (
    Clock,
    ControlEvent,
    EventKind,
    Action,
    ControlSnapshot,
    Decision,
    Plan,
    TimeWindow,
)
from packages.contracts.models import require
from packages.control_store.store import StoreFailure
from packages.simulator.engine import Simulator, FakeProof
from packages.fan_policy import FanState, FanPolicy, FanDemand, reduce_fan
from packages.planner import Proposal, Stamp, Request, Curve, bridge, replan
from packages.offline.contracts import (
    SourceEvent,
    SaveRequest,
    APIReceipt,
    ArchiveRecord,
    StatusView,
    RecoveryRequest,
    RecoveryReceipt,
    ForecastRecord,
    ProviderEvent,
)
from packages.evidence.store import EvidenceStore, EvidenceFailure, record
from packages.ha_fake.client import FakeHAClient, FakeSession
from packages.ha_fake.adapter import SourceAdapter


class OfflineIntegration:
    def __init__(
        self,
        client: FakeHAClient,
        simulator: Simulator,
        evidence: EvidenceStore,
        operator: FakeSession,
        *,
        model_revision: int,
    ):
        require(
            type(client) is FakeHAClient
            and type(simulator) is Simulator
            and type(evidence) is EvidenceStore,
            "Only isolated fake components are supported",
        )
        require(
            evidence.path != simulator.store.path
            and evidence.root != simulator.store.root,
            "Evidence must be independent of critical store",
        )
        self.client = client
        self.simulator = simulator
        self.evidence = evidence
        self.operator = operator
        self.model_revision = model_revision
        self.adapter = SourceAdapter(client.registry)
        self.adapter.connection(client.generation)
        self._pending: list[ArchiveRecord] = []
        self.archive_lost = 0
        self._raw_frontier = 0
        self._sequence = 0
        self._settings_generation = 0
        self._config_revision = simulator.store.view().policy.config_revision
        self._armed = simulator.store.view().policy.armed
        self._fan_manual = False

    def _event(
        self, kind: EventKind, clock: Clock, *, plan: Plan | None = None
    ) -> ControlEvent:
        self._sequence = (
            max(
                self._sequence,
                self.simulator.state.last_event_sequence,
                self.simulator.state.last_safety_stop_sequence,
            )
            + 1
        )
        return ControlEvent(
            kind=kind,
            boot_id=self.simulator.state.boot_id,
            owner_epoch=self.simulator.state.owner_epoch,
            sequence=self._sequence,
            at=clock.utc,
            expires_at=clock.utc + 1,
            plan=plan,
        )

    def snapshot(self, clock: Clock) -> ControlSnapshot:
        self.adapter.connection(self.client.generation)
        return self.adapter.snapshot(
            clock,
            self.simulator.state,
            self._config_revision,
            self.model_revision,
            connected=self.client.connected,
        )

    def _archive(self, event: ArchiveRecord) -> None:
        if len(self._pending) < 256:
            self._pending.append(event)
        else:
            self.archive_lost += 1

    def deliver(self, event: SourceEvent, clock: Clock) -> Decision | None:
        self.adapter.connection(self.client.generation)
        if not self.adapter.ingest(event):
            return None
        self._archive(record(event.identity, event, event.received_at, event.entity))
        snapshot = self.snapshot(clock)
        binding = next(
            b for b in self.client.registry.bindings if b.entity == event.entity
        )
        if not self.client.permits(self.operator, "control"):
            return self.trusted_stop(clock)
        if (
            binding.role == "fan"
            and event.author != "sensor"
            and self.adapter.current_event(event)
        ):
            self._fan_manual = True
        kind = EventKind.TICK
        observation = None
        if (
            binding.role == "thermostat"
            and event.author != "sensor"
            and self.adapter.current_assertion(event, clock, binding.max_age_s)
        ):
            # Source labels can revoke ownership, never authenticate a physical action.
            # Missing/unqualified state has no observed action, including a claimed echo.
            kind = EventKind.UNKNOWN_CHANGE
            observation = self.simulator.actuator.feedback(
                None,
                clock,
                manual=False,
                writers_known=False,
            )
        return self.simulator.apply(
            self._event(kind, clock), snapshot, clock, observation=observation
        )

    def drain_events(
        self, clock: Clock, order: tuple[int, ...] | None = None
    ) -> tuple[Decision | None, ...]:
        return tuple(self.deliver(event, clock) for event in self.client.drain(order))

    def reconcile(
        self,
        clock: Clock,
        session: FakeSession,
        *,
        action: Action | None,
        writers_known: bool,
    ) -> Decision | None:
        require(
            self.client.permits(session, "control"), "Fake control permission required"
        )
        observation = self.simulator.actuator.feedback(
            action, clock, writers_known=writers_known
        )
        return self.simulator.apply(
            self._event(EventKind.RECONCILE, clock),
            self.snapshot(clock),
            clock,
            observation=observation,
        )

    def resume(self, clock: Clock, session: FakeSession) -> Decision | None:
        require(
            self.client.permits(session, "control"), "Fake control permission required"
        )
        event = self._event(EventKind.RESUME, clock)
        return self.simulator.apply(
            event,
            self.snapshot(clock),
            clock,
            proof=self.simulator.authority.attest(event),
        )

    def provider(self, event: ProviderEvent) -> bool:
        accepted = self.client.publish(event)
        if accepted:
            self._archive(
                record(event.identity, event, event.received_at, event.entity)
            )
        return accepted

    def plan(
        self,
        request: Request,
        previous: Proposal | None = None,
        *,
        material_change: bool = False,
    ) -> Proposal:
        require(
            request.model.revision == self.model_revision,
            "Compute model revision mismatch",
        )
        return replan(request, previous, material_change=material_change)

    def queue_forecast(
        self,
        proposal: Proposal,
        request: Request,
        cycle: str,
        reference: float,
        *,
        role: Literal["initial", "prestart", "latest"],
    ) -> ForecastRecord:
        require(
            proposal.stamp == request.stamp
            and proposal.status not in ("BLOCKED", "SEARCH_EXHAUSTED")
            and bool(proposal.trajectory),
            "Invalid forecast proposal",
        )
        identity = sha256(repr(proposal).encode()).hexdigest()
        curve = Curve(
            identity,
            request.state.at,
            ((request.state.at, request.state.room),)
            + tuple((s.at, s.room) for s in proposal.trajectory),
            request.stamp.input_hash,
            request.model.revision,
            identity,
            (request.weather.issue,),
        )
        scope = None
        energy = None
        horizon = request.slots[-1].window.end
        covered = (
            request.state.at == request.slots[0].window.start
            and all(
                a.window.end == b.window.start
                for a, b in zip(request.slots, request.slots[1:])
            )
            and tuple(s.at for s in proposal.trajectory)
            == tuple(s.window.end for s in request.slots)
        )
        require(
            all(
                request.state.at <= s.start < s.end <= horizon
                for s in proposal.segments
            )
            and all(
                a.end <= b.start
                for a, b in zip(proposal.segments, proposal.segments[1:])
            ),
            "Invalid forecast energy segments",
        )
        if (
            covered
            and request.state.at <= reference < horizon
            and request.limits_qualified
            and proposal.power_kw in request.stages_kw
            and proposal.power_kw is not None
        ):
            scope = TimeWindow(start=reference, end=horizon)
            energy = (
                sum(
                    max(0, min(s.end, scope.end) - max(s.start, scope.start))
                    for s in proposal.segments
                )
                * proposal.power_kw
                / 3600
            )
        forecast = ForecastRecord(
            sha256(repr((identity, cycle, role, reference)).encode()).hexdigest(),
            cycle,
            role,
            reference,
            curve,
            request.state.at,
            energy,
            scope,
        )
        self._archive(record(identity, proposal, request.state.at, cycle))
        self._archive(record(forecast.identity, forecast, forecast.recorded_at, cycle))
        return forecast  # Queued evidence, never a durable-save or physical receipt.

    def accept(self, proposal: Proposal, clock: Clock) -> Decision | None:
        require(
            self.client.permits(self.operator, "control"),
            "Fake control permission required",
        )
        require(bool(proposal.trajectory), "Missing proposal trajectory")
        snapshot = self.snapshot(clock)
        stamp = Stamp(
            snapshot.input_hash,
            snapshot.revisions,
            snapshot.boot_id,
            snapshot.owner_epoch,
            snapshot.grid_epoch,
        )
        plan = bridge(proposal, stamp, clock.utc, proposal.trajectory[-1].at + 1)
        event = self._event(EventKind.PLAN, clock, plan=plan)
        return self.simulator.apply(event, snapshot, clock)

    def pump(self, clock: Clock) -> bool:
        if not self.client.permits(self.operator, "control"):
            self.trusted_stop(clock)
            return False
        snapshot = self.snapshot(clock)
        self.simulator.update_inputs(snapshot, clock)
        return self.simulator.pump(snapshot, clock)

    def trusted_stop(self, clock: Clock) -> Decision:
        event = self._event(EventKind.SAFETY_STOP, clock)
        return self.simulator.emergency(
            event,
            self.snapshot(clock),
            clock,
            proof=self.simulator.authority.attest(event),
        )

    def emergency(
        self, event: ControlEvent, clock: Clock, proof: FakeProof | None = None
    ) -> Decision:
        return self.simulator.emergency(event, self.snapshot(clock), clock, proof=proof)

    def revoke(self, identity: str, clock: Clock) -> None:
        self.client.revoke(identity)
        self.trusted_stop(clock)

    def save(
        self, request: SaveRequest, session: FakeSession, clock: Clock
    ) -> APIReceipt:
        if not self.client.permits(session, "admin"):
            return APIReceipt(
                request.identity,
                "denied",
                self._config_revision,
                None,
                "admin_required",
            )
        self.trusted_stop(clock)
        try:
            current = self.simulator.store.view()
        except StoreFailure:
            return APIReceipt(
                request.identity,
                "unavailable",
                self._config_revision,
                None,
                "critical_store_unavailable",
            )
        if current.revision != request.expected_revision:
            return APIReceipt(
                request.identity,
                "conflict",
                current.policy.config_revision,
                None,
                "stale_revision",
            )
        try:
            flushed = self.simulator.flush_audit()
            stopped = self.simulator.store.view()
            if (
                stopped.revision != current.revision + flushed
                or stopped.policy != current.policy
                or stopped.state != self.simulator.state
            ):
                raise StoreFailure("Concurrent settings/state change")
            saved = self.simulator.store.configure(
                request.policy, stopped.revision, self.simulator.state
            )
            # Recreate only the fake runtime, fenced and unreconciled; no implicit restart HEAT.
            old = self.simulator
            old.close()
            self._settings_generation += 1
            self.simulator = Simulator(
                old.store,
                old.actuator,
                old.state.boot_id + f".settings{self._settings_generation}",
            )
            actual = self.simulator.store.view()
            if actual.policy != request.policy:
                raise StoreFailure("Readback mismatch")
            self._config_revision = actual.policy.config_revision
            self._armed = actual.policy.armed
            return APIReceipt(
                request.identity,
                "saved",
                saved.policy.config_revision,
                actual.policy.config_revision,
                "durable_fake_settings",
            )
        except StoreFailure:
            return APIReceipt(
                request.identity,
                "conflict",
                current.policy.config_revision,
                None,
                "not_saved",
            )

    def resume_fan(self, session: FakeSession) -> None:
        require(
            self.client.permits(session, "control"),
            "Fake fan control permission required",
        )
        self._fan_manual = False

    def fan_demand(
        self,
        previous: FanState,
        clock: Clock,
        policy: FanPolicy,
        *,
        mode: str,
        night: bool,
        night_request: bool,
        permitted: bool,
    ) -> FanDemand:
        self.adapter.connection(self.client.generation)
        room = self.adapter.select("room", clock, connected=self.client.connected)
        fireplace = self.adapter.select(
            "fireplace", clock, connected=self.client.connected
        )
        grid = self.adapter.select("grid", clock, connected=self.client.connected)
        valid = (
            room is not None
            and fireplace is not None
            and room.value is not None
            and fireplace.value is not None
        )
        delta = (
            float(fireplace.value) - float(room.value)
            if valid
            and fireplace is not None
            and room is not None
            and fireplace.value is not None
            and room.value is not None
            else None
        )
        return reduce_fan(
            previous,
            clock.utc,
            delta,
            valid=valid,
            grid=grid.value if grid and type(grid.value) is bool else None,
            armed=self._armed,
            permitted=permitted and self.client.permits(self.operator, "control"),
            mode="manual" if self._fan_manual and mode != "stop" else mode,
            night=night,
            night_request=night_request,
            policy=policy,
        )

    def recovery(
        self,
        request: RecoveryRequest,
        stream: str,
        backup_root: Path,
        session: FakeSession,
        *,
        dry_run: bool,
    ) -> RecoveryReceipt:
        require(self.client.permits(session, "admin"), "Fake admin permission required")
        return self.evidence.recover(
            request, stream, backup_root, dry_run=dry_run, approved=not dry_run
        )

    def status(self, session: FakeSession, clock: Clock) -> StatusView:
        require(self.client.permits(session, "read"), "Fake read permission required")
        snapshot = self.snapshot(clock)
        stage = None
        intent = self.simulator.state.last_intent
        if intent is not None:
            try:
                stage = self.simulator.store.receipt(intent.intent_id).stage
            except StoreFailure:
                pass
        return StatusView(
            self._sequence,
            self.simulator.state.boot_id,
            self.simulator.state.owner_epoch,
            None,
            self.simulator.state.desired_action,
            self.simulator.state.mode.value,
            snapshot.snapshot_id,
            snapshot.captured_at,
            len(self._pending) + self.client.raw_count - self._raw_frontier,
            self.archive_lost,
            stage,
        )

    def flush_evidence(self) -> int:
        """May fail or block; never called by deliver/emergency/pump."""
        count = 0
        for event in self.client.raw_page(self._raw_frontier):
            try:
                self.evidence.append(
                    record(event.identity, event, event.received_at, event.entity)
                )
            except EvidenceFailure:
                return count
            self._raw_frontier += 1
            count += 1
        while self._pending:
            try:
                self.evidence.append(self._pending[0])
            except EvidenceFailure:
                break
            self._pending.pop(0)
            count += 1
        return count
