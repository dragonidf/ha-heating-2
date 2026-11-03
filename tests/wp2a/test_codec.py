import json, unittest, random
from dataclasses import replace, FrozenInstanceError
from packages.contracts import ContractError, TimeWindow
from packages.offline.contracts import (
    Principal,
    SaveRequest,
    APIReceipt,
    Cursor,
    RecoveryRequest,
    RecoveryReceipt,
    Origin,
    EnergySlice,
    ArchivePage,
    ArchiveRecord,
    Tariff,
    CostSummary,
    MigrationReceipt,
    RollbackResult,
    StatusView,
)
from packages.offline.codec import encode, decode, TYPES
from packages.evidence.store import record
from packages.migration.rehearsal import dry_run
from tests.wp2a.helpers import binding, registry, event, harness, planned
from tests.wp2a.test_energy import point
from tests.wp2a.test_migration import legacy
from tests.wp2a import test_bindings as binding_cases
from tests.fixtures.synthetic import policy


class CodecTests(unittest.TestCase):
    def test_every_wp2a_contract_roundtrips_with_strict_version_and_null_zero(self):
        b = legacy()
        plan = dry_run(b)
        p = point(100)
        r = record(p.identity, p, 100, p.stream)
        records = [
            binding("room"),
            registry(),
            event(binding("room"), 100, 19),
            Principal("x", ("read",), 1),
            SaveRequest("x", 0, policy()),
            APIReceipt("x", "saved", 1, 1, "durable"),
            p,
            Origin("s", "c", 100, 0),
            EnergySlice("e", "s", "c", 100, 200, "unknown", None, (), "gap"),
            Tariff("t", 100, 200, 1, "SYN"),
            b.curves[0],
            r,
            Cursor(1, 100, 1, "a" * 64),
            RecoveryRequest("x", ("e",), 0, 0, "a" * 64, "b" * 64),
            RecoveryReceipt("x", True, 0, 0, 100, 1),
            *b.counters,
            b,
            plan,
            ArchivePage(((1, r),), None, 1),
            CostSummary(0, 1, 2, 3, None),
            MigrationReceipt("x", "a" * 64, 1, 2),
            binding_cases.BalanceTests().topology(),
        ]
        from packages.offline.contracts import (
            EnergySummary,
            CounterPoint,
        )

        records.extend(
            (
                EnergySummary("s", 1, 2, 3, 4, 5, 6, 11, 0),
                CounterPoint("x", "s", 100, 0, "m"),
            )
        )
        for value in records:
            with self.subTest(kind=type(value).__name__):
                payload = encode(value)
                self.assertEqual(json.loads(payload)["version"], [2, 0])
                self.assertEqual(decode(payload), value)
                with self.assertRaises(FrozenInstanceError):
                    setattr(value, next(iter(value.__dataclass_fields__)), None)

    def test_unknown_fields_major_version_duplicate_keys_and_nonfinite_are_rejected(
        self,
    ):
        value = json.loads(encode(point(100)))
        for extra in (
            dict(version=[True, 0]),
            dict(version=[1, 0]),
            dict(type="FakeHAClient"),
            dict(extra=1),
            dict(data=[]),
        ):
            with self.assertRaises(ContractError):
                decode(json.dumps(value | extra))
        for field, bad in (
            ("kw", True),
            ("at", "100"),
            ("category", "measured"),
            ("url", "private.invalid"),
            ("sources", []),
        ):
            with self.assertRaises(ContractError):
                decode(json.dumps(value | dict(data=value["data"] | {field: bad})))
        for payload in (
            "{",
            '{"version":[2,0],"version":[2,0]}',
            encode(point(100)).replace("3,", "NaN,"),
            '"' + "x" * 524289 + '"',
        ):
            with self.assertRaises(ContractError):
                decode(payload)
        with self.assertRaises(ContractError):
            encode(object())
        with self.assertRaises(ContractError):
            decode("[" * 2000 + "]" * 2000)

    def test_seeded_wire_mutations_never_bypass_validation(self):
        rng = random.Random(14)
        payload = encode(legacy())
        for _ in range(100):
            where = rng.randrange(len(payload))
            mutated = payload[:where] + rng.choice('x{}[]0"') + payload[where + 1 :]
            try:
                obj = decode(mutated)
            except ContractError:
                continue
            self.assertEqual(decode(encode(obj)), obj)

    def test_fake_status_and_save_receipts_cannot_claim_actual_state_or_physical_success(
        self,
    ):
        runtime, session = harness(self)
        clock, _ = planned(runtime)
        before = runtime.status(session, clock)
        self.assertIsNone(before.actual)
        self.assertFalse(before.physical_verified)
        runtime.pump(clock)
        runtime.simulator.ack(clock)
        after = runtime.status(session, clock)
        self.assertEqual(after.receipt_stage.value, "ha_acknowledged")
        self.assertFalse(after.physical_verified)
        self.assertEqual(decode(encode(after)), after)
        with self.assertRaises(ContractError):
            replace(after, physical_verified=True)
        runtime.client.revoke(session.principal.identity)
        with self.assertRaises(ContractError):
            runtime.status(session, clock)
        for status, persisted in (("saved", None), ("denied", 1), ("invented", None)):
            with self.assertRaises(ContractError):
                APIReceipt("x", status, 1, persisted, "test")
