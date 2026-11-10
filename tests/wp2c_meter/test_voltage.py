"""Pure fictional grid-input voltage guard cases; never physical protection."""
from dataclasses import replace
import unittest

from packages.contracts import Clock, ContractError, QualityStatus, SourceKind
from packages.ha_native.voltage import (
    VoltageFrame, VoltagePhase, VoltagePolicy, decode_voltage_frame,
    evaluate_voltage, voltage_view,
)


def clock(at=100, mono=None, boot="synthetic.boot"):
    return Clock(utc=at, monotonic=at if mono is None else mono, boot_id=boot)


def frame(at=100, volts=(230, 230, 230), **changes):
    phases = tuple(VoltagePhase(p, f"synthetic.input220.{p}", v, at, at, int(at),
                               phase_verified=True, online=True)
                   for p, v in zip(("L1", "L2", "L3"), volts))
    values = dict(phases=phases, mapping_verified=True, grid_available=True,
                  protection_trip=False, protection_last_reported=at, protection_qualified=True)
    values.update(changes)
    return VoltageFrame(**values)


class VoltageTests(unittest.TestCase):
    def test_missing_initial_input_and_unverified_roles_fail_closed(self):
        for f in (VoltageFrame(), frame(mapping_verified=False), frame(grid_available=None),
                  frame(grid_available=False), frame(protection_trip=None),
                  frame(protection_qualified=False), frame(protection_last_reported=None)):
            state = evaluate_voltage(VoltagePolicy(), f, clock())
            self.assertEqual(state.status, "MISSING_OR_STALE")
            self.assertFalse(state.eligible)

    def test_all_three_phase_low_high_and_equal_boundaries(self):
        policy = VoltagePolicy(stable_recovery_s=0)
        normal = evaluate_voltage(policy, frame(), clock())
        self.assertTrue(normal.eligible)
        for index, p in enumerate(("L1", "L2", "L3")):
            for value, expected in ((189.9, "LOW"), (250.1, "HIGH")):
                values = [230, 230, 230]; values[index] = value
                result = evaluate_voltage(policy, frame(101, values), clock(101), normal)
                self.assertEqual(result.status, expected)
                self.assertIn(p, result.affected_phases)
                self.assertFalse(result.eligible)
            for value in (190, 250):
                values = [230, 230, 230]; values[index] = value
                self.assertTrue(evaluate_voltage(policy, frame(101, values), clock(101), normal).eligible)

    def test_conflicting_low_and_high_retains_both_affected_phases(self):
        state = evaluate_voltage(VoltagePolicy(), frame(volts=(189, 251, 230)), clock())
        self.assertEqual(state.status, "LOW")
        self.assertEqual(state.affected_phases, ("L1", "L2"))
        self.assertIn("low_and_high", state.reason)

    def test_inward_hysteresis_inclusive_dwell_and_boot_reset(self):
        policy = VoltagePolicy(stable_recovery_s=10)
        low = evaluate_voltage(policy, frame(volts=(180, 230, 230)), clock())
        edge = evaluate_voltage(policy, frame(101, (194.9, 245, 230)), clock(101), low)
        self.assertFalse(edge.eligible)
        start = evaluate_voltage(policy, frame(102, (195, 245, 230)), clock(102), edge)
        self.assertEqual(start.status, "STABILIZING")
        almost = evaluate_voltage(policy, frame(111, (195, 245, 230)), clock(111), start)
        self.assertFalse(almost.eligible)
        recovered = evaluate_voltage(policy, frame(112, (195, 245, 230)), clock(112), almost)
        self.assertEqual(recovered.status, "NORMAL")
        self.assertTrue(recovered.eligible)
        restarted = evaluate_voltage(policy, frame(113), clock(113, boot="synthetic.new"), recovered)
        self.assertEqual(restarted.status, "STABILIZING")
        self.assertIsNone(voltage_view(recovered, policy).get("heat_command"))

    def test_oscillation_outside_recovery_band_restarts_dwell(self):
        policy = VoltagePolicy(stable_recovery_s=10)
        a = evaluate_voltage(policy, frame(), clock())
        b = evaluate_voltage(policy, frame(109, (194, 230, 230)), clock(109), a)
        c = evaluate_voltage(policy, frame(110), clock(110), b)
        self.assertFalse(evaluate_voltage(policy, frame(119), clock(119), c).eligible)
        self.assertTrue(evaluate_voltage(policy, frame(120), clock(120), c).eligible)

    def test_idle_stream_expires_without_fabricating_new_reports(self):
        policy = VoltagePolicy(stable_recovery_s=0, voltage_max_age_s=10)
        f = frame()
        good = evaluate_voltage(policy, f, clock())
        at_limit = evaluate_voltage(policy, f, clock(110), good)
        self.assertTrue(at_limit.eligible)
        expired = evaluate_voltage(policy, f, clock(110.01), at_limit)
        self.assertEqual(expired.status, "MISSING_OR_STALE")
        self.assertEqual(expired.frame, f)
        self.assertGreater(dict(expired.ages)["L1"], 10)

    def test_monotonic_age_prevents_frozen_utc_from_refreshing_cached_samples(self):
        policy = VoltagePolicy(stable_recovery_s=0, voltage_max_age_s=10)
        good = evaluate_voltage(policy, frame(), clock())
        expired = evaluate_voltage(policy, frame(), clock(100, mono=111), good)
        self.assertFalse(expired.eligible)
        self.assertGreater(dict(expired.ages)["L2"], 10)

    def test_same_value_new_last_reported_is_fresh_but_last_changed_is_not_used(self):
        policy = VoltagePolicy(stable_recovery_s=0, voltage_max_age_s=10)
        a = evaluate_voltage(policy, frame(), clock())
        b = evaluate_voltage(policy, frame(109), clock(109), a)
        self.assertTrue(evaluate_voltage(policy, frame(118), clock(118), b).eligible)
        payload = {"phases": [], "last_changed": 118}
        with self.assertRaises(ContractError):
            decode_voltage_frame(payload)

    def test_each_missing_offline_stale_unverified_wrong_role_phase_blocks(self):
        policy = VoltagePolicy(stable_recovery_s=0)
        for i in range(3):
            for changes in (dict(online=False), dict(phase_verified=False), dict(value_v=None),
                            dict(quality=QualityStatus.STALE), dict(last_reported=60),
                            dict(provider="synthetic.tuya_local.kws"), dict(origin=SourceKind.HELD),
                            dict(last_reported=101, received_at=101), dict(received_at=99)):
                phases = list(frame().phases); phases[i] = replace(phases[i], **changes)
                state = evaluate_voltage(policy, frame(phases=tuple(phases)), clock())
                self.assertFalse(state.eligible, changes)
                self.assertIn(f"L{i+1}", state.affected_phases)
            phases = frame().phases[:i] + frame().phases[i+1:]
            self.assertFalse(evaluate_voltage(policy, frame(phases=phases), clock()).eligible)

    def test_phase_skew_trip_and_protection_age_block(self):
        phases = list(frame().phases)
        phases[0] = replace(phases[0], last_reported=94, received_at=94)
        for f in (frame(phases=tuple(phases)), frame(protection_trip=True),
                  frame(protection_last_reported=60), frame(protection_last_reported=101)):
            self.assertFalse(evaluate_voltage(VoltagePolicy(stable_recovery_s=0), f, clock()).eligible)

    def test_reordering_duplicate_conflict_clock_rollback_and_policy_changes(self):
        policy = VoltagePolicy(stable_recovery_s=0)
        old = evaluate_voltage(policy, frame(), clock())
        for phase in (replace(frame().phases[0], sequence=99),
                      replace(frame().phases[0], last_reported=99),
                      replace(frame().phases[0], value_v=231)):
            phases = (phase, *frame().phases[1:])
            self.assertFalse(evaluate_voltage(policy, frame(phases=phases), clock(101), old).eligible)
        self.assertFalse(evaluate_voltage(policy, frame(), clock(99), old).eligible)
        self.assertFalse(evaluate_voltage(policy, frame(), clock(100, mono=99), old).eligible)
        changed = replace(policy, stable_recovery_s=10)
        self.assertFalse(evaluate_voltage(changed, frame(101), clock(101), old).eligible)

    def test_gaps_between_evaluations_cannot_claim_continuous_recovery(self):
        policy = VoltagePolicy(stable_recovery_s=10, voltage_max_age_s=5)
        a = evaluate_voltage(policy, frame(), clock())
        b = evaluate_voltage(policy, frame(110), clock(110), a)
        self.assertFalse(b.eligible)
        self.assertEqual(b.recovery_since_mono, 110)

    def test_strict_schema_limits_and_no_user_identifiers(self):
        for values in (dict(min_voltage_v=True), dict(min_voltage_v=79), dict(max_voltage_v=301),
                       dict(min_voltage_v=250, max_voltage_v=250), dict(hysteresis_v=30, max_voltage_v=240),
                       dict(stable_recovery_s=-1), dict(voltage_max_age_s=0), dict(max_skew_s=-1)):
            with self.assertRaises(ContractError):
                VoltagePolicy(**values)
        for values in (dict(source_id="sensor.private"), dict(value_v=float("nan")),
                       dict(phase="L4"), dict(online=1), dict(sequence=True), dict(unit="kW")):
            with self.assertRaises(ContractError):
                replace(frame().phases[0], **values)
        with self.assertRaises(ContractError):
            frame(phases=(frame().phases[0], frame().phases[0]))

    def test_strict_decode_and_sanitized_view(self):
        payload = dict(phases=[dict(phase=p.phase,source_id=p.source_id,value_v=p.value_v,
                      last_reported=p.last_reported,received_at=p.received_at,sequence=p.sequence,
                      phase_verified=True,online=True) for p in frame().phases],
                      mapping_verified=True,grid_available=True,protection_trip=False,
                      protection_last_reported=100,protection_qualified=True)
        f = decode_voltage_frame(payload)
        self.assertEqual(f, frame())
        view = voltage_view(evaluate_voltage(VoltagePolicy(), f, clock()), VoltagePolicy())
        self.assertEqual(view["source_role"], "grid_input_voltage")
        self.assertFalse(view["physical_authority"])
        self.assertEqual(len(view["phases"]), 3)
        self.assertNotIn("source_id", str(view))
        for raw in (None, [], {"phases": [] , "unknown": True}, {"phases": [True]}):
            with self.assertRaises(ContractError):
                decode_voltage_frame(raw)
