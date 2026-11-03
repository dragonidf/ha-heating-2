"""Demand descriptions only; no fan/ventilation command or ownership transfer."""

from dataclasses import dataclass
from packages.contracts.models import number, require


@dataclass(frozen=True, slots=True)
class FanState:
    at: float
    delta: float | None
    burning: bool = False
    below_since: float | None = None
    night_until: float | None = None
    night_request_active: bool = False
    sensor_valid: bool = True

    def __post_init__(self) -> None:
        number(self.at, nonnegative=True)
        if self.delta is not None:
            number(self.delta)
        require(
            type(self.sensor_valid) is bool and type(self.burning) is bool,
            "Invalid fireplace state",
        )
        require(type(self.night_request_active) is bool, "Invalid night request")
        if self.below_since is not None:
            require(self.below_since <= self.at, "Future continuity evidence")
        for value in (self.below_since, self.night_until):
            if value is not None:
                number(value, nonnegative=True)


@dataclass(frozen=True, slots=True)
class FanPolicy:
    night: float
    standard: float
    intense: float

    def __post_init__(self) -> None:
        for v in (self.night, self.standard, self.intense):
            number(v)
        require(
            0 <= self.night <= self.standard <= self.intense <= 100, "Invalid speeds"
        )


@dataclass(frozen=True, slots=True)
class FanDemand:
    state: FanState
    percentage: float | None
    reason: str
    ignition: bool


def reduce_fan(
    previous: FanState,
    at: float,
    delta: float | None,
    *,
    valid: bool,
    grid: bool | None,
    armed: bool,
    permitted: bool,
    mode: str,
    night: bool,
    night_request: bool,
    policy: FanPolicy
) -> FanDemand:
    number(at)
    require(at > previous.at, "Fan time must advance")
    require(mode in ("auto", "manual", "stop"), "Invalid fan mode")
    require(
        all(type(v) is bool for v in (valid, armed, permitted, night, night_request)),
        "Invalid fan flags",
    )
    require(grid is None or type(grid) is bool, "Invalid power availability")
    if delta is not None:
        number(delta)
    gap = at - previous.at
    slope = (
        None
        if gap > 90
        or not previous.sensor_valid
        or not valid
        or previous.delta is None
        or delta is None
        else (delta - previous.delta) * 60 / gap
    )
    burning = previous.burning
    below = None if gap > 90 else previous.below_since
    ignition = False
    if not valid or delta is None:
        below = None
    else:
        ignition = delta >= 2 and slope is not None and slope > 0.8
        if delta >= 5:
            burning = True
            below = None
        elif burning:
            if delta >= 3:
                below = None
            else:
                below = at if below is None else below
            if (below is not None and at - below >= 300) or (
                delta < 4 and slope is not None and slope <= -2
            ):
                burning = False
    until = previous.night_until
    if night_request and not previous.night_request_active:
        until = at + 900
    state = FanState(
        at,
        delta if valid else None,
        burning,
        below,
        until,
        night_request,
        valid and delta is not None,
    )
    if mode == "manual":
        return FanDemand(state, None, "manual_ownership", ignition)
    if mode == "stop":
        return FanDemand(
            FanState(at, state.delta, False, None, None, night_request),
            0,
            "explicit_stop",
            ignition,
        )
    if not armed or not permitted or grid is not True:
        return FanDemand(state, 0, "permission_or_grid", ignition)
    fire = (
        policy.intense
        if state.sensor_valid
        and burning
        and delta is not None
        and delta >= 10
        and slope is not None
        and slope >= 0
        else policy.standard if state.sensor_valid and burning else 0
    )
    demand = max(fire, policy.night if until is not None and at < until else 0)
    if night:
        demand = min(demand, policy.night)
    return FanDemand(
        state, demand, "fireplace_or_night" if demand else "no_demand", ignition
    )
