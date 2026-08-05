"""Input loading, schema validation, and canonical model construction.

Validation has two channels:
  * FATAL problems raise ValidationError (with a line reference). The file does
    not load.
  * NON-FATAL problems are returned as a list of ValidationWarning so a
    partially-complete ICD can still be loaded and finished in the tool.

The ICD definition file is YAML. It is parsed with PyYAML ``safe_load`` and the
resulting structure is validated against a JSON Schema that is generated from
the field registries (``schema_gen``), so the schema can never drift from the
registry. The raw input bytes are hashed (SHA-256) before parsing so the
provenance stamp traces to the exact authored file.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import yaml


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


from .model import (  # noqa: E402
    IcdModel,
    Interface,
    Metadata,
    PriorRevision,
    RevisionEntry,
    Signal,
)
from .signal_codec import interface_from_json_dict  # noqa: E402

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

_C_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def hash_file(path: str) -> str:
    """SHA-256 of the raw input bytes. The traceability anchor."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Schema (generated from the field registries — single source of truth)
# --------------------------------------------------------------------------
def _data_schema() -> dict:
    """The JSON Schema the parsed YAML is validated against. The signal and
    interface objects are generated from the registries (single source)."""
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


def schema_hash() -> str:
    """SHA-256 of the generated JSON Schema (canonical JSON). Provenance anchor
    for the schema the input was validated against."""
    canon = json.dumps(_data_schema(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# YAML load + validate
# --------------------------------------------------------------------------
def _validate_yaml(path: str) -> dict:
    import jsonschema

    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        line = None
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            line = mark.line + 1
        raise ValidationError(f"YAML syntax error: {exc}", line=line, source=path)

    if not isinstance(data, dict):
        raise ValidationError("Top-level YAML must be a mapping (an ICD object).",
                              source=path)

    validator = jsonschema.Draft7Validator(_data_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        err = errors[0]
        loc = "/".join(str(p) for p in err.path) or "<root>"
        line = _approx_line(raw, err.path)
        raise ValidationError(
            f"Schema validation failed at '{loc}': {err.message}",
            line=line, source=path,
        )
    return data


def _approx_line(raw: str, path) -> int | None:
    """Best-effort source line for a schema error: locate the deepest mapping
    key from the error path in the raw YAML text (keys appear as ``key:``)."""
    keys = [p for p in path if isinstance(p, str)]
    if not keys:
        return None
    needle = f"{keys[-1]}:"
    for i, ln in enumerate(raw.splitlines(), start=1):
        if needle in ln.strip():
            return i
    return None


def _model_from_data(data: dict) -> IcdModel:
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
    """Validate and load a YAML ICD definition. Returns (model, sha256_hex,
    warnings).

    Raises ValidationError on a FATAL problem; non-fatal issues come back as
    the warnings list so partially-complete ICDs can still be loaded.
    """
    file_hash = hash_file(path)
    data = _validate_yaml(path)
    model = _model_from_data(data)
    warnings = _semantic_checks(model, path)
    return model, file_hash, warnings
