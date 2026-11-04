"""Synthetic native service contract: actual disposable SQLite, no HA/device I/O."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from packages.ha_native.backend import NativeBackend, NativeProtocolError
from packages.ha_native.store import NativeStore, StoreError


def fixture():
    wire = json.loads(Path('frontend/src/contracts.fixture.json').read_text())
    return {'snapshot': {'version': 1, 'seq': 1, 'generation': 1, 'now': 1793750400,
        'connected': True, 'permitted': True, 'status': wire['status']['data'],
        'room': {'value': 21.8, 'observed': 1793750400, 'quality': 'valid'}, 'grid': True,
        'notices': [], 'fan': {'phase': 'Спокій', 'requested': 0, 'actual': None, 'night': True, 'fire': False},
        'oneShot': {'state': 'inactive', 'expires': None, 'gridEpoch': 4},
        'diagnostics': {'loopLagMs': 8, 'persistence': 'ok', 'worker': 'ready', 'source': 'valid'}},
        'settings': {'day': 21.5, 'night': 20.5, 'budget': 650, 'windowStart': '23:00',
        'windowEnd': '07:00', 'strategy': 'balanced', 'mode': 'auto', 'circulation': 'auto',
        'fan': 42, 'scenario': 6, 'freshness': 30, 'aiAdvice': False},
        'actual': [{'at': 1793750300, 'value': 21.8, 'quality': 'valid'}], 'intervals': [],
        'original': None, 'latest': [], 'cycleEnergy': {}, 'timeline': [], 'metrics': []}


def observe(backend):
    from packages.contracts import Clock, Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
    from packages.offline.contracts import SourceEvent
    state = backend.status(True)
    now, boot = state['now'], state['status']['boot_id']
    reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
        value=21.8, unit=Unit.CELSIUS, observed_at=now, received_at=now,
        quality=Quality(status=QualityStatus.VALID, age_s=0, reason='synthetic-test'),
        provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
    assert backend.accept_source(SourceEvent(boot + '.setup', 'synthetic.native.room', 0, now, reading),
                                 Clock(utc=now, monotonic=0, boot_id=boot))
    assert backend.flush_stop()


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='heating-wp2c-'))
        self.backend = NativeBackend(self.root, fixture(), enabled=True)
        self.backend.open()
        observe(self.backend)

    def tearDown(self):
        self.backend.close()
        shutil.rmtree(self.root)

    def request(self, **extra):
        state = self.backend.status(True)
        return dict(version=[2, 0], entry_id='synthetic-entry', boot_id=state['status']['boot_id'],
                    generation=state['generation'], owner_epoch=state['status']['owner_epoch'], **extra)

    def test_default_disabled_and_authoritative_permissions(self):
        other = NativeBackend(self.root, fixture())
        other.open()
        self.assertFalse(other.status(True)['permitted'])
        self.assertEqual(other.status(True)['status']['mode'], 'SAFE_HOLD')
        self.assertFalse(self.backend.status(False)['permitted'])
        self.assertFalse(self.backend.status(True)['status']['physical_verified'])
        other.close()

    def test_cas_readback_and_duplicate_body(self):
        values = fixture()['settings'] | {'day': 22}
        body = self.request(request_id='save-1', expected_revision=1, values=values)
        first = self.backend.dispatch('settings/save', body, True)
        self.assertEqual(first['status'], 'saved')
        self.assertEqual(first['persisted_revision'], 2)
        self.assertEqual(first, self.backend.dispatch('settings/save', body, True))
        changed = body | {'values': values | {'day': 23}}
        self.assertEqual(self.backend.dispatch('settings/save', changed, True)['status'], 'conflict')
        self.assertEqual(self.backend.dispatch('settings/save', body | {'request_id': 'save-2', 'owner_epoch': self.backend.status(True)['status']['owner_epoch']}, True)['status'], 'conflict')
        self.assertEqual(self.backend.dispatch('settings/get', {'entry_id': 'synthetic-entry', 'version': [2, 0]}, False)['values'], values)

    def test_boundary_tampering(self):
        read = {'entry_id': 'synthetic-entry', 'version': [2, 0]}
        for invalid in (None, [], read | {'admin': True}, read | {'version': [1, 0]}, read | {'entry_id': 'foreign'}, read | {'huge': 'x' * 262144}, read | {'x': float('nan')}):
            with self.assertRaises(NativeProtocolError):
                self.backend.dispatch('status', invalid, True)
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('arbitrary/service', read, True)
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('diagnostics', read, False)
        for invalid in (self.request(kind='arm') | {'generation': 0}, self.request(kind='arm') | {'boot_id': 'old'}):
            with self.assertRaises(NativeProtocolError):
                self.backend.dispatch('control', invalid, True)

    def test_settings_validation_and_denial(self):
        values = fixture()['settings']
        for changes in ({'day': 21.1}, {'day': True}, {'night': 26}, {'budget': '5 kWh'}, {'fan': 1.5}, {'freshness': 301}, {'windowStart': '24:00'}, {'windowEnd': '23:00'}, {'strategy': 'x'}, {'mode': 'x'}, {'circulation': 'x'}, {'scenario': 2}, {'aiAdvice': 1}, {'extra': 1}):
            result = self.backend.dispatch('settings/save', self.request(request_id='bad', expected_revision=1, values=values | changes), True)
            self.assertEqual(result['status'], 'denied', changes)
        self.assertEqual(self.backend.dispatch('control', self.request(kind='arm'), False)['status'], 'denied')

    def test_manual_oneshot_restart_and_fencing(self):
        stale = self.request(kind='arm')
        self.assertEqual(self.backend.dispatch('control', stale, True)['status'], 'accepted_fake')
        self.backend.dispatch('control', self.request(kind='unknown'), True)
        self.assertEqual(self.backend.dispatch('control', self.request(kind='arm'), True)['status'], 'denied')
        self.backend.dispatch('control', self.request(kind='pause'), True)
        self.backend.reboot()
        self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
        self.assertEqual(self.backend.status(True)['oneShot']['state'], 'unknown_outcome')
        self.assertEqual(self.backend.status(True)['status']['desired'], 'stop_demand')
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('control', stale, True)

    def test_archive_failure_does_not_block_stop(self):
        self.backend.evidence.path.write_bytes(b'broken archive')
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('history', self.request(start=1793750000, end=1793750400, cursor=None, limit=128), True)
        body = self.request(kind='pause')
        with patch.object(self.backend.critical, 'connect', side_effect=StoreError('locked')):
            result = self.backend.stop(True, body['boot_id'], body['generation'], 'stop')
            self.assertEqual(result['status'], 'accepted_fake')
            self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
            self.assertFalse(self.backend.flush_stop())
        self.assertTrue(self.backend.flush_stop())

    def test_history_cursor_and_energy_independence(self):
        body = self.request(start=1793750000, end=1793750400, cursor=None, limit=1)
        body.pop('boot_id'); body.pop('generation'); body.pop('owner_epoch')
        self.assertEqual(len(self.backend.dispatch('history', body, True)['rows']), 1)
        for changes in ({'limit': 257}, {'end': body['start']}, {'end': body['start'] + 32 * 86400}, {'cursor': {'scope': 'x', 'offset': 0, 'watermark': 1}}):
            with self.assertRaises(NativeProtocolError):
                self.backend.dispatch('history', body | changes, True)
        self.assertEqual(self.backend.dispatch('energy', {'entry_id': 'synthetic-entry', 'version': [2, 0]}, True), [])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='heating-wp2c-'))
        self.store = NativeStore(self.root, 'critical')
        self.store.open({'state': {'revision': 1}})

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_wal_full_backup_migration_and_rollback(self):
        with self.store.connect() as con:
            self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(con.execute('PRAGMA synchronous').fetchone()[0], 2)
            con.execute('PRAGMA user_version=1')
        self.store.open({})
        self.assertTrue(self.store.path.with_suffix('.migration.sqlite3').exists())
        self.store.rollback_migration()
        with self.store.connect() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 1)
        self.store.open({})
        self.assertEqual(self.store.read('state'), {'revision': 1})

    def test_lock_readonly_checksum_and_fault_rollback(self):
        with self.store.connect() as lock:
            lock.execute('BEGIN IMMEDIATE')
            with self.assertRaises(StoreError):
                with self.store.transaction() as con:
                    self.store.write(con, 'state', {'revision': 2})
            lock.rollback()
        for error in (OSError(5, 'EIO'), OSError(28, 'ENOSPC')):
            self.store.hook = lambda point, e=error: (_ for _ in ()).throw(e)
            with self.assertRaises(StoreError):
                with self.store.transaction() as con:
                    self.store.write(con, 'state', {'revision': 2})
            self.store.hook = None
            self.assertEqual(self.store.read('state'), {'revision': 1})
        readonly = NativeStore(self.root, 'critical', readonly=True)
        readonly.open({})
        with self.assertRaises(StoreError):
            with readonly.transaction() as con:
                readonly.write(con, 'state', {})
        with self.store.connect() as con:
            con.execute("UPDATE records SET digest='wrong'")
        with self.assertRaises(StoreError):
            self.store.read('state')

    def test_rejects_foreign_and_linked_root(self):
        with self.assertRaises(StoreError):
            NativeStore(Path('/workspace'), 'critical')
        self.store.path.unlink()
        self.store.path.symlink_to(self.root / 'missing')
        with self.assertRaises(StoreError):
            self.store.open({})

class ExtendedBackendTests(unittest.TestCase):
    setUp = BackendTests.setUp
    tearDown = BackendTests.tearDown
    request = BackendTests.request
    def test_model_persisted_demo_and_immutable_original(self):
        read = {'entry_id': 'synthetic-entry', 'version': [2, 0]}
        original = self.backend.dispatch('overview', read, True)['original']
        for kind, revision in [('promote', 3), ('train', 3), ('promote', 4), ('freeze', 4), ('train', 4), ('rollback', 3), ('freeze', 3)]:
            result = self.backend.dispatch('model', self.request(kind=kind), True)
            self.assertEqual(result['model']['revision'], revision)
        self.backend.reboot()
        self.assertEqual(self.backend.dispatch('overview', read, True)['original'], original)
        self.assertEqual(self.backend.dispatch('diagnostics', read, True)['kernel_reason'], 'shadow')
        self.assertFalse(self.backend.safety_permit().allowed)

    def test_own_source_updates_reject_stale_duplicate_wrong_provenance(self):
        from packages.contracts import Clock, Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
        from packages.offline.contracts import SourceEvent
        now = self.backend.status(True)['now']
        boot = self.backend.status(True)['status']['boot_id']
        def event(seq, at=None, entity='synthetic.native.room', value=0):
            at = now if at is None else at
            reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
                value=value, unit=Unit.CELSIUS, observed_at=at, received_at=at,
                quality=Quality(status=QualityStatus.VALID, age_s=0, reason='synthetic'),
                provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
            return SourceEvent('event-' + str(seq), entity, seq, at, reading)
        self.backend.invalidate_source('registry_removed')
        self.assertFalse(self.backend.status(True)['permitted'])
        self.assertEqual(self.backend.status(True)['status']['mode'], 'SAFE_HOLD')
        self.assertTrue(self.backend.accept_source(event(1), Clock(utc=now, monotonic=0, boot_id=boot)))
        self.assertFalse(self.backend.status(True)['permitted'])  # pending durable reconciliation
        self.assertTrue(self.backend.flush_stop())
        self.assertEqual(self.backend.status(True)['room']['value'], 0)
        self.assertTrue(self.backend.status(True)['permitted'])
        self.assertFalse(self.backend.accept_source(event(1), Clock(utc=now, monotonic=0, boot_id=boot)))
        self.assertFalse(self.backend.accept_source(event(2), Clock(utc=now, monotonic=0, boot_id='old')))
        self.assertFalse(self.backend.accept_source(event(3, now - 100), Clock(utc=now, monotonic=0, boot_id=boot)))
        self.assertFalse(self.backend.accept_source(event(4, entity='synthetic.foreign'), Clock(utc=now, monotonic=0, boot_id=boot)))
        self.assertFalse(self.backend.status(True)['permitted'])

    def test_duplicate_writer_and_disabled_stop(self):
        stale = self.request(kind='arm')
        other = NativeBackend(self.root, fixture(), enabled=True)
        other.open()
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('control', stale, True)
        disabled = NativeBackend(self.root, fixture())
        disabled.open()
        status = disabled.status(True)
        self.assertEqual(disabled.stop(True, status['status']['boot_id'], status['generation'], 'stop')['status'], 'denied')
        other.close(); disabled.close()

    def test_recovery_never_replays_pending_or_consumed(self):
        for state in ('armed', 'consumed'):
            with self.backend.critical.transaction() as con:
                persisted = self.backend.critical.read_from(con, 'snapshot')
                persisted['oneShot']['state'] = state
                persisted['status']['desired'] = 'heat'
                self.backend.critical.write(con, 'snapshot', persisted)
            self.backend.reboot()
            self.assertEqual(self.backend.status(True)['oneShot']['state'], 'unknown_outcome' if state == 'armed' else 'consumed')
            self.assertEqual(self.backend.status(True)['status']['desired'], 'stop_demand')

    def test_rejected_mutation_forms_and_safe_resume(self):
        for operation, changes in [('control', {'kind': 'x'}), ('model', {'kind': 'x'}),
                ('control', {'kind': 'arm', 'request_id': ''}),
                ('settings/save', {'expected_revision': 1, 'values': fixture()['settings']})]:
            with self.assertRaises(NativeProtocolError):
                self.backend.dispatch(operation, self.request(**changes), True)
        self.assertEqual(self.backend.dispatch('control', self.request(kind='consume'), True)['status'], 'denied')
        for kind in ('arm', 'cancel', 'expire', 'pause', 'resume'):
            self.assertEqual(self.backend.dispatch('control', self.request(kind=kind), True)['status'], 'accepted_fake')
        self.assertEqual(self.backend.status(True)['status']['mode'], 'RECOVERING')
        self.assertFalse(self.backend.status(True)['permitted'])
        self.assertEqual(self.backend.dispatch('subscribe', {'entry_id': 'synthetic-entry', 'version': [2, 0]}, True)['status']['desired'], 'stop_demand')

    def test_settings_write_readback_and_fault_uncertainty(self):
        for circulation in ('manual', 'stop'):
            revision = self.backend.critical.read('settings')['revision']
            receipt = self.backend.dispatch('settings/save', self.request(request_id='fan-' + circulation,
                expected_revision=revision, values=fixture()['settings'] | {'circulation': circulation}), True)
            self.assertEqual(receipt['status'], 'saved')
            self.assertEqual(self.backend.status(True)['fan']['requested'], 42 if circulation == 'manual' else 0)
        read = self.backend.critical.read
        def corrupt_read(name):
            value = read(name)
            if name == 'settings':
                value['revision'] = 999
            return value
        with patch.object(self.backend.critical, 'read', side_effect=corrupt_read):
            result = self.backend.dispatch('settings/save', self.request(request_id='readback', expected_revision=3,
                values=fixture()['settings']), True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(self.backend.status(True)['permitted'])
        # STOP remains admitted after a critical write/readback failure.
        self.assertEqual(self.backend.dispatch('control', self.request(kind='pause'), True)['status'], 'accepted_fake')
        self.backend.critical.hook = lambda _: (_ for _ in ()).throw(OSError(28, 'disk full'))
        result = self.backend.dispatch('settings/save', self.request(request_id='disk', expected_revision=4,
            values=fixture()['settings']), True)
        self.assertEqual(result['status'], 'unavailable')

    def test_concurrent_stop_supersedes_settings_commit_without_blocking(self):
        import threading
        reached = threading.Event()
        release = threading.Event()
        def block(point):
            reached.set()
            self.assertTrue(release.wait(2))
        self.backend.critical.hook = block
        body = self.request(request_id='racing', expected_revision=1, values=fixture()['settings'])
        results = []
        worker = threading.Thread(target=lambda: results.append(self.backend.dispatch('settings/save', body, True)))
        worker.start()
        self.assertTrue(reached.wait(2))
        before = self.backend.status(True)
        self.assertEqual(self.backend.stop(True, before['status']['boot_id'], before['generation'], 'independent')['status'], 'accepted_fake')
        self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0]['status'], 'unavailable')
        self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
        self.backend.critical.hook = None
        self.assertTrue(self.backend.flush_stop())
        self.backend.reboot()
        self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')

    def test_history_stable_pagination_bounds_and_untrusted_cursor(self):
        with self.backend.evidence.transaction() as con:
            f = self.backend.evidence.read_from(con, 'fixture')
            f['actual'] = [{'at': i, 'value': i} for i in range(10)]
            self.backend.evidence.write(con, 'fixture', f)
        body = {'entry_id': 'synthetic-entry', 'version': [2, 0], 'start': 0, 'end': 10, 'limit': 3}
        first = self.backend.dispatch('history', body, True)
        second = self.backend.dispatch('history', body | {'cursor': first['cursor']}, True)
        self.assertEqual([p['value'] for p in second['rows']], [3, 4, 5])
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('history', body | {'cursor': first['cursor'] | {'offset': 11}}, True)
        with self.backend.evidence.transaction() as con:
            f['actual'][0]['extra'] = 'x' * 70000
            self.backend.evidence.write(con, 'fixture', f)
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('history', body, True)

    def test_failed_startup_fails_closed_without_silent_defaults(self):
        self.backend.close()
        with self.backend.critical.connect() as con:
            con.execute('PRAGMA user_version=999')
        with self.assertRaises(StoreError):
            self.backend.open()
        self.assertFalse(self.backend.status(True)['permitted'])
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('status', {'entry_id': 'synthetic-entry', 'version': [2, 0]}, True)


class ExtendedStoreTests(unittest.TestCase):
    setUp = StoreTests.setUp
    tearDown = StoreTests.tearDown
    def test_migration_failure_keeps_old_schema_and_backup(self):
        with self.store.connect() as con:
            con.execute('PRAGMA user_version=1')
        self.store.hook = lambda _: (_ for _ in ()).throw(OSError(5, 'EIO'))
        with self.assertRaises(StoreError):
            self.store.open({})
        with self.store.connect() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 1)
        readonly = NativeStore(self.root, 'critical', readonly=True)
        with self.assertRaises(StoreError):
            readonly.open({})
        self.store.hook = None
        self.store.open({})

    def test_missing_readonly_unqualified_schema_and_corruption(self):
        from dataclasses import replace
        from packages.control_store.qualification import inspect_sqlite
        with patch('packages.ha_native.store.inspect_sqlite', return_value=replace(inspect_sqlite(), qualified=False)):
            with self.assertRaises(StoreError):
                self.store.open({})
        with self.assertRaises(StoreError):
            NativeStore(self.root, 'evidence', readonly=True).open({})
        with self.assertRaises(StoreError):
            self.store.read('missing')
        with self.assertRaises(StoreError):
            self.store.rollback_migration()
        with self.store.connect() as con:
            con.execute('PRAGMA user_version=5')
        with self.assertRaises(StoreError):
            self.store.open({})
        self.store.path.write_bytes(b'broken')
        with self.assertRaises(StoreError):
            self.store.open({})

class AdditionalFaultTests(unittest.TestCase):
    setUp = BackendTests.setUp
    tearDown = BackendTests.tearDown
    request = BackendTests.request

    def test_invalid_configuration_corrupt_settings_and_archive_restart(self):
        with self.assertRaises(NativeProtocolError):
            NativeBackend(self.root, fixture(), entry_id='foreign/path')
        bad = fixture()
        bad['settings']['budget'] = -1
        invalid = NativeBackend(self.root, bad)
        with self.assertRaises(StoreError):
            invalid.open()
        self.backend.evidence.path.write_bytes(b'broken archive')
        self.backend.reboot()
        self.assertEqual(self.backend.status(True)['diagnostics']['persistence'], 'archive_unavailable')
        self.assertEqual(self.backend.dispatch('control', self.request(kind='pause'), True)['status'], 'accepted_fake')
        with self.backend.critical.transaction() as con:
            value = self.backend.critical.read_from(con, 'settings')
            value['values']['budget'] = -1
            self.backend.critical.write(con, 'settings', value)
        with self.assertRaises(StoreError):
            self.backend.reboot()

    def test_request_capacity_validation_and_archive_fault_projection(self):
        body = self.request(request_id='negative', expected_revision=-1, values=fixture()['settings'])
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('settings/save', body, True)
        with self.backend.critical.transaction() as con:
            self.backend.critical.write(con, 'requests', {str(i): {} for i in range(4096)})
        self.assertEqual(self.backend.dispatch('control', self.request(kind='arm'), True)['status'], 'unavailable')
        with patch.object(self.backend.evidence, 'read', side_effect=StoreError('EIO')):
            with self.assertRaises(NativeProtocolError):
                self.backend.dispatch('overview', {'entry_id': 'synthetic-entry', 'version': [2, 0]}, True)
        self.assertTrue(self.backend.flush_stop())

    def test_newer_stop_during_durability_does_not_clear_pending_stop(self):
        body = self.request()
        self.backend.stop(True, body['boot_id'], body['generation'], 'first')
        self.backend.critical.hook = lambda _: self.backend.stop(True, body['boot_id'], body['generation'], 'second')
        self.assertFalse(self.backend.flush_stop())
        self.assertFalse(self.backend.status(True)['permitted'])
        self.backend.critical.hook = None
        self.assertTrue(self.backend.flush_stop())

    def test_source_loss_and_reconciliation_preserve_manual_priority(self):
        from packages.contracts import Clock
        from packages.offline.contracts import SourceEvent
        boot = self.backend.status(True)['status']['boot_id']
        now = self.backend.status(True)['now']
        self.backend.dispatch('control', self.request(kind='pause'), True)
        self.backend.invalidate_source('registry')
        self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
        missing = SourceEvent('missing', 'synthetic.native.room', 1, now, None)
        self.assertFalse(self.backend.accept_source(missing, Clock(utc=now, monotonic=0, boot_id=boot)))
        self.assertEqual(self.backend.status(True)['room']['quality'], 'missing')


class StoreBoundaryTests(unittest.TestCase):
    setUp = StoreTests.setUp
    tearDown = StoreTests.tearDown

    def test_invalid_initial_record_rolls_back_and_cannot_silently_reinitialize(self):
        new = NativeStore(self.root, 'evidence')
        with self.assertRaises(StoreError):
            new.open({'bad': float('nan')})
        with self.assertRaises(StoreError):
            new.open({'good': {}})

    def test_valid_checksum_does_not_hide_invalid_json_or_non_wal_runtime(self):
        from hashlib import sha256
        with self.store.connect() as con:
            raw = 'invalid-json'
            con.execute('UPDATE records SET payload=?, digest=?', (raw, sha256(raw.encode()).hexdigest()))
        with self.assertRaises(StoreError):
            self.store.read('state')
        with self.store.connect() as con:
            self.store.write(con, 'state', {'revision': 1})
            con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            con.execute('PRAGMA journal_mode=DELETE')
        with self.assertRaises(StoreError):
            self.store.open({})

class NativeFenceTests(unittest.TestCase):
    setUp = BackendTests.setUp
    tearDown = BackendTests.tearDown
    request = BackendTests.request

    def test_old_owner_cannot_resume_or_arm_after_new_manual_pause(self):
        stale_resume = self.request(kind='resume', request_id='old-resume')
        stale_arm = self.request(kind='arm', request_id='old-arm')
        self.backend.stop_request(self.request(kind='pause', request_id='new-pause'), True)
        self.assertTrue(self.backend.flush_stop())
        for body in (stale_resume, stale_arm):
            with self.assertRaisesRegex(NativeProtocolError, 'stale_owner'):
                self.backend.dispatch('control', body, True)
            self.assertEqual(self.backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
        fresh = self.request(kind='resume', request_id='fresh-resume')
        result = self.backend.dispatch('control', fresh, True)
        self.assertEqual(result['status'], 'accepted_fake')
        # Replaying this exact accepted request remains harmless even in RECOVERING.
        epoch = self.backend.status(True)['status']['owner_epoch']
        self.assertEqual(result, self.backend.dispatch('control', fresh, True))
        self.assertEqual(epoch, self.backend.status(True)['status']['owner_epoch'])

    def test_memory_stop_strict_payload_and_owner_fence_without_disk(self):
        body = self.request(kind='pause', request_id='strict-stop')
        invalids = (body | {'admin': True}, body | {'version': [1, 0]}, body | {'entry_id': 'foreign'},
                    body | {'boot_id': 'old'}, body | {'kind': 'resume'}, body | {'request_id': ''},
                    body | {'owner_epoch': True}, body | {'generation': 0}, body | {'extra': 'x' * 262144})
        for invalid in invalids:
            with self.assertRaises(NativeProtocolError):
                self.backend.stop_request(invalid, True)
        with patch.object(self.backend.critical, 'connect', side_effect=AssertionError('STOP touched disk')):
            denied = self.backend.stop_request(body, False)
            self.assertEqual(denied['status'], 'denied')
            accepted = self.backend.stop_request(body, True)
            self.assertEqual(accepted['status'], 'accepted_fake')
            epoch = self.backend.status(True)['status']['owner_epoch']
            self.assertEqual(accepted, self.backend.stop_request(body, True))
            self.assertEqual(epoch, self.backend.status(True)['status']['owner_epoch'])
            conflict = self.backend.stop_request(body | {'owner_epoch': epoch}, True)
            self.assertEqual(conflict['status'], 'conflict')
            with self.assertRaisesRegex(NativeProtocolError, 'stale_owner'):
                self.backend.stop_request(body | {'request_id': 'new-old-stop'}, True)
        self.assertTrue(self.backend.flush_stop())

    def test_age_option_is_authoritative_and_reconfig_drops_prior_observation(self):
        from packages.contracts import Clock, Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
        from packages.offline.contracts import SourceEvent
        for invalid in (4, 301, float('nan'), True):
            with self.assertRaises(NativeProtocolError):
                self.backend.configure_source(invalid)
        boot = self.backend.status(True)['status']['boot_id']
        now = self.backend.status(True)['now']
        self.backend.configure_source(120)
        self.assertFalse(self.backend.status(True)['permitted'])
        reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
            value=22, unit=Unit.CELSIUS, observed_at=now - 60, received_at=now - 60,
            quality=Quality(status=QualityStatus.VALID, age_s=0, reason='synthetic'),
            provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
        event = SourceEvent('age-120', 'synthetic.native.room', 1, now - 60, reading)
        self.assertTrue(self.backend.accept_source(event, Clock(utc=now, monotonic=0, boot_id=boot)))
        self.assertTrue(self.backend.flush_stop())
        self.assertTrue(self.backend.status(True)['permitted'])
        self.backend.configure_source(5)
        self.assertFalse(self.backend.accept_source(event, Clock(utc=now, monotonic=0, boot_id=boot)))
        self.assertFalse(self.backend.status(True)['permitted'])

    def test_disposable_default_fixture_loads_without_mutable_shared_data(self):
        temporary = tempfile.TemporaryDirectory(prefix='heating-wp2c-')
        self.addCleanup(temporary.cleanup)
        default = NativeBackend(Path(temporary.name), enabled=True)
        default.open()
        read = {'entry_id': 'synthetic-entry', 'version': [2, 0]}
        overview = default.dispatch('overview', read, False)
        original = overview['original']
        self.assertIsNotNone(original)
        overview['original'] = None
        self.assertEqual(default.dispatch('overview', read, False)['original'], original)
        default.close()

class ProcessRecoveryTests(unittest.TestCase):
    setUp = BackendTests.setUp
    tearDown = BackendTests.tearDown

    def child(self, crash):
        import subprocess
        import sys
        script = '''
import os, sys
from pathlib import Path
from packages.ha_native.backend import NativeBackend
backend = NativeBackend(Path(sys.argv[1]), enabled=True)
backend.open()
from packages.contracts import Clock, Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
from packages.offline.contracts import SourceEvent
state = backend.status(True)
now, boot = state['now'], state['status']['boot_id']
reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
    value=21.8, unit=Unit.CELSIUS, observed_at=now, received_at=now,
    quality=Quality(status=QualityStatus.VALID, age_s=0, reason='child-test'),
    provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
assert backend.accept_source(SourceEvent(boot + '.setup', 'synthetic.native.room', 0, now, reading),
                             Clock(utc=now, monotonic=0, boot_id=boot))
assert backend.flush_stop()
def request(**fields):
    state = backend.status(True)
    return dict(entry_id='synthetic-entry', version=[2,0], boot_id=state['status']['boot_id'],
                generation=state['generation'], owner_epoch=state['status']['owner_epoch'], **fields)
if sys.argv[2] == 'before_commit':
    backend.critical.hook = lambda point: os._exit(71)
settings = backend.critical.read('settings')
settings['values']['day'] = 22
result = backend.dispatch('settings/save', request(request_id='process-save',
    expected_revision=settings['revision'], values=settings['values']), True)
assert result['status'] == 'saved', result
result = backend.dispatch('control', request(request_id='process-arm', kind='arm'), True)
assert result['status'] == 'accepted_fake', result
os._exit(0)
'''
        return subprocess.run([sys.executable, '-B', '-c', script, str(self.root), crash],
                              capture_output=True, timeout=10)

    def test_killed_writer_leaves_no_partial_settings_or_receipt(self):
        result = self.child('before_commit')
        self.assertEqual(result.returncode, 71, result.stderr.decode())
        self.backend.reboot()
        settings = self.backend.critical.read('settings')
        self.assertEqual(settings['revision'], 1)
        self.assertEqual(settings['values']['day'], 21.5)
        self.assertEqual(self.backend.critical.read('requests'), {})
        self.assertEqual(self.backend.status(True)['status']['desired'], 'stop_demand')

    def test_uncheckpointed_commit_survives_exit_without_rearming(self):
        result = self.child('after_commit')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.backend.reboot()
        settings = self.backend.critical.read('settings')
        self.assertEqual(settings['revision'], 2)
        self.assertEqual(settings['values']['day'], 22)
        self.assertEqual(self.backend.status(True)['oneShot']['state'], 'unknown_outcome')
        self.assertEqual(self.backend.status(True)['status']['desired'], 'stop_demand')

class ShutdownFenceTests(unittest.TestCase):
    setUp = BackendTests.setUp
    tearDown = BackendTests.tearDown
    request = BackendTests.request

    def test_close_during_committing_save_cannot_revive_old_backend(self):
        import threading
        reached = threading.Event()
        release = threading.Event()
        self.backend.critical.hook = lambda _: (reached.set(), release.wait(2))
        body = self.request(request_id='unload-race', expected_revision=1, values=fixture()['settings'])
        results = []
        thread = threading.Thread(target=lambda: results.append(self.backend.dispatch('settings/save', body, True)))
        thread.start()
        self.assertTrue(reached.wait(2))
        self.backend.close()
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]['status'], 'unavailable')
        state = self.backend.status(True)
        self.assertFalse(state['connected'])
        self.assertFalse(state['permitted'])
        self.assertEqual(state['status']['desired'], 'stop_demand')
        self.assertEqual(state['status']['mode'], 'SAFE_HOLD')
        with self.assertRaises(NativeProtocolError):
            self.backend.dispatch('control', body | {'kind': 'resume'}, True)
        self.backend.critical.hook = None

    def test_open_and_reboot_require_new_synthetic_observation(self):
        self.backend.reboot()
        state = self.backend.status(True)
        self.assertFalse(state['permitted'])
        self.assertEqual(state['status']['mode'], 'SAFE_HOLD')
        self.assertEqual(state['room']['quality'], 'missing')
        self.assertIsNone(state['room']['value'])
        self.assertEqual(self.backend.dispatch('control', self.request(kind='arm'), True)['status'], 'denied')

class OriginalEvidenceProofTests(unittest.TestCase):
    def test_nonempty_original_bytes_survive_mutations_reboot_and_archive_migration_rollback(self):
        from hashlib import sha256
        from packages.ha_native.store import encode
        with tempfile.TemporaryDirectory(prefix='heating-wp2c-') as directory:
            backend = NativeBackend(Path(directory), enabled=True)
            backend.open()
            observe(backend)
            read = {'entry_id': 'synthetic-entry', 'version': [2, 0]}
            original = backend.dispatch('overview', read, True)['original']
            self.assertGreater(len(original['points']), 1)
            self.assertTrue(original['frozen'])
            self.assertLessEqual(original['issued'], original['received'])
            self.assertLessEqual(original['received'], original['reference'] - 43200)
            original_bytes = encode(original).encode()
            original_hash = sha256(original_bytes).hexdigest()
            with backend.evidence.connect() as con:
                archived_record = con.execute("SELECT payload,digest FROM records WHERE name='fixture'").fetchone()
            def assert_original_unchanged():
                current = backend.dispatch('overview', read, True)['original']
                self.assertEqual(encode(current).encode(), original_bytes)
                self.assertEqual(sha256(encode(current).encode()).hexdigest(), original_hash)
                self.assertEqual((current['issued'], current['received']), (original['issued'], original['received']))
                with backend.evidence.connect() as con:
                    self.assertEqual(con.execute("SELECT payload,digest FROM records WHERE name='fixture'").fetchone(), archived_record)
            def request(**fields):
                state = backend.status(True)
                return dict(read, boot_id=state['status']['boot_id'], generation=state['generation'],
                            owner_epoch=state['status']['owner_epoch'], **fields)
            for kind in ('train', 'promote', 'freeze', 'rollback'):
                model = backend.dispatch('model', request(kind=kind, request_id='original-' + kind), True)
                self.assertIn('model', model)
                assert_original_unchanged()
            settings = backend.dispatch('settings/get', read, True)
            receipt = backend.dispatch('settings/save', request(request_id='original-settings',
                expected_revision=settings['revision'], values=settings['values'] | {'day': 22}), True)
            self.assertEqual(receipt['status'], 'saved')
            assert_original_unchanged()
            self.assertEqual(backend.dispatch('control', request(kind='pause', request_id='original-pause'), True)['status'], 'accepted_fake')
            assert_original_unchanged()
            backend.reboot()
            self.assertEqual(backend.status(True)['status']['mode'], 'MANUAL_PAUSE')
            assert_original_unchanged()
            with backend.evidence.connect() as con:
                con.execute('PRAGMA user_version=1')
            backend.evidence.open({})
            self.assertTrue(backend.evidence.path.with_suffix('.migration.sqlite3').is_file())
            assert_original_unchanged()
            backend.evidence.rollback_migration()
            with backend.evidence.connect() as con:
                self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 1)
            assert_original_unchanged()
            backend.evidence.open({})
            assert_original_unchanged()
            backend.close()
