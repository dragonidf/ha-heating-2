"""Read-only projection using the ACCEPTED pure fireplace/fan policy.

No actuator services. Backup permission alone cannot prove physical supply.
State is bounded in memory and a restart simply re-enters observation.
"""
from __future__ import annotations

from .engine.fan_policy import FanPolicy, FanState, reduce_fan


MODES = {"Авто": "auto", "Ручний запуск": "manual", "Зупинити": "stop"}

def project(values: dict, previous: FanState | None, at: float, local_hour: int) -> tuple[FanState | None, dict]:
    mode = MODES.get(values.get("fan_mode_last_known"))
    speeds = values.get("fan_speed_percent_last_known", {})
    delta = values.get("fireplace_delta_c_last_known")
    result = {
        "origin": "ha_last_known_unverified", "physical_authority": False,
        "commands_sent": 0, "percentage_proposed": None, "reason": "unqualified",
        "burning_inferred": None,
        "backup_power_physical_ack": False,
    }
    if (mode is None or any(speeds.get(name) is None for name in
                            ("fan_night", "fan_standard", "fan_intense"))):
        return None, result
    try:
        policy = FanPolicy(
            speeds["fan_night"], speeds["fan_standard"], speeds["fan_intense"]
        )
        if previous is not None and at <= previous.at:
            return previous, result
        if previous is None:
            previous = FanState(at=max(0.0, at - 1), delta=None)
        grid = values.get("grid_last_known")
        # Only confirmed grid counts as supply in this observer.
        # Static backup-enabled helper alone does NOT prove inverter power.
        supply = grid is True
        valid = delta is not None
        demand = reduce_fan(
            previous, at, delta, valid=valid, grid=grid if supply else None,
            armed=values.get("fan_control_enabled_last_known") is True,
            permitted=supply, mode=mode, night=local_hour >= 23 or local_hour < 7,
            night_request=False, policy=policy,
        )
        result.update(
            percentage_proposed=demand.percentage,
            reason=demand.reason,
            burning_inferred=demand.state.burning if valid else None,
        )
        return demand.state, result
    except (ValueError, TypeError, ArithmeticError):
        return None, result
