"""Four isolated durable-journal tests; no HA import, services or owner grant."""
from pathlib import Path
import runpy
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

MODULE = runpy.run_path('releases/ha_v2/custom_components/heating_ai_v2/critical_ledger.py')
CriticalLedger = MODULE['CriticalLedger']
LedgerError, LedgerConflict = MODULE['LedgerError'], MODULE['LedgerConflict']


class CriticalLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = dict(owner_id='synthetic.owner', boot_id='synthetic.boot', owner_epoch=1)
        self.ledger = CriticalLedger(self.root, **self.identity)

    def args(self):
        return dict(self.identity, expected_revision=self.ledger.status()['revision'])

    def prepare(self, name='synthetic.heat', action='HEAT'):
        return self.ledger.prepare(name, action, {'target_c': 22.5}, at=100, **self.args())

    def test_durable_prepare_and_sent_restart_are_unknown_and_fenced(self):
        for stage in ('PREPARED', 'SENT'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                ledger = CriticalLedger(directory, **self.identity)
                ledger.prepare('synthetic.intent', 'HEAT', {'target_c': 22.5}, at=100,
                               expected_revision=0, **self.identity)
                if stage == 'SENT':
                    ledger.record_sent('synthetic.intent', at=101, expected_revision=1, **self.identity)
                restarted = CriticalLedger(directory, **self.identity)
                status = restarted.status()
                self.assertEqual(status['commands']['synthetic.intent']['stage'], 'UNKNOWN')
                self.assertTrue(status['fenced'])
                self.assertEqual(status['owner_epoch'], 2)
                current = dict(owner_id='synthetic.owner', boot_id='synthetic.boot', owner_epoch=2,
                               expected_revision=status['revision'])
                with self.assertRaises(LedgerConflict):
                    restarted.prepare('synthetic.retry', 'HEAT', {}, **current)
                restarted.reconcile_restart('synthetic.new-boot', **current)
                self.assertEqual(restarted.status()['boot_id'], 'synthetic.new-boot')
                self.assertTrue(restarted.status()['fenced'])
                with sqlite3.connect(restarted.path) as con:
                    self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
                    self.assertEqual(con.execute('PRAGMA synchronous').fetchone()[0], 2)

    def test_idempotent_prepare_immutable_request_owner_epoch_and_cas(self):
        peer = CriticalLedger(self.root, **self.identity)
        request = {'target_c': 22.5}
        first = self.ledger.prepare('synthetic.heat', 'HEAT', request, at=100, **self.args())
        request['target_c'] = 30
        duplicate = self.prepare()
        self.assertTrue(first['created'])
        self.assertFalse(duplicate['created'])
        self.assertEqual(duplicate['command'], first['command'])
        self.assertEqual(duplicate['revision'], first['revision'])
        with self.assertRaises(LedgerConflict):
            self.ledger.prepare('synthetic.heat', 'HEAT', request, at=100, **self.args())
        for changed in ({'owner_id': 'synthetic.foreign'}, {'boot_id': 'synthetic.old'}, {'owner_epoch': 0}):
            with self.subTest(changed=changed), self.assertRaises(LedgerConflict):
                self.ledger.prepare('synthetic.other', 'HEAT', {}, **(self.args() | changed))
        with self.assertRaises(LedgerConflict):
            peer.prepare('synthetic.race', 'HEAT', {}, expected_revision=0, **self.identity)
        with self.assertRaises(LedgerError):
            self.ledger.prepare('synthetic.large', 'HEAT', {'value': 'x' * 4097}, **self.args())
        self.ledger.record_sent('synthetic.heat', at=101, **self.args())
        self.ledger.record_ha_echo('synthetic.heat', at=102, **self.args())
        with patch.dict(CriticalLedger.prepare.__globals__, MAX_RECORDS=1):
            with self.assertRaises(LedgerError):
                self.prepare('synthetic.full')
        with self.assertRaises(LedgerError):
            self.ledger.status()  # A full store fails closed; never evicts or resets.

    def test_stop_corruption_schema_symlink_and_storage_failure_fail_closed(self):
        self.prepare()
        self.prepare('synthetic.stop', 'STOP')
        status = self.ledger.status()
        self.assertTrue(status['fenced'])
        self.assertEqual(status['commands']['synthetic.heat']['stage'], 'UNKNOWN')
        with self.assertRaises(LedgerConflict):
            self.prepare('synthetic.resume')
        with self.assertRaises(LedgerConflict):
            self.ledger.record_sent('synthetic.heat', at=101, **self.args())
        self.ledger.fence(**self.args())
        self.assertEqual(self.ledger.status()['owner_epoch'], 2)
        with sqlite3.connect(self.ledger.path) as con:
            con.execute("UPDATE journal SET checksum='corrupt'")
        with self.assertRaises(LedgerError):
            self.ledger.status()
        with self.assertRaises(LedgerError):
            self.prepare('synthetic.retry')
        for fault in ('schema', 'symlink', 'locked'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                ledger = CriticalLedger(directory, **self.identity)
                if fault == 'symlink':
                    target = Path(directory) / 'other.sqlite3'
                    ledger.path.rename(target)
                    ledger.path.symlink_to(target)
                    with self.assertRaises(LedgerError):
                        CriticalLedger(directory, **self.identity)
                else:
                    with sqlite3.connect(ledger.path, isolation_level=None) as con:
                        con.execute('PRAGMA user_version=99' if fault == 'schema' else 'BEGIN IMMEDIATE')
                        try:
                            with self.assertRaises(LedgerError):
                                ledger.status()
                        finally:
                            con.rollback()
                    with self.assertRaises(LedgerError):
                        ledger.status()

    def test_projection_is_never_physical_ack_or_authority(self):
        self.prepare()
        for expected in ('PREPARED', 'SENT', 'HA_ECHO'):
            status = self.ledger.status()
            self.assertEqual(status['commands']['synthetic.heat']['stage'], expected)
            for flag in ('physical_ack', 'physical_authority', 'physical_commands_enabled'):
                self.assertIs(status[flag], False)
            self.assertIsNone(status['contacts_open'])
            if expected == 'PREPARED':
                self.ledger.record_sent('synthetic.heat', at=101, **self.args())
            elif expected == 'SENT':
                self.ledger.record_ha_echo('synthetic.heat', at=102, **self.args())
        self.assertFalse(self.ledger.physical_commands_enabled)
        status['commands']['synthetic.heat']['request']['target_c'] = 35
        self.assertEqual(self.ledger.status()['commands']['synthetic.heat']['request']['target_c'], 22.5)
        with self.assertRaises(LedgerConflict):
            self.ledger.record_sent('synthetic.heat', at=103, **self.args())
        source = Path('releases/ha_v2/custom_components/heating_ai_v2/__init__.py').read_text()
        self.assertNotIn('critical_ledger', source)


if __name__ == '__main__':
    unittest.main()
