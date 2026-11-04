"""Verify canonical traceability without changing acceptance criteria."""
import csv
from pathlib import Path
from packages.contracts import Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
from packages.offline.codec import decode, encode
from packages.offline.contracts import SourceEvent

ROOT = Path(__file__).resolve().parents[2]


def verify() -> None:
    for original, mapped, key, count in (
        ("requirements.csv", "requirements-coverage.csv", "id", 86),
        ("test-scenarios.csv", "scenario-coverage.csv", "scenario_id", 38),
    ):
        with (ROOT / "docs/spec/heating-ai-2.0" / original).open(encoding="utf-8-sig", newline="") as stream:
            expected = list(csv.DictReader(stream))
        with (ROOT / "docs/wp2c" / mapped).open(encoding="utf-8", newline="") as stream:
            actual = list(csv.DictReader(stream))
        assert len(expected) == len(actual) == count
        assert len({row[key] for row in actual}) == count
        assert [row[key] for row in expected] == [row[key] for row in actual]
        for baseline, row in zip(expected, actual, strict=True):
            assert all(row[name] == value for name, value in baseline.items()), row[key]
            assert row["test_evidence"] and row["remaining_acceptance"]
            assert "G1/B01-B08 BLOCKED" in row["gate_status"]
            for column in ("implementation", "test_evidence", "native_ha_test_source"):
                for name in filter(None, row.get(column, "").split(";")):
                    target = ROOT / name
                    assert target.exists() if column == "implementation" else target.is_file(), (row[key], name)
        print(f"{count} exact canonical rows and mapped evidence paths verified: {mapped}")
    expected_event = SourceEvent("native-browser-1", "synthetic.native.room", 1, 0,
        Reading(physical_id="synthetic.native.room", source_id="synthetic.native.room", value=21,
            unit=Unit.CELSIUS, observed_at=0, received_at=0,
            quality=Quality(status=QualityStatus.VALID, age_s=0, reason="synthetic"),
            provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=()))
    fixture = ROOT / "frontend/e2e-native/source.fixture.json"
    assert encode(decode(fixture.read_text())) == encode(expected_event)
    print("Native browser source fixture matches the accepted Python codec")


if __name__ == "__main__":
    verify()
