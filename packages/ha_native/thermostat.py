"""Final synthetic HEAT limiter; the effective planner limit is input, never guessed."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from packages.contracts.models import number, require
from .store import JSON
from .voltage import synthetic_heat_withdrawal


@dataclass(frozen=True)
class ActiveRoomLimit:
    source_mode: str
    upper_c: float
    comfort_target_c: float
    reserve_margin_c: float = 2.5
    qualified: bool = False

    def __post_init__(self) -> None:
        require(isinstance(self.source_mode, str) and 0 < len(self.source_mode) <= 64, 'Invalid effective limit source')
        for value in (self.upper_c, self.comfort_target_c, self.reserve_margin_c):
            number(value)
        number(float(Decimal(str(self.upper_c))+Decimal(str(self.reserve_margin_c))))
        require(self.reserve_margin_c >= 0 and self.comfort_target_c <= self.upper_c
                and type(self.qualified) is bool, 'Invalid effective limit')


def supported_ceiling(limit: ActiveRoomLimit | None, minimum: float | None,
                      maximum: float | None, step: float | None) -> float | None:
    if limit is None or not limit.qualified:
        return None
    try:
        for value in (minimum, maximum, step):
            number(value)
        low, high, quantum = (Decimal(str(v)) for v in (minimum, maximum, step))
        if low >= high or quantum != Decimal('0.5') or quantum > high-low:
            return None
        raw = Decimal(str(limit.upper_c)) + Decimal(str(limit.reserve_margin_c))
        cap = low + ((min(raw,high)-low)/quantum).to_integral_value(rounding=ROUND_FLOOR)*quantum
        result = float(cap)
        if not low <= cap <= high or cap > raw or Decimal(str(result)) != cap:
            return None
        return result
    except (ValueError, TypeError, ArithmeticError):
        return None


def finalize_heat_setpoint(*, limit: ActiveRoomLimit | None, room_c: float | None,
                           requested_setpoint_c: float | None, heat_permitted: bool,
                           planner_requests_heat: bool, thermostat_c: float | None,
                           min_setpoint_c: float | None, max_setpoint_c: float | None,
                           temperature_step_c: float | None, thermostat_fresh: bool,
                           thermostat_mode: str, owns_thermostat: bool,
                           manual_stop: bool) -> dict[str, JSON] | None:
    """No command sender: every result is a proposal without ACK/contact proof."""
    if manual_stop or owns_thermostat is not True:
        return None
    common: dict[str, JSON] = dict(physical_authority=False, physical_ack=False,
        acknowledged_setpoint_c=None, stage='proposed', scope='synthetic_only')
    if thermostat_mode != 'HEAT':
        return common | dict(action='cannot_confirm_withdrawal', reason='vendor_auto_or_mode_unknown_ceiling_not_enforced')
    ceiling = supported_ceiling(limit,min_setpoint_c,max_setpoint_c,temperature_step_c)
    if ceiling is None:
        return common | dict(action='cannot_confirm_withdrawal', reason='effective_limit_or_capabilities_unqualified', ceiling_c=None)
    reason = 'safety_or_planner_inhibit'
    try:
        number(thermostat_c)
        if room_c is not None:
            number(room_c)
        if thermostat_fresh is not True:
            raise ValueError('Stale thermostat')
        if ceiling is None or limit is None or not limit.qualified:
            reason = 'effective_limit_or_capabilities_unqualified'
        elif room_c is None:
            reason = 'room_measurement_unqualified'
        elif room_c >= min(limit.comfort_target_c,limit.upper_c):
            reason = 'room_target_or_upper_reached'
        elif heat_permitted is True and planner_requests_heat is True:
            number(requested_setpoint_c)
            low, quantum = Decimal(str(min_setpoint_c)), Decimal('0.5')
            wanted = min(Decimal(str(requested_setpoint_c)),Decimal(str(ceiling)))
            candidate = low+((wanted-low)/quantum).to_integral_value(rounding=ROUND_FLOOR)*quantum
            value = float(candidate)
            if (candidate >= low and candidate <= Decimal(str(ceiling)) and Decimal(str(value)) == candidate
                    and thermostat_c is not None and value > thermostat_c):
                return common | dict(action='request_heat', mode='HEAT', setpoint_c=value,
                                     ceiling_c=ceiling, reason='planner_demand_capped')
            reason = 'no_supported_heat_target_below_ceiling'
    except (ValueError, TypeError, ArithmeticError):
        reason = 'thermostat_or_requested_target_unqualified'
    maximum = min(max_setpoint_c,ceiling) if max_setpoint_c is not None and ceiling is not None else max_setpoint_c
    withdrawal = synthetic_heat_withdrawal(thermostat_c=thermostat_c,min_setpoint_c=min_setpoint_c,
        max_setpoint_c=maximum,temperature_step_c=temperature_step_c,thermostat_fresh=thermostat_fresh,
        owns_thermostat=owns_thermostat,manual_stop=manual_stop)
    if withdrawal is None:
        return None
    return withdrawal | common | dict(reason=reason if withdrawal['action']=='withdraw_demand' else withdrawal['reason'], ceiling_c=ceiling)
