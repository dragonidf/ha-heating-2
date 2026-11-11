"""Native demand gating composes voltage evidence, clock expiry and manual priority."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from packages.ha_native.backend import NativeBackend
from packages.ha_native.voltage import SyntheticFeedReadiness, VoltageFrame, VoltagePhase
from tests.wp2c_backend.test_backend import fixture, observe
from tests.wp2c_backend.test_clock import FakeTime


class VoltageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='heating-wp2c-')
        self.addCleanup(self.directory.cleanup)
        self.clock = FakeTime()
        self.backend = NativeBackend(Path(self.directory.name), fixture(), enabled=True, clock=self.clock)
        self.backend.open()
        observe(self.backend)
        self.addCleanup(self.backend.close)

    def frame(self, values=(220, 220, 220), sequence=1):
        return VoltageFrame(tuple(VoltagePhase(p, 'synthetic.input.' + p, value, self.clock.utc,
            self.clock.utc, sequence, phase_verified=True, online=True)
            for p, value in zip(('L1', 'L2', 'L3'), values)), mapping_verified=True,
            grid_available=True, protection_trip=False, protection_last_reported=self.clock.utc,
            protection_qualified=True, feed=SyntheticFeedReadiness(self.clock.utc, True, True, True, True))

    def request(self, **values):
        state = self.backend.status(True)
        return dict(version=[2, 0], entry_id='synthetic-entry', boot_id=state['status']['boot_id'],
            generation=state['generation'], owner_epoch=state['status']['owner_epoch'], **values)

    def test_missing_voltage_denies_arm_but_operator_can_edit_settings(self):
        self.backend.accept_voltage(VoltageFrame())
        self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertTrue(state['permitted'])
        self.assertFalse(state['demand_eligible'])
        self.assertEqual(state['voltage']['status'], 'MISSING_OR_STALE')
        self.assertEqual(self.backend.dispatch('control', self.request(kind='arm'), True)['status'], 'denied')
        settings = self.backend.critical.read('settings')
        result = self.backend.dispatch('settings/save', self.request(request_id='guard-fix',
            expected_revision=settings['revision'], values=settings['values'] | {'max_voltage_v': 245}), True)
        self.assertEqual(result['status'], 'saved')

    def test_voltage_idle_expiry_is_independent_from_room_age(self):
        self.backend.configure_source(120)
        observe(self.backend)
        settings = self.backend.critical.read('settings')
        result = self.backend.dispatch('settings/save', self.request(request_id='short-voltage-age',
            expected_revision=settings['revision'], values=settings['values'] | {'voltage_max_age_s': 5}), True)
        self.assertEqual(result['status'], 'saved')
        self.backend.accept_voltage(self.frame())
        self.backend.flush_stop()
        self.assertTrue(self.backend.status(True)['demand_eligible'])
        before = self.backend.status(True)['voltage']['phases']
        self.clock.advance(6)
        self.backend.refresh()
        self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertTrue(state['permitted'])
        self.assertEqual(state['room']['quality'], 'valid')
        self.assertFalse(state['demand_eligible'])
        self.assertEqual(state['voltage']['status'], 'MISSING_OR_STALE')
        self.assertEqual([p['voltage_v'] for p in state['voltage']['phases']], [p['voltage_v'] for p in before])
        self.assertEqual(state['voltage']['ages']['L1'], 6)

    def test_voltage_recovery_never_clears_manual_pause_or_replays_oneshot(self):
        self.assertEqual(self.backend.dispatch('control', self.request(kind='arm'), True)['status'], 'accepted_fake')
        self.backend.dispatch('control', self.request(kind='unknown'), True)
        self.backend.stop_request(self.request(kind='pause', request_id='priority'), True)
        self.backend.flush_stop()
        self.backend.accept_voltage(self.frame((180, 220, 260)))
        self.backend.flush_stop()
        self.assertEqual(self.backend.status(True)['voltage']['status'], 'LOW')
        self.clock.advance(1)
        self.backend.accept_voltage(self.frame(sequence=2))
        self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertEqual(state['voltage']['status'], 'NORMAL')
        self.assertEqual(state['status']['mode'], 'MANUAL_PAUSE')
        self.assertFalse(state['demand_eligible'])
        self.assertEqual(state['oneShot']['state'], 'unknown_outcome')
        self.assertEqual(state['status']['desired'], 'stop_demand')

    def test_rollback_does_not_block_memory_only_stop_and_idle_oneshot_expiry(self):
        self.assertEqual(self.backend.dispatch('control', self.request(kind='arm'), True)['status'], 'accepted_fake')
        expires = self.backend.status(True)['oneShot']['expires']
        self.clock.advance(expires - self.clock.utc)
        state = self.backend.status(True)
        self.assertEqual(state['oneShot']['state'], 'expired')
        self.assertFalse(state['demand_eligible'])
        self.clock.utc -= 1
        body = self.request(kind='pause', request_id='rollback-stop')
        with patch.object(self.backend.critical, 'connect', side_effect=AssertionError('STOP touched disk')):
            self.assertEqual(self.backend.stop_request(body, True)['status'], 'accepted_fake')
        self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
        self.assertFalse(self.backend.status(True)['demand_eligible'])

    def test_kws_counter_pairs_persist_once_without_cloud_fallback(self):
        from tests.wp2c_meter.test_kws import frame
        self.backend.accept_power(frame(self.clock.utc, kwh=10))
        self.assertTrue(self.backend.flush_evidence())
        self.clock.advance(10)
        self.backend.accept_power(frame(self.clock.utc, kwh=10.001))
        self.assertTrue(self.backend.flush_evidence())
        self.assertAlmostEqual(self.backend._boiler_energy()['known_kwh'], .001)
        self.backend.accept_power(frame(self.clock.utc, kwh=10.001))
        self.assertTrue(self.backend.flush_evidence())
        self.assertEqual(self.backend._boiler_energy()['interval_count'], 1)
        self.clock.advance(10)
        self.backend.accept_power(frame(self.clock.utc, kwh=20, provider='tuya_cloud'))
        self.assertTrue(self.backend.flush_evidence())
        self.assertEqual(self.backend._boiler_energy()['interval_count'], 1)
        self.backend.close()
        self.backend.open()
        self.assertAlmostEqual(self.backend._boiler_energy()['known_kwh'], .001)

    def test_manual_resume_requires_durable_voltage_reconciliation(self):
        self.backend.accept_voltage(self.frame())
        self.backend.flush_stop()
        self.backend.stop_request(self.request(kind='pause', request_id='pause-reconcile'), True)
        self.backend.flush_stop()
        self.clock.advance(30)
        self.backend.accept_voltage(self.frame(sequence=2))
        state = self.backend.status(True)
        self.assertEqual(state['status']['mode'], 'MANUAL_PAUSE')
        self.assertFalse(state['permitted'])
        denied = self.backend.dispatch('control', self.request(kind='resume', request_id='resume-before-flush'), True)
        self.assertEqual(denied['status'], 'denied')
        self.backend.flush_stop()
        accepted = self.backend.dispatch('control', self.request(kind='resume', request_id='resume-after-flush'), True)
        self.assertEqual(accepted['status'], 'accepted_fake')
        self.assertEqual(self.backend.status(True)['status']['mode'], 'RECOVERING')
        self.assertFalse(self.backend.status(True)['demand_eligible'])

    def test_known_voltage_fault_fences_owned_intent_from_auto_and_manual_stop(self):
        self.backend.accept_voltage(self.frame((199, 220, 220)))
        # Existing minimum is190; use an actual below-limit fault without changing settings.
        self.backend.accept_voltage(self.frame((189, 220, 220), sequence=2))
        self.backend.flush_stop()
        state = self.backend.status(True)
        args = dict(owner_epoch=state['status']['owner_epoch'], owns_thermostat=True, thermostat_fresh=True)
        intent = self.backend.voltage_stop_intent(**args)
        self.assertEqual(intent['mode'], 'HEAT')
        self.assertLess(intent['setpoint_c'], state['room']['value'])
        self.assertIsNone(self.backend.voltage_stop_intent(**(args | {'owner_epoch': args['owner_epoch'] - 1})))
        self.assertIsNone(self.backend.voltage_stop_intent(**(args | {'thermostat_fresh': False})))
        self.backend.stop_request(self.request(kind='pause', request_id='supply-stop'), True)
        args['owner_epoch'] = self.backend.status(True)['status']['owner_epoch']
        self.assertIsNone(self.backend.voltage_stop_intent(**args))
