# icdgen editor — web UI

A form-based web editor for ICD interface definitions, built on top of the
`icdgen` core library. Author interfaces and signals in a UI (no hand-writing
XML), validate live against the schema, and generate all artifacts — ICD
documents (DOCX/PDF), C/C++ headers, Simulink bus scripts, and traceability
matrices — with one click.

## Architecture

```
Browser (React + Vite)
      │  /api/*  (JSON)
      ▼
FastAPI backend  ── service layer ──►  icdgen core library
      │                                  (loader, generators, diff, serializer)
      ▼
/data  (projects + generated artifacts, one directory per project)
```

- **Core library (`icdgen/`)** is unchanged from the CLI tool and remains the
  single source of truth for the schema, validation, generation, and
  determinism guarantees. The web layer never reimplements any of it.
- **Backend (`icdweb/backend/`)** is a thin FastAPI wrapper. `schemas.py` holds
  the API DTOs and conversions to/from the core model; `service.py` orchestrates
  validate/generate/diff and persists projects; `main.py` is just routing.
- **Frontend (`icdweb/frontend/`)** is React. The form editor builds the same
  canonical model the validator expects, then round-trips it through the
  identical XSD/jsonschema gate via the new `icdgen.serializer`. A hand-authored
  file and a form-built one are validated by exactly the same code.

### Why this scales to 50–100 users later

The backend is stateless per request; all state lives under `ICDGEN_DATA_DIR`.
To scale you run more uvicorn workers / containers behind a load balancer and
point `ICDGEN_DATA_DIR` at shared storage (NFS or an object-store-backed mount).
Long generations can later move to a job queue (Celery/RQ) without touching the
frontend — the `/generate` endpoint already returns a result object that could
become a job handle. Nothing in the current design blocks that.

## Run with Docker (recommended)

From the **repository root** (the directory containing both `icdgen/` and
`icdweb/`):

```bash
docker compose -f icdweb/docker-compose.yml up --build
```

Open <http://localhost:8000>. Projects and artifacts persist in the `icd_data`
volume across restarts.

## Run locally without Docker (dev mode)

Two terminals — backend with autoreload, frontend with hot module reload:

```bash
# Terminal 1 — backend
pip install -e ./icdgen
pip install -r icdweb/backend/requirements.txt
ICDGEN_DATA_DIR=./_data uvicorn app.main:app --reload --app-dir icdweb/backend

# Terminal 2 — frontend (proxies /api to :8000)
cd icdweb/frontend
npm install
npm run dev          # http://localhost:5173
```

In dev, use the Vite URL (`:5173`); it proxies API calls to the backend. In the
Docker/production build, the backend serves the built frontend on a single port.

## Using the editor

1. **New** creates an empty ICD, or **Import XML / JSON** loads an existing
   definition into an editable project.
2. Edit document metadata, add interfaces, and fill the signal tables. The
   status bar shows live schema validity (debounced) and an unsaved indicator.
3. **Save** persists the definition.
4. In **Generate Artifacts**, choose formats and generate. Download links
   appear, each artifact stamped with the input SHA-256 and tool version. The
   source XML the artifacts were generated from is also downloadable
   ("Export source XML").

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + tool version |
| GET | `/api/meta/options` | enum choices for the form |
| GET/POST | `/api/projects` | list / create |
| GET/PUT/DELETE | `/api/projects/{id}` | read / save / delete definition |
| POST | `/api/projects/{id}/validate` | validate (line-referenced errors) |
| POST | `/api/projects/{id}/generate` | generate selected artifacts |
| GET | `/api/projects/{id}/artifacts/{file}` | download an artifact |
| GET | `/api/projects/{id}/export.xml` | canonical source XML |
| POST | `/api/import` | parse uploaded XML/JSON into a definition |
| POST | `/api/diff` | diff two definitions |

## Adding a new feature

- **New artifact format**: add the generator in `icdgen/`, then one line in
  `service.ARTIFACT_BUILDERS`. The API and the UI's format checklist pick it up
  automatically (the frontend reads the list from `/api/meta/options`).
- **New signal field**: add it to the XSD + jsonschema + `serializer.py`, the
  `Signal` dataclass, the `SignalDTO`, and one column in
  `frontend/src/SignalTable.jsx`. The editor and validator stay in lockstep.
- **New schema version**: the namespace is versioned; add a `1.1` XSD and
  register it in `loader.SUPPORTED_SCHEMA_VERSIONS`.

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `ICDGEN_DATA_DIR` | `/data` | where projects + artifacts are stored |
| `ICDGEN_STATIC_DIR` | `/app/static` | built frontend to serve (prod) |
| `ICDGEN_CORS_ORIGINS` | `*` | comma-separated allowed origins |
| `PORT` | `8000` | backend port |
