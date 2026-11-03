"""Strict data-only control/receipt/one-shot boundaries, no execution."""
import unittest
from dataclasses import FrozenInstanceError, fields, replace

from packages.contracts import (
    Action, CommandReceipt, ContractError, ControlState, EventKind, HeatPermit,
    OneShot, OneShotKind, OneShotOutcome, Reason, ReceiptStage, from_json, to_json,
)
from packages.control import reduce
from tests.fixtures.synthetic import clock, event, plan, policy, reading, snapshot, state
from tests.unit.test_ownership import receipt


class ControlRecordTests(unittest.TestCase):
    def samples(self):
        decision = reduce(state(), event(), snapshot(), policy(), clock())
        one_shot = OneShot(intent_id="synthetic.one-shot", kind=OneShotKind.HEAT_AFTER_GRID_RESTORE,
                           created_at=90, expires_at=200, armed_grid_epoch=4,
                           consumed_at=None, outcome=OneShotOutcome.PENDING)
        return (policy(), state(), event(), decision, decision.permit, decision.intents[0],
                receipt(decision.intents[0]), one_shot)

    def test_every_control_record_roundtrips_as_a_frozen_value(self):
        for record in self.samples():
            with self.subTest(record=type(record).__name__):
                self.assertEqual(from_json(to_json(record), type(record)), record)
                with self.assertRaises(FrozenInstanceError):
                    setattr(record, fields(record)[0].name, None)

    def test_no_one_shot_off_reinterpretation_or_global_cap_exists(self):
        one_shot = self.samples()[-1]
        self.assertEqual(one_shot.kind, OneShotKind.HEAT_AFTER_GRID_RESTORE)
        self.assertFalse(any("cap" in f.name or "180" in f.name for f in fields(type(policy()))))
        for change in (dict(kind="off_after_grid_restore"),
                       dict(outcome=OneShotOutcome.CONSUMED),
                       dict(consumed_at=100), dict(expires_at=89)):
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(one_shot, **change)
        unknown = replace(one_shot, consumed_at=100, outcome=OneShotOutcome.UNKNOWN)
        self.assertEqual(from_json(to_json(unknown)), unknown)

    def test_stage_timestamps_and_external_evidence_are_not_optional_claims(self):
        r = self.samples()[6]
        for change in (dict(stage=ReceiptStage.PREPARED), dict(stage=ReceiptStage.SENT),
                       dict(stage=ReceiptStage.ACKNOWLEDGED),
                       dict(stage=ReceiptStage.PHYSICAL_EVIDENCE),
                       dict(device_echo_at=1), dict(physical_effect_at=100)):
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(r, **change)

    def test_structural_invalid_direct_construction_is_rejected_too(self):
        for call in (lambda: policy(armed=1), lambda: policy(intent_ttl_s=0),
                     lambda: policy(min_on_s=-1), lambda: policy(strict_windows=[]),
                     lambda: state(plan="not-a-plan"), lambda: event(plan="not-a-plan"),
                     lambda: event(kind=EventKind.PLAN), lambda: event(kind=EventKind.OWN_ECHO),
                     lambda: event(receipt="not-a-receipt"), lambda: state(owner_epoch=False)):
            with self.assertRaises(ContractError):
                call()
