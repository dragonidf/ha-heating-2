"""P0 real-HA shadow stays read-only, lightweight and zero-tolerant."""
import ast
import json
from pathlib import Path
import runpy
import unittest

ROOT = Path("releases/ha_v2/custom_components/heating_ai_v2")
module = runpy.run_path(str(ROOT / "telemetry.py"))
snapshot = module["snapshot"]
ROLES = module["ROLES"]


def frame():
    return {
        "thermostat": {"state": "heat", "unit": "", "last_reported": "today"},
        "room": {"state": "21.6", "unit": "°C", "last_reported": "today"},
        "grid": {"state": "Наявна мережа", "unit": "", "last_reported": "today"},
        **{r: {"state": "230", "unit": "V", "last_reported": "today"}
           for r in ("voltage_l1", "voltage_l2", "voltage_l3")},
        **{r: {"state": "0.0", "unit": "kW", "last_reported": "hours_ago"}
           for r in ("kws_l1", "kws_l2", "kws_l3")},
        "kws_energy": {"state": "160.75", "unit": "kWh", "last_reported": "today"},
    }


class ReadOnlyShadowTests(unittest.TestCase):
    def test_one_well_formed_real_ha_mapping_has_exact_required_roles(self):
        self.assertEqual(len(ROLES), 10)
        self.assertEqual(len(set(ROLES)), 10)
        self.assertEqual(set(frame()), set(ROLES))

    def test_unchanged_zero_is_last_known_not_stale_failure(self):
        v = snapshot(frame())
        self.assertEqual(v["kws_total_kw_last_known"], 0.0)
        self.assertEqual(v["kws_phases_kw_last_known"]["kws_l1"], 0.0)
        self.assertEqual(v["ha_last_reported"]["kws_l1"], "hours_ago")
        self.assertEqual(v["kws_value_semantics"], "HA_last_known_not_verified_raw_sample")
        self.assertEqual(v["mode"], "SHADOW")
        self.assertFalse(v["commands_enabled"])
        self.assertFalse(v["physical_ack"])
        self.assertIsNone(v["contacts_open"])
        self.assertEqual(v["kws_stage"], "UNCALIBRATED")

    def test_three_direct_phase_values_are_summed_without_helpers(self):
        f = frame()
        f["kws_l1"]["state"], f["kws_l2"]["state"], f["kws_l3"]["state"] = "1.1", "2.1", "3.02"
        v = snapshot(f)
        self.assertEqual(v["kws_total_kw_last_known"], 6.22)
        self.assertEqual(v["kws_energy_kwh_last_known"], 160.75)

    def test_single_missing_or_unavailable_phase_does_not_become_zero(self):
        for state in ("unavailable", "unknown", None, "-1", "nan", "inf"):
            with self.subTest(state=state):
                f = frame()
                f["kws_l2"]["state"] = state
                self.assertIsNone(snapshot(f)["kws_total_kw_last_known"])

    def test_wrong_units_never_blend_watts_and_kilowatts(self):
        f = frame()
        f["kws_l3"]["unit"] = "W"
        self.assertIsNone(snapshot(f)["kws_total_kw_last_known"])
        f = frame()
        f["kws_energy"]["unit"] = "W"
        self.assertIsNone(snapshot(f)["kws_energy_kwh_last_known"])

    def test_empty_states_and_unknown_grid_never_grant_heat(self):
        v = snapshot({})
        self.assertEqual(v["unavailable_sources"], list(ROLES))
        self.assertIsNone(v["grid_last_known"])
        self.assertIsNone(v["room_c_last_known"])
        self.assertIsNone(v["kws_total_kw_last_known"])
        self.assertFalse(v["commands_enabled"])

    def test_grid_and_voltage_are_display_only_even_if_all_good(self):
        f = frame()
        v = snapshot(f)
        self.assertTrue(v["grid_last_known"])
        self.assertEqual(v["voltages_v_last_known"]["voltage_l1"], 230)
        self.assertFalse(v["commands_enabled"])
        f["grid"]["state"] = "Відсутня мережа"
        self.assertFalse(snapshot(f)["grid_last_known"])
        # The upstream meter may retain a non-zero voltage even while utility is absent.
        self.assertEqual(snapshot(f)["voltages_v_last_known"]["voltage_l1"], 230)
        f["grid"]["state"] = "unavailable"
        self.assertIsNone(snapshot(f)["grid_last_known"])
        f["grid"]["state"] = "on"  # A Boolean state is not this input_select contract.
        self.assertIsNone(snapshot(f)["grid_last_known"])
        self.assertFalse(snapshot(f)["commands_enabled"])

    def test_fireplace_fan_modes_and_ventilation_are_read_only(self):
        f = frame()
        f.update({
            "fireplace": {"state": "27.4", "unit": "°C", "last_reported": "today"},
            "circulation": {"state": "off", "unit": "", "last_reported": "today",
                            "attributes": {"percentage": 42}},
            "fan_mode": {"state": "Зупинити", "unit": "", "last_reported": "today"},
            "fan_night": {"state": "38", "unit": "%", "last_reported": "today"},
            "fan_standard": {"state": "42", "unit": "%", "last_reported": "today"},
            "fan_intense": {"state": "45", "unit": "%", "last_reported": "today"},
            "fan_backup": {"state": "on", "unit": "", "last_reported": "today"},
            "fan_control": {"state": "on", "unit": "", "last_reported": "today"},
            "recuperator": {"state": "unavailable", "unit": "", "last_reported": "today"},
            "bath": {"state": "off", "unit": "", "last_reported": "today"},
        })
        view = snapshot(f)
        self.assertAlmostEqual(view["fireplace_delta_c_last_known"], 5.8)
        self.assertEqual(view["circulation_last_known"], "off")
        self.assertEqual(view["fan_mode_last_known"], "Зупинити")
        self.assertEqual(view["fan_speed_percent_last_known"], {
            "fan_night": 38., "fan_standard": 42., "fan_intense": 45.,
        })
        self.assertTrue(view["fan_backup_verified_last_known"])
        self.assertIsNone(view["ventilation_last_known"]["recuperator"])
        self.assertIs(view["ventilation_last_known"]["bath"], False)
        self.assertFalse(view["fireplace_heat_proven"])
        self.assertFalse(view["fan_commands_enabled"])

    def test_missing_fireplace_never_invents_flame_or_fan_demand(self):
        view = snapshot(frame())
        self.assertIsNone(view["fireplace_delta_c_last_known"])
        self.assertIsNone(view["fan_mode_last_known"])
        self.assertIsNone(view["ventilation_last_known"]["bath"])
        self.assertFalse(view["fan_commands_enabled"])

    def test_no_services_transports_automation_or_actuator_code_in_live_shadow(self):
        forbidden = {"async_call", "call_service", "set_temperature", "set_hvac_mode",
                     "turn_on", "turn_off", "async_press", "async_turn_on", "async_turn_off"}
        for file in ROOT.glob("*.py"):
            tree = ast.parse(file.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(node.attr, "services", str(file))
                if isinstance(node, ast.Call):
                    name = (node.func.attr if isinstance(node.func, ast.Attribute)
                            else node.func.id if isinstance(node.func, ast.Name) else "")
                    self.assertNotIn(name, forbidden, str(file))
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["domain"], "heating_ai_v2")
        self.assertEqual(manifest["requirements"], [])
        self.assertTrue(manifest["single_config_entry"])
        self.assertFalse((ROOT / "switch.py").exists())
        self.assertFalse((ROOT / "climate.py").exists())

    def test_legacy_synthetic_package_remains_separate(self):
        self.assertTrue(Path("ha_sdk/heating_ai/manifest.json").is_file())
        self.assertFalse((ROOT / "telemetry.py").read_text().find("group_balance") >= 0)
        self.assertFalse((ROOT / "telemetry.py").read_text().find("fixed_6") >= 0)


if __name__ == "__main__":
    unittest.main()
