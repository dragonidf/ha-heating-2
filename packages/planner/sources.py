"""Pure provider normalization. Forecasts never stand in for actual grid or sensors."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from hashlib import sha256
from packages.contracts import TimeWindow
from packages.contracts.models import require, number, text
from packages.thermal import Interval
from packages.planner import Forecast


def day_span(day: date, zone: tzinfo) -> TimeWindow:
    begin = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    return TimeWindow(start=begin.timestamp(), end=end.timestamp())


def allowed_window(
    day: date, start_minute: int, end_minute: int, zone: tzinfo
) -> tuple[TimeWindow, ...]:
    require(
        type(start_minute) is int
        and type(end_minute) is int
        and 0 <= start_minute < 1440
        and 0 <= end_minute < 1440,
        "Invalid local hours",
    )
    if start_minute == end_minute:
        return ()
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone) + timedelta(
        minutes=start_minute
    )
    end = datetime.combine(
        day + timedelta(days=int(end_minute < start_minute)),
        datetime.min.time(),
        tzinfo=zone,
    ) + timedelta(minutes=end_minute)
    from packages.contracts import utc_window

    return (utc_window(start, end),)


@dataclass(frozen=True, slots=True)
class WeatherPoint:
    at: float
    temperature: Interval

    def __post_init__(self) -> None:
        number(self.at, nonnegative=True)
        require(isinstance(self.temperature, Interval), "Invalid temperature range")


@dataclass(frozen=True, slots=True)
class WeatherSeries:
    header: Forecast
    points: tuple[WeatherPoint, ...]

    def __post_init__(self) -> None:
        require(
            type(self.points) is tuple and 0 < len(self.points) <= 865,
            "Invalid weather series",
        )
        previous = -1.0
        for point in self.points:
            require(
                previous < point.at
                and self.header.horizon.start <= point.at <= self.header.horizon.end,
                "Weather point outside provider horizon",
            )
            previous = point.at


def weather_at(
    series: WeatherSeries, at: float, now: float, max_age: float
) -> Interval | None:
    number(at)
    number(now)
    number(max_age, nonnegative=True)
    if (
        not 0 <= now - series.header.issue <= max_age
        or series.header.received > now
        or not series.header.horizon.start <= at <= series.header.horizon.end
    ):
        return None
    for point in series.points:
        if point.at == at:
            return point.temperature
    for left, right in zip(series.points, series.points[1:]):
        if left.at < at < right.at:
            fraction = (at - left.at) / (right.at - left.at)
            return Interval(
                left.temperature.low * (1 - fraction)
                + right.temperature.low * fraction,
                left.temperature.high * (1 - fraction)
                + right.temperature.high * fraction,
            )
    return None


@dataclass(frozen=True, slots=True)
class OutageSchedule:
    header: Forecast
    region: str
    queue: str
    local_day: str
    outages: tuple[TimeWindow, ...]
    coverage_known: bool
    emergency: bool

    def __post_init__(self) -> None:
        text(self.region)
        text(self.queue)
        date.fromisoformat(self.local_day)
        require(
            type(self.coverage_known) is bool and type(self.emergency) is bool,
            "Invalid coverage",
        )
        require(
            type(self.outages) is tuple and len(self.outages) <= 256,
            "Invalid outage intervals",
        )
        previous = self.header.horizon.start
        for w in self.outages:
            require(
                previous <= w.start < w.end <= self.header.horizon.end,
                "Overlapping/out-of-horizon outage",
            )
            previous = w.end

    def status(
        self,
        window: TimeWindow,
        region: str,
        queue: str,
        now: float,
        zone: tzinfo,
        max_age: float,
    ) -> str:
        if (
            not self.coverage_known
            or self.region != region
            or self.queue != queue
            or not 0 <= now - self.header.issue <= max_age
            or self.header.received > now
            or not self.header.horizon.start
            <= window.start
            < window.end
            <= self.header.horizon.end
            or datetime.fromtimestamp(window.start, zone).date().isoformat()
            != self.local_day
            or datetime.fromtimestamp(window.end - 1e-3, zone).date().isoformat()
            != self.local_day
        ):
            return "unknown"
        if self.emergency:
            return "emergency"
        return (
            "scheduled_off"
            if any(w.start < window.end and window.start < w.end for w in self.outages)
            else "normal"
        )

    @property
    def content_key(self) -> str:
        return sha256(
            repr(
                (
                    self.region,
                    self.queue,
                    self.local_day,
                    self.outages,
                    self.coverage_known,
                    self.emergency,
                    self.header.horizon,
                )
            ).encode()
        ).hexdigest()


def next_available(
    schedules: tuple[OutageSchedule, ...],
    after: float,
    region: str,
    queue: str,
    now: float,
    zone: tzinfo,
    max_age: float,
) -> float | None:
    """First confirmed normal five-minute slot, no extrapolation across unknown days."""
    number(after, nonnegative=True)
    require(type(schedules) is tuple and len(schedules) <= 4, "Invalid provider batch")
    for i in range(864):
        start = after + i * 300
        w = TimeWindow(start=start, end=start + 300)
        statuses = tuple(
            s.status(w, region, queue, now, zone, max_age) for s in schedules
        )
        if "emergency" in statuses or "scheduled_off" in statuses:
            continue
        if "normal" in statuses:
            return start
    return None
