"""Offline, lossless legacy Heating AI state.json dry-run import.

Does not touch Home Assistant, legacy state, counters, or the live v2 database.
This stages evidence with byte/source and per-field integrity checks; it is NOT
permission to replay commands or to consider G4 completed without other archives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import tempfile
from pathlib import Path

MAX_SOURCE_BYTES = 16 * 1024 * 1024
REQUIRED = (
    "model", "equipment_settings", "system_settings", "temperature_forecasts",
    "temperature_history", "energy_bins", "energy_last", "inlet_energy",
    "power_observation_ledger", "fire_circulation",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")


def _original(path: Path) -> tuple[bytes, dict]:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES:
        raise ValueError("Missing or oversized original snapshot")
    raw = path.read_bytes()

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate JSON field")
            value[key] = item
        return value

    def bad_constant(_):
        raise ValueError("Non-finite JSON number")

    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=bad_constant)
    if type(data) is not dict or not all(key in data for key in REQUIRED):
        raise ValueError("Required legacy collections absent")
    for key in ("model", "equipment_settings", "system_settings",
                "temperature_history", "energy_last", "inlet_energy",
                "fire_circulation", "power_observation_ledger"):
        if type(data[key]) is not dict:
            raise ValueError("Invalid legacy object schema")
    for key in ("energy_bins", "temperature_forecasts"):
        if type(data[key]) is not list:
            raise ValueError("Invalid legacy list schema")
    _canonical(data)
    total = data["energy_last"].get("total")
    if type(total) not in (int, float) or not math.isfinite(total) or total < 0:
        raise ValueError("Invalid cumulative total")
    for item in data["energy_bins"]:
        if type(item) is not dict:
            raise ValueError("Invalid energy interval")
        start, end = item.get("start"), item.get("end")
        if (type(start) not in (int, float)
                or type(end) not in (int, float)
                or not math.isfinite(start)
                or not math.isfinite(end)
                or start >= end):
            raise ValueError("Invalid interval window")
    return raw, data


def _check(path: Path, data: dict, raw: bytes) -> dict:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity failed")
        identity = db.execute("SELECT source_sha, original_bytes FROM provenance").fetchone()
        if identity != (_sha(raw), len(raw)):
            raise ValueError("Source SHA/length mismatch")
        rows = db.execute("SELECT field, value_json, sha256 FROM legacy_record").fetchall()
        if len(rows) != len(data):
            raise ValueError("Legacy field count mismatch")
        restored = {}
        for key, blob, check in rows:
            if _sha(blob) != check:
                raise ValueError("Legacy field hash mismatch")
            restored[key] = json.loads(blob.decode("utf-8"))
        if _canonical(restored) != _canonical(data):
            raise ValueError("Exact value parity lost")
        proofs = db.execute("SELECT index_no, sha256 FROM forecast_proof ORDER BY index_no").fetchall()
        expected = [(i, _sha(_canonical(item))) for i, item in
                    enumerate(data["temperature_forecasts"])]
        if proofs != expected:
            raise ValueError("Original forecast-reference hashes changed")
        intervals = data["energy_bins"]
        gaps = sum(intervals[i]["end"] < intervals[i + 1]["start"] - 0.001
                   for i in range(len(intervals) - 1))
        overlaps = sum(intervals[i]["end"] > intervals[i + 1]["start"] + 0.001
                       for i in range(len(intervals) - 1))
        return {
            "status": "PASS_STATE_ONLY", "source_sha256": _sha(raw),
            "source_bytes": len(raw), "fields_preserved": len(rows),
            "forecast_references_preserved": len(proofs),
            "energy_intervals": len(intervals), "energy_gaps": gaps,
            "energy_overlaps": overlaps,
            "temperature_history_cycles": len(data["temperature_history"]),
            "source_total_unchanged": True, "byte_field_parity": True,
            "forecast_reference_hash_parity": True,
            "sqlite_integrity": "ok",
            "full_G4": "BLOCKED_OTHER_ARCHIVES_FRESH_DELTA_AND_RESTORE",
        }


def dry_run(source: Path, directory: Path) -> dict:
    raw, data = _original(source)
    directory.mkdir(parents=True, exist_ok=True)
    db_path = directory / "legacy_state_rehearsal.sqlite3"
    if db_path.exists():
        return {**_check(db_path, data, raw), "idempotent_rerun": True}
    with tempfile.NamedTemporaryFile(
        dir=directory, prefix=".legacy-v2-", suffix=".tmp", delete=False
    ) as tmp:
        path = Path(tmp.name)
    try:
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE provenance (source_sha TEXT PRIMARY KEY, original_bytes INTEGER NOT NULL)")
            db.execute("CREATE TABLE legacy_record (field TEXT PRIMARY KEY, value_json BLOB NOT NULL, sha256 TEXT NOT NULL)")
            db.execute("CREATE TABLE forecast_proof (index_no INTEGER PRIMARY KEY, sha256 TEXT NOT NULL)")
            db.execute("INSERT INTO provenance VALUES (?, ?)", (_sha(raw), len(raw)))
            for key, item in data.items():
                blob = _canonical(item)
                db.execute("INSERT INTO legacy_record VALUES (?, ?, ?)", (key, blob, _sha(blob)))
            for i, item in enumerate(data["temperature_forecasts"]):
                db.execute("INSERT INTO forecast_proof VALUES (?, ?)", (i, _sha(_canonical(item))))
            db.commit()
        report = _check(path, data, raw)
        os.replace(path, db_path)
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return {**report, "idempotent_rerun": False}
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("staging_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(dry_run(args.source, args.staging_directory), indent=2))
