"""T-D01/D03/D04/D05: synthetic readings, never household data."""
import unittest
from dataclasses import FrozenInstanceError, replace

from packages.contracts import (
    ContractError, Missing, Provenance, Quality, QualityStatus, Reading,
    SourceKind, Unit, independent_measurements, power_to_watts,
)


def reading(value=0, unit=Unit.WATT, **changes):
    values = dict(
        physical_id="synthetic.meter", source_id="synthetic.local",
        value=value, unit=unit, observed_at=100.0, received_at=101.0,
        quality=Quality(status=QualityStatus.MISSING if value is None else QualityStatus.VALID,
                        age_s=1.0, reason="sample"),
        provenance=Provenance(kind=SourceKind.DIRECT, independent=True),
        evidence_ids=("synthetic.evidence",), signed=False,
    )
    return Reading(**(values | changes))


class ReadingTests(unittest.TestCase):
    def test_zero_null_false_and_absent_sequence_are_distinct(self):
        self.assertEqual(reading().value, 0)
        self.assertIsNone(reading(None).value)
        self.assertIs(reading(False, Unit.BOOLEAN).value, False)
        self.assertIs(reading().source_sequence, Missing.VALUE)
        self.assertIsNone(reading(source_sequence=None).source_sequence)
        self.assertEqual(reading(source_sequence=0).source_sequence, 0)

    def test_reading_and_nested_quality_are_immutable(self):
        r = reading()
        with self.assertRaises(FrozenInstanceError):
            r.value = 5
        with self.assertRaises(FrozenInstanceError):
            r.quality.age_s = 0

    def test_boolean_is_not_numeric_and_nonfinite_values_are_rejected(self):
        for value in (True, False, float("nan"), float("inf"), -float("inf"), "0"):
            with self.subTest(value=repr(value)), self.assertRaises(ContractError):
                reading(value)

    def test_unsigned_negative_power_and_negative_energy_are_not_silently_clipped(self):
        for unit in (Unit.WATT, Unit.KILOWATT, Unit.KWH):
            with self.subTest(unit=unit), self.assertRaises(ContractError):
                reading(-1, unit)
        self.assertEqual(reading(-2, signed=True).value, -2)
        self.assertEqual(reading(-20, Unit.CELSIUS).value, -20)

    def test_aliases_and_derived_balances_are_not_independent(self):
        a = reading()
        cloud = replace(a, source_id="synthetic.cloud")
        b = replace(a, physical_id="synthetic.other")
        self.assertFalse(independent_measurements((a, cloud)))
        self.assertTrue(independent_measurements((a, b)))
        derived = replace(b, provenance=Provenance(kind=SourceKind.DERIVED, independent=False))
        self.assertFalse(independent_measurements((a, derived)))
        with self.assertRaises(ContractError):
            Provenance(kind=SourceKind.DERIVED, independent=True)

    def test_unit_conversion_is_explicit_and_preserves_unknown(self):
        self.assertEqual(power_to_watts(reading(1.25, Unit.KILOWATT)), 1250)
        self.assertEqual(power_to_watts(reading(0)), 0)
        self.assertIsNone(power_to_watts(reading(None)))
        with self.assertRaises(ContractError):
            power_to_watts(reading(10, Unit.CELSIUS))

    def test_receipt_refresh_does_not_change_observed_at(self):
        r = reading()
        updated = replace(r, received_at=999.0)
        self.assertEqual(updated.observed_at, r.observed_at)
        self.assertEqual(updated.received_at, 999)
