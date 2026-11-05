"""Authoritative synthetic-only panel service; no HA imports or actuator transport."""
from __future__ import annotations

import math
import re
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import cast
from uuid import uuid4

from packages.contracts import Clock, ControlState, ControlPolicy, ControlMode, HeatPermit, Unit
from packages.control import evaluate
from packages.ha_fake.adapter import SourceAdapter
from packages.offline.contracts import Binding, Registry, SourceEvent

from .store import JSON as JSON, NativeStore, StoreError, decode, encode


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
    if not isinstance(values, dict) or set(values) != {
        'day', 'night', 'budget', 'windowStart', 'windowEnd', 'strategy',
        'mode', 'circulation', 'fan', 'scenario', 'freshness', 'aiAdvice',
    }:
        return False
    try:
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
                 entry_id: str = 'synthetic-entry', enabled: bool = False):
        if type(enabled) is not bool or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', entry_id):
            raise NativeProtocolError('invalid_configuration')
        self.fixture = deepcopy(fixture) if fixture is not None else obj(decode(Path(__file__).with_name('fixture.json').read_text()))
        encode(self.fixture)
        self.entry_id = entry_id
        self.enabled = enabled
        self.critical = NativeStore(root, 'critical')
        self.evidence = NativeStore(root, 'evidence')
        self._snapshot = deepcopy(obj(self.fixture['snapshot']))
        self._memory = RLock()
        self._serial = 0
        self._source_max_age = 30.0
        self._adapter = self._source_adapter(30)
        self._stop_receipts: dict[str, JSON] = {}
        self._opened = False
        self._pending_stop = False
        self._store_failed = False
        self._model: dict[str, JSON] = {'revision': 3, 'candidate': False, 'frozen': False}

    def open(self) -> None:
        self._opened = False
        self._store_failed = True
        self._snapshot['permitted'] = False
        obj(self._snapshot['status'])['desired'] = 'stop_demand'
        obj(self._snapshot['status'])['mode'] = 'SAFE_HOLD'
        defaults = self.fixture.get('settings', self.fixture.get('defaults'))
        if not settings_valid(defaults):
            raise StoreError('Invalid synthetic fixture settings')
        self.critical.open({'settings': {'revision': 1, 'values': defaults, 'lastRequest': None},
                            'snapshot': self._snapshot, 'requests': {}, 'model': self._model})
        with self.critical.transaction() as con:
            saved = obj(self.critical.read_from(con, 'settings'))
            if not settings_valid(saved.get('values')):
                raise StoreError('Invalid stored synthetic settings')
            integer(saved.get('revision'), 1)
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
        self._serial += 1
        self._adapter.connection(integer(state['generation']))
        # Evidence may fail independently; safety and STOP keep their own critical path.
        try:
            self.evidence.open({'fixture': self.fixture})
        except StoreError:
            obj(self._snapshot['diagnostics'])['persistence'] = 'archive_unavailable'
        self._store_failed = False
        self._pending_stop = False
        self._opened = True

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
            result = deepcopy(self._snapshot)
            result['permitted'] = self._can_change(is_admin)
            obj(result['status'])['physical_verified'] = False
            if self.safety_permit().allowed:
                raise NativeProtocolError('physical_authority_forbidden')
            return result

    def safety_permit(self) -> HeatPermit:
        """Reuse accepted eligibility guards with unconditional synthetic SHADOW policy."""
        view = obj(self._snapshot['status'])
        boot = str(view['boot_id'])
        clock = Clock(utc=number(self._snapshot['now']), monotonic=0, boot_id=boot)
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

    def accept_source(self, event: SourceEvent, clock: Clock) -> bool:
        """Only typed, own synthetic observations; no body-supplied provenance privilege."""
        with self._memory:
            if clock.boot_id != obj(self._snapshot['status'])['boot_id']:
                return False
            try:
                accepted = self._adapter.ingest(event)
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
            self._serial += 1
            self._pending_stop = True
            return True

    def _can_change(self, is_admin: bool) -> bool:
        room = obj(self._snapshot['room'])
        age = number(self._snapshot['now']) - number(room['observed'])
        return (is_admin is True and self.enabled and self._opened
                and not self._store_failed and not self._pending_stop
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
                return deepcopy(fixture['intervals'])
            if operation == 'overview':
                overview = {key: deepcopy(fixture[key]) for key in ('original', 'latest', 'cycleEnergy', 'timeline', 'metrics')}
                overview.update({'model': deepcopy(self._model), 'enabled': self.enabled,
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
                saved = {'revision': revision + 1, 'values': body['values'], 'lastRequest': request}
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
            if readback['revision'] != obj(result)['revision'] or readback['values'] != body['values']:
                self._store_failed = True
                return self._receipt(request, 'unavailable')
        with self._memory:
            if serial != self._serial:
                return self._receipt(request, 'unavailable')
            self._snapshot = state
            self._serial += 1
            if operation == 'model':
                self._model = obj(obj(result)['model'])
            return result

    def _control(self, state: dict[str, JSON], kind: JSON, request: str) -> JSON:
        if kind not in ('resume', 'arm', 'cancel', 'expire', 'unknown', 'consume'):
            raise NativeProtocolError('invalid_control')
        shot = obj(state['oneShot'])
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
