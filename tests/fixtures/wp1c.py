"""Artificial states, policy and coefficients; no household calibration."""

from dataclasses import replace
from datetime import datetime, timezone
from packages.thermal import Interval, Coefficients, ThermalState, Forcing
from packages.planner import Stamp, Forecast, Slot, Morning, Request
from packages.contracts import Revisions, TimeWindow, Unit
from tests.fixtures.synthetic import reading


def model(**changes):
    return replace(Coefficients(0.04, 0.02, 0.1, 0.6, 0.02, 1), **changes)


def forcing(**changes):
    return replace(
        Forcing(
            Interval(-5, -5),
            Interval(0, 0),
            Interval(0, 0),
            Interval(0, 0),
            True,
            Interval(0, 0),
        ),
        **changes
    )


def thermal(at=100000, room=19, stored=24, **changes):
    return replace(
        ThermalState(Interval(room, room), Interval(stored, stored), at, at, False),
        **changes
    )


def request(hours=2, **changes):
    at = datetime(2026, 1, 5, 4, tzinfo=timezone.utc).timestamp()
    slots = tuple(
        Slot(
            TimeWindow(start=at + i * 300, end=at + (i + 1) * 300),
            forcing(),
            "normal",
            20,
            25,
            0.2,
        )
        for i in range(int(hours * 12))
    )
    values = dict(
        stamp=Stamp(
            "a" * 64,
            Revisions(config=1, model=1, topology=1),
            "synthetic.compute",
            1,
            1,
        ),
        state=thermal(at),
        model=model(),
        slots=slots,
        weather=Forecast(
            at - 3600,
            at - 3500,
            TimeWindow(start=at, end=at + hours * 3600),
            "synthetic.weather",
        ),
        allowed=(TimeWindow(start=at, end=at + hours * 3600),),
        morning=Morning(TimeWindow(start=at, end=at + 7200), 10800, None, 0, False),
        stages_kw=(3.0, 6.0, 9.0),
        stored_upper=45,
        armed=True,
        manual=False,
        actual_grid=True,
        budget_kwh=20,
        known_spent_kwh=0,
        spend_complete=True,
        return_probe=reading(25, Unit.CELSIUS, observed_at=at, received_at=at),
        return_upper_c=45,
        return_max_age_s=120,
        limits_qualified=True,
        state_max_age_s=120,
    )
    return Request(**(values | changes))
