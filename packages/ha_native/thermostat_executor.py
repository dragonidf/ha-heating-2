"""One mock-only native writer. Real HA transport/physical ACK remain BLOCKED."""
from __future__ import annotations
import asyncio
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable
from uuid import uuid4
from packages.contracts import Action, Clock, ControlState
from packages.simulator.engine import FakeActuator, FakeObservation
from .backend import NativeBackend, obj, integer, number
from .store import JSON, StoreError, encode


@dataclass(frozen=True)
class MockCredential:
    issuer: object
    principal: str


@dataclass(frozen=True)
class ThermostatCommand:
    identity: str
    boot_id: str
    owner_epoch: int
    target: float
    positive: bool
    issued_at: float


@dataclass(frozen=True)
class MockReadback:
    proof: FakeObservation
    command_id: str
    mode: str
    target: float
    origin: str = 'synthetic_device_readback'
    device_evidence_qualified: bool = False


class IsolatedClimateMock:
    """RAM only, separate explicit device reports; send never fabricates readback."""
    def __init__(self, clock: Callable[[], Clock]):
        self.clock = clock
        self.actuator = FakeActuator()
        self._issuer = object()
        self.authenticated = True
        self.exclusive = True
        self.mapping_qualified = False
        self.minimum, self.maximum, self.step = 5.0, 35.0, .5
        self.temperature: float | None = None
        self.temperature_at: float | None = None
        self.temperature_boot: str | None = None
        self.temperature_clock: Clock | None = None
        self.mode = 'UNKNOWN'
        self.generation = 0
        self._bound: ControlState | None = None
        self.calls: list[ThermostatCommand] = []
        self.send_gate = asyncio.Event();self.send_gate.set()
        self.sent = asyncio.Event()
        self.reports: asyncio.Queue[MockReadback] = asyncio.Queue()
        self.drop = False
        self.noop = False

    def credential(self, principal: str) -> MockCredential:
        if not principal.startswith('synthetic.'):
            raise ValueError('Synthetic principal only')
        return MockCredential(self._issuer,principal)

    def accepts(self, credential: MockCredential | None) -> bool:
        return (type(credential) is MockCredential and credential.issuer is self._issuer
                and credential.principal.startswith('synthetic.') and self.authenticated and self.exclusive)

    def observe_temperature(self, value: float, *, qualified: bool = False) -> None:
        number(value)
        clock=self.clock()
        self.temperature = value if qualified else None
        self.temperature_at = clock.utc if qualified else None
        self.temperature_boot = clock.boot_id if qualified else None
        self.temperature_clock = clock if qualified else None

    def fresh(self) -> bool:
        clock=self.clock()
        return (self.mapping_qualified and self.mode=='HEAT' and self.temperature is not None
            and self.temperature_at is not None and self.temperature_boot==clock.boot_id
            and 0 <= clock.utc-self.temperature_at <= 30 and self.temperature_clock is not None
            and 0 <= clock.monotonic-self.temperature_clock.monotonic <= 30 and self.minimum<self.maximum and self.step==.5)

    def fence(self, token: object, clock: Clock, epoch: int) -> int:
        self.generation+=1
        state=ControlState(boot_id=clock.boot_id,owner_epoch=epoch)
        self.actuator.fence(token,state,self.generation)
        self._bound=state
        return self.generation

    def owns(self, token: object) -> bool:
        if self._bound is None:return False
        try:
            # Idempotent existing FakeActuator fence verifies the live reservation.
            self.actuator.fence(token,self._bound,self.generation)
            return True
        except RuntimeError:
            return False

    async def send(self, token: object, generation: int, command: ThermostatCommand, admit: Callable[[], bool]) -> bool:
        await self.send_gate.wait()
        if not admit():
            return False
        self.calls.append(command);self.sent.set()
        if self.drop:
            return True  # Service returned, device outcome still unknown.
        if self.noop:
            return True
        return self.actuator.send(token,generation,Action.HEAT if command.positive else Action.STOP,0,self.clock())

    def device_report(self, command_id: str, *, mode: str, target: float, echo_action: Action,
                      qualified: bool=False, manual: bool=False, writers_known: bool=True,
                      origin: str='synthetic_device_readback') -> None:
        # All observed fields are explicit independent fixture input, never a send echo.
        proof=self.actuator.feedback(echo_action,self.clock(),manual=manual,writers_known=writers_known)
        self.reports.put_nowait(MockReadback(proof,command_id,mode,target,origin,qualified))


class ThermostatExecutor:
    """Inert by default; only the exact closed mock can ever receive commands."""
    physical_commands_enabled = False
    KEY='thermostat_executor_v1'

    def __init__(self, backend: NativeBackend, transport: IsolatedClimateMock, *, enabled: bool=False, timeout_s: float=1):
        if type(transport) is not IsolatedClimateMock or type(enabled) is not bool:
            raise ValueError('Real transports are BLOCKED')
        if not 0 < number(timeout_s) <= 30:
            raise ValueError('Invalid readback timeout')
        self.backend,self.transport,self.enabled,self.timeout_s=backend,transport,enabled,timeout_s
        self.writer='synthetic.executor.'+uuid4().hex
        self.token: object | None=None
        self.credential: MockCredential | None=None
        self.boot='';self.epoch=-1
        self._lock=asyncio.Lock()
        self.broken=False
        try:
            with backend.critical.transaction() as con:
                if not con.execute('SELECT 1 FROM records WHERE name=?',(self.KEY,)).fetchone():
                    backend.critical.write(con,self.KEY,dict(version=1,boot=backend.trusted_clock().boot_id,
                        holder=None,pending=None,uncertain=False,receipts={},one_shots={}))
                row=self._row(backend.critical.read_from(con,self.KEY))
                if row['boot'] != backend.trusted_clock().boot_id:
                    if row['pending'] is not None:
                        obj(obj(row['receipts'])[str(row['pending'])])['status']='uncertain'
                        row['uncertain']=True
                    row['boot']=backend.trusted_clock().boot_id;row['holder']=None;row['pending']=None
                    backend.critical.write(con,self.KEY,row)
        except (StoreError,ValueError):
            self.broken=True

    @staticmethod
    def _row(raw: JSON) -> dict[str,JSON]:
        row=obj(raw)
        if (set(row)!= {'version','boot','holder','pending','uncertain','receipts','one_shots'} or type(row['version']) is not int or row['version']!=1
                or type(row['uncertain']) is not bool or len(obj(row['receipts']))>256):
            raise StoreError('Invalid executor ledger')
        obj(row['one_shots'])
        if (not isinstance(row['boot'],str) or row['holder'] is not None and not isinstance(row['holder'],str)
                or row['pending'] is not None and not isinstance(row['pending'],str)
                or row['pending'] is not None and row['pending'] not in obj(row['receipts'])
                or len(obj(row['one_shots']))>256):
            raise StoreError('Invalid executor lease/pending state')
        for receipt in obj(row['receipts']).values():
            r=obj(receipt)
            if (set(r)!= {'status','physical_ack','contacts_open','boot','epoch','target','positive'}
                    or r['status'] not in ('prepared','sent','uncertain','echoed_mock') or r['physical_ack'] is not False
                    or r['contacts_open'] is not None or type(r['positive']) is not bool or not isinstance(r['boot'],str)):
                raise StoreError('Invalid executor receipt')
            integer(r['epoch']);number(r['target'])
        if any(not isinstance(cid,str) or cid not in obj(row['receipts']) for cid in obj(row['one_shots']).values()):
            raise StoreError('Invalid one-shot claim')
        return row

    def status(self) -> dict[str,JSON]:
        return self._row(self.backend.critical.read(self.KEY))

    def activate(self, credential: MockCredential, proposal: dict[str,JSON]) -> bool:
        if not self.enabled or self.broken or not self.transport.accepts(credential) or self.backend._health_evidence().owner != credential.principal or not self.transport.fresh():
            return False
        if proposal.get('action')!='request_heat' or not self._validate(proposal):
            return False
        try:
            with self.backend.critical.transaction() as con:
                row=self._row(self.backend.critical.read_from(con,self.KEY))
                if row['holder'] not in (None,self.writer) or row['uncertain'] or row['pending'] is not None:
                    return False
                if self.token is None:
                    self.token=self.transport.actuator.reserve()
                row['holder']=self.writer
                self.backend.critical.write(con,self.KEY,row)
            clock=self.backend.trusted_clock()
            self.credential=credential;self.boot=clock.boot_id;self.epoch=integer(proposal.get('owner_epoch'))
            self.transport.fence(self.token,clock,self.epoch)
            return True
        except (StoreError,ValueError,RuntimeError):
            self.broken=True
            return False

    def _validate(self, proposal: dict[str,JSON]) -> bool:
        t=self.transport
        return (t.fresh() and t.temperature is not None and self.backend.revalidate_thermostat_proposal(proposal,
            thermostat_c=t.temperature,minimum=t.minimum,maximum=t.maximum,step=t.step,observed_at=number(t.temperature_at)))

    def _live(self, command: ThermostatCommand, proposal: dict[str,JSON]) -> bool:
        if (self.broken or self.token is None or not self.transport.owns(self.token) or not self.transport.accepts(self.credential)
                or self.credential is None or self.backend._health_evidence().owner != self.credential.principal or not self.transport.fresh()):
            return False
        state=self.backend.status(True)
        if (state['status'] is None or command.boot_id!=self.backend.trusted_clock().boot_id
                or command.owner_epoch!=obj(state['status'])['owner_epoch'] or self.status()['holder']!=self.writer):
            return False
        return self._validate(proposal) if command.positive or self.backend.issued_thermostat_request(proposal) is not None else self.backend.executor_withdrawal(
            owner_epoch=command.owner_epoch,thermostat_c=number(self.transport.temperature),
            minimum=self.transport.minimum,maximum=self.transport.maximum,step=self.transport.step) == proposal

    def _claim(self, command: ThermostatCommand, one_shot: str | None, safety: bool) -> dict[str,JSON] | None:
        with self.backend.critical.transaction() as con:
            row=self._row(self.backend.critical.read_from(con,self.KEY));receipts=obj(row['receipts'])
            if row['holder']!=self.writer:
                raise StoreError('Writer revoked')
            if command.identity in receipts:
                return obj(receipts[command.identity])
            if (not safety and (row['pending'] is not None or row['uncertain'])
                    or len(receipts)>=256 or one_shot is not None and one_shot in obj(row['one_shots'])):
                return dict(status='blocked',physical_ack=False,contacts_open=None)
            if safety and row['pending'] is not None:
                obj(receipts[str(row['pending'])])['status']='uncertain'
                row['uncertain']=True
            receipts[command.identity]=dict(status='prepared',physical_ack=False,contacts_open=None,
                boot=command.boot_id,epoch=command.owner_epoch,target=command.target,positive=command.positive)
            if one_shot is not None:obj(row['one_shots'])[one_shot]=command.identity
            row['pending']=command.identity
            self.backend.critical.write(con,self.KEY,row)
        verified=self.status()
        if verified['pending']!=command.identity:
            raise StoreError('Claim readback mismatch')
        return None

    def _record(self, command: ThermostatCommand, status: str) -> dict[str,JSON]:
        with self.backend.critical.transaction() as con:
            row=self._row(self.backend.critical.read_from(con,self.KEY))
            if row['holder']!=self.writer or row['pending']!=command.identity:
                raise StoreError('Superseded receipt')
            record=obj(obj(row['receipts'])[command.identity]);record['status']=status
            if status in ('uncertain','echoed_mock'):
                row['pending']=None
            if status=='uncertain':row['uncertain']=True
            self.backend.critical.write(con,self.KEY,row)
        return obj(obj(self.status()['receipts'])[command.identity])

    async def _wait(self, task: asyncio.Task[object], command: ThermostatCommand,
                    proposal: dict[str,JSON], start: Clock, deadline: float) -> object:
        while True:
            if not self._live(command,proposal):raise RuntimeError('Preempted')
            remaining=min(deadline-asyncio.get_running_loop().time(),self.timeout_s-(self.backend.trusted_clock().monotonic-start.monotonic))
            if remaining<=0:raise TimeoutError('Readback deadline')
            done,_=await asyncio.wait({task},timeout=min(.01,remaining))
            if done:
                if not self._live(command,proposal):raise RuntimeError('Preempted')
                return task.result()

    def _echo_valid(self, echo: MockReadback, command: ThermostatCommand) -> bool:
        clock=self.backend.trusted_clock()
        state=ControlState(boot_id=command.boot_id,owner_epoch=command.owner_epoch)
        return (echo.origin=='synthetic_device_readback' and echo.device_evidence_qualified is True
            and echo.command_id==command.identity and echo.mode=='HEAT' and echo.target==command.target
            and not echo.proof.manual and echo.proof.writers_known and command.issued_at<echo.proof.at<=clock.utc
            and echo.proof.action==(Action.HEAT if command.positive else Action.STOP)
            and self.transport.actuator.accepts(echo.proof,state,clock,30,0))

    async def _perform(self, proposal: dict[str,JSON], *, safety: bool=False) -> dict[str,JSON]:
        clock=self.backend.trusted_clock()
        identity=sha256(encode(dict(boot=clock.boot_id,proposal=proposal)).encode()).hexdigest()
        command=ThermostatCommand(identity,clock.boot_id,integer(proposal.get('owner_epoch')),
                                  number(proposal.get('setpoint_c')),proposal.get('action')=='request_heat',clock.utc)
        request=self.backend.issued_thermostat_request(proposal)
        shot=obj(self.backend.status(True)['oneShot'])
        ticket=encode(dict(expires=shot['expires'],grid_epoch=shot['gridEpoch'])) if command.positive and request is not None and request[2] else None
        cached=await asyncio.to_thread(self._claim,command,ticket,safety)
        if cached is not None:return cached
        pending: asyncio.Task[object] | None=None
        try:
            if not self._live(command,proposal):raise RuntimeError('Preempted')
            if self.token is None:raise RuntimeError('No lease')
            generation=self.transport.fence(self.token,clock,command.owner_epoch)
            deadline=asyncio.get_running_loop().time()+self.timeout_s
            pending=asyncio.create_task(self.transport.send(self.token,generation,command,lambda:self._live(command,proposal)))
            sent=await self._wait(pending,command,proposal,clock,deadline)
            if sent is not True:raise RuntimeError('Send rejected')
            await asyncio.to_thread(self._record,command,'sent')
            pending=asyncio.create_task(self.transport.reports.get())
            echo=await self._wait(pending,command,proposal,clock,deadline)
            if isinstance(echo,MockReadback) and (echo.proof.manual or not echo.proof.writers_known or echo.mode!='HEAT'):
                self.credential=None  # Do not fight an external/manual/AUTO writer.
            if not isinstance(echo,MockReadback) or not self._echo_valid(echo,command):raise RuntimeError('Contradictory/unqualified readback')
            return await asyncio.to_thread(self._record,command,'echoed_mock')
        except (RuntimeError,TimeoutError,StoreError,ValueError,asyncio.CancelledError):
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending,return_exceptions=True)
            try:result=await asyncio.to_thread(self._record,command,'uncertain')
            except (StoreError,ValueError):
                self.broken=True;result=dict(status='uncertain',physical_ack=False,contacts_open=None)
            if command.positive:
                await self._safe_withdraw()
            return result

    async def _safe_withdraw(self) -> None:
        if self.token is None:return
        clock=self.backend.trusted_clock()
        epoch=integer(obj(self.backend.status(True)['status'])['owner_epoch'])
        try:
            self.transport.fence(self.token,clock,epoch)  # Revoke any queued old generation.
        except RuntimeError:
            self.broken=True
            return
        if (not self.transport.accepts(self.credential) or self.credential is None
                or self.backend._health_evidence().owner != self.credential.principal or not self.transport.fresh()):return
        if not await asyncio.to_thread(self.backend.flush_stop):
            self.broken=True
            return
        epoch=integer(obj(self.backend.status(True)['status'])['owner_epoch'])
        p=self.backend.executor_withdrawal(owner_epoch=epoch,thermostat_c=number(self.transport.temperature),
            minimum=self.transport.minimum,maximum=self.transport.maximum,step=self.transport.step)
        if p is not None and p.get('action')=='withdraw_demand':
            try:await self._perform(p,safety=True)
            except (StoreError,ValueError,RuntimeError):self.broken=True

    async def execute(self, proposal: dict[str,JSON]) -> dict[str,JSON]:
        proposal=deepcopy(proposal)
        if self._lock.locked() or self.token is None or not self.enabled or self.broken:
            return dict(status='blocked',physical_ack=False,contacts_open=None)
        async with self._lock:
            try:
                clock=self.backend.trusted_clock()
                if clock.boot_id!=self.boot or integer(proposal.get('owner_epoch'))!=self.epoch or not self._validate(proposal):
                    return dict(status='blocked',physical_ack=False,contacts_open=None)
                return await self._perform(proposal)
            except (StoreError,ValueError,RuntimeError):
                self.broken=True
                return dict(status='blocked',physical_ack=False,contacts_open=None)

    def close(self) -> None:
        if self.token is not None:
            self.transport.actuator.release(self.token);self.token=None
        try:
            with self.backend.critical.transaction() as con:
                row=self._row(self.backend.critical.read_from(con,self.KEY))
                if row['holder']==self.writer:
                    if row['pending'] is not None:row['uncertain']=True
                    row['holder']=None
                    self.backend.critical.write(con,self.KEY,row)
        except (StoreError,ValueError):self.broken=True
