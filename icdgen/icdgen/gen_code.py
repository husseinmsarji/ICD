"""Source-code artifact generators: C header and Simulink bus script.

The C header targets MISRA C:2012: fixed-width types, fully parenthesized macro
bodies, and integer-constant suffixes (U for unsigned). Both generators are pure
template renders over the canonical model, making them trivially deterministic.

Optional numeric fields (range_min/range_max/update_rate_hz) may be None on an
in-progress ICD; the helpers below tolerate None and the template emits a
placeholder comment instead of a #define in that case.

MACRO-NAME SAFETY: packet names are unconstrained xs:string and signal names
use the relaxed (non-C-identifier-permitting) pattern, so every token embedded
in a #define name goes through `macro_token` (sanitize + uppercase). Struct
FIELD names intentionally stay raw: silently rewriting a wire-mapped field name
would be worse than the existing non-C-identifier warning, which already covers
that case.
"""
from __future__ import annotations

import re

from jinja2 import Environment, FileSystemLoader

from .model import IcdModel, Interface, Packet, Signal
from .provenance import Provenance

from .resources import template_dir as _template_dir

# Signal types whose C representation is unsigned -> integer constants need a
# 'U' suffix to satisfy MISRA C:2012 Rule 7.2.
_UNSIGNED_TYPES = {"bool", "uint8", "uint16", "uint32", "uint64"}
# 64-bit types take an 'LL'/'ULL' suffix so the literal's type matches the field.
_LONGLONG_TYPES = {"uint64", "int64"}


def _env() -> Environment:
    # keep_trailing_newline + lstrip/trim give stable, diff-friendly output.
    return Environment(
        loader=FileSystemLoader(_template_dir()),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _sanitize_upper(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", str(s)).upper()


def _prefix(iface: Interface) -> str:
    return _sanitize_upper(iface.id)


def _struct_name(iface: Interface) -> str:
    return f"{_sanitize_upper(iface.id).lower()}_t"


def _bus_name(iface: Interface) -> str:
    return f"Bus_{re.sub(r'[^A-Za-z0-9]', '_', iface.id)}"


def _packet_struct_name(iface: Interface, pkt: Packet) -> str:
    return f"{_sanitize_upper(iface.id).lower()}_{_sanitize_upper(pkt.name).lower()}_t"


def _packet_bus_name(iface: Interface, pkt: Packet) -> str:
    return (f"Bus_{re.sub(r'[^A-Za-z0-9]', '_', iface.id)}"
            f"_{re.sub(r'[^A-Za-z0-9]', '_', pkt.name)}")


def _m_escape(s) -> str:
    """Escape a value for a single-quoted MATLAB string literal."""
    return str(s or "").replace("'", "''")


def _float_const(x: float) -> str:
    """MISRA-safe floating constant: always has a decimal point and 'F' suffix
    (Rule 7.2/7.4 — a float literal used in float context should be typed)."""
    if x == int(x):
        return f"{int(x)}.0F"
    return f"{repr(x)}F"


def _num_const(sig: Signal, x: float) -> str:
    """Render a range bound as a constant whose suffix matches the field type.

    Integer-typed signals get integer literals (with U/LL suffixes as needed);
    float-typed signals get float literals. A blank/unknown signal type is
    treated as integer-ish only when the value is whole, else a float literal.
    """
    is_int_type = sig.signal_type not in {"float32", "float64"}
    if is_int_type and x == int(x):
        lit = str(int(x))
        suffix = ""
        if sig.signal_type in _UNSIGNED_TYPES:
            suffix += "U"
        if sig.signal_type in _LONGLONG_TYPES:
            suffix += "LL"
        return f"{lit}{suffix}"
    return _float_const(x)


def render_header(model: IcdModel, prov: Provenance) -> str:
    guard = f"ICD_{_sanitize_upper(model.metadata.document_id)}_H"
    tmpl = _env().get_template("header.h.j2")
    return tmpl.render(
        model=model, prov=prov, guard=guard,
        prefix=_prefix, struct_name=_struct_name,
        packet_struct_name=_packet_struct_name,
        macro=_sanitize_upper,
        num_const=_num_const, float_const=_float_const,
        literal_open="{", literal_close="}",
    )


def render_simulink(model: IcdModel, prov: Provenance) -> str:
    tmpl = _env().get_template("simulink_bus.m.j2")
    return tmpl.render(model=model, prov=prov, bus_name=_bus_name,
                       packet_bus_name=_packet_bus_name, m_escape=_m_escape)