"""Transactional, disposable OFFLINE control store. Never accepts an HA DB path."""
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Callable, Iterator, Literal, TypeVar

from packages.contracts import (
    Action, Clock, CommandIntent, CommandReceipt, ControlEvent, ControlPolicy, ControlSnapshot,
    ControlState, Decision, EventKind, OneShot, OneShotOutcome, ReceiptStage, RuntimeMode,
    from_json, to_json,
)
from packages.control import assess_intent, evaluate
from .qualification import inspect_sqlite


class StoreFailure(RuntimeError):
    """Sanitized failure; never a signal to re-arm or dispatch."""


class StoreConflict(StoreFailure):
    """CAS, owner fence or immutable identity conflict."""


@dataclass(frozen=True, slots=True)
class StoreView:
    revision: int
    state: ControlState
    policy: ControlPolicy


T = TypeVar("T")
PROTOCOL = "heating-offline-control/1;contracts/1.0"
MAX_EVENTS = 4096
MAX_OUTBOX = 256
MAX_ONE_SHOTS = 256


def _hash(payload: str) -> str:
    return sha256(payload.encode()).hexdigest()


def _decode(payload: object, checksum: object, kind: type[T]) -> T:
    if type(payload) is not str or type(checksum) is not str or _hash(payload) != checksum:
        raise StoreFailure("Record checksum mismatch")
    try:
        return from_json(payload, kind)
    except ValueError:
        raise StoreFailure("Invalid versioned record") from None


def _fence(current: ControlState, expected: ControlState) -> None:
    if (current.boot_id, current.owner_epoch) != (expected.boot_id, expected.owner_epoch):
        raise StoreConflict("Stale boot/owner fence")


def _revision(value: int) -> None:
    if type(value) is not int or not 0 <= value < 2**63:
        raise StoreConflict("Invalid transaction revision")


class ControlStore:
    def __init__(self, root: Path, *, readonly: bool = False,
                 hook: Callable[[str], None] | None = None):
        temp_root = Path(tempfile.gettempdir()).resolve()
        if (not root.is_dir() or root.is_symlink() or root.resolve().parent != temp_root
                or not root.name.startswith("heating-wp1b-")):
            raise StoreFailure("Disposable sandbox directory required")
        self.root = root.resolve()
        self.path = self.root / "control.sqlite3"
        self.readonly = readonly
        self.hook = hook
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.path) + suffix)
            if p.is_symlink() or p.exists() and p.stat().st_nlink != 1:
                raise StoreFailure("Linked database files forbidden")
        self.info = inspect_sqlite()
        if not self.info.qualified:
            raise StoreFailure("BLOCKED: linked SQLite WAL-reset qualification")
        if not self.path.is_file():
            raise StoreFailure("Missing control store; no implicit defaults")
        with self._connection() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (1, 2):
                raise StoreFailure("Incompatible store schema")
            meta = con.execute("SELECT protocol,checksum FROM metadata").fetchall()
            if meta != [(PROTOCOL, _hash(PROTOCOL))]:
                raise StoreFailure("Incompatible store protocol")
            if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise StoreFailure("Corrupt control store")
            self._view(con)
            if version == 1:
                con.execute("BEGIN IMMEDIATE")
                self._create_outbox(con)
                self._point("migration_before_commit")
                con.execute("PRAGMA user_version=2")
                con.commit()
            self._validate_records(con)
        if self.pragmas() != ("wal", 2):
            raise StoreFailure("WAL/FULL readback failed")

    @classmethod
    def create(cls, root: Path, state: ControlState, policy: ControlPolicy) -> "ControlStore":
        # Exclusive creation only inside an existing disposable directory.
        if (not root.is_dir() or root.is_symlink() or root.resolve().parent != Path(tempfile.gettempdir()).resolve()
                or not root.name.startswith("heating-wp1b-") or not inspect_sqlite().qualified):
            raise StoreFailure("Unqualified sandbox/runtime")
        path = root / "control.sqlite3"
        try:
            with path.open("xb"):
                pass
            con = sqlite3.connect(path, isolation_level=None)
            try:
                if con.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                    raise StoreFailure("WAL unavailable")
                con.execute("PRAGMA synchronous=FULL")
                con.execute("BEGIN IMMEDIATE")
                con.execute("CREATE TABLE metadata(protocol TEXT NOT NULL, checksum TEXT NOT NULL)")
                con.execute("INSERT INTO metadata VALUES (?,?)", (PROTOCOL, _hash(PROTOCOL)))
                con.execute("CREATE TABLE control(singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
                            "revision INTEGER NOT NULL,state TEXT NOT NULL,state_hash TEXT NOT NULL,"
                            "policy TEXT NOT NULL,policy_hash TEXT NOT NULL)")
                s, p = to_json(state), to_json(policy)
                con.execute("INSERT INTO control VALUES (1,0,?,?,?,?)", (s, _hash(s), p, _hash(p)))
                con.execute("CREATE TABLE events(tx INTEGER PRIMARY KEY,event_id TEXT UNIQUE NOT NULL,"
                            "payload TEXT NOT NULL,checksum TEXT NOT NULL,event TEXT NOT NULL,event_hash TEXT NOT NULL)")
                con.execute("CREATE TABLE boots(id TEXT PRIMARY KEY)")
                con.execute("INSERT INTO boots VALUES (?)", (state.boot_id,))
                cls._create_outbox(con)
                con.execute("PRAGMA user_version=2")
                con.commit()
            finally:
                con.close()
        except (OSError, sqlite3.Error):
            raise StoreFailure("Control store creation failed") from None
        return cls(root)

    @staticmethod
    def _create_outbox(con: sqlite3.Connection) -> None:
        con.execute("CREATE TABLE outbox(id TEXT PRIMARY KEY,intent TEXT NOT NULL,intent_hash TEXT NOT NULL,"
                    "receipt TEXT NOT NULL,receipt_hash TEXT NOT NULL,boot TEXT NOT NULL,owner INTEGER NOT NULL,"
                    "sequence INTEGER NOT NULL,UNIQUE(boot,owner,sequence))")
        con.execute("CREATE TABLE oneshots(id TEXT PRIMARY KEY,payload TEXT NOT NULL,checksum TEXT NOT NULL)")

    def _point(self, point: str) -> None:
        if self.hook is not None:
            self.hook(point)

    @classmethod
    def _validate_records(cls, con: sqlite3.Connection) -> None:
        for table, maximum in (("events", MAX_EVENTS), ("outbox", MAX_OUTBOX), ("oneshots", MAX_ONE_SHOTS)):
            if con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > maximum:
                raise StoreFailure("Critical store capacity exceeded")
        for payload, checksum, event, event_hash in con.execute("SELECT payload,checksum,event,event_hash FROM events"):
            _decode(payload, checksum, Decision)
            _decode(event, event_hash, ControlEvent)
        for (identity,) in con.execute("SELECT id FROM outbox"):
            cls._receipt(con, identity)
        for identity, payload, checksum in con.execute("SELECT id,payload,checksum FROM oneshots"):
            if _decode(payload, checksum, OneShot).intent_id != identity:
                raise StoreFailure("One-shot identity mismatch")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        con = None
        try:
            con = sqlite3.connect(self.path.as_uri() + ("?mode=ro" if self.readonly else "?mode=rw"),
                                  uri=True, timeout=0.025, isolation_level=None)
            con.execute("PRAGMA synchronous=FULL")
            con.execute("PRAGMA trusted_schema=OFF")
            yield con
        except (sqlite3.Error, OSError):
            raise StoreFailure("SQLite operation failed") from None
        finally:
            if con is not None:
                con.close()

    @contextmanager
    def _write(self, *, point: str = "before_commit", started: float | None = None) -> Iterator[sqlite3.Connection]:
        with self._connection() as con:
            con.execute("BEGIN IMMEDIATE")
            if started is not None:
                con.set_progress_handler(lambda: int(monotonic() - started > 0.250), 100)
            try:
                yield con
                self._point(point)
                if started is not None and monotonic() - started > 0.250:
                    raise StoreFailure("Prepare deadline exceeded")
                con.commit()
            except BaseException:
                con.rollback()
                raise

    @staticmethod
    def _view(con: sqlite3.Connection) -> StoreView:
        row = con.execute("SELECT revision,state,state_hash,policy,policy_hash FROM control WHERE singleton=1").fetchone()
        if row is None or type(row[0]) is not int or row[0] < 0:
            raise StoreFailure("Missing/invalid control state")
        return StoreView(row[0], _decode(row[1], row[2], ControlState), _decode(row[3], row[4], ControlPolicy))

    def view(self) -> StoreView:
        with self._connection() as con:
            return self._view(con)

    def pragmas(self) -> tuple[str, int]:
        with self._connection() as con:
            return str(con.execute("PRAGMA journal_mode").fetchone()[0]), int(con.execute("PRAGMA synchronous").fetchone()[0])

    @staticmethod
    def _save(con: sqlite3.Connection, view: StoreView) -> None:
        _revision(view.revision)
        s, p = to_json(view.state), to_json(view.policy)
        con.execute("UPDATE control SET revision=?,state=?,state_hash=?,policy=?,policy_hash=? WHERE singleton=1",
                    (view.revision, s, _hash(s), p, _hash(p)))

    def transition(self, event: ControlEvent, decision: Decision, expected_revision: int) -> StoreView:
        _revision(expected_revision)
        payload = to_json(decision)
        event_id = f"{event.boot_id}:{event.owner_epoch}:{event.kind.value}:{event.sequence}"
        with self._write(point="owner_before_commit" if decision.state.owner_epoch != event.owner_epoch else "before_commit") as con:
            current = self._view(con)
            existing = con.execute("SELECT payload,checksum,event,event_hash FROM events WHERE event_id=?", (event_id,)).fetchone()
            if existing is not None:
                if (_decode(existing[0], existing[1], Decision) != decision
                        or _decode(existing[2], existing[3], ControlEvent) != event):
                    raise StoreConflict("Event identity conflict")
                return current
            if current.revision != expected_revision:
                raise StoreConflict("State CAS conflict")
            if con.execute("SELECT count(*) FROM events").fetchone()[0] >= MAX_EVENTS:
                raise StoreFailure("Critical event capacity exhausted")
            if (event.boot_id, event.owner_epoch) != (current.state.boot_id, current.state.owner_epoch):
                raise StoreConflict("Stale event fence")
            if decision.state.boot_id != current.state.boot_id or decision.state.owner_epoch not in (
                    current.state.owner_epoch, current.state.owner_epoch + 1):
                raise StoreConflict("Invalid ownership transition")
            if decision.state.owner_epoch != current.state.owner_epoch and not (
                    event.kind in (EventKind.MANUAL_CHANGE, EventKind.UNKNOWN_CHANGE, EventKind.OFF)
                    or event.kind is EventKind.RESUME and event.authorized):
                raise StoreConflict("Ordinary events cannot acquire ownership")
            if decision.state.owner_epoch == current.state.owner_epoch and (
                    decision.state.last_event_sequence < current.state.last_event_sequence
                    or decision.state.last_safety_stop_sequence < current.state.last_safety_stop_sequence):
                raise StoreConflict("Replay frontiers cannot move backwards")
            if ((current.state.manual_paused and not decision.state.manual_paused
                 or current.state.off_latched and not decision.state.off_latched) and not (
                    event.kind is EventKind.RESUME and event.authorized
                    and decision.state.owner_epoch == current.state.owner_epoch + 1)):
                raise StoreConflict("Manual pause requires explicit new authority")
            updated = StoreView(current.revision + 1, decision.state, current.policy)
            self._save(con, updated)
            e = to_json(event)
            con.execute("INSERT INTO events(event_id,payload,checksum,event,event_hash) VALUES (?,?,?,?,?)",
                        (event_id, payload, _hash(payload), e, _hash(e)))
        return updated

    def configure(self, policy: ControlPolicy, expected_revision: int, fence: ControlState) -> StoreView:
        _revision(expected_revision)
        with self._write() as con:
            current = self._view(con)
            _fence(current.state, fence)
            if expected_revision != current.revision or policy.config_revision != current.policy.config_revision + 1:
                raise StoreConflict("Configuration CAS conflict")
            stopped = replace(current.state, plan=None, accepted_input_hash=None, desired_action=Action.STOP)
            updated = StoreView(current.revision + 1, stopped, policy)
            self._save(con, updated)
        return updated

    def register_one_shot(self, shot: OneShot) -> None:
        if shot.outcome is not OneShotOutcome.PENDING:
            raise StoreConflict("Only a new pending marker may be registered")
        payload = to_json(shot)
        with self._write() as con:
            old = con.execute("SELECT payload,checksum FROM oneshots WHERE id=?", (shot.intent_id,)).fetchone()
            if old is not None:
                if _decode(old[0], old[1], OneShot) != shot:
                    raise StoreConflict("One-shot identity already consumed/conflicting")
                return
            if con.execute("SELECT count(*) FROM oneshots").fetchone()[0] >= MAX_ONE_SHOTS:
                raise StoreFailure("Critical one-shot capacity exhausted")
            con.execute("INSERT INTO oneshots VALUES (?,?,?)", (shot.intent_id, payload, _hash(payload)))

    def one_shot(self, identity: str) -> OneShot:
        with self._connection() as con:
            row = con.execute("SELECT payload,checksum FROM oneshots WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise StoreFailure("Missing one-shot")
            shot = _decode(row[0], row[1], OneShot)
            if shot.intent_id != identity:
                raise StoreFailure("One-shot identity mismatch")
            return shot

    def prepare(self, intent: CommandIntent, snapshot: ControlSnapshot, clock: Clock,
                expected_revision: int, *, one_shot_id: str | None = None) -> None:
        _revision(expected_revision)
        if one_shot_id is not None and type(one_shot_id) is not str:
            raise StoreConflict("Invalid one-shot identity")
        started = monotonic()
        self._point("before_prepare")
        with self._write(started=started) as con:
            current = self._view(con)
            if current.revision != expected_revision or current.state.last_intent != intent:
                raise StoreConflict("Prepare revision/intent mismatch")
            if con.execute("SELECT count(*) FROM outbox").fetchone()[0] >= MAX_OUTBOX:
                raise StoreFailure("Critical outbox capacity exhausted")
            if (intent.action is not Action.HEAT or not evaluate(current.state, snapshot, current.policy, clock).allowed
                    or assess_intent(intent, clock, current.state.owner_epoch, -1, snapshot.snapshot_id).value != "allowed"):
                raise StoreConflict("HEAT prepare denied")
            receipt = CommandReceipt(intent_id=intent.intent_id, boot_id=intent.boot_id, owner_epoch=intent.owner_epoch,
                                     sequence=intent.sequence, action=intent.action, stage=ReceiptStage.PREPARED,
                                     requested_at=intent.not_before, prepared_at=clock.utc)
            p, r = to_json(intent), to_json(receipt)
            try:
                con.execute("INSERT INTO outbox VALUES (?,?,?,?,?,?,?,?)",
                            (intent.intent_id, p, _hash(p), r, _hash(r), intent.boot_id, intent.owner_epoch, intent.sequence))
            except sqlite3.IntegrityError:
                raise StoreConflict("Intent already prepared") from None
            if one_shot_id is not None:
                row = con.execute("SELECT payload,checksum FROM oneshots WHERE id=?", (one_shot_id,)).fetchone()
                if row is None:
                    raise StoreConflict("Unregistered one-shot")
                shot = _decode(row[0], row[1], OneShot)
                if (shot.outcome is not OneShotOutcome.PENDING or not shot.created_at <= clock.utc < shot.expires_at
                        or shot.armed_grid_epoch != snapshot.grid_epoch):
                    raise StoreConflict("One-shot unavailable")
                consumed = to_json(replace(shot, consumed_at=clock.utc, outcome=OneShotOutcome.CONSUMED))
                con.execute("UPDATE oneshots SET payload=?,checksum=? WHERE id=?", (consumed, _hash(consumed), one_shot_id))
        self._point("after_prepare")
        if monotonic() - started > 0.250:
            raise StoreFailure("Prepare deadline exceeded; committed outcome may exist")

    @staticmethod
    def _receipt(con: sqlite3.Connection, identity: str) -> tuple[CommandIntent, CommandReceipt]:
        row = con.execute("SELECT intent,intent_hash,receipt,receipt_hash,boot,owner,sequence FROM outbox WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise StoreFailure("Missing prepared intent")
        intent, receipt = _decode(row[0], row[1], CommandIntent), _decode(row[2], row[3], CommandReceipt)
        if (intent.intent_id != identity or (intent.boot_id, intent.owner_epoch, intent.sequence) != row[4:]
                or (receipt.intent_id, receipt.boot_id, receipt.owner_epoch, receipt.sequence, receipt.action)
                != (identity, intent.boot_id, intent.owner_epoch, intent.sequence, intent.action)):
            raise StoreFailure("Outbox identity/fence mismatch")
        return intent, receipt

    @staticmethod
    def _put_receipt(con: sqlite3.Connection, receipt: CommandReceipt) -> None:
        payload = to_json(receipt)
        con.execute("UPDATE outbox SET receipt=?,receipt_hash=? WHERE id=?", (payload, _hash(payload), receipt.intent_id))

    def receipt(self, identity: str) -> CommandReceipt:
        with self._connection() as con:
            return self._receipt(con, identity)[1]

    def delivery_status(self, identity: str) -> Literal["in_flight", "unknown", "confirmed", "failed"]:
        """Historical delivery outcome, never a statement of current device state."""
        with self._connection() as con:
            current = self._view(con).state
            intent, receipt = self._receipt(con, identity)
            if receipt.stage is ReceiptStage.FAILED:
                return "failed"
            if receipt.stage in (ReceiptStage.ACKNOWLEDGED, ReceiptStage.ECHOED, ReceiptStage.PHYSICAL_EVIDENCE):
                return "confirmed"
            if receipt.stage is ReceiptStage.UNKNOWN or (intent.boot_id, intent.owner_epoch) != (current.boot_id, current.owner_epoch):
                return "unknown"
            return "in_flight"

    def claim(self, intent: CommandIntent, fence: ControlState, snapshot: ControlSnapshot, clock: Clock) -> None:
        with self._write() as con:
            current = self._view(con)
            _fence(current.state, fence)
            if (intent.boot_id, intent.owner_epoch) != (fence.boot_id, fence.owner_epoch):
                raise StoreConflict("Intent belongs to an old writer")
            if current.state.last_intent != intent or not evaluate(current.state, snapshot, current.policy, clock).allowed:
                raise StoreConflict("Current persisted permission denies send claim")
            original, receipt = self._receipt(con, intent.intent_id)
            if original != intent or receipt.stage is not ReceiptStage.PREPARED:
                raise StoreConflict("Send claim already used or mismatched")
            self._put_receipt(con, replace(receipt, stage=ReceiptStage.UNKNOWN))
        self._point("after_claim")

    def record_receipt(self, receipt: CommandReceipt, fence: ControlState) -> bool:
        with self._write() as con:
            _fence(self._view(con).state, fence)
            intent, old = self._receipt(con, receipt.intent_id)
            if (intent.boot_id, intent.owner_epoch) != (fence.boot_id, fence.owner_epoch):
                raise StoreConflict("Old intent cannot receive new-epoch evidence")
            if (receipt.boot_id, receipt.owner_epoch, receipt.sequence, receipt.action) != (
                    fence.boot_id, fence.owner_epoch, intent.sequence, intent.action):
                raise StoreConflict("Receipt identity mismatch")
            order = {ReceiptStage.UNKNOWN: -1, ReceiptStage.SENT: 1, ReceiptStage.ACKNOWLEDGED: 2,
                     ReceiptStage.ECHOED: 3, ReceiptStage.PHYSICAL_EVIDENCE: 4, ReceiptStage.FAILED: 5}
            if receipt == old or order.get(receipt.stage, -2) < order.get(old.stage, 0):
                return False
            for field in ("requested_at", "prepared_at", "sent_at", "ha_ack_at", "device_echo_at", "physical_effect_at"):
                known = getattr(old, field)
                if known is not None and getattr(receipt, field) != known:
                    raise StoreConflict("Receipt cannot rewrite known facts")
            if old.stage is ReceiptStage.PREPARED or receipt.stage not in order or (
                    old.stage is receipt.stage and receipt != old):
                raise StoreConflict("Receipt stage conflict or unclaimed send")
            self._put_receipt(con, receipt)
        return True

    def restart(self, new_boot: str) -> StoreView:
        with self._write(point="owner_before_commit") as con:
            current = self._view(con)
            if con.execute("SELECT 1 FROM boots WHERE id=?", (new_boot,)).fetchone():
                raise StoreConflict("Boot identity reused")
            restarted = ControlState(boot_id=new_boot, owner_epoch=current.state.owner_epoch+1,
                                     manual_paused=current.state.manual_paused, off_latched=current.state.off_latched,
                                     mode=RuntimeMode.MANUAL_PAUSE if current.state.manual_paused else RuntimeMode.STARTING)
            updated = StoreView(current.revision+1, restarted, current.policy)
            self._save(con, updated)
            con.execute("INSERT INTO boots VALUES (?)", (new_boot,))
            for (identity,) in con.execute("SELECT id FROM outbox").fetchall():
                self._receipt(con, identity)  # Validate historical evidence without rewriting it.
            for identity, payload, checksum in con.execute("SELECT id,payload,checksum FROM oneshots").fetchall():
                shot = _decode(payload, checksum, OneShot)
                if shot.outcome is OneShotOutcome.CONSUMED:
                    p = to_json(replace(shot, outcome=OneShotOutcome.UNKNOWN))
                    con.execute("UPDATE oneshots SET payload=?,checksum=? WHERE id=?", (p, _hash(p), identity))
        return updated

    def checkpoint(self) -> tuple[int, int, int]:
        self._point("checkpoint_before")
        def progress() -> int:
            self._point("checkpoint_during")
            return 0
        with self._connection() as con:
            con.set_progress_handler(progress, 1)
            row = con.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
            return int(row[0]), int(row[1]), int(row[2])
