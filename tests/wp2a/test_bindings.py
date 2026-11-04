import unittest
from dataclasses import replace
from packages.contracts import Unit, ContractError, Clock, QualityStatus
from packages.offline.contracts import Registry, Principal, SourceEvent
from packages.ha_fake.client import FakeHAClient, FakeSession
from packages.ha_fake.adapter import SourceAdapter
from packages.evidence.energy import derive_power
from packages.offline.contracts import BalanceTopology
from tests.wp2a.helpers import binding, registry, event, measurement
from tests.fixtures.synthetic import state


class BindingTests(unittest.TestCase):
    def test_required_unit_time_capability_and_fake_only_handles_are_validated(self):
        base = binding("thermostat")
        for changes in (
            dict(entity="climate.real"),
            dict(unit=Unit.WATT),
            dict(max_age_s=-1),
            dict(priority=True),
            dict(capabilities=("read", "send")),
            dict(minimum=5),
            dict(minimum=10, maximum=5),
            dict(step=0),
            dict(capabilities=("read", "propose")),
        ):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(base, **changes)
        qualified = replace(
            base,
            capabilities=("read", "setpoint", "propose"),
            minimum=5,
            maximum=35,
            step=0.5,
        )
        self.assertEqual(qualified.step, 0.5)
        self.assertEqual(binding("counter").unit, Unit.KWH)
        self.assertEqual(binding("weather").unit, Unit.CELSIUS)

    def test_alias_precedence_cross_role_independence_and_version_are_strict(self):
        r = registry()
        room = r.bindings[0]
        cloud = replace(
            room,
            entity="synthetic.cloud",
            source_id="synthetic.cloud.source",
            priority=1,
        )
        self.assertEqual(len(replace(r, bindings=r.bindings + (cloud,)).bindings), 5)
        for changes in (
            dict(bindings=r.bindings + (room,)),
            dict(bindings=r.bindings + (replace(cloud, priority=0),)),
            dict(bindings=(room, replace(r.bindings[1], physical_id=room.physical_id))),
            dict(bindings=(room, replace(cloud, physical_id="another"))),
            dict(version=2),
            dict(alias_policy="auto"),
        ):
            with self.assertRaises(ContractError):
                replace(r, **changes)

    def test_client_duplicates_reordered_delivery_and_no_url_or_token(self):
        client = FakeHAClient(registry())
        b = client.registry.bindings[0]
        with self.assertRaises(ContractError):
            client.push(event(b, 100, 19))
        with self.assertRaises(TypeError):
            client.connect("http://invalid.synthetic")
        client.connect()
        a = event(b, 100, 19)
        b_event = event(b, 101, 20, 2)
        self.assertTrue(client.push(a))
        self.assertFalse(client.push(a))
        client.push(b_event)
        self.assertEqual(client.drain((1, 0)), (b_event, a))
        self.assertEqual(client.drain(), ())
        with self.assertRaises(ContractError):
            client.push(replace(a, reading=replace(a.reading, value=20)))
        with self.assertRaises(ContractError):
            client.push(replace(a, identity="bad", entity="synthetic.unbound"))
        with self.assertRaises(ContractError):
            client.drain((0,))
        with self.assertRaises(ContractError):
            client.push(
                replace(
                    a,
                    identity="bad.unit",
                    reading=replace(a.reading, physical_id="another"),
                )
            )
        client.disconnect()
        self.assertFalse(client.connected)

    def test_in_process_grant_revocation_and_forged_session(self):
        client = FakeHAClient(registry())
        p = Principal("synthetic.reader", ("read",), 1)
        session = client.grant(p)
        self.assertTrue(client.permits(session, "read"))
        self.assertFalse(client.permits(session, "admin"))
        self.assertFalse(client.permits(FakeSession(object(), p), "read"))
        self.assertFalse(client.permits(None, "read"))
        with self.assertRaises(ContractError):
            client.grant(p)
        client.revoke(p.identity)
        self.assertFalse(client.permits(session, "read"))
        self.assertTrue(client.permits(client.grant(replace(p, epoch=3)), "read"))


class SourceQualityTests(unittest.TestCase):
    def setUp(self):
        self.room = binding("room")
        self.cloud = replace(
            self.room,
            entity="synthetic.cloud",
            source_id="synthetic.cloud.source",
            priority=1,
        )
        self.registry = replace(registry(), bindings=(self.room, self.cloud))
        self.clock = Clock(utc=106, monotonic=1006, boot_id="synthetic.boot")

    def test_stale_local_cloud_and_unavailability_never_manufacture_temperature(self):
        a = SourceAdapter(self.registry)
        a.ingest(event(self.room, 90, 18))
        a.ingest(event(self.cloud, 91, 20))
        self.assertIsNone(a.select("room", self.clock, connected=True))
        current = event(self.cloud, 105, 20, 2)
        a.ingest(current)
        selected = a.select("room", self.clock, connected=True)
        self.assertEqual(selected.observed_at, 105)
        self.assertEqual(selected.quality.age_s, 1)
        a.ingest(SourceEvent("synthetic.missing", self.cloud.entity, 3, 106, None))
        self.assertIsNone(a.select("room", self.clock, connected=True))
        self.assertIsNone(a.select("room", self.clock, connected=False))

    def test_conflict_is_unknown_and_explicit_priority_does_not_average(self):
        for policy, expected in (("conflict_unknown", None), ("prefer_priority", 18)):
            a = SourceAdapter(replace(self.registry, alias_policy=policy))
            a.ingest(event(self.room, 105, 18))
            a.ingest(event(self.cloud, 105, 21))
            selected = a.select("room", self.clock, connected=True)
            self.assertEqual(selected.value if selected else None, expected)
        a = SourceAdapter(self.registry)
        a.ingest(event(self.room, 105, 18))
        a.ingest(event(self.cloud, 105, 18.2))
        self.assertEqual(a.select("room", self.clock, connected=True).value, 18)

    def test_reorder_duplicate_clock_skew_and_explicit_utc_rollback_fail_closed(self):
        a = SourceAdapter(self.registry)
        e = event(self.room, 105, 18, 2)
        a.ingest(e)
        self.assertFalse(a.ingest(e))
        self.assertFalse(a.ingest(event(self.room, 100, 10, 1)))
        with self.assertRaises(ContractError):
            a.ingest(replace(e, reading=replace(e.reading, value=20)))
        with self.assertRaises(ContractError):
            a.ingest(replace(e, identity="bad.binding", entity="synthetic.unknown"))
        a.snapshot(self.clock, state(), 1, 1, connected=True)
        self.assertIsNone(
            a.snapshot(replace(self.clock, utc=104), state(), 1, 1, connected=True).room
        )
        a.connection(2)
        self.assertIsNone(a.select("room", self.clock, connected=True))


class BalanceTests(unittest.TestCase):
    def topology(self):
        inlet = binding("inlet")
        grid = binding("deye_grid")
        groups = (
            binding("group", coverage=("synthetic.load1", "synthetic.load2")),
            binding("phase", coverage=("synthetic.load3",)),
        )
        return BalanceTopology(inlet, grid, groups, True, 12, 10, 2)

    def readings(self, t):
        return tuple(
            measurement(b, 100, v)
            for b, v in zip((t.inlet, *t.subtract, t.grid), (10000, 1000, 2000, 1000))
        )

    def test_signed_grid_import_export_and_9237_watts_do_not_round_to_stages(self):
        t = self.topology()
        r = list(self.readings(t))
        r[-1] = replace(r[-1], signed=True)
        p = derive_power(t, tuple(r), 100, "synthetic.p", "synthetic.heat")
        self.assertEqual(p.kw, 6)
        self.assertEqual(p.category, "derived")
        r[-1] = replace(r[-1], value=-1000)
        self.assertEqual(
            derive_power(t, tuple(r), 100, "synthetic.p", "synthetic.heat").kw, 8
        )
        r[0] = replace(r[0], value=11237)
        self.assertEqual(
            derive_power(t, tuple(r), 100, "synthetic.p", "synthetic.heat").kw, 9.237
        )

    def test_phase_group_load_alias_overlap_and_deye_load_are_never_subtracted_twice(
        self,
    ):
        t = self.topology()
        for subtract in (
            t.subtract + (replace(t.subtract[0], source_id="alias"),),
            (t.subtract[0], binding("load", coverage=("synthetic.load1",))),
            (binding("deye_load"),),
        ):
            with self.assertRaises(ContractError):
                replace(t, subtract=subtract)
        with self.assertRaises(ContractError):
            replace(t, grid=replace(t.grid, physical_id=t.inlet.physical_id))
        with self.assertRaises(ContractError):
            replace(t, qualified=1)

    def test_missing_stale_skew_unsigned_and_negative_residual_remain_unknown(self):
        t = self.topology()
        r = list(self.readings(t))
        r[-1] = replace(r[-1], signed=True)
        for topology, samples in (
            (replace(t, qualified=False), tuple(r)),
            (t, tuple(r[:-1])),
            (t, tuple(r) + (r[0],)),
            (t, (replace(r[0], observed_at=90), *r[1:])),
            (t, tuple(self.readings(t))),
            (t, (replace(r[0], observed_at=97), *r[1:])),
        ):
            self.assertIsNone(derive_power(topology, samples, 100, "p", "s").kw)
        negative = derive_power(t, (replace(r[0], value=100), *r[1:]), 100, "p", "s")
        self.assertEqual(negative.method, "balance_conflict")
        self.assertEqual(negative.raw_w, -3900)
        self.assertIsNone(negative.kw)
        self.assertIsNone(
            derive_power(t, (replace(r[0], value=99999), *r[1:]), 100, "p", "s").kw
        )

    def test_alias_clock_skew_and_fan_capability_bounds_are_not_silently_accepted(self):
        room = binding("room")
        cloud = replace(
            room,
            entity="synthetic.cloud",
            source_id="synthetic.cloud.source",
            priority=1,
        )
        r = replace(registry(), bindings=(room, cloud))
        a = SourceAdapter(r)
        a.ingest(event(room, 105, 18))
        a.ingest(event(cloud, 100, 18))
        self.assertIsNone(
            a.select(
                "room",
                Clock(utc=106, monotonic=1006, boot_id="synthetic.boot"),
                connected=True,
            )
        )
        with self.assertRaises(ContractError):
            replace(
                binding("fan"),
                minimum=0,
                maximum=200,
                step=1,
                capabilities=("read", "propose"),
            )

    def test_runtime_derived_component_overlap_cannot_hide_behind_distinct_meter_ids(
        self,
    ):
        from packages.contracts import Provenance, SourceKind

        t = self.topology()
        r = list(self.readings(t))
        r[-1] = replace(r[-1], signed=True)
        r[1] = replace(
            r[1],
            provenance=Provenance(
                kind=SourceKind.DERIVED,
                independent=False,
                components=(t.inlet.physical_id,),
            ),
        )
        result = derive_power(
            t, tuple(r), 100, "synthetic.derived-overlap", "synthetic.heat"
        )
        self.assertIsNone(result.kw)
        self.assertEqual(result.method, "source_dependency_overlap")
