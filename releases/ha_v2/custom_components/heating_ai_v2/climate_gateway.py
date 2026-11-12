"""One native climate boundary; HA acceptance/echo is never physical ACK.

Only a trusted server callback can supply a future commissioned witness. The
installed controller supplies None unconditionally: no UI/option activation.
"""
import asyncio
import json
import time
from .engine.contracts import Action, to_json
from .engine.ha_native.thermostat import finalize_heat_setpoint


class ClimateGateway:
    def __init__(self, ledger, entity_id, service, readback, witness):
        self.ledger, self.entity_id = ledger, entity_id
        self.service, self.readback, self.witness = service, readback, witness
        self.stopped = True
        self.lock = asyncio.Lock()

    @property
    def physical_commands_enabled(self):
        return False  # No commissioned activation implementation exists in this release.

    async def execute(self, intent):
        # Do not grow an unqualified activation path merely to make a fake send pass.
        if not self.physical_commands_enabled or self.stopped or self.witness() is None:
            return dict(stage='DENIED', reason='exclusive_signed_handoff_missing', physical_ack=False)
        return await self._commissioned_send(intent)

    async def _commissioned_send(self, intent):
        """Future server-only path; deliberately unreachable from installed runtime."""
        async with self.lock:
            witness = self.witness()
            if not witness or self.stopped:
                return dict(stage='DENIED', physical_ack=False)
            status = await asyncio.to_thread(self.ledger.status)
            def current():
                other = self.witness()
                return (other == witness and not self.stopped and witness['expires_at'] > time.time()
                        and witness['independent_safety'] is True and witness['physical_authorized'] is True
                        and witness['exclusive'] is True and witness['manual_stop'] is False
                        and intent.boot_id == status['boot_id'] == witness['boot_id']
                        and intent.owner_epoch == status['owner_epoch'] == witness['owner_epoch']
                        and status['owner_id'] == witness['owner_id'] and not status['fenced']
                        and intent.snapshot_id == witness['snapshot_id']
                        and intent.not_before <= time.time() < intent.expires_at)
            if not current():
                return dict(stage='DENIED', physical_ack=False)
            proposal = finalize_heat_setpoint(**witness['thermostat_inputs'])
            expected_action = 'request_heat' if intent.action is Action.HEAT else 'withdraw_demand'
            if not proposal or proposal.get('action') != expected_action:
                return dict(stage='DENIED', physical_ack=False)
            target = proposal['setpoint_c']
            identity = dict(owner_id=status['owner_id'], boot_id=status['boot_id'], owner_epoch=status['owner_epoch'])
            request = dict(version=1, intent=json.loads(to_json(intent)), entity_id=self.entity_id,
                           service='set_temperature', data=dict(temperature=target))
            claimed = await asyncio.to_thread(self.ledger.prepare, intent.intent_id,
                'HEAT' if intent.action is Action.HEAT else 'STOP', request,
                expected_revision=status['revision'], **identity)
            if not claimed['created']:
                return dict(stage=claimed['command']['stage'], duplicate=True, physical_ack=False)
            revision = claimed['revision']
            try:
                deadline = asyncio.get_running_loop().time()+5
                if not current():
                    raise RuntimeError('Authority changed')
                sent = time.time()
                # Persist service initiation before allowing any service side effect.
                await asyncio.to_thread(self.ledger.record_sent, intent.intent_id, at=sent,
                                        expected_revision=revision, **identity)
                revision += 1
                if not current():
                    raise RuntimeError('Preempted')
                context = await asyncio.wait_for(self.service(self.entity_id, target),
                    max(0, deadline-asyncio.get_running_loop().time()))
                if not current():
                    raise RuntimeError('Preempted')
                echo = await asyncio.wait_for(self.readback(self.entity_id, sent, context),
                    max(0, deadline-asyncio.get_running_loop().time()))
                if (not current() or echo['entity_id'] != self.entity_id or echo['mode'] != 'heat'
                        or echo['temperature'] != target or echo['context_id'] != context
                        or not sent < echo['at'] <= time.time()):
                    raise RuntimeError('Foreign/contradictory HA observation')
                await asyncio.to_thread(self.ledger.record_ha_echo, intent.intent_id, at=echo['at'],
                                        expected_revision=revision, **identity)
                return dict(stage='HA_ECHO', physical_ack=False, contacts_open=None)
            except (Exception, asyncio.CancelledError):
                self.stopped = True
                try:
                    await asyncio.to_thread(self.ledger.fence, expected_revision=revision, **identity)
                except Exception:
                    pass  # No grant/retry even if persistence itself has failed.
                return dict(stage='UNKNOWN', physical_ack=False, contacts_open=None)


async def ha_service(hass, entity_id, target):
    """Only thermostat temperature; never KWS, pumps, fan or vendor AUTO."""
    from homeassistant.core import Context
    context = Context()
    await hass.services.async_call('climate', 'set_temperature',
        {'entity_id': entity_id, 'temperature': target}, blocking=True, context=context)
    return context.id


async def ha_readback(hass, entity_id, after, context_id):
    ready = asyncio.Event()
    def changed(event):
        if event.data.get('entity_id') == entity_id:
            ready.set()
    remove = hass.bus.async_listen('state_changed', changed)
    try:
        async with asyncio.timeout(5):
            while True:
                ready.clear()
                state = hass.states.get(entity_id)
                if state and state.last_updated.timestamp() > after:
                    return dict(entity_id=entity_id, mode=state.state,
                        temperature=state.attributes.get('temperature'),
                        context_id=state.context.id, at=state.last_updated.timestamp())
                await ready.wait()
    finally:
        remove()
