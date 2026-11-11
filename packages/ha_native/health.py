"""Issue27: synthetic health projection and proposed failover, never a device sender."""
from dataclasses import dataclass, field
from typing import Literal, cast
from packages.contracts.models import number, require

HealthStatus = Literal['OK', 'PROBLEM', 'WAITING']


@dataclass(frozen=True)
class HealthPolicy:
    # Synthetic report-age policy, NOT a validated household disconnect interval.
    room_timeout_s: float = 10800
    recovery_s: float = 30
    cold_grace_s: float = 60
    notification_cooldown_s: float = 30

    def __post_init__(self) -> None:
        for value in (self.room_timeout_s, self.recovery_s, self.cold_grace_s, self.notification_cooldown_s):
            number(value, nonnegative=True)
        require(60 <= self.room_timeout_s <= 86400 and self.recovery_s <= 3600
                and self.cold_grace_s <= 3600 and self.notification_cooldown_s <= 3600, 'Invalid health policy')


@dataclass(frozen=True)
class HealthInputs:
    room_age_s: float | None = None
    room_report_verified: bool = False
    room_valid: bool = False
    room_report_id: str | None = None
    room_failure_confirmed: bool = False
    room_silence_qualified: bool = True
    room_status: HealthStatus | None = None
    room_reason: str | None = None
    fireplace_age_s: float | None = None
    fireplace_qualified: bool = False
    thermostat_qualified: bool = False
    thermostat_age_s: float | None = None
    electrical_eligible: bool = False
    electrical_reason: str = 'Очікування мережі/KWS'
    electrical_fault: bool = False
    power_qualified: bool = False
    clock_ok: bool = True
    persistence_ok: bool = False
    plan_ok: bool = False
    owner: str | None = None
    manual_stop: bool = False
    operator_changed_mode: bool = False
    one_shot_blocked: bool = False
    # Already qualified by #26: caller supplies a proposed safe HEAT withdrawal or None.
    withdrawal: dict[str, object] | None = None


@dataclass
class HealthMemory:
    boot: str = ''
    started: float = 0
    last_mono: float = 0
    mode: str = 'NORMAL'
    auto_owner: str | None = None
    recovery_since: float | None = None
    recovered_report: str | None = None
    lost_report: str | None = None
    intent_key: str = ''
    transition_seq: int = 0
    last_proposal: dict[str, object] | None = None
    operator_latched: bool = False
    notification_at: float | None = None
    notification_key: str = ''
    pending_notification: str = ''
    transitions: dict[str, tuple[str, str, float]] = field(default_factory=dict)


    @classmethod
    def from_record(cls, raw: dict[str, object]) -> 'HealthMemory':
        require(set(raw) == set(cls.__dataclass_fields__), 'Invalid health memory schema')
        result = cls()
        for key in ('boot', 'mode', 'notification_key', 'pending_notification', 'intent_key'):
            require(type(raw[key]) is str, 'Invalid health memory string')
            setattr(result, key, raw[key])
        for key in ('auto_owner', 'recovered_report', 'lost_report'):
            require(raw[key] is None or type(raw[key]) is str, 'Invalid health owner/report')
            setattr(result, key, raw[key])
        for key in ('started', 'last_mono', 'recovery_since', 'notification_at'):
            value = raw[key]
            if value is None:
                require(key in ('recovery_since', 'notification_at'), 'Invalid clock memory')
            else:
                number(value, nonnegative=True)
            setattr(result, key, value)
        require(type(raw['transition_seq']) is int and raw['transition_seq'] >= 0, 'Invalid intent sequence')
        result.transition_seq = cast(int, raw['transition_seq'])
        proposal = raw['last_proposal']
        require(proposal is None or type(proposal) is dict, 'Invalid proposal record')
        if proposal is not None:
            require(cast(dict[str, object], proposal).get('physical_authority') is False and cast(dict[str, object], proposal).get('stage') == 'proposed', 'Invalid proposal authority')
        result.last_proposal = cast(dict[str, object] | None, proposal)
        require(type(raw['operator_latched']) is bool, 'Invalid operator latch')
        result.operator_latched = cast(bool, raw['operator_latched'])
        require(type(raw['transitions']) is dict, 'Invalid transition memory')
        for key, value in cast(dict[str, object], raw['transitions']).items():
            require(type(value) in (list, tuple), 'Invalid transition record')
            row = cast(list[object], value)
            require(len(row) == 3 and type(row[0]) is str and type(row[1]) is str, 'Invalid transition')
            number(row[2], nonnegative=True)
            result.transitions[key] = (cast(str, row[0]), cast(str, row[1]), cast(float, row[2]))
        return result


def project_health(inputs: HealthInputs, *, now: float, mono: float, boot: str,
                   policy: HealthPolicy, memory: HealthMemory) -> tuple[dict[str, object], HealthMemory]:
    """Same snapshot evidence -> one projection; AUTO/HEAT are proposed intents only."""
    from copy import deepcopy
    m = deepcopy(memory)
    number(now, nonnegative=True); number(mono, nonnegative=True)
    restart = m.boot != boot
    rollback = not restart and mono < m.last_mono
    if restart:
        m.boot, m.started, m.recovery_since, m.recovered_report = boot, mono, None, None
        m.notification_at = None
    # last_mono is a high-water mark: clock rollback cannot silently heal.
    m.last_mono = max(m.last_mono if not restart else mono, mono)
    age = inputs.room_age_s
    confirmed_loss = (inputs.room_failure_confirmed or (inputs.room_silence_qualified
                      and inputs.room_report_verified and age is not None and age > policy.room_timeout_s))
    confirmed_loss = confirmed_loss and mono - m.started >= policy.cold_grace_s
    room_ok = inputs.room_valid and inputs.room_report_verified and age is not None and 0 <= age <= policy.room_timeout_s
    thermostat_ok = (inputs.thermostat_qualified and inputs.thermostat_age_s is not None
                     and 0 <= inputs.thermostat_age_s <= 120)
    owner_ok = inputs.owner is not None
    if inputs.manual_stop or inputs.operator_changed_mode or (m.auto_owner is not None and inputs.owner != m.auto_owner):
        m.operator_latched = True
    guards = inputs.clock_ok and not rollback and inputs.persistence_ok and owner_ok and not m.operator_latched
    intent: dict[str, object] | None = None
    event = ''
    previous_mode = m.mode
    if not guards:
        m.recovery_since = None
        m.mode = 'BLOCKED'
    elif not inputs.electrical_eligible and not inputs.electrical_fault and mono - m.started < policy.cold_grace_s:
        m.recovery_since = None
        m.mode = 'WAITING'
    elif not inputs.electrical_eligible:
        m.recovery_since = None
        m.mode = 'ELECTRICAL_INHIBIT'
        if not inputs.manual_stop:
            intent = inputs.withdrawal
            if (not thermostat_ok or intent is None or intent.get('action') != 'withdraw_demand'
                    or intent.get('mode') != 'HEAT' or intent.get('physical_authority') is not False):
                intent = {'action': 'cannot_confirm_withdrawal', 'physical_authority': False}
                event = 'Неможливо підтвердити зняття нагріву. Незалежний захист KWS залишається необхідним.'
    elif confirmed_loss:
        m.recovery_since = None
        m.lost_report = inputs.room_report_id
        if thermostat_ok:
            m.mode = 'AUTO_PROPOSED'
            if m.auto_owner is None or previous_mode != 'AUTO_PROPOSED':
                m.auto_owner = inputs.owner
                intent = {'mode': 'AUTO', 'action': 'proposed_fallback', 'preserve_weekly_program': True}
                event = 'Втрачено підтверджені звіти вітальні. Запропоновано резервний AUTO.'
        else:
            m.mode = 'WAITING'
    elif m.auto_owner is not None:
        m.mode = 'RECOVERING'
        if (room_ok and inputs.room_report_id is not None and inputs.room_report_id != m.lost_report and thermostat_ok
                and inputs.plan_ok and not inputs.one_shot_blocked):
            if m.recovery_since is None:
                m.recovery_since, m.recovered_report = mono, inputs.room_report_id
            if mono - m.recovery_since >= policy.recovery_s:
                intent = {'mode': 'HEAT', 'action': 'proposed_recovery', 'owner': m.auto_owner}
                m.mode = 'HEAT_PROPOSED'
                event = 'Джерело вітальні відновлено. Запропоновано повернення до HEAT за планом.'
        else:
            m.recovery_since = None
    else:
        m.mode = 'NORMAL' if room_ok else 'WAITING'
    if intent is not None:
        intent = intent | {'physical_authority': False, 'stage': 'proposed', 'owner': inputs.owner}
        # Stable key is a proposal identity, never a physical ACK.
        key = f'{inputs.owner}:{m.mode}:{intent.get("action")}'
        if key == m.intent_key:
            intent = None
        else:
            m.transition_seq += 1
            m.intent_key = key
            intent['id'] = f'{key}:{m.transition_seq}'
            m.last_proposal = deepcopy(intent)
    active_proposal = None
    if guards and m.last_proposal is not None:
        action = m.last_proposal.get('action')
        if ((m.mode == 'AUTO_PROPOSED' and action == 'proposed_fallback' and inputs.electrical_eligible and thermostat_ok and confirmed_loss)
            or (m.mode == 'HEAT_PROPOSED' and action == 'proposed_recovery' and room_ok and inputs.electrical_eligible and thermostat_ok and inputs.plan_ok and not inputs.one_shot_blocked)
            or (m.mode == 'ELECTRICAL_INHIBIT' and action in ('withdraw_demand', 'cannot_confirm_withdrawal'))):
            active_proposal = deepcopy(m.last_proposal)
    notification = None
    if event:
        m.pending_notification = event if event != m.notification_key else ''
    if m.pending_notification and (m.notification_at is None or mono - m.notification_at >= policy.notification_cooldown_s):
        notification = m.pending_notification
        m.notification_at, m.notification_key, m.pending_notification = mono, notification, ''
    specs = [
        ('living_room', 'Датчик вітальні', inputs.room_status or ('OK' if room_ok else 'PROBLEM' if confirmed_loss else 'WAITING'),
         'critical' if confirmed_loss else 'warning', age,
         inputs.room_reason or ('Температура вітальні — єдина основа моделі та графіків' if room_ok else 'Втрачено підтверджені звіти' if confirmed_loss else 'Очікуємо достовірний звіт/heartbeat; незмінна температура не означає втрату')),
        ('fireplace', 'Камін і циркуляція', 'OK' if inputs.fireplace_qualified and inputs.fireplace_age_s is not None and 0 <= inputs.fireplace_age_s <= 300 else 'WAITING', 'warning', inputs.fireplace_age_s, 'Окреме джерело каміна; не замінює температуру вітальні'),
        ('thermostat', 'Термостат і контакти', 'OK' if thermostat_ok else 'WAITING', 'warning', inputs.thermostat_age_s, 'Власна температура, межі й readback лише для контактів; фізичний стан не підтверджений'),
        ('utility', 'Мережа та три фази', 'OK' if inputs.electrical_eligible else 'PROBLEM' if inputs.electrical_fault else 'WAITING', 'critical', None, inputs.electrical_reason),
        ('kws', 'Живлення та облік KWS', 'OK' if inputs.electrical_eligible and inputs.power_qualified else 'WAITING', 'warning', None, 'Очікування мережі/KWS або кваліфікованих звітів; відсутність не є 0 W'),
        ('controller', 'Контролер і план', 'OK' if guards and inputs.plan_ok and not (m.mode == 'ELECTRICAL_INHIBIT' and inputs.withdrawal is None) else 'PROBLEM' if not inputs.clock_ok or rollback or not inputs.persistence_ok or (m.mode == 'ELECTRICAL_INHIBIT' and inputs.withdrawal is None) else 'WAITING', 'critical', None, 'Не можна підтвердити зняття нагріву: потрібні власник і свіжий термостат' if m.mode == 'ELECTRICAL_INHIBIT' and inputs.withdrawal is None else 'STOP/власник мають пріоритет; аналіз не є виконавцем'),
    ]
    rows = []
    for key, label, status, severity, evidence_age, reason in specs:
        old = m.transitions.get(key)
        transition = old[2] if old and old[:2] == (status, reason) else now
        m.transitions[key] = (status, reason, transition)
        rows.append(dict(key=key, label=label, status=status, severity=severity, age_s=evidence_age,
                         reason=reason, checked_at=now, last_transition=transition, physical_verified=False,
                         fallback_action=m.mode))
    return dict(components=rows, mode=m.mode, intent=intent, proposal=active_proposal, notification=notification, last_notice=m.notification_key or None,
                physical_verified=False, semantics='proposed_only_no_device_ack'), m
