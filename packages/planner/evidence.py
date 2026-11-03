"""Comparison-ready immutable evidence. Persistence belongs to a later archive worker."""

from dataclasses import dataclass
from packages.contracts.models import require, number
from packages.planner import Request, Proposal, Curve


@dataclass(frozen=True, slots=True)
class Recommendation:
    power_kw: float | None
    deadline: float | None
    deficit_degree_hours: float
    calibration: str
    conditional: bool

    def __post_init__(self) -> None:
        if self.power_kw is not None:
            number(self.power_kw, nonnegative=True)
        if self.deadline is not None:
            number(self.deadline, nonnegative=True)
        number(self.deficit_degree_hours, nonnegative=True)
        require(
            self.calibration in ("NOT_PARITY_VERIFIED", "SYNTHETIC_QUALIFIED")
            and type(self.conditional) is bool,
            "Invalid recommendation",
        )


def recommend(proposal: Proposal, request: Request) -> Recommendation:
    require(proposal.stamp == request.stamp, "Stale recommendation")
    return Recommendation(
        proposal.power_kw,
        proposal.segments[0].start if proposal.segments else None,
        proposal.deficit_degree_hours,
        request.model.calibration,
        proposal.status != "PROPOSAL" or any(s.conditional for s in proposal.segments),
    )


@dataclass(frozen=True, slots=True)
class CycleBudget:
    initial_kwh: float
    known_actual_kwh: float
    unknown_s: float
    latest_projected_kwh: float

    def __post_init__(self) -> None:
        for v in (
            self.initial_kwh,
            self.known_actual_kwh,
            self.unknown_s,
            self.latest_projected_kwh,
        ):
            number(v, nonnegative=True)

    @property
    def known_remaining_kwh(self) -> float:
        return self.initial_kwh - self.known_actual_kwh

    @property
    def deviation_kwh(self) -> float | None:
        return self.known_actual_kwh - self.initial_kwh if self.unknown_s == 0 else None


def comparison(
    curve: Curve, target: float, actual: float | None
) -> tuple[float, float] | None:
    """Exact frozen forecast point only. Missing coverage/actual breaks the series."""
    number(target)
    if actual is None:
        return None
    number(actual)
    prediction = next((value for at, value in curve.points if at == target), None)
    if prediction is None:
        return None
    return actual - prediction.high, actual - prediction.low
