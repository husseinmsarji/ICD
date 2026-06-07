"""FastAPI application for the ICD editor.

Thin HTTP layer over service.py. Endpoints:
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
  POST   /api/import                  parse an uploaded XML/JSON into a definition
  POST   /api/diff                    diff two posted definitions

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
from icdgen.serializer import to_xml

from . import service
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
    # Persist posted definition first so generation reflects the latest edits.
    if payload and payload.get("definition") is not None:
        dto = IcdDTO.model_validate(payload["definition"])
        service.save_definition(project_id, dto)
    try:
        return service.generate(project_id, formats)
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
    """Parse an uploaded XML/JSON ICD into an editable definition (no save)."""
    raw = await file.read()
    suffix = ".json" if (file.filename or "").lower().endswith(".json") else ".xml"
    with tempfile.NamedTemporaryFile("wb", suffix=suffix, delete=False) as fh:
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
    """Diff two uploaded XML/JSON ICD files directly. Each is parsed via the
    authoritative loader; a parse failure on either side returns an error."""
    async def _parse(f: UploadFile):
        raw = await f.read()
        sfx = ".json" if (f.filename or "").lower().endswith(".json") else ".xml"
        with tempfile.NamedTemporaryFile("wb", suffix=sfx, delete=False) as fh:
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


@app.get("/api/projects/{project_id}/export.xml")
def export_xml(project_id: str):
    from fastapi.responses import Response
    try:
        dto = service.read_definition(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "project not found")
    from .schemas import dto_to_model
    xml = to_xml(dto_to_model(dto))
    return Response(xml, media_type="application/xml")


# ---- Serve the built frontend if present (production single-container) ----
_static_dir = os.environ.get("ICDGEN_STATIC_DIR", "/app/static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")