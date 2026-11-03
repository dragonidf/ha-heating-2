"""Observe the actual linked library. No qualification of a different host is implied."""
import re
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SQLiteInfo:
    version: str
    source_id: str
    qualified: bool


def supported_sqlite(version: str) -> bool:
    # Older patched backports need independently documented provenance, absent here.
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return False
    parts = tuple(map(int, version.split(".")))
    return parts[0] == 3 and parts >= (3, 51, 3)


def inspect_sqlite() -> SQLiteInfo:
    connection = sqlite3.connect(":memory:")
    try:
        version, source_id = connection.execute("SELECT sqlite_version(), sqlite_source_id()").fetchone()
        return SQLiteInfo(version, source_id, supported_sqlite(version))
    finally:
        connection.close()
