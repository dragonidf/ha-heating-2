"""T-D01: strict versioned JSON with no I/O or hidden coercions."""
import json
import unittest
from dataclasses import replace

from packages.contracts import ContractError, Missing, Unit, from_json, to_json
from tests.contracts.test_plans import plan, snapshot
from tests.contracts.test_readings import reading


class CodecTests(unittest.TestCase):
    def test_nested_roundtrip_is_canonical_and_immutable(self):
        for value in (reading(), reading(False, Unit.BOOLEAN), reading(None),
                      plan(), snapshot()):
            payload = to_json(value)
            result = from_json(payload, type(value))
            self.assertEqual(result, value)
            self.assertEqual(to_json(result), payload)

    def test_absent_null_and_zero_optional_fields_roundtrip_separately(self):
        values = [reading(), reading(source_sequence=None), reading(source_sequence=0)]
        encoded = [to_json(r) for r in values]
        self.assertEqual(len(set(encoded)), 3)
        self.assertNotIn("source_sequence", json.loads(encoded[0])["data"])
        self.assertIs(from_json(encoded[0]).source_sequence, Missing.VALUE)
        self.assertIsNone(from_json(encoded[1]).source_sequence)
        self.assertEqual(from_json(encoded[2]).source_sequence, 0)

    def test_unknown_fields_missing_required_types_and_versions_are_rejected(self):
        base = json.loads(to_json(reading()))
        mutations = [dict(base, schema_version={"major": 2, "minor": 0}),
                     dict(base, schema_version={"major": True, "minor": 0}),
                     dict(base, type="Unknown"), dict(base, extra=1),
                     dict(base, data=base["data"] | {"unit": "F"}),
                     dict(base, data=base["data"] | {"source_sequence": False}),
                     dict(base, data=base["data"] | {"source_sequence": "absent"}),
                     dict(base, data=base["data"] | {"value": True}),
                     dict(base, data={k: v for k, v in base["data"].items() if k != "value"})]
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(ContractError):
                from_json(json.dumps(value))

    def test_duplicate_keys_nonfinite_corrupt_and_oversized_payloads_are_rejected(self):
        for payload in ('{"type":"Reading","type":"Plan"}', 'NaN', 'Infinity',
                        '{', '[]', 'null', '"wrong"', ' ' * (256 * 1024 + 1)):
            with self.subTest(payload=payload[:50]), self.assertRaises(ContractError):
                from_json(payload)
        with self.assertRaises(ContractError):
            from_json(to_json(reading()), type(plan()))

    def test_nested_structures_are_validated_not_just_the_envelope(self):
        body = json.loads(to_json(plan()))
        body["data"]["segments"][0]["end"] = float("inf")
        with self.assertRaises(ContractError):
            from_json(json.dumps(body))
