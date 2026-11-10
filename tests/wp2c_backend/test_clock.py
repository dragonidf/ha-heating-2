"""Trusted time advances during stream silence; refresh never invents reports."""
import tempfile
import unittest
from pathlib import Path

from packages.ha_native.backend import NativeBackend
from tests.wp2c_backend.test_backend import fixture, observe


class FakeTime:
    def __init__(self):
        self.utc = 1793750400.0
        self.monotonic = 100.0

    def __call__(self):
        return self.utc, self.monotonic

    def advance(self, seconds):
        self.utc += seconds
        self.monotonic += seconds


class TrustedClockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='heating-wp2c-')
        self.addCleanup(self.directory.cleanup)
        self.clock = FakeTime()
        self.backend = NativeBackend(Path(self.directory.name), fixture(), enabled=True, clock=self.clock)
        self.backend.open()
        observe(self.backend)
        self.addCleanup(self.backend.close)

    def test_idle_source_expires_without_a_new_event(self):
        before = self.backend.status(True)
        self.assertTrue(before['permitted'])
        self.clock.advance(31)
        self.assertTrue(self.backend.refresh())
        after = self.backend.status(True)
        self.assertFalse(after['permitted'])
        self.assertEqual(after['status']['mode'], 'SAFE_HOLD')
        self.assertEqual(after['room']['quality'], 'stale')
        self.assertEqual(after['room']['observed'], before['room']['observed'])
        self.assertEqual(after['room']['value'], before['room']['value'])
        self.assertEqual(after['now'], self.clock.utc)
        self.assertFalse(self.backend.refresh())

    def test_monotonic_time_expires_evidence_even_if_wall_time_stops(self):
        self.clock.monotonic += 31
        self.assertFalse(self.backend.status(True)['permitted'])

    def test_utc_and_monotonic_rollback_latch_fail_closed(self):
        for field in ('utc', 'monotonic'):
            with self.subTest(field=field):
                self.clock.advance(1)
                self.backend.status(True)
                setattr(self.clock, field, getattr(self.clock, field) - 2)
                self.assertFalse(self.backend.status(True)['permitted'])
                self.assertEqual(self.backend.status(True)['diagnostics']['source'], 'clock_invalid')
                self.clock.advance(10)
                self.assertFalse(self.backend.status(True)['permitted'])
                self.backend.reboot()
                observe(self.backend)
                self.assertTrue(self.backend.status(True)['permitted'])

    def test_idle_expiry_preserves_manual_stop_and_one_shot_outcome(self):
        state = self.backend.status(True)
        self.backend.stop(True, state['status']['boot_id'], state['generation'], 'clock-stop')
        self.backend.flush_stop()
        self.clock.advance(100)
        after = self.backend.status(True)
        self.assertEqual(after['status']['mode'], 'MANUAL_PAUSE')
        self.assertFalse(after['permitted'])
        self.assertEqual(after['oneShot'], state['oneShot'])
        self.assertEqual(after['status']['desired'], 'stop_demand')
