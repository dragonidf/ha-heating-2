import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from packages.contracts import Action, CommandReceipt, EventKind, OneShot, OneShotKind, OneShotOutcome, ReceiptStage, to_json
from packages.control import reduce
from packages.control_store.store import ControlStore, StoreConflict, StoreFailure
from tests.fixtures.synthetic import clock, event, policy, snapshot, state


class StoreFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ControlStore.create(self.root, state(), policy())

    def sql(self, statement, parameters=()):
        with sqlite3.connect(self.store.path) as con:
            return con.execute(statement, parameters).fetchall()

    def heating(self):
        before = self.store.view()
        d = reduce(before.state, event(), snapshot(), policy(), clock())
        view = self.store.transition(event(), d, before.revision)
        return view, d.intents[0]

    def test_no_recreation_and_readonly_never_applies_settings(self):
        before = self.store.view()
        with self.assertRaises(StoreFailure):
            ControlStore.create(self.root, state(), policy())
        readonly = ControlStore(self.root, readonly=True)
        with self.assertRaises(StoreFailure):
            readonly.configure(policy(config_revision=2), 0, before.state)
        self.assertEqual(self.store.view(), before)

    def test_settings_cas_rejects_stale_revision_and_fence(self):
        before = self.store.view()
        updated = self.store.configure(policy(config_revision=2, armed=False), 0, before.state)
        self.assertFalse(updated.policy.armed)
        for revision, fence in ((0, before.state), (updated.revision, replace(before.state, owner_epoch=4))):
            with self.assertRaises(StoreConflict):
                self.store.configure(policy(config_revision=3), revision, fence)
        restarted = self.store.restart("synthetic.disarmed-reboot")
        self.assertFalse(restarted.policy.armed)
        with self.assertRaises(StoreConflict):
            self.store.restart("synthetic.disarmed-reboot")

    def test_transition_is_idempotent_but_identity_cannot_be_rewritten(self):
        d = reduce(state(), event(), snapshot(), policy(), clock())
        first = self.store.transition(event(), d, 0)
        self.assertEqual(self.store.transition(event(), d, 0), first)
        with self.assertRaises(StoreConflict):
            self.store.transition(replace(event(), authorized=True), d, first.revision)
        with self.assertRaises(StoreConflict):
            self.store.transition(event(), replace(d, state=replace(d.state, plan=None)), first.revision)
        stored_event = self.sql("SELECT event FROM events")[0][0]
        self.assertEqual(json.loads(stored_event)["type"], "ControlEvent")

    def test_owner_or_off_latch_cannot_be_forged_by_an_ordinary_event(self):
        current = self.store.view()
        e = event()
        d = reduce(current.state, e, snapshot(), policy(), clock())
        for bad in (replace(d.state, boot_id="synthetic.other"), replace(d.state, owner_epoch=6),
                    replace(d.state, owner_epoch=7)):
            with self.subTest(state=bad), self.assertRaises(StoreConflict):
                self.store.transition(e, replace(d, state=bad), current.revision)
        off = event(kind=EventKind.OFF)
        off_decision = reduce(current.state, off, snapshot(), policy(), clock())
        saved = self.store.transition(off, off_decision, current.revision)
        forged = replace(off_decision, state=replace(saved.state, off_latched=False))
        with self.assertRaises(StoreConflict):
            self.store.transition(event(owner_epoch=6, sequence=2), forged, saved.revision)

    def test_manual_pause_never_clears_by_missing_or_ordinary_state(self):
        e = event(kind=EventKind.MANUAL_CHANGE)
        d = reduce(state(), e, snapshot(), policy(), clock())
        saved = self.store.transition(e, d, 0)
        forged = replace(d, state=replace(d.state, manual_paused=False))
        with self.assertRaises(StoreConflict):
            self.store.transition(event(owner_epoch=6, sequence=2), forged, saved.revision)
        with self.assertRaises(StoreConflict):
            self.store.transition(event(owner_epoch=4, sequence=2), d, saved.revision)

    def test_prepare_rejects_stale_revision_missing_intent_grid_and_expiry(self):
        view, intent = self.heating()
        cases = ((intent, snapshot(), clock(), 0),
                 (replace(intent, action=Action.STOP), snapshot(), clock(), view.revision),
                 (intent, snapshot(grid_actual=None), clock(), view.revision),
                 (intent, snapshot(), clock(utc=106), view.revision))
        for command, snap, now, revision in cases:
            with self.subTest(command=command), self.assertRaises(StoreConflict):
                self.store.prepare(command, snap, now, revision)
        self.assertEqual(self.sql("SELECT count(*) FROM outbox")[0][0], 0)
        self.store.prepare(intent, snapshot(), clock(), view.revision)
        with self.assertRaises(StoreConflict):
            self.store.prepare(intent, snapshot(), clock(), view.revision)

    def test_claim_rechecks_persisted_permission_and_owner(self):
        view, intent = self.heating()
        self.store.prepare(intent, snapshot(), clock(), view.revision)
        changed = self.store.configure(policy(config_revision=2, armed=False), view.revision, view.state)
        with self.assertRaises(StoreConflict):
            self.store.claim(intent, changed.state, snapshot(), clock())
        e = event(kind=EventKind.MANUAL_CHANGE, sequence=2)
        d = reduce(changed.state, e, snapshot(), changed.policy, clock())
        manual = self.store.transition(e, d, changed.revision)
        with self.assertRaises(StoreConflict):
            self.store.claim(intent, manual.state, snapshot(owner_epoch=6), clock())

    def test_receipt_stages_idempotence_identity_and_immutable_known_facts(self):
        view, intent = self.heating()
        self.store.prepare(intent, snapshot(), clock(), view.revision)
        prepared = self.store.receipt(intent.intent_id)
        with self.assertRaises(StoreConflict):
            self.store.record_receipt(replace(prepared, stage=ReceiptStage.SENT, sent_at=100), view.state)
        self.store.claim(intent, view.state, snapshot(), clock())
        sent = replace(prepared, stage=ReceiptStage.SENT, sent_at=100)
        self.assertTrue(self.store.record_receipt(sent, view.state))
        self.assertFalse(self.store.record_receipt(sent, view.state))
        for change in (dict(owner_epoch=4), dict(sequence=4), dict(sent_at=101), dict(requested_at=99)):
            with self.subTest(change=change), self.assertRaises(StoreConflict):
                self.store.record_receipt(replace(sent, **change), view.state)
        echoed = replace(sent, stage=ReceiptStage.ECHOED, device_echo_at=100)
        self.store.record_receipt(echoed, view.state)
        self.assertFalse(self.store.record_receipt(sent, view.state))
        self.store.restart("synthetic.receipt-reboot")
        new = self.store.view()
        with self.assertRaises(StoreConflict):
            self.store.record_receipt(replace(echoed, boot_id=new.state.boot_id,
                                              owner_epoch=new.state.owner_epoch), new.state)

    def test_locked_database_and_failed_sync_never_commit_prepare(self):
        view, intent = self.heating()
        with sqlite3.connect(self.store.path, isolation_level=None) as locked:
            locked.execute("BEGIN IMMEDIATE")
            with self.assertRaises(StoreFailure):
                self.store.prepare(intent, snapshot(), clock(), view.revision)
            locked.rollback()
        def sync_failure(point):
            if point == "before_commit":
                raise OSError(5, "synthetic sync failure")
        self.store.hook = sync_failure
        with self.assertRaises(StoreFailure):
            self.store.prepare(intent, snapshot(), clock(), view.revision)
        self.store.hook = None
        self.assertEqual(self.sql("SELECT count(*) FROM outbox")[0][0], 0)

    def test_actual_sqlite_full_rolls_back_without_resetting_control(self):
        before = self.store.view()
        with sqlite3.connect(self.store.path) as con:
            pages = con.execute("PRAGMA page_count").fetchone()[0]
            con.execute(f"PRAGMA max_page_count={pages}")
            with self.assertRaises(sqlite3.OperationalError) as error:
                con.execute("INSERT INTO events(event_id,payload,checksum,event,event_hash) VALUES (?,?,?,?,?)",
                            ("synthetic.full", "x" * 100_000, "x", "x", "x"))
            self.assertEqual(error.exception.sqlite_errorcode, sqlite3.SQLITE_FULL)
        self.assertEqual(self.store.view(), before)

    def test_corrupt_checksum_semantic_payload_protocol_and_future_schema_rejected(self):
        for mutation in ("UPDATE control SET state_hash='invalid'",
                         "UPDATE metadata SET checksum='invalid'", "PRAGMA user_version=99"):
            with self.subTest(mutation=mutation):
                tmp = tempfile.TemporaryDirectory(prefix="heating-wp1b-")
                self.addCleanup(tmp.cleanup)
                root = Path(tmp.name)
                other = ControlStore.create(root, state(), policy())
                with sqlite3.connect(other.path) as con:
                    con.execute(mutation)
                before = other.path.read_bytes()
                with self.assertRaises(StoreFailure):
                    ControlStore(root)
                self.assertEqual(other.path.read_bytes(), before)
        payload = json.loads(self.sql("SELECT policy FROM control")[0][0])
        payload["schema_version"]["major"] = 99
        corrupt = json.dumps(payload)
        self.sql("UPDATE control SET policy=?,policy_hash=?", (corrupt, hashlib.sha256(corrupt.encode()).hexdigest()))
        with self.assertRaises(StoreFailure):
            self.store.view()

    def test_truncated_database_and_missing_control_are_not_defaulted(self):
        self.sql("DELETE FROM control")
        with self.assertRaises(StoreFailure):
            self.store.view()
        self.store.path.write_bytes(b"synthetic truncated SQLite")
        with self.assertRaises(StoreFailure):
            ControlStore(self.root)

    def test_migration_is_atomic_and_preserves_manual_pause(self):
        self.sql("DROP TABLE outbox")
        self.sql("DROP TABLE oneshots")
        self.sql("PRAGMA user_version=1")
        before = self.store.view()
        def fail(point):
            if point == "migration_before_commit":
                raise OSError(5, "synthetic migration sync failure")
        with self.assertRaises(StoreFailure):
            ControlStore(self.root, hook=fail)
        self.assertEqual(self.sql("PRAGMA user_version")[0][0], 1)
        migrated = ControlStore(self.root)
        self.assertEqual(migrated.view(), before)
        self.assertEqual(migrated.pragmas(), ("wal", 2))
        self.assertEqual(migrated.checkpoint()[0], 0)

    def test_missing_expired_wrong_grid_and_consumed_markers_cannot_prepare(self):
        view, intent = self.heating()
        base = OneShot(intent_id="synthetic.once-failure", kind=OneShotKind.HEAT_AFTER_GRID_RESTORE,
                       created_at=90, expires_at=200, armed_grid_epoch=4, consumed_at=None,
                       outcome=OneShotOutcome.PENDING)
        for index, bad in enumerate((replace(base, expires_at=99), replace(base, armed_grid_epoch=5),
                                     replace(base, outcome=OneShotOutcome.CONSUMED, consumed_at=95))):
            bad = replace(bad, intent_id=f"synthetic.bad-marker-{index}")
            p = to_json(bad)
            self.sql("INSERT INTO oneshots VALUES (?,?,?)", (bad.intent_id, p, hashlib.sha256(p.encode()).hexdigest()))
            with self.assertRaises(StoreConflict):
                self.store.prepare(intent, snapshot(), clock(), view.revision, one_shot_id=bad.intent_id)
        self.assertEqual(self.sql("SELECT count(*) FROM outbox")[0][0], 0)

    def test_outbox_and_one_shot_index_corruption_are_not_trusted(self):
        view, intent = self.heating()
        self.store.prepare(intent, snapshot(), clock(), view.revision)
        self.sql("UPDATE outbox SET owner=0")
        with self.assertRaises(StoreFailure):
            self.store.receipt(intent.intent_id)
        with self.assertRaises(StoreFailure):
            ControlStore(self.root)
        shot = OneShot(intent_id="synthetic.original", kind=OneShotKind.HEAT_AFTER_GRID_RESTORE,
                       created_at=90, expires_at=200, armed_grid_epoch=4, consumed_at=None,
                       outcome=OneShotOutcome.PENDING)
        self.store.register_one_shot(shot)
        self.sql("UPDATE oneshots SET id='synthetic.wrong-index'")
        with self.assertRaises(StoreFailure):
            self.store.one_shot("synthetic.wrong-index")

    def test_linked_database_and_incompatible_empty_schema_are_rejected(self):
        original = self.root / "original.sqlite3"
        self.store.path.rename(original)
        self.store.path.symlink_to(original)
        with self.assertRaises(StoreFailure):
            ControlStore(self.root)
        self.store.path.unlink()
        self.store.path.write_bytes(b"")
        with self.assertRaises(StoreFailure):
            ControlStore(self.root)

    def test_boolean_negative_and_overflow_cas_are_not_integer_revisions(self):
        d = reduce(state(), event(), snapshot(), policy(), clock())
        for revision in (False, -1, 2**63):
            with self.subTest(revision=revision), self.assertRaises(StoreConflict):
                self.store.transition(event(), d, revision)
        self.assertEqual(self.store.view().revision, 0)

    def test_actual_process_write_lock_blocks_prepare_without_partial_commit(self):
        view, intent = self.heating()
        code = ("import sqlite3,sys,pathlib; c=sqlite3.connect(sys.argv[1],isolation_level=None);"
                "c.execute('BEGIN IMMEDIATE'); pathlib.Path(sys.argv[2]).write_text('ready'); sys.stdin.read(1)")
        marker = self.root / "process-lock.ready"
        child = subprocess.Popen([sys.executable, "-c", code, str(self.store.path), str(marker)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            end = time.monotonic()+2
            while not marker.exists() and child.poll() is None and time.monotonic() < end:
                time.sleep(0.005)
            self.assertTrue(marker.exists())
            with self.assertRaises(StoreFailure):
                self.store.prepare(intent, snapshot(), clock(), view.revision)
            self.assertEqual(self.sql("SELECT count(*) FROM outbox")[0][0], 0)
        finally:
            child.terminate()
            child.communicate(timeout=5)
        self.store.prepare(intent, snapshot(), clock(), view.revision)
