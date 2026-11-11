"""Bounded HA climate service transport; no authority, planner, or AUTO fallback.

This module is deliberately *not* a controller. It can only execute an already
validated command while an external exclusive-writer/STOP/safety gate remains true.
An HA state echo is not a device ACK or proof of opened dry contacts.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Callable, Literal, Mapping, Protocol


class ClimateState(Protocol):
    state: str
    attributes: Mapping[str, Any]
    last_reported: datetime


class ClimateStates(Protocol):
    def get(self, entity_id: str) -> ClimateState | None: ...


class ClimateServices(Protocol):
    async def async_call(self, domain: str, service: str, service_data: dict[str, Any],
                         *, blocking: bool, context: Any) -> Any: ...


class ClimateHass(Protocol):
    states: ClimateStates
    services: ClimateServices


@dataclass(frozen=True, slots=True)
class ClimateOrder:
    """An already-approved, epoch-bound manual-HEAT setpoint intent."""
    identity: str
    owner_epoch: int
    target_c: float
    expected_previous_c: float
    kind: Literal["HEAT", "WITHDRAW"]
    upper_limit_c: float | None = None

    def __post_init__(self) -> None:
        if (not self.identity or type(self.owner_epoch) is not int or self.owner_epoch < 0
                or self.kind not in ("HEAT", "WITHDRAW")):
            raise ValueError("Invalid climate order identity/owner/kind")
        for value in (self.target_c, self.expected_previous_c):
            if not isinstance(value, (int, float)) or type(value) is bool or not isfinite(value):
                raise ValueError("Invalid temperature")
        if self.kind == "HEAT" and (self.upper_limit_c is None
                or not isinstance(self.upper_limit_c, (int, float))
                or type(self.upper_limit_c) is bool or not isfinite(self.upper_limit_c)
                or self.target_c > self.upper_limit_c):
            raise ValueError("HEAT must respect a validated upper limit")


@dataclass(frozen=True, slots=True)
class ClimateReceipt:
    status: Literal["BLOCKED", "UNCERTAIN", "HA_ECHO", "ALREADY_OBSERVED"]
    reason: str
    physical_ack: bool = False
    contacts_open: None = None


class LiveClimateTransport:
    """HA service adapter. Default disabled and NOT wired into production.

    The external gate must check the exclusive writer epoch and all accepted
    controller permissions on EVERY call: ownership, STOP, room ceiling, upstream
    grid/voltages, one-shot, persistence. Its critical ledger must durably claim
    each identity before dispatch and latch UNCERTAIN across reboot.
    This adapter NEVER automatically retries a service call.
    """

    def __init__(self, hass: ClimateHass, entity_id: str,
                 gate: Callable[[ClimateOrder], bool], *, enabled: bool = False,
                 timeout_s: float = 3.0, poll_s: float = .10):
        if not entity_id.startswith("climate.") or not callable(gate):
            raise ValueError("Explicit climate binding and gate required")
        if type(enabled) is not bool or not .1 <= timeout_s <= 10 or not .01 <= poll_s <= .5:
            raise ValueError("Invalid transport options")
        self.hass, self.entity_id, self.gate = hass, entity_id, gate
        self.enabled, self.timeout_s, self.poll_s = enabled, timeout_s, poll_s
        self._lock = asyncio.Lock()

    @staticmethod
    def _temp(value: Any) -> float | None:
        if type(value) not in (float, int) or not isfinite(value):
            return None
        return float(value)

    @staticmethod
    def _reported(state: ClimateState) -> float | None:
        try:
            return state.last_reported.timestamp()
        except (AttributeError, ValueError, OverflowError, OSError):
            return None

    def _snapshot(self, order: ClimateOrder, *, before: bool) -> tuple[str, float] | None:
        state = self.hass.states.get(self.entity_id)
        if state is None or state.state != "heat":
            return None
        attrs = state.attributes
        step = self._temp(attrs.get("target_temp_step"))
        minimum = self._temp(attrs.get("min_temp"))
        maximum = self._temp(attrs.get("max_temp"))
        target = self._temp(attrs.get("temperature"))
        local = self._temp(attrs.get("current_temperature"))
        if (step != .5 or minimum is None or maximum is None or target is None
                or local is None or minimum >= maximum or not minimum <= order.target_c <= maximum
                or abs(round(order.target_c * 2) - order.target_c * 2) > 1e-6):
            return None
        if before and abs(target - order.expected_previous_c) > .01:
            return None
        if order.kind == "WITHDRAW" and order.target_c >= local - .5:
            return None
        return (state.state, target)

    async def execute(self, order: ClimateOrder, *, context: Any) -> ClimateReceipt:
        """One service call, bounded fresh HA echo, never a physical ACK."""
        if (not self.enabled or self._lock.locked()
                or not getattr(context, "user_id", None) or not self.gate(order)):
            return ClimateReceipt("BLOCKED", "disabled_owner_or_context")
        async with self._lock:
            if not self.gate(order) or self._snapshot(order, before=True) is None:
                return ClimateReceipt("BLOCKED", "precondition_or_manual_mode")
            initial = self.hass.states.get(self.entity_id)
            if initial is None:
                return ClimateReceipt("BLOCKED", "thermostat_unavailable")
            baseline = self._reported(initial)
            if baseline is None:
                return ClimateReceipt("BLOCKED", "missing_ha_timestamp")
            if abs(float(initial.attributes["temperature"]) - order.target_c) <= .01:
                return ClimateReceipt("ALREADY_OBSERVED", "unchanged_setpoint_not_device_ack")
            if not self.gate(order) or self._snapshot(order, before=True) is None:
                return ClimateReceipt("BLOCKED", "revoked_before_send")
            deadline = asyncio.get_running_loop().time() + self.timeout_s
            try:
                await asyncio.wait_for(self.hass.services.async_call(
                    "climate", "set_temperature", {"entity_id": self.entity_id, "temperature": order.target_c},
                    blocking=True, context=context), timeout=self.timeout_s)
            except (Exception, asyncio.CancelledError):
                return ClimateReceipt("UNCERTAIN", "service_error_or_timeout")
            while True:
                if not self.gate(order):
                    return ClimateReceipt("UNCERTAIN", "owner_or_safety_revoked_after_send")
                observed = self._snapshot(order, before=False)
                state = self.hass.states.get(self.entity_id)
                if observed is None or state is None:
                    return ClimateReceipt("UNCERTAIN", "mode_or_thermostat_changed")
                at = self._reported(state)
                if at is not None and at > baseline:
                    if abs(observed[1] - order.target_c) <= .01:
                        return ClimateReceipt("HA_ECHO", "ha_state_only_not_physical_ack")
                    return ClimateReceipt("UNCERTAIN", "contradictory_new_state")
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return ClimateReceipt("UNCERTAIN", "no_new_ha_echo")
                await asyncio.sleep(min(self.poll_s, remaining))
