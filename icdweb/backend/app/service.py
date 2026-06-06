"""Service layer between the HTTP API and the icdgen library.

Responsibilities:
  * Persist ICD definitions as projects (one directory each).
  * Validate a definition (returns structured errors, never raises to the API).
  * Generate artifacts into a per-project output directory.
  * Diff two definitions.

Storage is deliberately a flat directory tree under DATA_DIR. This is easy to
reason about for a single user and maps cleanly onto a future object store or
database: a "project" is just (id, definition.json, latest artifacts). Nothing
here assumes a single process, so it is safe to run behind multiple workers as
long as DATA_DIR is shared.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from icdgen import gen_code, gen_docx, gen_pdf, gen_trace
from icdgen.diff import diff as diff_models
from icdgen.diff import render_csv as diff_csv
from icdgen.diff import render_text as diff_text
from icdgen.loader import ValidationError, hash_file, load
from icdgen.provenance import Provenance
from icdgen.serializer import to_xml

from .schemas import IcdDTO, dto_to_model, model_to_dto

DATA_DIR = os.environ.get("ICDGEN_DATA_DIR", "/data")

# Artifact key -> (filename suffix, builder). Adding a format = one line here
# plus the generator in icdgen. The API and UI enumerate this dict, so new
# formats surface automatically.
ARTIFACT_BUILDERS = {
    "header": (".h", "_write_header"),
    "simulink": ("_bus.m", "_write_simulink"),
    "trace-csv": ("_traceability.csv", "_write_trace_csv"),
    "trace-xlsx": ("_traceability.xlsx", "_write_trace_xlsx"),
    "docx": (".docx", "_write_docx"),
    "pdf": (".pdf", "_write_pdf"),
}


@dataclass
class ValidationIssue:
    message: str
    line: int | None = None


def _projects_root() -> str:
    root = os.path.join(DATA_DIR, "projects")
    os.makedirs(root, exist_ok=True)
    return root


def _project_dir(project_id: str) -> str:
    # project_id is a server-generated uuid; never user-controlled path input.
    return os.path.join(_projects_root(), project_id)


def _def_path(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "definition.json")


def _meta_path(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "project.json")


def _out_dir(project_id: str) -> str:
    d = os.path.join(_project_dir(project_id), "out")
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# Project CRUD
# --------------------------------------------------------------------------
def list_projects() -> list[dict]:
    out = []
    root = _projects_root()
    for pid in os.listdir(root):
        meta = _meta_path(pid)
        if os.path.isfile(meta):
            with open(meta, encoding="utf-8") as fh:
                out.append(json.load(fh))
    out.sort(key=lambda p: p.get("updatedAt", ""), reverse=True)
    return out


def create_project(name: str, dto: IcdDTO | None = None) -> dict:
    pid = uuid.uuid4().hex
    os.makedirs(_project_dir(pid), exist_ok=True)
    if dto is None:
        dto = _empty_definition(name)
    save_definition(pid, dto, name=name, _new=True)
    return read_meta(pid)


def read_meta(project_id: str) -> dict:
    with open(_meta_path(project_id), encoding="utf-8") as fh:
        return json.load(fh)


def read_definition(project_id: str) -> IcdDTO:
    with open(_def_path(project_id), encoding="utf-8") as fh:
        return IcdDTO.model_validate_json(fh.read())


def save_definition(project_id: str, dto: IcdDTO, name: str | None = None,
                    _new: bool = False) -> dict:
    pdir = _project_dir(project_id)
    if not os.path.isdir(pdir):
        raise FileNotFoundError(project_id)
    # Atomic write of the definition.
    _atomic_write(_def_path(project_id), dto.model_dump_json(indent=2))

    now = datetime.now(timezone.utc).isoformat()
    meta = {} if _new else read_meta(project_id)
    meta.update({
        "id": project_id,
        "name": name or meta.get("name") or dto.metadata.documentTitle,
        "documentId": dto.metadata.documentId,
        "revision": dto.metadata.revision,
        "interfaceCount": len(dto.interfaces),
        "packetCount": sum(len(i.packets) for i in dto.interfaces),
        "signalCount": sum(len(p.signals) for i in dto.interfaces for p in i.packets),
        "updatedAt": now,
    })
    if _new:
        meta["createdAt"] = now
    _atomic_write(_meta_path(project_id), json.dumps(meta, indent=2))
    return meta


def delete_project(project_id: str) -> None:
    shutil.rmtree(_project_dir(project_id), ignore_errors=True)


# --------------------------------------------------------------------------
# Validate / generate / diff
# --------------------------------------------------------------------------
def validate_dto(dto: IcdDTO) -> list[ValidationIssue]:
    """Validate via the authoritative icdgen loader. Returns [] if valid."""
    model = dto_to_model(dto)
    xml = to_xml(model)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(xml)
        tmp = fh.name
    try:
        load(tmp)
        return []
    except ValidationError as exc:
        return [ValidationIssue(message=exc.message, line=exc.line)]
    finally:
        os.unlink(tmp)


def generate(project_id: str, formats: list[str]) -> dict:
    dto = read_definition(project_id)
    issues = validate_dto(dto)
    if issues:
        return {"ok": False, "issues": [i.__dict__ for i in issues], "artifacts": []}

    model = dto_to_model(dto)
    # Hash the canonical serialized XML so the stamp traces to exactly what was
    # generated from (the definition the user saved), independent of formatting.
    xml = to_xml(model)
    out = _out_dir(project_id)
    src_path = os.path.join(out, f"{model.metadata.document_id}.source.xml")
    _atomic_write(src_path, xml)
    file_hash = hash_file(src_path)
    prov = Provenance.create(file_hash, model.schema_version)

    base = model.metadata.document_id
    produced = []
    for key in formats:
        if key not in ARTIFACT_BUILDERS:
            continue
        suffix, builder = ARTIFACT_BUILDERS[key]
        path = os.path.join(out, f"{base}{suffix}")
        globals()[builder](model, prov, path)
        produced.append({"format": key, "filename": os.path.basename(path)})

    return {
        "ok": True,
        "issues": [],
        "inputHash": file_hash,
        "schemaVersion": model.schema_version,
        "artifacts": produced,
    }


def artifact_path(project_id: str, filename: str) -> str:
    # Guard against path traversal: filename must be a bare basename.
    if os.path.basename(filename) != filename:
        raise ValueError("invalid filename")
    path = os.path.join(_out_dir(project_id), filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(filename)
    return path


def diff(old: IcdDTO, new: IcdDTO) -> dict:
    old_m = dto_to_model(old)
    new_m = dto_to_model(new)
    res = diff_models(old_m, new_m)
    old_hash = hash_file_text(to_xml(old_m))
    new_hash = hash_file_text(to_xml(new_m))
    return {
        "hasChanges": res.has_changes,
        "text": diff_text(res, old_hash, new_hash),
        "csv": diff_csv(res),
        "addedInterfaces": res.added_interfaces,
        "removedInterfaces": res.removed_interfaces,
        "addedSignals": [
            {"interface": i, "packet": p, "signal": s}
            for i, p, s in res.added_signals
        ],
        "removedSignals": [
            {"interface": i, "packet": p, "signal": s}
            for i, p, s in res.removed_signals
        ],
        "modifiedSignals": [
            {
                "interface": sc.interface_id,
                "packet": sc.packet_name,
                "signal": sc.signal_name,
                "changes": [
                    {"field": c.field, "old": str(c.old), "new": str(c.new)}
                    for c in sc.changes
                ],
            }
            for sc in res.modified_signals
        ],
    }


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------
def hash_file_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: str, text: str) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _empty_definition(name: str) -> IcdDTO:
    today = datetime.now(timezone.utc).date().isoformat()
    return IcdDTO.model_validate({
        "schemaVersion": "1.0",
        "metadata": {
            "documentId": "ICD-NEW-001",
            "documentTitle": name,
            "program": "",
            "revision": "A",
            "revisionDate": today,
            "author": "",
            "revisionHistory": [
                {"revision": "A", "date": today, "author": "",
                 "description": "Initial draft."}
            ],
        },
        "interfaces": [],
    })


# Artifact builder shims (string-dispatched from ARTIFACT_BUILDERS).
def _write_header(model, prov, path):
    _write_text(path, gen_code.render_header(model, prov))


def _write_simulink(model, prov, path):
    _write_text(path, gen_code.render_simulink(model, prov))


def _write_trace_csv(model, prov, path):
    _write_text(path, gen_trace.render_csv(model, prov))


def _write_trace_xlsx(model, prov, path):
    gen_trace.write_xlsx(model, prov, path)


def _write_docx(model, prov, path):
    gen_docx.build_docx(model, prov, path)


def _write_pdf(model, prov, path):
    gen_pdf.build_pdf(model, prov, path)


def _write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
