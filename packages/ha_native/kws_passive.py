"""Passive HA-state view of KWS Tuya Local channels, NOT raw meter evidence.

Do not elevate HA last_reported/last_changed, state polling or device metadata
to KWS measurement sequence, physical readiness, output state or contact ACK.
Only the separate, future commissioned raw-report path can provide those facts.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.contracts import Clock, QualityStatus, SourceKind
from packages.contracts.models import number, require
from .kws import KWSFrame, KWSPhaseName, KWSReading, KWSType

_ROLES: tuple[tuple[KWSType, KWSPhaseName], ...] = (
    ("active_power", "L1"),
    ("active_power", "L2"),
    ("active_power", "L3"),
    ("imported_energy", "total"),
)


@dataclass(frozen=True, slots=True)
class KWSHAChannel:
    """Externally supplied, registry-checked source binding; no public HA IDs."""
    entity_id: str
    device_id: str
    quantity: KWSType
    phase: KWSPhaseName
    unit: str
    integration: str = "tuya_local"

    def __post_init__(self) -> None:
        require(bool(self.entity_id) and bool(self.device_id)
                and self.integration == "tuya_local", "KWS source must be local and bound")
        require((self.quantity, self.phase) in _ROLES, "Unsupported KWS role")
        expected = "kWh" if self.quantity == "imported_energy" else "kW"
        require(self.unit == expected, "Wrong KWS unit")


@dataclass(frozen=True, slots=True)
class KWSHAState:
    """HA state metadata only; it contains NO independently verified raw report."""
    entity_id: str
    device_id: str
    integration: str
    unit: str
    value: float | None
    last_changed: float
    last_updated: float
    last_reported: float
    registry_verified: bool = False
    available: bool = True
    restored: bool = False

    def __post_init__(self) -> None:
        for at in (self.last_changed, self.last_updated, self.last_reported):
            number(at, nonnegative=True)
        require(self.last_changed <= self.last_updated <= self.last_reported,
                "Invalid HA state chronology")
        require(all(type(v) is bool for v in
                    (self.registry_verified, self.available, self.restored)),
                "Invalid HA state flags")
        if self.value is not None:
            number(self.value, nonnegative=True)


class KWSPassiveStateBridge:
    """In-memory state view; cannot create a physically qualified KWS reading."""

    physical_commands_enabled = False

    def __init__(self, bindings: tuple[KWSHAChannel, ...],
                 *, physical_commands_enabled: bool = False):
        require(physical_commands_enabled is False, "No physical KWS commands")
        require(type(bindings) is tuple and len(bindings) == len(_ROLES),
                "Exactly three phase power channels and one total counter required")
        require({(b.quantity, b.phase) for b in bindings} == set(_ROLES)
                and len({b.entity_id for b in bindings}) == len(_ROLES)
                and len({b.device_id for b in bindings}) == 1,
                "Incomplete, duplicate or cross-device KWS mapping")
        self.bindings = {b.entity_id: b for b in bindings}
        self.latest: dict[str, KWSHAState] = {}

    def observe(self, state: KWSHAState, clock: Clock) -> bool:
        """Accept one HA read-only state for diagnostics, never measurement."""
        binding = self.bindings.get(state.entity_id)
        if (binding is None or state.registry_verified is not True
                or state.restored is not False
                or (state.device_id, state.integration, state.unit)
                != (binding.device_id, binding.integration, binding.unit)
                or state.last_reported > clock.utc):
            return False
        previous = self.latest.get(state.entity_id)
        if previous is not None and state.last_reported <= previous.last_reported:
            return False
        self.latest[state.entity_id] = state
        return True

    def shadow_frame(self, clock: Clock) -> KWSFrame:
        """Reuse the accepted KWS contract with explicitly UNQUALIFIED samples.

        Zero is still not OFF; HA state timestamps are not hardware measurement
        timestamps, and the zero sequence is only an inert sentinel.
        """
        readings: list[KWSReading] = []
        for quantity, phase in _ROLES:
            b = next(b for b in self.bindings.values()
                     if (b.quantity, b.phase) == (quantity, phase))
            state = self.latest.get(b.entity_id)
            if state is None:
                continue
            readings.append(KWSReading(
                source_id=f"synthetic.kws.passive.{quantity}.{phase}",
                physical_id="synthetic.kws.passive.one_meter",
                phase=phase, quantity=quantity,
                value=state.value if state.available else None,
                unit="kWh" if quantity == "imported_energy" else "kW",
                last_reported=state.last_reported,
                received_at=clock.utc,
                sequence=0,
                online=None, heartbeat_verified=False,
                quality=QualityStatus.MISSING,
                origin=SourceKind.HELD, provider="tuya_local",
            ))
        return KWSFrame(tuple(readings), meter_id="synthetic.kws.passive.one_meter",
                        provider="tuya_local", verification=None,
                        calibration=None, online=None)

    def view(self, clock: Clock) -> dict[str, object]:
        channels: list[dict[str, object]] = []
        for quantity, phase in _ROLES:
            b = next(b for b in self.bindings.values()
                     if (b.quantity, b.phase) == (quantity, phase))
            obs = self.latest.get(b.entity_id)
            channels.append({
                "quantity": quantity, "phase": phase,
                "last_known": obs.value if obs is not None and obs.available else None,
                "unit": b.unit,
                "ha_report_age_s": max(0.0, clock.utc - obs.last_reported) if obs else None,
                "ha_value_change_age_s": max(0.0, clock.utc - obs.last_changed) if obs else None,
                "registry_state": "known" if obs is not None and obs.available else "unknown",
                "raw_measurement_qualified": False,
            })
        return {
            "scope": "read_only_ha_state", "origin": "tuya_local_ha_state",
            "power_w": None, "energy_kwh": None, "stage": "UNKNOWN",
            "physical_authority": False, "physical_heat": None,
            "reason": "no_verified_raw_kws_sequence_or_measurement_time",
            "channels": channels,
        }
