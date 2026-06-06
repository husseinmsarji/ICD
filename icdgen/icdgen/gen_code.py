"""Source-code artifact generators: C/C++ header and Simulink bus script.

Both are pure template renders over the canonical model, making them trivially
deterministic. The C `{` / `}` collisions with Jinja are handled by passing
literal_open / literal_close into the context rather than escaping braces.
"""
from __future__ import annotations

import re

from jinja2 import Environment, FileSystemLoader

from .model import IcdModel, Interface
from .provenance import Provenance

from .resources import template_dir as _template_dir


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
    return re.sub(r"[^A-Za-z0-9]", "_", s).upper()


def _prefix(iface: Interface) -> str:
    return _sanitize_upper(iface.id)


def _struct_name(iface: Interface) -> str:
    return f"{_sanitize_upper(iface.id).lower()}_t"


def _bus_name(iface: Interface) -> str:
    return f"Bus_{re.sub(r'[^A-Za-z0-9]', '_', iface.id)}"


def render_header(model: IcdModel, prov: Provenance) -> str:
    guard = f"ICD_{_sanitize_upper(model.metadata.document_id)}_H"
    tmpl = _env().get_template("header.h.j2")
    return tmpl.render(
        model=model, prov=prov, guard=guard,
        prefix=_prefix, struct_name=_struct_name,
        literal_open="{", literal_close="}",
    )


def render_simulink(model: IcdModel, prov: Provenance) -> str:
    tmpl = _env().get_template("simulink_bus.m.j2")
    return tmpl.render(model=model, prov=prov, bus_name=_bus_name)
