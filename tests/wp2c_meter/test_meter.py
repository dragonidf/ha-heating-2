"""Artificial boiler-meter data: no HA/network/device access."""

import dataclasses
import unittest

from packages.contracts import ContractError, Quality, QualityStatus, SourceKind
from packages.ha_native.meter import (
    MeterBinding,
    MeterChannel,
    MeterFrame,
    MeterSample,
    SyntheticMeterVerification,
    binding_summary,
    counter_energy,
    future_meter_binding,
    project_meter,
)


def quality(status=QualityStatus.VALID, age=0):
    return Quality(status=status, age_s=age, reason="synthetic.fixture")


def channel(quantity="active_power", phase="total"):
    units = {"active_power": "W", "imported_energy": "kWh", "voltage": "V",
             "current": "A", "apparent_power": "VA"}
    source = f"synthetic.{quantity}_{phase}"
    return MeterChannel(source, source, quantity, units[quantity], phase)


def verification(**changes):
    values = dict(evidence_ids=("synthetic.verification",), boiler_only=True,
                  auxiliaries_included=True, phase_mapping=True,
                  import_direction=True, counter_accuracy=True)
    values.update(changes)
    return SyntheticMeterVerification(**values)


def binding(**changes):
    values = dict(meter_id="synthetic.boiler_meter",
                  coverage=("synthetic.boiler_feed",),
                  channels=(channel(), channel("imported_energy")),
                  verification=verification())
    values.update(changes)
    return MeterBinding(**values)


def sample(quantity="active_power", phase="total", value=6000, at=100, **changes):
    c = channel(quantity, phase)
    values = dict(source_id=c.source_id, value=value, unit=c.unit,
                  observed_at=at, received_at=at, sequence=int(at),
                  quality=quality())
    values.update(changes)
    return MeterSample(**values)


def frame(at=100, watts=6000, kwh=10, **changes):
    values = dict(at=at, received_at=at, online=True,
                  samples=(sample(value=watts, at=at),
                           sample("imported_energy", value=kwh, at=at)))
    values.update(changes)
    return MeterFrame(**values)


class MeterSchemaTests(unittest.TestCase):
    def test_sanitized_summary_reports_only_synthetic_scope_and_unqualified_hardware(self):
        summary = binding_summary(MeterBinding())
        self.assertIsNone(summary["source_id"])
        self.assertFalse(summary["bound"])
        self.assertFalse(summary["synthetic_verified"])
        summary = binding_summary(binding())
        self.assertEqual(summary["source_id"], "synthetic.boiler_meter")
        self.assertTrue(summary["bound"])
        self.assertTrue(summary["synthetic_verified"])
        self.assertTrue(summary["active_power_supported"])
        self.assertTrue(summary["imported_energy_supported"])
        self.assertEqual(summary["physical_model"], "unknown")
        self.assertEqual(summary["physical_wiring"], "unknown")
        self.assertEqual(summary["physical_accuracy"], "unknown")
        self.assertEqual(summary["B03"], "BLOCKED")
        self.assertFalse(summary["physical_authority"])
        self.assertEqual(summary["scope"], "synthetic_only")
        summary = binding_summary(future_meter_binding("synthetic.future_meter"))
        self.assertEqual(summary["source_id"], "synthetic.future_meter")
        self.assertFalse(summary["active_power_supported"])

    def test_options_source_id_is_a_placeholder_and_cannot_qualify_or_bind_channels(self):
        self.assertEqual(future_meter_binding(), MeterBinding())
        b = future_meter_binding("synthetic.future_meter")
        self.assertEqual(b.meter_id, "synthetic.future_meter")
        self.assertEqual(b.channels, ())
        self.assertIsNone(b.verification)
        self.assertEqual(b.physical_qualification, "unverified")
        self.assertIsNone(project_meter(b, frame(), now=100).power.kw)
        for source_id in ("sensor.example", " ", True, None):
            with self.subTest(source_id=source_id), self.assertRaises(ContractError):
                future_meter_binding(source_id)

    def test_default_is_unbound_and_physical_qualification_never_changes(self):
        unbound = MeterBinding()
        result = project_meter(unbound, MeterFrame(100, 100), now=100)
        self.assertIsNone(result.power.kw)
        self.assertIsNone(result.counter)
        for b in (unbound, binding()):
            self.assertEqual(b.physical_qualification, "unverified")
            self.assertFalse(b.physical_authority)
        self.assertFalse(result.physical_authority)
        self.assertIsNone(result.physical_heat)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            unbound.meter_id = "synthetic.changed"

    def test_only_synthetic_identifiers_and_no_write_privilege(self):
        for make in (
            lambda: MeterBinding(meter_id="sensor.example"),
            lambda: binding(coverage=("real.feed",)),
            lambda: dataclasses.replace(channel(), entity_id="sensor.example"),
            lambda: dataclasses.replace(channel(), source_id="sensor.example"),
            lambda: sample(origin_id="real.origin"),
            lambda: sample(components=("real.feed",)),
            lambda: verification(evidence_ids=("real.proof",)),
            lambda: verification(evidence_ids=()),
            lambda: dataclasses.replace(channel(), quantity="relay"),
            lambda: dataclasses.replace(channel(), phase="L4"),
        ):
            with self.subTest(make=make), self.assertRaises(ContractError):
                make()
        with self.assertRaises(TypeError):
            MeterBinding(physical_authority=True)
        with self.assertRaises(TypeError):
            MeterChannel("synthetic.x", "synthetic.x", "active_power", "W",
                         capabilities=("write",))

    def test_units_cannot_relabel_apparent_power_or_current_as_active_power(self):
        for quantity, unit in (("active_power", "VA"), ("active_power", "A"),
                               ("imported_energy", "W"), ("voltage", "W")):
            with self.subTest(quantity=quantity, unit=unit), self.assertRaises(ContractError):
                MeterChannel("synthetic.x", "synthetic.x", quantity, unit)
        for unit in ("var", "Wh", "kVA", True):
            with self.subTest(unit=unit), self.assertRaises(ContractError):
                sample(unit=unit)

    def test_binding_schema_rejects_duplicates_partial_phases_and_bad_limits(self):
        for changes in (
            dict(version=2), dict(version=True), dict(channels=[channel()]),
            dict(channels=(None,)), dict(channels=(channel(), channel())),
            dict(channels=(channel("active_power", "L1"),)),
            dict(channels=(channel(), dataclasses.replace(channel(), source_id="synthetic.other"))),
            dict(channels=(channel(), dataclasses.replace(channel("current"), entity_id=channel().entity_id))),
            dict(coverage=("synthetic.x", "synthetic.x")), dict(coverage=[]),
            dict(max_age_s=-1), dict(max_age_s=46), dict(max_skew_s=-1),
            dict(max_kw=0), dict(max_kw=float("inf")), dict(phase_tolerance_w=-1),
            dict(verification="trusted"), dict(channels=(channel(),), coverage=()),
        ):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                binding(**changes)

    def test_quality_numeric_flags_and_frame_schema_are_strict(self):
        for changes in (dict(value=True), dict(value=-1), dict(value=float("nan")),
                        dict(value=None), dict(observed_at=-1), dict(sequence=True),
                        dict(quality="valid"), dict(origin="direct")):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                sample(**changes)
        for changes in (dict(online=1), dict(relay_on=1), dict(protection="closed"),
                        dict(samples=[]), dict(samples=(None,)), dict(quality="valid"),
                        dict(samples=(sample(), sample())), dict(at=-1),
                        dict(received_at=float("nan"))):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                frame(**changes)
        with self.assertRaises(ContractError):
            verification(boiler_only="yes")


class MeterProjectionTests(unittest.TestCase):
    def test_verified_synthetic_active_power_and_counter_preserve_lineage_and_time(self):
        result = project_meter(binding(), frame(), now=110)
        self.assertEqual((result.power.kw, result.power.at, result.power.received), (6, 100, 100))
        self.assertEqual(result.power.category, "confirmed")
        self.assertEqual(result.counter.kwh, 10)
        self.assertEqual(result.counter.at, 100)
        for source in ("synthetic.boiler_feed", "synthetic.verification",
                       "synthetic.active_power_total", "synthetic.fixture"):
            self.assertIn(source, result.power.sources)
        self.assertFalse(result.physical_authority)
        self.assertIsNone(result.physical_heat)

    def test_verified_zero_and_missing_are_different(self):
        self.assertEqual(project_meter(binding(), frame(watts=0, kwh=0), now=100).power.kw, 0)
        missing = sample(value=None, quality=quality(QualityStatus.MISSING))
        result = project_meter(binding(), frame(samples=(missing,)), now=100)
        self.assertIsNone(result.power.kw)
        self.assertIsNone(result.counter)

    def test_every_unverified_scope_fact_prevents_primary(self):
        for name in ("boiler_only", "auxiliaries_included", "phase_mapping",
                     "import_direction", "counter_accuracy"):
            b = binding(verification=verification(**{name: False}))
            result = project_meter(b, frame(), now=100)
            self.assertIsNone(result.power.kw, name)
            self.assertIsNone(result.counter, name)
        self.assertIsNone(project_meter(binding(verification=None), frame(), now=100).power.kw)

    def test_stages_are_lower_confidence_explicit_assumptions_at_now(self):
        for stage in (3, 6, 9):
            result = project_meter(MeterBinding(), MeterFrame(100, 100), now=110, stage_kw=stage)
            self.assertEqual((result.power.kw, result.power.category, result.power.at),
                             (stage, "estimated", 110))
            self.assertIsNone(result.counter)
        result = project_meter(binding(), frame(watts=0), now=100, stage_kw=9)
        self.assertEqual((result.power.kw, result.power.category), (0, "confirmed"))
        for stage in (0, 4, -1, True, float("nan")):
            with self.subTest(stage=stage), self.assertRaises(ContractError):
                project_meter(binding(), frame(), now=100, stage_kw=stage)

    def test_relay_and_protection_are_diagnostics_never_heat_or_energy(self):
        for relay in (True, False, None):
            f = MeterFrame(100, 100, online=True, relay_on=relay, protection="tripped")
            result = project_meter(binding(), f, now=100)
            self.assertIsNone(result.power.kw)
            self.assertIsNone(result.physical_heat)
        result = project_meter(binding(), frame(relay_on=False, protection="tripped"), now=100)
        self.assertEqual(result.power.kw, 6)

    def test_absent_offline_stale_and_future_metadata_cannot_qualify(self):
        for changes in (dict(online=False), dict(online=None), dict(at=54),
                        dict(at=101, received_at=101), dict(received_at=101),
                        dict(received_at=99), dict(quality=quality(QualityStatus.STALE)),
                        dict(quality=quality(age=46))):
            with self.subTest(changes=changes):
                result = project_meter(binding(), frame(**changes), now=100)
                self.assertIsNone(result.power.kw)
                self.assertIsNone(result.counter)

    def test_source_timestamp_not_receive_timestamp_controls_freshness(self):
        f = frame(samples=(sample(at=54, received_at=100),))
        self.assertIsNone(project_meter(binding(), f, now=100).power.kw)
        f = frame(samples=(sample(at=55, received_at=100),))
        self.assertEqual(project_meter(binding(), f, now=100).power.kw, 6)

    def test_invalid_sample_time_quality_origin_and_unit_fail_closed(self):
        for changes in (dict(at=101), dict(received_at=101), dict(received_at=99),
                        dict(quality=quality(age=46)), dict(unit="VA"),
                        dict(quality=quality(QualityStatus.ESTIMATED)),
                        dict(quality=quality(QualityStatus.CONFLICTING)),
                        dict(origin=SourceKind.DERIVED), dict(origin=SourceKind.HELD),
                        dict(origin=SourceKind.FORECAST)):
            s = sample(**changes)
            result = project_meter(binding(), frame(samples=(s,)), now=100)
            self.assertIsNone(result.power.kw, changes)
        self.assertIsNone(project_meter(binding(max_kw=5), frame(), now=100).power.kw)

    def test_diagnostics_voltage_current_va_never_synthesize_active_watts(self):
        channels = tuple(channel(q) for q in ("voltage", "current", "apparent_power"))
        samples = tuple(sample(q, value=230) for q in ("voltage", "current", "apparent_power"))
        result = project_meter(binding(channels=channels), frame(samples=samples), now=100)
        self.assertIsNone(result.power.kw)
        self.assertIsNone(result.counter)

    def test_phase_sum_requires_all_phases_coherent_fresh_and_consistent(self):
        phases = tuple(channel(phase=p) for p in ("L1", "L2", "L3"))
        samples = tuple(sample(phase=p, value=2000) for p in ("L1", "L2", "L3"))
        b = binding(channels=phases)
        result = project_meter(b, frame(samples=samples), now=100)
        self.assertEqual((result.power.kw, result.power.method), (6, "synthetic_phase_sum"))
        for broken in (samples[:-1], samples[:-1] + (sample(phase="L3", at=94, value=2000),)):
            self.assertIsNone(project_meter(b, frame(samples=broken), now=100).power.kw)
        b = binding(channels=(channel(), *phases))
        self.assertEqual(project_meter(b, frame(samples=(sample(), *samples)), now=100).power.kw, 6)
        self.assertIsNone(project_meter(b, frame(samples=(sample(value=9000), *samples)), now=100).power.kw)
        self.assertIsNone(project_meter(b, frame(samples=(sample(), *samples[:-1])), now=100).power.kw)

    def test_phase_sum_preserves_oldest_observation_and_latest_receipt(self):
        phases = tuple(channel(phase=p) for p in ("L1", "L2", "L3"))
        samples = tuple(sample(phase=p, value=1000, at=98+i, received_at=100)
                        for i, p in enumerate(("L1", "L2", "L3")))
        result = project_meter(binding(channels=phases), frame(samples=samples), now=100)
        self.assertEqual((result.power.at, result.power.received, result.power.kw), (98, 100, 3))

    def test_duplicate_and_reordered_source_events_never_replace_newer_evidence(self):
        prior = frame()
        self.assertEqual(project_meter(binding(), prior, now=100, previous=prior).power.kw, 6)
        for s in (sample(at=99, received_at=101, sequence=101),
                  sample(at=101, sequence=99), sample(value=9000),
                  sample(at=100, sequence=101, value=9000)):
            result = project_meter(binding(), frame(at=101, samples=(s,)), now=101, previous=prior)
            self.assertIsNone(result.power.kw)

    def test_sample_input_order_never_changes_projection(self):
        f = frame()
        self.assertEqual(project_meter(binding(), f, now=100),
                         project_meter(binding(), dataclasses.replace(f, samples=f.samples[::-1]), now=100))

    def test_overlap_excludes_meter_and_dependencies_from_primary_without_zero(self):
        for coverage in (("synthetic.boiler_feed",), ("synthetic.upstream",)):
            f = frame(samples=(sample(components=("synthetic.upstream",)),))
            result = project_meter(binding(), f, now=100, excluded_coverage=coverage)
            self.assertIsNone(result.power.kw)
            self.assertIsNone(result.counter)
        self.assertEqual(project_meter(binding(), frame(), now=100,
                                       excluded_coverage=("synthetic.unrelated",)).power.kw, 6)
        with self.assertRaises(ContractError):
            project_meter(binding(), frame(), now=100, excluded_coverage=("real.feed",))

    def test_unbound_sample_cannot_claim_a_different_meter(self):
        result = project_meter(binding(), frame(samples=(sample("current"),)), now=100)
        self.assertIsNone(result.power.kw)
        self.assertIsNone(result.counter)

    def test_sample_cannot_arrive_after_its_containing_frame(self):
        f = frame(samples=(sample(at=110), sample("imported_energy", at=110)))
        result = project_meter(binding(), f, now=110)
        self.assertIsNone(result.power.kw)
        self.assertIsNone(result.counter)

    def test_phase_contradiction_quarantines_counter_topology_too(self):
        phases = tuple(channel(phase=p) for p in ("L1", "L2", "L3"))
        samples = tuple(sample(phase=p, value=1000) for p in ("L1", "L2", "L3"))
        b = binding(channels=(*binding().channels, *phases))
        f = frame(samples=(*frame().samples, *samples))
        result = project_meter(b, f, now=100)
        self.assertIsNone(result.power.kw)
        self.assertIsNone(result.counter)
        self.assertIn("contradiction", result.counter_reason)

    def test_overlap_exclusion_also_blocks_a_duplicate_stage_contribution(self):
        result = project_meter(binding(), frame(), now=100, stage_kw=9,
                               excluded_coverage=("synthetic.boiler_feed",))
        self.assertIsNone(result.power.kw)

    def test_projection_identities_distinguish_time_and_are_deterministic(self):
        a = project_meter(binding(), frame(), now=100)
        b = project_meter(binding(), frame(at=110), now=110)
        self.assertNotEqual(a.power.identity, b.power.identity)
        self.assertNotEqual(a.counter.identity, b.counter.identity)
        self.assertEqual(a, project_meter(binding(), frame(), now=100))

    def test_lineage_capacity_fails_closed_instead_of_truncating_provenance(self):
        parts = tuple(f"synthetic.part{i}" for i in range(64))
        result = project_meter(binding(), frame(samples=(sample(components=parts),)), now=100)
        self.assertIsNone(result.power.kw)
        self.assertEqual(result.power.method, "meter_lineage_capacity")
        result = project_meter(binding(), frame(samples=(
            sample("imported_energy", value=10, components=parts),)), now=100)
        self.assertIsNone(result.counter)
        self.assertEqual(result.counter_reason, "meter_lineage_capacity")


class MeterCounterTests(unittest.TestCase):
    def test_counter_delta_reuses_accepted_contract_without_inventing_distribution(self):
        energy = counter_energy(binding(), frame(), frame(at=400, kwh=10.5),
                                now=400, continuity="synthetic.continuity")
        self.assertEqual((energy.kwh, energy.category, energy.method), (0.5, "confirmed", "counter_delta"))
        self.assertEqual((energy.start, energy.end), (100, 400))
        zero = counter_energy(binding(), frame(), frame(at=400), now=400,
                              continuity="synthetic.continuity")
        self.assertEqual(zero.kwh, 0)

    def test_counter_resets_and_impossible_jumps_are_unknown(self):
        for value, reason in ((1, "counter_reset"), (20, "counter_jump")):
            energy = counter_energy(binding(), frame(), frame(at=400, kwh=value),
                                    now=400, continuity="synthetic.continuity")
            self.assertIsNone(energy.kwh)
            self.assertEqual(energy.method, reason)

    def test_counter_missing_stale_unverified_or_overlap_never_becomes_zero(self):
        for b, right, excluded in (
            (binding(), frame(at=400, samples=()), ()),
            (binding(), frame(at=400), ()),
            (binding(verification=None), frame(at=400), ()),
            (binding(), frame(at=400), ("synthetic.boiler_feed",)),
        ):
            now = 446 if b.verification is not None and right.samples and not excluded else 400
            energy = counter_energy(b, frame(), right, now=now,
                                    continuity="synthetic.continuity", excluded_coverage=excluded)
            self.assertIsNone(energy.kwh)

    def test_changed_origin_or_reordered_counter_does_not_join_continuity(self):
        for s in (sample("imported_energy", at=400, value=10.5, origin_id="synthetic.new_origin"),
                  sample("imported_energy", at=99, received_at=400, value=10.5),
                  sample("imported_energy", at=400, value=10.5, sequence=99)):
            energy = counter_energy(binding(), frame(), frame(at=400, samples=(s,)),
                                    now=400, continuity="synthetic.continuity")
            self.assertIsNone(energy.kwh)
        with self.assertRaises(ContractError):
            counter_energy(binding(), frame(), frame(at=99), now=100,
                           continuity="synthetic.continuity")
        with self.assertRaises(ContractError):
            counter_energy(binding(), frame(), frame(at=400), now=400, continuity="real.continuity")

    def test_partial_counter_support_is_not_a_total_energy_source(self):
        c = channel("imported_energy", "L1")
        f = frame(samples=(sample("imported_energy", "L1", value=10),))
        self.assertIsNone(project_meter(binding(channels=(c,)), f, now=100).counter)

    def test_counter_energy_retains_origin_scope_and_verification_provenance(self):
        energy = counter_energy(binding(), frame(), frame(at=400, kwh=10.5),
                                now=400, continuity="synthetic.continuity")
        for source in ("synthetic.boiler_feed", "synthetic.verification", "synthetic.fixture",
                       "synthetic.imported_energy_total"):
            self.assertIn(source, energy.sources)

    def test_two_valid_endpoints_cannot_truncate_their_combined_lineage(self):
        left_parts = tuple(f"synthetic.left{i}" for i in range(32))
        right_parts = tuple(f"synthetic.right{i}" for i in range(32))
        left = frame(samples=(sample("imported_energy", value=10, components=left_parts),))
        right = frame(at=400, samples=(sample("imported_energy", at=400, value=10.5,
                                             components=right_parts),))
        energy = counter_energy(binding(), left, right, now=400,
                                continuity="synthetic.continuity")
        self.assertIsNone(energy.kwh)
        self.assertIn("lineage_capacity", energy.method)


if __name__ == "__main__":
    unittest.main()
