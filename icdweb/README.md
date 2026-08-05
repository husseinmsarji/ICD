# icdgen editor — web UI

A form-based web app over the `icdgen` core library. It has **two tabs**:

- **ICD Editor** — author interfaces/packets/signals in a form (no hand-writing
  XML), validate live against the schema, generate all artifacts (DOCX/PDF, C
  header, Simulink bus script, traceability matrix), and build diff reports.
- **Requirements** — the `reqgen` config editor: edit the requirement config,
  see a live requirements preview, view the coverage/traceability matrix, and
  reconcile.

Architecture is documented in [`../AI_README.md`](../AI_README.md) (§10 covers
the web layer and tab persistence).

## Architecture

```
Browser (React + Vite)
      │  /api/*  (JSON)
      ▼
FastAPI backend  ── service layer ──►  icdgen core library  (loader, generators,
      │                │                diff, serializer)
      │                └────────────►  reqgen  (config, preview, trace, reconcile)
      ▼
/data  (projects + generated artifacts, one directory per project)
```

- **Core library (`icdgen/`)** is unchanged from the CLI tool and remains the
  single source of truth for schema, validation, generation, and determinism.
  The web layer never reimplements any of it.
- **Backend (`icdweb/backend/`)** is a thin FastAPI wrapper. `schemas.py` holds
  the API DTOs (incl. `prTicket` and `PriorRevisionDTO`); `service.py`
  orchestrates validate/generate/diff and persists ICD projects (the only file
  touching ICD-project storage); `reqgen_service.py` orchestrates reqgen (it
  never holds config state; the file is the source of truth); `main.py` is just
  routing.
- **Frontend (`icdweb/frontend/`)** is React. The form builds all its inputs
  from the registry descriptors served by `/api/meta/options`, then round-trips
  the model through the identical XSD/jsonschema gate via `icdgen.serializer`.
  A hand-authored file and a form-built one are validated by exactly the same
  code.

### Why this scales to 50–100 users later

The backend is stateless per request; all state lives under `ICDGEN_DATA_DIR`.
To scale, run more uvicorn workers / containers behind a load balancer and point
`ICDGEN_DATA_DIR` at shared storage (NFS or an object-store-backed mount). Long
generations can later move to a job queue (Celery/RQ) without touching the
frontend — `/generate` already returns a result object that could become a job
handle.

## Run with Docker (recommended)

From the **repository root** (the directory containing `icdgen/`, `reqgen/`, and
`icdweb/`):

```bash
docker compose -f icdweb/docker-compose.yml up --build
```

Open <http://localhost:8000>. Projects and artifacts persist in the `icd_data`
volume across restarts.

## Run locally without Docker (dev mode)

```bash
# Terminal 1 — backend
pip install -e ./icdgen
pip install -e ./reqgen
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
2. Edit document metadata, add interfaces/packets, and fill the signal tables.
   The status bar shows live schema validity (debounced), an unsaved indicator,
   and an amber count for non-fatal warnings.
3. In the revision-history table you can attach a **baseline file** per prior
   revision; on generate, the ICD document's revision table gains an
   auto-computed **Change Summary Report** column diffing against it.
4. **Save** persists the definition.
5. In **Generate Artifacts**, choose formats and generate. Download links
   appear, each stamped with the input SHA-256 and tool version; the canonical
   source XML is downloadable too ("Export source XML").
6. **Diff** compares two definitions and downloads a PDF change report.
7. The **Requirements** tab edits the reqgen config, previews requirements, and
   shows the coverage strip + traceability matrix with a CSV download. Its
   state (draft config, chosen ICD source, preview, trace) survives switching
   back to the ICD Editor.

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + tool version |
| GET | `/api/meta/options` | registry descriptors / enum choices for the form |
| GET/POST | `/api/projects` | list / create |
| GET/PUT/DELETE | `/api/projects/{id}` | read / save / delete definition |
| POST | `/api/projects/{id}/validate` | validate (line-referenced errors + warnings) |
| POST | `/api/projects/{id}/generate` | generate selected artifacts (optional `priorFiles`) |
| GET | `/api/projects/{id}/artifacts/{file}` | download an artifact |
| GET | `/api/projects/{id}/export.xml` | canonical source XML |
| POST | `/api/import` | parse uploaded XML/JSON into a definition |
| POST | `/api/diff` | diff two saved definitions (JSON) |
| POST | `/api/diff-files` | diff two uploaded files (JSON) |
| POST | `/api/diff-report` | diff two files → **PDF** change report (download) |
| GET | `/api/reqgen/meta` | reqgen aspect/granularity descriptors |
| GET/PUT | `/api/reqgen/config` | read / save the reqgen config |
| POST | `/api/reqgen/preview` | live requirements preview for a draft config |
| POST | `/api/reqgen/trace` | traceability matrix rows + coverage summary (JSON) |
| POST | `/api/reqgen/trace.csv` | traceability matrix (CSV download) |
| POST | `/api/reqgen/reconcile` | reconcile current reqs vs a prior export |

## Adding a new feature

- **New artifact format**: add the generator in `icdgen/`, then one entry in
  `service.ARTIFACT_BUILDERS`. The API and the UI's format checklist pick it up
  automatically (the frontend reads the list from `/api/meta/options`).
- **New signal/interface field**: add one `FieldSpec` in `icdgen/icdgen/fields.py`
  plus one dataclass attribute in `model.py`. The XSD, jsonschema, serializer,
  DTO descriptor, and the React form column all derive from the registry — the
  editor and validator stay in lockstep automatically.
- **New schema version**: the namespace is versioned; add a `1.1` XSD template
  and register it in `loader.SUPPORTED_SCHEMA_VERSIONS`.

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `ICDGEN_DATA_DIR` | `/data` | where projects + artifacts are stored |
| `ICDGEN_STATIC_DIR` | `/app/static` | built frontend to serve (prod) |
| `ICDGEN_CORS_ORIGINS` | `*` | comma-separated allowed origins |
| `PORT` | `8000` | backend port |
| `ICDGEN_TEMPLATE_DIR` | (unset) | optional Jinja template override (C header / Simulink) |
| `REQGEN_CONFIG` | (unset) | optional reqgen config-of-record path |

## Tests

```bash
cd icdweb/backend
ICDGEN_DATA_DIR=/tmp/icdtest python -m pytest tests/ -q     # 9 passed
```

Includes `test_prior_file_revision_key_cannot_escape_output_dir` (the prior-file
path-traversal guard). See [`../TESTING.md`](../TESTING.md) for the full
walkthrough.
