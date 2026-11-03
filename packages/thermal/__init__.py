"""Pure two-state room/stored-heat model; never a floor-surface measurement."""

from dataclasses import dataclass
from itertools import product
from packages.contracts.models import number, require, counter

LEGACY_COMMIT = "db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426"
LEGACY_SHA256 = "9028b4bd811d37052b4c4b01b226d0ddb6f8d88871479483c07bd547a20bdc5a"


@dataclass(frozen=True, slots=True)
class Interval:
    low: float
    high: float

    def __post_init__(self) -> None:
        number(self.low)
        number(self.high)
        require(self.low <= self.high, "Inverted interval")

    @property
    def exact(self) -> bool:
        return self.low == self.high


@dataclass(frozen=True, slots=True)
class Coefficients:
    floor_air: float
    room_loss: float
    floor_decay: float
    heat_gain: float
    fire_gain: float
    revision: int
    version: int = 1
    calibration: str = "NOT_PARITY_VERIFIED"

    def __post_init__(self) -> None:
        for value, lower, upper in (
            (self.floor_air, 0.001, 0.2),
            (self.room_loss, 0.001, 0.15),
            (self.floor_decay, 0.01, 1.5),
            (self.heat_gain, 0.02, 3),
            (self.fire_gain, 0, 0.15),
        ):
            number(value)
            require(lower <= value <= upper, "Coefficient outside legacy bounds")
        counter(self.revision)
        require(
            type(self.version) is int and self.version == 1,
            "Unsupported thermal schema",
        )
        require(
            self.calibration in ("NOT_PARITY_VERIFIED", "SYNTHETIC_QUALIFIED"),
            "Invalid calibration",
        )


@dataclass(frozen=True, slots=True)
class ThermalState:
    room: Interval
    stored: Interval
    at: float
    observed_at: float
    estimated: bool

    def __post_init__(self) -> None:
        require(
            isinstance(self.room, Interval) and isinstance(self.stored, Interval),
            "Typed state required",
        )
        number(self.at, nonnegative=True)
        number(self.observed_at, nonnegative=True)
        require(
            self.observed_at <= self.at and type(self.estimated) is bool,
            "Invalid observer age",
        )
        require(min(self.room.low, self.stored.low) >= -273.15, "Invalid temperature")


@dataclass(frozen=True, slots=True)
class Forcing:
    outside: Interval
    power_kw: Interval
    fire_delta: Interval
    ventilation_loss: Interval
    quality_valid: bool
    external_gain: Interval

    def __post_init__(self) -> None:
        require(
            all(
                isinstance(v, Interval)
                for v in (
                    self.outside,
                    self.power_kw,
                    self.fire_delta,
                    self.ventilation_loss,
                    self.external_gain,
                )
            ),
            "Typed forcing required",
        )
        require(
            min(self.power_kw.low, self.ventilation_loss.low) >= 0, "Negative heat/duty"
        )
        require(type(self.quality_valid) is bool, "Invalid forcing quality")


def step(
    state: ThermalState, forcing: Forcing, model: Coefficients, seconds: float
) -> ThermalState:
    number(seconds)
    require(0 < seconds <= 300, "Bounded model step required")
    hours = seconds / 3600
    rooms = []
    stored = []
    for r, f, o, p, fire, vent, gain in product(
        *[
            (x.low,) if x.exact else (x.low, x.high)
            for x in (
                state.room,
                state.stored,
                forcing.outside,
                forcing.power_kw,
                forcing.fire_delta,
                forcing.ventilation_loss,
                forcing.external_gain,
            )
        ]
    ):
        rooms.append(
            r
            + (
                model.floor_air * (f - r)
                - model.room_loss * (r - o) * (1 + vent)
                + model.fire_gain * max(0, fire)
                + gain
            )
            * hours
        )
        stored.append(f + (model.heat_gain * p - model.floor_decay * (f - r)) * hours)
    uncertain = (
        state.estimated
        or not forcing.quality_valid
        or any(
            not x.exact
            for x in (
                state.room,
                state.stored,
                forcing.outside,
                forcing.power_kw,
                forcing.fire_delta,
                forcing.ventilation_loss,
                forcing.external_gain,
            )
        )
    )
    return ThermalState(
        Interval(min(rooms), max(rooms)),
        Interval(min(stored), max(stored)),
        state.at + seconds,
        state.observed_at,
        uncertain,
    )


def observe(
    saved: ThermalState, forcing: Forcing, model: Coefficients, until: float
) -> ThermalState:
    number(until)
    require(saved.at <= until <= saved.at + 259200, "Observer horizon exceeded")
    current = saved
    while current.at < until:
        current = step(current, forcing, model, min(300, until - current.at))
    return ThermalState(
        current.room, current.stored, current.at, saved.observed_at, True
    )
