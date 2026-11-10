"""Advancing-clock regressions with fictional, deterministic sensor observations."""
import tempfile
import unittest
from pathlib import Path

from packages.ha_native.backend import NativeBackend
from tests.wp2c_backend.test_backend import fixture, observe


class FakeClock:
    def __init__(self):
        self.utc = 1793750400.0
        self.monotonic = 100.0

    def __call__(self):
        return self.utc, self.monotonic

    def advance(self, seconds):
        self.utc += seconds
        self.monotonic += seconds


class IdleClockRegressions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='heating-wp2c-clock-regression-')
        self.clock = FakeClock()
        self.backend = NativeBackend(Path(self.temporary.name), fixture(), enabled=True, clock=self.clock)
        self.backend.open()
        observe(self.backend)

    def tearDown(self):
        self.backend.close()
        self.temporary.cleanup()

    def request(self, **extra):
        state = self.backend.status(True)
        return dict(version=[2, 0], entry_id='synthetic-entry',
                    boot_id=state['status']['boot_id'], generation=state['generation'],
                    owner_epoch=state['status']['owner_epoch'], **extra)

    def test_idle_stream_expires_without_fabricating_a_new_observation(self):
        before = self.backend.status(True)
        self.assertTrue(before['permitted'])
        self.clock.advance(30.001)
        after = self.backend.status(True)
        self.assertFalse(after['permitted'])
        self.assertEqual(after['room']['quality'], 'stale')
        self.assertEqual(after['room']['observed'], before['room']['observed'])
        self.assertEqual(after['room']['value'], before['room']['value'])
        self.assertEqual(after['now'], self.clock.utc)
        self.assertEqual(after['status']['boot_id'], before['status']['boot_id'])
        self.assertEqual(after['generation'], before['generation'])
        self.assertGreater(after['seq'], before['seq'])
        self.assertEqual(after['status']['desired'], 'stop_demand')
        self.assertFalse(after['status']['physical_verified'])

    def test_age_equality_is_fresh_and_the_next_instant_is_stale(self):
        self.clock.advance(30)
        self.assertTrue(self.backend.status(True)['permitted'])
        self.assertEqual(self.backend.status(True)['room']['quality'], 'valid')
        self.clock.advance(.001)
        self.assertFalse(self.backend.status(True)['permitted'])
        self.assertEqual(self.backend.status(True)['room']['quality'], 'stale')

    def test_advancing_monotonic_time_expires_room_if_utc_has_not_advanced(self):
        before = self.backend.status(True)
        self.clock.monotonic += 31
        expired = self.backend.status(True)
        self.assertFalse(expired['permitted'])
        self.assertEqual(expired['room']['quality'], 'stale')
        self.assertEqual(expired['room']['observed'], before['room']['observed'])
        self.assertEqual(expired['room']['value'], before['room']['value'])

    def test_idle_timeout_preserves_manual_stop_and_its_audit(self):
        receipt = self.backend.dispatch('control', self.request(kind='pause', request_id='synthetic.pause'), True)
        self.assertEqual(receipt['status'], 'accepted_fake')
        paused = self.backend.status(True)
        self.clock.advance(31)
        expired = self.backend.status(True)
        self.assertFalse(expired['permitted'])
        self.assertEqual(expired['status']['mode'], 'MANUAL_PAUSE')
        self.assertEqual(expired['status']['desired'], 'stop_demand')
        self.assertEqual(expired['oneShot'], paused['oneShot'])
        self.assertTrue(any(n['priority'] == 'manual' for n in expired['notices']))
        self.assertGreaterEqual(expired['status']['owner_epoch'], paused['status']['owner_epoch'])

    def test_utc_rollback_latches_safe_hold_without_hiding_it_on_recovery(self):
        self.backend.status(True)
        self.clock.utc -= 1
        self.clock.monotonic += 1
        rolled_back = self.backend.status(True)
        self.assertFalse(rolled_back['permitted'])
        self.assertEqual(rolled_back['status']['mode'], 'SAFE_HOLD')
        self.assertEqual(rolled_back['diagnostics']['source'], 'clock_invalid')
        self.clock.advance(2)
        self.assertFalse(self.backend.status(True)['permitted'])
        self.assertEqual(self.backend.status(True)['diagnostics']['source'], 'clock_invalid')

    def test_monotonic_rollback_cannot_restore_cached_source_eligibility(self):
        self.backend.status(True)
        self.clock.utc += 1
        self.clock.monotonic -= 1
        state = self.backend.status(True)
        self.assertFalse(state['permitted'])
        self.assertEqual(state['status']['mode'], 'SAFE_HOLD')
        self.assertEqual(state['diagnostics']['source'], 'clock_invalid')
