"""Offline fitting and immutable champion/challenger qualification; no auto-apply."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo
from typing import Literal
from math import ulp
from packages.contracts.models import number, require, text, counter
from packages.thermal import Coefficients, Forcing, ThermalState, step

HORIZONS = (1, 3, 6, 12, 24, 36, 48)


@dataclass(frozen=True, slots=True)
class Transition:
    local_date: str
    at: float
    end: float
    room: float
    stored: float
    outside: float
    power_kw: float
    fire_delta: float
    next_room: float
    next_stored: float
    qualified: bool

    def __post_init__(self) -> None:
        text(self.local_date)
        for v in (
            self.at,
            self.end,
            self.room,
            self.stored,
            self.outside,
            self.power_kw,
            self.fire_delta,
            self.next_room,
            self.next_stored,
        ):
            number(v)
        require(
            0 < self.end - self.at <= 300
            and self.power_kw >= 0
            and self.fire_delta >= 0
            and type(self.qualified) is bool,
            "Invalid training transition",
        )


def _regression(
    rows: tuple[tuple[tuple[float, ...], float], ...], prior: tuple[float, ...]
) -> tuple[float, ...]:
    size = len(prior)
    ridge = 1e-6
    a = [
        [
            sum(x[i] * x[j] for x, _ in rows) + (ridge if i == j else 0)
            for j in range(size)
        ]
        for i in range(size)
    ]
    b = [sum(x[i] * y for x, y in rows) + ridge * prior[i] for i in range(size)]
    for i in range(size):
        pivot = max(range(i, size), key=lambda k: abs(a[k][i]))
        a[i], a[pivot] = a[pivot], a[i]
        b[i], b[pivot] = b[pivot], b[i]
        div = a[i][i]
        require(abs(div) > 1e-15, "Unidentifiable fit")
        for j in range(i, size):
            a[i][j] /= div
        b[i] /= div
        for k in range(size):
            if k == i:
                continue
            factor = a[k][i]
            for j in range(i, size):
                a[k][j] -= factor * a[i][j]
            b[k] -= factor * b[i]
    return tuple(b)


def fit(samples: tuple[Transition, ...], champion: Coefficients) -> Coefficients:
    require(
        type(samples) is tuple
        and 0 < len(samples) <= 100000
        and all(s.qualified for s in samples),
        "Unqualified fit data",
    )
    room = []
    stored = []
    for s in samples:
        hours = (s.end - s.at) / 3600
        room.append(
            (
                (s.stored - s.room, -(s.room - s.outside), s.fire_delta),
                (s.next_room - s.room) / hours,
            )
        )
        stored.append(
            ((s.power_kw, -(s.stored - s.room)), (s.next_stored - s.stored) / hours)
        )
    fa, loss, fire = _regression(
        tuple(room), (champion.floor_air, champion.room_loss, champion.fire_gain)
    )
    gain, decay = _regression(tuple(stored), (champion.heat_gain, champion.floor_decay))
    return Coefficients(fa, loss, decay, gain, fire, champion.revision + 1)


def stage(
    identity: str,
    samples: tuple[Transition, ...],
    champion: Coefficients,
    daily_baseline: Coefficients,
    timezone: tzinfo,
    source_ids: tuple[str, ...],
) -> "Candidate":
    require(
        all(
            s.local_date == datetime.fromtimestamp(s.at, timezone).date().isoformat()
            for s in samples
        ),
        "Invalid training dates",
    )
    return Candidate(
        identity,
        champion.revision,
        fit(samples, champion),
        tuple(sorted({s.local_date for s in samples})),
        max(s.end for s in samples),
        source_ids,
        champion,
        daily_baseline,
    )


@dataclass(frozen=True, slots=True)
class ValidationPoint:
    day: str
    origin: float
    target: float
    available_at: float
    actual: float
    champion: float
    candidate: float
    regime: str
    qualified: bool

    def __post_init__(self) -> None:
        text(self.day)
        text(self.regime)
        for v in (
            self.origin,
            self.target,
            self.available_at,
            self.actual,
            self.champion,
            self.candidate,
        ):
            number(v)
        require(
            self.target > self.origin
            and self.available_at >= self.target
            and type(self.qualified) is bool,
            "Invalid validation point",
        )


@dataclass(frozen=True, slots=True)
class Metric:
    hours: int
    regime: str
    days: int
    count: int
    candidate_mae: float
    champion_mae: float
    candidate_under: float
    champion_under: float


@dataclass(frozen=True, slots=True)
class Candidate:
    identity: str
    parent_revision: int
    coefficients: Coefficients
    train_days: tuple[str, ...]
    train_end: float
    source_ids: tuple[str, ...]
    parent: Coefficients
    daily_baseline: Coefficients

    def __post_init__(self) -> None:
        text(self.identity)
        counter(self.parent_revision)
        number(self.train_end)
        require(
            type(self.train_days) is tuple
            and len(set(self.train_days)) == len(self.train_days),
            "Invalid training split",
        )
        require(
            type(self.source_ids) is tuple and bool(self.source_ids),
            "Missing training lineage",
        )
        for v in self.train_days + self.source_ids:
            text(v)
        for day in self.train_days:
            try:
                date.fromisoformat(day)
            except ValueError:
                require(False, "Invalid training date")
        require(
            self.coefficients.revision == self.parent_revision + 1,
            "Candidate revision mismatch",
        )
        require(
            self.parent.revision == self.parent_revision, "Parent revision mismatch"
        )


@dataclass(frozen=True, slots=True)
class Qualification:
    candidate_id: str
    parent_revision: int
    outcome: Literal["accepted", "pending", "rejected"]
    reason: str
    metrics: tuple[Metric, ...]
    coefficients: Coefficients


def qualify(
    candidate: Candidate,
    points: tuple[ValidationPoint, ...],
    required_regimes: tuple[str, ...],
    as_of: float,
    timezone: tzinfo,
) -> Qualification:
    number(as_of)
    require(
        type(required_regimes) is tuple
        and len(set(required_regimes)) == len(required_regimes),
        "Invalid regime partition",
    )
    require(
        type(points) is tuple and len(points) <= 100000, "Validation capacity exceeded"
    )

    def result(
        outcome: Literal["accepted", "pending", "rejected"],
        reason: str,
        metrics: tuple[Metric, ...] = (),
    ) -> Qualification:
        return Qualification(
            candidate.identity,
            candidate.parent_revision,
            outcome,
            reason,
            metrics,
            candidate.coefficients,
        )

    if any(
        day > datetime.fromtimestamp(candidate.train_end, timezone).date().isoformat()
        for day in candidate.train_days
    ):
        return result("rejected", "future_training_day")
    if not points or len(candidate.train_days) < 7:
        return result("pending", "insufficient_training")
    for name in ("floor_air", "room_loss", "floor_decay", "heat_gain", "fire_gain"):
        value = getattr(candidate.coefficients, name)
        for base in (candidate.parent, candidate.daily_baseline):
            old = getattr(base, name)
            if (old == 0 and value != 0) or not old * 0.8 - 8 * ulp(
                old
            ) <= value <= old * 1.2 + 8 * ulp(old):
                return result("rejected", "daily_change_bounds")
    if any(
        p.day in candidate.train_days or p.origin < candidate.train_end for p in points
    ):
        return result("rejected", "leakage")
    if any(
        p.day != datetime.fromtimestamp(p.origin, timezone).date().isoformat()
        for p in points
    ):
        return result("rejected", "invalid_day_partition")
    qualified = tuple(p for p in points if p.qualified and p.available_at <= as_of)
    if not required_regimes or len({p.day for p in qualified}) < 3:
        return result("pending", "insufficient_holdout")
    metrics: list[Metric] = []
    for horizon in HORIZONS:
        for regime in required_regimes:
            subset = [
                p
                for p in qualified
                if abs((p.target - p.origin) / 3600 - horizon) < 1e-6
                and p.regime == regime
            ]
            if len({p.day for p in subset}) < 3:
                return result("pending", "missing_horizon_or_regime", tuple(metrics))
            mae = sum(abs(p.actual - p.candidate) for p in subset) / len(subset)
            old = sum(abs(p.actual - p.champion) for p in subset) / len(subset)
            under = max(p.actual - p.candidate for p in subset)
            old_under = max(p.actual - p.champion for p in subset)
            metrics.append(
                Metric(
                    horizon,
                    regime,
                    len({p.day for p in subset}),
                    len(subset),
                    mae,
                    old,
                    under,
                    old_under,
                )
            )
            if (
                mae > 0.3 + 1e-12
                or (horizon == 24 and mae > old + 0.05 + 1e-12)
                or under > old_under + 0.1 + 1e-12
            ):
                return result("rejected", "accuracy_or_peak_gate", tuple(metrics))
    return result("accepted", "synthetic_gate_only", tuple(metrics))


@dataclass(frozen=True, slots=True)
class Promotion:
    previous: Coefficients
    current: Coefficients
    candidate_id: str
    source_ids: tuple[str, ...]


def promote(
    champion: Coefficients,
    candidate: Candidate,
    receipt: Qualification,
    *,
    approved: bool,
    backtests: tuple["Backtest", ...],
    regimes: tuple[str, ...],
    as_of: float,
    timezone: tzinfo,
) -> Promotion:
    require(type(approved) is bool and approved, "Explicit approval required")
    verified = evaluate(candidate, backtests, regimes, as_of, timezone)
    require(receipt == verified, "Receipt does not match replayed evidence")
    require(
        receipt.outcome == "accepted"
        and receipt.candidate_id == candidate.identity
        and receipt.coefficients == candidate.coefficients
        and receipt.parent_revision == champion.revision == candidate.parent_revision,
        "Stale/unqualified promotion",
    )
    return Promotion(
        champion,
        replace(candidate.coefficients, calibration="SYNTHETIC_QUALIFIED"),
        candidate.identity,
        candidate.source_ids,
    )


def rollback(promotion: Promotion, expected_revision: int) -> Coefficients:
    require(
        type(expected_revision) is int
        and promotion.current.revision == expected_revision,
        "Rollback CAS conflict",
    )
    return replace(promotion.previous, revision=expected_revision + 1)


def due_slots(
    now: datetime, completed: tuple[str, ...], lookback_days: int = 1
) -> tuple[str, ...]:
    require(
        now.tzinfo is not None and type(completed) is tuple,
        "Aware scheduler context required",
    )
    require(
        type(lookback_days) is int and 0 <= lookback_days <= 7,
        "Bounded catch-up required",
    )
    due = []
    for back in range(lookback_days, -1, -1):
        day = now.date() - timedelta(days=back)
        for hour, minute in ((10, 0), (20, 45)):
            slot = datetime.combine(
                day, datetime.min.time(), tzinfo=now.tzinfo
            ) + timedelta(hours=hour, minutes=minute)
            identity = day.isoformat() + f"/{hour:02d}:{minute:02d}"
            if slot.timestamp() <= now.timestamp() and identity not in completed:
                due.append(identity)
    return tuple(due)


@dataclass(frozen=True, slots=True)
class Backtest:
    initial: ThermalState
    forcing: tuple[Forcing, ...]
    actual: tuple[tuple[float, float | None], ...]
    forecast_issued: float
    available_at: float
    regime: str

    def __post_init__(self) -> None:
        require(
            type(self.forcing) is tuple and 0 < len(self.forcing) <= 864,
            "Invalid backtest horizon",
        )
        require(type(self.actual) is tuple, "Immutable observations required")
        number(self.forecast_issued)
        number(self.available_at)
        text(self.regime)
        require(
            self.forecast_issued <= self.initial.at
            and self.available_at >= self.initial.at,
            "Forecast leakage",
        )
        previous = self.initial.at
        for at, value in self.actual:
            number(at)
            require(
                previous < at <= self.initial.at + len(self.forcing) * 300,
                "Invalid actual timestamp",
            )
            if value is not None:
                number(value)
                require(at <= self.available_at, "Actual label not yet available")
            previous = at


def evaluate(
    candidate: Candidate,
    backtests: tuple[Backtest, ...],
    regimes: tuple[str, ...],
    as_of: float,
    timezone: tzinfo,
) -> Qualification:
    require(
        type(backtests) is tuple and len(backtests) <= 366, "Backtest capacity exceeded"
    )
    points = []
    for test in backtests:
        old = test.initial
        new = test.initial
        actual = dict(test.actual)
        for forcing in test.forcing:
            old = step(old, forcing, candidate.parent, 300)
            new = step(new, forcing, candidate.coefficients, 300)
            hours = (new.at - test.initial.at) / 3600
            value = actual.get(new.at)
            if hours in HORIZONS and value is not None:
                points.append(
                    ValidationPoint(
                        datetime.fromtimestamp(test.initial.at, timezone)
                        .date()
                        .isoformat(),
                        test.initial.at,
                        new.at,
                        test.available_at,
                        value,
                        old.room.low,
                        new.room.low,
                        test.regime,
                        not old.estimated and not new.estimated,
                    )
                )
    return qualify(candidate, tuple(points), regimes, as_of, timezone)
