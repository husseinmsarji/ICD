"""FastAPI application for the ICD editor.

Thin HTTP layer over service.py (ICD projects) and reqgen_service.py (the
requirement-generation config editor). Endpoints:
  GET    /api/health
  GET    /api/meta/options            enum options for the form (bus, dal, types)
  GET    /api/projects                list projects
  POST   /api/projects                create project
  GET    /api/projects/{id}           read definition
  PUT    /api/projects/{id}           save definition
  DELETE /api/projects/{id}           delete project
  POST   /api/projects/{id}/validate  validate current/posted definition
  POST   /api/projects/{id}/generate  generate artifacts
  GET    /api/projects/{id}/artifacts/{filename}   download an artifact
  POST   /api/import                  parse an uploaded YAML into a definition
  POST   /api/diff                    diff two posted definitions
  POST   /api/diff-files              diff two uploaded files (JSON)
  POST   /api/diff-report             diff two uploaded files (PDF download)
  GET    /api/projects/{id}/export.yaml

  --- reqgen config editor ---
  GET    /api/reqgen/meta             aspect-registry descriptor for the editor
  GET    /api/reqgen/config           config of record (+ hash)
  PUT    /api/reqgen/config           validate + save a config draft (400 on
                                      bright-line / schema violation)
  POST   /api/reqgen/preview          generate requirements from a draft config
  POST   /api/reqgen/trace            traceability matrix (rows + coverage)
  POST   /api/reqgen/trace.csv        traceability matrix as a CSV download
  POST   /api/reqgen/reconcile        draft-vs-saved requirement diff

The static React build is mounted at / when present (single-container deploy).
"""
from __future__ import annotations

import os
import tempfile

from fastapi import Body, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from icdgen.loader import ValidationError, load
from icdgen.provenance import TOOL_VERSION
from icdgen.serializer import to_yaml

from . import service
from . import reqgen_service
from .schemas import IcdDTO, model_to_dto

app = FastAPI(title="icdgen editor", version=TOOL_VERSION)

# CORS: permissive in dev (Vite on :5173). Tighten via env for production.
_origins = os.environ.get("ICDGEN_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "toolVersion": TOOL_VERSION}


@app.get("/api/meta/options")
def options():
    """Enum choices + signal field descriptor for the editor.

    Everything here is derived from the icdgen field registry, so the form and
    the validator are guaranteed consistent and a new field surfaces in the UI
    automatically.
    """
    from icdgen.fields import (
        BUS_TYPES, DAL_LEVELS, DIRECTIONS, DATA_TYPE_NAMES,
        signal_fields_descriptor,
        interface_fields_descriptor,
    )
    return {
        "busTypes": list(BUS_TYPES),
        "dalLevels": list(DAL_LEVELS),
        "dataTypes": list(DATA_TYPE_NAMES),
        "directions": list(DIRECTIONS),
        "signalFields": signal_fields_descriptor(),
        "interfaceFields": interface_fields_descriptor(),
        "artifactFormats": list(service.ARTIFACT_BUILDERS.keys()),
        "toolVersion": TOOL_VERSION,
    }


@app.get("/api/projects")
def get_projects():
    return service.list_projects()


@app.post("/api/projects")
def post_project(payload: dict = Body(...)):
    name = payload.get("name", "Untitled ICD")
    dto = None
    if payload.get("definition") is not None:
        dto = IcdDTO.model_validate(payload["definition"])
    return service.create_project(name, dto)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    try:
        return {
            "meta": service.read_meta(project_id),
            "definition": service.read_definition(project_id).model_dump(),
        }
    except FileNotFoundError:
        raise HTTPException(404, "project not found")


@app.put("/api/projects/{project_id}")
def put_project(project_id: str, payload: dict = Body(...)):
    try:
        dto = IcdDTO.model_validate(payload["definition"])
        meta = service.save_definition(project_id, dto, name=payload.get("name"))
        return meta
    except FileNotFoundError:
        raise HTTPException(404, "project not found")


@app.delete("/api/projects/{project_id}")
def del_project(project_id: str):
    service.delete_project(project_id)
    return {"deleted": project_id}


@app.post("/api/projects/{project_id}/validate")
def validate_project(project_id: str, payload: dict = Body(default=None)):
    # Validate the posted definition if provided, else the saved one.
    if payload and payload.get("definition") is not None:
        dto = IcdDTO.model_validate(payload["definition"])
    else:
        try:
            dto = service.read_definition(project_id)
        except FileNotFoundError:
            raise HTTPException(404, "project not found")
    errors, warnings = service.validate_dto(dto)
    return {
        "ok": len(errors) == 0,
        "issues": [i.__dict__ for i in errors],
        "warnings": [w.__dict__ for w in warnings],
    }


@app.post("/api/projects/{project_id}/generate")
def generate_project(project_id: str, payload: dict = Body(default=None)):
    formats = (payload or {}).get("formats") or list(service.ARTIFACT_BUILDERS.keys())
    # Optional just-in-time prior-revision files for the Change Summary Report
    # column: {revisionLetter: fileText}. Not persisted with the project.
    prior_files = (payload or {}).get("priorFiles") or None
    # Persist posted definition first so generation reflects the latest edits.
    if payload and payload.get("definition") is not None:
        dto = IcdDTO.model_validate(payload["definition"])
        service.save_definition(project_id, dto)
    try:
        return service.generate(project_id, formats, prior_files=prior_files)
    except FileNotFoundError:
        raise HTTPException(404, "project not found")


@app.get("/api/projects/{project_id}/artifacts/{filename}")
def download_artifact(project_id: str, filename: str):
    try:
        path = service.artifact_path(project_id, filename)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "artifact not found")
    return FileResponse(path, filename=filename)


@app.post("/api/import")
async def import_file(file: UploadFile):
    """Parse an uploaded YAML ICD into an editable definition (no save)."""
    raw = await file.read()
    with tempfile.NamedTemporaryFile("wb", suffix=".yaml", delete=False) as fh:
        fh.write(raw)
        tmp = fh.name
    try:
        model, file_hash, warns = load(tmp)
        return {"ok": True, "definition": model_to_dto(model).model_dump(),
                "inputHash": file_hash,
                "warnings": [{"message": w.message, "line": w.line} for w in warns]}
    except ValidationError as exc:
        return {"ok": False, "issues": [{"message": exc.message, "line": exc.line}]}
    finally:
        os.unlink(tmp)


@app.post("/api/diff")
def diff_definitions(payload: dict = Body(...)):
    old = IcdDTO.model_validate(payload["old"])
    new = IcdDTO.model_validate(payload["new"])
    return service.diff(old, new)


@app.post("/api/diff-files")
async def diff_files(old: UploadFile, new: UploadFile):
    """Diff two uploaded YAML ICD files directly. Each is parsed via the
    authoritative loader; a parse failure on either side returns an error."""
    async def _parse(f: UploadFile):
        raw = await f.read()
        with tempfile.NamedTemporaryFile("wb", suffix=".yaml", delete=False) as fh:
            fh.write(raw)
            tmp = fh.name
        try:
            model, _hash, _warns = load(tmp)
            return model_to_dto(model), None
        except ValidationError as exc:
            return None, {"message": exc.message, "line": exc.line}
        finally:
            os.unlink(tmp)

    old_dto, old_err = await _parse(old)
    if old_err:
        return {"ok": False, "side": "old", "issue": old_err}
    new_dto, new_err = await _parse(new)
    if new_err:
        return {"ok": False, "side": "new", "issue": new_err}
    result = service.diff(old_dto, new_dto)
    result["ok"] = True
    return result


@app.post("/api/diff-report")
async def diff_report(old: UploadFile, new: UploadFile):
    """Diff two uploaded YAML ICD files and return a formatted PDF change
    report as a download. Either side failing to parse yields a 400 with the
    offending side + message."""
    import hashlib
    from fastapi.responses import Response
    from icdgen.diff import diff as _diff
    from icdgen.gen_diff_pdf import build_diff_pdf

    async def _parse(f: UploadFile):
        raw = await f.read()
        with tempfile.NamedTemporaryFile("wb", suffix=".yaml", delete=False) as fh:
            fh.write(raw)
            tmp = fh.name
        try:
            model, _hash, _warns = load(tmp)
            return model, None
        except ValidationError as exc:
            return None, {"message": exc.message, "line": exc.line}
        finally:
            os.unlink(tmp)

    old_model, old_err = await _parse(old)
    if old_err:
        raise HTTPException(400, f"old file: {old_err['message']}")
    new_model, new_err = await _parse(new)
    if new_err:
        raise HTTPException(400, f"new file: {new_err['message']}")

    # Hash the canonical serialized YAML of each side (matches generate()).
    old_yaml = to_yaml(old_model)
    new_yaml = to_yaml(new_model)
    old_hash = hashlib.sha256(old_yaml.encode("utf-8")).hexdigest()
    new_hash = hashlib.sha256(new_yaml.encode("utf-8")).hexdigest()

    res = _diff(old_model, new_model)
    with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as fh:
        out = fh.name
    try:
        build_diff_pdf(res, old_hash, new_hash, out,
                       old_label=old.filename or "old",
                       new_label=new.filename or "new")
        data = open(out, "rb").read()
    finally:
        os.unlink(out)

    fname = f"{new_model.metadata.document_id}_diff.pdf"
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/api/projects/{project_id}/export.yaml")
def export_yaml(project_id: str):
    from fastapi.responses import Response
    try:
        dto = service.read_definition(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "project not found")
    from .schemas import dto_to_model
    yaml_text = to_yaml(dto_to_model(dto))
    return Response(yaml_text, media_type="application/x-yaml")


# ==========================================================================
# reqgen config editor
#
# The config FILE is the single record of truth and reqgen.config_io.save_config
# is its only writer. These routes are a thin pass-through to reqgen_service,
# which never holds its own config state. PUT validates (bright line included)
# and 400s on a bad draft; preview/trace/reconcile generate in-memory and never
# write.
# ==========================================================================
@app.get("/api/reqgen/meta")
def reqgen_meta():
    return reqgen_service.meta()


@app.get("/api/reqgen/config")
def reqgen_get_config():
    return reqgen_service.read_config()


@app.put("/api/reqgen/config")
def reqgen_put_config(payload: dict = Body(...)):
    cfg = (payload or {}).get("config")
    if cfg is None:
        raise HTTPException(400, "missing 'config'")
    try:
        return reqgen_service.save(cfg)
    except reqgen_service.ConfigError as exc:
        # Bright-line / schema violation -> 400 with the specific message.
        raise HTTPException(400, str(exc))


@app.post("/api/reqgen/preview")
def reqgen_preview(payload: dict = Body(...)):
    try:
        result = reqgen_service.preview(payload or {})
    except FileNotFoundError:
        raise HTTPException(404, "ICD project not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except ValidationError as exc:
        raise HTTPException(400, f"ICD did not validate: {exc}")
    return result


@app.post("/api/reqgen/trace")
def reqgen_trace(payload: dict = Body(...)):
    """Requirements-to-signals traceability matrix (rows + coverage summary)
    for the posted draft config against the chosen ICD. Read-only."""
    try:
        result = reqgen_service.trace(payload or {})
    except FileNotFoundError:
        raise HTTPException(404, "ICD project not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except ValidationError as exc:
        raise HTTPException(400, f"ICD did not validate: {exc}")
    return result


@app.post("/api/reqgen/trace.csv")
def reqgen_trace_csv(payload: dict = Body(...)):
    """Stream the traceability matrix as a downloadable CSV."""
    from fastapi.responses import Response
    try:
        csv_text, doc_id = reqgen_service.trace_csv(payload or {})
    except reqgen_service.ConfigError as exc:
        raise HTTPException(400, str(exc))
    except FileNotFoundError:
        raise HTTPException(404, "ICD project not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except ValidationError as exc:
        raise HTTPException(400, f"ICD did not validate: {exc}")
    fname = f"{doc_id}_req_trace.csv"
    return Response(csv_text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/api/reqgen/reconcile")
def reqgen_reconcile(payload: dict = Body(...)):
    try:
        result = reqgen_service.reconcile(payload or {})
    except FileNotFoundError:
        raise HTTPException(404, "ICD project not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except ValidationError as exc:
        raise HTTPException(400, f"ICD did not validate: {exc}")
    return result


# ---- Serve the built frontend if present (production single-container) ----
_static_dir = os.environ.get("ICDGEN_STATIC_DIR", "/app/static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")