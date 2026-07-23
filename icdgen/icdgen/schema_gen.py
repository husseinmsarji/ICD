"""Derive JSON Schema fragments from the field registries.

The JSON Schema objects for *signals* and *interfaces* are GENERATED here from
the ``FieldSpec`` registries, so the validation rules can never drift from the
serializer or the model. The loader assembles the full document schema
(``loader._data_schema``) around these fragments and validates the parsed YAML
against it.
"""
from __future__ import annotations

from .fields import INTERFACE_FIELDS, SIGNAL_FIELDS


def _json_object(fields) -> dict:
    props: dict = {}
    required: list[str] = []
    for f in fields:
        spec: dict = {}
        if f.enum_values() is not None:
            vals = list(f.enum_values())
            if not f.required and "" not in vals:
                vals = vals + [""]  # allow blank for in-progress optional enums
            spec["enum"] = vals
        elif f.py_type is str:
            spec["type"] = "string"
            if f.pattern:
                spec["pattern"] = f"^{f.pattern}$"
            if f.min_length:
                spec["minLength"] = f.min_length
        elif f.py_type is float:
            spec["type"] = "number"
            if f.positive:
                spec["exclusiveMinimum"] = 0
            if f.min_inclusive is not None:
                spec["minimum"] = f.min_inclusive
        elif f.py_type is int:
            spec["type"] = "integer"
            if f.positive:
                spec["exclusiveMinimum"] = 0
        elif f.py_type is bool:
            spec["type"] = "boolean"
        props[f.json_name] = spec
        if f.required:
            required.append(f.json_name)
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": props,
    }


def json_signal_schema() -> dict:
    return _json_object(SIGNAL_FIELDS)


def json_interface_schema() -> dict:
    return _json_object(INTERFACE_FIELDS)
