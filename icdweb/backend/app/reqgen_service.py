"""Service layer for the reqgen config editor (icdweb backend).

reqgen's config FILE is the single record of truth and `config_io.save_config`
is its ONLY writer. This module is a thin orchestrator over reqgen: it never
holds its own copy of the config and never writes the file by any other path.

Responsibilities:
  * read the config of record (+ its hash) for the editor to display,
  * validate + save a posted draft (delegates to save_config, which enforces
    the bright-line placeholder rule and rejects bad configs),
  * generate a live requirements PREVIEW from a posted (unsaved) draft against a
    chosen ICD — saved project or just-in-time uploaded XML — without writing,
  * reconcile a draft's output against the SAVED config's output so the editor
    can show "what your edits change" before you commit,
  * build the requirements-to-signals TRACEABILITY MATRIX from a posted draft
    against a chosen ICD (rows + coverage summary for the UI), and stream it as
    a downloadable CSV.

The ICD is read through the authoritative icdgen loader, exactly like the rest
of icdweb, so a preview validates against the same schema as everything else.
"""
from __future__ import annotations

import os
import tempfile

from icdgen.loader import ValidationError, load

from reqgen.config_io import (
    ConfigError, config_from_dict, config_hash, ensure_config, save_config,
)
from reqgen.config_schema import config_descriptor
from reqgen.generate import generate_requirements
from reqgen.paths import default_config_path
from reqgen.reconcile import reconcile as reconcile_reqs
from reqgen.trace import build_trace_rows, coverage_summary, render_trace_csv

from dataclasses import asdict

from . import service as icd_service
from .schemas import IcdDTO, dto_to_model


# --------------------------------------------------------------------------
# Config path resolution. Honors $REQGEN_CONFIG (so a deployment can point the
# editor at the committed config of record); otherwise the conventional
# reqgen/config/reqgen.json baked into reqgen.paths.
# --------------------------------------------------------------------------
def _config_path() -> str:
    return default_config_path()


# --------------------------------------------------------------------------
# Descriptor + config read
# --------------------------------------------------------------------------
def meta() -> dict:
    """The aspect-registry descriptor the editor builds itself from."""
    return config_descriptor()


def read_config() -> dict:
    """Current config of record as a plain dict + its canonical SHA-256.
    Creates the populated default on first ever read (ensure_config)."""
    path = _config_path()
    cfg = ensure_config(path)
    return {
        "config": asdict(cfg),
        "configHash": config_hash(cfg),
        "path": path,
    }


# --------------------------------------------------------------------------
# Save (the only mutation; delegates to the single writer)
# --------------------------------------------------------------------------
def save(config_dict: dict) -> dict:
    """Validate + persist a posted config draft. Returns the new hash.

    Validation (including the bright-line placeholder check) happens inside
    config_from_dict/save_config; a violation raises ConfigError, which the
    route turns into a 400 so the editor shows the specific message.
    """
    cfg = config_from_dict(config_dict)   # validates; raises ConfigError if bad
    path = _config_path()
    save_config(path, cfg)
    return {"ok": True, "configHash": config_hash(cfg), "path": path}


# --------------------------------------------------------------------------
# ICD source resolution for preview/reconcile/trace
# --------------------------------------------------------------------------
def _model_from_project(project_id: str):
    """Load the saved project's definition into an icdgen model."""
    dto = icd_service.read_definition(project_id)   # raises FileNotFoundError
    return dto_to_model(dto)


def _model_from_xml_text(xml_text: str):
    """Parse uploaded XML/JSON text into an icdgen model via the real loader."""
    suffix = ".json" if xml_text.lstrip().startswith("{") else ".xml"
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False,
                                     encoding="utf-8") as fh:
        fh.write(xml_text)
        tmp = fh.name
    try:
        model, _hash, _warns = load(tmp)
        return model
    finally:
        os.unlink(tmp)


def _resolve_model(payload: dict):
    """Pick the ICD source: saved project id or inline uploaded text.
    Returns (model, source_label). Raises ValueError if neither is provided."""
    pid = payload.get("icdProjectId")
    if pid:
        return _model_from_project(pid), f"project:{pid}"
    xml = payload.get("icdXml")
    if xml:
        return _model_from_xml_text(xml), "upload"
    raise ValueError("no ICD source: provide icdProjectId or icdXml")


# --------------------------------------------------------------------------
# Preview — generate from the POSTED (unsaved) draft, never write
# --------------------------------------------------------------------------
def _reqs_to_rows(reqs) -> list[dict]:
    return [
        {
            "reqId": r.req_id, "level": r.level, "aspect": r.aspect,
            "text": r.text, "iface": r.iface, "packet": r.packet,
            "signal": r.signal,
        }
        for r in reqs
    ]


def preview(payload: dict) -> dict:
    """Generate requirements from the posted draft config against the chosen
    ICD. Validates the draft first (bright line included) so the preview can
    never crash on a bad placeholder; a ConfigError comes back as ok=False."""
    try:
        cfg = config_from_dict(payload.get("config") or {})
    except ConfigError as exc:
        return {"ok": False, "error": str(exc)}

    model, source = _resolve_model(payload)
    reqs = generate_requirements(model, cfg)
    rows = _reqs_to_rows(reqs)

    by_level: dict[str, int] = {}
    by_aspect: dict[str, int] = {}
    for r in reqs:
        by_level[r.level] = by_level.get(r.level, 0) + 1
        by_aspect[r.aspect] = by_aspect.get(r.aspect, 0) + 1

    return {
        "ok": True,
        "source": source,
        "documentId": model.metadata.document_id,
        "count": len(rows),
        "countsByLevel": by_level,
        "countsByAspect": by_aspect,
        "requirements": rows,
        "configHashDraft": config_hash(cfg),
    }


# --------------------------------------------------------------------------
# Trace — requirements-to-signals traceability matrix from the posted draft
# --------------------------------------------------------------------------
def _trace_rows_to_dicts(rows) -> list[dict]:
    return [
        {
            "iface": r.iface, "packet": r.packet, "signal": r.signal,
            "level": r.level, "reqIds": r.req_ids,
            "reqCount": len(r.req_ids),
            "covered": r.covered,
        }
        for r in rows
    ]


def trace(payload: dict) -> dict:
    """Build the traceability matrix (rows + coverage) from the posted draft
    config against the chosen ICD. Validates the draft first; a ConfigError
    comes back as ok=False. Read-only: never writes the config file."""
    try:
        cfg = config_from_dict(payload.get("config") or {})
    except ConfigError as exc:
        return {"ok": False, "error": str(exc)}

    model, source = _resolve_model(payload)
    reqs = generate_requirements(model, cfg)
    rows = build_trace_rows(model, reqs)
    summary = coverage_summary(rows)

    return {
        "ok": True,
        "source": source,
        "documentId": model.metadata.document_id,
        "rows": _trace_rows_to_dicts(rows),
        "summary": summary,
        "configHashDraft": config_hash(cfg),
    }


def trace_csv(payload: dict) -> tuple[str, str]:
    """Render the traceability matrix CSV for download.

    Returns (csv_text, document_id). Raises ConfigError on a bad draft (the
    route turns it into a 400) and ValueError when no ICD source is given.
    Uses the ICD hash from the loaded source and the draft config hash so the
    downloaded CSV's provenance matches what the editor previewed.
    """
    cfg = config_from_dict(payload.get("config") or {})   # raises ConfigError

    # Resolve the model AND its ICD hash. For an uploaded file we hash the
    # uploaded text; for a saved project we hash the canonical serialized XML
    # (mirrors icd_service.generate()).
    import hashlib
    from icdgen.serializer import to_xml

    pid = payload.get("icdProjectId")
    xml = payload.get("icdXml")
    if pid:
        model = _model_from_project(pid)
        icd_hash = hashlib.sha256(to_xml(model).encode("utf-8")).hexdigest()
    elif xml:
        model = _model_from_xml_text(xml)
        icd_hash = hashlib.sha256(xml.encode("utf-8")).hexdigest()
    else:
        raise ValueError("no ICD source: provide icdProjectId or icdXml")

    from reqgen.provenance import ReqProvenance
    prov = ReqProvenance.create(icd_hash, config_hash(cfg))
    reqs = generate_requirements(model, cfg)
    return render_trace_csv(model, reqs, prov), model.metadata.document_id


# --------------------------------------------------------------------------
# Reconcile — draft output vs SAVED-config output (impact of your edits)
# --------------------------------------------------------------------------
def reconcile(payload: dict) -> dict:
    """Compare what the posted draft would generate against what the SAVED
    config of record generates, for the same ICD. Shows added/removed/changed
    requirement IDs so the editor can preview the impact before saving."""
    try:
        draft = config_from_dict(payload.get("config") or {})
    except ConfigError as exc:
        return {"ok": False, "error": str(exc)}

    model, source = _resolve_model(payload)

    # Saved config of record (the baseline). ensure_config never writes when the
    # file already exists, so this is read-only in practice.
    saved = ensure_config(_config_path())

    from reqgen.export import to_csv
    from reqgen.provenance import ReqProvenance
    _prov = ReqProvenance.create("0" * 64, config_hash(saved))

    draft_reqs = generate_requirements(model, draft)
    saved_csv = to_csv(generate_requirements(model, saved), _prov)
    rec = reconcile_reqs(draft_reqs, saved_csv)

    return {
        "ok": True,
        "source": source,
        "documentId": model.metadata.document_id,
        "savedConfigHash": config_hash(saved),
        "draftConfigHash": config_hash(draft),
        "added": rec.added,
        "removed": rec.removed,
        "changed": [
            {"reqId": rid, "was": old, "now": new}
            for rid, old, new in rec.changed
        ],
        "unchangedCount": len(rec.unchanged),
    }