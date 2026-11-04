"""Original12h selection uses synthetic receipt availability, not issue time alone."""

import unittest
from packages.offline.contracts import ForecastRecord
from packages.evidence.store import EvidenceStore
from packages.planner import Curve
from packages.thermal import Interval
from tests.wp2a.helpers import temp


class OriginalReceiptTests(unittest.TestCase):
    def setUp(self):
        self.store = EvidenceStore.create(temp(self))

    def latest(self, identity="synthetic.late", issue=56000, received=95000):
        return ForecastRecord(
            identity,
            "synthetic.cycle",
            "latest",
            100000,
            Curve(
                identity,
                issue,
                ((issue, Interval(18, 19)), (100001, Interval(20, 21))),
                "a" * 64,
                7,
                "synthetic.plan",
                (issue - 100,),
            ),
            received,
            5,
        )

    def test_late_first_freeze_rejects_early_issue_received_after_cutoff(self):
        self.store.forecast(self.latest())
        original = self.store.freeze_original("synthetic.cycle", 100000, as_of=96000)
        self.assertIsNone(original.curve)
        self.assertIsNone(original.planned_kwh)
        self.assertIsNone(original.energy_scope)

    def test_early_receipt_late_invocation_retains_complete_lineage_and_energy(self):
        from dataclasses import replace
        from packages.contracts import TimeWindow
        from packages.offline.codec import decode

        source = replace(
            self.latest(received=56800),
            energy_scope=TimeWindow(start=100000, end=100001),
        )
        self.store.forecast(source)
        original = self.store.freeze_original("synthetic.cycle", 100000, as_of=96000)
        self.assertEqual(original.curve, source.curve)
        self.assertEqual(original.curve.model_revision, 7)
        self.assertEqual(original.curve.plan_id, "synthetic.plan")
        self.assertEqual(original.curve.source_issued, (55900,))
        self.assertEqual(original.planned_kwh, source.planned_kwh)
        self.assertEqual(original.energy_scope, source.energy_scope)
        self.assertEqual(
            original.recorded_at, 96000
        )  # freeze invocation, not source receipt
        self.assertEqual(decode(self.store.get(source.identity).payload), source)

    def test_issue_and_receipt_exactly_at_cutoff_are_eligible(self):
        source = self.latest(issue=56800, received=56800)
        self.store.forecast(source)
        self.assertEqual(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=56800).curve,
            source.curve,
        )

    def test_receipt_just_after_cutoff_is_ineligible_even_at_cycle_reference(self):
        self.store.forecast(self.latest(received=56800.000001))
        self.assertIsNone(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=100000).curve
        )

    def test_issue_just_after_cutoff_is_ineligible(self):
        self.store.forecast(self.latest(issue=56800.000001, received=56800.000001))
        self.assertIsNone(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=100000).curve
        )

    def test_as_of_before_cutoff_cannot_use_not_yet_received_forecast(self):
        self.store.forecast(self.latest(received=56700))
        self.assertIsNone(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=56699).curve
        )

    def test_late_received_newer_issue_does_not_displace_eligible_older_reference(self):
        early = self.latest("synthetic.early", issue=55000, received=56000)
        late = self.latest("synthetic.late", issue=56800, received=95000)
        self.store.forecast(early)
        self.store.forecast(late)
        self.assertEqual(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=96000).curve,
            early.curve,
        )

    def test_missing_is_immutable_after_later_and_backdated_arrival_and_restart(self):
        self.store.forecast(self.latest())
        missing = self.store.freeze_original("synthetic.cycle", 100000, as_of=96000)
        self.assertIsNone(missing.curve)
        archived = self.store.get(missing.identity)
        self.store.forecast(self.latest("synthetic.later", received=97000))
        self.store.forecast(self.latest("synthetic.backdated", received=56000))
        reopened = EvidenceStore(self.store.root)
        before = reopened.head()
        self.assertEqual(
            reopened.freeze_original("synthetic.cycle", 100000, as_of=100000), missing
        )
        self.assertEqual(reopened.head(), before)
        self.assertEqual(reopened.get(missing.identity), archived)

    def test_valid_historical_original_cannot_be_replaced_or_rewritten(self):
        import sqlite3
        from dataclasses import replace
        from packages.evidence.store import EvidenceConflict

        source = self.latest(received=56000)
        self.store.forecast(source)
        original = self.store.freeze_original("synthetic.cycle", 100000, as_of=96000)
        archived = self.store.get(original.identity)
        self.store.forecast(self.latest("synthetic.new", issue=56800, received=56800))
        before = self.store.head()
        self.assertEqual(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=100000),
            original,
        )
        self.assertEqual(self.store.head(), before)
        with self.assertRaises(EvidenceConflict):
            self.store.forecast(replace(original, identity="synthetic.replacement"))
        for statement in (
            "UPDATE archive SET at=1 WHERE id=?",
            "DELETE FROM archive WHERE id=?",
        ):
            with self.store.connection() as con:
                with self.assertRaises(sqlite3.Error):
                    con.execute(statement, (original.identity,))
        self.assertEqual(
            EvidenceStore(self.store.root).get(original.identity), archived
        )

    def test_latest_prestart_and_initial_keep_their_existing_time_rules(self):
        from dataclasses import replace
        from packages.offline.codec import decode

        for role in ("latest", "prestart", "initial"):
            source = replace(self.latest(identity="synthetic." + role), role=role)
            self.store.forecast(source)
            self.assertEqual(decode(self.store.get(source.identity).payload), source)
        missing = self.store.freeze_original("synthetic.cycle", 100000, as_of=96000)
        self.assertIsNone(missing.curve)

    def test_index_cannot_backdate_immutable_payload_receipt(self):
        source = self.latest()
        self.store.forecast(source)
        with self.store.connection() as con:
            # Deliberate corruption of the disposable derived index only.
            con.execute("DROP TRIGGER forecasts_immutable_update")
            con.execute(
                "UPDATE forecasts SET recorded=56000 WHERE cycle=?", (source.cycle_id,)
            )
        self.assertIsNone(
            self.store.freeze_original("synthetic.cycle", 100000, as_of=96000).curve
        )
