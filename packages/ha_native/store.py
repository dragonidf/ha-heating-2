"""Checksummed SQLite confined to a disposable synthetic instance, never Recorder."""
from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterator, TypeAlias, cast

from packages.control_store.qualification import inspect_sqlite

JSON: TypeAlias = 'None | bool | int | float | str | list[JSON] | dict[str, JSON]'


class StoreError(RuntimeError):
    """Sanitized unavailable/corrupt synthetic storage."""


def encode(value: JSON) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':'))


def decode(raw: str) -> JSON:
    return cast(JSON, json.loads(raw))


class NativeStore:
    def __init__(self, root: Path, name: str, *, readonly: bool = False):
        if (not root.is_dir() or root.is_symlink()
                or root.resolve().parent != Path(tempfile.gettempdir()).resolve()
                or not root.name.startswith('heating-wp2c-')
                or name not in ('critical', 'evidence')):
            raise StoreError('Disposable synthetic directory required')
        self.path = root.resolve() / (name + '.sqlite3')
        self.readonly = readonly
        self.hook: Callable[[str], None] | None = None

    def _links(self) -> None:
        for suffix in ('', '-wal', '-shm', '.migration.sqlite3'):
            path = Path(str(self.path) + suffix) if suffix != '.migration.sqlite3' else self.path.with_suffix(suffix)
            if path.is_symlink() or path.exists() and path.stat().st_nlink != 1:
                raise StoreError('Linked synthetic store forbidden')

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._links()
        con: sqlite3.Connection | None = None
        try:
            con = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if self.readonly else '?mode=rw'),
                                  uri=True, timeout=0.05, isolation_level=None)
            con.execute('PRAGMA synchronous=FULL')
            yield con
        except (sqlite3.Error, OSError) as exc:
            raise StoreError('Synthetic store unavailable') from exc
        finally:
            if con is not None:
                con.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                yield con
                if self.hook:
                    self.hook('before_commit')
                con.commit()
            except BaseException:
                con.rollback()
                raise

    def open(self, initial: dict[str, JSON]) -> None:
        self._links()
        if not inspect_sqlite().qualified:
            raise StoreError('BLOCKED: linked SQLite WAL-reset qualification')
        try:
            if not self.path.exists():
                if self.readonly:
                    raise StoreError('Missing synthetic store')
                with self.path.open('xb'):
                    pass
                con = sqlite3.connect(self.path)
                try:
                    if con.execute('PRAGMA journal_mode=WAL').fetchone()[0] != 'wal':
                        raise StoreError('WAL unavailable')
                    con.execute('PRAGMA synchronous=FULL')
                    con.execute('BEGIN IMMEDIATE')
                    con.execute('CREATE TABLE records (name TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL)')
                    con.execute('PRAGMA user_version=2')
                    for key, value in initial.items():
                        self.write(con, key, value)
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
                finally:
                    con.close()
            with self.connect() as con:
                version = con.execute('PRAGMA user_version').fetchone()[0]
                if version not in (1, 2):
                    raise StoreError('Unsupported synthetic schema')
                if con.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise StoreError('Corrupt synthetic store')
                if con.execute('PRAGMA journal_mode').fetchone()[0] != 'wal':
                    raise StoreError('Synthetic WAL readback failed')
                for name, payload, digest in con.execute('SELECT name,payload,digest FROM records'):
                    self._value(payload, digest)
                if version == 1:
                    if self.readonly:
                        raise StoreError('Migration needs writable synthetic store')
                    backup = self.path.with_suffix('.migration.sqlite3')
                    if backup.exists():
                        backup.unlink()
                    out = sqlite3.connect(backup)
                    try:
                        con.backup(out)
                    finally:
                        out.close()
                    con.execute('BEGIN IMMEDIATE')
                    try:
                        con.execute('PRAGMA user_version=2')
                        if self.hook:
                            self.hook('migration_before_commit')
                        con.commit()
                    except BaseException:
                        con.rollback()
                        raise
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise StoreError('Synthetic startup failed') from exc

    def rollback_migration(self) -> None:
        self._links()
        try:
            source = sqlite3.connect(self.path.with_suffix('.migration.sqlite3').as_uri() + '?mode=ro', uri=True)
            try:
                with self.connect() as destination:
                    source.backup(destination)
            finally:
                source.close()
        except sqlite3.Error as exc:
            raise StoreError('Synthetic rollback unavailable') from exc

    @staticmethod
    def _value(payload: str, digest: str) -> JSON:
        if sha256(payload.encode()).hexdigest() != digest:
            raise StoreError('Synthetic record checksum mismatch')
        try:
            value = decode(payload)
            encode(value)
            return value
        except (ValueError, TypeError, RecursionError) as exc:
            raise StoreError('Invalid synthetic record') from exc

    @classmethod
    def read_from(cls, con: sqlite3.Connection, name: str) -> JSON:
        row = con.execute('SELECT payload,digest FROM records WHERE name=?', (name,)).fetchone()
        if row is None:
            raise StoreError('Missing synthetic record')
        return cls._value(str(row[0]), str(row[1]))

    def read(self, name: str) -> JSON:
        with self.connect() as con:
            return self.read_from(con, name)

    @staticmethod
    def write(con: sqlite3.Connection, name: str, value: JSON) -> None:
        raw = encode(value)
        con.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', (name, raw, sha256(raw.encode()).hexdigest()))
