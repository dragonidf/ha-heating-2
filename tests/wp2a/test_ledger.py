import sqlite3, unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from packages.contracts import (
    ContractError,
    Unit,
    QualityStatus,
    SourceKind,
    TimeWindow,
)
from packages.offline.contracts import (
    Origin,
    EnergySlice,
    CounterPoint,
    RecoveryRequest,
    ForecastRecord,
    Cursor,
)
from packages.evidence.store import (
    EvidenceStore,
    EvidenceConflict,
    EvidenceFailure,
    record,
    checksum,
)
from packages.offline.codec import encode, decode
from packages.planner import Curve
from packages.thermal import Interval
from tests.fixtures.synthetic import reading
from tests.wp2a.helpers import temp
from tests.wp2a.test_energy import point


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.root = temp(self)
        self.store = EvidenceStore.create(self.root)
        self.origin = Origin("synthetic.heat", "synthetic.continuity", 100, 10)
        self.store.origin(self.origin)

    def test_append_identity_is_durable_idempotent_and_conflict_is_atomic(self):
        p = point(100)
        first = self.store.power(p)
        self.assertEqual(self.store.power(p), first)
        with self.assertRaises(EvidenceConflict):
            self.store.power(replace(p, kw=9))
        self.assertEqual(EvidenceStore(self.root).head(), self.store.head())
        self.assertEqual(self.store.verify(), 2)
        with self.assertRaises(EvidenceConflict):
            self.store.append(
                replace(record(p.identity, p, 100, p.stream), kind="Origin")
            )
        with self.assertRaises(EvidenceConflict):
            self.store.append(
                replace(record(p.identity, p, 100, p.stream), stream="other")
            )

    def test_45_second_hold_unknown_gap_and_restart_cannot_double_count(self):
        self.store.power(point(100))
        self.store.power(point(400))
        slices = self.store.finalize("synthetic.heat", 400, as_of=400)
        s = self.store.summary("synthetic.heat")
        self.assertAlmostEqual(s.actual_total_kwh, 10.0375)
        self.assertEqual(s.unknown_s, 255)
        self.assertEqual(self.store.finalize("synthetic.heat", 400, as_of=400), ())
        self.assertEqual(EvidenceStore(self.root).summary("synthetic.heat"), s)
        with self.assertRaises(EvidenceConflict):
            self.store.post(replace(slices[0], identity="synthetic.overlap"))
        with self.assertRaises(EvidenceConflict):
            self.store.finalize("synthetic.heat", 399, as_of=400)
        with self.assertRaises(ContractError):
            self.store.finalize("synthetic.heat", 500, as_of=400)

    def test_late_reordered_samples_are_raw_facts_not_retrospective_energy(self):
        self.store.power(point(100))
        self.store.finalize("synthetic.heat", 300, as_of=300)
        before = self.store.summary("synthetic.heat")
        _, late = self.store.power(point(200, 9))
        self.assertTrue(late)
        self.assertEqual(
            self.store.summary("synthetic.heat").actual_total_kwh,
            before.actual_total_kwh,
        )
        self.assertEqual(self.store.get(point(200, 9).identity).kind, "PowerPoint")
        self.store.finalize("synthetic.heat", 400, as_of=400)
        self.assertAlmostEqual(
            self.store.summary("synthetic.heat").actual_total_kwh,
            before.actual_total_kwh,
        )

    def test_zero_is_known_missing_and_estimates_do_not_count_as_actual(self):
        for p in (
            point(100, 0, "confirmed"),
            point(130, None, "unknown"),
            point(160, 9, "estimated"),
        ):
            self.store.power(p)
        self.store.finalize("synthetic.heat", 190, as_of=190)
        s = self.store.summary("synthetic.heat")
        self.assertEqual(s.confirmed_kwh, 0)
        self.assertEqual(s.actual_total_kwh, 10)
        self.assertAlmostEqual(s.estimated_kwh, 0.075)
        self.assertEqual(s.unknown_s, 30)

    def test_counter_switch_reset_jump_and_shared_continuity(self):
        a = CounterPoint("synthetic.c1", "synthetic.heat", 100, 30, "synthetic.counter")
        b = replace(a, identity="synthetic.c2", at=400, kwh=30.5)
        self.store.post_counter(a, b, 12)
        self.assertAlmostEqual(
            self.store.summary("synthetic.heat").actual_total_kwh, 10.5
        )
        self.store.power(point(400, 6))
        self.store.finalize("synthetic.heat", 430, as_of=430)
        self.assertAlmostEqual(
            self.store.summary("synthetic.heat").actual_total_kwh, 10.55
        )
        before = self.store.head()
        self.store.post_counter(a, b, 12)
        self.assertEqual(
            self.store.head(), before
        )  # repeated identity never adds energy
        with self.assertRaises(EvidenceConflict):
            self.store.post_counter(
                replace(a, identity="other-left"),
                replace(b, identity="other-right"),
                12,
            )
        reset = replace(b, identity="synthetic.reset", at=500, kwh=1)
        # The gap itself must be explicit, never hidden by a new counter origin.
        with self.assertRaises(EvidenceConflict):
            self.store.post_counter(b, reset, 12)
        self.store.finalize("synthetic.heat", 500, as_of=500)
        next_reset = replace(reset, identity="synthetic.reset2", at=600, kwh=0.5)
        self.assertEqual(
            self.store.post_counter(reset, next_reset, 12).method, "counter_reset"
        )
        jump = replace(next_reset, identity="synthetic.jump", at=700, kwh=100)
        self.assertEqual(
            self.store.post_counter(next_reset, jump, 12).method, "counter_jump"
        )

    def test_future_received_points_are_not_usable_early(self):
        self.store.power(replace(point(100), received=400))
        self.store.finalize("synthetic.heat", 130, as_of=130)
        self.assertEqual(self.store.summary("synthetic.heat").actual_total_kwh, 10)
        self.assertEqual(self.store.summary("synthetic.heat").unknown_s, 30)

    def test_same_timestamp_conflicting_sources_are_unknown_not_averaged(self):
        self.store.power(point(100, 3, identity="synthetic.alias1"))
        self.store.power(point(100, 9, identity="synthetic.alias2"))
        self.store.finalize("synthetic.heat", 145, as_of=145)
        self.assertEqual(self.store.summary("synthetic.heat").actual_total_kwh, 10)
        self.assertEqual(self.store.summary("synthetic.heat").unknown_s, 45)

    def test_indexed_pages_have_stable_watermark_and_bounded_cursor_scope(self):
        for at in (110, 120, 130, 140):
            self.store.power(point(at))
        page = self.store.query("synthetic.heat", "PowerPoint", 100, 200, limit=2)
        self.assertEqual([r.at for _, r in page.rows], [110, 120])
        self.assertIsNotNone(page.cursor)
        self.store.power(point(125, identity="synthetic.late-page"))
        rest = self.store.query(
            "synthetic.heat", "PowerPoint", 100, 200, limit=2, cursor=page.cursor
        )
        self.assertEqual([r.at for _, r in rest.rows], [130, 140])
        self.assertIsNone(rest.cursor)
        with self.assertRaises(EvidenceConflict):
            self.store.query("other", "PowerPoint", 100, 200, cursor=page.cursor)
        with self.assertRaises(EvidenceConflict):
            self.store.query(
                "synthetic.heat",
                "PowerPoint",
                100,
                200,
                cursor=replace(page.cursor, watermark=999),
            )
        with self.assertRaises(ContractError):
            self.store.query("synthetic.heat", "PowerPoint", 100, 200, limit=257)
        with self.store.connection() as con:
            plan = con.execute(
                "EXPLAIN QUERY PLAN SELECT seq FROM archive WHERE stream=? AND kind=? AND at>=? AND at<? ORDER BY at,seq",
                ("synthetic.heat", "PowerPoint", 100, 200),
            ).fetchall()
        self.assertTrue(any("archive_time" in str(r) for r in plan))

    def test_busy_readonly_and_batch_rollback_do_not_emit_partial_archive(self):
        before = self.store.head()
        with self.store.connection() as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaises(EvidenceFailure):
                self.store.power(point(100))
            blocker.rollback()
        self.assertEqual(self.store.head(), before)
        readonly = EvidenceStore(self.root, readonly=True)
        with self.assertRaises(EvidenceFailure):
            readonly.power(point(100))
        good = record(
            "synthetic.good",
            point(110, identity="synthetic.good"),
            110,
            "synthetic.heat",
        )
        bad = replace(good, identity="synthetic.bad")
        with self.assertRaises(EvidenceConflict):
            self.store.append_batch((good, bad))
        self.assertEqual(self.store.head(), before)

    def test_commit_failure_and_lost_after_commit_ack_are_idempotent(self):
        before = self.store.head()

        def fail(name):
            if name == "before_commit":
                raise sqlite3.OperationalError("injected synthetic write failure")

        self.store.hook = fail
        with self.assertRaises(EvidenceFailure):
            self.store.power(point(100))
        self.assertEqual(self.store.head(), before)

        def after(name):
            if name == "after_commit":
                raise OSError("injected lost ack")

        self.store.hook = after
        with self.assertRaises(EvidenceFailure):
            self.store.power(point(100))
        self.store.hook = None
        self.store.power(point(100))
        self.assertEqual(self.store.head()[0], before[0] + 1)

    def test_append_only_triggers_and_corrupt_checksum_fail_closed(self):
        with self.store.connection() as con:
            for statement in (
                "UPDATE archive SET at=1",
                "DELETE FROM archive",
                "UPDATE origins SET initial=0",
            ):
                with self.assertRaises(sqlite3.Error):
                    con.execute(statement)
            con.execute("DROP TRIGGER archive_immutable_update")
            con.execute("UPDATE archive SET checksum=? WHERE seq=1", ("f" * 64,))
        with self.assertRaises(EvidenceFailure):
            self.store.verify()
        with self.assertRaises(EvidenceFailure):
            self.store.get("origin:synthetic.heat")

    def test_version_upgrade_rollback_and_unknown_version_never_reset(self):
        root = temp(self)
        old = EvidenceStore.create(root, version=1)

        def fail(name):
            if name == "schema_before_commit":
                raise sqlite3.OperationalError("schema rollback")

        old.hook = fail
        with self.assertRaises(EvidenceFailure):
            old.migrate()
        self.assertEqual(EvidenceStore(root).version, 1)
        old.hook = None
        old.migrate()
        old.migrate()
        self.assertEqual(EvidenceStore(root).version, 2)
        with old.connection() as con:
            con.execute("PRAGMA user_version=99")
        with self.assertRaises(EvidenceFailure):
            EvidenceStore(root)

    def test_backup_is_consistent_and_does_not_overwrite_a_destination(self):
        self.store.power(point(100))
        head = self.store.head()
        destination = temp(self)
        digest = self.store.backup(destination)
        self.assertEqual(len(digest), 64)
        self.assertEqual(EvidenceStore(destination).head(), head)
        self.assertEqual(self.store.head(), head)
        with self.assertRaises(EvidenceConflict):
            self.store.backup(destination)
        self.assertEqual(self.store.checkpoint()[0], 0)

    def test_missing_or_linked_non_disposable_store_never_becomes_empty(self):
        with self.assertRaises(EvidenceFailure):
            EvidenceStore(temp(self))
        with self.assertRaises(EvidenceFailure):
            EvidenceStore.create(self.root)
        with self.assertRaises(EvidenceFailure):
            EvidenceStore(Path("/workspace"))
        root = temp(self)
        (root / "evidence.sqlite3").symlink_to(self.store.path)
        with self.assertRaises(EvidenceFailure):
            EvidenceStore(root)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.store = EvidenceStore.create(temp(self))
        self.store.origin(Origin("synthetic.heat", "synthetic.continuity", 100, 20))
        self.slices = self.store.finalize("synthetic.heat", 400, as_of=400)
        self.backup = temp(self)
        digest = self.store.backup(self.backup)
        self.request = RecoveryRequest(
            "synthetic.recover",
            tuple(s.identity for s in self.slices),
            0.5,
            20,
            digest,
            "a" * 64,
        )

    def test_preview_does_not_write_apply_is_approved_and_idempotent(self):
        before = self.store.head()
        preview = self.store.recover(
            self.request, "synthetic.heat", self.backup, dry_run=True, approved=False
        )
        self.assertEqual(self.store.head(), before)
        self.assertEqual(preview.total_after, 20.5)
        with self.assertRaises(EvidenceConflict):
            self.store.recover(
                self.request,
                "synthetic.heat",
                self.backup,
                dry_run=False,
                approved=False,
            )
        result = self.store.recover(
            self.request, "synthetic.heat", self.backup, dry_run=False, approved=True
        )
        self.assertEqual(result.total_after, 20.5)
        self.store.recover(
            self.request, "synthetic.heat", self.backup, dry_run=False, approved=True
        )
        summary = self.store.summary("synthetic.heat")
        self.assertEqual(summary.recovered_kwh, 0.5)
        self.assertEqual(summary.unknown_s, 0)
        self.assertEqual(summary.actual_total_kwh, 20.5)
        self.assertEqual(
            decode(self.store.get(self.slices[0].identity).payload).category, "unknown"
        )

    def test_stale_total_backup_identity_or_known_coverage_cannot_recover(self):
        for change in (
            dict(expected_total=0),
            dict(backup_hash="f" * 64),
            dict(unknown_ids=("origin:synthetic.heat",)),
        ):
            with self.assertRaises(EvidenceConflict):
                self.store.recover(
                    replace(self.request, **change),
                    "synthetic.heat",
                    self.backup,
                    dry_run=False,
                    approved=True,
                )
        self.store.power(point(400))
        with self.assertRaises(EvidenceConflict):
            self.store.recover(
                self.request,
                "synthetic.heat",
                self.backup,
                dry_run=False,
                approved=True,
            )

    def test_second_recovery_never_claims_the_same_unknown_interval(self):
        self.store.recover(
            self.request, "synthetic.heat", self.backup, dry_run=False, approved=True
        )
        second = temp(self)
        digest = self.store.backup(second)
        request = replace(
            self.request,
            identity="synthetic.second",
            expected_total=20.5,
            backup_hash=digest,
        )
        with self.assertRaises(EvidenceConflict):
            self.store.recover(
                request, "synthetic.heat", second, dry_run=False, approved=True
            )


class FrozenForecastTests(unittest.TestCase):
    def setUp(self):
        self.store = EvidenceStore.create(temp(self))

    def curve(self, issue, end=100001):
        return Curve(
            "synthetic.curve",
            issue,
            ((issue, Interval(20, 21)), (end, Interval(21, 22))),
            "a" * 64,
            1,
            "synthetic.plan",
            (issue,),
        )

    def latest(self, identity, issue, recorded, end=100001):
        return ForecastRecord(
            identity,
            "synthetic.cycle",
            "latest",
            100000,
            self.curve(issue, end),
            recorded,
            5,
        )

    def test_original_cutoff_exact_coverage_and_no_retroactive_backfill(self):
        for identity, issue, recorded, end in (
            ("early", 56000, 56000, 100001),
            ("exact", 56800, 56800, 100001),
            ("late", 56801, 56801, 100001),
            ("uncovered", 56800, 56800, 99999),
        ):
            self.store.forecast(self.latest(identity, issue, recorded, end))
        original = self.store.freeze_original("synthetic.cycle", 100000, as_of=99999)
        self.assertEqual(original.curve.issued, 56800)
        self.assertEqual(original.planned_kwh, 5)
        self.assertEqual(original.curve.points[-1][0], 100001)
        self.assertEqual(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=100000),
            original,
        )
        with self.assertRaises(ContractError):
            self.store.freeze_original("synthetic.cycle", 100000, as_of=100001)
        with self.assertRaises(EvidenceConflict):
            self.store.forecast(replace(original, identity="replacement"))
        with self.assertRaises(EvidenceConflict):
            self.store.freeze_original("synthetic.cycle", 100001, as_of=100000)

    def test_missing_original_stays_missing_and_latest_initial_prestart_are_separate(
        self,
    ):
        initial = replace(self.latest("initial", 60000, 60000), role="initial")
        prestart = replace(self.latest("prestart", 70000, 70000), role="prestart")
        self.store.forecast(initial)
        self.store.forecast(prestart)
        missing = self.store.freeze_original("synthetic.cycle", 100000, as_of=90000)
        self.assertIsNone(missing.curve)
        self.store.forecast(self.latest("arrived-late", 56000, 95000))
        self.assertIsNone(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=99999).curve
        )
        self.assertEqual(decode(self.store.get("initial").payload), initial)
        self.assertEqual(decode(self.store.get("prestart").payload), prestart)

    def test_comparison_requires_actual_reported_temperature_and_exact_target(self):
        self.store.forecast(self.latest("valid", 56800, 56800, 100000))
        self.store.freeze_original("synthetic.cycle", 100000, as_of=100000)
        actual = reading(21.5, Unit.CELSIUS, observed_at=100000)
        self.assertEqual(
            self.store.compare_original("synthetic.cycle", 100000, actual), (-0.5, 0.5)
        )
        for bad in (
            reading(None, Unit.CELSIUS, observed_at=100000),
            replace(actual, observed_at=99999),
            replace(
                actual, quality=replace(actual.quality, status=QualityStatus.ESTIMATED)
            ),
            replace(
                actual,
                provenance=replace(
                    actual.provenance, kind=SourceKind.DERIVED, independent=False
                ),
            ),
        ):
            self.assertIsNone(
                self.store.compare_original("synthetic.cycle", 100000, bad)
            )

    def test_late_direct_original_cannot_bypass_no_backfill_contract(self):
        with self.assertRaises(ContractError):
            ForecastRecord(
                "synthetic.retro",
                "synthetic.cycle",
                "original",
                100000,
                self.curve(56800),
                100001,
                5,
            )


class LedgerTrustBoundaryTests(unittest.TestCase):
    def test_generic_append_cannot_bypass_recovery_or_verified_energy_processing(self):
        store = EvidenceStore.create(temp(self))
        store.origin(Origin("s", "c", 100, 0))
        request = RecoveryRequest(
            "synthetic.bypass", ("missing",), 100, 0, "a" * 64, "b" * 64
        )
        with self.assertRaises(EvidenceConflict):
            store.append(record(request.identity, request, 0, "s"))
        unproven = EnergySlice(
            "synthetic.unproven",
            "s",
            "c",
            100,
            200,
            "confirmed",
            100,
            ("synthetic.fake",),
            "not_counter_delta",
        )
        with self.assertRaises(EvidenceConflict):
            store.post(unproven)
        self.assertEqual(store.summary("s").actual_total_kwh, 0)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.store = EvidenceStore.create(temp(self))
        self.store.origin(Origin("s", "c", 100, 1000))
        self.curve = Curve(
            "synthetic.initial",
            90,
            ((90, Interval(20, 21)), (400, Interval(20, 21))),
            "a" * 64,
        )
        self.initial = ForecastRecord(
            "synthetic.initial",
            "cycle",
            "initial",
            100,
            self.curve,
            90,
            5,
            TimeWindow(start=100, end=400),
        )
        self.store.forecast(self.initial)

    def test_budget_uses_scoped_known_energy_and_all_unknown_time(self):
        pending = self.store.budget("cycle", "s", 400, 7)
        self.assertEqual(pending.known_spent_kwh, 0)
        self.assertEqual(pending.unknown_s, 300)
        self.store.power(replace(point(100), stream="s"))
        self.store.finalize("s", 400, as_of=400)
        budget = self.store.budget("cycle", "s", 400, 7)
        self.assertAlmostEqual(budget.known_spent_kwh, 0.0375)
        self.assertAlmostEqual(budget.known_remaining_kwh, 4.9625)
        self.assertEqual(budget.unknown_s, 255)
        self.assertEqual(budget.projected_overrun_kwh, 2)
        self.assertEqual(decode(encode(budget)), budget)
        self.assertEqual(
            decode(self.store.get("synthetic.initial").payload), self.initial
        )

    def test_frozen_prestart_cannot_be_invented_after_cycle_start(self):
        with self.assertRaises(ContractError):
            replace(self.initial, role="prestart", recorded_at=101)
        with self.assertRaises(ContractError):
            replace(self.initial, role="initial", recorded_at=101)
        with self.assertRaises(EvidenceConflict):
            self.store.budget("missing", "s", 400, 7)
        self.store.forecast(
            replace(
                self.initial,
                identity="synthetic.no-budget",
                cycle_id="missing-cap",
                planned_kwh=None,
            )
        )
        missing = self.store.budget("missing-cap", "s", 400, 7)
        self.assertIsNone(missing.reference_kwh)
        self.assertIsNone(missing.known_remaining_kwh)
        self.assertIsNone(missing.projected_overrun_kwh)

    def test_full_recovery_counts_in_scope_partial_recovery_distribution_stays_unknown(
        self,
    ):
        slices = self.store.finalize("s", 400, as_of=400)
        backup = temp(self)
        digest = self.store.backup(backup)
        request = RecoveryRequest(
            "synthetic.recover.scope",
            tuple(s.identity for s in slices),
            0.5,
            1000,
            digest,
            "a" * 64,
        )
        self.store.recover(request, "s", backup, dry_run=False, approved=True)
        full = self.store.budget("cycle", "s", 400, 6)
        partial = self.store.budget("cycle", "s", 200, 6)
        self.assertEqual(full.known_spent_kwh, 0.5)
        self.assertEqual(full.unknown_s, 0)
        self.assertEqual(partial.known_spent_kwh, 0)
        self.assertEqual(partial.unknown_s, 100)


class MaterializedIndexTests(unittest.TestCase):
    def test_corrupted_origin_index_cannot_rewrite_a_canonical_total(self):
        store = EvidenceStore.create(temp(self))
        store.origin(Origin("s", "c", 100, 10))
        with store.connection() as con:
            con.execute("DROP TRIGGER origins_immutable_update")
            con.execute("UPDATE origins SET initial=0")
        with self.assertRaises(EvidenceFailure):
            store.summary("s")

    def test_corrupted_energy_index_cannot_hide_or_repeat_accounted_energy(self):
        store = EvidenceStore.create(temp(self))
        store.origin(Origin("synthetic.heat", "c", 100, 0))
        store.power(point(100))
        store.finalize("synthetic.heat", 130, as_of=130)
        with store.connection() as con:
            con.execute("DROP TRIGGER energy_immutable_update")
            con.execute("UPDATE energy SET end=200")
        with self.assertRaises(EvidenceFailure):
            store.summary("synthetic.heat")
        with self.assertRaises(EvidenceFailure):
            store.finalize("synthetic.heat", 300, as_of=300)


class EnergyScopeTests(unittest.TestCase):
    def test_unscoped_old_forecast_is_preserved_but_not_a_verified_budget(self):
        store = EvidenceStore.create(temp(self))
        store.origin(Origin("s", "c", 100, 10))
        curve = Curve(
            "synthetic.curve",
            90,
            ((90, Interval(20, 20)), (400, Interval(21, 21))),
            "a" * 64,
        )
        forecast = ForecastRecord("initial", "cycle", "initial", 100, curve, 90, 5)
        store.forecast(forecast)
        budget = store.budget("cycle", "s", 200, 6)
        self.assertEqual(decode(store.get("initial").payload).planned_kwh, 5)
        self.assertIsNone(budget.reference_kwh)
        self.assertIsNone(budget.projected_overrun_kwh)
        self.assertIsNone(budget.scope)
        self.assertEqual(budget.actual_until, 200)
        scoped = replace(
            forecast,
            identity="other-initial",
            cycle_id="other-cycle",
            energy_scope=TimeWindow(start=100, end=400),
        )
        store.forecast(scoped)
        with self.assertRaises(EvidenceConflict):
            store.budget("other-cycle", "s", 401, 6)
