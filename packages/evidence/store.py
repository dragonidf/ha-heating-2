"""Disposable append-only SQLite evidence DB. Never imported by the safety kernel."""

import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterator, Any
from packages.control_store.qualification import inspect_sqlite
from packages.contracts import Reading, Unit, QualityStatus, SourceKind
from packages.contracts.models import require, number, counter, ContractError
from packages.offline.contracts import (
    ArchiveRecord,
    ArchivePage,
    Cursor,
    Origin,
    EnergySlice,
    EnergySummary,
    PowerPoint,
    CounterPoint,
    ForecastRecord,
    RecoveryRequest,
    RecoveryProof,
    RecoveryReceipt,
    BudgetReceipt,
)
from packages.offline.codec import encode, decode
from packages.evidence.energy import integrate, counter_delta, clip
from packages.planner.evidence import comparison

PROTOCOL = "heating-offline-evidence/2"


class EvidenceFailure(RuntimeError):
    """Sanitized archive error; never permission to operate equipment."""


class EvidenceConflict(EvidenceFailure):
    """Immutable identity, coverage or revision conflict."""


def checksum(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def record(identity: str, value: object, at: float, stream: str) -> ArchiveRecord:
    return ArchiveRecord(identity, type(value).__name__, at, stream, encode(value))


def _root(root: Path) -> Path:
    base = Path(tempfile.gettempdir()).resolve()
    if (
        not root.is_dir()
        or root.is_symlink()
        or root.resolve().parent != base
        or not root.name.startswith("heating-wp2a-")
    ):
        raise EvidenceFailure("Disposable evidence directory required")
    root = root.resolve()
    for suffix in ("", "-wal", "-shm"):
        path = root / ("evidence.sqlite3" + suffix)
        if path.is_symlink() or path.exists() and path.stat().st_nlink != 1:
            raise EvidenceFailure("Linked database files forbidden")
    return root


class EvidenceStore:
    def __init__(
        self,
        root: Path,
        *,
        readonly: bool = False,
        hook: Callable[[str], None] | None = None,
    ):
        self.root = _root(root)
        self.path = self.root / "evidence.sqlite3"
        self.readonly = readonly
        self.hook = hook
        if not inspect_sqlite().qualified:
            raise EvidenceFailure("BLOCKED linked SQLite qualification")
        if not self.path.is_file():
            raise EvidenceFailure("Missing evidence DB; no implicit reset")
        with self.connection() as con:
            if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise EvidenceFailure("Corrupt evidence DB")
            version = int(con.execute("PRAGMA user_version").fetchone()[0])
            if version not in (1, 2) or con.execute(
                "SELECT protocol,checksum FROM metadata"
            ).fetchall() != [(PROTOCOL, checksum(PROTOCOL))]:
                raise EvidenceFailure("Unknown evidence schema/protocol")
        self.version = version

    @classmethod
    def create(
        cls, root: Path, *, version: int = 2, hook: Callable[[str], None] | None = None
    ) -> "EvidenceStore":
        root = _root(root)
        path = root / "evidence.sqlite3"
        if version not in (1, 2) or path.exists():
            raise EvidenceFailure("New disposable DB required")
        if not inspect_sqlite().qualified:
            raise EvidenceFailure("BLOCKED linked SQLite qualification")
        con = None
        try:
            con = sqlite3.connect(path, isolation_level=None)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "CREATE TABLE metadata(protocol TEXT NOT NULL,checksum TEXT NOT NULL)"
            )
            con.execute(
                "INSERT INTO metadata VALUES (?,?)", (PROTOCOL, checksum(PROTOCOL))
            )
            con.execute(
                "CREATE TABLE archive(seq INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,at REAL NOT NULL,kind TEXT NOT NULL,stream TEXT NOT NULL,payload TEXT NOT NULL,checksum TEXT NOT NULL,previous TEXT NOT NULL,chain TEXT NOT NULL)"
            )
            con.execute("CREATE INDEX archive_time ON archive(stream,kind,at,seq)")
            con.execute(
                "CREATE TABLE origins(stream TEXT PRIMARY KEY,continuity TEXT UNIQUE NOT NULL,at REAL NOT NULL,initial REAL NOT NULL,seq INTEGER NOT NULL REFERENCES archive(seq))"
            )
            con.execute(
                "CREATE TABLE energy(id TEXT PRIMARY KEY,stream TEXT NOT NULL,start REAL NOT NULL,end REAL NOT NULL,seq INTEGER UNIQUE NOT NULL REFERENCES archive(seq))"
            )
            con.execute("CREATE INDEX energy_range ON energy(stream,start,end)")
            con.execute(
                "CREATE TABLE forecasts(cycle TEXT NOT NULL,role TEXT NOT NULL,issued REAL NOT NULL,recorded REAL NOT NULL,seq INTEGER UNIQUE NOT NULL REFERENCES archive(seq))"
            )
            con.execute(
                "CREATE UNIQUE INDEX frozen_forecasts ON forecasts(cycle,role) WHERE role IN ('initial','prestart','original')"
            )
            for table in ("archive", "origins", "energy", "forecasts"):
                con.execute(
                    f"CREATE TRIGGER {table}_immutable_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'append only'); END"
                )
                con.execute(
                    f"CREATE TRIGGER {table}_immutable_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'append only'); END"
                )
            if version == 2:
                cls._v2(con)
            con.execute(f"PRAGMA user_version={version}")
            con.commit()
        except (sqlite3.Error, OSError):
            if con is not None:
                con.rollback()
            raise EvidenceFailure("Evidence creation failed") from None
        finally:
            if con is not None:
                con.close()
        return cls(root, hook=hook)

    @staticmethod
    def _v2(con: sqlite3.Connection) -> None:
        con.execute("CREATE INDEX energy_frontier ON energy(stream,end)")
        con.execute(
            "CREATE TABLE recovery_claims(unknown_id TEXT PRIMARY KEY,recovery_id TEXT NOT NULL,seq INTEGER NOT NULL REFERENCES archive(seq))"
        )
        con.execute("CREATE INDEX forecasts_cycle ON forecasts(cycle,role,issued,seq)")
        for operation in ("UPDATE", "DELETE"):
            con.execute(
                f"CREATE TRIGGER recovery_{operation} BEFORE {operation} ON recovery_claims BEGIN SELECT RAISE(ABORT,'append only'); END"
            )

    def point(self, name: str) -> None:
        if self.hook is not None:
            self.hook(name)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        con = None
        try:
            _root(self.root)
            if self.path != self.root / "evidence.sqlite3":
                raise EvidenceFailure("Invalid evidence path")
            con = sqlite3.connect(
                self.path.as_uri() + ("?mode=ro" if self.readonly else "?mode=rw"),
                uri=True,
                timeout=0.025,
                isolation_level=None,
            )
            con.execute("PRAGMA synchronous=FULL")
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA trusted_schema=OFF")
            if con.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                raise EvidenceFailure("Evidence WAL mode changed")
            yield con
        except (sqlite3.Error, OSError, ValueError):
            raise EvidenceFailure("Evidence operation failed") from None
        finally:
            if con is not None:
                con.close()

    @contextmanager
    def read_snapshot(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as con:
            con.execute("BEGIN")
            try:
                yield con
            finally:
                con.rollback()

    @contextmanager
    def transaction(self, *, migration: bool = False) -> Iterator[sqlite3.Connection]:
        if self.readonly or self.version != 2 and not migration:
            raise EvidenceFailure("Evidence is read-only or needs migration")
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
                self.point("before_commit")
                con.commit()
                self.point("after_commit")
            except BaseException:
                con.rollback()
                raise

    def migrate(self) -> None:
        if self.version == 2:
            return
        with self.transaction(migration=True) as con:
            self._v2(con)
            self.point("schema_before_commit")
            con.execute("PRAGMA user_version=2")
        self.version = 2

    @staticmethod
    def _head(con: sqlite3.Connection) -> tuple[int, str]:
        row = con.execute(
            "SELECT seq,chain FROM archive ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return (int(row[0]), str(row[1])) if row else (0, "0" * 64)

    def head(self) -> tuple[int, str]:
        with self.read_snapshot() as con:
            return self._head(con)

    @staticmethod
    def _read(row: tuple[Any, ...]) -> ArchiveRecord:
        seq, payload, hashed, previous, chain = row
        if (
            checksum(payload) != hashed
            or checksum(f"{seq}:{previous}:{hashed}") != chain
        ):
            raise EvidenceFailure("Archive checksum mismatch")
        value = decode(payload)
        if not isinstance(value, ArchiveRecord):
            raise EvidenceFailure("Invalid archive record")
        inner = decode(value.payload)
        if type(inner).__name__ != value.kind:
            raise EvidenceFailure("Archive type mismatch")
        return value

    @classmethod
    def _get(cls, con: sqlite3.Connection, identity: str) -> ArchiveRecord:
        row = con.execute(
            "SELECT seq,payload,checksum,previous,chain FROM archive WHERE id=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise EvidenceFailure("Missing archive identity")
        result = cls._read(row)
        if result.identity != identity:
            raise EvidenceFailure("Archive identity mismatch")
        return result

    def get(self, identity: str) -> ArchiveRecord:
        with self.read_snapshot() as con:
            return self._get(con, identity)

    @classmethod
    def _origin(cls, con: sqlite3.Connection, stream: str) -> Origin:
        row = con.execute(
            "SELECT continuity,at,initial,seq FROM origins WHERE stream=?", (stream,)
        ).fetchone()
        if row is None:
            raise EvidenceConflict("Missing energy origin")
        raw = con.execute(
            "SELECT seq,payload,checksum,previous,chain FROM archive WHERE seq=?",
            (row[3],),
        ).fetchone()
        if raw is None:
            raise EvidenceFailure("Missing origin evidence")
        value = decode(cls._read(raw).payload)
        if not isinstance(value, Origin) or value != Origin(
            stream, str(row[0]), float(row[1]), float(row[2])
        ):
            raise EvidenceFailure("Origin evidence/index mismatch")
        return value

    @classmethod
    def _frontier(cls, con: sqlite3.Connection, stream: str) -> float:
        origin = cls._origin(con, stream)
        row = con.execute(
            "SELECT e.end,a.seq,a.payload,a.checksum,a.previous,a.chain FROM energy e JOIN archive a ON a.seq=e.seq WHERE e.stream=? ORDER BY e.end DESC LIMIT 1",
            (stream,),
        ).fetchone()
        if row is None:
            return origin.at
        value = decode(cls._read(tuple(row[1:])).payload)
        if (
            not isinstance(value, EnergySlice)
            or value.stream != stream
            or value.end != row[0]
        ):
            raise EvidenceFailure("Energy frontier mismatch")
        return value.end

    @classmethod
    def _append(
        cls,
        con: sqlite3.Connection,
        event: ArchiveRecord,
        *,
        accounted: bool = False,
        recovery: bool = False,
    ) -> int:
        value = decode(event.payload)
        if isinstance(value, RecoveryRequest) and not recovery:
            raise EvidenceConflict("Recovery requires the administrative gate")
        if isinstance(value, EnergySlice) and value.kwh is not None and not accounted:
            raise EvidenceConflict("Known energy requires source processing")
        if type(value).__name__ != event.kind:
            raise EvidenceConflict("Payload kind mismatch")
        for field, expected in (("identity", event.identity), ("stream", event.stream)):
            actual = getattr(value, field, expected)
            if actual != expected:
                raise EvidenceConflict("Payload identity/stream mismatch")
        source_at = (
            value.start
            if isinstance(value, EnergySlice)
            else (
                value.recorded_at
                if isinstance(value, ForecastRecord)
                else getattr(value, "at", event.at)
            )
        )
        if source_at != event.at:
            raise EvidenceConflict("Archive/source timestamp mismatch")
        payload = encode(event)
        hashed = checksum(payload)
        existing = con.execute(
            "SELECT seq,payload,checksum,previous,chain FROM archive WHERE id=?",
            (event.identity,),
        ).fetchone()
        if existing is not None:
            if cls._read(existing) != event:
                raise EvidenceConflict("Immutable event identity conflict")
            return int(existing[0])
        last, previous = cls._head(con)
        seq = last + 1
        chain = checksum(f"{seq}:{previous}:{hashed}")
        if isinstance(value, EnergySlice):
            origin = cls._origin(con, value.stream)
            if value.continuity != origin.continuity or value.start != cls._frontier(
                con, value.stream
            ):
                raise EvidenceConflict("Energy gap/overlap/continuity conflict")
        if (
            isinstance(value, ForecastRecord)
            and value.role != "latest"
            and con.execute(
                "SELECT 1 FROM forecasts WHERE cycle=? AND role=?",
                (value.cycle_id, value.role),
            ).fetchone()
        ):
            raise EvidenceConflict("Frozen forecast cannot be replaced")
        con.execute(
            "INSERT INTO archive VALUES (?,?,?,?,?,?,?,?,?)",
            (
                seq,
                event.identity,
                event.at,
                event.kind,
                event.stream,
                payload,
                hashed,
                previous,
                chain,
            ),
        )
        if isinstance(value, Origin):
            con.execute(
                "INSERT INTO origins VALUES (?,?,?,?,?)",
                (value.stream, value.continuity, value.at, value.initial_kwh, seq),
            )
        if isinstance(value, EnergySlice):
            con.execute(
                "INSERT INTO energy VALUES (?,?,?,?,?)",
                (value.identity, value.stream, value.start, value.end, seq),
            )
        if isinstance(value, ForecastRecord):
            if event.stream != value.cycle_id:
                raise EvidenceConflict("Forecast cycle mismatch")
            con.execute(
                "INSERT INTO forecasts VALUES (?,?,?,?,?)",
                (
                    value.cycle_id,
                    value.role,
                    value.curve.issued if value.curve else -1,
                    value.recorded_at,
                    seq,
                ),
            )
        return seq

    def append(self, event: ArchiveRecord) -> int:
        with self.transaction() as con:
            self.point("append_before")
            seq = self._append(con, event)
        return seq

    def append_batch(self, events: tuple[ArchiveRecord, ...]) -> tuple[int, ...]:
        require(
            type(events) is tuple and len(events) <= 512, "Invalid atomic archive batch"
        )
        with self.transaction() as con:
            return tuple(self._append(con, e) for e in events)

    def origin(self, origin: Origin) -> int:
        return self.append(
            record("origin:" + origin.stream, origin, origin.at, origin.stream)
        )

    def power(self, point: PowerPoint) -> tuple[int, bool]:
        with self.transaction() as con:
            late = point.at < self._frontier(con, point.stream)
            seq = self._append(
                con, record(point.identity, point, point.at, point.stream)
            )
        return seq, late

    def post(self, value: EnergySlice) -> int:
        return self.append(record(value.identity, value, value.start, value.stream))

    def finalize(
        self, stream: str, until: float, *, as_of: float, hold_s: float = 45
    ) -> tuple[EnergySlice, ...]:
        number(until)
        number(as_of)
        require(until <= as_of, "Cannot finalize future energy")
        with self.transaction() as con:
            origin = self._origin(con, stream)
            start = self._frontier(con, stream)
            if until < start:
                raise EvidenceConflict("Accounting clock moved backwards")
            if until == start:
                return ()
            rows = con.execute(
                "SELECT seq,payload,checksum,previous,chain FROM archive WHERE stream=? AND kind='PowerPoint' AND at>=? AND at<=? ORDER BY at,seq LIMIT 10001",
                (stream, start - 45, until),
            ).fetchall()
            if len(rows) > 10000:
                raise EvidenceFailure("Power integration batch too large")
            points = []
            for row in rows:
                value = decode(self._read(row).payload)
                if not isinstance(value, PowerPoint):
                    raise EvidenceFailure("Invalid power row")
                if value.received <= as_of:
                    points.append(value)
            slices = integrate(
                tuple(points),
                start,
                until,
                origin.continuity,
                hold_s=hold_s,
                stream=stream,
            )
            for value in slices:
                self._append(
                    con,
                    record(value.identity, value, value.start, stream),
                    accounted=True,
                )
            return slices

    def post_counter(
        self, left: CounterPoint, right: CounterPoint, max_kw: float
    ) -> EnergySlice:
        with self.transaction() as con:
            value = counter_delta(
                left, right, max_kw, self._origin(con, left.stream).continuity
            )
            for p in (left, right):
                self._append(con, record(p.identity, p, p.at, p.stream))
            self._append(
                con,
                record(value.identity, value, value.start, value.stream),
                accounted=True,
            )
            return value

    def query(
        self,
        stream: str,
        kind: str,
        start: float,
        end: float,
        *,
        limit: int = 100,
        cursor: Cursor | None = None,
    ) -> ArchivePage:
        number(start)
        number(end)
        require(
            start < end and type(limit) is int and 1 <= limit <= 256,
            "Invalid history page",
        )

        with self.read_snapshot() as con:
            watermark = self._head(con)[0] if cursor is None else cursor.watermark
            if watermark > self._head(con)[0]:
                raise EvidenceConflict("Cursor frontier unavailable")
            chain = con.execute(
                "SELECT chain FROM archive WHERE seq=?", (watermark,)
            ).fetchone()
            query_hash = checksum(
                repr(
                    (
                        stream,
                        kind,
                        start,
                        end,
                        watermark,
                        chain[0] if chain else "0" * 64,
                    )
                )
            )
            if cursor is not None and cursor.query_hash != query_hash:
                raise EvidenceConflict("Cursor does not match query/archive")
            at, seq = (cursor.last_at, cursor.last_seq) if cursor else (start, -1)
            rows = con.execute(
                "SELECT seq,payload,checksum,previous,chain FROM archive WHERE stream=? AND kind=? AND at>=? AND at<? AND seq<=? AND (at>? OR at=? AND seq>?) ORDER BY at,seq LIMIT ?",
                (stream, kind, start, end, watermark, at, at, seq, limit + 1),
            ).fetchall()
            page = tuple((int(row[0]), self._read(row)) for row in rows[:limit])
            next_cursor = (
                Cursor(watermark, page[-1][1].at, page[-1][0], query_hash)
                if len(rows) > limit
                else None
            )
            return ArchivePage(page, next_cursor, watermark)

    @classmethod
    def _slices(cls, con: sqlite3.Connection, stream: str) -> Iterator[EnergySlice]:
        journal_count = con.execute(
            "SELECT count(*) FROM archive WHERE stream=? AND kind='EnergySlice'",
            (stream,),
        ).fetchone()[0]
        if (
            journal_count
            != con.execute(
                "SELECT count(*) FROM energy WHERE stream=?", (stream,)
            ).fetchone()[0]
        ):
            raise EvidenceFailure("Energy index coverage mismatch")
        rows = con.execute(
            "SELECT a.seq,a.payload,a.checksum,a.previous,a.chain,e.id,e.start,e.end FROM energy e JOIN archive a ON a.seq=e.seq WHERE e.stream=? ORDER BY e.start",
            (stream,),
        )
        for row in rows:
            value = decode(cls._read(tuple(row[:5])).payload)
            if not isinstance(value, EnergySlice) or (
                value.identity,
                value.stream,
                value.start,
                value.end,
            ) != (row[5], stream, row[6], row[7]):
                raise EvidenceFailure("Invalid energy evidence/index")
            yield value

    @classmethod
    def _summary(cls, con: sqlite3.Connection, stream: str) -> EnergySummary:
        origin = cls._origin(con, stream)
        sums = {c: 0.0 for c in ("confirmed", "derived", "estimated", "recovered")}
        unknown = 0.0
        for value in cls._slices(con, stream):
            if value.category == "unknown":
                if not con.execute(
                    "SELECT 1 FROM recovery_claims WHERE unknown_id=?",
                    (value.identity,),
                ).fetchone():
                    unknown += value.end - value.start
            else:
                sums[value.category] += value.kwh or 0
        rows = con.execute(
            "SELECT seq,payload,checksum,previous,chain FROM archive WHERE stream=? AND kind='RecoveryRequest'",
            (stream,),
        )
        for row in rows:
            recovery = decode(cls._read(row).payload)
            if not isinstance(recovery, RecoveryRequest):
                raise EvidenceFailure("Invalid recovery")
            cls._recovery_proof(con, recovery, stream)
            sums["recovered"] += recovery.kwh
        return EnergySummary(
            stream,
            origin.initial_kwh,
            sums["confirmed"],
            sums["derived"],
            sums["estimated"],
            sums["recovered"],
            unknown,
            origin.initial_kwh
            + sums["confirmed"]
            + sums["derived"]
            + sums["recovered"],
            cls._head(con)[0],
        )

    def summary(self, stream: str) -> EnergySummary:
        with self.read_snapshot() as con:
            return self._summary(con, stream)

    def backup(self, destination: Path) -> str:
        destination = _root(destination)
        target = destination / "evidence.sqlite3"
        if target.exists():
            raise EvidenceConflict("Backup destination must be empty")
        with self.connection() as con:
            out = sqlite3.connect(target)
            try:
                con.backup(out)
            finally:
                out.close()
        self.point("backup_after")
        return sha256(target.read_bytes()).hexdigest()

    @classmethod
    def _recovery_proof(
        cls, con: sqlite3.Connection, request: RecoveryRequest, stream: str
    ) -> None:
        def get(identity: str) -> ArchiveRecord:
            try:
                return cls._get(con, identity)
            except EvidenceFailure as exc:
                raise EvidenceConflict("Missing or invalid recovery evidence") from exc

        archived = get(request.evidence_hash)
        proof = decode(archived.payload)
        origin = cls._origin(con, stream)
        if (
            not isinstance(proof, RecoveryProof)
            or checksum(archived.payload) != request.evidence_hash
            or archived.stream != stream
            or proof.stream != stream
            or proof.continuity != origin.continuity
            or proof.unknown_ids != request.unknown_ids
            or proof.quality is not QualityStatus.VALID
            or proof.kwh != request.kwh
        ):
            raise EvidenceConflict("Unqualified recovery proof")
        spans = []
        for identity in proof.unknown_ids:
            span = decode(get(identity).payload)
            if (
                not isinstance(span, EnergySlice)
                or span.stream != stream
                or span.continuity != proof.continuity
                or span.category != "unknown"
            ):
                raise EvidenceConflict("Recovery gap mismatch")
            spans.append(span)
        spans.sort(key=lambda s: s.start)
        if (
            spans[0].start != proof.window.start
            or spans[-1].end != proof.window.end
            or any(a.end != b.start for a, b in zip(spans, spans[1:]))
        ):
            raise EvidenceConflict("Recovery time coverage mismatch")
        readings = []
        for identity, at in (
            (proof.left_id, proof.window.start),
            (proof.right_id, proof.window.end),
        ):
            raw = get(identity)
            value = decode(raw.payload)
            if (
                not isinstance(value, Reading)
                or raw.stream != stream
                or raw.at != at
                or value.unit is not Unit.KWH
                or value.value is None
                or value.quality.status is not QualityStatus.VALID
                or value.provenance.kind is not SourceKind.DIRECT
                or not value.provenance.independent
                or (value.source_id, value.physical_id)
                != (proof.source_id, proof.physical_id)
                or value.observed_at != at
                or not at <= value.received_at <= archived.at
            ):
                raise EvidenceConflict("Recovery meter source/time/quality mismatch")
            readings.append(float(value.value))
        # Only arithmetic rounding is tolerated; approval cannot choose the amount.
        delta = readings[1] - readings[0]
        if delta < 0 or abs(delta - proof.kwh) > 1e-9:
            raise EvidenceConflict("Recovery amount is not supported by meter delta")

    def recover(
        self,
        request: RecoveryRequest,
        stream: str,
        backup_root: Path,
        *,
        dry_run: bool,
        approved: bool,
    ) -> RecoveryReceipt:
        require(
            type(dry_run) is bool and type(approved) is bool,
            "Invalid recovery authority flags",
        )
        backup_root = _root(backup_root)
        backup = EvidenceStore(backup_root, readonly=True)
        if sha256(backup.path.read_bytes()).hexdigest() != request.backup_hash:
            raise EvidenceConflict("Recovery backup checksum mismatch")
        with self.transaction() as con:
            self._recovery_proof(con, request, stream)
            old = con.execute(
                "SELECT seq FROM archive WHERE id=?", (request.identity,)
            ).fetchone()
            if old:
                if self._get(con, request.identity) != record(
                    request.identity, request, 0, stream
                ):
                    raise EvidenceConflict("Recovery identity reused")
                seconds = sum(
                    decode(self._get(con, identity).payload).end
                    - decode(self._get(con, identity).payload).start
                    for identity in request.unknown_ids
                )
                return RecoveryReceipt(
                    request.identity,
                    dry_run,
                    request.expected_total,
                    request.expected_total + request.kwh,
                    seconds,
                    int(old[0]),
                )
            before = self._summary(con, stream)
            if abs(
                before.actual_total_kwh - request.expected_total
            ) > 1e-9 or backup.head() != self._head(con):
                raise EvidenceConflict("Stale recovery preview/backup")
            seconds = 0.0
            for identity in request.unknown_ids:
                value = decode(self._get(con, identity).payload)
                if (
                    not isinstance(value, EnergySlice)
                    or value.stream != stream
                    or value.category != "unknown"
                ):
                    raise EvidenceConflict("Recovery coverage is not unknown")
                if con.execute(
                    "SELECT 1 FROM recovery_claims WHERE unknown_id=?", (identity,)
                ).fetchone():
                    raise EvidenceConflict("Coverage already recovered")
                seconds += value.end - value.start
            if not dry_run:
                if not approved:
                    raise EvidenceConflict("Explicit recovery approval required")
                seq = self._append(
                    con, record(request.identity, request, 0, stream), recovery=True
                )
                for identity in request.unknown_ids:
                    con.execute(
                        "INSERT INTO recovery_claims VALUES (?,?,?)",
                        (identity, request.identity, seq),
                    )
            return RecoveryReceipt(
                request.identity,
                dry_run,
                before.actual_total_kwh,
                before.actual_total_kwh + request.kwh,
                seconds,
                self._head(con)[0],
            )

    def forecast(self, value: ForecastRecord) -> int:
        return self.append(
            record(value.identity, value, value.recorded_at, value.cycle_id)
        )

    def freeze_original(
        self, cycle: str, reference: float, *, as_of: float
    ) -> ForecastRecord:
        number(reference)
        number(as_of)
        require(as_of <= reference, "Cannot backfill original after reference")
        with self.transaction() as con:
            rows = con.execute(
                "SELECT a.seq,a.payload,a.checksum,a.previous,a.chain FROM forecasts f JOIN archive a ON a.seq=f.seq WHERE cycle=? AND role='original'",
                (cycle,),
            ).fetchall()
            if rows:
                existing = decode(self._read(rows[0]).payload)
                if (
                    not isinstance(existing, ForecastRecord)
                    or existing.reference != reference
                ):
                    raise EvidenceConflict("Frozen reference mismatch")
                return existing
            rows = con.execute(
                "SELECT a.seq,a.payload,a.checksum,a.previous,a.chain FROM forecasts f JOIN archive a ON a.seq=f.seq WHERE cycle=? AND role='latest' AND issued<=? AND recorded<=? ORDER BY issued DESC,a.seq DESC LIMIT 1001",
                # Source issue lead does not prove availability before the cutoff.
                (cycle, reference - 43200, min(as_of, reference - 43200)),
            ).fetchall()
            if len(rows) > 1000:
                raise EvidenceFailure("Forecast selection bound exceeded")
            curve = None
            planned = None
            energy_scope = None
            for row in rows:
                candidate = decode(self._read(row).payload)
                if not isinstance(candidate, ForecastRecord):
                    raise EvidenceFailure("Invalid curve row")
                if (
                    candidate.curve
                    and candidate.curve.issued <= reference - 43200
                    and candidate.recorded_at <= min(as_of, reference - 43200)
                    and candidate.curve.points[0][0]
                    <= reference
                    <= candidate.curve.points[-1][0]
                ):
                    curve = candidate.curve
                    planned = candidate.planned_kwh
                    energy_scope = candidate.energy_scope
                    break
            original = ForecastRecord(
                "original:" + cycle,
                cycle,
                "original",
                reference,
                curve,
                as_of,
                planned,
                energy_scope,
            )
            self._append(con, record(original.identity, original, as_of, cycle))
            return original

    def budget(
        self, cycle: str, stream: str, end: float, latest_projected_kwh: float
    ) -> BudgetReceipt:
        number(end)
        number(latest_projected_kwh, nonnegative=True)
        with self.read_snapshot() as con:
            row = con.execute(
                "SELECT a.seq,a.payload,a.checksum,a.previous,a.chain FROM forecasts f JOIN archive a ON a.seq=f.seq WHERE cycle=? AND role='initial'",
                (cycle,),
            ).fetchone()
            if row is None:
                raise EvidenceConflict("Missing immutable initial forecast")
            initial = decode(self._read(row).payload)
            if not isinstance(initial, ForecastRecord):
                raise EvidenceFailure("Invalid initial forecast")
            require(initial.reference < end, "Invalid cycle budget scope")
            known = 0.0
            unknown = end - initial.reference
            rows = con.execute(
                "SELECT a.seq,a.payload,a.checksum,a.previous,a.chain FROM energy e JOIN archive a ON a.seq=e.seq WHERE e.stream=? AND e.start<? AND e.end>? ORDER BY e.start",
                (stream, end, initial.reference),
            )
            for value_row in rows:
                value = decode(self._read(value_row).payload)
                if not isinstance(value, EnergySlice):
                    raise EvidenceFailure("Invalid cycle energy")
                part = clip(value, initial.reference, end)
                if part is None:
                    continue
                if part.category in ("confirmed", "derived"):
                    known += part.kwh or 0
                    unknown -= part.end - part.start
            # Recovery has an amount and interval coverage, never an invented time profile.
            for recovery_row in con.execute(
                "SELECT seq,payload,checksum,previous,chain FROM archive WHERE stream=? AND kind='RecoveryRequest'",
                (stream,),
            ):
                recovery = decode(self._read(recovery_row).payload)
                if not isinstance(recovery, RecoveryRequest):
                    raise EvidenceFailure("Invalid recovery")
                self._recovery_proof(con, recovery, stream)
                spans = [
                    decode(self._get(con, i).payload) for i in recovery.unknown_ids
                ]
                if all(
                    isinstance(s, EnergySlice)
                    and initial.reference <= s.start < s.end <= end
                    for s in spans
                ):
                    known += recovery.kwh
                    unknown -= sum(s.end - s.start for s in spans)
            reference = (
                initial.planned_kwh if initial.energy_scope is not None else None
            )
            if initial.energy_scope is not None and end > initial.energy_scope.end:
                raise EvidenceConflict("Actual period exceeds forecast energy scope")
            return BudgetReceipt(
                cycle,
                stream,
                reference,
                known,
                max(0, unknown),
                latest_projected_kwh,
                reference - known if reference is not None else None,
                (
                    max(0, latest_projected_kwh - reference)
                    if reference is not None
                    else None
                ),
                self._head(con)[0],
                initial.energy_scope,
                end,
            )

    def compare_original(
        self, cycle: str, target: float, actual: Reading
    ) -> tuple[float, float] | None:
        if (
            actual.unit is not Unit.CELSIUS
            or actual.value is None
            or actual.observed_at != target
            or actual.quality.status is not QualityStatus.VALID
            or actual.provenance.kind is not SourceKind.DIRECT
        ):
            return None
        frozen = decode(self.get("original:" + cycle).payload)
        if not isinstance(frozen, ForecastRecord) or frozen.curve is None:
            return None
        return comparison(frozen.curve, target, float(actual.value))

    def verify(self) -> int:
        with self.read_snapshot() as con:
            previous = "0" * 64
            expected = 1
            for row in con.execute(
                "SELECT seq,payload,checksum,previous,chain FROM archive ORDER BY seq"
            ):
                if row[0] != expected or row[3] != previous:
                    raise EvidenceFailure("Broken archive continuity")
                self._read(row)
                previous = row[4]
                expected += 1
            return expected - 1

    def checkpoint(self) -> tuple[int, int, int]:
        self.point("checkpoint_before")
        with self.connection() as con:
            row = con.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
            return int(row[0]), int(row[1]), int(row[2])
