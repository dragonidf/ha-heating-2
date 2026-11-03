"""Strict WP2A envelope2.0, no transport or dynamic import."""

import json
from typing import Any
from packages.contracts.codec import (
    CONTRACT_TYPES,
    _encode,
    _unique_object,
    _bad_constant,
)
from packages.contracts.models import ContractError, require
from packages.thermal.wire import TYPES as THERMAL_TYPES, _decode
from packages.offline.contracts import (
    Binding,
    Registry,
    SourceEvent,
    Principal,
    SaveRequest,
    APIReceipt,
    PowerPoint,
    CounterPoint,
    EnergySlice,
    Origin,
    Tariff,
    ForecastRecord,
    ArchiveRecord,
    Cursor,
    RecoveryRequest,
    RecoveryReceipt,
    CounterMapping,
    LegacyBundle,
    MigrationPlan,
    ManifestEntry,
    BalanceTopology,
    ArchivePage,
    EnergySummary,
    MigrationReceipt,
    RollbackResult,
    CostSummary,
    StatusView,
    ProviderEvent,
    BudgetReceipt,
)

TYPES = (
    *CONTRACT_TYPES,
    *THERMAL_TYPES,
    Binding,
    Registry,
    SourceEvent,
    Principal,
    SaveRequest,
    APIReceipt,
    PowerPoint,
    CounterPoint,
    EnergySlice,
    Origin,
    Tariff,
    ForecastRecord,
    ArchiveRecord,
    Cursor,
    RecoveryRequest,
    RecoveryReceipt,
    CounterMapping,
    LegacyBundle,
    MigrationPlan,
    ManifestEntry,
    BalanceTopology,
    ArchivePage,
    EnergySummary,
    MigrationReceipt,
    RollbackResult,
    CostSummary,
    StatusView,
    ProviderEvent,
    BudgetReceipt,
)


def encode(value: object) -> str:
    require(type(value) in TYPES, "Unknown offline record")
    try:
        payload = json.dumps(
            dict(version=[2, 0], type=type(value).__name__, data=_encode(value)),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        require(len(payload.encode()) <= 524288, "Offline record too large")
        return payload
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ContractError("Invalid offline record") from None


def decode(payload: str) -> Any:
    try:
        require(
            type(payload) is str and len(payload.encode()) <= 524288, "Invalid payload"
        )
        obj = json.loads(
            payload, object_pairs_hook=_unique_object, parse_constant=_bad_constant
        )
        require(
            type(obj) is dict and set(obj) == {"version", "type", "data"},
            "Invalid envelope",
        )
        require(
            obj["version"] == [2, 0] and all(type(v) is int for v in obj["version"]),
            "Unsupported offline version",
        )
        cls = next((t for t in TYPES if t.__name__ == obj["type"]), None)
        require(cls is not None, "Unknown offline type")
        return _decode(obj["data"], cls)
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ContractError("Invalid offline record") from None
