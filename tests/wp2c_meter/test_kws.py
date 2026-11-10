"""Fictional local KWS source roles, counter coverage and empirical stages."""
from dataclasses import replace
import unittest

from packages.contracts import Clock, ContractError, QualityStatus
from packages.ha_native.kws import (
    KWSFrame, KWSReading, StageCalibration, StageSignature, decode_kws_frame,
    kws_counter_energy, kws_view, project_kws, synthetic_kws_calibration,
)
from packages.ha_native.meter import SyntheticMeterVerification


def clock(at=100, mono=None, boot="synthetic.kws.boot"):
    return Clock(utc=at, monotonic=at if mono is None else mono, boot_id=boot)


def frame(at=100, watts=(1100, 1800, 3200), kwh=10, phase_kwh=None, **changes):
    def r(phase, quantity, value):
        return KWSReading(f"synthetic.kws.{quantity}.{phase}", "synthetic.kws", phase,
                          quantity, value, "kW" if quantity == "active_power" else "kWh",
                          at, at, int(at), online=True, heartbeat_verified=True)
    readings = tuple(r(p, "active_power", v / 1000) for p, v in zip(("L1", "L2", "L3"), watts))
    if kwh is not None:
        readings += (r("total", "imported_energy", kwh),)
    if phase_kwh is not None:
        readings += tuple(r(p, "imported_energy", v) for p, v in zip(("L1", "L2", "L3"), phase_kwh))
    verification = SyntheticMeterVerification(("synthetic.kws.proof",), True, True, True, True, True)
    values = dict(readings=readings, provider="tuya_local", meter_id="synthetic.kws",
                  verification=verification, calibration=synthetic_kws_calibration(), online=True)
    values.update(changes)
    return KWSFrame(**values)


class KWSTests(unittest.TestCase):
    def test_local_phase_kw_normalizes_to_w_and_one_total_counter(self):
        state = project_kws(frame(phase_kwh=(1, 2, 7)), clock())
        self.assertEqual(state.power.raw_w, 6100)
        self.assertAlmostEqual(state.power.kw, 6.1)
        self.assertEqual(state.counter.kwh, 10)
        view = kws_view(state)
        self.assertEqual(view["total_imported_kwh"], 10)
        self.assertEqual(view["source_provider"], "tuya_local_kws")
        self.assertEqual(view["cloud_duplicate_policy"], "excluded_no_fallback")
        self.assertFalse(view["physical_authority"])
        self.assertIsNone(view["physical_heat"])

    def test_no_cloud_fallback_or_mixed_cloud_alias_privilege(self):
        for f in (frame(provider="tuya_cloud"), frame(verification=None), frame(online=False),
                  frame(readings=tuple(replace(r, provider="tuya_cloud") for r in frame().readings))):
            state = project_kws(f, clock())
            self.assertIsNone(state.power.kw)
            self.assertIsNone(state.counter)
            self.assertEqual(state.stage, "UNKNOWN")

    def test_each_empirical_asymmetric_stage_requires_sustained_dwell(self):
        for signature in synthetic_kws_calibration().signatures:
            first = project_kws(frame(watts=signature.phase_w), clock())
            self.assertEqual(first.stage, "UNKNOWN")
            second = project_kws(frame(109, signature.phase_w), clock(109), first)
            self.assertEqual(second.stage, "UNKNOWN")
            final = project_kws(frame(110, signature.phase_w), clock(110), second)
            self.assertEqual(final.stage, signature.stage)

    def test_missing_calibration_and_ambiguous_signatures_do_not_round_total(self):
        state = project_kws(frame(calibration=None), clock())
        self.assertEqual(state.stage, "UNKNOWN")
        self.assertAlmostEqual(state.power.kw, 6.1)
        signatures = (StageSignature("~3kW", (1100, 1800, 3200), (10, 10, 10)),
                      StageSignature("~6kW", (1100, 1800, 3200), (10, 10, 10)))
        calibration = StageCalibration(signatures=signatures, verified=True,
                                       evidence_id="synthetic.overlap", minimum_dwell_s=0)
        self.assertEqual(project_kws(frame(calibration=calibration), clock()).stage, "UNKNOWN")

    def test_phase_stale_skew_unavailable_and_future_do_not_become_zero(self):
        for index in range(3):
            for changes in (dict(value=None), dict(last_reported=60), dict(last_reported=94),
                            dict(last_reported=101, received_at=101), dict(online=None),
                            dict(heartbeat_verified=False), dict(quality=QualityStatus.ESTIMATED)):
                readings = list(frame().readings); readings[index] = replace(readings[index], **changes)
                state = project_kws(frame(readings=tuple(readings)), clock())
                self.assertIsNone(state.power.kw, changes)
                self.assertEqual(state.stage, "UNKNOWN")

    def test_idle_and_frozen_utc_age_expire_and_restart_resets_stage(self):
        first = project_kws(frame(), clock())
        ready = project_kws(frame(110), clock(110), first)
        self.assertEqual(ready.stage, "~6kW")
        self.assertEqual(project_kws(frame(110), clock(141), ready).stage, "UNKNOWN")
        self.assertEqual(project_kws(frame(110), clock(110, mono=141), ready).stage, "UNKNOWN")
        self.assertEqual(project_kws(frame(111), clock(111, boot="synthetic.new"), ready).stage, "UNKNOWN")
        self.assertEqual(project_kws(frame(), clock(100, mono=99), ready).stage, "UNKNOWN")

    def test_hysteresis_holds_stage_but_transition_spike_does_not_prove_next(self):
        policy = replace(synthetic_kws_calibration(), minimum_dwell_s=0)
        a = project_kws(frame(calibration=policy), clock())
        self.assertEqual(a.stage, "~6kW")
        b = project_kws(frame(101, (1235, 1800, 3200), calibration=policy), clock(101), a)
        self.assertEqual(b.stage, "~6kW")
        c = project_kws(frame(102, (1246, 1800, 3200), calibration=policy), clock(102), b)
        self.assertEqual(c.stage, "UNKNOWN")

    def test_unchanged_counter_needs_a_new_qualified_heartbeat_not_cached_value(self):
        for changes in (dict(heartbeat_verified=False), dict(last_reported=60), dict(online=False)):
            readings = (*frame().readings[:-1], replace(frame().readings[-1], **changes))
            self.assertIsNone(project_kws(frame(readings=readings), clock()).counter)
        result = kws_counter_energy(frame(), frame(110), clock(110), "synthetic.energy")
        self.assertEqual(result.kwh, 0)
        cached = kws_counter_energy(frame(), frame(200), clock(200), "synthetic.energy")
        self.assertIsNone(cached.kwh)

    def test_total_only_ledger_uses_phase_counters_as_delta_crosscheck(self):
        left = frame(phase_kwh=(1, 2, 7))
        right = frame(110, kwh=10.02, phase_kwh=(1.005, 2.005, 7.01))
        good = kws_counter_energy(left, right, clock(110), "synthetic.energy")
        self.assertAlmostEqual(good.kwh, 0.02)
        self.assertIn("synthetic.kws.imported_energy.total", good.sources)
        bad = kws_counter_energy(left, frame(110, kwh=10.02, phase_kwh=(1, 2, 7.1)),
                                 clock(110), "synthetic.energy")
        self.assertIsNone(bad.kwh)
        self.assertIn("phase_counter", bad.method)

    def test_reset_jump_cloud_and_missing_counter_fail_closed(self):
        for right in (frame(110, kwh=1), frame(110, kwh=20), frame(110, kwh=None),
                      frame(110, provider="tuya_cloud")):
            self.assertIsNone(kws_counter_energy(frame(), right, clock(110), "synthetic.energy").kwh)

    def test_strict_typed_schema_and_json_roles(self):
        for changes in (dict(unit="W"), dict(phase="L4"), dict(value=True), dict(value=-1),
                        dict(physical_id="device.private"), dict(heartbeat_verified=1)):
            with self.assertRaises(ContractError):
                replace(frame().readings[0], **changes)
        with self.assertRaises(ContractError):
            frame(readings=(frame().readings[0], frame().readings[0]))
        for raw in (None, {"readings": [], "service": "arbitrary"}, {"readings": [None]}):
            with self.assertRaises(ContractError):
                decode_kws_frame(raw)
        f = decode_kws_frame({"readings": []})
        self.assertEqual(project_kws(f, clock()).stage, "UNKNOWN")
