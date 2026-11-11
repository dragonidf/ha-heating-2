"""Issue25 synthetic supply readiness and non-actuating HEAT withdrawal fence."""
from dataclasses import replace
import unittest
from packages.ha_native.voltage import (SyntheticFeedReadiness, VoltagePolicy, evaluate_voltage,
    decode_voltage_frame, synthetic_voltage_withdrawal)
from tests.wp2c_meter.test_voltage import frame, clock


class SupplyGateTests(unittest.TestCase):
    policy = VoltagePolicy(min_voltage_v=200, max_voltage_v=250, stable_recovery_s=30)

    def ready(self, at, values=(205, 220, 245), **flags):
        return replace(frame(at, values), feed=replace(SyntheticFeedReadiness(at, True, True, True, True), **flags))

    def test_limits_and_continuous_recovery_reuse_policy(self):
        first = evaluate_voltage(self.policy, self.ready(100), clock())
        self.assertFalse(first.eligible)
        stable = evaluate_voltage(self.policy, self.ready(130), clock(130), first)
        self.assertTrue(stable.eligible)
        equal = evaluate_voltage(self.policy, self.ready(131, (200, 220, 250)), clock(131), stable)
        self.assertTrue(equal.eligible)
        for values, status in (((199, 220, 220), 'LOW'), ((251, 220, 220), 'HIGH')):
            with self.subTest(values=values):
                bad = evaluate_voltage(self.policy, self.ready(132, values), clock(132), equal)
                self.assertFalse(bad.eligible)
                self.assertEqual(bad.status, status)
                self.assertIn('L1', bad.affected_phases)
                recovered = evaluate_voltage(self.policy, self.ready(133), clock(133), bad)
                self.assertFalse(evaluate_voltage(self.policy, self.ready(162), clock(162), recovered).eligible)
                self.assertTrue(evaluate_voltage(self.policy, self.ready(163), clock(163), recovered).eligible)

    def test_grid_on_and_voltage_alone_cannot_prove_kws_output(self):
        for changes in ({'feed': None}, {'feed': SyntheticFeedReadiness(100, True, True, True, False)},
                        {'feed': SyntheticFeedReadiness(100, True, False, None, True)}, {'grid_available': False}):
            with self.subTest(changes=changes):
                state = evaluate_voltage(self.policy, replace(self.ready(100), **changes), clock())
                self.assertFalse(state.eligible)
                self.assertIsNone(state.recovery_since_mono)
        waiting = evaluate_voltage(self.policy, self.ready(110, output_ready=False), clock(110))
        self.assertIn('waiting_kws', waiting.reason)
        ready = evaluate_voltage(self.policy, self.ready(120), clock(120), waiting)
        self.assertFalse(evaluate_voltage(self.policy, self.ready(149), clock(149), ready).eligible)
        self.assertTrue(evaluate_voltage(self.policy, self.ready(150), clock(150), ready).eligible)

    def test_cached_numeric_voltage_and_readiness_age_and_restart(self):
        initial = evaluate_voltage(self.policy, self.ready(100), clock())
        healthy = evaluate_voltage(self.policy, self.ready(130), clock(130), initial)
        stale = evaluate_voltage(self.policy, healthy.frame, clock(161), healthy)
        self.assertFalse(stale.eligible)
        self.assertEqual(stale.frame.phases[0].value_v, 205)
        resumed = evaluate_voltage(self.policy, self.ready(162), clock(162), stale)
        self.assertFalse(resumed.eligible)
        restart = evaluate_voltage(self.policy, self.ready(163), clock(163, boot='synthetic.new'), resumed)
        self.assertFalse(restart.eligible)
        self.assertFalse(evaluate_voltage(self.policy, self.ready(129), clock(129), healthy).eligible)

    def test_feed_loss_and_bad_phase_reset_recovery_without_one_shot(self):
        state = evaluate_voltage(self.policy, self.ready(100), clock())
        for at, value in ((110, self.ready(110, kws_online=False)), (120, self.ready(120, (199, 220, 220)))):
            state = evaluate_voltage(self.policy, value, clock(at), state)
            self.assertIsNone(state.recovery_since_mono)
        state = evaluate_voltage(self.policy, self.ready(130), clock(130), state)
        self.assertFalse(evaluate_voltage(self.policy, self.ready(159), clock(159), state).eligible)
        self.assertTrue(evaluate_voltage(self.policy, self.ready(160), clock(160), state).eligible)

    def test_known_fault_withdraws_only_owned_fresh_manual_heat_never_auto(self):
        bad = evaluate_voltage(self.policy, self.ready(100, (199, 220, 220)), clock())
        args = dict(room_c=21, room_fresh=True, thermostat_fresh=True, owns_thermostat=True, manual_stop=False)
        intent = synthetic_voltage_withdrawal(bad, **args)
        self.assertEqual(intent['mode'], 'HEAT')
        self.assertLess(intent['setpoint_c'], 21)
        self.assertFalse(intent['physical_authority'])
        for field in ('room_fresh', 'thermostat_fresh', 'owns_thermostat'):
            self.assertIsNone(synthetic_voltage_withdrawal(bad, **(args | {field: False})))
        self.assertIsNone(synthetic_voltage_withdrawal(bad, **(args | {'manual_stop': True})))
        self.assertIsNone(synthetic_voltage_withdrawal(bad, **(args | {'room_c': None})))

    def test_decoder_defaults_unknown_not_fabricated_ready(self):
        empty = decode_voltage_frame({'phases': []})
        self.assertIsNone(empty.feed)
        self.assertFalse(evaluate_voltage(self.policy, empty, clock()).eligible)
