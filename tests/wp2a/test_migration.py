import unittest, sqlite3
from dataclasses import replace
from packages.contracts import (
    OneShot,
    OneShotKind,
    OneShotOutcome,
    ContractError,
    Action,
)
from packages.offline.contracts import CounterMapping, LegacyBundle, ForecastRecord
from packages.offline.codec import encode, decode
from packages.evidence.store import (
    EvidenceStore,
    EvidenceConflict,
    EvidenceFailure,
    record,
)
from packages.migration.rehearsal import dry_run, stage, rollback_copy
from packages.thermal import Interval
from packages.planner import Curve
from packages.fan_policy import FanState, FanPolicy
from tests.fixtures.wp1c import model
from tests.fixtures.synthetic import state, policy, plan
from tests.wp2a.helpers import temp
from tests.wp2a.test_energy import point


def legacy():
    curve = Curve(
        "synthetic.frozen",
        56800,
        ((56800, Interval(20, 20)), (100000, Interval(21, 21))),
        "a" * 64,
        1,
        "synthetic.old-plan",
        (56000,),
    )
    forecast = ForecastRecord(
        "synthetic.original",
        "synthetic.old-cycle",
        "original",
        100000,
        curve,
        99999,
        17.9594,
    )
    shot = OneShot(
        intent_id="synthetic.once",
        kind=OneShotKind.HEAT_AFTER_GRID_RESTORE,
        created_at=99900,
        expires_at=101000,
        armed_grid_epoch=1,
        consumed_at=None,
        outcome=OneShotOutcome.PENDING,
    )
    return LegacyBundle(
        "synthetic.legacy",
        100000,
        (
            CounterMapping(
                "legacy.total", "synthetic.total", 123.456789, "synthetic.origin.total"
            ),
            CounterMapping("legacy.day", "synthetic.day", 4, "synthetic.origin.day"),
        ),
        model(),
        plan(),
        (shot,),
        FanState(99999, 6, True, None, 100500, True),
        FanPolicy(38, 42, 50),
        (forecast,),
        policy(),
        state(manual_paused=True),
    )


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = legacy()
        self.plan = dry_run(self.bundle)
        self.store = EvidenceStore.create(temp(self))

    def test_dry_run_hashes_every_scope_and_has_no_writes(self):
        before = self.store.head()
        again = dry_run(self.bundle)
        self.assertEqual(self.plan, again)
        self.assertEqual(self.store.head(), before)
        self.assertEqual(encode(self.bundle), encode(legacy()))
        self.assertGreaterEqual(len(self.plan.manifest), 9)
        self.assertTrue(all(len(entry.checksum) == 64 for entry in self.plan.manifest))

    def test_stage_idempotent_continuity_and_original_hashes_are_preserved(self):
        receipt = stage(self.plan, self.store)
        head = self.store.head()
        self.assertEqual(stage(self.plan, self.store), receipt)
        self.assertEqual(self.store.head(), head)
        self.assertFalse(receipt.automatic_armed)
        self.assertTrue(
            all(
                entry.source_version
                and entry.target_version
                and entry.unit
                and entry.continuity_key
                for entry in self.plan.manifest
            )
        )
        self.assertAlmostEqual(
            self.store.summary("synthetic.total").actual_total_kwh, 123.456789, places=9
        )
        self.assertEqual(self.store.summary("synthetic.day").actual_total_kwh, 4)
        self.assertEqual(
            decode(self.store.get("synthetic.original").payload), self.bundle.curves[0]
        )
        self.assertEqual(
            decode(self.store.get("synthetic.once").payload), self.bundle.one_shots[0]
        )
        self.assertEqual(self.store.verify(), head[0])

    def test_changed_or_forged_manifest_nonempty_target_and_bad_units_are_blocked(self):
        with self.assertRaises(EvidenceConflict):
            stage(replace(self.plan, source_hash="f" * 64), self.store)
        stage(self.plan, self.store)
        other = dry_run(replace(self.bundle, coefficients=model(heat_gain=0.7)))
        with self.assertRaises(EvidenceConflict):
            stage(other, self.store)
        from packages.contracts import Unit

        with self.assertRaises(ContractError):
            replace(self.bundle.counters[0], unit=Unit.WATT)
        with self.assertRaises(ContractError):
            replace(self.bundle, counters=(self.bundle.counters[0],) * 2)
        with self.assertRaises(ContractError):
            replace(self.bundle, version=2)

    def test_stage_failure_rolls_back_all_counters_states_and_freeze_refs(self):
        def fail(point):
            if point == "before_commit":
                raise sqlite3.OperationalError("injected migration write")

        self.store.hook = fail
        with self.assertRaises(EvidenceFailure):
            stage(self.plan, self.store)
        self.store.hook = None
        self.assertEqual(self.store.head()[0], 0)
        self.assertGreater(stage(self.plan, self.store).last_seq, 0)

    def test_rollback_copy_preserves_new_energy_and_consumed_shot_without_rearming(
        self,
    ):
        receipt = stage(self.plan, self.store)
        for p in (
            point(100000, 6, identity="synthetic.new1"),
            point(100030, 0, identity="synthetic.new2"),
        ):
            self.store.power(replace(p, stream="synthetic.total"))
        self.store.finalize("synthetic.total", 100030, as_of=100030)
        consumed = replace(
            self.bundle.one_shots[0],
            consumed_at=100010,
            outcome=OneShotOutcome.CONSUMED,
        )
        self.store.append(
            record("synthetic.consumed", consumed, 100010, "synthetic.one_shots")
        )
        head = self.store.head()
        destination = temp(self)
        result = rollback_copy(self.plan, self.store, destination)
        self.assertEqual(self.store.head(), head)
        self.assertEqual(result.copied_seq, head[0])
        self.assertAlmostEqual(result.bundle.counters[0].value, 123.506789, places=9)
        self.assertEqual(result.bundle.one_shots[0].consumed_at, 100010)
        self.assertFalse(result.bundle.policy.armed)
        self.assertFalse(result.bundle.policy.allow_automatic)
        self.assertTrue(result.bundle.state.manual_paused)
        self.assertFalse(result.bundle.state.reconciled)
        self.assertEqual(result.bundle.state.desired_action, Action.STOP)
        self.assertIsNone(result.bundle.plan)
        copied = EvidenceStore(destination)
        self.assertEqual(
            decode(copied.get("synthetic.original").payload).curve.checksum,
            self.bundle.curves[0].curve.checksum,
        )
        self.assertEqual(copied.get("synthetic.new1"), self.store.get("synthetic.new1"))
        self.assertGreater(copied.head()[0], result.copied_seq)

    def test_rollback_will_not_rewind_one_shot_consumption(self):
        consumed = replace(
            self.bundle.one_shots[0],
            consumed_at=100000,
            outcome=OneShotOutcome.CONSUMED,
        )
        source = replace(self.bundle, one_shots=(consumed,))
        plan = dry_run(source)
        stage(plan, self.store)
        self.store.append(
            record(
                "synthetic.illegal.pending",
                self.bundle.one_shots[0],
                100001,
                "synthetic.one_shots",
            )
        )
        with self.assertRaises(EvidenceConflict):
            rollback_copy(plan, self.store, temp(self))

    def test_rollback_of_unstaged_or_forged_source_never_overwrites_legacy(self):
        with self.assertRaises(EvidenceFailure):
            rollback_copy(self.plan, self.store, temp(self))
        with self.assertRaises(EvidenceConflict):
            rollback_copy(
                replace(self.plan, source_hash="0" * 64), self.store, temp(self)
            )
        self.assertEqual(encode(self.bundle), encode(legacy()))

    def test_optional_old_plan_and_forecasts_remain_explicitly_missing(self):
        bundle = replace(self.bundle, plan=None, curves=(), one_shots=())
        receipt = stage(dry_run(bundle), self.store)
        self.assertGreater(receipt.last_seq, 0)
        result = rollback_copy(dry_run(bundle), self.store, temp(self))
        self.assertIsNone(result.bundle.plan)
        self.assertEqual(result.bundle.curves, ())
