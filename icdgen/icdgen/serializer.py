"""Serialize an IcdModel to canonical, schema-valid YAML.

This is the inverse of loader.py. The form-based editor (and any programmatic
caller) builds an IcdModel; this turns it into a YAML document that re-validates
against the generated JSON Schema. Keeping serialization here means there is
exactly one source of truth for the wire format, shared by the CLI and the web
layer.

Determinism: the emitter is hand-rolled (not a third-party YAML dumper) so the
output bytes are fully under our control — a hard requirement because identical
input must produce byte-identical artifacts (DO-330 evidence). Key order is
fixed (registry order for signals/interfaces), indentation is 2 spaces, and
*every string scalar is double-quoted and escaped*. Quoting every string is what
keeps the output unambiguous and stable, and it stops YAML from coercing a value
like ``2026-06-01`` into a native date on re-parse.
"""
from __future__ import annotations

from .model import IcdModel


def _num(x: float) -> str:
    # Match the numeric formatting used elsewhere: integer-valued floats render
    # without a trailing ".0" (e.g. 90.0 -> "90"), everything else via repr.
    if x == int(x):
        return str(int(x))
    return repr(x)


def _scalar(v) -> str:
    """Render a leaf value as a YAML scalar token."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return _num(v)
    if isinstance(v, int):
        return str(v)
    return _quote(str(v))


def _quote(s: str) -> str:
    """Double-quote a string with YAML-compatible escaping."""
    out = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20:
            out.append("\\x%02x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _emit_map(d: dict, pad: str, lines: list[str]) -> None:
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            _emit_map(v, pad + "  ", lines)
        elif isinstance(v, list):
            lines.append(f"{pad}{k}:")
            _emit_seq(v, pad + "  ", lines)
        else:
            lines.append(f"{pad}{k}: {_scalar(v)}")


def _emit_seq(items: list, pad: str, lines: list[str]) -> None:
    for item in items:
        if isinstance(item, dict):
            child = pad + "  "
            first = True
            for k, v in item.items():
                lead = pad + "- " if first else child
                first = False
                if isinstance(v, dict):
                    lines.append(f"{lead}{k}:")
                    _emit_map(v, child + "  ", lines)
                elif isinstance(v, list):
                    lines.append(f"{lead}{k}:")
                    _emit_seq(v, child + "  ", lines)
                else:
                    lines.append(f"{lead}{k}: {_scalar(v)}")
        else:
            lines.append(f"{pad}- {_scalar(item)}")


def model_to_yaml_dict(model: IcdModel) -> dict:
    """Build the ordered, canonical dict for an IcdModel (the shape the loader's
    JSON Schema validates and _model_from_data consumes)."""
    from .signal_codec import interface_to_yaml_dict

    m = model.metadata
    doc: dict = {"schemaVersion": model.schema_version}
    doc["metadata"] = {
        "documentId": m.document_id,
        "documentTitle": m.document_title,
        "program": m.program,
        "revision": m.revision,
        "revisionDate": m.revision_date,
        "author": m.author,
        "revisionHistory": [
            {"revision": e.revision, "date": e.date, "author": e.author,
             "description": e.description}
            for e in m.revision_history
        ],
    }
    if model.prior_revisions:
        doc["priorRevisions"] = [
            {"revision": pr.revision, "source": pr.source}
            for pr in model.prior_revisions
        ]
    doc["interfaces"] = [interface_to_yaml_dict(i) for i in model.interfaces]
    return doc


def to_yaml(model: IcdModel) -> str:
    """Render an IcdModel to canonical YAML text (UTF-8, schema-valid)."""
    lines: list[str] = []
    _emit_map(model_to_yaml_dict(model), "", lines)
    return "\n".join(lines) + "\n"
