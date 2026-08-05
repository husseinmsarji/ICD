# TESTING & RUNNING — icdgen / reqgen / icdweb (v1.6.0)

Step-by-step instructions to verify and run everything. Three pieces share one
core library:

- **`icdgen/`** — core library + CLI (validate / generate / diff).
- **`reqgen/`** — a separate requirement generator that imports icdgen.
- **`icdweb/`** — a FastAPI + React web app over the core.

Architecture details are in [`AI_README.md`](AI_README.md); this file is the
"run it and confirm it works" guide.

Prerequisites: **Python 3.10+**, and for the web frontend **Node 18+ / npm**.
For the container path, **Docker Desktop** (running). All paths below are
relative to the repo root (the folder containing `icdgen/`, `reqgen/`, and
`icdweb/`).

The demo ICD is **`ICD-EVTOL-AVS-200`**, supplied as three revisions:

| File | Interfaces | Packets | Signals |
|---|---|---|---|
| `icdgen/examples/icd_evtol_revA.xml` | 3 | 3 | 9 |
| `icdgen/examples/icd_evtol_revB.xml` | 4 | 5 | 16 |
| `icdgen/examples/icd_evtol_revC.xml` (current) | 6 | 9 | 31 |

---

## 1. Core library + CLI (`icdgen`)

### 1a. Install (use a virtualenv)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ./icdgen              # installs the EXACT-pinned dependencies
```

### 1b. Run the test suite (expect: 36 passed)

```bash
pip install pytest
cd icdgen && python -m pytest tests/ -q && cd ..
```

The suite covers XML+JSON validation with line-referenced errors, the signal
AND interface registry↔schema sync guards, codec round-trips, byte-determinism,
the prior-revision auto-diff summaries, and `test_pr_ticket_in_traceability`
(the PR Ticket column in the traceability matrix).

### 1c. Validate the current demo (expect: 6 interfaces, 9 packets, 31 signals)

```bash
python -m icdgen validate icdgen/examples/icd_evtol_revC.xml
```

Post-Rev-A ICDs emit non-fatal `WARNING`s for signals carried over without a PR
ticket — that is expected (exit code 0). Add `--strict` to turn every warning
fatal (the release gate).

### 1d. Generate all artifacts

```bash
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o out
ls out
```

You should see, for `ICD-EVTOL-AVS-200`:
`.docx`, `.pdf`, `.h` (MISRA C:2012-oriented), `_bus.m` (Simulink),
`_traceability.csv`, `_traceability.xlsx`, and `run.log`. Restrict the set with
`-f` (choices: `docx pdf header simulink trace-csv trace-xlsx`).

### 1e. Verify DETERMINISM (the core guarantee)

Generate twice and confirm identical hashes:

```bash
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o det1
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o det2
# macOS/Linux:
for f in ICD-EVTOL-AVS-200.h ICD-EVTOL-AVS-200.pdf ICD-EVTOL-AVS-200.docx \
         ICD-EVTOL-AVS-200_traceability.csv ICD-EVTOL-AVS-200_traceability.xlsx; do
  shasum -a 256 det1/$f det2/$f
done
```

```powershell
# Windows PowerShell:
Get-FileHash det1\ICD-EVTOL-AVS-200.pdf, det2\ICD-EVTOL-AVS-200.pdf -Algorithm SHA256 |
  Format-Table Hash, Path
```

The two hashes for each file must match. `run.log` is the one file that
intentionally records a timestamp — it is provenance metadata, not an artifact,
so don't hash it.

### 1f. Verify the DIFF feature (text / CSV / PDF)

```bash
python -m icdgen diff icdgen/examples/icd_evtol_revB.xml \
                      icdgen/examples/icd_evtol_revC.xml -o out
```

Writes `ICD-EVTOL-AVS-200_diff.{txt,csv,pdf}` classifying added / removed /
modified signals (and interface add/remove) with old→new field values. Exit
code is **2** when differences exist (useful for CI gates).

---

## 2. Requirement generator (`reqgen`)

`reqgen` reads an ICD as a library input and emits a requirements export, a
requirements-to-signals traceability matrix, and a reconciliation report. It
never writes back into the ICD.

```bash
pip install -e ./reqgen
```

### 2a. Run the test suite (expect: 25 passed)

```bash
cd icdgen && PYTHONPATH=../reqgen python -m pytest ../reqgen/tests/ -q && cd ..
```

Covers the aspect registry, the L3 port/packet granularity model, applicability
(no vacuous requirements), the trace matrix + coverage, reconciliation, and the
`test_package_is_properly_nested` layout guard.

### 2b. Generate + trace + reconcile

```bash
reqgen init                                             # writes config/reqgen.json from defaults
reqgen generate icdgen/examples/icd_evtol_revC.xml -o out
reqgen trace    icdgen/examples/icd_evtol_revC.xml -o out
reqgen reconcile icdgen/examples/icd_evtol_revC.xml out/ICD-EVTOL-AVS-200_requirements.csv
```

Expected: `generate` → `ICD-EVTOL-AVS-200_requirements.csv` (80 requirements for
revC); `trace` → `ICD-EVTOL-AVS-200_req_trace.csv`, prints `L3: 9/9 covered` /
`L4: 31/31 covered` to stderr and exits **2** on any coverage gap (**0** when
fully covered). `generate`/`trace`/`reconcile` auto-create the config from
defaults if it is absent.

---

## 3. Web app (`icdweb`) — quickest path: Docker (recommended)

From the repo root, with Docker Desktop running:

```bash
docker compose -f icdweb/docker-compose.yml up --build
```

First build takes a few minutes. Then open **http://localhost:8000**.

Smoke test in the UI:
1. **Import XML / JSON** and choose `icdgen/examples/icd_evtol_revC.xml`. The
   form fills with 6 interfaces; expand one and edit a signal — the status bar
   shows **SCHEMA VALID** (or a line-referenced error) and an amber warning
   count.
2. **Save**, then in **Generate Artifacts** pick formats and **Generate**;
   download links appear, each stamped with the input SHA-256.
3. Switch to the **Requirements** tab: edit the reqgen config, see the live
   requirements preview and the coverage/traceability matrix, and download the
   trace CSV. The tab state survives switching back to the ICD Editor.

Stop with `Ctrl+C`; data persists in the `icd_data` Docker volume.

---

## 4. Web app — local dev (two terminals, hot reload)

```bash
# Terminal 1 — backend (auto-reload)
source .venv/bin/activate
pip install -r icdweb/backend/requirements.txt
ICDGEN_DATA_DIR=./_data uvicorn app.main:app --reload --app-dir icdweb/backend
```

```bash
# Terminal 2 — frontend (proxies /api to :8000)
cd icdweb/frontend
npm install
npm run dev            # open the printed http://localhost:5173
```

In dev use the Vite URL (`:5173`); the Docker/production build serves the built
frontend on a single port.

### Backend tests (expect: 9 passed)

```bash
cd icdweb/backend
ICDGEN_DATA_DIR=/tmp/icdtest python -m pytest tests/ -q
```

Includes `test_prior_file_revision_key_cannot_escape_output_dir` (the
prior-file path-traversal guard).

---

## 5. One-shot "everything passes" check

```bash
# from repo root, venv active, icdgen + reqgen installed
( cd icdgen && python -m pytest tests/ -q ) && \
( cd icdgen && PYTHONPATH=../reqgen python -m pytest ../reqgen/tests/ -q ) && \
( cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/icdtest python -m pytest tests/ -q ) && \
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o /tmp/_v && \
echo "ALL GREEN"
```

Expected tail: `36 passed`, `25 passed`, `9 passed`, a generate summary, then
`ALL GREEN`.

---

## Troubleshooting

- **`docker ... cannot find ... dockerDesktopLinuxEngine`** — Docker Desktop
  isn't running. Start it, wait for "Engine running", retry.
- **`vite: not found`** — run `npm install` in `icdweb/frontend` first.
- **Determinism hashes differ** — make sure you installed from the pinned
  `icdgen/requirements.txt`; a different ReportLab/python-docx/openpyxl version
  can change output bytes (that is exactly what the pins prevent).
- **A field you added doesn't appear** — see
  [`AI_README.md`](AI_README.md) → "How to make common changes". A signal or
  interface field is one `FieldSpec` in `icdgen/icdgen/fields.py` plus one
  dataclass attribute in `model.py`; everything else derives from the registry.
