"""Native orchestration of accepted decisions, bounded compute, persistence and UI.

HA cache provenance is retained; a live state timestamp is not a raw sensor ACK.
There is intentionally no physical-authority issuer in this installed runtime.
"""
import asyncio
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import time
from uuid import uuid4

from .critical_ledger import CriticalLedger, FILENAME
from .native_store import NativeStore, SETTINGS, validate
from .climate_gateway import ClimateGateway
from .engine.contracts import (
    Clock, ControlEvent, ControlMode, ControlPolicy, ControlSnapshot, ControlState,
    EventKind, Provenance, Quality, QualityStatus, Reading, Revisions, SourceKind, Unit,
)
from .engine.control import reduce
from .engine.ha_native.thermostat import ActiveRoomLimit, finalize_heat_setpoint, supported_ceiling
from .shadow_plan import REQUIRED, _model, _minutes


def reported(row, now):
    try:
        value = datetime.fromisoformat(row['last_reported'])
        stamp = value.timestamp() if value.tzinfo else None
        return stamp if stamp is not None and 0 < stamp <= now else None
    except (TypeError, KeyError, ValueError, OverflowError):
        return None


def seed_settings(rows):
    values = {}
    for role in SETTINGS:
        row = rows.get(role)
        if not row or row.get('state') in ('unknown', 'unavailable'):
            continue
        raw = row['state']
        try:
            value = (raw if role in ('strategy', 'power_model', 'fan_mode') or role.endswith(('_start', '_end'))
                     else float(raw))
            validate({role: value})
            values[role] = value
        except (ValueError, TypeError):
            continue
    try:
        return validate(values)
    except ValueError:
        return {}  # Invalid legacy bands cannot silently become new valid defaults.


class NativeController:
    def __init__(self, directory, rows, service, readback):
        self.boot_id = uuid4().hex
        self.store = NativeStore(directory)
        self.store.seed(seed_settings(rows))
        path = directory/FILENAME
        self.ledger = (CriticalLedger(directory) if path.exists() else
                       CriticalLedger(directory, owner_id='heating_ai_v2', boot_id=self.boot_id, owner_epoch=0))
        old = self.ledger.status()
        self.ledger.reconcile_restart(self.boot_id, expected_revision=old['revision'],
            owner_id=old['owner_id'], boot_id=old['boot_id'], owner_epoch=old['owner_epoch'])
        self.journal = self.ledger.status()
        self.persisted = self.store.status()
        if self.persisted['one_shot']['state'] == 'armed':
            self.persisted['one_shot'] = dict(state='unknown_outcome', expires=None)
        self.gateway = ClimateGateway(self.ledger, '', service, readback, lambda: None)
        self.state = ControlState(boot_id=self.boot_id, owner_epoch=self.journal['owner_epoch'])
        self.sequence = 0
        self.grid_epoch = 0
        self.previous_grid = None
        self.lock = asyncio.Lock()
        self._sample_key = None
        self.fault = None
        self.rows, self.values, self.safety = {}, {}, {}
        self.proposal = None
        self.tick(rows, {}, time.time(), time.monotonic())

    def planning_rows(self, rows):
        result = deepcopy(rows)
        for key, value in self.persisted['values'].items():
            if key in SETTINGS:
                result[key] = dict(state=str(value), unit='°C' if key.endswith(('_target', '_upper')) else '%',
                                   last_reported=datetime.now().astimezone().isoformat())
        return result

    def tick(self, rows, values, now, mono):
        """Small memory-only safety pass. Never waits for provider, DB or planner."""
        self.rows, self.values = deepcopy(rows), deepcopy(values)
        settings = self.persisted['values']
        grid = values.get('grid_last_known')
        if grid != self.previous_grid:
            self.grid_epoch += 1
        self.previous_grid = grid
        ages = {k: None if reported(rows.get(k), now) is None else now-reported(rows[k], now)
                for k in ('room', 'thermostat', 'voltage_l1', 'voltage_l2', 'voltage_l3')}
        voltage_age = settings.get('voltage_max_age_s')
        fresh_volts = (voltage_age is not None and all(ages[k] is not None and ages[k] <= voltage_age
                       for k in ('voltage_l1', 'voltage_l2', 'voltage_l3')))
        minimum, maximum = settings.get('min_voltage_v'), settings.get('max_voltage_v')
        volts = values.get('voltages_v_last_known', {})
        voltage_inside = (fresh_volts and minimum is not None and maximum is not None and
                          all(v is not None and minimum <= v <= maximum for v in volts.values()) and len(volts)==3)
        self.safety = dict(grid=grid, ages=ages, voltage_cache_in_band=bool(voltage_inside),
            voltage_source='input220', voltage_independently_qualified=False,
            room_raw_measurement_qualified=False, kws_supply_ready=None,
            voltage_status=('GRID_OFF_OR_UNKNOWN' if grid is not True else
                            'CACHE_STALE_OR_MISSING' if not fresh_volts else
                            'UNQUALIFIED_IN_BAND' if voltage_inside else 'OUTSIDE_OR_UNKNOWN_LIMITS'),
            physical_commands_enabled=False, reason='signed_exclusive_handoff_and_raw_safety_witness_missing')
        self.sequence += 1
        clock = Clock(utc=now, monotonic=mono, boot_id=self.boot_id)
        def held(role, value, unit):
            stamp = reported(rows.get(role), now)
            if value is None or stamp is None:
                return None
            return Reading(physical_id='ha.cache.'+role, source_id='ha.'+role, value=value, unit=unit,
                observed_at=stamp, received_at=stamp,
                quality=Quality(status=QualityStatus.STALE, age_s=now-stamp, reason='HA_cache_not_raw_sample'),
                provenance=Provenance(kind=SourceKind.HELD, independent=False), evidence_ids=())
        stamp = sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
        snapshot = ControlSnapshot(snapshot_id=stamp[:24], input_hash=stamp, boot_id=self.boot_id,
            revisions=Revisions(config=self.persisted['revision'], model=0, topology=0),
            grid_epoch=self.grid_epoch, owner_epoch=self.state.owner_epoch, captured_at=now,
            room=held('room', values.get('room_c_last_known'), Unit.CELSIUS),
            return_temperature=held('return_probe', values.get('return_c_last_known'), Unit.CELSIUS),
            thermostat=None, grid_actual=held('grid', grid, Unit.BOOLEAN), forecast_grid=None,
            power=held('kws_l1', values.get('kws_total_kw_last_known'), Unit.KILOWATT),
            compute_available=True, hard_stop=self.persisted['manual_pause'] or bool(self.fault), scheduled_outage=False)
        policy = ControlPolicy(config_revision=self.persisted['revision'], operating_mode=ControlMode.AUTO,
            armed=False, allow_automatic=False, configuration_valid=all(k in settings for k in REQUIRED),
            limits_qualified=False, room_upper_c=None, return_upper_c=None,
            room_max_age_s=settings.get('room_max_age_s', 0), return_max_age_s=0, thermostat_max_age_s=0,
            grid_max_age_s=0, snapshot_max_age_s=5, max_skew_s=0,
            min_on_s=0, min_off_s=0, intent_ttl_s=5, recovery_stable_s=0, strict_windows=None)
        event = ControlEvent(kind=EventKind.TICK, boot_id=self.boot_id, owner_epoch=self.state.owner_epoch,
                            sequence=self.sequence, at=now, expires_at=now+5)
        decision = reduce(self.state, event, snapshot, policy, clock)
        self.state = decision.state
        self.decision = dict(mode=self.state.mode.value, reason=decision.permit.reason.value,
                             permit=False, intents=0, permitted=False,
                             proposed_intents=len(decision.intents), actual_commands=0)
        # Use the accepted final limiter, never duplicate its dynamic ceiling algorithm.
        planning = self.planning_rows(rows)
        start, end = _minutes(planning.get('sleep_start')), _minutes(planning.get('sleep_end'))
        from zoneinfo import ZoneInfo
        local = datetime.fromtimestamp(now, ZoneInfo('Europe/Kyiv'))
        minute = local.hour*60+local.minute
        sleeping = start is not None and end is not None and start != end and (
            start <= minute < end if start < end else minute >= start or minute < end)
        band = 'night' if sleeping else 'day'
        upper, target = settings.get(band+'_upper'), settings.get(band+'_target')
        attrs = (rows.get('thermostat') or {}).get('attributes', {})
        limit = (ActiveRoomLimit(band, upper, target, qualified=True)
                 if upper is not None and target is not None else None)
        self.proposal = finalize_heat_setpoint(limit=limit, room_c=values.get('room_c_last_known'),
            requested_setpoint_c=attrs.get('max_temp'), heat_permitted=False, planner_requests_heat=False,
            thermostat_c=attrs.get('current_temperature'), min_setpoint_c=attrs.get('min_temp'),
            max_setpoint_c=attrs.get('max_temp'), temperature_step_c=attrs.get('target_temp_step'),
            thermostat_fresh=False, thermostat_mode=str((rows.get('thermostat') or {}).get('state')).upper(),
            owns_thermostat=False, manual_stop=self.persisted['manual_pause'])
        self.active_limit = dict(band=band, target=target, upper=upper,
                                ceiling=supported_ceiling(limit, attrs.get('min_temp'),
                                    attrs.get('max_temp'), attrs.get('target_temp_step')), qualified=False)

    async def observe(self):
        rows, values = deepcopy(self.rows), deepcopy(self.values)
        now = time.time()
        room_at = reported(rows.get('room'), now)
        counter_at = reported(rows.get('kws_energy'), now)
        key = (room_at, values.get('room_c_last_known'), counter_at, values.get('kws_energy_kwh_last_known'))
        if key == self._sample_key:
            return
        self._sample_key = key
        async with self.lock:
            try:
                if room_at is not None or counter_at is not None:
                    await asyncio.to_thread(self.store.observe, room_at, values.get('room_c_last_known'),
                        values.get('kws_energy_kwh_last_known') if counter_at is not None else None,
                        values.get('kws_total_kw_last_known'), counter_at)
                self.persisted = await asyncio.to_thread(self.store.status)
            except Exception:
                self.fault = 'native_persistence_failed'
                self.gateway.stopped = True

    def overview(self):
        model = (self.rows.get('legacy_model') or {}).get('attributes', {}).get('parameters')
        return dict(version=[2,0], seq=self.sequence, boot_id=self.boot_id,
            owner_epoch=self.state.owner_epoch, settings=deepcopy(self.persisted),
            safety=deepcopy(self.safety), controller=deepcopy(self.decision), active_limit=self.active_limit,
            model=dict(parameters=model if _model(model) is not None else None,
                       qualification='NOT_PARITY_VERIFIED', frozen=self.persisted['model_frozen']),
            plan=deepcopy(self.values.get('virtual_plan')), coast=deepcopy(self.values.get('coast')),
            fan=deepcopy(self.values.get('fan')), journal=deepcopy(self.journal),
            one_shot=deepcopy(self.persisted['one_shot']), physical_commands_enabled=False,
            fault=self.fault, original_history='MISSING_UNLESS_ARCHIVED_BEFORE_12H_CUTOFF')

    async def dispatch(self, operation, payload, admin):
        if operation == 'snapshot':
            return self.overview()
        if operation == 'history':
            async with self.lock:
                return await asyncio.to_thread(self.store.history, payload['start'], payload['end'], time.time())
        if not admin:
            raise PermissionError('HA administrator required')
        if operation not in ('settings/save', 'pause', 'resume', 'cancel', 'freeze'):
            return dict(status='denied', reason='unqualified_physical_or_training_operation')
        if type(payload.get('owner_epoch')) is not int or (payload.get('boot_id'), payload.get('owner_epoch')) != (self.boot_id, self.state.owner_epoch):
            return dict(status='conflict', reason='stale_boot_or_owner')
        if operation == 'pause':
            self.persisted['manual_pause'] = True  # Memory-first STOP wins over slow I/O.
            self.gateway.stopped = True
        async with self.lock:
            try:
                expected = payload['expected_revision']
                if operation == 'pause':
                    expected = (await asyncio.to_thread(self.store.status))['revision']
                result = await asyncio.to_thread(self.store.mutate, expected,
                    payload['request_id'], operation, payload.get('values', {}))
                if operation == 'pause':
                    row = await asyncio.to_thread(self.ledger.status)
                    await asyncio.to_thread(self.ledger.fence, expected_revision=row['revision'],
                        owner_id=row['owner_id'], boot_id=row['boot_id'], owner_epoch=row['owner_epoch'])
                    self.journal = await asyncio.to_thread(self.ledger.status)
                    self.state = ControlState(boot_id=self.boot_id, owner_epoch=self.journal['owner_epoch'])
                self.persisted = await asyncio.to_thread(self.store.status)
                return result
            except Exception:
                self.fault = 'native_mutation_failed'
                self.gateway.stopped = True
                raise ValueError('Mutation failed closed') from None
