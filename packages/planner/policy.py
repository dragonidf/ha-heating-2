"""Injected local-calendar policy, never a scheduler or physical power selector."""

from dataclasses import dataclass
from datetime import datetime, date, tzinfo, timedelta
from packages.contracts import TimeWindow
from packages.contracts.models import require, number
from packages.planner.sources import allowed_window, day_span


@dataclass(frozen=True, slots=True)
class ComfortPolicy:
    day_target: float
    sleep_target: float
    upper: float
    sleep_start_minute: int
    sleep_end_minute: int

    def __post_init__(self) -> None:
        for v in (self.day_target, self.sleep_target, self.upper):
            number(v)
        require(
            max(self.day_target, self.sleep_target) < self.upper,
            "Invalid comfort limits",
        )
        for v in (self.sleep_start_minute, self.sleep_end_minute):
            require(type(v) is int and 0 <= v < 1440, "Invalid sleep schedule")

    def target(self, local: datetime) -> float:
        require(local.tzinfo is not None, "Aware local time required")
        minute = local.hour * 60 + local.minute
        start = self.sleep_start_minute
        end = self.sleep_end_minute
        sleeping = (
            (start <= minute < end if start < end else minute >= start or minute < end)
            if start != end
            else False
        )
        return self.sleep_target if sleeping else self.day_target


def windows(
    day: date, zone: tzinfo, mode: str, strict: tuple[TimeWindow, ...]
) -> tuple[TimeWindow, ...]:
    require(mode in ("strict", "night", "comfort"), "Invalid strategy")
    require(
        type(strict) is tuple and all(isinstance(w, TimeWindow) for w in strict),
        "Invalid strict windows",
    )
    span = day_span(day, zone)
    if mode == "comfort":
        return (span,)
    if mode == "night":
        return allowed_window(day, 0, 420, zone) + allowed_window(day, 1380, 0, zone)
    result = []
    for w in strict:
        start = max(w.start, span.start)
        end = min(w.end, span.end)
        if start < end:
            result.append(TimeWindow(start=start, end=end))
    return tuple(result)


def planning_horizon(
    start: float, next_available: float | None, response_s: float
) -> tuple[TimeWindow, bool]:
    number(start, nonnegative=True)
    number(response_s, nonnegative=True)
    require(response_s <= 259200, "Response reserve exceeds horizon")
    if next_available is not None:
        number(next_available)
        require(next_available >= start, "Past availability")
    end = max(
        start + 86400,
        next_available + response_s if next_available is not None else start + 259200,
    )
    capped = min(end, start + 259200)
    return TimeWindow(start=start, end=capped), next_available is None or end > capped


def power_scenarios(
    choice: str, auto_effective_kw: float | None, auto_calibrated: bool
) -> tuple[float, ...]:
    """Synthetic effective-power assumptions only, never hardware stage selection."""
    require(
        choice in ("3", "6", "9", "AUTO", "compare") and type(auto_calibrated) is bool,
        "Invalid scenario policy",
    )
    if auto_effective_kw is not None:
        number(auto_effective_kw)
        require(0 < auto_effective_kw <= 100, "Invalid effective power")
    if choice == "AUTO":
        return (
            (auto_effective_kw,)
            if auto_calibrated and auto_effective_kw is not None
            else ()
        )
    if choice == "compare":
        return (3.0, 6.0, 9.0)
    return (float(choice),)
