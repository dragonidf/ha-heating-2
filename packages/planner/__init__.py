"""Bounded offline proposals and immutable forecast evidence; no actuation path."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, tzinfo
from hashlib import sha256
from typing import Callable
from packages.contracts import (
    Plan,
    PlanSegment,
    Revisions,
    TimeWindow,
    Reading,
    Unit,
    QualityStatus,
    SourceKind,
)
from packages.contracts.models import number, require, counter, digest, text
from packages.thermal import Coefficients, Forcing, Interval, ThermalState, step


@dataclass(frozen=True, slots=True)
class Stamp:
    input_hash: str
    revisions: Revisions
    boot_id: str
    owner_epoch: int
    grid_epoch: int

    def __post_init__(self) -> None:
        digest(self.input_hash)
        text(self.boot_id)
        counter(self.owner_epoch)
        counter(self.grid_epoch)
        require(isinstance(self.revisions, Revisions), "Invalid revisions")


@dataclass(frozen=True, slots=True)
class Forecast:
    issue: float
    received: float
    horizon: TimeWindow
    source_id: str

    def __post_init__(self) -> None:
        number(self.issue, nonnegative=True)
        number(self.received, nonnegative=True)
        text(self.source_id)
        require(
            self.issue <= self.received and isinstance(self.horizon, TimeWindow),
            "Invalid forecast provenance",
        )


@dataclass(frozen=True, slots=True)
class Slot:
    window: TimeWindow
    forcing: Forcing
    grid: str
    target: float
    upper: float
    price: float | None

    def __post_init__(self) -> None:
        require(
            isinstance(self.window, TimeWindow) and isinstance(self.forcing, Forcing),
            "Invalid slot",
        )
        require(
            self.grid in ("normal", "scheduled_off", "emergency", "unknown"),
            "Invalid grid forecast",
        )
        number(self.target)
        number(self.upper)
        require(self.target < self.upper, "Invalid comfort band")
        if self.price is not None:
            number(self.price, nonnegative=True)
        require(
            0 < self.window.end - self.window.start <= 300,
            "Planning resolution exceeded",
        )


@dataclass(frozen=True, slots=True)
class Morning:
    window: TimeWindow
    advance_s: float
    confirmed_until: float | None
    confirmed_s: float
    confirmed_valid: bool

    def __post_init__(self) -> None:
        number(self.advance_s, nonnegative=True)
        require(self.advance_s <= 10800, "Advance exceeds scope")
        number(self.confirmed_s, nonnegative=True)
        require(type(self.confirmed_valid) is bool, "Invalid continuity")
        if self.confirmed_until is not None:
            number(self.confirmed_until, nonnegative=True)


def cycle(now: datetime) -> tuple[str, TimeWindow]:
    require(now.tzinfo is not None, "Aware calendar required")
    day = now.date() if now.hour < 7 else now.date() + timedelta(days=1)
    end = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo) + timedelta(
        hours=7
    )
    begin = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo) + timedelta(
        hours=5
    )
    return day.isoformat(), TimeWindow(start=begin.timestamp(), end=end.timestamp())


@dataclass(frozen=True, slots=True)
class Request:
    stamp: Stamp
    state: ThermalState
    model: Coefficients
    slots: tuple[Slot, ...]
    weather: Forecast
    allowed: tuple[TimeWindow, ...]
    morning: Morning
    stages_kw: tuple[float, ...]
    stored_upper: float
    armed: bool
    manual: bool
    actual_grid: bool | None
    budget_kwh: float | None
    known_spent_kwh: float
    spend_complete: bool
    return_probe: Reading | None
    return_upper_c: float | None
    return_max_age_s: float
    limits_qualified: bool
    state_max_age_s: float
    beam: int = 4
    max_work: int = 50000
    forecast_max_age_s: float = 21600

    def __post_init__(self) -> None:
        require(
            type(self.slots) is tuple and 0 < len(self.slots) <= 864, "Invalid horizon"
        )
        require(
            type(self.allowed) is tuple
            and len(self.allowed) <= 256
            and all(isinstance(w, TimeWindow) for w in self.allowed),
            "Invalid windows",
        )
        require(
            type(self.stages_kw) is tuple and len(self.stages_kw) <= 4,
            "Invalid scenario list",
        )
        number(self.forecast_max_age_s, nonnegative=True)
        require(
            all(
                type(v) is bool
                for v in (
                    self.armed,
                    self.manual,
                    self.spend_complete,
                    self.limits_qualified,
                )
            ),
            "Invalid permissions",
        )
        require(
            self.actual_grid is None or type(self.actual_grid) is bool,
            "Invalid actual grid",
        )
        number(self.state_max_age_s, nonnegative=True)
        number(self.stored_upper)
        number(self.known_spent_kwh, nonnegative=True)
        number(self.return_max_age_s, nonnegative=True)
        if self.return_upper_c is not None:
            number(self.return_upper_c)
        require(
            self.return_probe is None
            or isinstance(self.return_probe, Reading)
            and self.return_probe.unit is Unit.CELSIUS,
            "Invalid return probe",
        )
        if self.budget_kwh is not None:
            number(self.budget_kwh, nonnegative=True)
        for power in self.stages_kw:
            number(power)
            require(0 < power <= 100, "Invalid synthetic power")
        require(
            type(self.beam) is int
            and 1 <= self.beam <= 16
            and type(self.max_work) is int
            and 1 <= self.max_work <= 200000,
            "Invalid search bound",
        )
        require(
            self.model.revision == self.stamp.revisions.model, "Model stamp mismatch"
        )
        previous = self.state.at
        for slot in self.slots:
            require(slot.window.start == previous, "Non-contiguous planning inputs")
            previous = slot.window.end
        require(previous - self.state.at <= 259200, "72h cap exceeded")


@dataclass(frozen=True, slots=True)
class Proposal:
    stamp: Stamp
    status: str
    segments: tuple[PlanSegment, ...]
    trajectory: tuple[ThermalState, ...]
    power_kw: float | None
    energy_kwh: float
    deficit_degree_hours: float
    projected_overrun: float | None
    budget_uncertain: bool
    morning_s: float
    reason: str
    work: int
    changes: tuple[str, ...] = ()
    retention_key: str | None = None
    morning_required: bool = False
    segment_reasons: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        require(
            self.status
            in ("BLOCKED", "SEARCH_EXHAUSTED", "SHORTFALL", "CONDITIONAL", "PROPOSAL"),
            "Invalid proposal status",
        )
        require(
            type(self.segments) is tuple
            and len(self.segments) <= 256
            and type(self.trajectory) is tuple
            and len(self.trajectory) <= 864,
            "Invalid proposal capacity",
        )
        for v in (self.energy_kwh, self.deficit_degree_hours, self.morning_s):
            number(v, nonnegative=True)
        if self.projected_overrun is not None:
            number(self.projected_overrun, nonnegative=True)
        if self.power_kw is not None:
            number(self.power_kw, nonnegative=True)
        counter(self.work)
        if self.retention_key is not None:
            digest(self.retention_key)
        require(type(self.morning_required) is bool, "Invalid morning requirement")
        require(
            type(self.segment_reasons) is tuple
            and (
                not self.segment_reasons
                or len(self.segment_reasons) == len(self.segments)
            ),
            "Invalid segment provenance",
        )
        for segment, reasons in zip(self.segments, self.segment_reasons):
            require(
                type(reasons) is tuple and segment.conditional == bool(reasons),
                "Invalid segment reasons",
            )
            for reason in reasons:
                text(reason)
        text(self.reason)
        require(
            type(self.budget_uncertain) is bool and type(self.changes) is tuple,
            "Invalid proposal evidence",
        )
        for cause in self.changes:
            text(cause)


@dataclass(frozen=True, slots=True)
class _Node:
    state: ThermalState
    path: tuple[bool, ...]
    energy: float
    cost: float
    unknown_cost_kwh: float
    deficit: float
    run_s: float
    morning_s: float
    segment_count: int


def _weather_current(req: Request) -> bool:
    return (
        req.weather.received <= req.state.at
        and 0 <= req.state.at - req.weather.issue <= req.forecast_max_age_s
    )


def _retention_key(req: Request) -> str:
    # Publication-only refreshes may differ; every objective/safety input has zero tolerance.
    semantic = replace(
        req,
        stamp=replace(req.stamp, input_hash="0" * 64),
        weather=replace(req.weather, issue=0, received=0),
    )
    return sha256(repr((semantic, _weather_current(req))).encode()).hexdigest()


def _return_ready(req: Request) -> bool:
    probe = req.return_probe
    return (
        probe is not None
        and probe.value is not None
        and req.return_upper_c is not None
        and probe.quality.status is QualityStatus.VALID
        and probe.provenance.kind not in (SourceKind.HELD, SourceKind.FORECAST)
        and 0 <= req.state.at - probe.observed_at <= req.return_max_age_s
        and probe.observed_at <= probe.received_at <= req.state.at
        and probe.quality.age_s <= req.return_max_age_s
        and float(probe.value) < req.return_upper_c
    )


def _state_ready(req: Request) -> bool:
    return (
        not req.state.estimated
        and req.state.at - req.state.observed_at <= req.state_max_age_s
    )


def _eligible(req: Request, slot: Slot, index: int) -> bool:
    return (
        req.armed
        and not req.manual
        and (
            index > 0
            or req.actual_grid is True
            and _state_ready(req)
            and _return_ready(req)
        )
        and slot.grid not in ("scheduled_off", "emergency")
        and any(
            w.start <= slot.window.start and slot.window.end <= w.end
            for w in req.allowed
        )
    )


def _conditional_reasons(
    req: Request, slot: Slot, state: ThermalState
) -> tuple[str, ...]:
    conditions = (
        (slot.window.start > req.state.at, "future_execution_unverified"),
        (req.actual_grid is not True, "actual_grid_unverified"),
        (not _return_ready(req), "current_return_unverified"),
        (not _state_ready(req), "current_state_unverified"),
        (slot.grid == "unknown", "grid_forecast_unknown"),
        (not slot.forcing.quality_valid or state.estimated, "thermal_inputs_uncertain"),
        (
            not req.weather.horizon.start
            <= slot.window.start
            < slot.window.end
            <= req.weather.horizon.end,
            "weather_horizon_missing",
        ),
        (not _weather_current(req), "weather_not_current"),
        (slot.price is None, "price_unknown"),
        (req.model.calibration != "SYNTHETIC_QUALIFIED", "model_not_qualified"),
        (req.slots[-1].window.end < req.morning.window.end, "morning_horizon_missing"),
    )
    return tuple(reason for condition, reason in conditions if condition)


def solve(
    req: Request,
    cancelled: Callable[[], bool] = lambda: False,
    *,
    _fixed: tuple[bool, ...] | None = None
) -> Proposal:
    """Finite beam optimization; exhaustion is not a physical infeasibility proof."""
    work = 0
    empty = Proposal(
        req.stamp,
        "BLOCKED",
        (),
        (),
        None,
        0,
        0,
        None,
        not req.spend_complete,
        0,
        "permissions_or_data",
        0,
    )
    if not req.armed or req.manual:
        return empty
    if not req.limits_qualified or req.return_upper_c is None:
        return replace(empty, reason="limits_unqualified")
    if not req.stages_kw:
        return replace(empty, reason="power_unknown")
    if (
        req.state.room.high >= req.slots[0].upper
        or req.state.stored.high >= req.stored_upper
    ):
        return Proposal(
            req.stamp, "BLOCKED", (), (), None, 0, 0, None, True, 0, "overheat", 0
        )
    coast = req.state
    coasts = []
    need = (
        req.state.at == req.morning.window.end and coast.room.low < req.slots[0].target
    )
    reserve_end = next(
        (
            slot.window.start
            for i, slot in enumerate(req.slots)
            if slot.window.start >= req.morning.window.end
            and slot.grid == "normal"
            and _eligible(req, slot, i)
        ),
        req.slots[-1].window.end,
    )
    for slot in req.slots:
        work += 1
        if work > req.max_work or cancelled():
            return replace(
                empty,
                status="SEARCH_EXHAUSTED",
                reason="cancelled_or_work_cap",
                work=work,
            )
        forcing = replace(slot.forcing, power_kw=Interval(0, 0))
        if slot.window.start < req.morning.window.end < slot.window.end:
            work += 1
            if work > req.max_work or cancelled():
                return replace(
                    empty,
                    status="SEARCH_EXHAUSTED",
                    reason="cancelled_or_work_cap",
                    work=work,
                )
            deadline = step(
                coast, forcing, req.model, req.morning.window.end - slot.window.start
            )
            need |= deadline.room.low < slot.target
        coast = step(coast, forcing, req.model, slot.window.end - slot.window.start)
        coasts.append(coast)
        if (
            req.morning.window.end <= slot.window.end <= reserve_end
            and coast.room.low < slot.target
        ):
            need = True
    results = []
    advance = (
        req.morning.advance_s
        if any(
            s.grid in ("scheduled_off", "emergency")
            and s.window.start < req.morning.window.end
            and s.window.end > req.morning.window.start
            for s in req.slots
        )
        else 0
    )
    for power in req.stages_kw:
        credit = (
            req.morning.confirmed_s
            if (
                req.morning.confirmed_valid
                and req.morning.confirmed_until == req.state.at
                and req.morning.window.start - advance
                <= req.state.at
                <= req.morning.window.end
                and req.morning.confirmed_s
                <= req.state.at - (req.morning.window.start - advance)
            )
            else 0
        )
        nodes = [_Node(req.state, (), 0, 0, 0, 0, credit, credit, 0)]
        for index, slot in enumerate(req.slots):
            following = []
            duration = slot.window.end - slot.window.start
            for node in nodes:
                for on in ((_fixed[index],) if _fixed is not None else (False, True)):
                    work += 1
                    if work > req.max_work or cancelled():
                        return Proposal(
                            req.stamp,
                            "SEARCH_EXHAUSTED",
                            (),
                            (),
                            None,
                            0,
                            0,
                            None,
                            True,
                            0,
                            "cancelled_or_work_cap",
                            work,
                        )
                    segment_count = node.segment_count + int(
                        on and (not node.path or not node.path[-1])
                    )
                    if segment_count > 255:
                        continue
                    if on and not _eligible(req, slot, index):
                        continue
                    forcing = Forcing(
                        slot.forcing.outside,
                        Interval(power, power) if on else Interval(0, 0),
                        slot.forcing.fire_delta,
                        slot.forcing.ventilation_loss,
                        slot.forcing.quality_valid,
                        slot.forcing.external_gain,
                    )
                    state = step(node.state, forcing, req.model, duration)
                    if on and (
                        state.room.high >= slot.upper
                        or state.stored.high >= req.stored_upper
                    ):
                        continue
                    in_morning = (
                        req.morning.window.start - advance <= slot.window.start
                        and slot.window.end <= req.morning.window.end
                    )
                    run = node.run_s + duration if on and in_morning else 0
                    morning = max(node.morning_s, run)
                    energy = node.energy + (power * duration / 3600 if on else 0)
                    target = slot.target
                    # A safe natural warm-up to 07:00 is not a boiler comfort deficit.
                    if (
                        not need
                        and req.slots[-1].window.end >= req.morning.window.end
                        and req.morning.window.start
                        <= slot.window.start
                        < slot.window.end
                        <= req.morning.window.end
                    ):
                        target = min(target, coasts[index].room.low)
                    deficit = (
                        node.deficit + max(0, target - state.room.low) * duration / 3600
                    )
                    following.append(
                        _Node(
                            state,
                            node.path + (on,),
                            energy,
                            node.cost
                            + (
                                power * duration / 3600 * slot.price
                                if on and slot.price is not None
                                else 0
                            ),
                            node.unknown_cost_kwh
                            + (
                                power * duration / 3600
                                if on and slot.price is None
                                else 0
                            ),
                            deficit,
                            run,
                            morning,
                            segment_count,
                        )
                    )

            def rank(n: _Node) -> tuple[float, ...]:
                missing = (
                    max(0, 1800 - n.morning_s)
                    if need and slot.window.end >= req.morning.window.end
                    else 0
                )
                over = (
                    max(0, n.energy + req.known_spent_kwh - req.budget_kwh)
                    if req.budget_kwh is not None
                    else 0
                )
                # Reserve viable continuous morning prefixes before deadline; safety already filtered.
                progress = (
                    -min(n.run_s, 1800)
                    if need and slot.window.end <= req.morning.window.end
                    else 0
                )
                return (
                    missing,
                    n.deficit,
                    progress,
                    over,
                    n.unknown_cost_kwh,
                    n.cost,
                    n.energy,
                )

            if not following:
                return replace(empty, reason="unsafe_retained", work=work)
            nodes = sorted(following, key=rank)[: req.beam]
        best = min(
            nodes,
            key=lambda n: (
                max(0, 1800 - n.morning_s) if need else 0,
                n.deficit,
                (
                    max(0, n.energy + req.known_spent_kwh - req.budget_kwh)
                    if req.budget_kwh is not None
                    else 0
                ),
                n.unknown_cost_kwh,
                n.cost,
                n.energy,
            ),
        )
        results.append((best, power))
    best, power = min(
        results,
        key=lambda pair: (
            max(0, 1800 - pair[0].morning_s) if need else 0,
            pair[0].deficit,
            (
                max(0, pair[0].energy + req.known_spent_kwh - req.budget_kwh)
                if req.budget_kwh is not None
                else 0
            ),
            pair[0].unknown_cost_kwh,
            pair[0].cost,
            pair[0].energy,
        ),
    )
    trajectory: list[ThermalState] = []
    state = req.state
    segments: list[PlanSegment] = []
    conditional = False
    segment_reasons: list[tuple[str, ...]] = []
    for slot, on in zip(req.slots, best.path):
        reasons = _conditional_reasons(req, slot, state)
        uncertain = bool(reasons)
        if on:
            conditional |= uncertain
            if (
                segments
                and segments[-1].end == slot.window.start
                and segment_reasons[-1] == reasons
            ):
                old = segments.pop()
                segments.append(
                    PlanSegment(
                        start=old.start, end=slot.window.end, conditional=uncertain
                    )
                )
            else:
                segment_reasons.append(reasons)
                segments.append(
                    PlanSegment(
                        start=slot.window.start,
                        end=slot.window.end,
                        conditional=uncertain,
                    )
                )
        state = step(
            state,
            Forcing(
                slot.forcing.outside,
                Interval(power, power) if on else Interval(0, 0),
                slot.forcing.fire_delta,
                slot.forcing.ventilation_loss,
                slot.forcing.quality_valid,
                slot.forcing.external_gain,
            ),
            req.model,
            slot.window.end - slot.window.start,
        )
        trajectory.append(state)
    if len(segments) > 256:
        return replace(empty, reason="segment_capacity", work=work)
    if any(
        s.room.high >= slot.upper or s.stored.high >= req.stored_upper
        for s, slot in zip(trajectory, req.slots)
    ):
        return replace(empty, reason="external_overheat", work=work)
    short = need and best.morning_s < 1800
    status = (
        "SHORTFALL"
        if short or best.deficit > 0
        else "CONDITIONAL" if conditional else "PROPOSAL"
    )
    return Proposal(
        req.stamp,
        status,
        tuple(segments),
        tuple(trajectory),
        power,
        best.energy,
        best.deficit,
        (
            max(0, best.energy + req.known_spent_kwh - req.budget_kwh)
            if req.budget_kwh is not None
            else None
        ),
        not req.spend_complete,
        best.morning_s,
        (
            "morning_shortfall"
            if short
            else (
                "comfort_shortfall"
                if best.deficit
                else "no_need" if not segments else "candidate_only"
            )
        ),
        work,
        retention_key=_retention_key(req),
        morning_required=need,
        segment_reasons=tuple(segment_reasons),
    )


def bridge(proposal: Proposal, current: Stamp, issued: float, expires: float) -> Plan:
    require(
        proposal.stamp == current
        and proposal.status not in ("BLOCKED", "SEARCH_EXHAUSTED"),
        "Stale/blocked proposal",
    )
    require(bool(proposal.trajectory), "No trajectory")
    require(
        len(proposal.segment_reasons) == len(proposal.segments),
        "Missing segment provenance",
    )
    require(
        all(s.conditional for s in proposal.segments if s.start > issued),
        "Unconditional future heat",
    )
    return Plan(
        plan_id=sha256(repr(proposal).encode()).hexdigest(),
        boot_id=current.boot_id,
        revisions=current.revisions,
        grid_epoch=current.grid_epoch,
        owner_epoch=current.owner_epoch,
        input_hash=current.input_hash,
        issued_at=issued,
        valid_from=issued,
        valid_until=proposal.trajectory[-1].at,
        expires_at=expires,
        segments=proposal.segments,
    )


def retain(previous: Proposal, request: Request) -> bool:
    if replace(
        previous.stamp, input_hash=request.stamp.input_hash
    ) != request.stamp or len(previous.trajectory) != len(request.slots):
        return False
    if previous.retention_key != _retention_key(request):
        return False
    state = request.state
    for i, slot in enumerate(request.slots):
        on = any(
            s.start <= slot.window.start and slot.window.end <= s.end
            for s in previous.segments
        )
        if on and not _eligible(request, slot, i):
            return False
        kw = previous.power_kw if on else 0
        if kw is None:
            return False
        state = step(
            state,
            Forcing(
                slot.forcing.outside,
                Interval(kw, kw),
                slot.forcing.fire_delta,
                slot.forcing.ventilation_loss,
                slot.forcing.quality_valid,
                slot.forcing.external_gain,
            ),
            request.model,
            slot.window.end - slot.window.start,
        )
        if on and (
            state.room.high >= slot.upper or state.stored.high >= request.stored_upper
        ):
            return False
    return (
        previous.status not in ("BLOCKED", "SEARCH_EXHAUSTED")
        and request.limits_qualified
    )


def replan(
    request: Request,
    previous: Proposal | None = None,
    *,
    material_change: bool = False,
    cancelled: Callable[[], bool] = lambda: False
) -> Proposal:
    if (
        previous is not None
        and not material_change
        and previous.power_kw is not None
        and retain(previous, request)
    ):
        fixed = tuple(
            any(
                s.start <= slot.window.start and slot.window.end <= s.end
                for s in previous.segments
            )
            for slot in request.slots
        )
        replay = solve(
            replace(request, stages_kw=(previous.power_kw,)), cancelled, _fixed=fixed
        )
        if replay.status not in ("BLOCKED", "SEARCH_EXHAUSTED") and (
            replay.status,
            replay.morning_required,
            replay.morning_s,
            replay.deficit_degree_hours,
            replay.energy_kwh,
            replay.projected_overrun,
            replay.budget_uncertain,
            replay.trajectory,
        ) == (
            previous.status,
            previous.morning_required,
            previous.morning_s,
            previous.deficit_degree_hours,
            previous.energy_kwh,
            previous.projected_overrun,
            previous.budget_uncertain,
            previous.trajectory,
        ):
            return replace(
                replay,
                reason="retained_after_current_safety_replay",
                retention_key=_retention_key(request),
            )
    result = solve(request, cancelled)
    if previous is not None:
        causes = tuple(
            name
            for name in (
                "input_hash",
                "revisions",
                "boot_id",
                "owner_epoch",
                "grid_epoch",
            )
            if getattr(previous.stamp, name) != getattr(request.stamp, name)
        )
        return replace(
            result,
            changes=causes
            + (
                ("material_inputs_changed",)
                if material_change
                else ("current_safety_replay_failed",)
            ),
        )
    return result


@dataclass(frozen=True, slots=True)
class Curve:
    identity: str
    issued: float
    points: tuple[tuple[float, Interval], ...]
    input_hash: str
    model_revision: int = 0
    plan_id: str = "missing"
    source_issued: tuple[float, ...] = ()

    @property
    def checksum(self) -> str:
        return sha256(repr(self).encode()).hexdigest()

    def __post_init__(self) -> None:
        text(self.identity)
        number(self.issued, nonnegative=True)
        digest(self.input_hash)
        counter(self.model_revision)
        text(self.plan_id)
        require(
            type(self.source_issued) is tuple and len(self.source_issued) <= 32,
            "Invalid source provenance",
        )
        for issue in self.source_issued:
            number(issue)
            require(issue <= self.issued, "Forecast source leakage")
        require(
            type(self.points) is tuple and 0 < len(self.points) <= 865, "Invalid curve"
        )
        previous = self.issued
        for at, value in self.points:
            number(at)
            require(
                at >= previous and isinstance(value, Interval), "Invalid curve point"
            )
            previous = at


@dataclass(frozen=True, slots=True)
class References:
    cycle_id: str
    initial: Curve
    prestart: Curve
    original_12h: Curve | None
    latest: Curve

    def __post_init__(self) -> None:
        text(self.cycle_id)
        require(
            all(
                isinstance(c, Curve) for c in (self.initial, self.prestart, self.latest)
            ),
            "Invalid references",
        )
        require(
            self.original_12h is None or isinstance(self.original_12h, Curve),
            "Invalid original",
        )


def original(curves: tuple[Curve, ...], reference: float) -> Curve | None:
    eligible = [
        c
        for c in curves
        if c.issued <= reference - 43200
        and c.points[0][0] <= reference <= c.points[-1][0]
    ]
    return max(eligible, key=lambda c: c.issued) if eligible else None


def refresh(refs: References, latest: Curve) -> References:
    require(latest.issued >= refs.latest.issued, "Cannot rewrite estimate backwards")
    return References(
        refs.cycle_id, refs.initial, refs.prestart, refs.original_12h, latest
    )
