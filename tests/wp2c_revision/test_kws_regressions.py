"""Fictional KWS source-role and asymmetric transition regression scenarios."""
from dataclasses import replace
import unittest

from packages.contracts import Clock
from packages.ha_native.kws import (
    KWSFrame, KWSReading, project_kws, synthetic_kws_calibration,
)
from packages.ha_native.meter import SyntheticMeterVerification


def clock(at):
    return Clock(utc=at, monotonic=at, boot_id='synthetic.kws.revision.boot')


def calibration():
    return synthetic_kws_calibration()


def signature(near_total_w):
    return min(calibration().signatures, key=lambda s: abs(sum(s.phase_w) - near_total_w))


def frame(at, phase_w, *, provider='tuya_local', counter=10):
    readings = tuple(KWSReading(
        source_id=f'synthetic.kws.revision.power.{phase}', physical_id='synthetic.kws.revision',
        phase=phase, quantity='active_power', value=watts / 1000, unit='kW',
        last_reported=at, received_at=at, sequence=int(at), online=True,
        heartbeat_verified=True,
    ) for phase, watts in zip(('L1', 'L2', 'L3'), phase_w))
    readings += (KWSReading(
        source_id='synthetic.kws.revision.energy.total', physical_id='synthetic.kws.revision',
        phase='total', quantity='imported_energy', value=counter, unit='kWh',
        last_reported=at, received_at=at, sequence=int(at), online=True,
        heartbeat_verified=True,
    ),)
    verification = SyntheticMeterVerification(
        evidence_ids=('synthetic.kws.revision.fixture-proof',), boiler_only=True,
        auxiliaries_included=True, phase_mapping=True, import_direction=True, counter_accuracy=True,
    )
    return KWSFrame(readings=readings, provider=provider, meter_id='synthetic.kws.revision',
                    verification=verification, calibration=calibration(), online=True)


class KWSRoleRegressions(unittest.TestCase):
    def stable(self, near_total_w):
        stage = signature(near_total_w)
        first = project_kws(frame(100, stage.phase_w), clock(100))
        state = project_kws(frame(110, stage.phase_w), clock(110), first)
        self.assertEqual(state.stage, stage.stage)
        return state

    def test_cloud_copy_of_the_same_physical_meter_cannot_continue_local_evidence(self):
        local = self.stable(6000)
        self.assertAlmostEqual(local.power.kw, sum(signature(6000).phase_w) / 1000)
        self.assertIsNotNone(local.counter)
        cloud = project_kws(frame(111, signature(6000).phase_w,
                                  provider='tuya_cloud', counter=11), clock(111), local)
        self.assertIsNone(cloud.power.kw)
        self.assertIsNone(cloud.counter)
        self.assertEqual(cloud.stage, 'UNKNOWN')
        self.assertEqual(local.counter.kwh, 10)

    def test_cloud_alias_cannot_enter_a_local_frame_or_skip_local_recovery_dwell(self):
        local = self.stable(6000)
        fresh = frame(111, signature(6000).phase_w)
        mixed = replace(fresh, readings=(replace(fresh.readings[0], provider='tuya_cloud'),
                                         *fresh.readings[1:]))
        rejected = project_kws(mixed, clock(111), local)
        self.assertIsNone(rejected.power.kw)
        self.assertEqual(rejected.stage, 'UNKNOWN')
        recovering = project_kws(frame(112, signature(6000).phase_w), clock(112), rejected)
        self.assertEqual(recovering.stage, 'UNKNOWN')
        recovered = project_kws(frame(122, signature(6000).phase_w), clock(122), recovering)
        self.assertEqual(recovered.stage, signature(6000).stage)

    def test_same_total_with_permuted_asymmetric_phases_preserves_stage(self):
        local = self.stable(6000)
        watts = signature(6000).phase_w
        self.assertEqual(sum(watts), sum(reversed(watts)))
        contradictory = project_kws(frame(111, tuple(reversed(watts))), clock(111), local)
        self.assertEqual(contradictory.stage, signature(6000).stage)
        self.assertAlmostEqual(contradictory.power.kw, local.power.kw)

    def test_short_high_stage_spike_then_return_requires_fresh_stable_evidence(self):
        local = self.stable(3000)
        high = signature(9000)
        low = signature(3000)
        transient = project_kws(frame(111, high.phase_w), clock(111), local)
        self.assertNotEqual(transient.stage, high.stage)
        returned = project_kws(frame(112, low.phase_w), clock(112), transient)
        self.assertNotEqual(returned.stage, high.stage)
        sustained = project_kws(frame(122, low.phase_w), clock(122), returned)
        self.assertEqual(sustained.stage, low.stage)

    def test_partial_power_frame_never_becomes_zero_while_total_counter_is_cached(self):
        local = self.stable(6000)
        fresh = frame(111, signature(6000).phase_w)
        missing = replace(fresh, readings=tuple(r for r in fresh.readings if r.phase != 'L2'))
        state = project_kws(missing, clock(111), local)
        self.assertIsNone(state.power.kw)
        self.assertEqual(state.stage, 'UNKNOWN')

    def test_six_kw_rotating_allocations_share_aggregate_band_and_dwell(self):
        first = project_kws(frame(100, (1500, 1500, 3000)), clock(100))
        self.assertEqual(first.stage, 'UNKNOWN')
        self.assertAlmostEqual(first.power.kw, 6)
        pending = project_kws(frame(109, (3000, 1500, 1500)), clock(109), first)
        self.assertEqual(pending.stage, 'UNKNOWN')
        stable = project_kws(frame(110, (1500, 3000, 1500)), clock(110), pending)
        self.assertEqual(stable.stage, '~6kW')
        self.assertAlmostEqual(stable.power.kw, 6)

    def test_three_and_nine_kw_aggregate_modes_with_rotating_phases(self):
        for watts, stage in (((1000, 1000, 1000), '~3kW'), ((3000, 3000, 3000), '~9kW')):
            with self.subTest(stage=stage):
                first = project_kws(frame(100, watts), clock(100))
                final = project_kws(frame(110, tuple(reversed(watts))), clock(110), first)
                self.assertEqual(final.stage, stage)
                self.assertAlmostEqual(final.power.kw, sum(watts) / 1000)

    def test_valid_intermediate_watts_remain_unknown_and_reset_dwell(self):
        first = project_kws(frame(100, (1500, 1500, 3000)), clock(100))
        middle = project_kws(frame(105, (1500, 1500, 1500)), clock(105), first)
        self.assertAlmostEqual(middle.power.kw, 4.5)
        self.assertEqual(middle.stage, 'UNKNOWN')
        returned = project_kws(frame(109, (3000, 1500, 1500)), clock(109), middle)
        self.assertEqual(returned.stage, 'UNKNOWN')
        pending = project_kws(frame(118, (1500, 3000, 1500)), clock(118), returned)
        self.assertEqual(pending.stage, 'UNKNOWN')
        final = project_kws(frame(119, (1500, 1500, 3000)), clock(119), pending)
        self.assertEqual(final.stage, '~6kW')

    def test_stale_off_and_pump_readings_never_authorize_a_stage(self):
        for watts in ((0, 0, 0), (40, 20, 10)):
            with self.subTest(watts=watts):
                cached = frame(100, watts)
                first = project_kws(cached, clock(100))
                stable = project_kws(cached, clock(110), first)
                self.assertIn(stable.stage, ('OFF', 'PUMP_ONLY'))
                stale = project_kws(cached, clock(131), stable)
                self.assertIsNone(stale.power.kw)
                self.assertEqual(stale.stage, 'UNKNOWN')
