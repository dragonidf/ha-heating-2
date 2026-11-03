import json
import unittest
from dataclasses import replace

from packages.contracts import (
    ContractError, HeatPermit, Quality, QualityStatus, Provenance, Reason, SourceKind, Unit,
    from_json, power_to_kilowatts, power_to_watts, to_json,
)
from tests.fixtures.synthetic import policy, reading, snapshot


class BoundaryTests(unittest.TestCase):
    def test_watt_kilowatt_conversion_both_directions_preserves_signed_zero_and_unknown(self):
        for value in (-1200, 0, 1200):
            self.assertEqual(power_to_kilowatts(reading(value, signed=True)), value / 1000)
            self.assertEqual(power_to_watts(reading(value / 1000, Unit.KILOWATT, signed=True)), value)
        self.assertIsNone(power_to_kilowatts(reading(None)))
        with self.assertRaises(ContractError):
            power_to_kilowatts(reading(1, Unit.KWH))
        with self.assertRaises(ContractError):
            power_to_watts(reading(1e308, Unit.KILOWATT))

    def test_quality_bounds_identifiers_and_direct_constructor_ranges(self):
        for args in (dict(lower=1), dict(lower=2, upper=1), dict(age_s=-1), dict(lower=0, upper=float("nan"))):
            values = dict(status=QualityStatus.VALID, age_s=0, reason="synthetic") | args
            with self.subTest(args=args), self.assertRaises(ContractError):
                Quality(**values)
        for changes in (dict(physical_id=""), dict(source_id="x" * 129), dict(source_id="x\n"),
                        dict(evidence_ids=["mutable"]), dict(evidence_ids=("a", "a")),
                        dict(source_sequence=True), dict(source_sequence=2**63), dict(value=10**1000),
                        dict(value=-274, unit=Unit.CELSIUS), dict(signed=1), dict(quality=None)):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                reading(**changes)
        with self.assertRaises(ContractError):
            Provenance(kind=SourceKind.DIRECT, independent=1)
        with self.assertRaises(ContractError):
            replace(policy(), strict_windows=tuple(reversed(policy().strict_windows)) * 2)

    def test_permit_flag_and_reason_cannot_contradict_each_other(self):
        for allowed, reason in ((False, Reason.ALLOWED), (True, Reason.GRID), (False, Reason.MIN_ON)):
            with self.assertRaises(ContractError):
                HeatPermit(allowed=allowed, reason=reason, snapshot_id="synthetic", revisions=snapshot().revisions)

    def test_deep_large_unknown_or_malformed_payload_does_not_echo_its_content(self):
        payload = json.loads(to_json(reading()))
        for invalid in ("[" * 1500, "secret-marker", 1, b"invalid", "\ud800"):
            with self.subTest(kind=type(invalid).__name__), self.assertRaises(ContractError) as result:
                from_json(invalid)
            self.assertNotIn("secret-marker", str(result.exception))
        payload["data"]["evidence_ids"] = ["x"] * 4097
        with self.assertRaises(ContractError):
            from_json(json.dumps(payload))
        with self.assertRaises(ContractError):
            to_json(object())
