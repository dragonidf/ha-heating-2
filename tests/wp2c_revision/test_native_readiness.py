"""Synthetic orchestration only: no HA dependency, network or command retries."""
import asyncio
from contextlib import redirect_stderr
from copy import deepcopy
import io
import sys
import types
import unittest
from unittest.mock import patch

# Only the status-wait helper is exercised; the optional HA HTTP client is unused.
with patch.dict(sys.modules, {'aiohttp': types.ModuleType('aiohttp')}):
    from tools.wp2c.native_checks import wait_status


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
