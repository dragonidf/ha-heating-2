"""T-P02/P07/P10 and T-D01/D05: minimal, synthetic plan boundary."""
import unittest
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from packages.contracts import (
    Clock, ContractError, ControlSnapshot, Plan, PlanSegment, Revisions, TimeWindow,
    Unit, utc_window,
)
from tests.contracts.test_readings import reading


def snapshot(**changes):
    values = dict(
        snapshot_id="synthetic.snapshot", input_hash="a" * 64, boot_id="synthetic.boot",
        revisions=Revisions(config=1, model=2, topology=3), grid_epoch=4, owner_epoch=5,
        captured_at=100.0, room=reading(18, Unit.CELSIUS),
        return_temperature=reading(25, Unit.CELSIUS), thermostat=reading(19, Unit.CELSIUS),
        grid_actual=reading(True, Unit.BOOLEAN), forecast_grid=None, power=None,
        compute_available=True, hard_stop=False, scheduled_outage=False,
    )
    return ControlSnapshot(**(values | changes))


def plan(**changes):
    s = snapshot()
    values = dict(
        plan_id="synthetic.plan", boot_id=s.boot_id, revisions=s.revisions,
        grid_epoch=s.grid_epoch, owner_epoch=s.owner_epoch, input_hash=s.input_hash,
        issued_at=90.0, valid_from=95.0, valid_until=200.0, expires_at=210.0,
        segments=(PlanSegment(start=100.0, end=110.0, conditional=True),),
    )
    return Plan(**(values | changes))


class PlanTests(unittest.TestCase):
    def test_segments_are_half_open_and_cannot_overlap(self):
        p = plan()
        self.assertFalse(p.heats_at(99.9))
        self.assertTrue(p.heats_at(100))
        self.assertFalse(p.heats_at(110))
        for segments in ((PlanSegment(start=101, end=120), PlanSegment(start=110, end=125)),
                         (PlanSegment(start=101, end=220),), [PlanSegment(start=100, end=110)]):
            with self.subTest(segments=segments), self.assertRaises(ContractError):
                plan(segments=segments)

    def test_revisions_clock_hash_and_units_are_validated(self):
        for call in (lambda: Revisions(config=True, model=0, topology=0),
                     lambda: Clock(utc=float("nan"), monotonic=1, boot_id="synthetic.boot"),
                     lambda: snapshot(input_hash="not-a-hash"),
                     lambda: snapshot(room=reading(1, Unit.KILOWATT)),
                     lambda: plan(valid_until=80),
                     lambda: TimeWindow(start=5, end=5)):
            with self.assertRaises(ContractError):
                call()

    def test_dst_windows_use_real_utc_duration_and_explicit_fold(self):
        tz = ZoneInfo("Europe/Kyiv")
        fall = utc_window(datetime(2026, 10, 25, 0, tzinfo=tz),
                          datetime(2026, 10, 26, 0, tzinfo=tz))
        spring = utc_window(datetime(2026, 3, 29, 0, tzinfo=tz),
                            datetime(2026, 3, 30, 0, tzinfo=tz))
        self.assertEqual(fall.end - fall.start, 25 * 3600)
        self.assertEqual(spring.end - spring.start, 23 * 3600)
        ambiguous = utc_window(datetime(2026, 10, 25, 3, 30, tzinfo=tz, fold=0),
                               datetime(2026, 10, 25, 3, 30, tzinfo=tz, fold=1))
        self.assertEqual(ambiguous.end - ambiguous.start, 3600)
        with self.assertRaises(ContractError):
            utc_window(datetime(2026, 3, 29, 3, 30, tzinfo=tz),
                       datetime(2026, 3, 29, 5, tzinfo=tz))
        with self.assertRaises(ContractError):
            utc_window(datetime(2026, 1, 1), datetime(2026, 1, 2))
