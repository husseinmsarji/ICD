"""Input loading, schema validation, and canonical model construction.

Validation has two channels:
  * FATAL problems raise ValidationError (with a line reference). The file does
    not load.
  * NON-FATAL problems are returned as a list of ValidationWarning so a
    partially-complete ICD can still be loaded and finished in the tool.

XML is validated against the (registry-assembled) XSD; JSON against an
equivalent jsonschema. Both converge on the same IcdModel. The raw input bytes
are hashed (SHA-256) before parsing so the provenance stamp traces to the exact
authored file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass

from lxml import etree

from .signal_codec import (parse_signal_xml, parse_interface_xml,
                           parse_packet_xml, interface_from_json_dict)
from .model import (
    IcdModel,
    Interface,
    Metadata,
    PriorRevision,
    RevisionEntry,
    Signal,
)

XSD_NAMESPACE = "urn:icdgen:icd:1.0"
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

_C_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class ValidationError(Exception):
    """Raised on a FATAL input validation failure. Carries a line reference."""
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


@dataclass
class ValidationWarning:
    """A NON-FATAL issue. The file still loads; the warning is surfaced to the
    user (CLI/UI) so a partially-complete ICD can be finished in the tool."""
    message: str
    line: int | None = None


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
    schema_doc = etree.fromstring(compiled_xsd().encode("utf-8"))
    schema = etree.XMLSchema(schema_doc)
    parser = etree.XMLParser(remove_blank_text=False)
    try:
        tree = etree.parse(path, parser)
    except etree.XMLSyntaxError as exc:
        line = exc.lineno if exc.lineno else None
        raise ValidationError(f"XML syntax error: {exc.msg}", line=line, source=path)

    if not schema.validate(tree):
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
                signals.append(parse_signal_xml(sig_el, XSD_NAMESPACE, _text))
            packets.append(parse_packet_xml(pkt_el, XSD_NAMESPACE, _text, signals))
        interfaces.append(
            parse_interface_xml(iface_el, XSD_NAMESPACE, _text, packets)
        )

    prior = []
    pr_el = root.find(_q("priorRevisions"))
    if pr_el is not None:
        for e in pr_el.findall(_q("priorRevision")):
            prior.append(PriorRevision(revision=e.get("revision"),
                                       source=e.get("source")))

    return IcdModel(
        schema_version=schema_version,
        metadata=metadata,
        interfaces=tuple(interfaces),
        prior_revisions=tuple(prior),
    )


# --------------------------------------------------------------------------
# JSON path
# --------------------------------------------------------------------------
def _json_schema() -> dict:
    """Equivalent constraints to the XSD, expressed for jsonschema. The signal
    and interface objects are generated from the registries (single source)."""
    from .schema_gen import json_signal_schema, json_interface_schema

    signal = json_signal_schema()
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
            "priorRevisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["revision", "source"],
                    "additionalProperties": False,
                    "properties": {
                        "revision": {"type": "string", "minLength": 1},
                        "source": {"type": "string", "minLength": 1},
                    },
                },
            },
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
        line = _approx_json_line(raw, err.path)
        raise ValidationError(
            f"Schema validation failed at '{loc}': {err.message}",
            line=line, source=path,
        )
    return data


def _approx_json_line(raw: str, path) -> int | None:
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
    interfaces = [interface_from_json_dict(i) for i in data["interfaces"]]
    prior = tuple(
        PriorRevision(revision=pr["revision"], source=pr["source"])
        for pr in data.get("priorRevisions", [])
    )
    return IcdModel(
        schema_version=data["schemaVersion"],
        metadata=metadata,
        interfaces=tuple(interfaces),
        prior_revisions=prior,
    )


# --------------------------------------------------------------------------
# Cross-field semantic checks (beyond what schema can express)
# --------------------------------------------------------------------------
def _semantic_checks(model: IcdModel, source: str) -> list[ValidationWarning]:
    """FATAL problems raise ValidationError. NON-FATAL problems are returned as
    a list of ValidationWarning so a partially-complete ICD can still load."""
    warnings: list[ValidationWarning] = []

    # Change-control gate: tickets are expected for any revision past the
    # initial "A" (case-insensitive compare; blank revision is treated as "A").
    _rev = (model.metadata.revision or "A").strip().upper()
    _rev_requires_ticket = _rev not in ("", "A")

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
                where = f"{iface.id}/{pkt.name}.{sig.name}"
                if sig.name in seen_sig:
                    raise ValidationError(
                        f"Duplicate signal '{sig.name}' in packet "
                        f"'{pkt.name}' of interface '{iface.id}'", source=source)
                seen_sig.add(sig.name)
                # Range check only when BOTH bounds are present (both optional).
                if (sig.range_min is not None and sig.range_max is not None
                        and sig.range_min > sig.range_max):
                    raise ValidationError(
                        f"Signal '{sig.name}' in '{iface.id}/{pkt.name}': "
                        f"rangeMin ({sig.range_min}) > rangeMax ({sig.range_max})",
                        source=source)
                # ---- WARNINGS (non-fatal) ----
                if not sig.signal_type:
                    warnings.append(ValidationWarning(
                        f"Signal '{where}' has no signal type; the C header "
                        f"will use a placeholder type (uint8_t) until it is set."))
                if not _C_IDENT_RE.match(sig.name):
                    warnings.append(ValidationWarning(
                        f"Signal name '{where}' is not a valid C identifier; "
                        f"it will not compile in the generated C header as-is."))
                # Change-control: every signal in a post-Rev-A ICD should cite
                # the PR/ticket that last touched it. Non-fatal so drafts load.
                if _rev_requires_ticket and not sig.pr_ticket:
                    warnings.append(ValidationWarning(
                        f"Signal '{where}' has no PR ticket; change control "
                        f"expects a ticket for revisions after 'A'."))
    return warnings


def load(path: str) -> tuple[IcdModel, str, list[ValidationWarning]]:
    """Validate and load an input file. Returns (model, sha256_hex, warnings).

    Format is inferred from extension: .json -> JSON, otherwise XML.
    Raises ValidationError on a FATAL problem; non-fatal issues come back as
    the warnings list so partially-complete ICDs can still be loaded.
    """
    file_hash = hash_file(path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        data = _validate_json(path)
        model = _model_from_json(data)
    else:
        root = _validate_xml(path)
        model = _model_from_xml(root)
    warnings = _semantic_checks(model, path)
    return model, file_hash, warnings
