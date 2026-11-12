"""Six focused native integration transitions, synthetic inputs, no HA transport."""
import asyncio
from datetime import datetime, timezone
import importlib
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType
import unittest

from tools.release.build_v2_engine import package

ROOT = Path('releases/ha_v2/custom_components/heating_ai_v2')
TEMP = tempfile.TemporaryDirectory()
DEST = Path(TEMP.name)/'custom_components'/'heating_ai_v2'
shutil.copytree(ROOT, DEST, ignore=shutil.ignore_patterns('__pycache__'))
package(DEST/'engine')
for name, path in (('custom_components', DEST.parent), ('custom_components.heating_ai_v2', DEST)):
    module = ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
native = importlib.import_module('custom_components.heating_ai_v2.native_runtime')
telemetry = importlib.import_module('custom_components.heating_ai_v2.telemetry')
planning = importlib.import_module('custom_components.heating_ai_v2.shadow_plan')
ledger_module = importlib.import_module('custom_components.heating_ai_v2.critical_ledger')


def frame(now):
    stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
    def row(value, unit=''):
        return dict(state=str(value), unit=unit, last_reported=stamp, attributes={})
    rows = dict(room=row(20, '°C'), return_probe=row(25, '°C'), thermostat=row('heat'),
                grid=row('Наявна мережа'), stored_heat=row(25, '°C'))
    rows['thermostat']['attributes'] = dict(current_temperature=21, temperature=22,
        min_temp=5, max_temp=35, target_temp_step=.5)
    for phase in ('l1','l2','l3'):
        rows['voltage_'+phase] = row(230, 'V')
        rows['kws_'+phase] = row(0, 'kW')
    rows['kws_energy'] = row(100, 'kWh')
    rows.update({key: row(value, '°C') for key,value in
                 dict(day_target=21,night_target=20,day_upper=22,night_upper=21).items()})
    rows.update({key: row(value) for key,value in dict(sleep_start='23:00:00',sleep_end='07:00:00',
        heating_start='23:00:00',heating_end='07:00:00',strategy='Комфорт протягом доби',power_model='fixed_3',fan_mode='Зупинити').items()})
    rows.update({key: row(value,'%') for key,value in dict(fan_night=30,fan_standard=40,fan_intense=50).items()})
    rows['legacy_model'] = row('ready')
    rows['legacy_model']['attributes']['parameters'] = dict(floor_air=.04,room_loss=.02,
        floor_decay=.1,heat_gain=.3,fire_gain=.01,version=1)
    return rows


class NativeControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1794470400.0
        self.rows = frame(self.now)
        self.calls = []
        self.requests = 0
        async def forbidden(*args):
            self.calls.append(args)
            raise AssertionError('Physical transport reached')
        self.forbidden = forbidden
        self.controller = native.NativeController(self.root, self.rows, forbidden, forbidden)
        self.tick()

    def tick(self, elapsed=0):
        self.controller.tick(self.rows, telemetry.snapshot(self.rows), self.now+elapsed, 1000+elapsed)

    def mutation(self):
        c=self.controller
        self.requests += 1
        return dict(expected_revision=c.persisted['revision'], request_id='synthetic.'+str(self.requests),
                    boot_id=c.boot_id, owner_epoch=c.state.owner_epoch)

    async def test_outage_and_stale_upstream_voltages(self):
        c=self.controller
        values=dict(c.persisted['values'],min_voltage_v=190,max_voltage_v=250,
                    hysteresis_v=5,stable_recovery_s=30,voltage_max_age_s=30)
        await c.dispatch('settings/save', self.mutation()|dict(values=values), True)
        self.tick()
        self.assertEqual(c.safety['voltage_status'],'UNQUALIFIED_IN_BAND')
        self.rows['grid']['state']='Відсутня мережа'
        self.tick(1)
        self.assertEqual(c.safety['voltage_status'],'GRID_OFF_OR_UNKNOWN')
        self.rows['grid']['state']='Наявна мережа'
        self.tick(31)
        self.assertEqual(c.safety['voltage_status'],'CACHE_STALE_OR_MISSING')
        self.assertFalse(c.safety['physical_commands_enabled'])
        self.assertEqual(self.calls,[])

    async def test_three_phase_zero_unknown_and_one_counter_continuity(self):
        self.assertEqual(telemetry.snapshot(self.rows)['kws_total_kw_last_known'],0)
        self.rows['kws_l2']['state']='unavailable'
        self.assertIsNone(telemetry.snapshot(self.rows)['kws_total_kw_last_known'])
        store=self.controller.store
        store.observe(self.now,20,100,0)
        store.observe(self.now+60,20,None,None)
        store.observe(self.now+120,20,101,None)
        store.observe(self.now+120,20,101,None)
        history=store.history(self.now,self.now+180,self.now+180)
        self.assertEqual(sum(r['kwh'] for r in history['energy']),1)
        self.assertEqual(history['energy'][0]['category'],'recovered')
        store.observe(self.now+180,20,2,0)
        self.assertIsNotNone(store.status()['energy_fault'])
        self.assertEqual(store.status()['counter'],101)

    async def test_stop_manual_stale_owner_and_duplicate_mutations(self):
        c=self.controller
        request=self.mutation()
        first=await c.dispatch('settings/save',request|dict(values=c.persisted['values']),True)
        same=await c.dispatch('settings/save',request|dict(values=c.persisted['values']),True)
        self.assertEqual(first,same)
        await c.dispatch('resume',self.mutation(),True)
        self.assertFalse(c.persisted['manual_pause'])
        # STOP must not be lost merely because a settings revision changed.
        await c.dispatch('pause',self.mutation() | dict(expected_revision=0, request_id='synthetic.stop'),True)
        self.tick()
        self.assertTrue(c.persisted['manual_pause'])
        self.assertTrue(c.journal['fenced'])
        self.assertEqual((await c.dispatch('resume',request,True))['status'],'conflict')
        self.assertEqual((await c.gateway.execute(None))['stage'],'DENIED')
        self.assertEqual(self.calls,[])

    async def test_restart_pending_sent_echo_and_no_positive_retry(self):
        # Reopening must read the checksummed identity, not a second shadow owner file.
        root=self.root/'pending';root.mkdir()
        ledger=ledger_module.CriticalLedger(root,owner_id='synthetic',boot_id='old',owner_epoch=0)
        ledger.prepare('intent','HEAT',{'target':22},at=100,expected_revision=0,
                       owner_id='synthetic',boot_id='old',owner_epoch=0)
        ledger.record_sent('intent',at=101,expected_revision=1,
                           owner_id='synthetic',boot_id='old',owner_epoch=0)
        reopened=ledger_module.CriticalLedger(root)
        status=reopened.status()
        self.assertEqual(status['commands']['intent']['stage'],'UNKNOWN')
        self.assertTrue(status['fenced'])
        with self.assertRaises(ledger_module.LedgerConflict):
            reopened.record_ha_echo('intent',at=102,expected_revision=status['revision'],
                                    owner_id='synthetic',boot_id='old',owner_epoch=status['owner_epoch'])
        self.assertFalse(status['physical_ack'])
        restarted=native.NativeController(self.root,self.rows,self.forbidden,self.forbidden)
        self.assertNotEqual(restarted.boot_id,self.controller.boot_id)
        self.assertTrue(restarted.journal['fenced'])
        self.assertEqual((await restarted.gateway.execute(None))['stage'],'DENIED')
        self.assertEqual(self.calls,[])

    async def test_native_settings_cas_auth_and_immutable_original_truth(self):
        c=self.controller
        request=self.mutation()
        values=dict(c.persisted['values'],day_upper=23.2)
        with self.assertRaises(PermissionError):
            await c.dispatch('settings/save',request|dict(values=values),False)
        result=await c.dispatch('settings/save',request|dict(values=values),True)
        self.assertEqual(result['status'],'saved')
        conflict=await c.dispatch('settings/save',request|dict(request_id='stale',values=values),True)
        self.assertEqual(conflict['status'],'conflict')
        self.assertEqual(c.store.status()['values']['day_upper'],23.2)
        self.tick()
        self.assertEqual(c.active_limit['ceiling'],25.5)
        c.store.archive(dict(issued_at=None,received_at=self.now,hours=[]))
        result=c.store.history(self.now-100,self.now,self.now)
        self.assertEqual(result['original_status'],'MISSING')
        self.assertIsNone(result['original'])
        self.assertEqual(result['actual'],[])
        self.assertFalse(c.overview()['physical_commands_enabled'])

    async def test_source_change_planner_thermal_tick_oneshot_and_fan_handoff(self):
        c=self.controller
        weather=dict(received_at=self.now,issued_at=None,hours=[dict(at=self.now+i*3600,outside_c=0) for i in range(25)])
        plan,coast=planning.diagnostics(c.planning_rows(self.rows),weather,None,self.now)
        self.assertEqual(plan['status'],'VIRTUAL_CONDITIONAL')
        self.assertGreater(plan['horizon_hours'],20)
        self.assertGreater(len(plan['trajectory']),1)
        self.assertEqual(coast['status'],'UNQUALIFIED_CONDITIONAL_COAST')
        self.rows['room']['state']='24'
        self.tick(2)  # Works without waiting for a stalled weather or planning future.
        self.assertEqual(c.values['room_c_last_known'],24)
        self.assertEqual((await c.dispatch('arm',self.mutation(),True))['status'],'denied')
        fan=importlib.import_module('custom_components.heating_ai_v2.fan_shadow')
        _,decision=fan.project(dict(c.values,fan_mode_last_known='Зупинити'),None,1000,12)
        self.assertEqual(decision['commands_sent'],0)
        self.assertFalse(decision['physical_authority'])
        self.assertEqual(self.calls,[])


def tearDownModule():
    TEMP.cleanup()
