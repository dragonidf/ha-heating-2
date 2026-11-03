"""Synthetic reproductions of independent review 6612587291, written before fixes."""

import unittest
from dataclasses import replace
from packages.contracts import TimeWindow
from packages.planner import solve, replan, retain
from packages.thermal import Interval, step
from tests.fixtures.wp1c import request, thermal, forcing, model


def warm(req):
    return replace(
        req,
        state=thermal(req.state.at, 22, 22),
        slots=tuple(
            replace(s, target=19, forcing=forcing(outside=Interval(22, 22)))
            for s in req.slots
        ),
    )


def changed(req, **values):
    return replace(req, stamp=replace(req.stamp, input_hash="b" * 64), **values)


class IndependentReviewReproductions(unittest.TestCase):
    def test_changed_no_heat_plan_must_search_for_new_morning_demand(self):
        cold = request()
        previous = solve(warm(cold))
        self.assertEqual(previous.segments, ())
        result = replan(
            changed(cold), previous
        )  # Default material_change=False is no evidence.
        self.assertTrue(result.segments)
        self.assertGreaterEqual(result.morning_s, 1800)
        self.assertNotEqual(result.reason, "retained_after_current_safety_replay")

    def test_coasting_fireplace_reaches_morning_target_without_mandatory_thirty_minutes(
        self,
    ):
        req = request()
        f = forcing(outside=Interval(5, 5), fire_delta=Interval(50, 50))
        req = replace(
            req, slots=tuple(replace(s, forcing=f) for s in req.slots), allowed=()
        )
        coast = req.state
        for slot in req.slots:
            coast = step(coast, f, req.model, slot.window.end - slot.window.start)
        self.assertGreater(coast.room.low, 20.6)
        result = solve(req)
        self.assertEqual(result.energy_kwh, 0)
        self.assertNotEqual(result.reason, "morning_shortfall")

    def test_forecast_normal_cannot_make_future_unknown_grid_heat_unconditional(self):
        req = request(actual_grid=None, model=model(calibration="SYNTHETIC_QUALIFIED"))
        result = solve(req)
        self.assertTrue(result.segments)
        self.assertTrue(all(s.conditional for s in result.segments))


class RetentionReviewTests(unittest.TestCase):
    def test_cold_to_warm_removes_unnecessary_heat_even_without_caller_flag(self):
        req = request()
        old = solve(req)
        result = replan(changed(warm(req)), old)
        self.assertEqual(result.energy_kwh, 0)
        self.assertEqual(result.segments, ())
        self.assertFalse(result.morning_required)
        self.assertFalse(retain(old, changed(warm(req))))

    def test_changed_target_and_weather_force_search_even_if_hash_was_not_updated(self):
        req = warm(request())
        old = solve(req)
        for new in (
            replace(req, slots=tuple(replace(s, target=23) for s in req.slots)),
            replace(
                req,
                slots=tuple(
                    replace(s, target=21, forcing=forcing(outside=Interval(-30, -30)))
                    for s in req.slots
                ),
            ),
        ):
            with self.subTest(target=new.slots[0].target):
                result = replan(new, old)
                self.assertTrue(result.segments)
                self.assertTrue(result.morning_required)
                self.assertFalse(retain(old, new))
                self.assertNotEqual(
                    result.reason, "retained_after_current_safety_replay"
                )

    def test_sensor_uncertainty_and_expired_weather_cannot_reuse_old_no_heat_assumptions(
        self,
    ):
        req = warm(request())
        old = solve(req)
        for new in (
            replace(req, state=replace(req.state, estimated=True)),
            replace(
                req,
                slots=tuple(
                    replace(s, forcing=replace(s.forcing, quality_valid=False))
                    for s in req.slots
                ),
            ),
            replace(
                req,
                weather=replace(
                    req.weather, issue=req.state.at - req.forecast_max_age_s - 1
                ),
            ),
        ):
            self.assertFalse(retain(old, new))
            self.assertNotEqual(
                replan(new, old).reason, "retained_after_current_safety_replay"
            )

    def test_nineteen_publication_only_refreshes_preserve_feasibility_and_objective(
        self,
    ):
        req = request()
        old = solve(req)

        def objective(p):
            return (
                p.status,
                p.segments,
                p.segment_reasons,
                p.morning_required,
                p.morning_s,
                p.deficit_degree_hours,
                p.energy_kwh,
                p.projected_overrun,
                p.budget_uncertain,
                p.trajectory,
            )

        reference = objective(old)
        for i in range(19):
            new = replace(
                req,
                stamp=replace(req.stamp, input_hash=f"{i+1:064x}"),
                weather=replace(
                    req.weather,
                    issue=req.weather.issue + i,
                    received=req.weather.received + i,
                ),
            )
            result = replan(new, old)
            self.assertEqual(objective(result), reference)
            self.assertEqual(result.retention_key, old.retention_key)
            self.assertEqual(result.reason, "retained_after_current_safety_replay")
            old = result
        # A numeric forcing change is outside the verified zero-change retention bound.
        tiny = replace(
            req,
            slots=tuple(
                replace(s, forcing=forcing(outside=Interval(-5.001, -5.001)))
                for s in req.slots
            ),
        )
        self.assertFalse(retain(old, tiny))

    def test_missing_retention_evidence_and_changed_objective_force_fresh_search(self):
        req = request()
        old = solve(req)
        self.assertFalse(retain(replace(old, retention_key=None), req))
        for previous in (
            replace(old, energy_kwh=0),
            replace(old, deficit_degree_hours=0),
            replace(old, morning_s=0),
            replace(old, morning_required=False),
        ):
            result = replan(req, previous)
            self.assertEqual(
                result, replace(solve(req), changes=("current_safety_replay_failed",))
            )


class MorningReviewTests(unittest.TestCase):
    def fire(self, hours=2):
        req = request(hours=hours)
        return replace(
            req,
            slots=tuple(
                replace(
                    s,
                    forcing=forcing(
                        outside=Interval(5, 5), fire_delta=Interval(50, 50)
                    ),
                )
                for s in req.slots
            ),
        )

    def test_safe_fireplace_coasting_uses_zero_boiler_energy_even_when_heat_is_allowed(
        self,
    ):
        result = solve(self.fire())
        self.assertFalse(result.morning_required)
        self.assertEqual(result.segments, ())
        self.assertEqual(result.energy_kwh, 0)
        self.assertEqual(result.deficit_degree_hours, 0)
        self.assertGreater(result.trajectory[-1].room.low, 20.6)

    def test_cold_no_grid_and_upper_keep_need_separate_from_permission_and_feasibility(
        self,
    ):
        cold = request()
        result = solve(cold)
        self.assertTrue(result.morning_required)
        self.assertGreaterEqual(result.morning_s, 1800)
        no_grid = replace(
            cold,
            actual_grid=False,
            slots=tuple(replace(s, grid="scheduled_off") for s in cold.slots),
        )
        result = solve(no_grid)
        self.assertTrue(result.morning_required)
        self.assertEqual(result.segments, ())
        self.assertEqual(result.reason, "morning_shortfall")
        hot = replace(cold, state=thermal(cold.state.at, 26, 26))
        self.assertEqual(solve(hot).reason, "overheat")
        self.assertEqual(solve(hot).segments, ())

    def test_next_confirmed_heat_reserve_deficit_requires_morning_energy(self):
        req = self.fire(hours=5)
        deadline = req.morning.window.end
        slots = tuple(
            (
                s
                if s.window.end <= deadline
                else replace(
                    s, forcing=forcing(outside=Interval(-60, -60)), grid="scheduled_off"
                )
            )
            for s in req.slots
        )
        reserve = replace(req, slots=slots)
        result = solve(reserve)
        self.assertTrue(result.morning_required)
        self.assertGreaterEqual(result.morning_s, 1800)
        self.assertGreater(result.energy_kwh, 0)
        # Unknown availability is not a confirmed opportunity that can end the reserve.
        unknown = replace(
            reserve,
            slots=tuple(
                replace(s, grid="unknown") if s.window.start >= deadline else s
                for s in slots
            ),
        )
        self.assertTrue(solve(unknown).morning_required)

    def test_legitimate_early_comfort_deficit_does_not_become_mandatory_morning_session(
        self,
    ):
        req = self.fire()
        at = req.state.at
        # The first half hour precedes the morning warm-up window: its comfort target still counts.
        req = replace(
            req,
            morning=replace(
                req.morning, window=TimeWindow(start=at + 1800, end=at + 7200)
            ),
        )
        result = solve(req)
        self.assertFalse(result.morning_required)
        self.assertGreater(result.energy_kwh, 0)
        self.assertGreater(result.deficit_degree_hours, 0)

    def test_deadline_inside_slot_checks_exact_coast_and_bounded_cancellation(self):
        req = request()
        at = req.state.at
        req = replace(
            req,
            morning=replace(req.morning, window=TimeWindow(start=at, end=at + 7100)),
        )
        self.assertTrue(solve(req).morning_required)
        self.assertEqual(solve(replace(req, max_work=24)).status, "SEARCH_EXHAUSTED")
        short = replace(req, slots=req.slots[:1])
        self.assertFalse(solve(short).morning_required)  # no invented 07:00 coverage


class FutureConditionalReviewTests(unittest.TestCase):
    def test_normal_forecast_and_missing_actual_guards_always_leave_future_conditional(
        self,
    ):
        req = request(model=model(calibration="SYNTHETIC_QUALIFIED"))
        at = req.state.at
        for grid in (False, None, True):
            for probe in (
                None,
                replace(req.return_probe, observed_at=at - 121),
                req.return_probe,
            ):
                for forecast in ("normal", "unknown"):
                    new = replace(
                        req,
                        actual_grid=grid,
                        return_probe=probe,
                        slots=tuple(replace(s, grid=forecast) for s in req.slots),
                    )
                    p = solve(new)
                    self.assertTrue(p.segments)
                    for segment, reasons in zip(p.segments, p.segment_reasons):
                        if segment.start > at:
                            self.assertTrue(segment.conditional)
                            self.assertIn("future_execution_unverified", reasons)
                        if grid is not True:
                            self.assertIn("actual_grid_unverified", reasons)
                        if probe is not req.return_probe:
                            self.assertIn("current_return_unverified", reasons)
                        if forecast == "unknown":
                            self.assertIn("grid_forecast_unknown", reasons)
                    if grid is not True or probe is not req.return_probe:
                        self.assertTrue(all(s.conditional for s in p.segments))

    def test_safe_present_segment_is_separate_from_speculative_future(self):
        req = request(model=model(calibration="SYNTHETIC_QUALIFIED"))
        p = solve(req)
        self.assertEqual(p.segments[0].start, req.state.at)
        self.assertEqual(p.segments[0].end, req.slots[0].window.end)
        self.assertFalse(p.segments[0].conditional)
        self.assertEqual(p.segment_reasons[0], ())
        self.assertTrue(all(s.conditional for s in p.segments[1:]))
        self.assertTrue(
            all("future_execution_unverified" in r for r in p.segment_reasons[1:])
        )

    def test_bridge_rejects_unlabelled_future_heat_even_with_matching_stamp(self):
        from packages.contracts import ContractError
        from packages.planner import bridge

        req = request()
        p = solve(req)
        unlabelled = replace(
            p,
            segments=tuple(replace(s, conditional=False) for s in p.segments),
            segment_reasons=(),
        )
        with self.assertRaises(ContractError):
            bridge(unlabelled, req.stamp, req.state.at, req.slots[-1].window.end + 1)
