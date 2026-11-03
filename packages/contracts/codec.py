"""Strict JSON envelopes for the explicitly supported immutable contracts."""
import json
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, NoReturn, TypeVar, Union, get_args, get_origin, get_type_hints, overload

from .models import (
    Clock, ContractError, ControlSnapshot, Missing, Plan, PlanSegment, Provenance,
    Quality, Reading, Revisions, TimeWindow, number, require,
)
from .control import (
    CommandIntent, CommandReceipt, ControlEvent, ControlPolicy, ControlState,
    Decision, HeatPermit, OneShot,
)

MAX_PAYLOAD_BYTES = 256 * 1024
CONTRACT_TYPES = (Quality, Provenance, Reading, Clock, Revisions, TimeWindow,
                  PlanSegment, Plan, ControlSnapshot, CommandIntent, CommandReceipt,
                  ControlEvent, ControlPolicy, ControlState, Decision, HeatPermit, OneShot)
T = TypeVar("T")


def _encode(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)
                if getattr(value, f.name) is not Missing.VALUE}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def to_json(value: object) -> str:
    require(type(value) in CONTRACT_TYPES, "Unsupported contract type")
    try:
        payload = json.dumps(dict(schema_version=dict(major=1, minor=0),
                                  type=type(value).__name__, data=_encode(value)),
                             allow_nan=False, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":"))
        require(len(payload.encode("utf-8")) <= MAX_PAYLOAD_BYTES, "Payload too large")
        return payload
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ContractError("Cannot serialize contract") from None


def _decode(value: object, annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        for option in get_args(annotation):
            try:
                return _decode(value, option)
            except ContractError:
                continue
        raise ContractError("Value does not match union")
    if origin is tuple:
        if not isinstance(value, list):
            raise ContractError("Expected array")
        require(len(value) <= 4096, "Expected bounded array")
        return tuple(_decode(item, get_args(annotation)[0]) for item in value)
    if annotation is type(None):
        require(value is None, "Expected null")
        return None
    if annotation is Missing:
        raise ContractError("Absent marker is not a wire value")
    if annotation in (str, bool, int):
        require(type(value) is annotation, "Invalid scalar type")
        return value
    if annotation is float:
        number(value)
        return value
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        require(type(value) is str, "Expected enum string")
        try:
            return annotation(value)
        except ValueError:
            raise ContractError("Unknown enum value") from None
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict):
            raise ContractError("Expected contract object")
        definitions = fields(annotation)
        require(not set(value) - {f.name for f in definitions}, "Unknown contract fields")
        hints = get_type_hints(annotation)
        decoded = {}
        for f in definitions:
            if f.name in value:
                decoded[f.name] = _decode(value[f.name], hints[f.name])
            else:
                require(f.default is not MISSING or f.default_factory is not MISSING,
                        "Missing required contract field")
        return annotation(**decoded)
    raise ContractError("Unsupported schema annotation")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _bad_constant(value: str) -> NoReturn:
    raise ContractError("Nonfinite JSON constant")


@overload
def from_json(payload: str, expected_type: type[T]) -> T: ...


@overload
def from_json(payload: str, expected_type: None = None) -> Any: ...


def from_json(payload: str, expected_type: type[T] | None = None) -> Any:
    try:
        require(type(payload) is str and len(payload.encode("utf-8")) <= MAX_PAYLOAD_BYTES,
                "Invalid/oversized payload")
        envelope = json.loads(payload, object_pairs_hook=_unique_object,
                              parse_constant=_bad_constant)
        require(type(envelope) is dict
                and set(envelope) == {"schema_version", "type", "data"}, "Invalid envelope")
        version = envelope["schema_version"]
        require(type(version) is dict and set(version) == {"major", "minor"}
                and type(version["major"]) is int and type(version["minor"]) is int
                and version == {"major": 1, "minor": 0}, "Unsupported schema version")
        model = next((cls for cls in CONTRACT_TYPES if cls.__name__ == envelope["type"]), None)
        require(model is not None and (expected_type is None or model is expected_type),
                "Unexpected contract type")
        return _decode(envelope["data"], model)
    except (ValueError, TypeError, RecursionError, UnicodeError, KeyError):
        raise ContractError("Invalid contract payload") from None
