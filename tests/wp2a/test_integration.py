import unittest
from unittest.mock import patch
from tests.wp2a.helpers import harness, planned


class IndependentStopTests(unittest.TestCase):
    def test_stop_does_not_read_critical_or_evidence_store(self):
        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        self.assertTrue(runtime.pump(clock))
        with patch.object(
            runtime.simulator.store,
            "view",
            side_effect=AssertionError("disk forbidden"),
        ):
            runtime.trusted_stop(clock)

    def test_stale_manual_report_cannot_fabricate_new_manual_ownership(self):
        from dataclasses import replace
        from tests.wp2a.helpers import event
        from packages.contracts import Clock

        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        b = next(b for b in runtime.client.registry.bindings if b.role == "thermostat")
        report = event(b, 107, 19, 3, author="manual")
        report = replace(report, reading=replace(report.reading, observed_at=100))
        runtime.deliver(report, replace(clock, utc=107, monotonic=1007))
        self.assertFalse(runtime.simulator.state.manual_paused)


class IntegrationTests(unittest.TestCase):
    def test_source_to_snapshot_planner_store_and_fake_ack_are_distinct(self):
        from packages.contracts import Action, ReceiptStage

        runtime, _ = harness(self)
        clock, p = planned(runtime)
        self.assertTrue(runtime.pump(clock))
        self.assertFalse(runtime.pump(clock))
        intent = runtime.simulator.state.last_intent
        self.assertEqual(
            runtime.simulator.store.receipt(intent.intent_id).stage, ReceiptStage.SENT
        )
        runtime.simulator.ack(clock)
        runtime.simulator.echo(clock)
        self.assertIsNone(
            runtime.simulator.store.receipt(intent.intent_id).physical_effect_at
        )
        self.assertEqual(
            sum(c.action is Action.HEAT for c in runtime.simulator.actuator.calls), 1
        )
        self.assertGreater(runtime.flush_evidence(), 0)
        self.assertGreater(runtime.evidence.verify(), 0)
        self.assertTrue(all(s.conditional for s in p.segments))

    def test_manual_unknown_and_self_labelled_echo_never_acquire_automatic_authority(
        self,
    ):
        from dataclasses import replace
        from packages.contracts import Action
        from tests.wp2a.helpers import event

        for author in ("manual", "unknown", "automatic_echo"):
            runtime, _ = harness(self)
            clock, _ = planned(runtime)
            runtime.pump(clock)
            b = next(
                b for b in runtime.client.registry.bindings if b.role == "thermostat"
            )
            runtime.deliver(
                event(b, 107, 20, 3, author=author, observed_action=Action.HEAT),
                replace(clock, utc=107, monotonic=1007),
            )
            self.assertTrue(runtime.simulator.state.manual_paused)
            self.assertFalse(runtime.pump(replace(clock, utc=107, monotonic=1007)))
            restored = runtime.simulator.store.view().state
            self.assertTrue(restored.manual_paused)

    def test_permission_revocation_immediately_stops_and_old_sessions_are_fenced(self):
        from packages.contracts import Action, ContractError

        runtime, session = harness(self)
        clock, _ = planned(runtime)
        runtime.pump(clock)
        runtime.revoke(session.principal.identity, clock)
        self.assertEqual(runtime.simulator.actuator.calls[-1].action, Action.STOP)
        self.assertFalse(runtime.pump(clock))
        with self.assertRaises(ContractError):
            runtime.resume(clock, session)

    def test_serialized_emergency_authorized_flag_is_not_a_trusted_capability(self):
        from packages.contracts import EventKind, Action

        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        runtime.pump(clock)
        e = runtime._event(EventKind.SAFETY_STOP, clock)
        from dataclasses import replace

        before = runtime.simulator.actuator.calls
        runtime.emergency(replace(e, authorized=True), clock)
        self.assertEqual(runtime.simulator.actuator.calls, before)
        runtime.emergency(e, clock, runtime.simulator.authority.attest(e))
        self.assertEqual(runtime.simulator.actuator.calls[-1].action, Action.STOP)

    def test_disconnect_reconnect_stale_sources_do_not_resume_heat(self):
        from dataclasses import replace
        from packages.contracts import Action
        from tests.wp2a.helpers import load

        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        runtime.pump(clock)
        runtime.client.disconnect()
        self.assertIsNone(runtime.snapshot(clock).grid_actual)
        self.assertFalse(runtime.pump(clock))
        self.assertEqual(runtime.simulator.actuator.calls[-1].action, Action.STOP)
        runtime.client.connect()
        self.assertIsNone(runtime.snapshot(clock).room)
        later = load(runtime, 107, 3)
        self.assertFalse(
            runtime.pump(later)
        )  # no automatic restoration of discarded active plan
        self.assertFalse(runtime.simulator.state.reconciled)

    def test_old_reordered_event_and_duplicate_are_not_fresh_readings(self):
        from tests.wp2a.helpers import load, event
        from dataclasses import replace

        runtime, _ = harness(self)
        clock = load(runtime, 106, 2)
        b = runtime.client.registry.bindings[0]
        old = event(b, 100, 10, 1)
        self.assertIsNone(runtime.deliver(old, clock))
        self.assertEqual(runtime.snapshot(clock).room.value, 18)
        self.assertIsNone(runtime.deliver(old, clock))
        with self.assertRaises(ValueError):
            runtime.deliver(replace(old, reading=replace(old.reading, value=12)), clock)

    def test_settings_saved_only_after_durable_config_and_readback(self):
        from dataclasses import replace
        from packages.offline.contracts import SaveRequest

        runtime, session = harness(self)
        clock, _ = planned(runtime)
        runtime.pump(clock)
        before = runtime.simulator.store.view()
        request = SaveRequest(
            "synthetic.save",
            before.revision,
            replace(before.policy, config_revision=2, armed=False),
        )
        receipt = runtime.save(request, session, clock)
        self.assertEqual(receipt.status, "saved")
        self.assertEqual(receipt.persisted_revision, 2)
        self.assertEqual(runtime.simulator.store.view().policy, request.policy)
        self.assertFalse(runtime.simulator.state.reconciled)
        self.assertFalse(runtime.simulator.state.desired_action.value == "heat")
        self.assertEqual(runtime.save(request, session, clock).status, "conflict")

    def test_denied_conflicting_or_failed_settings_never_return_saved(self):
        from dataclasses import replace
        from packages.offline.contracts import SaveRequest, Principal
        from packages.control_store.store import StoreFailure

        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        view = runtime.simulator.store.view()
        request = SaveRequest(
            "synthetic.save", view.revision, replace(view.policy, config_revision=2)
        )
        reader = runtime.client.grant(Principal("synthetic.reader", ("read",), 1))
        self.assertEqual(runtime.save(request, reader, clock).status, "denied")
        self.assertEqual(
            runtime.save(
                replace(request, expected_revision=0), runtime.operator, clock
            ).status,
            "conflict",
        )
        with patch.object(
            runtime.simulator.store, "configure", side_effect=StoreFailure("injected")
        ):
            self.assertEqual(
                runtime.save(request, runtime.operator, clock).status, "conflict"
            )
        self.assertEqual(runtime.simulator.store.view().policy.config_revision, 1)

    def test_evidence_busy_and_saturated_queue_cannot_block_emergency_stop(self):
        import threading, time
        from packages.contracts import Action

        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        runtime.pump(clock)
        entered = threading.Event()
        release = threading.Event()

        def block(point):
            if point == "before_commit":
                entered.set()
                release.wait(5)

        runtime.evidence.hook = block
        thread = threading.Thread(target=runtime.flush_evidence)
        thread.start()
        self.assertTrue(entered.wait(2))
        start = time.monotonic()
        runtime.trusted_stop(clock)
        elapsed = time.monotonic() - start
        release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertLess(elapsed, 0.5)
        self.assertEqual(runtime.simulator.actuator.calls[-1].action, Action.STOP)
        record = runtime.evidence.get(runtime.client.registry.bindings[0].entity + ":1")
        for _ in range(300):
            runtime._archive(record)
        self.assertGreater(runtime.archive_lost, 0)
        runtime.trusted_stop(clock)

    def test_evidence_failure_keeps_pending_raw_and_does_not_claim_physical_success(
        self,
    ):
        from packages.evidence.store import EvidenceFailure

        runtime, _ = harness(self)
        clock, _ = planned(runtime)
        with patch.object(
            runtime.evidence, "append", side_effect=EvidenceFailure("injected")
        ):
            self.assertEqual(runtime.flush_evidence(), 0)
        self.assertGreater(runtime.flush_evidence(), 0)

    def test_stale_proposal_model_and_empty_result_are_rejected(self):
        from dataclasses import replace
        from packages.contracts import ContractError
        from tests.fixtures.wp1c import request

        runtime, _ = harness(self)
        clock, p = planned(runtime)
        with self.assertRaises(ContractError):
            runtime.accept(
                replace(p, stamp=replace(p.stamp, owner_epoch=p.stamp.owner_epoch + 1)),
                clock,
            )
        with self.assertRaises(ContractError):
            runtime.accept(replace(p, trajectory=()), clock)
        with self.assertRaises(ContractError):
            runtime.plan(
                replace(
                    request(),
                    model=replace(request().model, revision=2),
                    stamp=replace(
                        request().stamp,
                        revisions=replace(request().stamp.revisions, model=2),
                    ),
                )
            )

    def test_authorized_settings_request_stops_before_failed_durable_read(self):
        from packages.offline.contracts import SaveRequest
        from packages.control_store.store import StoreFailure
        from packages.contracts import Action
        from dataclasses import replace

        runtime, session = harness(self)
        clock, _ = planned(runtime)
        runtime.pump(clock)
        current = runtime.simulator.store.view()
        request = SaveRequest(
            "synthetic.unavailable",
            current.revision,
            replace(current.policy, config_revision=2, armed=False),
        )
        with patch.object(
            runtime.simulator.store,
            "view",
            side_effect=StoreFailure("injected failed read"),
        ):
            receipt = runtime.save(request, session, clock)
        self.assertEqual(receipt.status, "unavailable")
        self.assertIsNone(receipt.persisted_revision)
        self.assertEqual(runtime.simulator.actuator.calls[-1].action, Action.STOP)
