"""One closed mock writer with independent explicitly injected device readback."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
from threading import Event
import unittest
from packages.contracts import Action
from packages.ha_native.backend import NativeBackend
from packages.ha_native.health import HealthInputs
from packages.ha_native.thermostat import ActiveRoomLimit
from packages.ha_native.thermostat_executor import ThermostatExecutor, IsolatedClimateMock, MockCredential
from tests.wp2c_backend.test_backend import fixture, observe
from tests.wp2c_backend.test_clock import FakeTime
from tests.wp2c_meter.test_voltage import frame


class ThermostatExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='heating-wp2c-');self.addCleanup(self.tmp.cleanup)
        self.clock=FakeTime();self.limit=ActiveRoomLimit('day',22,22,qualified=True)
        self.evidence=HealthInputs(owner='synthetic.controller',plan_ok=True,thermostat_qualified=True,thermostat_age_s=0)
        self.backend=NativeBackend(Path(self.tmp.name),fixture(),enabled=True,clock=self.clock,
            effective_room_limit=lambda:self.limit,health_evidence=lambda:self.evidence)
        self.backend.open();self.addCleanup(self.backend.close);observe(self.backend)
        self.device=IsolatedClimateMock(self.backend.trusted_clock)
        self.device.mapping_qualified=True;self.device.mode='HEAT';self.device.observe_temperature(23,qualified=True)
        self.executor=ThermostatExecutor(self.backend,self.device,enabled=True,timeout_s=.15)
        self.addCleanup(self.executor.close)
        self.credential=self.device.credential('synthetic.controller')

    def proposal(self,**changes):
        self.backend.flush_stop();state=self.backend.status(True)
        return self.backend.heat_setpoint_intent(**(dict(owner_epoch=state['status']['owner_epoch'],
            requested_setpoint_c=30,planner_requests_heat=True,owns_thermostat=True,
            thermostat_mode='HEAT',thermostat_fresh=True,thermostat_c=23,
            min_setpoint_c=5,max_setpoint_c=35,temperature_step_c=.5)|changes))

    async def until(self,predicate):
        async with asyncio.timeout(2):
            while not predicate():await asyncio.sleep(0)

    def echo(self, command_id, *, target, action=Action.HEAT,**changes):
        self.clock.advance(.001)
        self.device.device_report(command_id,mode='HEAT',target=target,echo_action=action,qualified=True,**changes)

    async def complete(self, p, target=24.5):
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.echo(self.device.calls[-1].identity,target=target)
        return await asyncio.wait_for(task,2)

    async def test_inert_default_real_transport_and_invalid_auth_never_dispatch(self):
        p=self.proposal()
        inert=ThermostatExecutor(self.backend,self.device)
        self.addCleanup(inert.close)
        self.assertFalse(inert.activate(self.credential,p))
        self.assertEqual((await inert.execute(p))['status'],'blocked')
        self.assertFalse(self.executor.activate(MockCredential(object(),'synthetic.controller'),p))
        with self.assertRaises(ValueError):ThermostatExecutor(self.backend,object())
        self.assertEqual(self.device.calls,[])

    async def test_independent_echo_idempotence_and_no_physical_ack(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.assertFalse(task.done())
        await self.until(lambda:any(r['status']=='sent' for r in self.executor.status()['receipts'].values()))
        self.assertIsNotNone(self.executor.status()['pending'])
        self.echo(self.device.calls[0].identity,target=24.5)
        result=await asyncio.wait_for(task,2)
        self.assertEqual(result['status'],'echoed_mock')
        self.assertFalse(result['physical_ack']);self.assertIsNone(result['contacts_open'])
        self.assertEqual(await self.executor.execute(p),result)
        self.assertEqual(len(self.device.calls),1)
        self.assertFalse(self.backend.safety_permit().allowed)
        self.assertFalse(self.backend.status(True)['system_health']['thermostat_ceiling']['physical_ack'])

    async def test_single_writer_lease_prevents_other_controller_watchdog_or_updater(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        other=ThermostatExecutor(self.backend,self.device,enabled=True)
        self.addCleanup(other.close)
        for principal in ('synthetic.watchdog','synthetic.updater','synthetic.legacy'):
            self.assertFalse(other.activate(self.device.credential(principal),p))
        self.assertEqual(self.device.calls,[])

    async def test_forged_modified_or_uncapped_proposal_is_not_authorized(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        for changed in ({'setpoint_c':30},{'owner_epoch':0},{'physical_ack':True},{'mode':'AUTO'}):
            self.assertEqual((await self.executor.execute(p|changed))['status'],'blocked')
        self.assertEqual(self.device.calls,[])

    async def test_missing_dropped_noop_readback_is_uncertain_and_latches_positive_block(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        self.device.drop=True
        result=await asyncio.wait_for(self.executor.execute(p),2)
        self.assertEqual(result['status'],'uncertain')
        self.assertTrue(self.executor.status()['uncertain'])
        self.assertTrue(any(not c.positive for c in self.device.calls))
        count=len(self.device.calls)
        self.assertFalse(self.executor.activate(self.credential,p))
        self.assertEqual((await self.executor.execute(p))['status'],'uncertain')
        self.assertEqual(len(self.device.calls),count)

    async def test_contradictory_noop_device_readback_never_becomes_ack(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p));self.device.noop=True
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.echo(self.device.calls[0].identity,target=20)
        result=await asyncio.wait_for(task,2)
        self.assertEqual(result['status'],'uncertain')
        self.assertFalse(result['physical_ack'])

    async def test_ha_state_write_is_not_device_or_temperature_ack(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.echo(self.device.calls[0].identity,target=24.5,origin='ha_state_write')
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')
        self.assertEqual(self.device.temperature_at,self.clock.utc-.001)

    async def test_old_timestamp_wrong_identity_and_external_override_are_rejected(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.device.device_report('synthetic.wrong-id',mode='HEAT',target=24.5,echo_action=Action.HEAT,qualified=True,manual=True)
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')

    async def test_stop_preempts_delayed_send_without_positive_replay(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p));self.device.send_gate.clear()
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:self.executor.status()['pending'] is not None)
        state=self.backend.status(True)
        self.backend.stop(True,state['status']['boot_id'],state['generation'],'synthetic-stop')
        self.device.send_gate.set()
        await self.until(lambda:bool(self.device.calls))
        self.assertTrue(all(not c.positive for c in self.device.calls))
        self.echo(self.device.calls[-1].identity,target=22.5,action=Action.STOP)
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')
        self.assertEqual(self.backend.status(True)['status']['mode'],'MANUAL_PAUSE')
        self.assertTrue(self.executor.status()['uncertain'])

    async def test_grid_phase_and_kws_fault_preempt_pending_heat(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        f=frame(self.clock.utc)
        self.backend.accept_voltage(replace(f,phases=tuple(replace(v,value_v=180) for v in f.phases),
            feed=replace(f.feed,kws_online=False)))
        await self.until(lambda:len(self.device.calls)==2)
        self.assertFalse(self.device.calls[-1].positive)
        self.echo(self.device.calls[-1].identity,target=22.5,action=Action.STOP)
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')

    async def test_lowered_dynamic_upper_and_ownership_loss_cancel_delayed_command(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p));self.device.send_gate.clear()
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:self.executor.status()['pending'] is not None)
        self.limit=replace(self.limit,upper_c=21.9,comfort_target_c=21.9)
        self.device.exclusive=False  # Simulated external writer: no competing withdrawal.
        self.device.send_gate.set()
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')
        self.assertEqual(self.device.calls,[])

    async def test_restart_never_replays_pending_or_accepts_old_echo(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        old=self.device.calls[0]
        self.backend.reboot()
        restarted=ThermostatExecutor(self.backend,self.device,enabled=True)
        self.addCleanup(restarted.close)
        self.assertTrue(restarted.status()['uncertain'])
        self.assertFalse(restarted.activate(self.credential,p))
        self.echo(old.identity,target=24.5)
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')
        self.assertEqual(len(self.device.calls),1)

    async def test_stale_room_local_temperature_and_manual_auto_deny_activation(self):
        p=self.proposal()
        self.clock.advance(31)
        self.assertFalse(self.executor.activate(self.credential,p))
        self.device.observe_temperature(23,qualified=True)
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        self.assertFalse(self.executor.activate(self.credential,p))
        self.device.mode='AUTO'
        self.assertFalse(self.executor.activate(self.credential,p))
        self.assertEqual(self.device.calls,[])

    async def test_one_shot_claim_is_durable_and_cannot_send_twice(self):
        state=self.backend.status(True)
        body=dict(entry_id='synthetic-entry',version=[2,0],boot_id=state['status']['boot_id'],
            generation=state['generation'],owner_epoch=state['status']['owner_epoch'],kind='arm',request_id='synthetic-arm')
        self.assertEqual(self.backend.dispatch('control',body,True)['status'],'accepted_fake')
        p=self.proposal(one_shot=True);self.assertTrue(self.executor.activate(self.credential,p))
        self.assertEqual((await self.complete(p))['status'],'echoed_mock')
        self.assertEqual(len(self.executor.status()['one_shots']),1)
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        new=self.proposal(one_shot=True);self.assertTrue(self.executor.activate(self.credential,new))
        self.assertEqual((await self.executor.execute(new))['status'],'blocked')
        self.assertEqual(len(self.device.calls),1)

    async def reject_independent_echo(self, *, stale=False, qualified=True, **changes):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        if not stale:self.clock.advance(.001)
        args=dict(command_id=self.device.calls[0].identity,mode='HEAT',target=24.5,
                  echo_action=Action.HEAT,qualified=qualified)
        self.device.device_report(**(args|changes))
        result=await asyncio.wait_for(task,2)
        self.assertEqual(result['status'],'uncertain')
        self.assertFalse(result['physical_ack'])

    async def test_stale_matching_echo_is_not_ack(self):
        await self.reject_independent_echo(stale=True)

    async def test_readback_requires_separate_device_evidence(self):
        await self.reject_independent_echo(qualified=False)

    async def test_fresh_external_override_is_not_ack(self):
        await self.reject_independent_echo(manual=True)
        self.assertEqual(len(self.device.calls),1)  # Never fight a reported manual owner.

    async def test_authentication_loss_and_auto_during_pending_readback(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.device.authenticated=False;self.device.mode='AUTO'
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')
        self.assertEqual(len(self.device.calls),1)  # No second writer fights AUTO.

    async def test_lowered_ceiling_alone_preempts_delayed_high_target(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p));self.device.send_gate.clear()
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:self.executor.status()['pending'] is not None)
        self.limit=replace(self.limit,upper_c=21.9,comfort_target_c=21.9)
        self.device.send_gate.set()
        await self.until(lambda:bool(self.device.calls))
        self.assertTrue(all(not c.positive for c in self.device.calls))
        self.assertLessEqual(self.device.calls[-1].target,24)
        self.echo(self.device.calls[-1].identity,target=22.5,action=Action.STOP)
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')

    async def test_readback_never_renews_thermostat_temperature_timestamp(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        observed=self.device.temperature_at
        self.clock.advance(20)
        self.assertEqual((await self.complete(p))['status'],'echoed_mock')
        self.assertEqual(self.device.temperature_at,observed)
        self.assertEqual(self.backend._thermostat_seen.utc,observed)
        self.clock.advance(11)
        self.assertFalse(self.device.fresh())

    async def test_late_echo_cannot_clear_uncertainty_or_reheat(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        result=await asyncio.wait_for(self.executor.execute(p),2)
        self.assertEqual(result['status'],'uncertain')
        count=len(self.device.calls)
        self.echo(self.device.calls[0].identity,target=24.5)
        self.assertEqual((await self.executor.execute(p))['status'],'uncertain')
        self.assertTrue(self.executor.status()['uncertain'])
        self.assertEqual(len(self.device.calls),count)

    async def test_owner_identity_change_cannot_reuse_epoch_or_authorize_withdrawal(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.evidence=replace(self.evidence,owner='synthetic.new-owner')
        self.clock.advance(.2)
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')
        self.assertEqual(len(self.device.calls),1)
        other=self.device.credential('synthetic.new-owner')
        self.assertFalse(self.executor.activate(other,p))

    async def test_revoked_actuator_lease_cannot_accept_even_matching_readback(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        task=asyncio.create_task(self.executor.execute(p))
        await self.until(lambda:bool(self.device.calls))
        self.device.actuator.release(self.executor.token)
        self.echo(self.device.calls[0].identity,target=24.5)
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain')
        self.assertTrue(self.executor.status()['uncertain'])
        self.assertEqual(len(self.device.calls),1)

    async def test_on_time_readback_survives_delayed_sent_ledger_processing(self):
        await self.check_delayed_sent_processing(late=False)

    async def test_late_readback_during_delayed_sent_processing_is_rejected(self):
        await self.check_delayed_sent_processing(late=True)

    async def check_delayed_sent_processing(self, *, late):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        entered,release=Event(),Event()
        record=self.executor._record
        def delayed_record(command,status):
            if status=='sent':
                entered.set()
                if not release.wait(1):raise RuntimeError('test release deadline')
            return record(command,status)
        self.executor._record=delayed_record
        task=asyncio.create_task(self.executor.execute(p))
        try:
            await self.until(entered.is_set)
            if late:self.clock.advance(.2)
            self.echo(self.device.calls[0].identity,target=24.5)
            if not late:self.clock.advance(.2)  # On-time arrival, deferred processing.
        finally:
            release.set()
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'uncertain' if late else 'echoed_mock')
        self.assertEqual(self.device.temperature_at,self.clock.utc-.201)

    async def test_invalid_persisted_ledger_cannot_activate(self):
        p=self.proposal()
        with self.backend.critical.transaction() as con:
            row=self.executor.status();row['pending']=['invalid-reference']
            self.backend.critical.write(con,self.executor.KEY,row)
        broken=ThermostatExecutor(self.backend,self.device,enabled=True)
        self.addCleanup(broken.close)
        self.assertTrue(broken.broken)
        self.assertFalse(broken.activate(self.credential,p))
        self.assertEqual(self.device.calls,[])

    async def test_persistence_failure_before_claim_and_capability_failure_never_dispatch(self):
        p=self.proposal();self.assertTrue(self.executor.activate(self.credential,p))
        def fail(point):raise OSError('synthetic disk fault')
        self.backend.critical.hook=fail
        self.assertEqual((await self.executor.execute(p))['status'],'blocked')
        self.backend.critical.hook=None
        self.assertEqual(self.device.calls,[])
        self.device.step=1
        self.assertFalse(self.executor.activate(self.credential,p))
