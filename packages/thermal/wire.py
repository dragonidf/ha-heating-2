"""Strict WP1C schema 1.0; pure JSON boundary, no persistent store."""

import json
from dataclasses import fields, is_dataclass, MISSING
from types import UnionType
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
from packages.contracts.models import require, number, ContractError
from packages.contracts.codec import _encode, _unique_object, _bad_constant
from packages.thermal import Interval, Coefficients, ThermalState, Forcing
from packages.planner import (
    Stamp,
    Forecast,
    Slot,
    Morning,
    Request,
    Proposal,
    Curve,
    References,
)
from packages.learning import (
    Transition,
    ValidationPoint,
    Metric,
    Candidate,
    Qualification,
    Promotion,
    Backtest,
)
from packages.planner.evidence import Recommendation, CycleBudget
from packages.planner.policy import ComfortPolicy
from packages.planner.sources import WeatherPoint, WeatherSeries, OutageSchedule
from packages.fan_policy import FanState, FanPolicy, FanDemand

TYPES = (
    Interval,
    Coefficients,
    ThermalState,
    Forcing,
    Stamp,
    Forecast,
    Slot,
    Morning,
    Request,
    Proposal,
    Curve,
    References,
    Transition,
    ValidationPoint,
    Metric,
    Candidate,
    Qualification,
    Promotion,
    Backtest,
    FanState,
    FanPolicy,
    FanDemand,
    Backtest,
    WeatherPoint,
    WeatherSeries,
    OutageSchedule,
    ComfortPolicy,
    Recommendation,
    CycleBudget,
)


def encode(value: object) -> str:
    require(type(value) in TYPES, "Unknown WP1C record")
    payload = json.dumps(
        dict(version=[1, 0], type=type(value).__name__, data=_encode(value)),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    require(len(payload.encode()) <= 524288, "WP1C payload too large")
    return payload


def _decode(value: object, annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, UnionType):
        for choice in args:
            try:
                return _decode(value, choice)
            except ContractError:
                pass
        raise ContractError("Invalid optional value")
    if origin is Literal:
        require(value in args, "Invalid literal")
        return value
    if origin is tuple:
        if not isinstance(value, list):
            raise ContractError("Expected array")
        require(len(value) <= 4096, "Invalid bounded array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(v, args[0]) for v in value)
        require(len(value) == len(args), "Invalid fixed tuple")
        return tuple(_decode(v, t) for v, t in zip(value, args))
    if annotation is type(None):
        require(value is None, "Expected null")
        return None
    if annotation in (str, int, bool):
        require(type(value) is annotation, "Invalid scalar")
        return value
    if annotation is float:
        number(value)
        return value
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        require(type(value) is str, "Invalid enum")
        try:
            return annotation(value)
        except ValueError:
            raise ContractError("Invalid enum") from None
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict):
            raise ContractError("Expected record")
        definitions = fields(annotation)
        hints = get_type_hints(annotation)
        require(not set(value) - {f.name for f in definitions}, "Unknown record field")
        result = {}
        for f in definitions:
            if f.name in value:
                result[f.name] = _decode(value[f.name], hints[f.name])
            else:
                require(
                    f.default is not MISSING or f.default_factory is not MISSING,
                    "Missing record field",
                )
        return annotation(**result)
    raise ContractError("Unknown annotation")


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
            obj["version"] == [1, 0] and all(type(v) is int for v in obj["version"]),
            "Unsupported schema",
        )
        cls = next((t for t in TYPES if t.__name__ == obj["type"]), None)
        require(cls is not None, "Unknown type")
        return _decode(obj["data"], cls)
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ContractError("Invalid WP1C record") from None
