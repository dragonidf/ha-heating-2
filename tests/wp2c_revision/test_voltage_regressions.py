"""Additional synthetic boundary and uninterrupted-recovery cases."""
from dataclasses import replace
import unittest

from packages.contracts import Clock
from packages.ha_native.voltage import (
    VoltageFrame, VoltagePhase, VoltagePolicy, evaluate_voltage,
)


def clock(at):
    return Clock(utc=at, monotonic=at, boot_id='synthetic.boundary.boot')


def frame(at, values=(230, 230, 230), **changes):
    phases = tuple(VoltagePhase(phase, f'synthetic.input220.boundary.{phase}', value,
                               at, at, int(at), phase_verified=True, online=True)
                   for phase, value in zip(('L1', 'L2', 'L3'), values))
    return VoltageFrame(phases=phases, mapping_verified=True, grid_available=True,
                        protection_trip=False, protection_last_reported=at,
                        protection_qualified=True, **changes)


class VoltageRecoveryRegressions(unittest.TestCase):
    def test_equal_outer_boundaries_do_not_count_towards_blocked_recovery(self):
        policy = VoltagePolicy(stable_recovery_s=10)
        for outer, inner in ((190, 195), (250, 245)):
            with self.subTest(outer=outer):
                state = evaluate_voltage(policy, frame(100, (180, 230, 230)), clock(100))
                for at in (101, 110, 120):
                    state = evaluate_voltage(policy, frame(at, (outer, 230, 230)), clock(at), state)
                    self.assertFalse(state.eligible)
                state = evaluate_voltage(policy, frame(121, (inner, 230, 230)), clock(121), state)
                self.assertEqual(state.status, 'STABILIZING')
                state = evaluate_voltage(policy, frame(130, (inner, 230, 230)), clock(130), state)
                self.assertFalse(state.eligible)
                state = evaluate_voltage(policy, frame(131, (inner, 230, 230)), clock(131), state)
                self.assertTrue(state.eligible)

    def test_fresh_same_value_heartbeats_at_age_limit_sustain_inner_band_dwell(self):
        policy = VoltagePolicy(stable_recovery_s=10, voltage_max_age_s=5)
        state = evaluate_voltage(policy, frame(100, (195, 245, 230)), clock(100))
        self.assertFalse(state.eligible)
        state = evaluate_voltage(policy, frame(105, (195, 245, 230)), clock(105), state)
        self.assertFalse(state.eligible)
        state = evaluate_voltage(policy, frame(110, (195, 245, 230)), clock(110), state)
        self.assertTrue(state.eligible)
        self.assertEqual(state.status, 'NORMAL')

    def test_alternating_affected_phases_require_one_complete_shared_recovery_window(self):
        policy = VoltagePolicy(stable_recovery_s=10)
        state = evaluate_voltage(policy, frame(100, (180, 230, 230)), clock(100))
        state = evaluate_voltage(policy, frame(105), clock(105), state)
        state = evaluate_voltage(policy, frame(114, (230, 251, 230)), clock(114), state)
        self.assertFalse(state.eligible)
        self.assertIn('L2', state.affected_phases)
        state = evaluate_voltage(policy, frame(115), clock(115), state)
        state = evaluate_voltage(policy, frame(124), clock(124), state)
        self.assertFalse(state.eligible)
        state = evaluate_voltage(policy, frame(125), clock(125), state)
        self.assertTrue(state.eligible)

    def test_missing_one_phase_resets_dwell_even_when_other_heartbeats_continue(self):
        policy = VoltagePolicy(stable_recovery_s=10)
        state = evaluate_voltage(policy, frame(100), clock(100))
        incomplete = replace(frame(109), phases=frame(109).phases[:2])
        state = evaluate_voltage(policy, incomplete, clock(109), state)
        self.assertFalse(state.eligible)
        self.assertIn('L3', state.affected_phases)
        state = evaluate_voltage(policy, frame(110), clock(110), state)
        state = evaluate_voltage(policy, frame(119), clock(119), state)
        self.assertFalse(state.eligible)
        state = evaluate_voltage(policy, frame(120), clock(120), state)
        self.assertTrue(state.eligible)
