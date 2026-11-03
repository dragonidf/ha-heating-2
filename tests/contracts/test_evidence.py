import unittest
from dataclasses import replace

from packages.contracts import ContractError, QualityStatus, ReceiptStage, SourceKind
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, policy, reading, snapshot, state
from tests.unit.test_ownership import receipt


class EvidenceTests(unittest.TestCase):
    def test_derived_missing_stale_and_alias_evidence_cannot_claim_physical_effect(self):
        intent = reduce(state(), event(), snapshot(), policy(), clock()).intents[0]
        base = reading()
        derived = replace(base, provenance=replace(base.provenance, kind=SourceKind.DERIVED, independent=False))
        stale = replace(base, quality=replace(base.quality, status=QualityStatus.STALE))
        for evidence in ((derived,), (reading(None),), (stale,), (base, replace(base, source_id="synthetic.alias"))):
            with self.subTest(evidence=evidence), self.assertRaises(ContractError):
                receipt(intent, stage=ReceiptStage.PHYSICAL_EVIDENCE, physical_effect_at=100, evidence=evidence)

    def test_external_independent_evidence_is_preserved_without_synthesizing_success(self):
        intent = reduce(state(), event(), snapshot(), policy(), clock()).intents[0]
        external = receipt(intent, stage=ReceiptStage.PHYSICAL_EVIDENCE,
                           physical_effect_at=100, evidence=(reading(),))
        self.assertEqual(external.evidence, (reading(),))
        self.assertFalse(hasattr(external, "physical_success"))
