import unittest
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from packages.contracts import ContractError
from packages.learning import (
    Transition,
    ValidationPoint,
    Candidate,
    qualify,
    promote,
    rollback,
    due_slots,
    stage,
    Backtest,
    evaluate,
    HORIZONS,
)
from packages.thermal import step, Interval
from tests.fixtures.wp1c import model, thermal, forcing

TZ = ZoneInfo("Europe/Kyiv")


def stamp(day):
    return datetime(2026, 1, day, 12, tzinfo=TZ).timestamp()


def candidate(**changes):
    values = dict(
        identity="synthetic.candidate",
        parent_revision=1,
        coefficients=model(revision=2),
        train_days=tuple(f"2026-01-{i:02d}" for i in range(1, 8)),
        train_end=stamp(7) + 300,
        source_ids=("synthetic.fit",),
        parent=model(),
        daily_baseline=model(),
    )
    return Candidate(**(values | changes))


def points():
    return tuple(
        ValidationPoint(
            f"2026-01-{day:02d}",
            stamp(day),
            stamp(day) + h * 3600,
            stamp(day) + h * 3600,
            20,
            20.2,
            20.15,
            "winter/vent/fire/3",
            True,
        )
        for day in (10, 11, 12)
        for h in HORIZONS
    )


def gate(c=None, p=None, regimes=("winter/vent/fire/3",), asof=stamp(20)):
    return qualify(c or candidate(), points() if p is None else p, regimes, asof, TZ)


def backtests():
    f = forcing(outside=Interval(20, 20))
    return tuple(
        Backtest(
            thermal(stamp(day), 20, 20),
            (f,) * 576,
            tuple((stamp(day) + h * 3600, 20) for h in HORIZONS),
            stamp(day) - 1,
            stamp(day) + 172800,
            "winter/vent/fire/3",
        )
        for day in (10, 11, 12)
    )


def promote_checked(old, c, q, approved=True):
    return promote(
        old,
        c,
        q,
        approved=approved,
        backtests=backtests(),
        regimes=("winter/vent/fire/3",),
        as_of=stamp(20),
        timezone=TZ,
    )


class LearningTests(unittest.TestCase):
    def test_independent_days_all_horizons_approval_and_rollback(self):
        c = candidate()
        q = evaluate(c, backtests(), ("winter/vent/fire/3",), stamp(20), TZ)
        self.assertEqual(q.outcome, "accepted")
        self.assertEqual(len(q.metrics), 7)
        self.assertEqual(q.metrics[0].candidate_under, 0)
        self.assertLess(gate().metrics[0].candidate_under, 0)
        promotion = promote_checked(model(), c, q)
        self.assertEqual(promotion.current.calibration, "SYNTHETIC_QUALIFIED")
        self.assertEqual(model().revision, 1)
        self.assertEqual(rollback(promotion, 2).revision, 3)
        for old, receipt, approved in (
            (model(revision=5), q, True),
            (model(), replace(q, outcome="pending"), True),
            (model(), q, False),
            (model(), replace(q, candidate_id="foreign"), True),
        ):
            with self.assertRaises(ContractError):
                promote_checked(old, c, receipt, approved)
        with self.assertRaises(ContractError):
            rollback(promotion, 1)

    def test_pending_quality_days_horizons_and_future_labels(self):
        self.assertEqual(gate(candidate(train_days=("2026-01-01",))).outcome, "pending")
        for data in (
            (),
            points()[:7],
            tuple(replace(p, qualified=False) for p in points()),
            tuple(p for p in points() if (p.target - p.origin) / 3600 != 48),
        ):
            self.assertEqual(gate(p=data).outcome, "pending")
        self.assertEqual(gate(regimes=()).outcome, "pending")
        self.assertEqual(gate(regimes=("unqualified",)).outcome, "pending")
        self.assertEqual(gate(asof=stamp(9)).outcome, "pending")

    def test_leakage_daily_bounds_and_accuracy_failures(self):
        self.assertEqual(gate(candidate(train_end=stamp(11))).reason, "leakage")
        self.assertEqual(
            gate(p=tuple(replace(p, day="2026-01-01") for p in points())).reason,
            "leakage",
        )
        self.assertEqual(
            gate(p=tuple(replace(p, day="invalid") for p in points())).reason,
            "invalid_day_partition",
        )
        self.assertEqual(
            gate(candidate(coefficients=model(revision=2, floor_air=0.049))).reason,
            "daily_change_bounds",
        )
        zero = model(fire_gain=0)
        self.assertEqual(
            gate(
                candidate(
                    parent=zero,
                    daily_baseline=zero,
                    coefficients=model(revision=2, fire_gain=1e-14),
                )
            ).reason,
            "daily_change_bounds",
        )
        for predicted, old in ((20.31, 20.2), (19.85, 20), (20.12, 20)):
            data = tuple(
                replace(p, candidate=predicted, champion=old) for p in points()
            )
            self.assertEqual(gate(p=data).outcome, "rejected")

    def test_fit_uses_dated_qualified_transitions_and_preserves_equation_units(self):
        samples = []
        for day in range(1, 8):
            for i in range(14):
                s = thermal(stamp(day) + i * 300, 18 + i * 0.1, 22 + i * 0.5)
                f = forcing(
                    power_kw=Interval(i % 4 * 3, i % 4 * 3),
                    fire_delta=Interval(i % 3, i % 3),
                )
                next_s = step(s, f, model(), 300)
                samples.append(
                    Transition(
                        f"2026-01-{day:02d}",
                        s.at,
                        next_s.at,
                        s.room.low,
                        s.stored.low,
                        -5,
                        f.power_kw.low,
                        f.fire_delta.low,
                        next_s.room.low,
                        next_s.stored.low,
                        True,
                    )
                )
        c = stage(
            "synthetic.fit",
            tuple(samples),
            model(),
            model(),
            TZ,
            ("synthetic.dataset",),
        )
        self.assertEqual(len(c.train_days), 7)
        self.assertAlmostEqual(c.coefficients.heat_gain, 0.6, places=6)
        self.assertAlmostEqual(c.coefficients.floor_air, 0.04, places=6)
        for data in (
            (),
            (replace(samples[0], qualified=False),),
            (replace(samples[0], local_date="2025-01-01"),),
        ):
            with self.assertRaises(ContractError):
                stage("bad", data, model(), model(), TZ, ("synthetic",))

    def test_backtest_derives_predictions_instead_of_trusting_ai_metrics(self):
        tests = []
        for day in (10, 11, 12):
            s = thermal(stamp(day), 20, 20)
            f = forcing(outside=Interval(20, 20))
            tests.append(
                Backtest(
                    s,
                    (f,) * 576,
                    tuple((s.at + h * 3600, 20) for h in HORIZONS),
                    s.at - 1,
                    s.at + 172800,
                    "winter/vent/fire/3",
                )
            )
        q = evaluate(candidate(), tuple(tests), ("winter/vent/fire/3",), stamp(20), TZ)
        self.assertEqual(q.outcome, "accepted")
        self.assertEqual(q.metrics[-1].candidate_mae, 0)
        with self.assertRaises(ContractError):
            replace(tests[0], forecast_issued=tests[0].initial.at + 1)
        with self.assertRaises(ContractError):
            replace(tests[0], actual=((tests[0].initial.at, 20),))

    def test_due_slots_dedup_missed_day_and_invalid_contracts(self):
        now = datetime(2026, 1, 12, 20, 45, tzinfo=TZ)
        slots = due_slots(now, ())
        self.assertEqual(len(slots), 4)
        self.assertEqual(due_slots(now, slots), ())
        self.assertEqual(len(due_slots(now, (), 0)), 2)
        for at, lookback in ((now.replace(tzinfo=None), 1), (now, 8)):
            with self.assertRaises(ContractError):
                due_slots(at, (), lookback)
        for changes in (
            dict(parent_revision=3),
            dict(train_days=("a", "a")),
            dict(source_ids=()),
            dict(parent=model(revision=2)),
        ):
            with self.assertRaises(ContractError):
                candidate(**changes)
        with self.assertRaises(ContractError):
            replace(points()[0], available_at=0)

    def test_boundary_accuracy_and_daily_limits_do_not_reject_float_roundoff(self):
        data = tuple(replace(p, candidate=20.3, champion=20.3) for p in points())
        self.assertEqual(gate(p=data).outcome, "accepted")
        self.assertEqual(
            gate(p=tuple(replace(p, candidate=20.300001) for p in data)).outcome,
            "rejected",
        )
        self.assertEqual(
            gate(candidate(coefficients=model(revision=2, floor_air=0.048))).outcome,
            "accepted",
        )
        self.assertEqual(
            gate(candidate(daily_baseline=model(floor_air=0.03))).reason,
            "daily_change_bounds",
        )
        self.assertEqual(
            gate(
                candidate(train_days=tuple(f"2026-02-{i:02d}" for i in range(1, 8)))
            ).reason,
            "future_training_day",
        )
        with self.assertRaises(ContractError):
            candidate(train_days=("not-a-date",))

    def test_forged_receipt_and_unqualified_prospective_labels_never_promote(self):
        c = candidate()
        q = gate(c)
        with self.assertRaises(ContractError):
            promote_checked(model(), c, q)
        verified = evaluate(c, backtests(), ("winter/vent/fire/3",), stamp(20), TZ)
        with self.assertRaises(ContractError):
            promote_checked(model(), c, replace(verified, metrics=()))
        bad = tuple(
            replace(b, actual=tuple((at, None) for at, _ in b.actual))
            for b in backtests()
        )
        self.assertEqual(
            evaluate(c, bad, ("winter/vent/fire/3",), stamp(20), TZ).outcome, "pending"
        )
        with self.assertRaises(ContractError):
            replace(backtests()[0], available_at=stamp(10))
        with self.assertRaises(ContractError):
            qualify(c, points(), ("a", "a"), stamp(20), TZ)
