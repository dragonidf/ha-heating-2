"""Effective upper-limit guard at final synthetic HEAT intent, never physical ACK."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from packages.ha_native.backend import NativeBackend
from packages.ha_native.health import HealthInputs
from packages.ha_native.thermostat import ActiveRoomLimit, supported_ceiling
from packages.ha_native.source_activity import DeviceReport, BINDINGS
from tests.wp2c_backend.test_backend import fixture, observe
from tests.wp2c_backend.test_clock import FakeTime
from tests.wp2c_meter.test_voltage import frame


class ThermostatCeilingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='heating-wp2c-');self.addCleanup(self.tmp.cleanup)
        self.clock=FakeTime()
        self.limit=ActiveRoomLimit('day',22,22,qualified=True)
        self.evidence=HealthInputs(owner='synthetic.owner',plan_ok=True,thermostat_qualified=True,thermostat_age_s=0)
        self.backend=NativeBackend(Path(self.tmp.name),fixture(),enabled=True,clock=self.clock,
            effective_room_limit=lambda:self.limit,health_evidence=lambda:self.evidence)
        self.backend.open();self.addCleanup(self.backend.close);observe(self.backend)

    def propose(self, **changes):
        self.backend.flush_stop()
        state=self.backend.status(True)
        args=dict(owner_epoch=state['status']['owner_epoch'],requested_setpoint_c=30,planner_requests_heat=True,
            owns_thermostat=True,thermostat_mode='HEAT',thermostat_fresh=True,thermostat_c=23,
            min_setpoint_c=5,max_setpoint_c=35,temperature_step_c=.5)
        return self.backend.heat_setpoint_intent(**(args|changes))

    def room(self,value,sequence=1):
        clock=self.backend.trusted_clock();device,entity,unit=BINDINGS['temperature']
        self.clock.advance(1);clock=self.backend.trusted_clock()
        self.assertTrue(self.backend.accept_device_report(DeviceReport('temperature',device,entity,unit,
            clock.boot_id,sequence,clock.utc,clock.utc,clock.utc,value,
            mapping_verified=True,report_qualified=True,measurement_qualified=True)))
        self.backend.flush_stop()

    def test_day_and_live_upper_change_without_restart(self):
        before=self.backend.status(True)
        first=self.propose()
        self.assertEqual(first['action'],'request_heat');self.assertEqual(first['setpoint_c'],24.5)
        old_epoch=first['owner_epoch']
        self.limit=replace(self.limit,upper_c=23)
        updated=self.backend.status(True)
        self.assertEqual(updated['status']['boot_id'],before['status']['boot_id'])
        self.assertEqual(updated['system_health']['thermostat_ceiling']['proposed_ceiling_c'],25.5)
        self.assertIsNone(updated['system_health']['thermostat_ceiling']['proposed_setpoint_c'])
        self.assertIsNone(self.backend.heat_setpoint_intent(owner_epoch=old_epoch,requested_setpoint_c=30,owns_thermostat=True))
        self.assertEqual(self.propose()['setpoint_c'],25.5)

    def test_night_changes_and_effective_mode_transition(self):
        self.room(20.5)
        self.limit=ActiveRoomLimit('night',21.5,21,qualified=True)
        self.assertEqual(self.propose()['setpoint_c'],24)
        self.limit=replace(self.limit,upper_c=22)
        self.assertEqual(self.propose()['setpoint_c'],24.5)
        self.limit=ActiveRoomLimit('day',23,22,qualified=True)
        self.assertEqual(self.propose()['setpoint_c'],25.5)
        self.limit=ActiveRoomLimit('allowed_hours',21.7,21,qualified=True)
        self.assertEqual(self.propose()['setpoint_c'],24)

    def test_odd_upper_margin_device_bounds_and_decimal_floor(self):
        self.limit=replace(self.limit,upper_c=22.1)
        result=self.propose()
        self.assertEqual(result['ceiling_c'],24.5)
        self.assertEqual(self.backend.status(True)['system_health']['thermostat_ceiling']['ceiling_raw_c'],24.6)
        self.limit=replace(self.limit,upper_c=22,reserve_margin_c=3)
        self.assertEqual(self.propose()['setpoint_c'],25)
        self.assertEqual(self.propose(max_setpoint_c=24)['setpoint_c'],24)
        self.assertEqual(self.propose(requested_setpoint_c=23.9)['setpoint_c'],23.5)

    def test_room_target_withdraws_even_with_ceiling_headroom(self):
        self.room(22)
        result=self.propose(thermostat_c=23)
        self.assertEqual(result['action'],'withdraw_demand')
        self.assertEqual(result['setpoint_c'],22.5)
        self.assertEqual(result['reason'],'room_target_or_upper_reached')
        self.assertFalse(result['physical_ack'])

    def test_local_bias_does_not_become_room_stop_or_the_wrong_formula(self):
        self.assertEqual(self.propose(thermostat_c=19)['action'],'request_heat')
        self.assertEqual(self.propose(thermostat_c=24)['action'],'request_heat')
        for local in (24.5,25):
            result=self.propose(thermostat_c=local)
            self.assertEqual(result['action'],'withdraw_demand')
            self.assertLess(result['setpoint_c'],local)
            self.assertLessEqual(result['setpoint_c'],24.5)

    def test_lowering_ceiling_cancels_old_pending_request_and_withdraws(self):
        self.limit=replace(self.limit,upper_c=23)
        pending=self.propose(thermostat_c=24.5)
        self.assertEqual(pending['action'],'request_heat')
        self.limit=replace(self.limit,upper_c=22)
        view=self.backend.status(True)['system_health']['thermostat_ceiling']
        self.assertIsNone(view['proposed_setpoint_c'])
        result=self.propose(thermostat_c=24.5)
        self.assertEqual(result['action'],'withdraw_demand');self.assertEqual(result['setpoint_c'],24)

    def test_no_supported_on_or_off_value_never_claims_heat_or_off(self):
        result=self.propose(thermostat_c=24.5,min_setpoint_c=24.5)
        self.assertEqual(result['action'],'cannot_confirm_withdrawal')
        self.assertNotIn('setpoint_c',result)
        for changes in ({'temperature_step_c':1},{'min_setpoint_c':None},{'max_setpoint_c':4},
                        {'thermostat_fresh':False},{'thermostat_c':None}):
            result=self.propose(**changes)
            self.assertEqual(result['action'],'cannot_confirm_withdrawal')
            self.assertNotIn('setpoint_c',result)
            self.assertIsNone(result['acknowledged_setpoint_c'])

    def test_stale_room_humidity_and_probe_do_not_authorize_heat(self):
        self.room(21.8)
        observed=self.backend.status(True)['room']['observed']
        self.clock.advance(31)
        for role in ('humidity','return_water'):
            device,entity,unit=BINDINGS[role];clock=self.backend.trusted_clock()
            self.backend.accept_device_report(DeviceReport(role,device,entity,unit,clock.boot_id,1,
                clock.utc,clock.utc,clock.utc,45 if role=='humidity' else 25,
                mapping_verified=True,report_qualified=True,measurement_qualified=True))
        self.backend.accept_voltage(frame(self.clock.utc))
        result=self.propose()
        self.assertNotEqual(result['action'],'request_heat')
        self.assertEqual(self.backend.status(True)['room']['observed'],observed)

    def test_stop_voltage_kws_and_owner_fences(self):
        self.propose()
        original=frame(self.clock.utc)
        for voltage in (replace(original,phases=tuple(replace(p,value_v=180) for p in original.phases)),
                        replace(original,feed=replace(original.feed,kws_online=False))):
            self.backend.accept_voltage(voltage)
            result=self.propose()
            self.assertEqual(result['action'],'withdraw_demand')
        self.backend.accept_voltage(original)
        self.evidence=replace(self.evidence,owner=None)
        self.assertNotEqual(self.propose()['action'],'request_heat')
        self.assertIsNone(self.propose(owns_thermostat=False))
        state=self.backend.status(True)
        self.backend.stop(True,state['status']['boot_id'],state['generation'],'synthetic-stop')
        self.assertIsNone(self.propose())
        self.assertIsNone(self.backend.status(True)['system_health']['thermostat_ceiling']['proposed_setpoint_c'])

    def test_auto_never_claims_to_enforce_manual_heat_ceiling(self):
        for mode in ('AUTO','UNKNOWN','OFF'):
            result=self.propose(thermostat_mode=mode)
            self.assertEqual(result['action'],'cannot_confirm_withdrawal')
            self.assertNotIn('setpoint_c',result)
            self.assertIn('auto_or_mode_unknown',result['reason'])

    def test_comfort_target_is_not_upper_and_planner_no_heat_withdraws(self):
        self.limit=replace(self.limit,upper_c=23,comfort_target_c=22)
        self.assertEqual(self.propose()['ceiling_c'],25.5)
        self.limit=replace(self.limit,comfort_target_c=22.5)
        self.assertEqual(self.propose()['ceiling_c'],25.5)
        self.assertEqual(self.propose(planner_requests_heat=False)['action'],'withdraw_demand')

    def test_one_shot_has_same_cap_without_consuming_or_acknowledging_it(self):
        self.assertNotEqual(self.propose(one_shot=True)['action'],'request_heat')
        self.backend.flush_stop();state=self.backend.status(True)
        body=dict(entry_id='synthetic-entry',version=[2,0],boot_id=state['status']['boot_id'],
            generation=state['generation'],owner_epoch=state['status']['owner_epoch'],kind='arm',request_id='synthetic-arm')
        self.assertEqual(self.backend.dispatch('control',body,True)['status'],'accepted_fake')
        self.assertEqual(self.propose(one_shot=True)['setpoint_c'],24.5)
        self.assertEqual(self.backend.status(True)['oneShot']['state'],'armed')
        self.assertFalse(self.backend.safety_permit().allowed)

    def test_restart_persistence_failure_and_clock_rollback_cannot_grant_heat(self):
        self.propose();self.backend.flush_stop();self.backend.reboot()
        state=self.backend.status(True)
        self.assertIsNone(state['system_health']['thermostat_ceiling']['proposed_setpoint_c'])
        self.assertNotEqual(self.propose()['action'],'request_heat')
        observe(self.backend)
        self.backend._pending_stop=True
        def fail_commit(point):
            raise OSError('synthetic persistence fault')
        self.backend.critical.hook=fail_commit
        self.assertFalse(self.backend.flush_stop())
        state=self.backend.status(True)
        result=self.backend.heat_setpoint_intent(owner_epoch=state['status']['owner_epoch'],requested_setpoint_c=30,
            planner_requests_heat=True,owns_thermostat=True,thermostat_mode='HEAT',thermostat_fresh=True,
            thermostat_c=23,min_setpoint_c=5,max_setpoint_c=35,temperature_step_c=.5)
        self.assertNotEqual(result['action'],'request_heat')
        self.backend.critical.hook=None
        self.backend.flush_stop()
        self.clock.monotonic-=1
        self.assertIsNone(self.propose())

    def test_unqualified_effective_limit_and_invalid_values_fail_closed(self):
        self.limit=replace(self.limit,qualified=False)
        self.assertNotEqual(self.propose()['action'],'request_heat')
        for changes in ({'reserve_margin_c':-1},{'upper_c':float('nan')},{'source_mode':''},
                        {'upper_c':1.7e308,'reserve_margin_c':1.7e308}):
            with self.assertRaises(ValueError):replace(self.limit,**changes)
        self.assertIsNone(supported_ceiling(ActiveRoomLimit('day',1,0,qualified=True),5,35,.5))
