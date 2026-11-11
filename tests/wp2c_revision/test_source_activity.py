"""Issue29: independent raw-report liveness and qualified temperature age."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from packages.ha_native.backend import NativeBackend
from packages.ha_native.health import HealthInputs, HealthPolicy
from packages.ha_native.source_activity import DeviceReport, SourceActivity, BINDINGS
from tests.wp2c_backend.test_backend import fixture, observe
from tests.wp2c_backend.test_clock import FakeTime
from tests.wp2c_meter.test_voltage import frame


class SourceActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='heating-wp2c-')
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeTime()
        self.evidence = HealthInputs(owner='synthetic.owner', thermostat_qualified=True, thermostat_age_s=0, plan_ok=True)
        self.backend = NativeBackend(Path(self.tmp.name), fixture(), enabled=True, clock=self.clock,
                                    health_evidence=lambda: self.evidence)
        self.backend.open()
        self.addCleanup(self.backend.close)
        observe(self.backend)

    def report(self, role='temperature', sequence=1, **changes):
        device, entity, unit = BINDINGS[role]
        clock = self.backend.trusted_clock()
        return replace(DeviceReport(role, device, entity, unit, clock.boot_id, sequence,
            clock.utc, clock.utc, clock.utc, 22 if role != 'humidity' else 45,
            mapping_verified=True, report_qualified=True, measurement_qualified=True), **changes)

    def view(self):
        return self.backend.status(True)['source_freshness']

    def test_humidity_only_refreshes_device_not_room_measurement_or_history(self):
        self.assertTrue(self.backend.accept_device_report(self.report()))
        before = self.backend.status(True)
        self.clock.advance(31)
        self.assertTrue(self.backend.accept_device_report(self.report('humidity')))
        self.backend.accept_voltage(frame(self.clock.utc))
        self.backend.flush_stop()
        after = self.backend.status(True)
        self.assertEqual(after['room']['observed'], before['room']['observed'])
        self.assertEqual(after['room']['value'], before['room']['value'])
        self.assertEqual(after['source_freshness']['living_temperature_last_observed'], before['room']['observed'])
        self.assertEqual(after['source_freshness']['temperature_age_s'], 31)
        self.assertEqual(after['source_freshness']['device_age_s'], 0)
        self.assertEqual(after['source_freshness']['device_quality'], 'OK')
        self.assertEqual(after['source_freshness']['temperature_quality'], 'STALE')
        self.assertFalse(after['demand_eligible'])
        self.assertIsNone(after['system_health']['proposal'])
        self.assertEqual(self.backend.fixture['actual'], fixture()['actual'])

    def test_unrelated_devices_ha_republishes_and_unqualified_reports_are_rejected(self):
        report = self.report()
        for bad in [replace(report, device_id='synthetic.other'), replace(report, entity_id='synthetic.derived'),
                    replace(report, mapping_verified=False), replace(report, report_qualified=False),
                    replace(report, boot_id='previous'), replace(report, reported_at=self.clock.utc+1),
                    replace(report, received_at=self.clock.utc+1), replace(report, observed_at=self.clock.utc+1),
                    *[replace(report, origin=o) for o in ('ha_state_write','recorder','derived','ui_poll')]]:
            with self.subTest(bad=bad):
                self.assertFalse(self.backend.accept_device_report(bad))
                self.assertIsNone(self.view()['living_device_last_activity'])
        self.assertTrue(self.backend.accept_device_report(report))
        self.assertFalse(self.backend.accept_device_report(report))
        self.clock.advance(1)
        self.assertFalse(self.backend.accept_device_report(replace(report, sequence=2, received_at=self.clock.utc)))
        self.assertEqual(self.view()['temperature_age_s'], 1)

    def test_genuine_same_value_temperature_report_can_refresh_only_in_synthetic_seam(self):
        self.backend.accept_device_report(self.report())
        self.clock.advance(20)
        self.backend.accept_device_report(self.report(sequence=2))
        self.assertEqual(self.backend.status(True)['room']['value'], 22)
        self.assertEqual(self.view()['temperature_age_s'], 0)
        self.assertEqual(self.view()['living_temperature_last_observed'], self.clock.utc)
        report_id = self.backend._room_report[2]
        self.clock.advance(20)
        self.backend.accept_device_report(self.report(sequence=3, observed_at=self.clock.utc-20))
        self.assertEqual(self.view()['device_age_s'], 0)
        self.assertEqual(self.view()['temperature_age_s'], 20)
        self.assertEqual(self.backend._room_report[2], report_id)

    def test_61_min_boundary_and_two_hour_gap_are_uncertain_not_offline_or_auto(self):
        self.backend.accept_device_report(self.report())
        self.clock.advance(3660)
        self.assertEqual(self.view()['device_quality'], 'OK')
        self.clock.advance(.1)
        self.assertEqual(self.view()['device_quality'], 'DEGRADED')
        self.clock.advance(7200)
        self.backend.accept_voltage(frame(self.clock.utc))
        self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertEqual(state['source_freshness']['device_quality'], 'DEGRADED')
        self.assertEqual(state['system_health']['components'][0]['status'], 'WAITING')
        self.assertIsNone(state['system_health']['proposal'])
        self.assertNotEqual(state['system_health']['mode'], 'AUTO_PROPOSED')
        self.assertFalse(state['demand_eligible'])

    def test_qualified_unavailable_can_only_propose_auto_and_fresh_temp_still_hits_30_30_blocker(self):
        self.backend._health_policy = HealthPolicy(cold_grace_s=0)
        self.backend.accept_device_report(self.report())
        self.clock.advance(1)
        self.backend.accept_device_report(self.report(sequence=2, available=False, value=None,
                                                       observed_at=None, measurement_qualified=False))
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        failed = self.backend.status(True)
        self.assertEqual(failed['source_freshness']['temperature_quality'], 'OFFLINE')
        self.assertEqual(failed['source_freshness']['living_temperature_last_observed'], self.clock.utc-1)
        self.assertEqual(failed['system_health']['mode'], 'AUTO_PROPOSED')
        self.assertFalse(failed['system_health']['proposal']['physical_authority'])
        self.assertEqual(failed['system_health']['components'][0]['status'], 'PROBLEM')
        self.clock.advance(1)
        self.backend.accept_device_report(self.report(sequence=3));self.backend.flush_stop()
        self.assertEqual(self.backend.status(True)['system_health']['mode'], 'RECOVERING')
        self.clock.advance(30.1)
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertIsNone(state['system_health']['proposal'])
        self.assertFalse(state['demand_eligible'])
        self.assertEqual(state['system_health']['mode'], 'RECOVERING')
        self.assertIsNone(state['health_memory']['recovery_since'])

    def test_cold_grace_still_applies_to_qualified_unavailable(self):
        self.backend.accept_device_report(self.report())
        self.clock.advance(1)
        self.backend.accept_device_report(self.report(sequence=2, available=False,
            observed_at=None, value=None, measurement_qualified=False))
        self.backend.flush_stop()
        self.assertNotEqual(self.backend.status(True)['system_health']['mode'], 'AUTO_PROPOSED')
        self.clock.advance(60)
        self.backend.accept_voltage(frame(self.clock.utc))
        self.backend.accept_device_report(self.report(sequence=3, available=False,
            observed_at=None, value=None, measurement_qualified=False))
        self.backend.flush_stop()
        self.assertEqual(self.backend.status(True)['system_health']['mode'], 'AUTO_PROPOSED')

    def test_return_water_is_independent_veto_only_and_probe_body_is_rejected(self):
        self.backend.accept_device_report(self.report())
        self.assertFalse(self.backend.accept_device_report(self.report('return_water', entity_id='synthetic.return.body')))
        self.assertTrue(self.backend.accept_device_report(self.report('return_water', value=40)))
        self.backend.flush_stop()
        self.assertTrue(self.backend.status(True)['demand_eligible'])
        self.clock.advance(1)
        self.backend.accept_device_report(self.report('return_water', sequence=2, veto=True))
        self.backend.flush_stop()
        self.assertFalse(self.backend.status(True)['demand_eligible'])
        self.clock.advance(31)
        self.backend.accept_device_report(self.report('return_water', sequence=3))
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertEqual(state['source_freshness']['return_quality'], 'OK')
        self.assertEqual(state['room']['value'], 22)
        self.assertFalse(state['demand_eligible'])

    def test_auxiliary_veto_survives_restart_and_only_fresh_probe_can_clear_it(self):
        self.backend.accept_device_report(self.report('return_water', veto=True))
        self.backend.flush_stop();self.backend.reboot()
        self.assertTrue(self.view()['return_veto'])
        self.backend.accept_device_report(self.report('return_water', observed_at=self.clock.utc-60))
        self.assertTrue(self.view()['return_veto'])
        self.clock.advance(1)
        self.backend.accept_device_report(self.report('return_water', sequence=2))
        self.assertFalse(self.view()['return_veto'])

    def test_unavailable_probe_retains_last_measurement_without_false_ok(self):
        self.backend.accept_device_report(self.report('return_water'))
        measured = self.view()['return_water_last_observed']
        self.clock.advance(1)
        self.backend.accept_device_report(self.report('return_water', sequence=2, available=False,
            measurement_qualified=False, value=None, observed_at=None))
        self.assertEqual(self.view()['return_quality'], 'UNKNOWN')
        self.assertEqual(self.view()['return_water_last_observed'], measured)
        self.assertFalse(self.backend.status(True)['demand_eligible'])

    def assert_guard_priority(self, guard):
        self.backend.accept_device_report(self.report())
        if guard == 'stop':
            state = self.backend.status(True)
            self.backend.stop(True, state['status']['boot_id'], state['generation'], 'stop')
        self.clock.advance(1)
        self.backend.accept_device_report(self.report(sequence=2, available=False, value=None,
            observed_at=None, measurement_qualified=False))
        voltage = frame(self.clock.utc)
        if guard == 'voltage':
            voltage = replace(voltage, phases=tuple(replace(p, value_v=180) for p in voltage.phases))
        if guard == 'kws':
            voltage = replace(voltage, feed=replace(voltage.feed, kws_online=False))
        self.backend.accept_voltage(voltage);self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertFalse(state['demand_eligible'])
        self.assertNotEqual(state['system_health']['mode'], 'AUTO_PROPOSED')
        if guard == 'stop':
            self.assertEqual(state['status']['mode'], 'MANUAL_PAUSE')
            self.assertIsNone(state['system_health']['proposal'])

    def test_stop_priority(self):
        self.assert_guard_priority('stop')

    def test_voltage_priority(self):
        self.assert_guard_priority('voltage')

    def test_kws_priority(self):
        self.assert_guard_priority('kws')

    def test_restart_rejects_old_boot_and_requires_new_measurement(self):
        old = self.report()
        self.backend.accept_device_report(old);self.backend.flush_stop();self.backend.reboot()
        self.assertFalse(self.backend.accept_device_report(old))
        self.assertIsNone(self.view()['living_device_last_activity'])
        self.assertFalse(self.backend.status(True)['demand_eligible'])
        self.backend.accept_device_report(self.report('humidity'))
        self.assertEqual(self.view()['temperature_quality'], 'UNKNOWN')
        self.assertFalse(self.backend.status(True)['demand_eligible'])
        self.backend.accept_device_report(self.report());self.backend.accept_voltage(frame(self.clock.utc))
        self.backend.flush_stop()
        self.assertEqual(self.view()['temperature_quality'], 'OK')

    def test_window_validation_and_clock_rollback_do_not_forge_activity(self):
        for value in (True, float('nan'), 59, 86401):
            with self.assertRaises(ValueError):
                SourceActivity(value)
        tracker = SourceActivity(120)
        self.assertEqual(tracker.window_s, 120)
        report = self.report();clock = self.backend.trusted_clock()
        self.assertTrue(tracker.accept(report, clock))
        self.assertEqual(tracker.view(replace(clock, monotonic=clock.monotonic+121),30)['device_quality'],'DEGRADED')
        self.assertIsNone(tracker.view(replace(clock, monotonic=clock.monotonic-1),30)['living_device_last_activity'])
        self.assertIsNone(tracker.view(replace(clock, utc=clock.utc-1),30)['living_device_last_activity'])
        self.assertIsNone(tracker.view(clock,30,clock_ok=False)['living_device_last_activity'])
