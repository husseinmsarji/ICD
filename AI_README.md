# AI_README — icdgen / reqgen / icdweb architecture map

> **Purpose of this file.** This is the single document to paste back to Claude
> (or hand to any engineer) when requesting changes. It describes every file,
> its responsibilities, the key functions/classes, the data flow, the invariants
> that must hold, and the recipes for common changes — so source files do not
> need to be re-sent to understand the system.
>
> **Maintenance rule.** This file is regenerated **in full** at the end of every
> change so it always matches the code. Treat it as the source of truth for
> "what version are we on and how is it built." If this file and the code
> disagree, **the code wins** and this file must be corrected.

---

## 0. Status

No open blocking issues. The two historical section-0 items are resolved:

- **XSD template single-sourcing** — resolved. The XSD template is one physical
  file, package data at `icdgen/icdgen/schemas/icd-1.0.xsd.template`; it cannot
  drift across layouts. See section 3 (Schema note).
- **Stale test example references** — resolved. All three suites point at the
  eVTOL examples (`icd_evtol_revA/B/C.xml`): `icdgen/tests/test_icdgen.py`
  (EX_XML = revA, asserts 3 interfaces; diff-PDF tests use revB→revC),
  `icdweb/backend/tests/test_api.py` (revA import; the Flow A prior-file test
  uses revC/revB and asserts `+vel_north` / `AVS-1101`), and
  `reqgen/tests/test_reqgen.py` (revC/revB, 6 if / 9 pkt / 31 sig). NOTE: revC
  has 9 packets (count corrected from a stale 8 in the prior test/README; the
  example XML header comment still says 8 and should be fixed).

Recently delivered (no version bump): a **granularity-aware L3 aspect model**
(port/interface-contract aspects vs packet/message aspects, section 9.6), the
reqgen applicability + traceability matrix and its **web UI** (download +
on-screen coverage), the icdgen `--strict` release gate, the
`ICDGEN_TEMPLATE_DIR` override with run.log provenance closure, the PR Ticket
traceability column, the C-header/Simulink sanitizers, and the prior-file
path-traversal guard. Details in sections 1, 9.6, 10, 15, 16.

---

## 1. Version & history

- **Project version (`icdgen/pyproject.toml`):** 1.6.0
- **`icdgen` tool/provenance version:** 1.0.0 — the string stamped into
  artifacts (`provenance.TOOL_VERSION`). Bump it deliberately; it is independent
  of the project version and changing it changes artifact bytes (re-baseline).
- **`reqgen` tool version:** 0.1.0 (`reqgen.provenance.TOOL_VERSION`).
- **Schema version:** 1.0 — XML namespace `urn:icdgen:icd:1.0`, `schemaVersion`
  attribute pinned to `1.x`.

### History
- **1.0.0** — initial CLI tool + web app.
- **1.1.0** — SIGNAL field-registry refactor (single source of truth; XSD + JSON
  Schema generated, no longer hand-duplicated).
- **1.2.0** — INTERFACE field-registry refactor; deps EXACT-pinned; full demo.
- **1.2.1** — Dockerfile frontend COPY path bugfix (build context = repo root).
- **1.3.0** — BREAKING: removed signal `optional`; added PACKET grouping layer
  (Interface -> Packets -> Signals); new signal field set; renamed
  `data_type`->`signal_type`; added `enum` type, `data_bits`/`xmit_bits`/
  `xmit_bytes`, free-text `definition`; removed `direction`/`encoding`.
- **1.4.0** — BREAKING: C header targets MISRA C:2012; DOCX+PDF render all
  signal fields in landscape.
- **1.5.0** — Permissive draft-ICD support + non-fatal WARNINGS channel.
  **BREAKING API: `loader.load()` returns a 3-tuple** `(model, hash, warnings)`.
  Details in section 9.
- **1.6.0 (current)** — Change control + diff reporting:
  (a) per-signal `pr_ticket` field (PR/change ticket that last touched a signal;
  non-fatal warning when missing on a post-Rev-A ICD);
  (b) `<priorRevisions>` linkage + `rev_summary.py`: the ICD document's revision
  table gains a **"Change Summary Report"** column, auto-computed by diffing the
  current ICD against each linked prior-revision source (Flow A — CLI via path
  links, web via per-revision just-in-time file upload);
  (c) a standalone **PDF diff report** for comparing two arbitrary files
  (`gen_diff_pdf.py`, CLI `diff -o`, web `POST /api/diff-report`) (Flow B).
  Details in section 9.5.
- **Post-1.6.0 work (no version bump):**
  * **reqgen** added as a separate sibling tool (section 15).
  * Demo examples replaced with three revisions of one ICD,
    `ICD-EVTOL-AVS-200` (`icd_evtol_revA/B/C.xml`); old `icd_demo*` /
    `icd_example` files removed.
  * Schema single-sourcing fix — applied.
  * **icdgen release gate:** `--strict` on `validate`/`generate` turns warnings
    fatal; run.log records the compiled-XSD hash, the template dir, and a
    per-template hash manifest (`ICDGEN_TEMPLATE_DIR` override is auditable).
  * **Traceability matrix gains a PR Ticket column** (`gen_trace.py`).
  * **C-header macro sanitization + Simulink quote escaping** in `gen_code.py`.
  * **reqgen applicability + traceability matrix** (`config_schema.AspectSpec.
    requires`, `reqgen/reqgen/trace.py`, CLI `reqgen trace`).
  * **reqgen traceability matrix UI** — backend `POST /api/reqgen/trace` (JSON)
    and `POST /api/reqgen/trace.csv` (download); the Requirements tab shows a
    coverage strip + matrix table and a "Download trace matrix (CSV)" button
    (section 9.7).
  * **granularity-aware L3 aspect model** (port vs packet, section 9.6): port
    aspects (`CONNECT`, `BUS`, `DAL`) for the interface contract, packet aspects
    (`EXISTS`, `RATE`, `DAL`) for the per-message layer; the generator, the
    config validator, and the editor all filter L3 aspects by granularity.
  * **reqgen editor state lifted into `App.jsx`** so the draft/preview/trace
    survive switching to the ICD Editor tab and back (section 10, "Tab
    persistence").
  * **icdweb prior-file path-traversal guard** (`service._safe_rev_token`).

---

## 2. What the system is

Three pieces sharing one core library:

1. **`icdgen/`** — the core Python library + CLI. Takes a single
   schema-validated XML/JSON ICD definition and deterministically generates: a
   Word ICD (`.docx`), a PDF ICD, a C header (MISRA C:2012-oriented), a Simulink
   bus script (`.m`), a traceability matrix (`.csv` + `.xlsx`), a version diff
   report (text/CSV/PDF). pip-installable and PyInstaller-packageable.
2. **`icdweb/`** — a web app over the core: FastAPI backend + React form editor,
   containerized with Docker. The editor authors interfaces/packets/signals in a
   form; validation, generation, and diff call straight into the core library.
   It also hosts the **reqgen config editor** as a second tab (config editing,
   live requirements preview, reconcile, and the requirements traceability
   matrix with a CSV download).
3. **`reqgen/`** — a separate, independently-qualifiable tool that imports
   icdgen as a library, reads its own version-controlled config, and emits an
   RM-tool requirements export, a requirements-to-signals traceability matrix,
   and a reconciliation report. Never mutates the ICD.

**Core value proposition:** one input file is the single source of truth; every
artifact is generated from it. **Identical input => byte-identical output**
(SHA-256 verified), which is what makes it usable as DO-330 tool-qualification
evidence. Domain: certifiable avionics ICDs under ARP4754A / DO-178C / DO-254.

---

## 3. Repository layout

```
<repo root>/
├── AI_README.md                  ← this file
├── TESTING.md                    (frozen at v1.2.0-era content; see section 14)
├── .dockerignore
│
├── icdgen/                       ← CORE library + CLI (pip-installable)
│   ├── pyproject.toml            packaging; EXACT-pinned runtime deps
│   ├── requirements.txt
│   ├── icdgen.spec               PyInstaller build spec (bundles the package
│   │                             copy of the XSD template)
│   ├── run.py / pyi_rth_docx.py  PyInstaller entry + runtime hook
│   ├── README.md                 (stale v1.2.0-era paths; see section 14)
│   ├── examples/
│   │   ├── icd_evtol_revA.xml          initial release (3 if / 3 pkt / 9 sig)
│   │   ├── icd_evtol_revB.xml          adds AHRS bus (4 if / 5 pkt / 16 sig);
│   │   │                               links revA  (XML comment says 18 — wrong)
│   │   └── icd_evtol_revC.xml      ★   current (6 if / 9 pkt / 31 sig); links
│   │                                   revB  (XML comment says 8 pkt / 33 sig
│   │                                   — both wrong; actual 9 pkt / 31 sig)
│   ├── tests/test_icdgen.py            targets the eVTOL examples
│   └── icdgen/                   ← the importable package
│       ├── __init__.py / __main__.py
│       ├── cli.py                argparse CLI: validate | generate | diff;
│       │                         --strict gate; run.log provenance closure
│       ├── fields.py        ★    SINGLE SOURCE OF TRUTH: SIGNAL_FIELDS +
│       │                         INTERFACE_FIELDS + data-type catalog + enums
│       ├── schema_gen.py    ★    derives XSD + JSON Schema from the registries
│       ├── signal_codec.py  ★    registry-driven Signal/Interface codecs +
│       │                         structural Packet codec
│       ├── model.py              frozen dataclasses incl. PriorRevision
│       ├── loader.py             validate + parse -> IcdModel; WARNINGS channel;
│       │                         parses <priorRevisions>
│       ├── serializer.py         IcdModel -> canonical XML (emits priorRevisions)
│       ├── provenance.py         tool/version/hash stamp (timestamp-free)
│       ├── resources.py          schema template + Jinja dir resolution;
│       │                         ICDGEN_TEMPLATE_DIR override; compiled_xsd_hash
│       │                         + template_manifest for run.log provenance
│       ├── gen_code.py           C header + Simulink .m (Jinja2); MISRA helpers;
│       │                         macro-name sanitizer + Simulink quote escape
│       ├── gen_docx.py           DOCX ICD; landscape; revision table has the
│       │                         "Change Summary Report" column
│       ├── gen_pdf.py            PDF ICD; same revision-table column
│       ├── gen_trace.py          traceability CSV + XLSX (incl. PR Ticket col)
│       ├── gen_diff_pdf.py       standalone PDF change report (Flow B)
│       ├── rev_summary.py   ★    per-revision change summaries (Flow A)
│       ├── diff.py               version diff engine + text/CSV reports
│       ├── ooxml_determinism.py  ZIP-normalizes .docx/.xlsx
│       ├── schemas/icd-1.0.xsd.template  ★ THE one XSD template (package data,
│       │                                  single source — cannot drift)
│       └── templates/header.h.j2, simulink_bus.m.j2
│
├── icdweb/                       ← WEB app (FastAPI + React)
│   ├── Dockerfile, docker-compose.yml, README.md
│   ├── backend/app/
│   │   ├── main.py               routes incl. /api/diff-report (PDF) and the
│   │   │                         reqgen editor routes (meta/config/preview/
│   │   │                         trace/trace.csv/reconcile)
│   │   ├── schemas.py            DTOs incl. prTicket + PriorRevisionDTO
│   │   ├── service.py            project storage; validate/generate/diff;
│   │   │                         _safe_rev_token path-traversal guard
│   │   ├── reqgen_service.py     thin orchestrator over reqgen: read/save the
│   │   │                         config, preview, trace (+CSV), reconcile
│   │   └── tests/test_api.py     backend tests (9; incl. rev-token guard)
│   └── frontend/src/
│       ├── App.jsx          ★    shell; OWNS the reqgen editor state so it
│       │                         persists across tab switches; both views are
│       │                         mounted (display toggled), never unmounted
│       ├── MetadataEditor.jsx, InterfaceEditor.jsx ★, PacketEditor.jsx,
│       ├── SignalTable.jsx ★, GeneratePanel.jsx
│       ├── DiffPanel.jsx         two-file compare -> downloads PDF report
│       ├── ReqgenPanel.jsx  ★    CONTROLLED view over App's reqgen state:
│       │                         config editor + live preview + reconcile +
│       │                         traceability matrix (table + CSV download)
│       ├── api.js                one fn per endpoint (incl. reqgenTrace +
│       │                         reqgenTraceCsv, diffReportPdf)
│       └── styles.css            avionics instrument-panel design system
│
└── reqgen/                       ← REQUIREMENT generator (separate tool)
    ├── pyproject.toml            packages = ["reqgen"]; depends on icdgen
    ├── README.md
    ├── config/reqgen.json        the config of record (committed)
    ├── tests/test_reqgen.py      tests (incl. applicability + 2 trace tests)
    └── reqgen/                   ← the importable package
        ├── __init__.py / __main__.py
        ├── cli.py                init | generate | trace | reconcile
        ├── paths.py              bakes config location (reqgen/config/reqgen.json)
        ├── config_schema.py ★    aspect registry + ReqConfig (single source);
        │                         AspectSpec.requires drives applicability
        ├── config_io.py          read/write/hash the config file
        ├── generate.py           ICD model + config -> Requirement objects;
        │                         skips inapplicable aspects (no vacuous reqs)
        ├── export.py             pluggable exporters (CSV today)
        ├── trace.py         ★    requirements-to-signals traceability matrix +
        │                         coverage summary (the completeness artifact)
        ├── reconcile.py          four-state diff vs a prior export
        └── provenance.py         dual-hash (ICD + config) stamp
```

> **Schema note.** The full XSD is assembled in memory at load time from the
> template + both registries (`resources.compiled_xsd()`); it cannot drift from
> the registries. The template itself exists as exactly ONE physical file
> (package data at `icdgen/icdgen/schemas/icd-1.0.xsd.template`), so it cannot
> drift across layouts either — one copy serves source checkouts, pip wheels,
> and PyInstaller bundles.
> **Filename casing:** `App.jsx` imports `./DiffPanel.jsx` (capital P); the file
> must be committed with that exact casing or the Linux Docker build fails to
> resolve the import (case-insensitive Windows/macOS hide this).

★ = the files that make "add a field/aspect in one place" work, plus the two
files that own the new reqgen UI state and trace matrix.

---

## 4. The field registry (the heart of maintainability)

**File: `icdgen/icdgen/fields.py`.** Every signal AND interface field is declared
once as a `FieldSpec`. The XSD, JSON Schema, form column/input, API descriptor,
XML/JSON serialization, parsing, CSV/XLSX columns, AND DOCX/PDF tables are all
derived from it.

- **Data-type catalog:** `DataTypeSpec` + `DATA_TYPES` (incl. `"enum"` ->
  C `int32_t`); derived `DATA_TYPE_NAMES`, `C_TYPE_MAP`, `SIMULINK_TYPE_MAP`.
- **Interface lists:** `BUS_TYPES` (suggestions only — freeform), `DAL_LEVELS`
  (enforced enum), `DIRECTIONS` (namespace stability).
- **`FieldSpec`:** name/xml_name/json_name/label, `py_type`, `xml_location`,
  `required`, `default`, `enum`/`enum_source`; validation hints `positive`,
  `min_inclusive`, `pattern`, `min_length`; UI hints `ui_width`, `ui_numeric`,
  `suggestions`; serialization `emit_if`.
- **SIGNAL_FIELDS order (= column order everywhere):** name, description,
  signal_type, update_rate_hz, units, data_bits, xmit_bits, xmit_bytes, scaling,
  definition, range_min, range_max, offset, **pr_ticket** (1.6.0, appended).
- **INTERFACE_FIELDS:** id, bus_type, dal, name, source_lru, destination_lru,
  owning_document, description. `<packets>` is structural, not in the registry.
- **Descriptors** (`signal_fields_descriptor()` / `interface_fields_descriptor()`)
  feed `/api/meta/options`; the React form builds itself from them.

**Schema derivation — `schema_gen.py`:** generic over a registry + prefix
(`Sig`/`If`). Optional enum fields also accept `""`; pattern values are emitted
via `quoteattr()` so a quote-containing regex can't break the XSD.

---

## 5. Domain model — `icdgen/icdgen/model.py`

`IcdModel -> Interface -> Packet -> Signal`, all frozen.
- `Signal` — registry-backed; permissive optional defaults (`signal_type=""`,
  `update_rate_hz/range_min/range_max=None`, ... `pr_ticket=None`). Properties:
  `has_concrete_type`, `c_type` (placeholder `uint8_t` when blank),
  `simulink_type`.
- `Packet` — structural (name, signals, optional description).
- `Interface` — registry scalars + packets tuple.
- `PriorRevision(revision, source)` — maps a revision letter to the source file
  that defined the ICD at that revision (Flow A). Structural.
- `IcdModel(... , prior_revisions=())` + `all_signals()` triple iterator.

---

## 6. Codecs — `signal_codec.py`

Registry-driven movement (`_coerce` -> None becomes `spec.default`, so optional
numerics arrive as `None`). Signal/Interface/Packet to-from XML/JSON/dict.
`serializer.to_xml(model)` is the inverse of the loader and the single source of
truth for the wire format; it emits `<priorRevisions>` when present.

---

## 7. Loading & validation — `loader.py`

- **FATAL** -> `ValidationError(message, line, source)`: XML/JSON syntax, XSD/
  jsonschema violation, unsupported schemaVersion, duplicate id/packet/signal,
  `rangeMin > rangeMax` (when both present).
- **NON-FATAL** -> `list[ValidationWarning]`: blank `signal_type`; signal name
  not a valid C identifier; **missing `pr_ticket` on a signal when the ICD
  revision is not "A"** (change-control reminder). NOTE: carried-over signals
  legitimately have no ticket, so these warnings are expected on revB/revC.
- `load(path) -> (IcdModel, sha256_hex, list[ValidationWarning])` (3-tuple).
- Parses `<priorRevisions>` (XML + JSON).

---

## 8. Data flow

Web authoring -> DTO -> save; debounced validate -> `(errors, warnings)`.
Generate -> serialize to canonical `*.source.xml` -> hash -> `Provenance` ->
`ARTIFACT_BUILDERS`. CLI mirrors the same core. Generators iterate
`model.all_signals()`; C header/Simulink emit one struct/Bus per PACKET;
DOCX/PDF render the signal table per packet plus the revision table with the
Change Summary Report column. reqgen consumes the same `IcdModel` as a library
input and emits requirements / a trace matrix / a reconciliation report.

---

## 9. What 1.5.0 changed (permissive drafts + warnings)

Five relaxations: busType freeform (suggestions kept); signalType optional/blank;
updateRateHz optional + non-negative; signal-name pattern relaxed to `[^\s"'<>]+`
(warns if not a valid C identifier); rangeMin/rangeMax optional. Warnings channel
runs core -> CLI (stderr, exit 0) -> backend (`warnings: [{message, line}]` on
`/validate`, `/generate`, `/import`) -> frontend (amber count, lists). Backend
DTOs are intentionally loose; only `Dal` stays a `Literal`. `load()` is a 3-tuple
(breaking).

## 9.5. What 1.6.0 changed (change control + diff reporting)

### Flow A — per-revision Change Summary Report (inside the ICD document)
- `<priorRevisions>` block maps `revision -> source` file:
  ```xml
  <priorRevisions><priorRevision revision="B" source="icd_evtol_revB.xml"/></priorRevisions>
  ```
- `rev_summary.compute_revision_summaries(model, base_dir, mode="pr")` runs the
  diff engine against each linked prior source. Rev A -> "Initial release"; a
  revision with no linked source -> short note; never raises. **`mode` selects
  the cell wording:** `"pr"` (default) groups changes by the PR/change ticket
  that made them (added/modified use the NEW signal's `pr_ticket`; removed uses
  the OLD signal's; untagged -> "(no ticket)"; a modification whose ONLY change
  was the ticket is dropped); `"detailed"` itemizes per-signal lines; `"counts"`
  gives aggregate counts.
- `gen_docx`/`gen_pdf` render this as the **"Change Summary Report"** column in
  the revision-history table. Both builders take `base_dir`.
- **Web app (just-in-time upload).** The revision-history table in
  `MetadataEditor.jsx` has a per-row "Baseline file" upload; the frontend holds
  a transient `{revisionLetter: content}` map in `App.jsx` (NOT saved) and
  `GeneratePanel` passes it as `priorFiles` on generate. The backend
  `service.generate(..., prior_files=...)` writes each into the output dir as a
  hidden temp file (filename sanitized — see section 14 path-traversal note),
  attaches a synthetic `PriorRevision`, generates with `base_dir=out`, then
  deletes the temp files.

### Per-signal `pr_ticket`
- New last signal field (`<prTicket>` / `prTicket`, label "PR Ticket"); freeform;
  appended so all derived outputs (incl. the traceability matrix "PR Ticket"
  column) pick it up. Optional. Non-fatal warning when missing on a post-Rev-A
  ICD (gate is `revision not in {"", "A"}`, case-insensitive).

### Flow B — standalone two-file diff PDF report
- `gen_diff_pdf.build_diff_pdf(...)` renders a `DiffResult` into a deterministic
  PDF (header with both input SHA-256s + a counts summary, then Interface /
  Added / Removed / Modified sections).
- **CLI:** `icdgen diff old new -o DIR` writes `*_diff.txt/.csv/.pdf`.
- **Web:** `POST /api/diff-report` streams the PDF; a parse failure on either
  side returns HTTP 400 naming the side. `DiffPanel.jsx` is the download-only
  two-file form.

## 9.6. reqgen L3 aspect model: port (interface) vs packet (message) granularity

The L3 (interface) requirement layer is **granularity-aware**, reflecting the
ICD hierarchy itself. An ICD defines two distinct kinds of structural fact, and
they live at different layers (ARP4754A / standard ICD practice — the interface
is the physical+protocol+connectivity contract between two LRUs; the messages
are the data carried on it):

- **port granularity** — one L3 requirement *per interface*. These transcribe
  the interface/port contract: which two LRUs it connects, which bus/protocol it
  conforms to, and the DAL allocated to it. They are properties of the
  interface, not of any one message (e.g. an ARINC 429 bus has one wire speed
  for the whole bus; a CAN port connects a fixed source and destination).
- **packet granularity** — one L3 requirement *per packet*. These transcribe the
  per-message layer: the packet exists on the interface, and its refresh rate.
  Refresh rate is a per-message property (each ARINC 429 label has its own
  transmit interval even though the bus speed is fixed), so RATE is a packet
  aspect and is meaningless for a port.

Each L3 `AspectSpec` declares a `granularity` (`"port"`, `"packet"`, or
`"both"`). `generate.py` only emits an L3 aspect when its granularity matches
the active `l3_granularity`, so:

| Aspect    | Level | Granularity | Transcribes |
|-----------|-------|-------------|-------------|
| `CONNECT` | L3    | port        | `iface`, `source_lru`, `destination_lru` — "shall convey data from X to Y" |
| `BUS`     | L3    | port        | `iface`, `bus_type` — "shall be implemented on a {bus_type} bus" |
| `EXISTS`  | L3    | packet      | `iface`, `packet`, `bus_type` — "shall provide the {packet} packet over {bus_type}" |
| `RATE`    | L3    | packet      | `iface`, `packet`, `update_rate_hz` — "shall transmit {packet} at {rate} Hz" (off by default) |
| `DAL`     | L3    | both        | `iface`, `dal` — allocated to the interface; valid in either mode |

This corrects the prior model, where `RATE` (a message concept) was offered for a
port and the only port option produced a blank-packet `EXISTS` ("provide the
 packet"). The change is enforced at three layers so it is correct for every
caller, not just the UI: (1) `config_schema.aspect_valid_at` / `l3_aspects_for`
define validity; (2) `generate._resolve_l3_aspects` filters by the active
granularity; (3) `config_io._validate` **rejects** a config whose enabled L3
set (or an interface override's `l3_aspects`) contains an aspect invalid at its
granularity — so a "port" config listing `RATE` is a clear ConfigError, not a
silent no-op. The descriptor exposes `granularity` per aspect plus
`l3AspectsByGranularity` / `defaultL3AspectsByGranularity`, so the editor shows
only the aspects meaningful at the chosen granularity and re-seeds the enabled
set when the user flips it. L4 (signal) aspects are unaffected by granularity.

The default config is unchanged (packet granularity, `l3_aspects=[EXISTS, DAL]`),
so existing configs and their hashes are not disrupted.

## 9.7. reqgen requirements traceability matrix (the requirements document)

The requirements deliverable is a **requirements-to-signals traceability
matrix**, produced by `reqgen/reqgen/trace.py` and surfaced everywhere:

- **Module (`trace.py`).** `build_trace_rows(model, reqs)` emits one `TraceRow`
  per L3 element (interface/packet — per packet, or per interface for port
  granularity, auto-detected from a blank packet name) and one per signal (L4),
  in document order, each carrying the sorted list of requirement IDs that
  cover it. `render_trace_csv(model, reqs, prov)` serializes it (columns:
  Interface ID, Packet, Signal, Level, Covering Requirement IDs (`;`-joined),
  Requirement Count, Coverage [COVERED/NOT COVERED], ICD SHA-256, Config
  SHA-256). `coverage_summary(rows)` returns per-level total/covered/uncovered.
  An element with no covering requirement (all aspects suppressed, or skipped by
  applicability — e.g. a signal with no declared range) is **NOT COVERED**, a
  visible gap to close with a human-authored requirement, never silent.
- **Join key.** `(Interface ID, Packet, Signal)` is shared with icdgen's
  traceability matrix, so the two CSVs join into end-to-end
  signal → requirement → LRU/DAL/owning-document traceability without coupling
  the two tools' qualification scopes. Requirement ID is the RM-tool join key.
- **CLI.** `reqgen trace <icd> -o DIR` writes `<docid>_req_trace.csv`, prints
  per-level coverage to stderr, and exits **2** on any NOT COVERED gap (CI gate,
  mirroring `icdgen diff`'s changes-found convention), **1** on input error.
- **Web (download + on-screen).** Backend `reqgen_service.trace(payload)`
  returns rows + summary for the table; `reqgen_service.trace_csv(payload)`
  renders the CSV for download. Routes: `POST /api/reqgen/trace` (JSON) and
  `POST /api/reqgen/trace.csv` (attachment). The Requirements tab renders a
  coverage strip (L3 x/y, L4 x/y, gap count), a filterable matrix table
  (All rows / Gaps only), and a **"Download trace matrix (CSV)"** button. The
  download uses the ICD hash from the chosen source and the draft config hash,
  so the CSV's provenance matches the previewed matrix.
- **Applicability (no vacuous requirements).** `config_schema.AspectSpec.requires`
  declares which ICD fields must be present for an aspect to emit (RANGE needs
  both bounds, TYPE a type, RATE a rate, UNITS units). `generate.py` skips an
  aspect whose required fields are blank instead of emitting "range [, ]"; the
  skipped element then shows as a trace-matrix gap. This is what makes the trace
  matrix the completeness artifact rather than a rubber stamp.

---

## 10. The web layer

`main.py` routes: health; `/api/meta/options`; projects CRUD; `/validate`;
`/generate` (accepts optional `priorFiles: {rev: text}` for Flow A); artifact
download; `export.xml`; `/import`; `/diff` (JSON); `/diff-files` (JSON);
`/diff-report` (PDF download); and the reqgen editor routes — `/api/reqgen/meta`,
`/api/reqgen/config` (GET/PUT), `/api/reqgen/preview`, `/api/reqgen/trace`,
`/api/reqgen/trace.csv`, `/api/reqgen/reconcile`. `schemas.py` DTOs incl.
`prTicket` and `PriorRevisionDTO`/`IcdDTO.priorRevisions`. `service.py` is the
only file touching ICD-project storage; `reqgen_service.py` is the only file
orchestrating reqgen (it never holds config state — the file is the record of
truth). Frontend builds all inputs from registry descriptors.

### Tab persistence (reqgen state lives in App)
The app has two tabs (ICD Editor / Requirements). To keep the reqgen draft,
chosen ICD source, preview, reconcile, and trace from being lost when the user
flips to the ICD Editor and back:
- **State is lifted into `App.jsx`** as a single `reqgen` object, passed to
  `ReqgenPanel` via `state` + `patch` props. `ReqgenPanel` is a *controlled*
  view — it has no `useState` for any of that data (only ephemeral `saving`/
  `busy` flags). The bootstrap fetch (meta + config) is guarded by a `loaded`
  flag so it runs exactly once.
- **Both views are always mounted** in `App` (`display: none` on the inactive
  one) rather than conditionally rendered, so React never unmounts the reqgen
  subtree. Lifting alone would preserve the data; keeping it mounted also
  preserves un-lifted local UI bits (scroll position, the trace All/Gaps
  toggle). The two together are why nothing is lost on a tab switch.

---

## 11. Determinism contract (must never regress)

Identical input => byte-identical artifacts. No timestamps in artifacts
(`run.log` is the only wall-clock place). PDF: `rl_config.invariant=1` (covers
the ICD PDF AND the diff PDF). OOXML: pinned epoch + ZIP normalization. Registry
order fixes column order. The reqgen CSV exports and the trace matrix are
deterministic (document order, no timestamps, dual-hash provenance per row).
Guard tests + determinism tests in `tests/test_icdgen.py`. Re-verify the byte
baseline after any core change.

**Re-baseline note:** the PR Ticket column changed the trace-csv / trace-xlsx
artifact bytes relative to pre-PR-Ticket baselines. The C-header sanitizer and
the Simulink quote escape are no-ops on clean names (current examples), so those
bytes are unchanged — but re-verify across all artifacts after merging.

---

## 12. How to make common changes (recipes)

- **New SIGNAL field:** one `FieldSpec` in `fields.py` (append) + one attr in
  `model.py`. Flows to schema, codec, UI, traceability, DOCX/PDF tables. The
  traceability matrix uses an explicit column list in `gen_trace.py`, so add the
  column there too. C-header macros are human-curated in `header.h.j2`.
- **New DATA TYPE:** one `DataTypeSpec` in `fields.py` (+ `_UNSIGNED_TYPES`/
  `_LONGLONG_TYPES` in `gen_code.py` if needed).
- **New ARTIFACT format:** generator in `icdgen/` + one entry in
  `service.ARTIFACT_BUILDERS` + `_write_*` shim; for the CLI add to
  `cli.ALL_FORMATS` + a branch in `cmd_generate`.
- **New INTERFACE field:** one `FieldSpec` + one `Interface` attr (+ DTO type if
  strict). Keep `<packets>` structural.
- **PACKET fields:** edit `PacketType` (XSD template), `loader._json_schema`,
  `Packet`, the packet codec fns, `PacketDTO`, `PacketEditor.jsx`.
- **New VALIDATION rule:** schema-expressible -> a `FieldSpec` facet; cross-field
  -> `loader._semantic_checks` (raise for fatal, append `ValidationWarning` for
  non-fatal).
- **Custom C header / Simulink templates:** copy `icdgen/icdgen/templates/` to a
  program directory, edit, set `ICDGEN_TEMPLATE_DIR=/path`. run.log records the
  directory and per-template hashes, so the customization is under provenance.
- **Release gate:** run `icdgen validate|generate ... --strict` so any warning
  is fatal and nothing ships with open warnings.
- **Change the revision summary wording / grouping:** `rev_summary.py`.
- **Restyle the diff PDF:** `gen_diff_pdf.py` (one file, self-contained).
- **New schema version:** add `icd-1.1.xsd.template` beside the 1.0 one (inside
  the package `schemas/` dir), register in `loader.SUPPORTED_SCHEMA_VERSIONS`,
  keep 1.0 working.
- **New API endpoint:** `service.py` (or `reqgen_service.py`) fn + thin `main.py`
  route + `api.js` method.
- **New reqgen aspect:** one `AspectSpec` in `reqgen/config_schema.py`; set
  `requires=` if the aspect's template is only meaningful when certain fields
  are present (drives applicability + trace-matrix coverage).
- **New reqgen UI feature over App-owned state:** add a slice to the `reqgen`
  object in `App.jsx` and a `patch({...})` call in `ReqgenPanel.jsx`; do NOT add
  `useState` in the panel for anything that must survive a tab switch.

---

## 13. Build / run / test quick reference

- **Install (core):** `pip install -e ./icdgen`
- **Core tests:** `cd icdgen && python -m pytest tests/ -q`
  (targets the eVTOL examples; `test_pr_ticket_in_traceability` checks the PR
  Ticket column.)
- **Backend tests (9):**
  `cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/t python -m pytest tests/ -q`
  (includes `test_prior_file_revision_key_cannot_escape_output_dir`.)
- **reqgen tests (~22):**
  `cd icdgen && PYTHONPATH=../reqgen python -m pytest ../reqgen/tests/ -q`
  (includes the applicability test, the L3 port/packet granularity tests,
  and the trace-matrix tests.)
- **Frontend build:** `cd icdweb/frontend && npm install && npm run build`
- **Docker (from repo root):**
  `docker compose -f icdweb/docker-compose.yml up --build` -> http://localhost:8000
- **CLI (icdgen):**
  - `python -m icdgen validate examples/icd_evtol_revC.xml [--strict]`
  - `python -m icdgen generate examples/icd_evtol_revC.xml -o out [--strict]`
  - `python -m icdgen diff examples/icd_evtol_revB.xml examples/icd_evtol_revC.xml -o out`
- **CLI (reqgen):** `reqgen init` then
  `reqgen generate icdgen/examples/icd_evtol_revC.xml -o out` then
  `reqgen trace icdgen/examples/icd_evtol_revC.xml -o out` then
  `reqgen reconcile icdgen/examples/icd_evtol_revC.xml out/ICD-EVTOL-AVS-200_requirements.csv`
- **Determinism check:** generate twice, compare SHA-256 of all artifacts (skip
  `run.log`). Re-baseline the trace artifacts after the PR Ticket change.

### Backend env vars
`ICDGEN_DATA_DIR` (`/data`), `ICDGEN_STATIC_DIR` (`/app/static`),
`ICDGEN_CORS_ORIGINS` (`*`), `PORT` (`8000`), `ICDGEN_TEMPLATE_DIR` (optional
Jinja override), `REQGEN_CONFIG` (optional config-of-record path).

---

## 14. Known boundaries / not yet built (intentional)

- **No auth / multi-tenancy.** Projects are global.
- **Flat-directory storage** under `ICDGEN_DATA_DIR`; `service.py` is the only
  ICD-project storage-touching file.
- **No job queue.** Generation is synchronous.
- **Deps EXACT-pinned;** bump -> re-run determinism check.
- **MISRA compliance is checker-confirmed,** not self-certified.
- **Permissive signal-name pattern;** C-identifier enforcement is warning-only.
  C-header macro names are sanitized; struct FIELD names stay raw (the
  non-C-identifier warning covers them).
- **Flow A works in BOTH paths.** CLI: `priorRevisions` path links. Web:
  per-revision baseline upload, passed just-in-time as `priorFiles` (transient).
  The web prior-file revision key is sanitized (`service._safe_rev_token`,
  regex `[^A-Za-z0-9_-]→_`, empty→`_`) before composing the temp filename, so a
  malicious key like `/../../X` cannot write outside the project out/ dir; the
  `PriorRevision` keeps the original revision string for summary matching.
- **reqgen exporters:** CSV only so far; ReqIF / tool-specific pending the
  target RM tool. The reqgen UI exists for config editing, preview, reconcile,
  and the trace matrix; it remains a *view* over the config file, never a second
  source of state.
- **Hash-semantics inconsistency (flagged, not changed):** CLI `diff` hashes raw
  input bytes; web `/api/diff-report` and `service.generate` hash canonical
  serialized XML. Pick one policy and document it before relying on cross-path
  hash equality.
- **diff move detection:** a moved signal reports as removed+added (no rename
  detection yet).
- **`diff.py` pr_ticket-only modifications:** counted in the Flow B PDF while
  Flow A's summary suppresses them; a shared policy flag would unify them.
- **Example XML header comments overstate counts** (revB comment says 18 sigs,
  actual 16; revC says 33, actual 31) — fix the comments; the code counts are
  correct.
- **`TESTING.md` and `icdgen/README.md` are frozen at v1.2.0-era content**
  (icd_demo paths, wrong counts, `schemas/icd-1.0.xsd` path) — rewrite.
- **JSON date parity:** XML validates `revisionDate`/`date` as `xs:date`; the
  JSON path accepts any string.
- **`gen_pdf._REL_WIDTH`** has no `pr_ticket` entry (silently defaults 1.0);
  consider moving rel-width onto `FieldSpec` as `doc_rel_width`.

---

## 15. reqgen (requirement generator)

Separate tool, separate qualification scope. Imports icdgen as a library; reads
its own config; emits a requirements export, a requirements-to-signals trace
matrix, and a reconciliation report. Never writes to the ICD.

- **`config_schema.py`** — schema lives in code: an `ASPECTS` registry of
  structural requirement types. L3 splits by granularity (port: `CONNECT`,
  `BUS`, `DAL`; packet: `EXISTS`, `RATE`, `DAL`); L4: `TYPE`, `RANGE`, `SCALE`,
  `UNITS`) + the `ReqConfig` dataclass. Each `AspectSpec` declares `fields` (the
  ICD attrs it may transcribe = its allowed `{placeholders}`), `requires` (the
  fields that must be non-blank for it to emit), and — for L3 — `granularity`
  (`port` / `packet` / `both`, see section 9.6). Helpers `aspect_valid_at`,
  `l3_aspects_for`, `default_l3_aspects_for`. **Bright line:** templates
  substitute ONLY ICD field values; behavioral requirements stay human-authored
  in the RM tool, linked by ID.
- **`config_io.py`** — read/write/hash the config file; `ensure_config` writes a
  populated default if absent; `save_config` is the only writer and the place
  the bright line AND the L3 granularity-consistency rule are enforced
  (`config_from_dict` validates a posted draft without writing — used by the web
  preview/trace/save path; rejects an L3 aspect that does not fit the configured
  granularity).
- **`paths.py`** — bakes the config location: `reqgen/config/reqgen.json`.
  `$REQGEN_CONFIG` overrides.
- **`generate.py`** — walks the ICD, emits `Requirement` objects with stable IDs
  derived from ICD structure. Precedence: per-signal -> per-interface -> global
  -> aspect default. Applicability (`_applicable` via `AspectSpec.requires`)
  skips inapplicable aspects so no vacuous requirements are produced. L3 layer:
  `_resolve_l3_aspects` filters enabled aspects to those valid at the active
  `l3_granularity` ("packet" -> one row per packet; "port" -> one row per
  interface). `_raw_field_values` now also supplies the port-contract fields
  (`source_lru`, `destination_lru`, `owning_document`) for the port aspects.
- **`export.py`** — pluggable `EXPORTERS` registry; CSV today.
- **`trace.py`** — the requirements-to-signals traceability matrix + coverage
  summary (section 9.7). The completeness-evidence artifact.
- **`reconcile.py`** — four-state diff (added/removed/changed/unchanged) of a
  fresh generation vs a prior export CSV.
- **`provenance.py`** — dual-hash anchor: reqgen version + ICD SHA-256 + config
  SHA-256.
- **CLI:** `reqgen init | generate <icd> -o DIR | trace <icd> -o DIR |
  reconcile <icd> <prior.csv>`. `trace` exits 2 on coverage gaps.
- **Layout guard:** `pyproject.toml` declares `packages = ["reqgen"]`;
  `test_package_is_properly_nested` guards the double-nesting in CI.

---

## 16. Next steps (priority order)

1. **Generate-then-verify architecture for DO-330 Criteria 3:** a small,
   separately-qualified verifier that re-parses each generated artifact against
   the ICD (determinism ≠ correctness; this closes the "the generator is also
   the checker" gap).
2. **ARINC 429 word-layout fields** (label / SDI / SSM / start bit) in the
   signal registry — prerequisite for the planned autocoder.
3. **Semantic consistency checks** (data_bits ≤ xmit_bits, xmit_bytes*8 ≥
   xmit_bits, range representable under type/scaling/offset) as new
   `loader._semantic_checks` warnings.
4. **TOR mapping:** pytest markers -> a TOR coverage CSV, so the test suite maps
   to the qualification Tool Operational Requirements.
5. **ReqIF / tool-specific reqgen exporter** — blocked on naming the target RM
   tool (DOORS / Jama / Polarion / etc.).
6. **Fix the doc debt:** rewrite `TESTING.md` and `icdgen/README.md`; correct
   the revB/revC example XML header comment counts (16 and 31).
7. **Unify the hash-semantics policy** (raw bytes vs canonical XML) across the
   CLI diff and the web paths, and document it.
8. **Optional:** fold the template-set hash into `Provenance.footer_line()` at
   the next major re-baseline (tri-hash stamp, symmetric with reqgen's dual
   hash); add move detection to `diff.py`.