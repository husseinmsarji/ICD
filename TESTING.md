# TESTING & RUNNING — icdgen v1.6.0

Step-by-step instructions to verify and run everything. Three layers: the core
library/CLI (`icdgen/`), the web app (`icdweb/`), and the requirement generator
(`reqgen/`). They share the same core. Pick the path you want.

Prerequisites: **Python 3.10+**, and for the web frontend **Node 18+ / npm**.
For the container path, **Docker Desktop** (running).

> Unpack the archive first. All paths below are relative to the unpacked repo
> root (the folder containing `icdgen/`, `icdweb/`, and `reqgen/`).

---

## 1. Core library + CLI

### 1a. Install (use a virtualenv)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ./icdgen              # installs the pinned dependencies
```

### 1b. Run the test suite (expect: 36 passed)

```bash
cd icdgen
pip install pytest
python -m pytest tests/ -q
cd ..
```

The tests cover validation (XML + JSON, with line-referenced errors), the
permissive-draft / warnings behavior, byte-determinism, provenance stamping, the
signal AND interface registry↔schema sync guards, the PR-ticket change-control
field, the prior-revision Change Summary Report, the standalone diff PDF, the
serializer quote-escaping regression, and codec round-trips.

### 1c. Validate the demo (expect: 6 interfaces, 9 packets, 31 signals, a SHA-256)

```bash
python -m icdgen validate icdgen/examples/icd_evtol_revC.xml
```

Rev C is the current revision of the demonstration ICD (`ICD-EVTOL-AVS-200`).
It will print non-fatal WARNINGs for carried-over signals that have no AVS
change-control ticket — that is expected: only signals *touched* in a revision
carry a ticket.

### 1d. Generate all six artifacts

```bash
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o out_demo
ls out_demo
```

You should see: `ICD-EVTOL-AVS-200.{h,pdf,docx}`, `..._bus.m`,
`..._traceability.{csv,xlsx}`, and `run.log`. Open the `.pdf`/`.docx` to see the
formatted ICD (the revision-history table carries the auto "Change Summary
Report" column, since revC links revB as a prior revision); open the `.h` to see
the C structs and `#define`s.

### 1e. Verify DETERMINISM (the core guarantee)

Generate twice into different folders and confirm identical hashes:

```bash
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o det1
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o det2
# macOS/Linux:
for f in ICD-EVTOL-AVS-200.h ICD-EVTOL-AVS-200.pdf ICD-EVTOL-AVS-200.docx ICD-EVTOL-AVS-200_traceability.xlsx; do
  shasum -a 256 det1/$f det2/$f
done
```

```powershell
# Windows PowerShell:
Get-FileHash det1\ICD-EVTOL-AVS-200.pdf, det2\ICD-EVTOL-AVS-200.pdf -Algorithm SHA256 |
  Format-Table Hash, Path
```

The two hashes for each file must match. (The `run.log` is the one file that
intentionally records a timestamp — it is provenance metadata, not an artifact,
so don't hash it.)

### 1f. Verify the DIFF feature

```bash
python -m icdgen diff icdgen/examples/icd_evtol_revB.xml icdgen/examples/icd_evtol_revC.xml
```

Expected: two ADDED interfaces (`IF-ENV`, `IF-MOTOR-TELEM`), a batch of ADDED
signals (the new VELOCITY / MOTOR_TELEMETRY / AIR_DATA / CELL_HEALTH packets),
one REMOVED signal (`IF-BMS-CAN/PACK_TELEMETRY.bms_fault`), and two MODIFIED
signals (`torque_limit` range_max 400→500; `yaw_rate` range tightened). Exit
code is 2 when differences exist (useful for CI gates); add `-o out_demo` to also
write `*_diff.txt`, `*_diff.csv`, and `*_diff.pdf`.

### 1g. (Optional) Confirm the generated C header compiles

```bash
gcc -std=c99 -Wall -c out_demo/ICD-EVTOL-AVS-200.h -o /tmp/icd.o \
    -I out_demo 2>/dev/null && echo "compiles" || echo "see warnings"
```
(Compiling a header alone needs it included from a .c; the project README shows a
one-line test harness if you want a strict check.)

---

## 2. Web app — quickest path: Docker (recommended)

From the repo root, with Docker Desktop running:

```bash
docker compose -f icdweb/docker-compose.yml up --build
```

First build takes a few minutes (pulls base images, installs deps, builds the
React app). Then open **http://localhost:8000**.

Smoke test in the UI:
1. Click **Import XML / JSON** and choose `icdgen/examples/icd_evtol_revC.xml`.
2. The form fills with the interfaces. Expand one; edit a signal — note the
   status bar shows **SCHEMA VALID** (or a line-referenced error if you break a
   field).
3. **Save**, then in **Generate Artifacts** pick formats and **Generate**.
4. Download links appear, each stamped with the input SHA-256.

Stop with `Ctrl+C`; data persists in the `icd_data` Docker volume.

---

## 3. Web app — local dev (two terminals, hot reload)

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

### Backend tests (expect: 8 passed)

```bash
cd icdweb/backend
ICDGEN_DATA_DIR=/tmp/icdtest python -m pytest tests/ -q
```

---

## 4. Requirement generator (reqgen)

`reqgen` reads an icdgen ICD and emits an RM-tool requirements export plus a
reconciliation report. It is a separate, independently-qualifiable tool.

```bash
pip install -e ./reqgen                                  # depends on icdgen
reqgen init                                              # creates reqgen/config/reqgen.json
reqgen generate icdgen/examples/icd_evtol_revC.xml -o out
reqgen reconcile icdgen/examples/icd_evtol_revC.xml out/ICD-EVTOL-AVS-200_requirements.csv
```

### reqgen tests (expect: 16 passed)

```bash
cd icdgen && PYTHONPATH=../reqgen python -m pytest ../reqgen/tests/ -q
```

---

## 5. One-shot "everything passes" check

```bash
# from repo root, venv active, icdgen installed (step 1a)
( cd icdgen && python -m pytest tests/ -q ) && \
( cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/icdtest python -m pytest tests/ -q ) && \
python -m icdgen generate icdgen/examples/icd_evtol_revC.xml -o /tmp/_v && \
echo "ALL GREEN"
```

Expected tail: `36 passed`, `8 passed`, a generate summary, then `ALL GREEN`.

---

## Troubleshooting

- **`docker ... cannot find the file ... dockerDesktopLinuxEngine`** — Docker
  Desktop isn't running. Start it, wait for "Engine running", retry.
- **`vite: not found`** — run `npm install` in `icdweb/frontend` first.
- **Determinism hashes differ** — make sure you installed from the pinned
  `icdgen/requirements.txt` (a different ReportLab/python-docx version can change
  output bytes; that's exactly what the pins prevent).
- **A field you added doesn't appear** — see `AI_README.md` → "How to make common
  changes". For a signal/interface field it's one `FieldSpec` in `fields.py` plus
  one dataclass attribute in `model.py`; nothing else.
- **`priorRevisions ... not expected` on validate** — your installed tree has a
  stale XSD copy. The template is now single-sourced inside the package
  (`icdgen/icdgen/schemas/icd-1.0.xsd.template`); make sure no stale repo-root
  `icdgen/schemas/icd-1.0.xsd.template` shadows it, then reinstall.
