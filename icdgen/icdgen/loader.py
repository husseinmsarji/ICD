"""Input loading, schema validation, and canonical model construction.

Validation philosophy (certification-driven):
  * No silent failures. A missing required field raises ValidationError with a
    line reference back into the source file.
  * XML is validated against the versioned XSD; JSON against an equivalent
    jsonschema. Both converge on the same IcdModel.
  * The raw input bytes are hashed (SHA-256) before parsing so the stamp in
    every output traces to the exact authored file.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

from lxml import etree

from .signal_codec import (parse_signal_xml, parse_interface_xml,
                          parse_packet_xml, interface_from_json_dict)
from .model import (
    IcdModel,
    Interface,
    Metadata,
    RevisionEntry,
    Signal,
)

XSD_NAMESPACE = "urn:icdgen:icd:1.0"
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


@dataclass
class ValidationError(Exception):
    """Raised on any input validation failure. Carries a line reference."""
    message: str
    line: int | None = None
    source: str | None = None

    def __str__(self) -> str:
        loc = ""
        if self.source:
            loc = f"{self.source}"
            if self.line:
                loc += f":{self.line}"
            loc += ": "
        elif self.line:
            loc = f"line {self.line}: "
        return f"{loc}{self.message}"


def hash_file(path: str) -> str:
    """SHA-256 of the raw input bytes. The traceability anchor."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# XML path
# --------------------------------------------------------------------------
def _validate_xml(path: str) -> etree._Element:
    from .resources import compiled_xsd
    # The XSD is assembled from the template + field registry at load time, so
    # the schema and the registry cannot drift apart.
    schema_doc = etree.fromstring(compiled_xsd().encode("utf-8"))
    schema = etree.XMLSchema(schema_doc)
    parser = etree.XMLParser(remove_blank_text=False)
    try:
        tree = etree.parse(path, parser)
    except etree.XMLSyntaxError as exc:
        line = exc.lineno if exc.lineno else None
        raise ValidationError(f"XML syntax error: {exc.msg}", line=line, source=path)

    if not schema.validate(tree):
        # Report the first error with its line number for a precise DER trail.
        first = schema.error_log[0]
        raise ValidationError(
            f"Schema validation failed: {first.message}",
            line=first.line,
            source=path,
        )
    return tree.getroot()


def _q(tag: str) -> str:
    return f"{{{XSD_NAMESPACE}}}{tag}"


def _text(elem, tag, default=None):
    child = elem.find(_q(tag))
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _model_from_xml(root: etree._Element) -> IcdModel:
    schema_version = root.get("schemaVersion")

    meta_el = root.find(_q("metadata"))
    rev_hist_el = meta_el.find(_q("revisionHistory"))
    history = tuple(
        RevisionEntry(
            revision=_text(e, "revision"),
            date=_text(e, "date"),
            author=_text(e, "author"),
            description=_text(e, "description"),
        )
        for e in rev_hist_el.findall(_q("entry"))
    )
    metadata = Metadata(
        document_id=_text(meta_el, "documentId"),
        document_title=_text(meta_el, "documentTitle"),
        program=_text(meta_el, "program"),
        revision=_text(meta_el, "revision"),
        revision_date=_text(meta_el, "revisionDate"),
        author=_text(meta_el, "author"),
        revision_history=history,
    )

    interfaces = []
    for iface_el in root.find(_q("interfaces")).findall(_q("interface")):
        packets = []
        for pkt_el in iface_el.find(_q("packets")).findall(_q("packet")):
            signals = []
            for sig_el in pkt_el.find(_q("signals")).findall(_q("signal")):
                # Registry-driven parse: adding a signal field needs no change.
                signals.append(parse_signal_xml(sig_el, XSD_NAMESPACE, _text))
            packets.append(parse_packet_xml(pkt_el, XSD_NAMESPACE, _text, signals))
        # Registry-driven parse: adding an interface field needs no change here.
        interfaces.append(
            parse_interface_xml(iface_el, XSD_NAMESPACE, _text, packets)
        )

    return IcdModel(
        schema_version=schema_version,
        metadata=metadata,
        interfaces=tuple(interfaces),
    )


# --------------------------------------------------------------------------
# JSON path
# --------------------------------------------------------------------------
def _json_schema() -> dict:
    """Equivalent constraints to the XSD, expressed for jsonschema.

    Kept in lockstep with icd-1.0.xsd. Required arrays mirror the XSD's
    mandatory elements so a missing field is a hard error, not a default.
    """
    from .fields import BUS_TYPES, DAL_LEVELS
    from .schema_gen import json_signal_schema
    bus_types = list(BUS_TYPES)
    dal = list(DAL_LEVELS)
    # Signal object is generated from the field registry — single source of truth.
    signal = json_signal_schema()
    # Packet object: name + optional description + a signals array (which
    # references the generated signal schema). Packets group signals.
    packet = {
        "type": "object",
        "required": ["name", "signals"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "description": {"type": ["string", "null"]},
            "signals": {"type": "array", "minItems": 1, "items": signal},
        },
    }
    # Interface object generated from the registry; the packets array is
    # injected here so it references the packet schema.
    from .schema_gen import json_interface_schema
    interface = json_interface_schema()
    interface["properties"]["packets"] = {
        "type": "array", "minItems": 1, "items": packet,
    }
    interface["required"].append("packets")
    rev_entry = {
        "type": "object",
        "required": ["revision", "date", "author", "description"],
        "additionalProperties": False,
        "properties": {
            "revision": {"type": "string", "minLength": 1},
            "date": {"type": "string"},
            "author": {"type": "string", "minLength": 1},
            "description": {"type": "string", "minLength": 1},
        },
    }
    metadata = {
        "type": "object",
        "required": ["documentId", "documentTitle", "program", "revision",
                     "revisionDate", "author", "revisionHistory"],
        "additionalProperties": False,
        "properties": {
            "documentId": {"type": "string", "minLength": 1},
            "documentTitle": {"type": "string", "minLength": 1},
            "program": {"type": "string", "minLength": 1},
            "revision": {"type": "string", "minLength": 1},
            "revisionDate": {"type": "string"},
            "author": {"type": "string", "minLength": 1},
            "revisionHistory": {"type": "array", "minItems": 1, "items": rev_entry},
        },
    }
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["schemaVersion", "metadata", "interfaces"],
        "additionalProperties": False,
        "properties": {
            "schemaVersion": {"type": "string", "pattern": "^1\\.[0-9]+$"},
            "metadata": metadata,
            "interfaces": {"type": "array", "minItems": 1, "items": interface},
            "extensions": {"type": "object"},
        },
    }


def _validate_json(path: str) -> dict:
    import jsonschema

    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON syntax error: {exc.msg}",
                              line=exc.lineno, source=path)

    validator = jsonschema.Draft7Validator(_json_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        err = errors[0]
        loc = "/".join(str(p) for p in err.path) or "<root>"
        # Approximate a line by locating the failing key in the source text.
        line = _approx_json_line(raw, err.path)
        raise ValidationError(
            f"Schema validation failed at '{loc}': {err.message}",
            line=line, source=path,
        )
    return data


def _approx_json_line(raw: str, path) -> int | None:
    """Best-effort line lookup for a JSON error path.

    jsonschema does not report source offsets, so we locate the deepest named
    key from the error path in the raw text. Approximate but gives the DER a
    place to look.
    """
    keys = [p for p in path if isinstance(p, str)]
    if not keys:
        return None
    needle = f'"{keys[-1]}"'
    for i, ln in enumerate(raw.splitlines(), start=1):
        if needle in ln:
            return i
    return None


def _model_from_json(data: dict) -> IcdModel:
    m = data["metadata"]
    history = tuple(
        RevisionEntry(revision=e["revision"], date=e["date"],
                      author=e["author"], description=e["description"])
        for e in m["revisionHistory"]
    )
    metadata = Metadata(
        document_id=m["documentId"],
        document_title=m["documentTitle"],
        program=m["program"],
        revision=m["revision"],
        revision_date=m["revisionDate"],
        author=m["author"],
        revision_history=history,
    )
    # Registry-driven: interface + signal construction via the codec, so adding
    # a field needs no change here.
    interfaces = [interface_from_json_dict(i) for i in data["interfaces"]]
    return IcdModel(
        schema_version=data["schemaVersion"],
        metadata=metadata,
        interfaces=tuple(interfaces),
    )


# --------------------------------------------------------------------------
# Cross-field semantic checks (beyond what schema can express)
# --------------------------------------------------------------------------
def _semantic_checks(model: IcdModel, source: str) -> None:
    if model.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValidationError(
            f"Unsupported schemaVersion '{model.schema_version}'. "
            f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
            source=source,
        )
    seen_ids = set()
    for iface in model.interfaces:
        if iface.id in seen_ids:
            raise ValidationError(
                f"Duplicate interface id '{iface.id}'", source=source)
        seen_ids.add(iface.id)
        seen_pkt = set()
        for pkt in iface.packets:
            if pkt.name in seen_pkt:
                raise ValidationError(
                    f"Duplicate packet '{pkt.name}' in interface '{iface.id}'",
                    source=source)
            seen_pkt.add(pkt.name)
            seen_sig = set()
            for sig in pkt.signals:
                if sig.name in seen_sig:
                    raise ValidationError(
                        f"Duplicate signal '{sig.name}' in packet "
                        f"'{pkt.name}' of interface '{iface.id}'", source=source)
                seen_sig.add(sig.name)
                if sig.range_min > sig.range_max:
                    raise ValidationError(
                        f"Signal '{sig.name}' in '{iface.id}/{pkt.name}': "
                        f"rangeMin ({sig.range_min}) > rangeMax ({sig.range_max})",
                        source=source)


def load(path: str) -> tuple[IcdModel, str]:
    """Validate and load an input file. Returns (model, sha256_hex).

    Format is inferred from extension: .json -> JSON, otherwise XML.
    Raises ValidationError on any problem.
    """
    file_hash = hash_file(path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        data = _validate_json(path)
        model = _model_from_json(data)
    else:
        root = _validate_xml(path)
        model = _model_from_xml(root)
    _semantic_checks(model, path)
    return model, file_hash
