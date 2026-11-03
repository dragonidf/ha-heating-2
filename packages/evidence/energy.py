"""Pure timestamped energy math. No current-reading retrospective energy."""

from hashlib import sha256
from dataclasses import replace
from datetime import datetime, timedelta, tzinfo
from packages.contracts import Reading, QualityStatus, SourceKind, power_to_kilowatts
from packages.contracts.models import number, require, ContractError
from packages.offline.contracts import (
    PowerPoint,
    CounterPoint,
    EnergySlice,
    BalanceTopology,
    Tariff,
    CostSummary,
)


def derive_power(
    topology: BalanceTopology,
    readings: tuple[Reading, ...],
    at: float,
    identity: str,
    stream: str,
) -> PowerPoint:
    number(at, nonnegative=True)
    bindings = (topology.inlet, *topology.subtract, topology.grid)
    by_source = {r.source_id: r for r in readings}

    def unknown(reason: str, raw: float | None = None) -> PowerPoint:
        return PowerPoint(
            identity,
            stream,
            at,
            at,
            None,
            "unknown",
            tuple(b.physical_id for b in bindings),
            reason,
            raw,
        )

    if not topology.qualified:
        return unknown("topology_unqualified")
    if len(by_source) != len(readings):
        return unknown("duplicate_source")
    selected = []
    for b in bindings:
        r = by_source.get(b.source_id)
        if (
            r is None
            or r.physical_id != b.physical_id
            or r.unit != b.unit
            or r.value is None
            or r.quality.status is not QualityStatus.VALID
            or r.provenance.kind in (SourceKind.HELD, SourceKind.FORECAST)
            or not 0 <= at - r.observed_at <= min(b.max_age_s, topology.max_age_s)
            or not r.observed_at <= r.received_at <= at
            or r.quality.age_s > topology.max_age_s
        ):
            return unknown("missing_or_stale_component")
        selected.append(r)
    footprint: set[str] = set()
    for r in selected:
        components = {r.physical_id, *r.provenance.components}
        if components & footprint:
            return unknown("source_dependency_overlap")
        if r.provenance.kind is SourceKind.DERIVED and not r.provenance.components:
            return unknown("derived_lineage_missing")
        footprint |= components
    sources = tuple(
        sorted(
            footprint
            | {r.source_id for r in selected}
            | {e for r in selected for e in r.evidence_ids}
        )
    )
    if len(sources) > 64:
        return unknown("source_lineage_capacity")
    if (
        max(r.observed_at for r in selected) - min(r.observed_at for r in selected)
        > topology.max_skew_s
    ):
        return unknown("component_skew")
    if not selected[-1].signed:
        return unknown("grid_direction_unqualified")
    values = [power_to_kilowatts(r) for r in selected]
    require(all(v is not None for v in values), "Invalid balance units")
    numeric = [float(v) for v in values if v is not None]
    raw = numeric[0] - sum(numeric[1:])
    if raw < 0 or raw > topology.max_kw:
        return unknown("balance_conflict", raw * 1000)
    return PowerPoint(
        identity,
        stream,
        at,
        at,
        raw,
        "derived",
        sources,
        "inlet_minus_loads_minus_signed_grid",
        raw * 1000,
    )


def _slice(
    stream: str,
    continuity: str,
    start: float,
    end: float,
    p: PowerPoint | None,
    reason: str,
) -> EnergySlice:
    known = p is not None and p.kw is not None
    identity = sha256(
        repr((stream, continuity, start, end, p, reason)).encode()
    ).hexdigest()
    return EnergySlice(
        identity,
        stream,
        continuity,
        start,
        end,
        (
            ("derived" if p.category == "confirmed" else p.category)
            if known and p is not None
            else "unknown"
        ),
        (
            p.kw * (end - start) / 3600
            if known and p is not None and p.kw is not None
            else None
        ),
        p.sources if p is not None else (),
        p.method if known and p is not None else reason,
    )


def integrate(
    points: tuple[PowerPoint, ...],
    start: float,
    end: float,
    continuity: str,
    *,
    hold_s: float = 45,
    stream: str | None = None
) -> tuple[EnergySlice, ...]:
    number(start, nonnegative=True)
    number(end)
    number(hold_s, nonnegative=True)
    require(
        start < end and hold_s <= 45 and type(points) is tuple and len(points) <= 10000,
        "Invalid integration scope",
    )
    stream = stream or (points[0].stream if points else None)
    if stream is None:
        raise ContractError("Missing continuity stream")
    require(all(p.stream == stream for p in points), "Mixed continuity stream")
    times = sorted(
        {
            start,
            end,
            *[p.at for p in points if start < p.at < end],
            *[p.at + hold_s for p in points if start < p.at + hold_s < end],
        }
    )
    by_time: dict[float, list[PowerPoint]] = {}
    for p in points:
        by_time.setdefault(p.at, []).append(p)
    prior = sorted(t for t in by_time if t <= start)
    current = prior[-1] if prior else None
    result = []
    for a, b in zip(times, times[1:]):
        if a in by_time:
            current = a
        sample = None
        reason = "missing_or_hold_gap"
        if current is not None and a - current < hold_s:
            group = by_time[current]
            signatures = {
                (p.kw, p.category, p.sources, p.method, p.raw_w) for p in group
            }
            if len(signatures) == 1:
                sample = min(group, key=lambda p: p.identity)
            else:
                reason = "conflicting_same_time"
        result.append(_slice(stream, continuity, a, b, sample, reason))
    return tuple(result)


def counter_delta(
    left: CounterPoint, right: CounterPoint, max_kw: float, continuity: str
) -> EnergySlice:
    number(max_kw, nonnegative=True)
    require(
        left.stream == right.stream
        and left.source == right.source
        and left.at < right.at,
        "Counter continuity mismatch",
    )
    delta = right.kwh - left.kwh
    valid = 0 <= delta <= max_kw * (right.at - left.at) / 3600 + 1e-9
    reason = (
        "counter_delta" if valid else "counter_reset" if delta < 0 else "counter_jump"
    )
    identity = sha256(repr((left, right, continuity)).encode()).hexdigest()
    return EnergySlice(
        identity,
        left.stream,
        continuity,
        left.at,
        right.at,
        "confirmed" if valid else "unknown",
        delta if valid else None,
        (left.source,),
        reason,
    )


def stage_estimate(
    points: tuple[PowerPoint, ...],
    stages: tuple[float, ...],
    minimum_s: float,
    tolerance_kw: float,
) -> float | None:
    number(minimum_s, nonnegative=True)
    number(tolerance_kw, nonnegative=True)
    require(
        type(points) is tuple and type(stages) is tuple and len(stages) <= 8,
        "Invalid stage assumptions",
    )
    for v in stages:
        number(v, nonnegative=True)
    if len(points) < 2 or not stages:
        return None
    ordered = sorted(points, key=lambda p: p.at)
    if ordered[-1].at - ordered[0].at < minimum_s or any(
        b.at - a.at > 45 or b.at <= a.at for a, b in zip(ordered, ordered[1:])
    ):
        return None
    if any(p.kw is None or p.category not in ("confirmed", "derived") for p in ordered):
        return None
    for stage in stages:
        if all(p.kw is not None and abs(p.kw - stage) <= tolerance_kw for p in ordered):
            return stage
    return None


def dated_cost(
    slices: tuple[EnergySlice, ...], tariffs: tuple[Tariff, ...]
) -> CostSummary:
    """Dated cost: estimated energy or counter prorating never becomes an actual bill."""
    ordered = sorted(tariffs, key=lambda t: t.start)
    require(
        len({t.currency for t in tariffs}) <= 1
        and all(a.end <= b.start for a, b in zip(ordered, ordered[1:])),
        "Conflicting tariffs",
    )
    known = estimated = unpriced = unknown = 0.0
    for s in slices:
        if s.kwh is None:
            unknown += s.end - s.start
            continue
        covered = 0.0
        for t in ordered:
            seconds = max(0, min(t.end, s.end) - max(t.start, s.start))
            energy = s.kwh * seconds / (s.end - s.start)
            value = energy * t.per_kwh
            if (
                s.category in ("estimated", "recovered")
                or s.method == "counter_delta"
                and 0 < seconds < s.end - s.start
            ):
                estimated += value
            else:
                known += value
            covered += energy
        unpriced += max(0, s.kwh - covered)
    return CostSummary(
        known, estimated, unpriced, unknown, ordered[0].currency if ordered else None
    )


def clip(s: EnergySlice, start: float, end: float) -> EnergySlice | None:
    number(start)
    number(end)
    require(start < end, "Invalid energy query interval")
    a = max(s.start, start)
    b = min(s.end, end)
    if a >= b:
        return None
    partial = (a, b) != (s.start, s.end)
    estimated = partial and (s.method == "counter_delta" or s.category == "recovered")
    return replace(
        s,
        identity=sha256(repr((s.identity, a, b)).encode()).hexdigest(),
        start=a,
        end=b,
        kwh=s.kwh * (b - a) / (s.end - s.start) if s.kwh is not None else None,
        category="estimated" if estimated else s.category,
        method="prorated_estimate" if estimated else s.method,
    )


def local_day_slices(
    slices: tuple[EnergySlice, ...], zone: tzinfo
) -> tuple[EnergySlice, ...]:
    result = []
    for s in slices:
        at = s.start
        while at < s.end:
            local = datetime.fromtimestamp(at, zone)
            midnight = datetime.combine(
                local.date() + timedelta(days=1), datetime.min.time(), tzinfo=zone
            ).timestamp()
            end = min(s.end, midnight)
            require(end > at, "Invalid local-day progression")
            part = clip(s, at, end)
            if part is not None:
                result.append(part)
            at = end
    return tuple(result)
