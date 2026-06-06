"""Serialize an IcdModel back to canonical schema-valid XML.

This is the inverse of loader.py. The form-based editor (and any programmatic
caller) builds an IcdModel; this turns it into an XML document that re-validates
against icd-1.0.xsd. Keeping serialization here means there is exactly one
source of truth for the wire format, shared by the CLI and the web layer.

Determinism: element order and formatting are fixed, so the same model always
serializes to the same bytes.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from .model import IcdModel, Interface, Signal

_NS = "urn:icdgen:icd:1.0"


def _esc(text: str) -> str:
    return escape("" if text is None else str(text))


def _num(x: float) -> str:
    # Match the formatting used elsewhere: integers without trailing .0.
    if x == int(x):
        return str(int(x))
    return repr(x)


def _signal_xml(sig: Signal, indent: str) -> list[str]:
    # Registry-driven: ordering, element/attribute placement, and emit_if rules
    # all come from SIGNAL_FIELDS, so adding a field needs no change here.
    from .signal_codec import signal_xml_lines
    return signal_xml_lines(sig, indent, _esc, _num)


def _interface_xml(iface: Interface, indent: str) -> list[str]:
    # Registry-driven: attribute/element order + emit_if come from
    # INTERFACE_FIELDS. The <packets> collection (each packet wrapping a
    # <signals> block) is appended structurally.
    from .signal_codec import interface_open_xml, packet_xml_lines
    open_tag, body = interface_open_xml(iface, indent, _esc)
    lines = [open_tag, *body]
    inner = indent + "  "
    lines.append(f"{inner}<packets>")
    for pkt in iface.packets:
        lines.extend(packet_xml_lines(pkt, inner + "  ", _esc, _signal_xml))
    lines.append(f"{inner}</packets>")
    lines.append(f"{indent}</interface>")
    return lines


def to_xml(model: IcdModel) -> str:
    """Render an IcdModel to canonical XML text (UTF-8, schema-valid)."""
    m = model.metadata
    out: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append(f'<icd xmlns="{_NS}" schemaVersion="{_esc(model.schema_version)}">')
    out.append("  <metadata>")
    out.append(f"    <documentId>{_esc(m.document_id)}</documentId>")
    out.append(f"    <documentTitle>{_esc(m.document_title)}</documentTitle>")
    out.append(f"    <program>{_esc(m.program)}</program>")
    out.append(f"    <revision>{_esc(m.revision)}</revision>")
    out.append(f"    <revisionDate>{_esc(m.revision_date)}</revisionDate>")
    out.append(f"    <author>{_esc(m.author)}</author>")
    out.append("    <revisionHistory>")
    for e in m.revision_history:
        out.append("      <entry>")
        out.append(f"        <revision>{_esc(e.revision)}</revision>")
        out.append(f"        <date>{_esc(e.date)}</date>")
        out.append(f"        <author>{_esc(e.author)}</author>")
        out.append(f"        <description>{_esc(e.description)}</description>")
        out.append("      </entry>")
    out.append("    </revisionHistory>")
    out.append("  </metadata>")
    out.append("  <interfaces>")
    for iface in model.interfaces:
        out.extend(_interface_xml(iface, "    "))
    out.append("  </interfaces>")
    out.append("</icd>")
    return "\n".join(out) + "\n"
