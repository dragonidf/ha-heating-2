import unittest
from dataclasses import replace, FrozenInstanceError
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from packages.contracts import ContractError, TimeWindow, QualityStatus, SourceKind
from packages.planner import (
    solve,
    replan,
    retain,
    bridge,
    cycle,
    Curve,
    References,
    original,
    refresh,
    Stamp,
    Forecast,
    Slot,
    Morning,
)
from packages.thermal import Interval
from tests.fixtures.wp1c import request, thermal, model, forcing


class PlannerTests(unittest.TestCase):
    def test_cold_candidates_energy_and_morning_are_distinct(self):
        req = request()
        p = solve(req)
        self.assertEqual(p, solve(req))
        self.assertGreaterEqual(p.morning_s, 1800)
        self.assertGreater(p.energy_kwh, 0)
        self.assertGreater(p.deficit_degree_hours, 0)
        self.assertEqual(p.status, "SHORTFALL")
        self.assertIn(p.power_kw, (3, 6, 9))
        for kw in (3, 6, 9):
            result = solve(replace(req, stages_kw=(kw,)))
            duration = sum(s.end - s.start for s in result.segments)
            self.assertAlmostEqual(result.energy_kwh, kw * duration / 3600)
            self.assertEqual(result.power_kw, kw)
        self.assertEqual(solve(replace(req, stages_kw=())).reason, "power_unknown")

    def test_warm_no_need_and_external_overheat_have_explicit_outcomes(self):
        req = request()
        f = forcing(outside=Interval(22, 22))
        slots = tuple(replace(s, forcing=f, target=19) for s in req.slots)
        warm = replace(req, state=thermal(req.state.at, 22, 22), slots=slots)
        p = solve(warm)
        self.assertEqual(p.reason, "no_need")
        self.assertEqual(p.energy_kwh, 0)
        self.assertEqual(
            solve(replace(req, state=thermal(req.state.at, 26))).reason, "overheat"
        )
        fire = forcing(fire_delta=Interval(10000, 10000))
        self.assertEqual(
            solve(
                replace(warm, slots=tuple(replace(s, forcing=fire) for s in slots))
            ).reason,
            "external_overheat",
        )

    def test_permissions_return_probe_and_current_grid_never_create_current_heat(self):
        req = request()
        for changes in (
            dict(armed=False),
            dict(manual=True),
            dict(limits_qualified=False),
            dict(return_upper_c=None),
        ):
            self.assertEqual(solve(replace(req, **changes)).status, "BLOCKED")
        q = req.return_probe
        bad = (
            None,
            replace(
                q, value=None, quality=replace(q.quality, status=QualityStatus.MISSING)
            ),
            replace(q, value=50),
            replace(q, observed_at=req.state.at - 121),
            replace(q, quality=replace(q.quality, status=QualityStatus.STALE)),
            replace(q, quality=replace(q.quality, age_s=121)),
            replace(
                q,
                provenance=replace(
                    q.provenance, kind=SourceKind.HELD, independent=False
                ),
            ),
        )
        for probe in bad:
            p = solve(replace(req, return_probe=probe))
            self.assertFalse(any(s.start <= req.state.at < s.end for s in p.segments))
        for grid in (False, None):
            p = solve(replace(req, actual_grid=grid))
            self.assertFalse(any(s.start <= req.state.at < s.end for s in p.segments))
        p = solve(replace(req, state=replace(req.state, estimated=True)))
        self.assertFalse(any(s.start <= req.state.at < s.end for s in p.segments))

    def test_allowed_windows_outages_and_morning_shortfall(self):
        req = request()
        p = solve(replace(req, allowed=()))
        self.assertEqual(p.reason, "morning_shortfall")
        self.assertEqual(p.segments, ())
        slots = tuple(replace(s, grid="scheduled_off") for s in req.slots)
        p = solve(replace(req, slots=slots))
        self.assertEqual(p.segments, ())
        self.assertEqual(p.status, "SHORTFALL")
        # Only 25 minutes available: do not fabricate the missing five minutes.
        start = req.state.at
        p = solve(replace(req, allowed=(TimeWindow(start=start, end=start + 1500),)))
        self.assertLess(p.morning_s, 1800)
        self.assertEqual(p.reason, "morning_shortfall")
        p = solve(
            replace(req, slots=tuple(replace(s, grid="unknown") for s in req.slots))
        )
        self.assertTrue(all(s.conditional for s in p.segments))

    def test_advance_only_when_outage_requires_and_never_more_than_three_hours(self):
        req = request(hours=5)
        start = req.state.at
        morning = Morning(
            TimeWindow(start=start + 10800, end=start + 18000), 10800, None, 0, False
        )
        allowed = (TimeWindow(start=start, end=start + 1800),)
        no = solve(replace(req, morning=morning, allowed=allowed))
        self.assertEqual(no.morning_s, 0)
        slots = tuple(
            (
                replace(s, grid="scheduled_off")
                if s.window.start >= morning.window.start
                else s
            )
            for s in req.slots
        )
        yes = solve(replace(req, morning=morning, allowed=allowed, slots=slots))
        self.assertEqual(yes.morning_s, 1800)
        with self.assertRaises(ContractError):
            replace(morning, advance_s=10801)

    def test_partial_confirmed_session_continues_without_reset_or_fabricated_credit(
        self,
    ):
        req = request()
        at = req.state.at
        morning = Morning(TimeWindow(start=at - 1500, end=at + 300), 0, at, 1500, True)
        slots = req.slots[:1]
        p = solve(replace(req, morning=morning, slots=slots))
        self.assertEqual(p.morning_s, 1800)
        for m in (
            replace(morning, confirmed_valid=False),
            replace(morning, confirmed_until=at - 1),
            replace(morning, confirmed_s=1800),
            replace(morning, window=TimeWindow(start=at + 300, end=at + 600)),
        ):
            self.assertLess(solve(replace(req, morning=m, slots=slots)).morning_s, 1800)
        # Interrupted (OFF) prefix cannot be joined to a later 5-minute segment.
        slots = (replace(req.slots[0], grid="scheduled_off"), req.slots[1])
        p = solve(
            replace(
                req,
                morning=replace(
                    morning, window=TimeWindow(start=at - 1500, end=at + 600)
                ),
                slots=slots,
            )
        )
        self.assertEqual(p.morning_s, 1500)

    def test_budget_is_soft_known_spend_and_unknown_price_remain_explicit(self):
        req = request(budget_kwh=0, known_spent_kwh=5, spend_complete=False)
        p = solve(req)
        self.assertGreater(p.projected_overrun, 5)
        self.assertTrue(p.budget_uncertain)
        self.assertGreater(p.energy_kwh, 0)  # comfort outranks a soft budget
        no = solve(replace(req, budget_kwh=None))
        self.assertIsNone(no.projected_overrun)
        unknown = solve(
            replace(req, slots=tuple(replace(s, price=None) for s in req.slots))
        )
        self.assertTrue(all(s.conditional for s in unknown.segments))

    def test_work_caps_cancellation_and_hard_rejection_of_stale_bridge(self):
        req = request()
        self.assertEqual(solve(replace(req, max_work=1)).status, "SEARCH_EXHAUSTED")
        self.assertEqual(solve(req, lambda: True).status, "SEARCH_EXHAUSTED")
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls > len(req.slots) + 5

        self.assertEqual(solve(req, cancel).segments, ())
        p = solve(req)
        plan = bridge(p, req.stamp, req.state.at, req.slots[-1].window.end + 60)
        self.assertEqual(plan.segments, p.segments)
        for stamp in (
            replace(req.stamp, input_hash="b" * 64),
            replace(req.stamp, owner_epoch=2),
            replace(req.stamp, grid_epoch=2),
            replace(req.stamp, boot_id="new"),
            replace(req.stamp, revisions=replace(req.stamp.revisions, config=2)),
            replace(req.stamp, revisions=replace(req.stamp.revisions, model=2)),
            replace(req.stamp, revisions=replace(req.stamp.revisions, topology=2)),
        ):
            with self.assertRaises(ContractError):
                bridge(p, stamp, req.state.at, req.slots[-1].window.end + 60)
        with self.assertRaises(ContractError):
            bridge(
                solve(replace(req, armed=False)),
                req.stamp,
                req.state.at,
                req.slots[-1].window.end + 60,
            )
        with self.assertRaises(ContractError):
            bridge(
                replace(p, trajectory=()),
                req.stamp,
                req.state.at,
                req.slots[-1].window.end + 60,
            )

    def test_nineteen_minor_forecast_updates_preserve_plan_after_safety_replay(self):
        req = request()
        p = solve(req)
        segments = p.segments
        for i in range(19):
            updated = replace(
                req,
                stamp=replace(req.stamp, input_hash=f"{i+1:064x}"),
                weather=replace(req.weather, issue=req.weather.issue + i),
            )
            p = replan(updated, p)
            self.assertEqual(p.segments, segments)
            self.assertEqual(p.stamp, updated.stamp)
            self.assertEqual(p.reason, "retained_after_current_safety_replay")
        self.assertFalse(retain(p, replace(req, manual=True)))
        self.assertFalse(retain(p, replace(req, slots=req.slots[:-1])))
        self.assertFalse(
            retain(p, replace(req, stamp=replace(req.stamp, owner_epoch=2)))
        )
        self.assertFalse(retain(p, replace(req, stored_upper=24.01)))
        self.assertNotEqual(replan(replace(req, armed=False), p).status, "PROPOSAL")
        self.assertNotEqual(
            replan(req, p, material_change=True).reason,
            "retained_after_current_safety_replay",
        )
        self.assertFalse(retain(replace(p, power_kw=None), req))

    def test_frozen_original_cutoff_coverage_and_latest_are_distinct(self):
        ref = 100000.0

        def curve(issued, end=100001):
            return Curve(
                "synthetic.curve",
                issued,
                ((issued, Interval(20, 20)), (end, Interval(21, 21))),
                "a" * 64,
            )

        exact = curve(ref - 43200)
        early = curve(ref - 43201)
        late = curve(ref - 43199)
        self.assertEqual(original((early, late, exact), ref), exact)
        self.assertIsNone(original((late, curve(ref - 43200, ref - 1)), ref))
        refs = References("2026-01-05", early, exact, exact, late)
        newer = curve(ref)
        updated = refresh(refs, newer)
        self.assertEqual(updated.original_12h, exact)
        self.assertEqual(updated.initial, early)
        self.assertEqual(updated.prestart, exact)
        self.assertEqual(updated.latest, newer)
        self.assertNotEqual(exact.checksum, newer.checksum)
        with self.assertRaises(ContractError):
            refresh(updated, early)
        with self.assertRaises(FrozenInstanceError):
            exact.issued = 2
        with self.assertRaises(ContractError):
            curve(ref, ref - 1)

    def test_calendar_before_after_seven_dst_and_missed_midnight(self):
        tz = ZoneInfo("Europe/Kyiv")
        for month, day in ((3, 29), (10, 25), (1, 6)):
            before = datetime(2026, month, day, 6, 59, tzinfo=tz)
            after = before.replace(hour=7, minute=0)
            ident, window = cycle(before)
            self.assertEqual(ident, before.date().isoformat())
            self.assertEqual(window.end - window.start, 7200)
            self.assertNotEqual(cycle(after)[0], ident)
            self.assertEqual(cycle(before.replace(hour=0))[0], ident)
        with self.assertRaises(ContractError):
            cycle(datetime(2026, 1, 1))

    def test_forecast_horizon_age_and_interval_uncertainty(self):
        req = request()
        at = req.state.at
        for weather in (
            replace(req.weather, issue=at - 30000),
            replace(req.weather, received=at + 1),
            Forecast(at + 1, at + 1, req.weather.horizon, "synthetic.future"),
            replace(req.weather, horizon=TimeWindow(start=at, end=at + 300)),
        ):
            p = solve(replace(req, weather=weather))
            self.assertTrue(any(s.conditional for s in p.segments))
        uncertain = forcing(
            outside=Interval(-10, 0),
            ventilation_loss=Interval(0, 1),
            quality_valid=False,
        )
        p = solve(
            replace(req, slots=tuple(replace(s, forcing=uncertain) for s in req.slots))
        )
        self.assertTrue(p.trajectory[-1].estimated)
        self.assertLess(p.trajectory[-1].room.low, p.trajectory[-1].room.high)

    def test_qualified_feasible_status_and_contract_validation(self):
        req = request()
        at = req.state.at
        # A comfortable state with a cold stored state can need heat later.
        p = solve(
            replace(
                req,
                model=model(calibration="SYNTHETIC_QUALIFIED"),
                state=thermal(at, 21, 21),
                slots=tuple(replace(s, target=19) for s in req.slots),
            )
        )
        self.assertEqual(p.status, "PROPOSAL")
        for changes in (
            dict(slots=()),
            dict(stages_kw=(0,)),
            dict(stages_kw=(101,)),
            dict(beam=0),
            dict(max_work=200001),
            dict(actual_grid=1),
            dict(armed=1),
            dict(allowed=[]),
            dict(return_max_age_s=-1),
            dict(model=model(revision=2)),
            dict(
                slots=(
                    replace(
                        req.slots[0], window=TimeWindow(start=at + 1, end=at + 301)
                    ),
                )
            ),
        ):
            with self.assertRaises(ContractError):
                replace(req, **changes)
        with self.assertRaises(ContractError):
            replace(req.slots[0], grid="absent")
        with self.assertRaises(ContractError):
            replace(req.slots[0], target=30)
        with self.assertRaises(ContractError):
            replace(req.weather, received=0)
        with self.assertRaises(ContractError):
            replace(req.morning, confirmed_valid=1)
        with self.assertRaises(ContractError):
            replace(req.stamp, input_hash="bad")

    def test_grid_return_delivery_times_and_saved_state_age_are_not_refreshed(self):
        req = request()
        at = req.state.at
        q = req.return_probe
        for changes in (
            dict(return_probe=replace(q, received_at=at + 1)),
            dict(return_probe=replace(q, received_at=at - 1)),
            dict(state=replace(req.state, observed_at=at - 121)),
        ):
            p = solve(replace(req, **changes))
            self.assertFalse(any(s.start <= at < s.end for s in p.segments))

    def test_segment_capacity_and_replay_infeasibility_are_explicit(self):
        req = request(hours=72, stages_kw=(9.0,))
        # Tiny, cold target cannot be met; alternating permissions create >256 separate proposals.
        slots = tuple(
            replace(
                s,
                target=24,
                upper=100,
                forcing=forcing(outside=Interval(-100, -100)),
                grid="normal" if i % 2 == 0 else "scheduled_off",
            )
            for i, s in enumerate(req.slots)
        )
        p = solve(replace(req, slots=slots, stored_upper=1000))
        self.assertEqual(p.status, "SHORTFALL")
        self.assertLessEqual(len(p.segments), 256)
        # Metadata can independently split contiguous heat. Never truncate those safety labels.
        slots = tuple(
            replace(
                s,
                grid="normal" if i % 2 == 0 else "unknown",
                target=22,
                upper=100,
                forcing=forcing(outside=Interval(20, 20)),
            )
            for i, s in enumerate(req.slots)
        )
        r = replace(
            req,
            slots=slots,
            stages_kw=(3.0,),
            stored_upper=1000,
            model=model(calibration="SYNTHETIC_QUALIFIED"),
        )
        split = solve(r, _fixed=(True,) * 864)
        self.assertEqual(split.reason, "segment_capacity")
        self.assertEqual(split.segments, ())
        one = request(stages_kw=(9.0,))
        fixed = (True,) * len(one.slots)
        p = solve(replace(one, allowed=()), _fixed=fixed)
        self.assertEqual(p.reason, "unsafe_retained")

    def test_replan_changes_record_cause_and_cancel_is_not_hidden_by_retention(self):
        req = request()
        p = solve(req)
        result = replan(
            replace(req, stamp=replace(req.stamp, grid_epoch=2)),
            p,
            material_change=True,
        )
        self.assertIn("grid_epoch", result.changes)
        self.assertIn("material_inputs_changed", result.changes)
        result = replan(req, p, cancelled=lambda: True)
        self.assertEqual(result.status, "SEARCH_EXHAUSTED")
        self.assertEqual(result.segments, ())
        self.assertFalse(retain(replace(p, status="BLOCKED"), req))
