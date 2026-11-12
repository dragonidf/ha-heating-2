"""Real HA-state -> accepted PURE kernel. Hard-wired SHADOW; never dispatches.

HA cache writes are not raw-device samples. Live values can be displayed but
cannot qualify as independent physical evidence for a HEAT permit.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .engine.contracts import (
    Clock, ControlEvent, ControlMode, ControlPolicy, ControlSnapshot,
    ControlState, EventKind, Provenance, Quality, QualityStatus,
    Reading, Revisions, SourceKind, Unit,
)
from .engine.control import reduce


def _held(value: float | bool | None, unit: Unit, source: str,
          now: float) -> Reading | None:
    if value is None:
        return None
    return Reading(
        physical_id="ha.cached." + source,
        source_id="ha." + source,
        value=value, unit=unit,
        observed_at=now, received_at=now,
        quality=Quality(
            status=QualityStatus.STALE, age_s=0.0,
            reason="not_verified_physical_measurement",
        ),
        provenance=Provenance(kind=SourceKind.HELD, independent=False),
        evidence_ids=(),
    )


def shadow_decision(values: dict[str, Any]) -> dict[str, Any]:
    """One bounded, stateless diagnostic tick using accepted control code."""
    utc = time.time()
    clock = Clock(utc=utc, monotonic=time.monotonic(), boot_id="ha-v2-shadow")
    stamp = hashlib.sha256(json.dumps(
        {k: values.get(k) for k in (
            "room_c_last_known", "return_c_last_known",
            "thermostat_mode_last_known",
            "grid_last_known", "kws_total_kw_last_known"
        )}, sort_keys=True, default=str,
    ).encode()).hexdigest()
    snapshot = ControlSnapshot(
        snapshot_id="shadow-" + stamp[:24],
        input_hash=stamp,
        boot_id=clock.boot_id,
        revisions=Revisions(config=0, model=0, topology=0),
        grid_epoch=0, owner_epoch=0,
        captured_at=utc,
        room=_held(values.get("room_c_last_known"), Unit.CELSIUS, "room", utc),
        return_temperature=_held(values.get("return_c_last_known"), Unit.CELSIUS, "return_probe", utc),
        thermostat=None,
        grid_actual=_held(values.get("grid_last_known"), Unit.BOOLEAN, "grid", utc),
        forecast_grid=None,
        power=_held(values.get("kws_total_kw_last_known"), Unit.KILOWATT, "kws", utc),
        compute_available=False,
        hard_stop=True,
        scheduled_outage=False,
    )
    policy = ControlPolicy(
        config_revision=0,
        operating_mode=ControlMode.SHADOW,
        armed=False, allow_automatic=False,
        configuration_valid=False, limits_qualified=False,
        room_upper_c=None, return_upper_c=None,
        room_max_age_s=0.0, return_max_age_s=0.0,
        thermostat_max_age_s=0.0, grid_max_age_s=0.0,
        snapshot_max_age_s=5.0, max_skew_s=0.0,
        min_on_s=0.0, min_off_s=0.0,
        intent_ttl_s=5.0, recovery_stable_s=0.0,
        strict_windows=None,
    )
    event = ControlEvent(
        kind=EventKind.TICK, boot_id=clock.boot_id,
        owner_epoch=0, sequence=0, at=utc, expires_at=utc + 5,
    )
    decision = reduce(
        ControlState(boot_id=clock.boot_id, owner_epoch=0),
        event, snapshot, policy, clock,
    )
    if decision.permit.allowed or decision.intents:
        raise RuntimeError("SHADOW kernel safety invariant violated")
    return {
        "kernel": "accepted_control",
        "mode": decision.state.mode.value,
        "permit": False,
        "reason": decision.permit.reason.value,
        "intents": 0,
        "actual_commands_sent": 0,
        "physical_authority": False,
        "unverified_sources": [
            "room_physical_report", "return_probe", "thermostat_dry_contact",
            "grid_raw_sample", "voltage_raw_sample",
        ],
    }
