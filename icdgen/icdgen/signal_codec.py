"""Registry-driven conversion of a Signal to/from XML, JSON, and dicts.

All per-field logic loops over ``SIGNAL_FIELDS`` so that adding a field to the
registry automatically flows through parsing and serialization with no edits
here. This is the second half of the "one place to add a field" guarantee
(``schema_gen`` covers validation; this module covers data movement).

Coercion rules per ``FieldSpec.py_type``:
  * float -> float(value)
  * bool  -> "true"/True interpreted as True
  * str   -> str(value), with absent optionals becoming the spec default

Element vs attribute placement and the ``emit_if`` predicate are honored so XML
output is byte-identical to the previous hand-written serializer.
"""
from __future__ import annotations

from typing import Any

from .fields import SIGNAL_FIELDS, XML_ATTRIBUTE, XML_ELEMENT, FieldSpec
from .model import Signal


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


def signal_from_values(values: dict[str, Any]) -> Signal:
    """Build a Signal from a dict keyed by FieldSpec.name (snake_case)."""
    kwargs = {}
    for f in SIGNAL_FIELDS:
        kwargs[f.name] = _coerce(f, values.get(f.name, f.default))
    return Signal(**kwargs)


# -------- XML --------
def parse_signal_xml(sig_el, ns: str, text_of) -> Signal:
    """Parse a <signal> lxml element into a Signal using the registry.

    ``text_of(elem, tag, default)`` reads a child element's text (passed in to
    avoid a circular import with loader's helpers).
    """
    values: dict[str, Any] = {}
    for f in SIGNAL_FIELDS:
        if f.xml_location == XML_ATTRIBUTE:
            raw = sig_el.get(f.xml_name)
        else:
            raw = text_of(sig_el, f.xml_name, None)
        values[f.name] = raw
    return signal_from_values(values)


def signal_xml_lines(sig: Signal, indent: str, esc, num) -> list[str]:
    """Render a <signal> element. ``esc`` escapes text; ``num`` formats floats."""
    attr_parts = []
    for f in SIGNAL_FIELDS:
        if f.xml_location != XML_ATTRIBUTE:
            continue
        val = getattr(sig, f.name)
        if f.emit_if and not f.emit_if(val):
            continue
        if f.py_type is bool:
            rendered = "true" if val else "false"
        else:
            rendered = esc(val)
        attr_parts.append(f'{f.xml_name}="{rendered}"')
    open_tag = f"{indent}<signal {' '.join(attr_parts)}>"

    inner = indent + "  "
    body: list[str] = []
    for f in SIGNAL_FIELDS:
        if f.xml_location != XML_ELEMENT:
            continue
        val = getattr(sig, f.name)
        if f.emit_if and not f.emit_if(val):
            continue
        if f.py_type is float:
            rendered = num(val)
        elif f.py_type is int:
            rendered = str(val)
        else:
            rendered = esc("" if val is None else val)
        body.append(f"{inner}<{f.xml_name}>{rendered}</{f.xml_name}>")

    return [open_tag, *body, f"{indent}</signal>"]


# -------- JSON / dict (camelCase keys, for the API DTOs) --------
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
# Interface-level codec. Mirrors the signal codec but over INTERFACE_FIELDS.
# The <signals> collection is handled by the caller (loader/serializer), since
# it is a child collection, not a scalar field.
# ===========================================================================
from .fields import INTERFACE_FIELDS  # noqa: E402
from .model import Interface  # noqa: E402


def interface_from_values(values: dict[str, Any], packets) -> Interface:
    kwargs = {}
    for f in INTERFACE_FIELDS:
        kwargs[f.name] = _coerce(f, values.get(f.name, f.default))
    kwargs["packets"] = tuple(packets)
    return Interface(**kwargs)


def parse_interface_xml(iface_el, ns: str, text_of, packets) -> Interface:
    values: dict[str, Any] = {}
    for f in INTERFACE_FIELDS:
        if f.xml_location == XML_ATTRIBUTE:
            values[f.name] = iface_el.get(f.xml_name)
        else:
            values[f.name] = text_of(iface_el, f.xml_name, None)
    return interface_from_values(values, packets)


def interface_open_xml(iface: Interface, indent: str, esc) -> tuple[str, list[str]]:
    """Return (open-tag-with-attributes, list-of-child-element-lines BEFORE
    <signals>). The caller appends the <signals> block and the close tag, to
    preserve the existing serialization structure exactly."""
    attr_parts = []
    for f in INTERFACE_FIELDS:
        if f.xml_location != XML_ATTRIBUTE:
            continue
        val = getattr(iface, f.name)
        if f.emit_if and not f.emit_if(val):
            continue
        attr_parts.append(f'{f.xml_name}="{esc(val)}"')
    open_tag = f"{indent}<interface {' '.join(attr_parts)}>"

    inner = indent + "  "
    body: list[str] = []
    for f in INTERFACE_FIELDS:
        if f.xml_location != XML_ELEMENT:
            continue
        val = getattr(iface, f.name)
        if f.emit_if and not f.emit_if(val):
            continue
        body.append(f"{inner}<{f.xml_name}>{esc('' if val is None else val)}</{f.xml_name}>")
    return open_tag, body


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
# Packet-level codec. A packet groups signals under a name. It has a `name`
# attribute, an optional `description`, and a <signals> child collection.
# Packets are structural (fixed shape), so unlike signals/interfaces they are
# not registry-driven — there is nothing to extend per-field.
# ===========================================================================
from .model import Packet  # noqa: E402


def parse_packet_xml(pkt_el, ns: str, text_of, signals) -> Packet:
    return Packet(
        name=pkt_el.get("name"),
        description=text_of(pkt_el, "description", None),
        signals=tuple(signals),
    )


def packet_xml_lines(pkt: Packet, indent: str, esc,
                     signal_lines_fn) -> list[str]:
    """Render a <packet> element. ``signal_lines_fn(sig, indent)`` renders one
    signal (passed in to avoid a circular dependency with the serializer)."""
    lines = [f'{indent}<packet name="{esc(pkt.name)}">']
    inner = indent + "  "
    if pkt.description:
        lines.append(f"{inner}<description>{esc(pkt.description)}</description>")
    lines.append(f"{inner}<signals>")
    for sig in pkt.signals:
        lines.extend(signal_lines_fn(sig, inner + "  "))
    lines.append(f"{inner}</signals>")
    lines.append(f"{indent}</packet>")
    return lines


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
