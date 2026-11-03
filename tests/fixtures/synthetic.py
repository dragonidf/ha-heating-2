"""Invented values only. Qualification here asserts a test premise, not hardware truth."""
from dataclasses import replace

from packages.contracts import (
    Clock, ControlEvent, ControlMode, ControlPolicy, ControlState, EventKind,
    TimeWindow,
)
from tests.contracts.test_plans import plan, snapshot
from tests.contracts.test_readings import reading


def policy(**changes):
    values = dict(config_revision=1, operating_mode=ControlMode.AUTO,
                  armed=True, allow_automatic=True, configuration_valid=True,
                  limits_qualified=True, room_upper_c=30.0, return_upper_c=45.0,
                  room_max_age_s=10.0, return_max_age_s=10.0,
                  thermostat_max_age_s=10.0, grid_max_age_s=10.0,
                  snapshot_max_age_s=10.0, max_skew_s=2.0,
                  min_on_s=10.0, min_off_s=5.0, intent_ttl_s=5.0,
                  recovery_stable_s=3.0, strict_windows=(TimeWindow(start=95, end=150),))
    return ControlPolicy(**(values | changes))


def clock(**changes):
    return Clock(**(dict(utc=100.0, monotonic=1000.0, boot_id="synthetic.boot") | changes))


def state(**changes):
    values = dict(boot_id="synthetic.boot", owner_epoch=5, reconciled=True,
                  changed_at_monotonic=900.0, last_monotonic=990.0,
                  last_event_sequence=0, last_event_at=99.0, plan=plan(), accepted_input_hash="a"*64)
    return ControlState(**(values | changes))


def event(**changes):
    values = dict(kind=EventKind.TICK, boot_id="synthetic.boot", owner_epoch=5,
                  sequence=1, at=100.0, expires_at=101.0)
    return ControlEvent(**(values | changes))
