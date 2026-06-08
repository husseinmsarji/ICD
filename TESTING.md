# TESTING & RUNNING — icdgen v1.2.0

Step-by-step instructions to verify and run everything. Two layers: the core
library/CLI (`icdgen/`) and the web app (`icdweb/`). Pick the path you want;
they share the same core.

Prerequisites: **Python 3.10+**, and for the web frontend **Node 18+ / npm**.
For the container path, **Docker Desktop** (running).

> Unpack the archive first. All paths below are relative to the unpacked repo
> root (the folder containing both `icdgen/` and `icdweb/`).

---

## 1. Core library + CLI

### 1a. Install (use a virtualenv)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ./icdgen              # installs the pinned dependencies
```

### 1b. Run the test suite (expect: 20 passed)

```bash
cd icdgen
pip install pytest
python -m pytest tests/ -q
cd ..
```

The 20 tests cover validation (XML + JSON, with line-referenced errors),
byte-determinism, the signal AND interface registry↔schema sync guards, and
codec round-trips.

### 1c. Validate the demo (expect: 3 interfaces, 4 packets, 10 signals, a SHA-256)

```bash
python -m icdgen validate icdgen/examples/icd_demo.xml
```

### 1d. Generate all six artifacts

```bash
python -m icdgen generate icdgen/examples/icd_demo.xml -o out_demo
ls out_demo
```

You should see: `ICD-EVTOL-DEMO-100.{h,pdf,docx}`, `..._bus.m`,
`..._traceability.{csv,xlsx}`, and `run.log`. Open the `.pdf`/`.docx` to see the
formatted ICD; open the `.h` to see the C structs and `#define`s.

### 1e. Verify DETERMINISM (the core guarantee)

Generate twice into different folders and confirm identical hashes:

```bash
python -m icdgen generate icdgen/examples/icd_demo.xml -o det1
python -m icdgen generate icdgen/examples/icd_demo.xml -o det2
# macOS/Linux:
for f in ICD-EVTOL-DEMO-100.h ICD-EVTOL-DEMO-100.pdf ICD-EVTOL-DEMO-100.docx ICD-EVTOL-DEMO-100_traceability.xlsx; do
  shasum -a 256 det1/$f det2/$f
done
```

```powershell
# Windows PowerShell:
Get-FileHash det1\ICD-EVTOL-DEMO-100.pdf, det2\ICD-EVTOL-DEMO-100.pdf -Algorithm SHA256 |
  Format-Table Hash, Path
```

The two hashes for each file must match. (The `run.log` is the one file that
intentionally records a timestamp — it is provenance metadata, not an artifact,
so don't hash it.)

### 1f. Verify the DIFF feature

```bash
python -m icdgen diff icdgen/examples/icd_demo.xml icdgen/examples/icd_demo_revD.xml
```

Expected: one ADDED signal (`IF-NAV-STATE/POSITION.vertical_speed`), one REMOVED
(`IF-BMS-CAN/PACK_TELEMETRY.state_of_charge`), and one MODIFIED
(`IF-NAV-STATE/POSITION.altitude_msl` range_max 6000->8000). Exit code is 2 when
differences exist (useful for CI gates); add `-o out_demo` to also write
`*_diff.txt` and `*_diff.csv`.

### 1g. (Optional) Confirm the generated C header compiles

```bash
gcc -std=c99 -Wall -c out_demo/ICD-EVTOL-DEMO-100.h -o /tmp/icd.o \
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
1. Click **Import XML / JSON** and choose `icdgen/examples/icd_demo.xml`.
2. The form fills with 6 interfaces. Expand one; edit a signal — note the status
   bar shows **SCHEMA VALID** (or a line-referenced error if you break a field).
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

### Backend tests (expect: 7 passed)

```bash
cd icdweb/backend
ICDGEN_DATA_DIR=/tmp/icdtest python -m pytest tests/ -q
```

---

## 4. One-shot "everything passes" check

```bash
# from repo root, venv active, icdgen installed (step 1a)
( cd icdgen && python -m pytest tests/ -q ) && \
( cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/icdtest python -m pytest tests/ -q ) && \
python -m icdgen generate icdgen/examples/icd_demo.xml -o /tmp/_v && \
echo "ALL GREEN"
```

Expected tail: `20 passed`, `7 passed`, a generate summary, then `ALL GREEN`.

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
