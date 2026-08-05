"""Serialize an IcdModel back to canonical schema-valid XML.

Inverse of loader.py. The form-based editor (or any caller) builds an
IcdModel; this renders it as XML that re-validates against icd-1.0.xsd.
The CLI and web layer share this serializer.

Determinism: element order and formatting are fixed, so the same model always
serializes to the same bytes.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from .model import IcdModel, Interface, Signal

_NS = "urn:icdgen:icd:1.0"

# Adds the quote characters to the default & < > escapes. One escaper for
# both element text and attribute values; escaping quotes in element text is
# harmless, and attribute values (e.g. an unconstrained packet name) stay
# well-formed.
_ESCAPE_MAP = {'"': "&quot;", "'": "&apos;"}


def _esc(text: str) -> str:
    return escape("" if text is None else str(text), _ESCAPE_MAP)


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
    if model.prior_revisions:
        out.append("  <priorRevisions>")
        for pr in model.prior_revisions:
            out.append(
                f'    <priorRevision revision="{_esc(pr.revision)}" '
                f'source="{_esc(pr.source)}"/>')
        out.append("  </priorRevisions>")
    out.append("  <interfaces>")
    for iface in model.interfaces:
        out.extend(_interface_xml(iface, "    "))
    out.append("  </interfaces>")
    out.append("</icd>")
    return "\n".join(out) + "\n"