import unittest
from dataclasses import replace
from packages.contracts import ContractError, TimeWindow, Unit, Action
from packages.planner import solve, bridge, Curve
from packages.planner.evidence import recommend, CycleBudget, comparison
from packages.thermal import Interval
from tests.fixtures.wp1c import request
from tests.fixtures.synthetic import snapshot, state, policy, clock, event, reading
from packages.control import reduce


class BridgeTests(unittest.TestCase):
    def test_proposal_alone_does_not_authorize_grid_unknown_manual_stop_or_stale_inputs(
        self,
    ):
        req = request()
        at = req.state.at
        p = solve(req)
        plan = bridge(p, req.stamp, at, req.slots[-1].window.end + 1)
        readings = dict(
            room=reading(18, Unit.CELSIUS, observed_at=at, received_at=at),
            return_temperature=reading(
                25, Unit.CELSIUS, observed_at=at, received_at=at
            ),
            thermostat=reading(19, Unit.CELSIUS, observed_at=at, received_at=at),
            grid_actual=reading(True, Unit.BOOLEAN, observed_at=at, received_at=at),
        )
        snap = snapshot(
            boot_id=req.stamp.boot_id,
            input_hash=req.stamp.input_hash,
            revisions=req.stamp.revisions,
            grid_epoch=req.stamp.grid_epoch,
            owner_epoch=req.stamp.owner_epoch,
            captured_at=at,
            **readings
        )
        st = state(
            boot_id=req.stamp.boot_id,
            owner_epoch=req.stamp.owner_epoch,
            plan=plan,
            last_event_at=at - 1,
        )
        ev = event(
            boot_id=req.stamp.boot_id,
            owner_epoch=req.stamp.owner_epoch,
            at=at,
            expires_at=at + 1,
        )
        now = clock(utc=at, boot_id=req.stamp.boot_id)
        pol = policy(strict_windows=req.allowed)
        result = reduce(st, ev, snap, pol, now)
        self.assertIn(Action.HEAT, [i.action for i in result.intents])
        self.assertIsNone(result.state.last_receipt)
        for bad in (
            replace(snap, grid_actual=None),
            replace(
                snap,
                grid_actual=reading(
                    False, Unit.BOOLEAN, observed_at=at, received_at=at
                ),
            ),
            replace(snap, hard_stop=True),
            replace(snap, room=None),
        ):
            result = reduce(st, ev, bad, pol, now)
            self.assertNotIn(Action.HEAT, [i.action for i in result.intents])
        stale = reduce(replace(st, accepted_input_hash="b" * 64), ev, snap, pol, now)
        self.assertNotIn(Action.HEAT, [i.action for i in stale.intents])
        for changed in (replace(pol, armed=False), replace(pol, allow_automatic=False)):
            self.assertNotIn(
                Action.HEAT,
                [i.action for i in reduce(st, ev, snap, changed, now).intents],
            )
        # The exact absolute segment end forbids heating, even while a long compute runs elsewhere.
        end = p.segments[-1].end
        self.assertFalse(plan.heats_at(end))
        self.assertTrue(plan.heats_at(p.segments[0].start))

    def test_recommendations_budget_gaps_and_comparison_preserve_evidence(self):
        req = request()
        p = solve(req)
        r = recommend(p, req)
        self.assertEqual(r.power_kw, p.power_kw)
        self.assertEqual(r.deadline, p.segments[0].start)
        self.assertEqual(r.calibration, "NOT_PARITY_VERIFIED")
        self.assertTrue(r.conditional)
        self.assertIsNone(
            recommend(
                solve(replace(req, armed=False)), replace(req, armed=False)
            ).deadline
        )
        with self.assertRaises(ContractError):
            recommend(p, replace(req, stamp=replace(req.stamp, grid_epoch=2)))
        b = CycleBudget(17.9594, 22.11794, 583.628, 30)
        self.assertAlmostEqual(b.known_remaining_kwh, -4.15854)
        self.assertIsNone(b.deviation_kwh)
        self.assertAlmostEqual(replace(b, unknown_s=0).deviation_kwh, 4.15854)
        curve = Curve(
            "synthetic.original",
            100,
            ((100, Interval(19, 21)), (200, Interval(20, 22))),
            "a" * 64,
            1,
            "synthetic.plan",
            (99,),
        )
        self.assertEqual(comparison(curve, 200, 21), (-1, 1))
        self.assertIsNone(comparison(curve, 201, 21))
        self.assertIsNone(comparison(curve, 200, None))
        with self.assertRaises(ContractError):
            replace(curve, source_issued=(101,))
