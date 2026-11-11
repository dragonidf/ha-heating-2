"""Safety regressions for a read-only KWS HA-state seam (synthetic IDs)."""
from dataclasses import replace
import unittest

from packages.contracts import Clock, ContractError, QualityStatus, SourceKind
from packages.ha_native.kws import project_kws
from packages.ha_native.kws_passive import (
    KWSHAChannel, KWSHAState, KWSPassiveStateBridge,
)

ROLES = (
    ("active_power", "L1", "kW", 0.0),
    ("active_power", "L2", "kW", 0.0),
    ("active_power", "L3", "kW", 0.0),
    ("imported_energy", "total", "kWh", 100.0),
)


def clock(at=100):
    return Clock(utc=at, monotonic=at, boot_id="synthetic.kws.passive.boot")


def bindings():
    return tuple(KWSHAChannel(f"synthetic.ha.{phase}", "synthetic.private.device",
                              quantity, phase, unit)
                 for quantity, phase, unit, _ in ROLES)


def state(phase, unit, value, at=99, **changes):
    values = dict(entity_id=f"synthetic.ha.{phase}", device_id="synthetic.private.device",
                  integration="tuya_local", unit=unit, value=value,
                  last_changed=at-10, last_updated=at-2, last_reported=at,
                  registry_verified=True, available=True, restored=False)
    values.update(changes)
    return KWSHAState(**values)


def populated(values=(0.0, 0.0, 0.0, 100.0), at=99):
    bridge = KWSPassiveStateBridge(bindings())
    for (quantity, phase, unit, _), value in zip(ROLES, values):
        assert bridge.observe(state(phase, unit, value, at=at), clock(at+1))
    return bridge


class PassiveKWSStateTests(unittest.TestCase):
    def test_no_state_or_zero_state_can_authorize_electrical_off(self):
        empty = KWSPassiveStateBridge(bindings())
        self.assertIsNone(project_kws(empty.shadow_frame(clock()), clock()).power.kw)
        bridge = populated()
        f = bridge.shadow_frame(clock())
        self.assertEqual(len(f.readings), 4)
        self.assertEqual(tuple(r.value for r in f.readings), (0.0, 0.0, 0.0, 100.0))
        self.assertTrue(all(r.sequence == 0 and not r.heartbeat_verified
                            and r.origin is SourceKind.HELD
                            and r.quality is QualityStatus.MISSING
                            and r.online is None for r in f.readings))
        result = project_kws(f, clock())
        self.assertIsNone(result.power.kw)
        self.assertIsNone(result.counter)
        self.assertEqual(result.stage, "UNKNOWN")
        self.assertFalse(bridge.physical_commands_enabled)

    def test_fresh_nonzero_ha_states_still_are_not_raw_device_reports(self):
        bridge = populated((1.8, 1.6, 2.7, 101.4))
        f = bridge.shadow_frame(clock())
        self.assertAlmostEqual(sum(r.value for r in f.readings[:3]), 6.1)
        state_result = project_kws(f, clock())
        self.assertIsNone(state_result.power.kw)
        self.assertEqual(state_result.stage, "UNKNOWN")
        view = bridge.view(clock())
        self.assertIsNone(view["power_w"])
        self.assertIsNone(view["energy_kwh"])
        self.assertFalse(view["physical_authority"])
        self.assertEqual(view["reason"], "no_verified_raw_kws_sequence_or_measurement_time")
        self.assertEqual([row["ha_report_age_s"] for row in view["channels"]], [1, 1, 1, 1])

    def test_unchanged_zero_and_new_ha_report_do_not_forge_sample_sequence(self):
        bridge = populated()
        self.assertFalse(bridge.observe(state("L1", "kW", 0, at=99), clock(101)))
        self.assertTrue(bridge.observe(state("L1", "kW", 0, at=105), clock(106)))
        f = bridge.shadow_frame(clock(106))
        self.assertEqual(next(r for r in f.readings if r.phase == "L1").sequence, 0)
        self.assertIsNone(project_kws(f, clock(106)).power.kw)

    def test_stale_unchanged_sibling_stays_unqualified_when_other_phase_reports(self):
        bridge = populated(at=99)
        self.assertTrue(bridge.observe(state("L2", "kW", 0.06, at=10000), clock(10001)))
        view = bridge.view(clock(10001))
        self.assertGreater(view["channels"][0]["ha_report_age_s"], 9000)
        self.assertEqual(view["channels"][1]["last_known"], 0.06)
        self.assertEqual(view["stage"], "UNKNOWN")
        self.assertIsNone(project_kws(bridge.shadow_frame(clock(10001)), clock(10001)).power.kw)

    def test_cloud_same_physical_device_is_not_an_independent_fallback(self):
        bridge = populated()
        bad = state("L1", "kW", 3.0, at=101, integration="tuya")
        self.assertFalse(bridge.observe(bad, clock(102)))
        self.assertFalse(bridge.observe(replace(bad, integration="tuya_cloud"), clock(102)))
        self.assertFalse(bridge.observe(state("L1", "kW", 3.0, at=101,
                                              device_id="synthetic.other.device"), clock(102)))
        self.assertEqual(bridge.view(clock(102))["channels"][0]["last_known"], 0.0)

    def test_missing_unavailable_and_unregistered_states_are_not_measurements(self):
        bridge = KWSPassiveStateBridge(bindings())
        self.assertFalse(bridge.observe(state("L1", "kW", 1,
                                             registry_verified=False), clock()))
        self.assertFalse(bridge.observe(state("L1", "kW", 1, restored=True), clock()))
        self.assertTrue(bridge.observe(state("L1", "kW", None,
                                            available=False), clock()))
        self.assertIsNone(bridge.view(clock())["channels"][0]["last_known"])
        self.assertIsNone(project_kws(bridge.shadow_frame(clock()), clock()).power.kw)

    def test_invalid_roles_source_chronology_and_unsafe_activation_rejected(self):
        with self.assertRaises(ContractError):
            KWSPassiveStateBridge(bindings(), physical_commands_enabled=True)
        with self.assertRaises(ContractError):
            KWSPassiveStateBridge(bindings()[:3])
        with self.assertRaises(ContractError):
            KWSPassiveStateBridge((*bindings()[:3], bindings()[0]))
        with self.assertRaises(ContractError):
            KWSPassiveStateBridge((*bindings()[:3],
                                   replace(bindings()[3], device_id="synthetic.other")))
        with self.assertRaises(ContractError):
            KWSHAChannel("x", "y", "active_power", "total", "kW")
        with self.assertRaises(ContractError):
            KWSHAChannel("x", "y", "active_power", "L1", "W")
        for changes in (dict(last_changed=101), dict(last_updated=101),
                        dict(value=-1), dict(value=float("nan"))):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                state("L1", "kW", 0, **changes)
        bridge = KWSPassiveStateBridge(bindings())
        self.assertFalse(bridge.observe(state("L1", "kW", 0, at=101), clock(100)))


if __name__ == "__main__":
    unittest.main()
