"""Additive settings schema preserves old revisions, receipts and chosen guard bounds."""
import tempfile
import unittest
from pathlib import Path

from packages.ha_native.backend import NativeBackend, VOLTAGE_DEFAULTS
from packages.ha_native.store import NativeStore, StoreError
from tests.wp2c_backend.test_backend import fixture, observe


class SettingsRevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='heating-wp2c-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_legacy_settings_migrate_without_changing_revision_receipts_or_request(self):
        f = fixture()
        legacy = {k: v for k, v in f['settings'].items() if k not in VOLTAGE_DEFAULTS}
        requests = {'old-committed': {'signature': 'original-request-bytes', 'result': {'status': 'saved'}}}
        store = NativeStore(self.root, 'critical')
        store.open({'settings': {'revision': 7, 'values': legacy, 'lastRequest': 'old-committed'},
                    'snapshot': f['snapshot'], 'requests': requests,
                    'model': {'revision': 3, 'candidate': False, 'frozen': False}})
        backend = NativeBackend(self.root, f)
        backend.open()
        current = backend.critical.read('settings')
        self.assertEqual(current, {'revision': 7, 'values': legacy | VOLTAGE_DEFAULTS, 'lastRequest': 'old-committed'})
        self.assertEqual(backend.critical.read('requests'), requests)
        self.assertEqual(backend.critical.read('settings_schema'), 2)
        backend.close()

    def test_legacy_save_preserves_already_chosen_voltage_limits(self):
        f = fixture()
        backend = NativeBackend(self.root, f, enabled=True)
        backend.open()
        observe(backend)
        def save(request, expected, values):
            backend.refresh()
            backend.flush_stop()
            state = backend.status(True)
            return backend.dispatch('settings/save', dict(entry_id='synthetic-entry', version=[2, 0],
                boot_id=state['status']['boot_id'], generation=state['generation'], owner_epoch=state['status']['owner_epoch'],
                request_id=request, expected_revision=expected, values=values), True)
        limits = {'min_voltage_v': 200, 'max_voltage_v': 245, 'hysteresis_v': 3,
                  'stable_recovery_s': 10, 'voltage_max_age_s': 15}
        self.assertEqual(save('full', 1, f['settings'] | limits)['status'], 'saved')
        legacy = {k: v for k, v in f['settings'].items() if k not in VOLTAGE_DEFAULTS}
        self.assertEqual(save('legacy', 2, legacy | {'fan': 50})['status'], 'saved')
        current = backend.critical.read('settings')
        self.assertEqual({k: current['values'][k] for k in limits}, limits)
        self.assertEqual(current['values']['fan'], 50)
        backend.close()

    def test_future_or_partial_declared_schema_fails_closed(self):
        for schema in (3, 2):
            with self.subTest(schema=schema):
                f = fixture()
                backend = NativeBackend(self.root, f)
                backend.open()
                with backend.critical.transaction() as con:
                    backend.critical.write(con, 'settings_schema', schema)
                    if schema == 2:
                        saved = backend.critical.read_from(con, 'settings')
                        saved['values'].pop('min_voltage_v')
                        backend.critical.write(con, 'settings', saved)
                with self.assertRaises(StoreError):
                    backend.reboot()
                self.assertFalse(backend.status(True)['permitted'])
                backend.close()
                # Restore only the disposable record for the next independent schema case.
                with backend.critical.transaction() as con:
                    backend.critical.write(con, 'settings_schema', 2)
                    backend.critical.write(con, 'settings', {'revision': 1, 'values': f['settings'], 'lastRequest': None})
