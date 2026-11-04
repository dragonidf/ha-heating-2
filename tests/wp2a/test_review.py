"""Regressions for PR16 independent review; entirely synthetic evidence."""

import unittest
from dataclasses import replace
from packages.contracts import Action, TimeWindow
from packages.offline.contracts import Origin, RecoveryRequest
from packages.evidence.store import EvidenceStore, EvidenceConflict
from tests.wp2a.helpers import temp, harness, planned, event, load


class ReviewReproductions(unittest.TestCase):
    def test_recovery_random_evidence_hash_cannot_qualify_actual_energy(self):
        store = EvidenceStore.create(temp(self))
        store.origin(Origin("synthetic.heat", "synthetic.c", 100, 0))
        slices = store.finalize("synthetic.heat", 400, as_of=400)
        backup = temp(self)
        request = RecoveryRequest(
            "synthetic.r",
            tuple(s.identity for s in slices),
            999,
            0,
            store.backup(backup),
            "a" * 64,
        )
        before = store.head()
        with self.assertRaises(EvidenceConflict):
            store.recover(
                request, "synthetic.heat", backup, dry_run=False, approved=True
            )
        self.assertEqual(store.head(), before)
        self.assertEqual(store.summary("synthetic.heat").unknown_s, 300)

    def test_current_missing_manual_reading_persists_ownership_fence(self):
        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        binding = runtime.client.registry.bindings[2]
        clock = replace(clock, utc=107, monotonic=1007)
        assertion = replace(
            event(binding, 107, 19, 3, author="manual", observed_action=Action.HEAT),
            reading=None,
        )
        runtime.client.push(assertion)
        runtime.drain_events(clock)
        self.assertTrue(runtime.simulator.state.manual_paused)
        self.assertTrue(runtime.simulator.store.view().state.manual_paused)
        load(runtime, 108, 4)
        self.assertTrue(runtime.simulator.state.manual_paused)

    def test_queue_forecast_initial_produces_scoped_budget_end_to_end(self):
        runtime, _ = harness(self)
        _, proposal, request = planned(runtime, with_request=True)
        reference = request.state.at + 100
        forecast = runtime.queue_forecast(
            proposal, request, "synthetic.cycle", reference, role="initial"
        )
        scope = TimeWindow(start=reference, end=request.slots[-1].window.end)
        self.assertEqual(forecast.energy_scope, scope)
        expected = (
            sum(
                max(0, min(s.end, scope.end) - max(s.start, scope.start))
                for s in proposal.segments
            )
            * proposal.power_kw
            / 3600
        )
        self.assertAlmostEqual(forecast.planned_kwh, expected)
        runtime.flush_evidence()
        runtime.evidence.origin(Origin("synthetic.heat", "synthetic.c", reference, 0))
        runtime.evidence.finalize(
            "synthetic.heat", reference + 30, as_of=reference + 30
        )
        budget = runtime.evidence.budget(
            "synthetic.cycle", "synthetic.heat", reference + 30, expected + 1
        )
        self.assertEqual(budget.reference_kwh, forecast.planned_kwh)
        self.assertEqual(budget.unknown_s, 30)
        self.assertAlmostEqual(budget.projected_overrun_kwh, 1)


class RecoveryProofRegressions(unittest.TestCase):
    def setup_claim(self, **changes):
        from tests.wp2a.helpers import recovery_proof

        store = EvidenceStore.create(temp(self))
        store.origin(Origin("synthetic.heat", "synthetic.c", 100, 20))
        slices = store.finalize("synthetic.heat", 400, as_of=400)
        digest = recovery_proof(store, slices, 0.5, **changes)
        backup = temp(self)
        request = RecoveryRequest(
            "synthetic.claim",
            tuple(s.identity for s in slices),
            0.5,
            20,
            store.backup(backup),
            digest,
        )
        return store, backup, request

    def reject(self, store, backup, request):
        before = store.head()
        with self.assertRaises(EvidenceConflict):
            store.recover(
                request, "synthetic.heat", backup, dry_run=False, approved=True
            )
        self.assertEqual(store.head(), before)
        self.assertEqual(store.summary("synthetic.heat").actual_total_kwh, 20)
        self.assertEqual(store.summary("synthetic.heat").unknown_s, 300)

    def test_altered_hash_and_amount_never_qualify(self):
        for changes in (dict(evidence_hash="b" * 64), dict(kwh=500), dict(kwh=0.4)):
            with self.subTest(changes=changes):
                store, backup, request = self.setup_claim()
                self.reject(store, backup, replace(request, **changes))

    def test_proof_binds_source_physical_identity_time_and_continuity(self):
        for changes in (
            dict(source_id="synthetic.other"),
            dict(physical_id="synthetic.other"),
            dict(window=TimeWindow(start=101, end=400)),
            dict(continuity="synthetic.other"),
            dict(left_id="synthetic.absent"),
            dict(right_id="synthetic.absent"),
        ):
            with self.subTest(changes=changes):
                store, backup, request = self.setup_claim(**changes)
                self.reject(store, backup, request)

    def test_wrong_gap_or_stream_and_amount_in_proof_are_rejected(self):
        for changes in (dict(unknown_ids=("synthetic.other-gap",)), dict(kwh=0.4)):
            store, backup, request = self.setup_claim(**changes)
            if "kwh" in changes:
                request = replace(
                    request, kwh=0.4
                )  # even a matching forged claim fails raw delta
            self.reject(store, backup, request)
        store, backup, request = self.setup_claim()
        self.reject(
            store, backup, replace(request, unknown_ids=("origin:synthetic.heat",))
        )

    def test_estimated_missing_or_derived_counter_is_not_actual(self):
        from packages.contracts import QualityStatus, SourceKind
        from packages.offline.codec import decode, encode
        from packages.evidence.store import record, checksum

        for mode in (
            "estimated",
            "missing",
            "derived",
            "dependent",
            "wrong_unit",
            "time",
            "reset",
        ):
            with self.subTest(mode=mode):
                store, _, request = self.setup_claim()
                proof = decode(store.get(request.evidence_hash).payload)
                raw = decode(store.get(proof.right_id).payload)
                if mode == "estimated":
                    raw = replace(
                        raw,
                        quality=replace(raw.quality, status=QualityStatus.ESTIMATED),
                    )
                elif mode == "missing":
                    raw = replace(
                        raw,
                        value=None,
                        quality=replace(raw.quality, status=QualityStatus.MISSING),
                    )
                elif mode == "derived":
                    raw = replace(
                        raw,
                        provenance=replace(
                            raw.provenance, kind=SourceKind.DERIVED, independent=False
                        ),
                    )
                elif mode == "dependent":
                    raw = replace(
                        raw, provenance=replace(raw.provenance, independent=False)
                    )
                elif mode == "wrong_unit":
                    from packages.contracts import Unit

                    raw = replace(raw, unit=Unit.WATT)
                elif mode == "time":
                    raw = replace(raw, observed_at=399)
                else:
                    left = decode(store.get(proof.left_id).payload)
                    left = replace(left, value=0.6)
                    store.append(
                        record("synthetic.reset-left", left, 100, "synthetic.heat")
                    )
                    proof = replace(proof, left_id="synthetic.reset-left")
                store.append(
                    record("synthetic.bad-reading", raw, 400, "synthetic.heat")
                )
                proof = replace(proof, right_id="synthetic.bad-reading")
                digest = checksum(encode(proof))
                store.append(record(digest, proof, 400, "synthetic.heat"))
                backup = temp(self)
                request = replace(
                    request, evidence_hash=digest, backup_hash=store.backup(backup)
                )
                self.reject(store, backup, request)

    def test_estimated_proof_cannot_be_approved_into_actual(self):
        from packages.contracts import QualityStatus

        store, backup, request = self.setup_claim(quality=QualityStatus.ESTIMATED)
        self.reject(store, backup, request)

    def test_zero_delta_is_proven_zero_and_raw_proof_roundtrips(self):
        from tests.wp2a.helpers import recovery_proof
        from packages.offline.codec import decode, encode

        store = EvidenceStore.create(temp(self))
        store.origin(Origin("synthetic.heat", "synthetic.c", 100, 0))
        slices = store.finalize("synthetic.heat", 200, as_of=200)
        digest = recovery_proof(store, slices, 0)
        proof = decode(store.get(digest).payload)
        self.assertEqual(decode(encode(proof)), proof)
        backup = temp(self)
        r = RecoveryRequest(
            "synthetic.zero",
            tuple(s.identity for s in slices),
            0,
            0,
            store.backup(backup),
            digest,
        )
        store.recover(r, "synthetic.heat", backup, dry_run=False, approved=True)
        self.assertEqual(store.summary("synthetic.heat").actual_total_kwh, 0)
        self.assertEqual(store.summary("synthetic.heat").unknown_s, 0)

    def test_failed_commit_and_lost_ack_preserve_atomic_claim_and_retry_receipt(self):
        import sqlite3
        from packages.evidence.store import EvidenceFailure

        for where, expected in (("before_commit", 20), ("after_commit", 20.5)):
            store, backup, request = self.setup_claim()

            def fail(point):
                if point == where:
                    raise sqlite3.OperationalError("synthetic lost write/ack")

            store.hook = fail
            with self.assertRaises(EvidenceFailure):
                store.recover(
                    request, "synthetic.heat", backup, dry_run=False, approved=True
                )
            opened = EvidenceStore(store.root)
            self.assertEqual(
                opened.summary("synthetic.heat").actual_total_kwh, expected
            )
            receipt = opened.recover(
                request, "synthetic.heat", backup, dry_run=False, approved=True
            )
            self.assertEqual(
                opened.recover(
                    request, "synthetic.heat", backup, dry_run=False, approved=True
                ),
                receipt,
            )
            self.assertEqual(opened.summary("synthetic.heat").recovered_kwh, 0.5)
            self.assertEqual(opened.summary("synthetic.heat").unknown_s, 0)

    def test_process_kill_recovery_claims_commit_together(self):
        import subprocess, sys

        for checkpoint, expected in (("before_commit", 20), ("after_commit", 20.5)):
            store, backup, request = self.setup_claim()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.wp2a.crash_worker",
                    str(store.root),
                    "recovery",
                    checkpoint,
                    str(backup),
                    request.evidence_hash,
                    request.backup_hash,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 77, result.stdout + result.stderr)
            opened = EvidenceStore(store.root)
            self.assertEqual(
                opened.summary("synthetic.heat").actual_total_kwh, expected
            )
            opened.recover(
                request, "synthetic.heat", backup, dry_run=False, approved=True
            )
            self.assertEqual(opened.summary("synthetic.heat").recovered_kwh, 0.5)
            opened.verify()

    def test_existing_archive_under_wrong_digest_cannot_substitute_proof(self):
        from packages.evidence.store import record
        from packages.offline.codec import decode

        store, _, request = self.setup_claim()
        proof = decode(store.get(request.evidence_hash).payload)
        wrong = "e" * 64
        store.append(record(wrong, proof, 400, "synthetic.heat"))
        backup = temp(self)
        request = replace(
            request, evidence_hash=wrong, backup_hash=store.backup(backup)
        )
        self.reject(store, backup, request)

    def test_proof_cannot_be_reused_for_another_stream(self):
        store, _, request = self.setup_claim()
        store.origin(Origin("synthetic.other", "synthetic.other.c", 100, 20))
        store.finalize("synthetic.other", 400, as_of=400)
        backup = temp(self)
        request = replace(request, backup_hash=store.backup(backup))
        with self.assertRaises(EvidenceConflict):
            store.recover(
                request, "synthetic.other", backup, dry_run=False, approved=True
            )
        self.assertEqual(store.summary("synthetic.other").actual_total_kwh, 20)

    def test_noncontiguous_unknown_gaps_cannot_recover_known_middle(self):
        from tests.wp2a.helpers import recovery_proof
        from tests.wp2a.test_energy import point

        store = EvidenceStore.create(temp(self))
        store.origin(Origin("synthetic.heat", "synthetic.c", 100, 20))
        first = store.finalize("synthetic.heat", 200, as_of=200)
        store.power(point(200, 0))
        spans = store.finalize("synthetic.heat", 400, as_of=400)
        unknown = first + tuple(s for s in spans if s.category == "unknown")
        digest = recovery_proof(store, unknown, 0.5)
        backup = temp(self)
        r = RecoveryRequest(
            "synthetic.claim",
            tuple(s.identity for s in unknown),
            0.5,
            20,
            store.backup(backup),
            digest,
        )
        with self.assertRaises(EvidenceConflict):
            store.recover(r, "synthetic.heat", backup, dry_run=False, approved=True)
        self.assertEqual(store.summary("synthetic.heat").unknown_s, 255)

    def test_old_unproven_recovery_records_fail_closed_on_summary_and_budget(self):
        from packages.evidence.store import record
        from packages.offline.contracts import ForecastRecord
        from packages.planner import Curve
        from packages.thermal import Interval

        store, _, request = self.setup_claim()
        # Model an old v2 archive, whose former writer allowed a dummy hash.
        request = replace(request, evidence_hash="a" * 64)
        with store.transaction() as con:
            store._append(
                con,
                record(request.identity, request, 0, "synthetic.heat"),
                recovery=True,
            )
        with self.assertRaises(EvidenceConflict):
            store.summary("synthetic.heat")
        curve = Curve(
            "synthetic.old",
            100,
            ((100, Interval(18, 18)), (400, Interval(18, 18))),
            "a" * 64,
            1,
            "synthetic.old",
            (100,),
        )
        store.forecast(
            ForecastRecord(
                "synthetic.initial",
                "synthetic.cycle",
                "initial",
                100,
                curve,
                100,
                1,
                TimeWindow(start=100, end=400),
            )
        )
        with self.assertRaises(EvidenceConflict):
            store.budget("synthetic.cycle", "synthetic.heat", 400, 1)

    def test_typed_proof_rejects_duplicate_ids_method_and_mutation(self):
        from dataclasses import FrozenInstanceError
        from packages.contracts import ContractError
        from packages.offline.codec import decode

        store, _, request = self.setup_claim()
        proof = decode(store.get(request.evidence_hash).payload)
        for changes in (
            dict(unknown_ids=proof.unknown_ids * 2),
            dict(method="estimate"),
            dict(right_id=proof.left_id),
            dict(kwh=float("nan")),
        ):
            with self.assertRaises(ContractError):
                replace(proof, **changes)
        with self.assertRaises(FrozenInstanceError):
            proof.kwh = 99


class OwnershipRegressions(unittest.TestCase):
    def test_unknown_manual_and_untrusted_echo_missing_state_pause_durably(self):
        for author in ("manual", "unknown", "automatic_echo"):
            runtime, session = harness(self)
            clock, _ = planned(runtime)
            clock = replace(clock, utc=107, monotonic=1007)
            binding = runtime.client.registry.bindings[2]
            source = replace(
                event(binding, 107, 19, 3, author=author, observed_action=Action.HEAT),
                reading=None,
            )
            runtime.client.push(source)
            runtime.drain_events(clock)
            owner = runtime.simulator.state.owner_epoch
            self.assertTrue(runtime.simulator.state.manual_paused)
            self.assertIsNone(runtime.simulator.state.plan)
            self.assertTrue(runtime.simulator.store.view().state.manual_paused)
            self.assertIsNone(runtime.deliver(source, clock))
            self.assertEqual(runtime.simulator.state.owner_epoch, owner)
            later = load(runtime, 108, 4)
            self.assertTrue(runtime.simulator.state.manual_paused)
            self.assertFalse(runtime.pump(later))
            runtime.resume(later, session)
            self.assertFalse(runtime.simulator.state.manual_paused)
            self.assertFalse(runtime.simulator.state.reconciled)
            self.assertFalse(runtime.pump(later))
            runtime.reconcile(later, session, action=Action.STOP, writers_known=True)
            self.assertIsNone(runtime.simulator.state.plan)

    def test_unqualified_fresh_reading_pauses_without_invented_action(self):
        from packages.contracts import QualityStatus
        from unittest.mock import patch

        for quality in (QualityStatus.ESTIMATED, QualityStatus.MISSING):
            runtime, _ = harness(self)
            clock, _ = planned(runtime)
            clock = replace(clock, utc=107, monotonic=1007)
            source = event(
                runtime.client.registry.bindings[2],
                107,
                19,
                3,
                author="manual",
                observed_action=Action.HEAT,
            )
            source = replace(
                source,
                reading=replace(
                    source.reading,
                    value=None if quality is QualityStatus.MISSING else 19,
                    quality=replace(source.reading.quality, status=quality),
                ),
            )
            with patch.object(
                runtime.simulator.actuator,
                "feedback",
                wraps=runtime.simulator.actuator.feedback,
            ) as feedback:
                runtime.deliver(source, clock)
                self.assertIsNone(feedback.call_args.args[0])
                self.assertFalse(feedback.call_args.kwargs["writers_known"])
            self.assertTrue(runtime.simulator.store.view().state.manual_paused)

    def test_delayed_future_out_of_order_and_replayed_author_assertions(self):
        for received, seq in ((90, 3), (108, 3), (107, 1)):
            runtime, _ = harness(self)
            clock, _ = planned(runtime)
            clock = replace(clock, utc=107, monotonic=1007)
            source = replace(
                event(
                    runtime.client.registry.bindings[2],
                    received,
                    19,
                    seq,
                    author="manual",
                ),
                identity="synthetic.delayed",
                reading=None,
            )
            runtime.deliver(source, clock)
            self.assertFalse(runtime.simulator.state.manual_paused)
            self.assertIsNone(runtime.deliver(source, clock))

    def test_fresh_author_assertion_with_aged_state_still_fences_ownership(self):
        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        clock = replace(clock, utc=117, monotonic=1017)
        source = event(
            runtime.client.registry.bindings[2], 117, 19, 3, author="unknown"
        )
        # No observation-clock rollback: state simply stopped updating before the author assertion.
        source = replace(source, reading=replace(source.reading, observed_at=106))
        runtime.deliver(source, clock)
        self.assertTrue(runtime.simulator.store.view().state.manual_paused)

    def test_arbitrary_serialized_author_cannot_authenticate_observed_heat(self):
        from packages.offline.codec import encode, decode
        from unittest.mock import patch

        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        clock = replace(clock, utc=107, monotonic=1007)
        source = event(
            runtime.client.registry.bindings[2],
            107,
            19,
            3,
            author="manual",
            observed_action=Action.HEAT,
        )
        with patch.object(
            runtime.simulator.actuator,
            "feedback",
            wraps=runtime.simulator.actuator.feedback,
        ) as feedback:
            runtime.deliver(decode(encode(source)), clock)
            self.assertIsNone(feedback.call_args.args[0])
            self.assertFalse(feedback.call_args.kwargs["manual"])
        self.assertTrue(runtime.simulator.state.manual_paused)


class ForecastScopeRegressions(unittest.TestCase):
    def test_prefix_exclusion_half_slot_reference_and_immutable_budget(self):
        from packages.offline.codec import decode

        runtime, _ = harness(self)
        _, p, req = planned(runtime, with_request=True)
        reference = req.state.at + 150
        f = runtime.queue_forecast(
            p, req, "synthetic.prefix", reference, role="initial"
        )
        expected = (
            sum(max(0, s.end - max(s.start, reference)) for s in p.segments)
            * p.power_kw
            / 3600
        )
        self.assertLess(expected, p.energy_kwh)
        self.assertAlmostEqual(f.planned_kwh, expected)
        runtime.flush_evidence()
        self.assertEqual(decode(runtime.evidence.get(f.identity).payload), f)
        self.assertEqual(runtime.evidence.forecast(f), runtime.evidence.forecast(f))
        with self.assertRaises(EvidenceConflict):
            runtime.evidence.forecast(replace(f, identity="synthetic.replace"))

    def test_reference_outside_horizon_or_unqualified_power_keeps_budget_unavailable(
        self,
    ):
        for mode in (
            "before",
            "after",
            "unknown_power",
            "limits",
            "other_stage",
            "trajectory",
        ):
            runtime, _ = harness(self)
            _, p, req = planned(runtime, with_request=True)
            ref = req.state.at
            if mode == "before":
                ref -= 1
            elif mode == "after":
                ref = req.slots[-1].window.end
            elif mode == "unknown_power":
                p = replace(p, power_kw=None)
            elif mode == "limits":
                req = replace(req, limits_qualified=False)
            elif mode == "other_stage":
                p = replace(p, power_kw=99)
            else:
                p = replace(p, trajectory=p.trajectory[:-1])
            f = runtime.queue_forecast(
                p,
                req,
                "synthetic.unscoped",
                ref,
                role="latest" if mode == "before" else "initial",
            )
            self.assertIsNone(f.energy_scope)
            self.assertIsNone(f.planned_kwh)
            runtime.flush_evidence()
            if mode != "before":
                runtime.evidence.origin(Origin("synthetic.heat", "c", ref, 0))
                b = runtime.evidence.budget(
                    "synthetic.unscoped", "synthetic.heat", ref + 30, 2
                )
                self.assertIsNone(b.reference_kwh)
                self.assertIsNone(b.known_remaining_kwh)
                self.assertIsNone(b.projected_overrun_kwh)

    def test_scoped_zero_heat_and_known_energy_with_unknown_tail(self):
        from tests.wp2a.test_energy import point

        runtime, _ = harness(self)
        _, p, req = planned(runtime, with_request=True)
        f = runtime.queue_forecast(
            replace(p, segments=(), segment_reasons=(), energy_kwh=0),
            req,
            "synthetic.zero",
            req.state.at,
            role="initial",
        )
        self.assertIsNotNone(f.energy_scope)
        self.assertEqual(f.planned_kwh, 0)
        runtime.flush_evidence()
        runtime.evidence.origin(Origin("synthetic.heat", "c", req.state.at, 0))
        runtime.evidence.power(point(req.state.at, 3))
        runtime.evidence.finalize(
            "synthetic.heat", req.state.at + 90, as_of=req.state.at + 90
        )
        b = runtime.evidence.budget(
            "synthetic.zero", "synthetic.heat", req.state.at + 90, 1
        )
        self.assertEqual(b.unknown_s, 45)
        self.assertAlmostEqual(b.known_spent_kwh, 0.0375)
        self.assertAlmostEqual(b.known_remaining_kwh, -0.0375)
        with self.assertRaises(EvidenceConflict):
            runtime.evidence.budget(
                "synthetic.zero", "synthetic.heat", f.energy_scope.end + 1, 1
            )

    def test_outside_or_overlapping_energy_segments_cannot_get_scope(self):
        from packages.contracts import ContractError

        runtime, _ = harness(self)
        _, p, req = planned(runtime, with_request=True)
        for segments in (
            (replace(p.segments[0], start=req.state.at - 1),),
            (p.segments[0], p.segments[0]),
        ):
            with self.assertRaises(ContractError):
                runtime.queue_forecast(
                    replace(p, segments=segments),
                    req,
                    "synthetic.invalid",
                    req.state.at,
                    role="initial",
                )
