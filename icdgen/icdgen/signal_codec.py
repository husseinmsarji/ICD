"""Registry-driven conversion of a Signal to/from dict representations.

All per-field logic loops over ``SIGNAL_FIELDS`` (and ``INTERFACE_FIELDS``) so
that adding a field to the registry automatically flows through parsing and
serialization with no edits here. This is the second half of the "one place to
add a field" guarantee (``schema_gen`` covers validation; this module covers
data movement).

Two dict representations exist, both keyed by ``FieldSpec.json_name``:
  * ``*_to_json_dict`` / ``*_from_json_dict`` — the LOOSE, all-fields shape used
    by the web API DTOs (every key present, so the wire contract is stable).
  * ``*_to_yaml_dict`` — the MINIMAL, ordered shape the canonical YAML serializer
    emits (optional/blank fields dropped via ``FieldSpec.emit_if``).

Coercion rules per ``FieldSpec.py_type``:
  * float -> float(value)
  * int   -> int(value)
  * bool  -> "true"/True interpreted as True
  * str   -> str(value), with absent optionals becoming the spec default
"""
from __future__ import annotations

from typing import Any

from .fields import SIGNAL_FIELDS, INTERFACE_FIELDS, FieldSpec
from .model import Interface, Packet, Signal


def _coerce(spec: FieldSpec, value: Any) -> Any:
    if value is None:
        return spec.default
    if spec.py_type is float:
        return float(value)
    if spec.py_type is int:
        return int(value)
    if spec.py_type is bool:
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"
    # str
    return str(value)


# ===========================================================================
# Signal codec
# ===========================================================================
def signal_from_values(values: dict[str, Any]) -> Signal:
    """Build a Signal from a dict keyed by FieldSpec.name (snake_case)."""
    kwargs = {}
    for f in SIGNAL_FIELDS:
        kwargs[f.name] = _coerce(f, values.get(f.name, f.default))
    return Signal(**kwargs)


def signal_to_json_dict(sig: Signal) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in SIGNAL_FIELDS:
        out[f.json_name] = getattr(sig, f.name)
    return out


def signal_from_json_dict(d: dict[str, Any]) -> Signal:
    values: dict[str, Any] = {}
    for f in SIGNAL_FIELDS:
        values[f.name] = d.get(f.json_name, f.default)
    return signal_from_values(values)


# ===========================================================================
# Interface codec. The ``packets`` collection is handled structurally (it is a
# child collection, not a scalar field).
# ===========================================================================
def interface_from_values(values: dict[str, Any], packets) -> Interface:
    kwargs = {}
    for f in INTERFACE_FIELDS:
        kwargs[f.name] = _coerce(f, values.get(f.name, f.default))
    kwargs["packets"] = tuple(packets)
    return Interface(**kwargs)


def interface_to_json_dict(iface: Interface) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in INTERFACE_FIELDS:
        out[f.json_name] = getattr(iface, f.name)
    out["packets"] = [packet_to_json_dict(p) for p in iface.packets]
    return out


def interface_from_json_dict(d: dict[str, Any]) -> Interface:
    values: dict[str, Any] = {}
    for f in INTERFACE_FIELDS:
        values[f.name] = d.get(f.json_name, f.default)
    packets = [packet_from_json_dict(p) for p in d.get("packets", [])]
    return interface_from_values(values, packets)


# ===========================================================================
# Packet codec. A packet groups signals under a name. It has a `name`, an
# optional `description`, and a `signals` child collection. Packets are
# structural (fixed shape), so unlike signals/interfaces they are not
# registry-driven — there is nothing to extend per-field.
# ===========================================================================
def packet_to_json_dict(pkt: Packet) -> dict[str, Any]:
    return {
        "name": pkt.name,
        "description": pkt.description,
        "signals": [signal_to_json_dict(s) for s in pkt.signals],
    }


def packet_from_json_dict(d: dict[str, Any]) -> Packet:
    return Packet(
        name=d.get("name", ""),
        description=d.get("description"),
        signals=tuple(signal_from_json_dict(s) for s in d.get("signals", [])),
    )


# ===========================================================================
# Canonical-YAML dict builders. Unlike the *_to_json_dict functions (which are
# the loose, all-fields API representation), these produce the MINIMAL ordered
# dict the serializer emits: registry order, with optional/blank fields dropped
# via each FieldSpec.emit_if. Keys are FieldSpec.json_name (camelCase), which
# double as the YAML keys.
# ===========================================================================
def _yaml_value(f: FieldSpec, obj) -> Any:
    val = getattr(obj, f.name)
    if val is None:
        # A field with no emit_if and a None value falls back to its default
        # (blank string for required text fields) so the key is still present.
        return f.default if f.default is not None else ""
    return val


def signal_to_yaml_dict(sig: Signal) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in SIGNAL_FIELDS:
        val = getattr(sig, f.name)
        if f.emit_if and not f.emit_if(val):
            continue
        out[f.json_name] = _yaml_value(f, sig)
    return out


def interface_to_yaml_dict(iface: Interface) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in INTERFACE_FIELDS:
        val = getattr(iface, f.name)
        if f.emit_if and not f.emit_if(val):
            continue
        out[f.json_name] = _yaml_value(f, iface)
    out["packets"] = [packet_to_yaml_dict(p) for p in iface.packets]
    return out


def packet_to_yaml_dict(pkt: Packet) -> dict[str, Any]:
    out: dict[str, Any] = {"name": pkt.name}
    if pkt.description:
        out["description"] = pkt.description
    out["signals"] = [signal_to_yaml_dict(s) for s in pkt.signals]
    return out
