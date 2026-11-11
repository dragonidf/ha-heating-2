"""Synthetic orchestration only: no HA dependency, network or command retries."""
import asyncio
from contextlib import redirect_stderr
from copy import deepcopy
import io
import sys
import types
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Only the status-wait helper is exercised; the optional HA HTTP client is unused.
with patch.dict(sys.modules, {'aiohttp': types.ModuleType('aiohttp')}):
    from tools.wp2c.native_checks import wait_status, save_settings_once


def state(permitted=False, mode='SHADOW'):
    return dict(now=100, room=dict(observed=100, quality='valid'), permitted=permitted,
                demand_eligible=permitted, voltage=dict(status='NORMAL', eligible=True),
                status=dict(mode=mode, owner_epoch=2), oneShot=dict(state='inactive'),
                seq=2, generation=1, system_health=dict(mode='BLOCKED'),
                diagnostics=dict(persistence='ok'))


class NativeReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_durable_state_and_returns_confirmed_snapshot(self):
        reports = iter([state(), state(True)])
        async def read(operation):
            self.assertEqual(operation, 'status')
            return next(reports)
        with redirect_stderr(io.StringIO()) as output:
            ready = await wait_status(read, lambda s: s['permitted'], 'pending-critical')
        self.assertTrue(ready['permitted'])
        self.assertIn('"permitted": false', output.getvalue())
        self.assertIn('"permitted": true', output.getvalue())

    async def test_stop_and_voltage_inhibit_timeout_without_modifying_state(self):
        for mode, voltage in [('MANUAL_PAUSE', 'NORMAL'), ('SHADOW', 'STABILIZING'), ('SHADOW', 'MISSING_OR_STALE')]:
            with self.subTest(mode=mode, voltage=voltage):
                blocked = state(True, mode)
                blocked['demand_eligible'] = False
                blocked['voltage']['status'] = voltage
                original = deepcopy(blocked)
                async def read(operation):
                    self.assertEqual(operation, 'status')
                    return blocked
                with self.assertRaisesRegex(AssertionError, voltage):
                    await wait_status(read, lambda s: s['permitted'] and s['demand_eligible'], 'blocked', timeout=.01)
                self.assertEqual(blocked, original)

    async def test_unresponsive_status_read_is_bounded(self):
        async def read(operation):
            await asyncio.Event().wait()
        with self.assertRaisesRegex(AssertionError, 'status_timeout'):
            await wait_status(read, lambda s: s['permitted'], 'lost-response', timeout=.01)


class NativeSettingsReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_age_valid_room_waits_for_health_flush_then_one_cas_write(self):
        from packages.ha_native.backend import NativeBackend
        from packages.contracts import Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
        from packages.offline.contracts import SourceEvent
        from tests.wp2c_backend.test_backend import fixture, observe
        from tests.wp2c_backend.test_clock import FakeTime
        with tempfile.TemporaryDirectory(prefix='heating-wp2c-') as root:
            clock = FakeTime()
            backend = NativeBackend(Path(root), fixture(), enabled=True, clock=clock)
            backend.configure_source(120);backend.open()
            self.addCleanup(backend.close)
            observe(backend)
            clock.advance(60)
            self.assertTrue(backend.flush_stop())
            self.assertTrue(backend.status(True)['permitted'])
            backend.invalidate_source('synthetic-reload')
            backend.status(True)  # Health records the missing-source transition.
            at = clock.utc - 60
            reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
                value=21.8, unit=Unit.CELSIUS, observed_at=at, received_at=at,
                quality=Quality(status=QualityStatus.VALID, age_s=60, reason='synthetic'),
                provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
            self.assertTrue(backend.accept_source(SourceEvent('synthetic-restored', 'synthetic.native.room', 1, at, reading)))
            before = backend.status(True)
            self.assertEqual(before['room']['quality'], 'valid')
            self.assertEqual(before['now'] - before['room']['observed'], 60)
            self.assertTrue(backend._pending_stop)
            self.assertFalse(before['permitted'])
            settings = backend.critical.read('settings')
            values = settings['values'] | {'day': 22}
            common = dict(entry_id='synthetic-entry', version=[2, 0])
            premature = common | dict(boot_id=before['status']['boot_id'], generation=before['generation'],
                owner_epoch=before['status']['owner_epoch'], request_id='premature', expected_revision=settings['revision'], values=values)
            receipt = backend.dispatch('settings/save', premature, True)
            self.assertEqual(receipt['status'], 'denied')
            self.assertEqual(receipt['reason'], 'denied')
            self.assertEqual(backend.critical.read('settings'), settings)
            self.assertNotIn('premature', backend.critical.read('requests'))
            reads, writes = 0, []
            async def read(operation):
                nonlocal reads
                if operation == 'status':
                    reads += 1
                    if reads == 2:
                        self.assertTrue(backend.flush_stop())
                    return backend.status(True)
                return backend.critical.read('settings')
            async def save(body):
                writes.append(body)
                self.assertFalse(backend._pending_stop)
                self.assertEqual(body['owner_epoch'], backend.status(True)['status']['owner_epoch'])
                return backend.dispatch('settings/save', body, True)
            with redirect_stderr(io.StringIO()):
                receipt, body = await save_settings_once(read, save, common, settings, values, 'one-save')
            self.assertEqual(len(writes), 1)
            self.assertEqual(body['expected_revision'], settings['revision'])
            self.assertEqual(receipt['status'], 'saved')
            stored = backend.critical.read('settings')
            self.assertEqual(stored['values'], values)
            self.assertEqual(stored['revision'], settings['revision'] + 1)
            self.assertEqual(stored['lastRequest'], 'one-save')
            self.assertEqual(backend.critical.read('snapshot')['health_memory'], backend.status(True)['health_memory'])

    async def test_failed_save_reports_status_cas_and_mismatch_without_retry(self):
        ready = state(True)
        ready['status']['boot_id'] = 'synthetic.boot'
        for status in ('denied', 'unavailable', 'conflict'):
            calls = []
            async def read(operation):
                return ready if operation == 'status' else {'revision': 7, 'values': {'day': 21}}
            async def save(body):
                calls.append(body)
                return {'status': status, 'reason': status, 'revision': 7}
            with self.assertRaises(AssertionError) as error:
                await save_settings_once(read, save, {}, {'revision': 7}, {'day': 22}, 'synthetic-save')
            self.assertEqual(len(calls), 1)
            details = error.exception.args[0]
            self.assertEqual(details['after']['receipt']['status'], status)
            self.assertEqual(details['expected_revision'], 7)
            self.assertEqual(details['stored_revision'], 7)
            self.assertEqual(details['mismatched_keys'], ['day'])
