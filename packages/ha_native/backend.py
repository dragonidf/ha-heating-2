"""Authoritative synthetic-only panel service; no HA imports or actuator transport."""
from __future__ import annotations

import math
import re
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from threading import RLock
from typing import Callable, cast
from uuid import uuid4
from time import monotonic

from packages.contracts import Clock, ControlState, ControlPolicy, ControlMode, HeatPermit, Unit
from packages.control import evaluate
from packages.ha_fake.adapter import SourceAdapter
from packages.offline.contracts import Binding, Registry, SourceEvent, EnergySlice
from packages.offline.codec import encode as encode_contract, decode as decode_contract

from .store import JSON as JSON, NativeStore, StoreError, decode, encode
from .health import HealthPolicy, HealthInputs, HealthMemory, project_health, SourceTimingPolicy
from .source_activity import SourceActivity, DeviceReport
from .passive_bridge import IntegrationReport
from .thermostat import ActiveRoomLimit, supported_ceiling, finalize_heat_setpoint
from .voltage import VoltageFrame, VoltagePolicy, VoltageState, evaluate_voltage, voltage_view, synthetic_voltage_withdrawal
from .kws import KWSFrame, KWSState, project_kws, kws_view, kws_counter_energy


VOLTAGE_DEFAULTS: dict[str, JSON] = {
    'min_voltage_v': 190, 'max_voltage_v': 250, 'hysteresis_v': 5,
    'stable_recovery_s': 30, 'voltage_max_age_s': 30,
}


class NativeProtocolError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def obj(value: JSON) -> dict[str, JSON]:
    if not isinstance(value, dict):
        raise NativeProtocolError('invalid_payload')
    return value


def integer(value: JSON, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value < 2**53:
        raise NativeProtocolError('invalid_integer')
    return value


def number(value: JSON) -> float:
    if type(value) not in (int, float) or not math.isfinite(cast(float, value)):
        raise NativeProtocolError('invalid_number')
    return float(cast(float, value))


def settings_valid(values: JSON) -> bool:
    legacy = {
        'day', 'night', 'budget', 'windowStart', 'windowEnd', 'strategy',
        'mode', 'circulation', 'fan', 'scenario', 'freshness', 'aiAdvice',
    }
    if not isinstance(values, dict) or set(values) not in (legacy, legacy | set(VOLTAGE_DEFAULTS)):
        return False
    try:
        if set(VOLTAGE_DEFAULTS) <= set(values):
            low, high, hysteresis, recovery, max_age = (number(values[k]) for k in VOLTAGE_DEFAULTS)
            if not (80 <= low <= 280 and 120 <= high <= 300 and low < high
                    and 0 <= hysteresis <= 30 and 2 * hysteresis < high - low
                    and 0 <= recovery <= 600 and 1 <= max_age <= 300):
                return False
        day, night = number(values['day']), number(values['night'])
        budget, fan, freshness = (number(values[k]) for k in ('budget', 'fan', 'freshness'))
        start, end = values['windowStart'], values['windowEnd']
        return (16 <= night <= day <= 26 and (day * 2).is_integer() and (night * 2).is_integer()
                and 0 <= budget <= 2000 and 0 <= fan <= 100 and fan.is_integer()
                and 5 <= freshness <= 300
                and isinstance(start, str) and isinstance(end, str) and start != end
                and re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', start) is not None
                and re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', end) is not None
                and values['strategy'] in ('comfort', 'balanced', 'economy')
                and values['mode'] in ('auto', 'observation')
                and values['circulation'] in ('auto', 'manual', 'stop')
                and type(values['scenario']) in (int, float) and values['scenario'] in (3, 6, 9)
                and type(values['aiAdvice']) is bool)
    except NativeProtocolError:
        return False


class NativeBackend:
    """Only trusted SDK code supplies enabled/admin. Payload flags cannot grant either."""
    def __init__(self, root: Path, fixture: dict[str, JSON] | None = None, *,
                 entry_id: str = 'synthetic-entry', enabled: bool = False,
                 clock: Callable[[], tuple[float, float]] | None = None,
                 effective_room_limit: Callable[[], ActiveRoomLimit | None] = lambda: None,
                 activity_window_s: float = 3660, health_policy: HealthPolicy | None = None, health_evidence: Callable[[], HealthInputs] = HealthInputs):
        if type(enabled) is not bool or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', entry_id):
            raise NativeProtocolError('invalid_configuration')
        self.fixture = deepcopy(fixture) if fixture is not None else obj(decode(Path(__file__).with_name('fixture.json').read_text()))
        encode(self.fixture)
        self.entry_id = entry_id
        self.enabled = enabled
        self.critical = NativeStore(root, 'critical')
        self.evidence = NativeStore(root, 'evidence')
        self._snapshot = deepcopy(obj(self.fixture['snapshot']))
        anchor_utc, anchor_mono = number(self._snapshot['now']), monotonic()
        self._clock = clock if clock is not None else lambda: (anchor_utc + monotonic() - anchor_mono, monotonic())
        self._last_clock: tuple[float, float] | None = None
        self._clock_bad = False
        self._room_seen_mono: float | None = None
        self._room_initial_age = 0.0
        self._room_report: tuple[float, float, str] | None = None
        self._health_policy = health_policy or HealthPolicy(recovery_s=15)
        self._health_evidence = health_evidence
        self._activity = SourceActivity(activity_window_s)
        self._activity_active = False
        self._effective_room_limit = effective_room_limit
        self._active_room_limit: ActiveRoomLimit | None = None
        self._last_ceiling_intent: dict[str, JSON] | None = None
        self._last_heat_request: tuple[float | None, bool, bool] | None = None
        self._issued_thermostat_owner: str | None = None
        self._thermostat_caps: tuple[float | None, float | None, float | None] = (None,None,None)
        self._thermostat_seen: Clock | None = None
        self._thermostat_fresh = False
        self._thermostat_mode = 'UNKNOWN'
        self._health_memory = HealthMemory()
        self._memory = RLock()
        self._serial = 0
        self._source_max_age = 30.0
        self._adapter = self._source_adapter(30)
        self._stop_receipts: dict[str, JSON] = {}
        self._opened = False
        self._pending_stop = False
        self._store_failed = False
        self._model: dict[str, JSON] = {'revision': 3, 'candidate': False, 'frozen': False}
        self._settings_values: dict[str, JSON] = {}
        self._voltage_frame = VoltageFrame()
        self._voltage_state: VoltageState | None = None
        self._kws_frame = KWSFrame()
        self._kws_state: KWSState | None = None
        self._counter_left: KWSFrame | None = None
        self._counter_epoch = 0
        self._energy_pending: list[EnergySlice] = []
        self._energy_ledger: list[EnergySlice] = []
        self._energy_unavailable = False

    def open(self) -> None:
        self._opened = False
        self._last_clock = None
        self._clock_bad = False
        self._room_seen_mono = None
        self._room_report = None
        self._activity = SourceActivity(self._activity.window_s)
        self._activity_active = False
        self._active_room_limit = None
        self._last_ceiling_intent = None
        self._last_heat_request = None
        self._issued_thermostat_owner = None
        self._thermostat_caps = (None,None,None)
        self._thermostat_seen = None
        self._thermostat_fresh = False
        self._thermostat_mode = 'UNKNOWN'
        self._voltage_frame = VoltageFrame()
        self._voltage_state = None
        self._kws_frame = KWSFrame()
        self._kws_state = None
        self._counter_left = None
        self._energy_pending = []
        self._energy_ledger = []
        self._energy_unavailable = False
        self._store_failed = True
        self._snapshot['permitted'] = False
        obj(self._snapshot['status'])['desired'] = 'stop_demand'
        obj(self._snapshot['status'])['mode'] = 'SAFE_HOLD'
        defaults = self.fixture.get('settings', self.fixture.get('defaults'))
        if not settings_valid(defaults):
            raise StoreError('Invalid synthetic fixture settings')
        defaults = VOLTAGE_DEFAULTS | obj(defaults)
        self.critical.open({'settings': {'revision': 1, 'values': defaults, 'lastRequest': None},
                            'settings_schema': 2,
                            'snapshot': self._snapshot, 'requests': {}, 'model': self._model})
        with self.critical.transaction() as con:
            saved = obj(self.critical.read_from(con, 'settings'))
            if not settings_valid(saved.get('values')):
                raise StoreError('Invalid stored synthetic settings')
            schema = self.critical.read_from(con, 'settings_schema') if con.execute(
                "SELECT 1 FROM records WHERE name='settings_schema'").fetchone() else 1
            if type(schema) is not int or schema not in (1, 2):
                raise StoreError('Unsupported synthetic settings schema')
            if schema == 2 and not set(VOLTAGE_DEFAULTS) <= set(obj(saved['values'])):
                raise StoreError('Incomplete synthetic settings schema')
            integer(saved.get('revision'), 1)
            self._settings_values = VOLTAGE_DEFAULTS | obj(saved['values'])
            if saved['values'] != self._settings_values:
                saved['values'] = self._settings_values
                self.critical.write(con, 'settings', saved)
            self.critical.write(con, 'settings_schema', 2)
            state = deepcopy(obj(self.critical.read_from(con, 'snapshot')))
            view = obj(state['status'])
            state['generation'] = integer(state['generation']) + 1
            state['seq'] = integer(state['seq']) + 1
            view['boot_id'] = 'synthetic.' + uuid4().hex
            view['owner_epoch'] = integer(view['owner_epoch']) + 1
            view['status_seq'] = state['seq']
            view['actual'] = None
            view['desired'] = 'stop_demand'
            view['physical_verified'] = False
            view['receipt_stage'] = None
            view['mode'] = 'MANUAL_PAUSE' if view['mode'] == 'MANUAL_PAUSE' else 'SAFE_HOLD'
            state['room'] = {'value': None, 'observed': state['now'], 'quality': 'missing'}
            obj(state['diagnostics'])['source'] = 'unavailable'
            shot = obj(state['oneShot'])
            if shot['state'] == 'armed':
                shot['state'] = 'unknown_outcome'
            state['connected'] = True
            state['permitted'] = False
            self.critical.write(con, 'snapshot', state)
            self._model = obj(self.critical.read_from(con, 'model'))
        self._snapshot = state
        saved_veto = obj(state.get('source_freshness', {})).get('return_veto', False)
        if type(saved_veto) is not bool:
            raise StoreError('Invalid auxiliary veto')
        self._activity.veto_latched = saved_veto
        raw_health = state.get('health_memory')
        if raw_health is not None and not isinstance(raw_health, dict):
            raise StoreError('Invalid durable health memory')
        self._health_memory = HealthMemory() if raw_health is None else HealthMemory.from_record(cast(dict[str, object], raw_health))
        self._serial += 1
        self._adapter = self._source_adapter(self._source_max_age)
        self._adapter.connection(integer(state['generation']))
        # Evidence may fail independently; safety and STOP keep their own critical path.
        try:
            self.evidence.open({'fixture': self.fixture, 'kws_energy': []})
            with self.evidence.transaction() as con:
                if not con.execute("SELECT 1 FROM records WHERE name='kws_energy'").fetchone():
                    self.evidence.write(con, 'kws_energy', [])
                self._energy_ledger = self._read_energy(self.evidence.read_from(con, 'kws_energy'))
        except StoreError:
            self._energy_unavailable = True
            obj(self._snapshot['diagnostics'])['persistence'] = 'archive_unavailable'
        self._store_failed = False
        self._pending_stop = False
        self._opened = True
        self.refresh()

    def close(self) -> None:
        with self._memory:
            self._opened = False
            state = deepcopy(self._snapshot)
            self._advance(state)
            state['connected'] = False
            state['permitted'] = False
            if obj(state['status'])['mode'] != 'MANUAL_PAUSE':
                obj(state['status'])['mode'] = 'SAFE_HOLD'
            self._snapshot = state
            self._serial += 1

    def reboot(self) -> None:
        self.close()
        self.open()

    def status(self, is_admin: bool = False) -> dict[str, JSON]:
        with self._memory:
            permitted = self._can_change(is_admin)
            result = deepcopy(self._snapshot)
            result['permitted'] = permitted
            obj(result['status'])['physical_verified'] = False
            if self.safety_permit().allowed:
                raise NativeProtocolError('physical_authority_forbidden')
            return result

    def trusted_clock(self) -> Clock:
        """Trusted runtime clock; source payloads cannot choose the decision time."""
        with self._memory:
            try:
                utc, mono = self._clock()
                utc, mono = number(utc), number(mono)
                if utc < 0 or mono < 0:
                    raise NativeProtocolError('invalid_clock')
                if self._last_clock is not None and (utc < self._last_clock[0] or mono < self._last_clock[1]):
                    self._clock_bad = True
                self._last_clock = (utc, mono)
            except (ValueError, TypeError, OSError):
                self._clock_bad = True
                utc, mono = self._last_clock or (number(self._snapshot['now']), 0.0)
            return Clock(utc=utc, monotonic=mono, boot_id=str(obj(self._snapshot['status'])['boot_id']))

    def refresh(self, *, publish: bool = False) -> bool:
        """Recompute eligibility on idle time without creating an observation/report."""
        with self._memory:
            clock = self.trusted_clock()
            state = deepcopy(self._snapshot)
            previous_second = int(number(state['now']))
            state['now'] = clock.utc
            room = obj(state['room'])
            stale = self._clock_bad
            if self._room_seen_mono is not None:
                age = max(clock.utc - number(room['observed']),
                          self._room_initial_age + clock.monotonic - self._room_seen_mono)
                stale = stale or not 0 <= age <= self._source_max_age
            if stale and room['value'] is not None:
                room['quality'] = 'stale'
            source = 'clock_invalid' if self._clock_bad else ('stale' if stale else obj(state['diagnostics'])['source'])
            changed = room['quality'] != obj(self._snapshot['room'])['quality'] or source != obj(self._snapshot['diagnostics'])['source']
            obj(state['diagnostics'])['source'] = source
            try:
                active_limit = self._effective_room_limit()
                if active_limit is not None and not isinstance(active_limit, ActiveRoomLimit):
                    active_limit = None
            except (ValueError, TypeError, OSError):
                active_limit = None
            if active_limit != self._active_room_limit:
                self._active_room_limit = active_limit
                self._last_ceiling_intent = None
                changed = True

            shot = obj(state['oneShot'])
            if shot['state'] == 'armed' and shot['expires'] is not None and clock.utc >= number(shot['expires']):
                shot['state'] = 'expired'
                changed = True
            policy = self._voltage_policy()
            prior_voltage = self._voltage_state
            self._voltage_state = evaluate_voltage(policy, VoltageFrame() if self._clock_bad else self._voltage_frame, clock, prior_voltage)
            if prior_voltage is not None and (self._voltage_state.status, self._voltage_state.eligible,
                    self._voltage_state.affected_phases) != (prior_voltage.status, prior_voltage.eligible, prior_voltage.affected_phases):
                changed = True
            state['voltage'] = voltage_view(self._voltage_state, policy)
            prior_power = self._kws_state
            self._kws_state = project_kws(KWSFrame() if self._clock_bad else self._kws_frame, clock, prior_power)
            if prior_power is not None and (self._kws_state.stage, self._kws_state.power.kw, self._kws_state.counter is None) != (
                    prior_power.stage, prior_power.power.kw, prior_power.counter is None):
                changed = True
            state['power'] = kws_view(self._kws_state)
            if stale and obj(state['status'])['mode'] != 'MANUAL_PAUSE':
                obj(state['status'])['mode'] = 'SAFE_HOLD'
            changed = changed or obj(state['status'])['mode'] != obj(self._snapshot['status'])['mode']
            evidence = self._health_evidence()
            room_age = None if self._room_report is None else max(clock.utc - self._room_report[0], clock.monotonic - self._room_report[1])
            freshness = self._activity.view(clock, self._source_max_age, clock_ok=not self._clock_bad)
            freshness['measurement_authorization_age_s'] = self._source_max_age
            freshness['recovery_dwell_s'] = self._health_policy.recovery_s
            freshness['recovery_policy_ready'] = 0 < self._health_policy.recovery_s < self._source_max_age
            freshness['physical_commands_enabled'] = False
            state['source_freshness'] = freshness
            if self._activity_active:
                activity_age = freshness['device_age_s']
                room_age = number(activity_age) if activity_age is not None else None
            health_inputs = replace(evidence, room_age_s=room_age,
                room_report_verified=room_age is not None,
                room_valid=room['quality'] == 'valid' and (not self._activity_active or freshness['temperature_quality'] == 'OK'), room_report_id=self._room_report[2] if self._room_report is not None else None,
                electrical_eligible=self._voltage_state.eligible,
                electrical_reason='Напруга поза межами' if self._voltage_state.status in ('LOW', 'HIGH') else 'Мережа та KWS кваліфіковані' if self._voltage_state.eligible else 'Очікування мережі/KWS або свіжих фаз',
                electrical_fault=self._voltage_state.status in ('LOW', 'HIGH'),
                power_qualified=self._kws_state.power.kw is not None and self._kws_state.counter is not None and not self._energy_unavailable,
                clock_ok=self._opened and not self._clock_bad, persistence_ok=not self._store_failed,
                plan_ok=evidence.plan_ok and obj(state['diagnostics'])['worker'] == 'ready' and freshness['return_veto'] is not True and freshness['recovery_policy_ready'] is True,
                room_failure_confirmed=self._activity_active and freshness['failure_confirmed'] is True,
                room_silence_qualified=not self._activity_active,
                room_status=('PROBLEM' if freshness['failure_confirmed'] is True or freshness['return_veto'] is True else 'OK' if freshness['device_quality'] == 'OK' and freshness['temperature_quality'] == 'OK' and room['quality'] == 'valid' else 'WAITING') if self._activity_active else None,
                room_reason=self._activity_reason(freshness) if self._activity_active else None,
                manual_stop=evidence.manual_stop or obj(state['status'])['mode'] == 'MANUAL_PAUSE',
                one_shot_blocked=evidence.one_shot_blocked or shot['state'] in ('unknown_outcome', 'consumed', 'expired'))
            previous_memory = asdict(self._health_memory)
            health, self._health_memory = project_health(health_inputs, now=clock.utc, mono=clock.monotonic,
                boot=clock.boot_id, policy=self._health_policy, memory=self._health_memory)
            record = asdict(self._health_memory)
            changed = changed or any(v != previous_memory[k] for k, v in record.items() if k != 'last_mono')
            record['transitions'] = {k: list(v) for k, v in self._health_memory.transitions.items()}
            health['passive_sources'] = [dict(role=role, value=pair[0].value,
                last_reported=pair[0].reported_at, last_updated=pair[0].last_updated,
                last_changed=pair[0].last_changed, available=pair[0].available,
                origin='ha_state_write', physical_measurement='BLOCKED', physical_commands_enabled=False)
                for role, pair in sorted(self._activity.integration_reports.items())]
            health['source_freshness'] = freshness
            state['system_health'] = cast(JSON, health)
            state['health_memory'] = cast(JSON, record)
            if changed:
                self._advance(state)
                self._serial += 1
                self._pending_stop = self._opened
            elif publish and int(clock.utc) != previous_second:
                state['seq'] = integer(state['seq']) + 1
                obj(state['status'])['status_seq'] = state['seq']
                changed = True
            self._snapshot = state
            obj(self._snapshot['system_health'])['thermostat_ceiling'] = self._ceiling_view(clock)
            self._snapshot['demand_eligible'] = self._demand_eligible()
            return changed

    def _voltage_policy(self) -> VoltagePolicy:
        values = VOLTAGE_DEFAULTS | self._settings_values
        return VoltagePolicy(*(number(values[key]) for key in VOLTAGE_DEFAULTS))

    def accept_voltage(self, frame: VoltageFrame) -> bool:
        """SDK-authenticated synthetic upstream-voltage frame, never a service command."""
        if not isinstance(frame, VoltageFrame):
            raise NativeProtocolError('invalid_voltage_frame')
        with self._memory:
            if not self._opened:
                return False
            self._voltage_frame = frame
            self.refresh()
            state = deepcopy(self._snapshot)
            self._advance(state)
            self._snapshot = state
            self._serial += 1
            self._pending_stop = True
            return self._voltage_state is not None and self._voltage_state.eligible

    def accept_power(self, frame: KWSFrame) -> bool:
        """Qualified Tuya Local fixture observations, one total-counter lineage only."""
        if not isinstance(frame, KWSFrame):
            raise NativeProtocolError('invalid_power_frame')
        with self._memory:
            if not self._opened:
                return False
            clock = self.trusted_clock()
            current = project_kws(frame, clock, self._kws_state)
            left = self._counter_left
            if self._clock_bad or current.counter is None:
                self._counter_left = None
            elif (left is not None and left.meter_id == frame.meter_id
                    and left.provider == frame.provider and left.verification == frame.verification):
                old_total = next((r for r in left.readings if r.quantity == 'imported_energy' and r.phase == 'total'), None)
                new_total = next((r for r in frame.readings if r.quantity == 'imported_energy' and r.phase == 'total'), None)
                if old_total is not None and new_total is not None and new_total != old_total:
                    try:
                        span = kws_counter_energy(left, frame, clock,
                            'synthetic.kws.' + clock.boot_id + '.' + str(self._counter_epoch))
                        if len(self._energy_pending) >= 256:
                            raise ValueError('Bounded energy queue full')
                        self._energy_pending.append(span)
                        if span.category == 'unknown':
                            self._counter_epoch += 1
                    except ValueError:
                        self._counter_epoch += 1
                        self._energy_unavailable = True
                self._counter_left = frame
            else:
                self._counter_left = frame if current.counter is not None and not self._clock_bad else None
            self._kws_frame = frame
            self._kws_state = current
            self.refresh()
            state = deepcopy(self._snapshot)
            self._advance(state)
            self._snapshot = state
            self._serial += 1
            self._pending_stop = True
            return current.power.kw is not None

    @staticmethod
    def _read_energy(raw: JSON) -> list[EnergySlice]:
        if not isinstance(raw, list) or len(raw) > 4096:
            raise StoreError('Invalid synthetic energy ledger')
        spans: list[EnergySlice] = []
        identities: set[str] = set()
        for item in raw:
            try:
                value = decode_contract(encode(item))
            except ValueError as exc:
                raise StoreError('Invalid synthetic energy envelope') from exc
            if not isinstance(value, EnergySlice) or value.identity in identities:
                raise StoreError('Invalid synthetic energy contribution')
            if any(s.stream == value.stream and s.start < value.end and value.start < s.end for s in spans):
                raise StoreError('Overlapping synthetic meter contributions')
            spans.append(value)
            identities.add(value.identity)
        return spans

    def flush_evidence(self) -> bool:
        """Separate executor work; archive availability never gates STOP/settings."""
        with self._memory:
            pending = list(self._energy_pending)
        if not pending:
            return not self._energy_unavailable
        try:
            with self.evidence.transaction() as con:
                ledger = self._read_energy(self.evidence.read_from(con, 'kws_energy'))
                identities = {s.identity for s in ledger}
                ledger.extend(s for s in pending if s.identity not in identities)
                raw: JSON = [decode(encode_contract(s)) for s in ledger]
                self._read_energy(raw)
                self.evidence.write(con, 'kws_energy', raw)
            verified = self._read_energy(self.evidence.read('kws_energy'))
            if verified != ledger:
                raise StoreError('Energy readback not confirmed')
            with self._memory:
                self._energy_ledger = ledger
                self._energy_pending = [s for s in self._energy_pending if s not in pending]
                self._energy_unavailable = False
            return True
        except StoreError:
            self._energy_unavailable = True
            return False

    def _boiler_energy(self) -> dict[str, JSON]:
        return {'source': 'tuya_local_kws_total_counter', 'known_kwh': sum(s.kwh or 0 for s in self._energy_ledger),
                'unknown_s': sum(s.end - s.start for s in self._energy_ledger if s.category == 'unknown'),
                'interval_count': len(self._energy_ledger), 'pending': len(self._energy_pending),
                'quality': 'unavailable' if self._energy_unavailable else 'qualified_intervals' if self._energy_ledger else 'unknown',
                'scope': 'qualified_counter_intervals_only', 'physical_authority': False}

    def _demand_eligible(self) -> bool:
        return (self.enabled and self._opened and not self._clock_bad and not self._store_failed
                and obj(self._snapshot['room'])['quality'] == 'valid' and self._snapshot['grid'] is True
                and obj(self._snapshot['status'])['mode'] not in ('SAFE_HOLD', 'RECOVERING', 'MANUAL_PAUSE')
                and self._voltage_state is not None and self._voltage_state.eligible
                and obj(self._snapshot.get('source_freshness', {})).get('return_veto') is not True
                and (not self._activity_active or obj(self._snapshot['source_freshness'])['temperature_quality'] == 'OK'))

    def _ceiling_view(self, clock: Clock) -> dict[str, JSON]:
        from decimal import Decimal
        limit = self._active_room_limit
        fresh = (self._thermostat_fresh and self._thermostat_seen is not None
                 and self._thermostat_seen.boot_id == clock.boot_id
                 and 0 <= clock.utc-self._thermostat_seen.utc <= 30
                 and 0 <= clock.monotonic-self._thermostat_seen.monotonic <= 30 and not self._clock_bad)
        intent = self._last_ceiling_intent if fresh else None
        if intent is not None and (intent.get('owner_epoch') != obj(self._snapshot['status'])['owner_epoch']
                or obj(self._snapshot['status'])['mode'] == 'MANUAL_PAUSE'
                or intent.get('action') == 'request_heat' and (self._pending_stop or not self._demand_eligible()
                    or self._health_memory.operator_latched)):
            intent = None
        return dict(source_mode=limit.source_mode if limit is not None else None,
            room_upper_c=limit.upper_c if limit is not None else None,
            reserve_margin_c=limit.reserve_margin_c if limit is not None else None,
            ceiling_raw_c=float(Decimal(str(limit.upper_c))+Decimal(str(limit.reserve_margin_c))) if limit is not None and limit.qualified else None,
            proposed_ceiling_c=supported_ceiling(limit,*self._thermostat_caps),
            proposed_setpoint_c=intent.get('setpoint_c') if intent is not None else None,
            action=intent.get('action','none') if intent is not None else 'none',
            reason=intent.get('reason','unqualified') if intent is not None else 'effective_limits_or_thermostat_unqualified',
            thermostat_fresh=fresh, thermostat_mode=self._thermostat_mode,
            stage='proposed' if intent is not None else 'none', acknowledged_setpoint_c=None,
            physical_ack=False, physical_authority=False, scope='synthetic_only')

    def heat_setpoint_intent(self, *, owner_epoch: int, requested_setpoint_c: float | None,
                            planner_requests_heat: bool = False, one_shot: bool = False,
                            owns_thermostat: bool = False, thermostat_mode: str = 'UNKNOWN',
                            thermostat_fresh: bool = False, thermostat_c: float | None = None,
                            min_setpoint_c: float | None = None, max_setpoint_c: float | None = None,
                            temperature_step_c: float | None = None) -> dict[str, JSON] | None:
        """Final synthetic-only setpoint; provider is the actual effective planner limit."""
        with self._memory:
            self.refresh()
            view = obj(self._snapshot['status'])
            if (not self.enabled or not self._opened or self._clock_bad or type(owner_epoch) is not int or owner_epoch != view['owner_epoch']
                    or owns_thermostat is not True or view['mode'] == 'MANUAL_PAUSE'):
                self._last_ceiling_intent = None
                return None
            evidence = self._health_evidence()
            shot = obj(self._snapshot['oneShot'])
            room = obj(self._snapshot['room'])
            allowed = (self._can_change(True) and self._demand_eligible() and evidence.plan_ok
                and evidence.owner is not None and not self._health_memory.operator_latched
                and not evidence.manual_stop and not evidence.operator_changed_mode
                and not evidence.one_shot_blocked and shot['state'] not in ('unknown_outcome','consumed','expired')
                and (not one_shot or shot['state'] == 'armed'))
            if owner_epoch != obj(self._snapshot['status'])['owner_epoch']:
                self._last_ceiling_intent = None
                return None
            self._thermostat_caps = (min_setpoint_c,max_setpoint_c,temperature_step_c)
            self._thermostat_seen = self.trusted_clock()
            self._thermostat_fresh = thermostat_fresh is True
            self._thermostat_mode = thermostat_mode if thermostat_mode in ('HEAT','AUTO','OFF','UNKNOWN') else 'UNKNOWN'
            result = finalize_heat_setpoint(limit=self._active_room_limit,
                room_c=number(room['value']) if room['quality']=='valid' else None,
                requested_setpoint_c=requested_setpoint_c,heat_permitted=allowed,
                planner_requests_heat=planner_requests_heat,thermostat_c=thermostat_c,
                min_setpoint_c=min_setpoint_c,max_setpoint_c=max_setpoint_c,temperature_step_c=temperature_step_c,
                thermostat_fresh=thermostat_fresh,thermostat_mode=thermostat_mode,
                owns_thermostat=owns_thermostat,manual_stop=evidence.manual_stop or evidence.operator_changed_mode)
            if result is not None:
                result['owner_epoch'] = owner_epoch
            self._last_ceiling_intent = deepcopy(result)
            self._last_heat_request = (requested_setpoint_c,planner_requests_heat,one_shot)
            self._issued_thermostat_owner = evidence.owner
            obj(self._snapshot['system_health'])['thermostat_ceiling'] = self._ceiling_view(self.trusted_clock())
            return result

    def issued_thermostat_request(self, proposal: dict[str, JSON]) -> tuple[float | None, bool, bool] | None:
        with self._memory:
            return self._last_heat_request if proposal == self._last_ceiling_intent and self._health_evidence().owner == self._issued_thermostat_owner else None

    def revalidate_thermostat_proposal(self, proposal: dict[str, JSON], *, thermostat_c: float,
                                     minimum: float, maximum: float, step: float, observed_at: float) -> bool:
        with self._memory:
            request = self.issued_thermostat_request(proposal)
            if request is None:
                return False
            wanted, planner, one_shot = request
            checked = self.heat_setpoint_intent(owner_epoch=integer(proposal.get('owner_epoch')),
                requested_setpoint_c=wanted,planner_requests_heat=planner,one_shot=one_shot,
                owns_thermostat=True,thermostat_mode='HEAT',thermostat_fresh=True,thermostat_c=thermostat_c,
                min_setpoint_c=minimum,max_setpoint_c=maximum,temperature_step_c=step)
            clock = self.trusted_clock()
            age = max(0,clock.utc-observed_at)
            self._thermostat_seen = Clock(utc=observed_at,monotonic=max(0,clock.monotonic-age),boot_id=clock.boot_id)
            return checked == proposal

    def executor_withdrawal(self, *, owner_epoch: int, thermostat_c: float, minimum: float,
                            maximum: float, step: float) -> dict[str, JSON] | None:
        """STOP/preemption only: fixed negative permission, never resume or ON."""
        with self._memory:
            self.refresh()
            evidence = self._health_evidence()
            if (not self._opened or not self.enabled or self._clock_bad or evidence.owner is None
                    or evidence.operator_changed_mode or owner_epoch != obj(self._snapshot['status'])['owner_epoch']):
                return None
            result = finalize_heat_setpoint(limit=self._active_room_limit,room_c=None,
                requested_setpoint_c=None,heat_permitted=False,planner_requests_heat=False,
                thermostat_c=thermostat_c,min_setpoint_c=minimum,max_setpoint_c=maximum,
                temperature_step_c=step,thermostat_fresh=True,thermostat_mode='HEAT',
                owns_thermostat=True,manual_stop=False)
            if result is not None:
                result['owner_epoch'] = owner_epoch
            return result

    def voltage_stop_intent(self, *, owner_epoch: int, owns_thermostat: bool = False,
                            thermostat_fresh: bool = False, thermostat_c: float | None = None,
                            min_setpoint_c: float | None = None, max_setpoint_c: float | None = None,
                            temperature_step_c: float | None = None) -> dict[str, JSON] | None:
        """Internal synthetic intent only; no device route or inferred real ownership."""
        with self._memory:
            self.refresh()
            view = obj(self._snapshot['status'])
            if (not self.enabled or not self._opened or self._clock_bad
                    or owner_epoch != view['owner_epoch'] or self._voltage_state is None):
                return None
            return synthetic_voltage_withdrawal(self._voltage_state,
                thermostat_c=thermostat_c, min_setpoint_c=min_setpoint_c,
                max_setpoint_c=max_setpoint_c, temperature_step_c=temperature_step_c,
                thermostat_fresh=thermostat_fresh, owns_thermostat=owns_thermostat,
                manual_stop=view['mode'] == 'MANUAL_PAUSE')

    def safety_permit(self) -> HeatPermit:
        """Reuse accepted eligibility guards with unconditional synthetic SHADOW policy."""
        view = obj(self._snapshot['status'])
        boot = str(view['boot_id'])
        clock = self.trusted_clock()
        state = ControlState(boot_id=boot, owner_epoch=integer(view['owner_epoch']),
                             manual_paused=view['mode'] == 'MANUAL_PAUSE')
        source = self._adapter.snapshot(clock, state, 1, integer(self._model['revision']), connected=self._opened)
        policy = ControlPolicy(config_revision=1, operating_mode=ControlMode.SHADOW,
            armed=False, allow_automatic=False, configuration_valid=True, limits_qualified=False,
            room_upper_c=None, return_upper_c=None, room_max_age_s=30, return_max_age_s=30,
            thermostat_max_age_s=30, grid_max_age_s=30, snapshot_max_age_s=30, max_skew_s=0,
            min_on_s=0, min_off_s=0, intent_ttl_s=1, recovery_stable_s=0, strict_windows=None)
        return evaluate(state, source, policy, clock)

    @staticmethod
    def _source_adapter(max_age_s: float) -> SourceAdapter:
        return SourceAdapter(Registry(1, (Binding('synthetic.native.room', 'room',
            'synthetic.native.room', 'synthetic.native.room', Unit.CELSIUS, max_age_s, 0, ('read',)),),
            0, 'conflict_unknown', 0))

    def configure_source(self, max_age_s: float) -> None:
        """Trusted config/options age; rebuilding drops previously cached source assertions."""
        age = number(max_age_s)
        if not 5 <= age <= 300:
            raise NativeProtocolError('invalid_source_age')
        with self._memory:
            self._source_max_age = age
            self._adapter = self._source_adapter(age)
            self._adapter.connection(integer(self._snapshot['generation']))
            if self._opened:
                self.invalidate_source('source_options_changed')

    def invalidate_source(self, reason: str) -> None:
        """SDK-only lifecycle callback, memory-first and independent of every disk."""
        with self._memory:
            state = deepcopy(self._snapshot)
            self._advance(state)
            obj(state['room'])['quality'] = 'missing'
            obj(state['room'])['value'] = None
            if obj(state['status'])['mode'] != 'MANUAL_PAUSE':
                obj(state['status'])['mode'] = 'SAFE_HOLD'
            obj(state['diagnostics'])['source'] = 'unavailable'
            self._snapshot = state
            self._serial += 1
            self._pending_stop = True

    @staticmethod
    def _activity_reason(view: dict[str, JSON]) -> str:
        return ('Активність T&H (температура АБО вологість): ' + str(view['device_quality'])
                + '. Реальний вимір вітальні: ' + str(view['temperature_quality'])
                + '. Щуп обратки (лише допоміжний): ' + str(view['return_quality'])
                + ('. Допоміжне вето нагріву' if view['return_veto'] is True else '')
                + '. Вологість не оновлює температуру; перевищення порогу не підтверджує відключення.')

    def configure_timing(self, policy: SourceTimingPolicy) -> None:
        with self._memory:
            self.configure_source(policy.measurement_authorization_age_s)
            self._health_policy = replace(self._health_policy, recovery_s=policy.recovery_dwell_s)
            self._activity.window_s = policy.device_activity_window_s

    def accept_integration_report(self, report: IntegrationReport) -> bool:
        """Passive monitor: no hardware measurement, transport sequence or command."""
        with self._memory:
            clock = self.trusted_clock()
            if not self._opened or self._clock_bad or not self._activity.observe_integration(report, clock):
                return False
            self._activity_active = True
            if report.role == 'temperature' and not report.available:
                self.invalidate_source('integration_source_unavailable')
            self.refresh()
            return True

    def accept_device_report(self, report: DeviceReport) -> bool:
        """Trusted synthetic fixture seam only; no public physical Tuya binding."""
        from packages.contracts import Reading, Quality, QualityStatus, Provenance, SourceKind
        with self._memory:
            clock = self.trusted_clock()
            if not self._opened or self._clock_bad or not self._activity.accept(report, clock, self._source_max_age):
                return False
            self._activity_active = True
            if report.role == 'temperature':
                if not report.available:
                    self.invalidate_source('qualified_synthetic_unavailable')
                elif (report.measurement_qualified and report.observed_at is not None
                        and self._activity.measurements.get('temperature', (None, clock))[0] == report):
                    reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
                        value=report.value, unit=Unit.CELSIUS, observed_at=report.observed_at,
                        received_at=report.received_at,
                        quality=Quality(status=QualityStatus.VALID, age_s=clock.utc - report.observed_at, reason='synthetic-raw-report'),
                        provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
                    self.accept_source(SourceEvent('environment.' + clock.boot_id + '.' + str(report.sequence),
                        'synthetic.native.room', report.sequence, report.received_at, reading))
            self.refresh()
            return True

    def accept_source(self, event: SourceEvent, clock: Clock | None = None) -> bool:
        """Only typed, own synthetic observations; no body-supplied provenance privilege."""
        with self._memory:
            if clock is not None and clock.boot_id != obj(self._snapshot['status'])['boot_id']:
                return False
            clock = self.trusted_clock()
            if self._clock_bad:
                self.refresh()
                return False
            try:
                accepted = self._adapter.ingest(event)
                # Explicit qualified reports/heartbeats are distinct from a value change.
                if (accepted and event.reading is not None and event.entity == 'synthetic.native.room' and event.author == 'sensor'
                        and event.reading.quality.status.value == 'valid'
                        and event.reading.provenance.independent
                        and event.reading.provenance.kind.value == 'direct'
                        and 0 <= clock.utc - event.received_at <= self._source_max_age):
                    self._room_report = (event.received_at, clock.monotonic - (clock.utc - event.received_at),
                        clock.boot_id + ':' + event.identity)
                reading = self._adapter.select('room', clock, connected=self._opened)
            except ValueError:
                self.invalidate_source('invalid_event')
                return False
            if not accepted:
                return False
            if reading is None:
                self.invalidate_source('invalid_source')
                return False
            state = deepcopy(self._snapshot)
            self._advance(state)
            state['now'] = clock.utc
            state['room'] = {'value': reading.value, 'observed': reading.observed_at, 'quality': 'valid'}
            obj(state['diagnostics'])['source'] = 'valid'
            if obj(state['status'])['mode'] != 'MANUAL_PAUSE':
                obj(state['status'])['mode'] = 'SHADOW' if self.enabled else 'SAFE_HOLD'
            self._snapshot = state
            self._room_seen_mono = clock.monotonic
            self._room_initial_age = clock.utc - reading.observed_at
            self._serial += 1
            self._pending_stop = True
            return True

    def _can_change(self, is_admin: bool) -> bool:
        self.refresh()
        room = obj(self._snapshot['room'])
        age = number(self._snapshot['now']) - number(room['observed'])
        return (is_admin is True and self.enabled and self._opened
                and not self._store_failed and not self._pending_stop and not self._clock_bad
                and room['quality'] == 'valid' and 0 <= age <= self._source_max_age
                and obj(self._snapshot['status'])['mode'] not in ('SAFE_HOLD', 'RECOVERING'))

    def _advance(self, state: dict[str, JSON]) -> None:
        state['seq'] = integer(state['seq']) + 1
        view = obj(state['status'])
        view['status_seq'] = state['seq']
        view['owner_epoch'] = integer(view['owner_epoch']) + 1
        view['desired'] = 'stop_demand'
        view['physical_verified'] = False

    def _fence(self, value: dict[str, JSON]) -> None:
        if (value.get('boot_id') != obj(self._snapshot['status'])['boot_id']
                or value.get('generation') != self._snapshot['generation']
                or type(value.get('generation')) is not int):
            raise NativeProtocolError('stale_fence')

    def _disk_fence(self, state: JSON) -> None:
        saved = obj(state)
        if (obj(saved['status'])['boot_id'] != obj(self._snapshot['status'])['boot_id']
                or saved['generation'] != self._snapshot['generation']
                or (not self._pending_stop and obj(saved['status'])['owner_epoch']
                    != obj(self._snapshot['status'])['owner_epoch'])):
            self._store_failed = True
            raise NativeProtocolError('owner_conflict')

    @staticmethod
    def _receipt(request: str, status: str, revision: int = 0) -> dict[str, JSON]:
        return {'request_id': request, 'status': status, 'revision': revision,
                'persisted_revision': revision if status == 'saved' else None,
                'reason': {'saved': 'Збережено лише в синтетичному тесті',
                           'accepted_fake': 'Прийнято симулятором; фізичної дії немає'}.get(status, status)}

    def stop(self, is_admin: bool, boot_id: JSON, generation: JSON, request_id: str,
             owner_epoch: JSON = None) -> dict[str, JSON]:
        """Memory-only STOP; SDK invokes before scheduling separate durability work."""
        with self._memory:
            self._fence({'boot_id': boot_id, 'generation': generation})
            if is_admin is not True or not self.enabled or not self._opened:
                return self._receipt(request_id, 'denied')
            if owner_epoch is not None:
                self._owner_fence({'owner_epoch': owner_epoch})
            state = deepcopy(self._snapshot)
            self._advance(state)
            obj(state['status'])['mode'] = 'MANUAL_PAUSE'
            state['notices'] = [{'priority': 'manual', 'text': 'Автоматика на паузі. Лише синтетичний тест.'}]
            self._snapshot = state
            self._serial += 1
            self._pending_stop = True
            return self._receipt(request_id, 'accepted_fake')

    def stop_request(self, payload: JSON, is_admin: bool = False) -> JSON:
        """Strict native STOP admission, no database/evidence work or disk wait."""
        body = self._validate('control', payload)
        if body.get('kind') != 'pause':
            raise NativeProtocolError('invalid_control')
        request = body.get('request_id', 'synthetic.' + uuid4().hex)
        if not isinstance(request, str) or not 1 <= len(request) <= 128:
            raise NativeProtocolError('invalid_request_id')
        with self._memory:
            if is_admin is not True or not self.enabled or not self._opened:
                return self._receipt(request, 'denied')
            signature = encode(body)
            previous = self._stop_receipts.get(request)
            if previous is not None:
                record = obj(previous)
                return deepcopy(record['result']) if record['signature'] == signature else self._receipt(request, 'conflict')
            self._owner_fence(body)
            result = self.stop(is_admin, body['boot_id'], body['generation'], request, body['owner_epoch'])
            if len(self._stop_receipts) >= 4096:
                self._stop_receipts.pop(next(iter(self._stop_receipts)))
            self._stop_receipts[request] = {'signature': signature, 'result': result}
            return result

    def _owner_fence(self, body: dict[str, JSON]) -> None:
        if (type(body.get('owner_epoch')) is not int
                or body['owner_epoch'] != obj(self._snapshot['status'])['owner_epoch']):
            raise NativeProtocolError('stale_owner')

    def flush_stop(self) -> bool:
        # Persist derived health/STOP transitions in this same reconciliation pass.
        self.refresh()
        if not self._pending_stop:
            return True
        with self._memory:
            serial, snapshot = self._serial, deepcopy(self._snapshot)
        try:
            with self.critical.transaction() as con:
                self._disk_fence(self.critical.read_from(con, 'snapshot'))
                self.critical.write(con, 'snapshot', snapshot)
            with self._memory:
                if serial != self._serial:
                    return False
                self._pending_stop = False
                self._store_failed = False
                self._snapshot['seq'] = integer(self._snapshot['seq']) + 1
                obj(self._snapshot['status'])['status_seq'] = self._snapshot['seq']
                return True
        except (StoreError, NativeProtocolError):
            self._store_failed = True
            return False

    def _validate(self, operation: str, payload: JSON) -> dict[str, JSON]:
        keys = {'status': set(), 'subscribe': set(), 'overview': set(), 'energy': set(),
                'settings/get': set(), 'diagnostics': set(),
                'history': {'start', 'end', 'cursor', 'limit'},
                'settings/save': {'request_id', 'expected_revision', 'values'},
                'control': {'kind', 'request_id'}, 'model': {'kind', 'request_id'}}
        if operation not in keys:
            raise NativeProtocolError('unknown_operation')
        try:
            raw = encode(payload)
        except (ValueError, TypeError, RecursionError):
            raise NativeProtocolError('invalid_json') from None
        if len(raw.encode()) > 256 * 1024:
            raise NativeProtocolError('payload_too_large')
        body = obj(payload)
        mutation = operation in ('settings/save', 'control', 'model')
        common = {'entry_id', 'version'} | ({'boot_id', 'generation', 'owner_epoch'} if mutation else set())
        if (set(body) - common - keys[operation] or not common <= set(body)
                or body['entry_id'] != self.entry_id or body['version'] != [2, 0]
                or any(type(v) is not int for v in body['version'])):
            raise NativeProtocolError('invalid_envelope')
        if not self._opened:
            raise NativeProtocolError('unavailable')
        if mutation:
            self._fence(body)
            integer(body['owner_epoch'])
        return body

    def dispatch(self, operation: str, payload: JSON, is_admin: bool = False) -> JSON:
        self.refresh()
        body = self._validate(operation, payload)
        mutation = operation in ('settings/save', 'control', 'model')
        try:
            return self._dispatch(operation, body, is_admin)
        except StoreError:
            if mutation:
                self._store_failed = True
                request = body.get('request_id', '')
                return self._receipt(str(request), 'unavailable')
            raise NativeProtocolError('store_unavailable') from None

    def _dispatch(self, operation: str, body: dict[str, JSON], is_admin: bool) -> JSON:
        if operation in ('status', 'subscribe'):
            return self.status(is_admin)
        if operation == 'diagnostics':
            if is_admin is not True:
                raise NativeProtocolError('forbidden')
            return {'lifecycle': 'ready', 'critical': 'unavailable' if self._store_failed else 'ok',
                    'source': 'synthetic', 'kernel_reason': self.safety_permit().reason.value,
                    'meter': {'binding': 'unbound', 'B03': 'BLOCKED'}, 'gates': self._gates(), 'physical_authority': False}
        if operation == 'settings/get':
            return self.critical.read('settings')
        if operation in ('overview', 'energy', 'history'):
            fixture = obj(self.evidence.read('fixture'))
            if operation == 'energy':
                self._energy_ledger = self._read_energy(self.evidence.read('kws_energy'))
                return [{'start': s.start, 'end': s.end, 'kwh': s.kwh, 'category': s.category,
                         'price': None, 'method': 'counter_difference'} for s in self._energy_ledger]
            if operation == 'overview':
                overview = {key: deepcopy(fixture[key]) for key in ('original', 'latest', 'cycleEnergy', 'timeline', 'metrics')}
                overview.update({'model': deepcopy(self._model), 'enabled': self.enabled,
                               'boilerEnergy': self._boiler_energy(), 'energy_scope': 'approved_fixture_only',
                               'gates': self._gates(), 'physical_authority': False})
                return overview
            return self._history(body, fixture)
        request = body.get('request_id', 'synthetic.' + uuid4().hex)
        if not isinstance(request, str) or not 1 <= len(request) <= 128:
            raise NativeProtocolError('invalid_request_id')
        if operation == 'control' and body.get('kind') == 'pause':
            receipt = self.stop_request(body, is_admin)
            self.flush_stop()
            return receipt
        if is_admin is not True or not self.enabled:
            return self._receipt(request, 'denied')
        if operation == 'settings/save':
            if 'request_id' not in body:
                raise NativeProtocolError('invalid_request_id')
            integer(body.get('expected_revision'), 1)
            if not settings_valid(body.get('values')):
                return self._receipt(request, 'denied')
        result: JSON
        saved_values: JSON = None
        with self._memory:
            serial, state = self._serial, deepcopy(self._snapshot)
        with self.critical.transaction() as con:
            self._disk_fence(self.critical.read_from(con, 'snapshot'))
            requests = obj(self.critical.read_from(con, 'requests'))
            signature = encode({'operation': operation, 'body': body})
            previous = requests.get(request)
            if previous is not None:
                record = obj(previous)
                return deepcopy(record['result']) if record['signature'] == signature else self._receipt(request, 'conflict')
            self._owner_fence(body)
            if not self._can_change(is_admin):
                return self._receipt(request, 'denied')
            if len(requests) >= 4096:
                return self._receipt(request, 'unavailable')
            if operation == 'settings/save':
                saved = obj(self.critical.read_from(con, 'settings'))
                revision = integer(saved['revision'], 1)
                if body['expected_revision'] != revision:
                    return self._receipt(request, 'conflict', revision)
                saved_values = {key: obj(saved['values'])[key] for key in VOLTAGE_DEFAULTS} | obj(body['values'])
                saved = {'revision': revision + 1, 'values': saved_values, 'lastRequest': request}
                self.critical.write(con, 'settings', saved)
                result = self._receipt(request, 'saved', revision + 1)
                values = obj(body['values'])
                if values['circulation'] == 'manual':
                    obj(state['fan'])['requested'] = values['fan']
                elif values['circulation'] == 'stop':
                    obj(state['fan'])['requested'] = 0
            elif operation == 'control':
                result = self._control(state, body.get('kind'), request)
            else:
                result = self._model_action(body.get('kind'))
                self.critical.write(con, 'model', obj(result)['model'])
            if isinstance(result, dict) and result.get('status') == 'denied':
                return result
            self._advance(state)
            self.critical.write(con, 'snapshot', state)
            requests[request] = {'signature': signature, 'result': result}
            self.critical.write(con, 'requests', requests)
            if serial != self._serial:
                raise StoreError('Newer safety state superseded mutation')
        # A separate connection proves the committed readback, never a frontend cache.
        if operation == 'settings/save':
            readback = obj(self.critical.read('settings'))
            if readback['revision'] != obj(result)['revision'] or readback['values'] != saved_values:
                self._store_failed = True
                return self._receipt(request, 'unavailable')
        with self._memory:
            self.refresh()
            if serial != self._serial:
                return self._receipt(request, 'unavailable')
            self._snapshot = state
            self._serial += 1
            if operation == 'settings/save':
                self._settings_values = obj(saved_values)
            if operation == 'model':
                self._model = obj(obj(result)['model'])
            return result

    def _control(self, state: dict[str, JSON], kind: JSON, request: str) -> JSON:
        if kind not in ('resume', 'arm', 'cancel', 'expire', 'unknown', 'consume'):
            raise NativeProtocolError('invalid_control')
        shot = obj(state['oneShot'])
        if kind in ('arm', 'consume') and not self._demand_eligible():
            return self._receipt(request, 'denied')
        if kind == 'resume':
            obj(state['status'])['mode'] = 'RECOVERING'
            state['notices'] = [notice for notice in cast(list[JSON], state['notices'])
                                if obj(notice).get('priority') != 'manual']
        elif kind == 'arm' and shot['state'] in ('unknown_outcome', 'consumed'):
            return self._receipt(request, 'denied')
        elif kind == 'consume' and (shot['state'] != 'armed' or state['grid'] is not True
                or obj(state['status'])['mode'] in ('MANUAL_PAUSE', 'SHADOW', 'SAFE_HOLD', 'RECOVERING')
                or shot['expires'] is None or number(state['now']) >= number(shot['expires'])):
            return self._receipt(request, 'denied')
        else:
            shot['state'] = {'arm': 'armed', 'cancel': 'cancelled', 'expire': 'expired',
                             'unknown': 'unknown_outcome', 'consume': 'consumed'}[kind]
            if kind == 'arm':
                shot['expires'] = number(state['now']) + 3600
        return self._receipt(request, 'accepted_fake')

    def _model_action(self, kind: JSON) -> JSON:
        if kind not in ('train', 'promote', 'rollback', 'freeze'):
            raise NativeProtocolError('invalid_model_action')
        model = deepcopy(self._model)
        reason = 'Оновлено лише синтетичний приклад; історія незмінна'
        if kind == 'freeze':
            model['frozen'] = not model['frozen']
        elif model['frozen'] and kind != 'rollback':
            reason = 'Навчання заморожено'
        elif kind == 'train':
            model['candidate'] = True
        elif kind == 'promote':
            if model['candidate']:
                model['revision'], model['candidate'] = 4, False
            else:
                reason = 'Недостатньо доказів'
        else:
            model['revision'] = 3
        return {'reason': reason, 'model': deepcopy(model)}

    @staticmethod
    def _gates() -> list[JSON]:
        # The protocol lists blocked gate IDs; it never lists completed gates.
        return [f'B0{i}' for i in range(1, 9)]

    @staticmethod
    def _history(body: dict[str, JSON], fixture: dict[str, JSON]) -> JSON:
        start, end = number(body.get('start')), number(body.get('end'))
        limit = integer(body.get('limit', 128), 1)
        if not start < end or end - start > 31 * 86400 + 3600 or limit > 256:
            raise NativeProtocolError('invalid_history_range')
        source = cast(list[JSON], fixture['actual'])
        watermark = len(source)
        scope = f'{int(start) if start.is_integer() else start}:{int(end) if end.is_integer() else end}'
        cursor = body.get('cursor')
        offset = 0
        if cursor is not None:
            c = obj(cursor)
            if (set(c) != {'scope', 'watermark', 'offset'} or c['scope'] != scope
                    or c['watermark'] != watermark or type(c['watermark']) is not int):
                raise NativeProtocolError('invalid_cursor')
            offset = integer(c['offset'])
        rows = [deepcopy(p) for p in source if start <= number(obj(p)['at']) < end]
        if offset > len(rows):
            raise NativeProtocolError('invalid_cursor')
        page = rows[offset:offset + limit]
        next_cursor: JSON = {'offset': offset + len(page), 'scope': scope, 'watermark': watermark} if offset + len(page) < len(rows) else None
        result: JSON = {'rows': page, 'cursor': next_cursor, 'watermark': watermark}
        if len(encode(result).encode()) > 64 * 1024:
            raise NativeProtocolError('history_page_too_large')
        return result
