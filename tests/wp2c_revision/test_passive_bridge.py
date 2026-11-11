"""Passive state ingestion and one-report recovery; no physical HA connection."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from packages.ha_native.backend import NativeBackend
from packages.ha_native.health import HealthInputs, HealthPolicy, SourceTimingPolicy
from packages.ha_native.passive_bridge import PassiveBinding, PassiveSourceBridge, HAObservation
from packages.ha_native.source_activity import DeviceReport, BINDINGS
from tests.wp2c_backend.test_backend import fixture, observe
from tests.wp2c_backend.test_clock import FakeTime
from tests.wp2c_meter.test_voltage import frame


class PassiveBridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='heating-wp2c-')
        self.addCleanup(self.directory.cleanup)
        self.clock = FakeTime()
        self.inputs = HealthInputs(owner='synthetic.owner', thermostat_qualified=True, thermostat_age_s=0, plan_ok=True)
        self.backend = NativeBackend(Path(self.directory.name), fixture(), enabled=True, clock=self.clock,
                                    health_evidence=lambda: self.inputs)
        self.backend.configure_timing(SourceTimingPolicy())
        self.backend._health_policy = replace(self.backend._health_policy, cold_grace_s=0)
        self.backend.open();self.addCleanup(self.backend.close)
        observe(self.backend)
        self.bindings = tuple(PassiveBinding(role, 'sensor.synthetic_'+role, device, 'tuya', unit)
                              for role, (device, _, unit) in BINDINGS.items())
        self.bridge = PassiveSourceBridge(self.bindings)

    def event(self, role='temperature', **changes):
        b = next(b for b in self.bindings if b.role == role)
        return replace(HAObservation(b.entity_id,b.device_id,b.integration,b.unit,
            45 if role == 'humidity' else 22,self.clock.utc,self.clock.utc,self.clock.utc-100,
            registry_verified=True), **changes)

    def ingest(self, role='temperature', **changes):
        return self.bridge.observe(self.event(role, **changes),self.backend,self.backend.trusted_clock(),live_event=True)

    def qualified_temperature(self, sequence=1):
        device,entity,unit = BINDINGS['temperature']
        clock = self.backend.trusted_clock()
        return self.backend.accept_device_report(DeviceReport('temperature',device,entity,unit,
            clock.boot_id,sequence,clock.utc,clock.utc,clock.utc,22,
            mapping_verified=True,report_qualified=True,measurement_qualified=True))

    def test_state_write_and_humidity_are_monitoring_not_physical_temperature(self):
        original = self.backend.status(True)['room'].copy()
        self.assertTrue(self.ingest())
        state = self.backend.status(True)
        self.assertEqual(state['source_freshness']['device_quality'],'OK')
        self.assertEqual(state['source_freshness']['temperature_quality'],'UNKNOWN')
        self.assertFalse(state['demand_eligible'])
        self.clock.advance(20)
        self.assertTrue(self.ingest('humidity'))
        self.assertEqual(self.backend.status(True)['room'],original)
        self.assertIsNone(self.backend.status(True)['source_freshness']['living_temperature_last_observed'])
        self.assertEqual(self.backend.status(True)['source_freshness']['activity_provenance'],'ha_state_write')
        self.assertTrue(all(p['physical_measurement']=='BLOCKED' for p in self.backend.status(True)['system_health']['passive_sources']))

    def test_same_value_integration_rewrite_has_no_transport_sequence_or_measurement(self):
        self.assertTrue(self.ingest())
        self.clock.advance(1)
        self.assertTrue(self.ingest(last_updated=self.clock.utc-1))
        p = self.backend.status(True)['system_health']['passive_sources'][0]
        self.assertNotIn('sequence',p)
        self.assertNotIn('entity_id',p)
        self.assertNotIn('device_id',p)
        self.assertIsNone(self.backend.status(True)['source_freshness']['living_temperature_last_observed'])

    def test_config_misbindings_and_writes_are_rejected(self):
        for bindings in ((),self.bindings[:-1], self.bindings+(self.bindings[0],),
                         tuple(replace(b, device_id='synthetic.other') if b.role=='humidity' else b for b in self.bindings),
                         tuple(replace(b, device_id=BINDINGS['temperature'][0]) if b.role=='return_water' else b for b in self.bindings)):
            with self.assertRaises(ValueError):
                PassiveSourceBridge(bindings)
        with self.assertRaises(ValueError):
            PassiveSourceBridge(self.bindings,physical_commands_enabled=True)
        self.assertFalse(self.bridge.physical_commands_enabled)

    def test_cached_restored_cross_device_future_and_wrong_unit_are_not_reports(self):
        clock = self.backend.trusted_clock()
        self.assertFalse(self.bridge.observe(self.event(),self.backend,clock))
        for changes in ({'restored':True},{'registry_verified':False},{'device_id':'synthetic.other'},
                        {'integration':'derived'},{'unit':'F'},{'last_reported':clock.utc+1},
                        {'last_changed':clock.utc+1},{'value':float('nan')},{'value':None}):
            self.assertFalse(self.ingest(**changes))
        self.assertTrue(self.ingest())
        self.assertFalse(self.ingest())  # Identical integration write is not a new report.
        self.assertFalse(self.backend.status(True)['demand_eligible'])

    def test_61_minutes_and_return_probe_never_grant_heat_or_auto(self):
        self.ingest()
        self.clock.advance(3661)
        self.assertTrue(self.ingest('return_water',value=25))
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        state = self.backend.status(True)
        self.assertEqual(state['source_freshness']['device_quality'],'DEGRADED')
        self.assertEqual(state['source_freshness']['return_quality'],'UNKNOWN')
        self.assertIsNone(state['system_health']['proposal'])
        self.assertFalse(state['demand_eligible'])

    def test_one_new_qualified_report_recovers_after_positive_shorter_dwell(self):
        self.assertTrue(self.ingest(available=False,value=None))
        self.backend.flush_stop()
        self.assertEqual(self.backend.status(True)['system_health']['mode'],'AUTO_PROPOSED')
        self.clock.advance(1)
        self.assertTrue(self.qualified_temperature())
        self.backend.flush_stop()
        initial = self.backend.status(True)
        self.assertEqual(initial['system_health']['mode'],'RECOVERING')
        self.clock.advance(15)
        # No second measurement, heartbeat, voltage or humidity report.
        self.backend.flush_stop()
        final = self.backend.status(True)
        self.assertEqual(final['room']['observed'],initial['room']['observed'])
        self.assertEqual(final['system_health']['mode'],'HEAT_PROPOSED')
        self.assertEqual(final['system_health']['proposal']['stage'],'proposed')
        self.assertFalse(final['system_health']['proposal']['physical_authority'])
        self.assertEqual(final['health_memory']['auto_owner'],'synthetic.owner')
        self.assertFalse(self.backend.safety_permit().allowed)

    def test_humidity_cannot_recover_and_measurement_still_expires(self):
        self.ingest(available=False,value=None);self.backend.flush_stop()
        self.clock.advance(1);self.ingest('humidity');self.backend.flush_stop()
        self.clock.advance(15)
        self.assertNotEqual(self.backend.status(True)['system_health']['mode'],'HEAT_PROPOSED')
        self.qualified_temperature();self.backend.flush_stop()
        self.clock.advance(31);self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        self.assertFalse(self.backend.status(True)['demand_eligible'])
        self.assertIsNone(self.backend.status(True)['system_health']['proposal'])

    def test_stop_owner_voltage_and_kws_fence_recovery(self):
        self.ingest(available=False,value=None);self.backend.flush_stop()
        self.clock.advance(1);self.qualified_temperature();self.backend.flush_stop()
        self.clock.advance(15)
        for kind in ('voltage','kws','owner','stop'):
            if kind=='voltage':
                self.backend.accept_voltage(replace(frame(self.clock.utc),phases=tuple(replace(p,value_v=180) for p in frame(self.clock.utc).phases)))
            elif kind=='kws':
                self.backend.accept_voltage(replace(frame(self.clock.utc),feed=replace(frame(self.clock.utc).feed,kws_online=False)))
            elif kind=='owner':
                self.backend.accept_voltage(frame(self.clock.utc));self.inputs=replace(self.inputs,owner=None)
            else:
                state=self.backend.status(True)
                self.backend.stop(True,state['status']['boot_id'],state['generation'],'synthetic-stop')
            self.backend.flush_stop()
            self.assertNotEqual(self.backend.status(True)['system_health']['mode'],'HEAT_PROPOSED')
            self.assertFalse(self.backend.safety_permit().allowed)

    def test_restart_and_rollback_do_not_restore_fake_measurement(self):
        old=self.event();oldclock=self.backend.trusted_clock()
        self.ingest();self.backend.flush_stop();self.backend.reboot()
        self.assertIsNone(self.backend.status(True)['source_freshness']['living_temperature_last_observed'])
        self.assertFalse(self.bridge.observe(old,self.backend,self.backend.trusted_clock(),live_event=False))
        self.ingest('humidity')
        self.clock.monotonic-=1
        self.assertFalse(self.ingest())
        self.assertFalse(self.backend.status(True)['demand_eligible'])

    def test_timing_validation_and_configuration_are_separate(self):
        for age,dwell,window in ((5,15,3660),(5,5,3660),(5,-1,3660),(30,30,3660),(30,31,3660),(30,0,3660),(301,15,3660),(30,15,59)):
            with self.assertRaises(ValueError):SourceTimingPolicy(age,window,dwell)
        paired = SourceTimingPolicy(5,3660,2)
        self.assertEqual(paired.measurement_authorization_age_s,5)
        self.assertEqual(paired.recovery_dwell_s,2)
        self.backend.configure_timing(SourceTimingPolicy(60,120,10))
        view=self.backend.status(True)['source_freshness']
        self.assertEqual(view['measurement_authorization_age_s'],60)
        self.assertEqual(view['activity_window_s'],120)
        self.assertEqual(view['recovery_dwell_s'],10)
        self.assertTrue(view['recovery_policy_ready'])
