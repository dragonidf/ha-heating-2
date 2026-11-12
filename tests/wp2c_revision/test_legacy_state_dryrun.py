"""Synthetic-only migration tests; never commit or consume household source data."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.release.legacy_state_dryrun import dry_run, _original


def synthetic_state() -> dict:
    return {
        "model": {"validated": True, "floor_air": 0.02},
        "equipment_settings": {"boiler_power_mode": "fixed_9"},
        "system_settings": {"power_partial_reserve": "off"},
        "temperature_forecasts": [{"at": 100.0, "snapshot_id": "test"}],
        "temperature_history": {"synthetic_day": {"original": None}},
        "energy_bins": [
            {"start": 100.0, "end": 160.0, "kwh": 0.1},
            {"start": 220.0, "end": 280.0, "kwh": 0.2},
        ],
        "energy_last": {"ts": 300.0, "total": 100.5},
        "inlet_energy": {"origin_kwh": 50.0},
        "power_observation_ledger": {},
        "fire_circulation": {"active": False},
    }


class LegacyDryRunTests(unittest.TestCase):
    def test_roundtrip_idempotence_preserves_gaps_and_rejects_new_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "state.json"
            destination = root / "staging"
            source.write_text(json.dumps(synthetic_state()))
            first = dry_run(source, destination)
            self.assertEqual(first["status"], "PASS_STATE_ONLY")
            self.assertEqual(first["fields_preserved"], 10)
            self.assertEqual(first["forecast_references_preserved"], 1)
            self.assertEqual(first["energy_gaps"], 1)
            self.assertEqual(first["energy_overlaps"], 0)
            self.assertTrue(first["canonical_value_parity"])
            self.assertFalse(first["idempotent_rerun"])
            db = destination / "legacy_state_rehearsal.sqlite3"
            initial = db.read_bytes()
            second = dry_run(source, destination)
            self.assertTrue(second["idempotent_rerun"])
            self.assertEqual(db.read_bytes(), initial)
            other = synthetic_state()
            other["energy_last"]["total"] = 101.5
            source.write_text(json.dumps(other))
            with self.assertRaises(ValueError):
                dry_run(source, destination)

    def test_refuses_checksum_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "state.json"
            destination = root / "stage"
            source.write_text(json.dumps(synthetic_state()))
            dry_run(source, destination)
            with sqlite3.connect(destination / "legacy_state_rehearsal.sqlite3") as con:
                con.execute(
                    "UPDATE legacy_record SET sha256='tampered' WHERE field='model'"
                )
                con.commit()
            with self.assertRaises(ValueError):
                dry_run(source, destination)

    def test_rejects_duplicate_fields_invalid_totals_and_intervals(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "state.json"
            source.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                _original(source)
            bad = synthetic_state()
            bad["energy_bins"][1]["end"] = 210
            source.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                _original(source)
            bad = synthetic_state()
            bad["energy_last"]["total"] = -1
            source.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                _original(source)


if __name__ == "__main__":
    unittest.main()
