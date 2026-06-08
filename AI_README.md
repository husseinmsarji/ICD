# AI_README — icdgen / reqgen / icdweb architecture map

> **Purpose of this file.** This is the single document to paste back to Claude
> (or hand to any engineer) when requesting changes. It describes every file,
> its responsibilities, the key functions/classes, the data flow, the invariants
> that must hold, and the recipes for common changes — so source files do not
> need to be re-sent to understand the system.
>
> **Maintenance rule.** This file is regenerated/updated at the end of every
> change so it always matches the code. Treat it as the source of truth for
> "what version are we on and how is it built." If this file and the code
> disagree, **the code wins** and this file must be corrected.

---

## 0. ⚠️ LIVE ISSUE TO FIX FIRST — test suite references deleted example files

**Status: OPEN in the current tree.** The schema-template stale bug (the
previous section-0 item) is **RESOLVED** — see section 0.1. The remaining live
problem is a leftover from the GitHub restore: `tests/test_icdgen.py` still
points at example files that no longer exist.

**Symptom.** `cd icdgen && python -m pytest tests/ -q` errors during
collection / at runtime with `FileNotFoundError` (or a failing `open(...)`)
because three referenced files are gone:
- line 21:  `EX_XML = os.path.join(ROOT, "examples", "icd_example.xml")`
- line 350: `demo = os.path.join(ROOT, "examples", "icd_demo.xml")`
- line 351: `revd = os.path.join(ROOT, "examples", "icd_demo_revD.xml")`

The `examples/` dir now contains ONLY `icd_evtol_revA.xml`, `icd_evtol_revB.xml`,
and `icd_evtol_revC.xml`. The old `icd_demo*` / `icd_example` files were removed
when the eVTOL examples were put in place, but the test file's references were
not updated (the restore reverted the test edits while keeping — or
re-receiving — the eVTOL examples).

**The fix (apply next):** re-point the tests at the eVTOL examples.
1. `EX_XML` → `examples/icd_evtol_revA.xml` (the single-interface baseline that
   stands in for the old `icd_example.xml`). NOTE: revA has **3** interfaces, not
   1 — so `test_valid_xml_loads`'s `assert len(model.interfaces) == 1` must
   become `== 3`. Audit every `EX_XML`-based assertion (interface/packet/signal
   counts, the `if_nav_state_position_t` struct-name check still holds since
   revA keeps `IF-NAV-STATE` / `POSITION`).
2. `test_diff_pdf_report_builds_and_is_deterministic`: `demo` → `icd_evtol_revB.xml`,
   `revd` → `icd_evtol_revC.xml` (a real B→C diff with adds/removes/mods).
3. `test_diff_pdf_report_no_changes` uses `EX_XML` diffed against itself — fine
   once `EX_XML` resolves.
4. Re-confirm the expected count after the edits (was 36 with the old examples
   + the now-removed `test_schema_template_copies_in_sync`; recount after the
   re-point — see section 13).

Until this is done the icdgen suite cannot run to completion.

### 0.1. RESOLVED — XSD template drift ("stale schema") single-sourced
The recurring `Element '{urn:icdgen:icd:1.0}priorRevisions': This element is not
expected.` failure is **fixed**. The XSD template now exists as exactly ONE
physical file — package data at `icdgen/icdgen/schemas/icd-1.0.xsd.template`.
What changed:
- `resources.xsd_template_path()` resolves ONLY the package copy
  (`here/schemas/icd-1.0.xsd.template`), plus the `sys._MEIPASS/icdgen/schemas/`
  path for a PyInstaller bundle. The old repo-root candidate and the `_base_dir`
  helper are gone.
- The repo-root `icdgen/schemas/icd-1.0.xsd.template` and the (now-empty)
  `icdgen/schemas/` dir were deleted.
- `icdgen.spec` bundles `('icdgen/schemas/icd-1.0.xsd.template',
  'icdgen/schemas')` (the old stale `('schemas/icd-1.0.xsd', 'schemas')` line is
  gone).
- `pyproject.toml [tool.setuptools.package-data]` ships `schemas/*.template`
  (the dead `schemas/*.xsd` glob and the two-layout comment were removed).
- `test_schema_template_copies_in_sync` was removed from `tests/test_icdgen.py`
  (one copy → nothing to drift).

The manual `copy icdgen\icdgen\schemas\... icdgen\schemas\...` workaround is no
longer needed and must not be reintroduced. The "Schema note" in section 3 is
now literally true: the template cannot drift, because there is only one.

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
- **1.4.0** — BREAKING: C header targets MISRA C:2012; DOCX+PDF render all 13
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
    `icd_example` files removed. **PRESENT in the current tree.**
  * Schema single-sourcing fix (section 0.1) — **APPLIED in the current tree.**
  * **NOT yet done:** the test file's example references still point at the
    removed `icd_demo*`/`icd_example` files — the live open item (section 0).

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
3. **`reqgen/`** — a separate, independently-qualifiable tool that imports
   icdgen as a library, reads its own version-controlled config, and emits an
   RM-tool requirements export + reconciliation report. Never mutates the ICD.

**Core value proposition:** one input file is the single source of truth; every
artifact is generated from it. **Identical input => byte-identical output**
(SHA-256 verified), which is what makes it usable as DO-330 tool-qualification
evidence. Domain: certifiable avionics ICDs under ARP4754A / DO-178C / DO-254.

---

## 3. Repository layout

```
<repo root>/
├── AI_README.md                  ← this file
├── TESTING.md
├── .dockerignore
│
├── icdgen/                       ← CORE library + CLI (pip-installable)
│   ├── pyproject.toml            packaging; EXACT-pinned runtime deps
│   ├── requirements.txt
│   ├── icdgen.spec               PyInstaller build spec (bundles the package
│   │                             copy of the XSD template)
│   ├── run.py / pyi_rth_docx.py  PyInstaller entry + runtime hook
│   ├── README.md
│   ├── examples/
│   │   ├── icd_evtol_revA.xml          initial release (3 if / 3 pkt / 9 sig)
│   │   ├── icd_evtol_revB.xml          adds AHRS bus; links revA
│   │   └── icd_evtol_revC.xml      ★   current (6 if / 8 pkt / 31 sig); links revB
│   ├── tests/test_icdgen.py            ⚠ still references deleted icd_demo* /
│   │                                   icd_example files (section 0)
│   └── icdgen/                   ← the importable package
│       ├── __init__.py / __main__.py
│       ├── cli.py                argparse CLI: validate | generate | diff
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
│       ├── resources.py          schema template + Jinja dir resolution
│       │                         (single-source: package copy + MEIPASS only)
│       ├── gen_code.py           C header + Simulink .m (Jinja2); MISRA helpers
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
│   (NOTE: the old repo-root icdgen/schemas/ dir and its template copy were
│    DELETED by the single-sourcing fix. Do not recreate them.)
│
├── icdweb/                       ← WEB app (FastAPI + React)
│   ├── Dockerfile, docker-compose.yml, README.md
│   ├── backend/app/
│   │   ├── main.py               routes incl. /api/diff, /api/diff-files,
│   │   │                         /api/diff-report (PDF download)
│   │   ├── schemas.py            DTOs incl. prTicket + PriorRevisionDTO
│   │   └── service.py            project storage; validate/generate/diff
│   │   └── tests/test_api.py     8 tests (⚠ see section 13 re: icd_demo refs)
│   └── frontend/src/
│       ├── App.jsx               shell; renders DiffPanel (open + empty states)
│       ├── MetadataEditor.jsx, InterfaceEditor.jsx ★, PacketEditor.jsx,
│       ├── SignalTable.jsx ★, GeneratePanel.jsx
│       ├── DiffPanel.jsx         two-file compare -> downloads PDF report
│       ├── api.js                one fn per endpoint (incl. diffReportPdf)
│       └── styles.css            avionics instrument-panel design system
│
└── reqgen/                       ← REQUIREMENT generator (separate tool)
    ├── pyproject.toml            packages = ["reqgen"]; depends on icdgen
    ├── README.md
    ├── config/reqgen.json        the config of record (committed)
    ├── tests/test_reqgen.py      tests (⚠ see section 13 re: icd_demo refs)
    └── reqgen/                   ← the importable package
        ├── __init__.py / __main__.py
        ├── cli.py                init | generate | reconcile
        ├── paths.py              bakes config location (reqgen/config/reqgen.json)
        ├── config_schema.py ★    aspect registry + ReqConfig (single source)
        ├── config_io.py          read/write/hash the config file
        ├── generate.py           ICD model + config -> Requirement objects
        ├── export.py             pluggable exporters (CSV today)
        ├── reconcile.py          four-state diff vs a prior export
        └── provenance.py         dual-hash (ICD + config) stamp
```

> **Schema note.** The full XSD is assembled in memory at load time from the
> template + both registries (`resources.compiled_xsd()`); it cannot drift from
> the registries. The template itself now exists as exactly ONE physical file
> (package data at `icdgen/icdgen/schemas/icd-1.0.xsd.template`), so it cannot
> drift across layouts either — one copy serves source checkouts, pip wheels,
> and PyInstaller bundles. (This was the section-0 stale bug; it is fixed.)
> **Filename casing:** `App.jsx` imports `./DiffPanel.jsx` (capital P); the file
> must be committed with that exact casing or the Linux Docker build fails to
> resolve the import (case-insensitive Windows/macOS hide this).

★ = the files that make "add a field in one place" work.

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
DOCX/PDF render the 13-column signal table per packet plus the revision table
with the Change Summary Report column.

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
  diff engine against each linked prior source and returns a per-revision
  summary. Rev A -> "Initial release"; a revision with no linked source -> short
  note; never raises. **`mode` selects the cell wording:**
    * `"pr"` (default) — group every change by the PR/change ticket that made
      it, listing signal names: e.g.
      `AVS-1101: +vel_north; +vel_east | AVS-1110: ~torque_limit (range_max) | (no ticket): +interface IF-ENV; -bms_fault`.
      Attribution: added/modified use the NEW signal's `pr_ticket`; removed uses
      the OLD signal's `pr_ticket`; untagged -> "(no ticket)". The `pr_ticket`
      field is suppressed from a modified signal's listed fields, and a
      modification whose ONLY change was the ticket is dropped (so persisting a
      carried-over ticket on an unchanged signal produces no spurious diff).
    * `"detailed"` — itemized per-signal lines, no ticket grouping.
    * `"counts"` — compact aggregate counts.
- `gen_docx`/`gen_pdf` render this as the **"Change Summary Report"** column in
  the revision-history table. Both builders take `base_dir` (the dir prior
  `source` paths resolve against); the CLI passes the input file's directory.
- **Web app (just-in-time upload).** The revision-history table in
  `MetadataEditor.jsx` has a per-row "Baseline file (state at this revision)"
  upload. The frontend reads the file as text and holds a transient
  `{revisionLetter: content}` map in `App.jsx` (NOT saved with the project);
  `GeneratePanel` passes it as `priorFiles` on the generate call. The backend
  `service.generate(..., prior_files=...)` writes each into the output dir as a
  hidden temp file, attaches a synthetic `PriorRevision`, generates with
  `base_dir=out`, then deletes the temp files. Semantics: the file uploaded on
  revision X's row is the ICD as it was at X, so the diff X->(next revision)
  populates the NEXT row's summary (mirrors the `priorRevisions` letter
  convention, where `revision="B"` fills the C row).
- To change wording/grouping: edit `_pr_grouped_lines` (default), or
  `_detail_lines` / `_counts_line`, in `rev_summary.py`; pick the mode via the
  `mode=` arg. (Generators call it with the default "pr" mode.)

### Per-signal `pr_ticket`
- New last signal field (`<prTicket>` / `prTicket`, label "PR Ticket"); freeform;
  appended so all derived outputs (incl. the traceability matrix "PR Ticket"
  column) pick it up. Optional. Non-fatal warning when missing on a post-Rev-A
  ICD (gate is `revision not in {"", "A"}`, case-insensitive). The example ICDs
  use `AVS-####` ticket values; the field/label is still "PR Ticket" in the
  toolchain (renaming it to "AVS" across registry/schema/traceability/summary is
  a separate, deliberate change — NOT done). To make missing-ticket fatal,
  change the `warnings.append(...)` in `loader._semantic_checks` to `raise`.

### Flow B — standalone two-file diff PDF report
- `gen_diff_pdf.build_diff_pdf(res, old_hash, new_hash, path, old_label, new_label)`
  renders a `DiffResult` into a deterministic PDF: header with both input
  SHA-256s + a counts summary, then Interface / Added / Removed / Modified
  sections (modified shows field old->new).
- **CLI:** `icdgen diff old new -o DIR` writes `*_diff.txt`, `*_diff.csv`, AND
  `*_diff.pdf`.
- **Web:** `POST /api/diff-report` (two file uploads) streams the PDF as a
  download; a parse failure on either side returns HTTP 400 naming the side.
  `api.js#diffReportPdf` triggers the browser download. `DiffPanel.jsx` is a
  download-only two-file form, reachable both with a project open and from the
  empty state.
- The JSON endpoints `/api/diff` and `/api/diff-files` remain for programmatic
  callers; the UI no longer uses `/api/diff-files`.

---

## 10. The web layer

`main.py` routes: health; `/api/meta/options`; projects CRUD; `/validate`;
`/generate` (accepts optional `priorFiles: {rev: text}` for Flow A); artifact
download; `export.xml`; `/import`; `/diff` (JSON); `/diff-files` (JSON);
**`/diff-report` (PDF download)**. `schemas.py` DTOs incl. `prTicket` and
`PriorRevisionDTO`/`IcdDTO.priorRevisions`. `service.py` is the only file
touching storage. Frontend builds all inputs from `/api/meta/options`.

---

## 11. Determinism contract (must never regress)

Identical input => byte-identical artifacts. No timestamps in artifacts
(`run.log` is the only wall-clock place). PDF: `rl_config.invariant=1` (covers
the ICD PDF AND the diff PDF). OOXML: pinned epoch + ZIP normalization. Registry
order fixes column order. Guard tests + determinism tests in
`tests/test_icdgen.py`. The diff PDF and the per-revision summary are
deterministic because the diff engine and prior-file load are. Re-verify the
byte baseline after any core change.

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
- **Change the revision summary wording / grouping:** `rev_summary.py`.
- **Restyle the diff PDF:** `gen_diff_pdf.py` (one file, self-contained).
- **New schema version:** add `icd-1.1.xsd.template` beside the 1.0 one (inside
  the package `schemas/` dir — the single home), register in
  `loader.SUPPORTED_SCHEMA_VERSIONS`, keep 1.0 working.
- **New API endpoint:** `service.py` fn + thin `main.py` route + `api.js` method.
- **New reqgen aspect:** one `AspectSpec` in `reqgen/config_schema.py` (sec 15).
- **Edit the XSD template:** there is now ONE file
  (`icdgen/icdgen/schemas/icd-1.0.xsd.template`). No second copy to sync.

---

## 13. Build / run / test quick reference

- **Install (core):** `pip install -e ./icdgen`
- **Core tests:** `cd icdgen && python -m pytest tests/ -q`
  ⚠ **Will error until section-0 is fixed** (tests reference deleted
  `icd_example.xml` / `icd_demo.xml` / `icd_demo_revD.xml`). After re-pointing
  them at the eVTOL examples, recount the expected total (the previous "36"
  baseline included the now-removed `test_schema_template_copies_in_sync`, so
  expect one fewer from that removal, before adjusting for any test edits).
- **Backend tests:**
  `cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/t python -m pytest tests/ -q`
  ⚠ `test_api.py::test_generate_with_prior_file_fills_summary` references
  `icd_demo_revD.xml` and `icd_demo.xml`; re-point at `icd_evtol_revC.xml` /
  `icd_evtol_revB.xml` (and update the asserted added-signal name, which is
  `vertical_speed` today and would become e.g. `vel_north` for the eVTOL pair).
- **reqgen tests:**
  `cd icdgen && PYTHONPATH=../reqgen python -m pytest ../reqgen/tests/ -q`
  ✓ Already targets `icd_evtol_revC.xml` / `icd_evtol_revB.xml` (DEMO/REVB) —
  this suite is consistent with the eVTOL examples.
- **Frontend build:** `cd icdweb/frontend && npm install && npm run build`
- **Docker (from repo root):**
  `docker compose -f icdweb/docker-compose.yml up --build` -> http://localhost:8000
- **CLI:**
  - `python -m icdgen validate examples/icd_evtol_revC.xml`  (shows PR-ticket warnings)
  - `python -m icdgen generate examples/icd_evtol_revC.xml -o out`
  - `python -m icdgen diff examples/icd_evtol_revB.xml examples/icd_evtol_revC.xml -o out`
- **reqgen:** `reqgen init` then
  `reqgen generate icdgen/examples/icd_evtol_revC.xml -o out` then
  `reqgen reconcile icdgen/examples/icd_evtol_revC.xml out/ICD-EVTOL-AVS-200_requirements.csv`
- **Determinism check:** generate twice, compare SHA-256 of all artifacts (skip
  `run.log`).

### Backend env vars
`ICDGEN_DATA_DIR` (`/data`), `ICDGEN_STATIC_DIR` (`/app/static`),
`ICDGEN_CORS_ORIGINS` (`*`), `PORT` (`8000`).

---

## 14. Known boundaries / not yet built (intentional)

- **No auth / multi-tenancy.** Projects are global.
- **Flat-directory storage** under `ICDGEN_DATA_DIR`; `service.py` is the only
  storage-touching file.
- **No job queue.** Generation is synchronous.
- **Deps EXACT-pinned;** bump -> re-run determinism check.
- **MISRA compliance is checker-confirmed,** not self-certified.
- **Permissive signal-name pattern;** C-identifier enforcement is warning-only.
- **Flow A works in BOTH paths.** CLI: link `priorRevisions` (path-based,
  resolved against the ICD's dir). Web: per-revision baseline upload, passed
  just-in-time as `priorFiles` (content-based, transient — not persisted).
- **reqgen exporters:** CSV only so far; ReqIF / tool-specific pending the
  target RM tool. No reqgen UI yet (deferred until config schema settles).

---

## 15. reqgen (requirement generator)

Separate tool, separate qualification scope. Imports icdgen as a library; reads
its own config; emits a requirements export + reconciliation report. Never writes
to the ICD. Build sequence: core + CLI done; ReqIF/UI deferred.

- **`config_schema.py`** — schema lives in code: an `ASPECTS` registry of
  structural requirement types (L3: EXISTS, RATE, DAL; L4: TYPE, RANGE, SCALE,
  UNITS) + the `ReqConfig` dataclass. **Bright line:** templates substitute ONLY
  ICD field values (structural transcription), never engineering intent.
  Behavioral requirements stay human-authored in the RM tool; reqgen links to
  them by ID only.
- **`config_io.py`** — read/write/hash the config file; `ensure_config` writes a
  populated default if absent (the file is driven by code, never hand-started);
  `save_config` is the only writer (CLI today, UI later — file stays the single
  record of truth).
- **`paths.py`** — bakes the config location: `reqgen/config/reqgen.json`
  (inside the reqgen project, NOT the repo root). `$REQGEN_CONFIG` overrides;
  resolves relative to the package so it works from any cwd.
- **`generate.py`** — walks the ICD, emits `Requirement` objects with **stable
  IDs derived from ICD structure** (so regeneration is idempotent and an RM-tool
  import updates in place). Precedence: per-signal -> per-interface -> global ->
  aspect default. Default aspects: L3 EXISTS+DAL, L4 TYPE+RANGE (RATE/SCALE/UNITS
  available but off). L3 granularity: "packet" (default) or "port".
- **`export.py`** — pluggable `EXPORTERS` registry; CSV today (universal RM-tool
  import). ReqIF / tool-specific slots in here once the target RM tool is chosen.
- **`reconcile.py`** — four-state diff (added/removed/changed/unchanged) of a
  fresh generation vs a prior export CSV; the "what to touch in the RM tool"
  report. Matches by stable ID, detects change by text.
- **`provenance.py`** — dual-hash anchor: a generated module traces to the
  reqgen version + the ICD SHA-256 + the config SHA-256.
- **CLI:** `reqgen init | generate <icd> -o DIR | reconcile <icd> <prior.csv>`.
- **Layout guard:** `pyproject.toml` declares `packages = ["reqgen"]`; a
  flattened tree fails to install loudly, and `test_package_is_properly_nested`
  guards it in CI. Config of record committed at `reqgen/config/reqgen.json`.

---

## 16. Next steps (priority order)

1. **Re-point `tests/test_icdgen.py` at the eVTOL examples** — the live open
   item (section 0). `EX_XML` -> revA (fix the `== 1` interface assertion to
   `== 3`), diff-PDF tests -> revB/revC. Then do the same for
   `icdweb/backend/tests/test_api.py` (`icd_demo*` -> `icd_evtol_*`).
2. **Confirm green:** icdgen (recounted total), reqgen 16, backend 8;
   determinism holds; revC validates (now that the schema single-sourcing fix is
   in, `validate`/`generate` on revB/revC succeed — the `priorRevisions`
   rejection is gone).
3. **ReqIF / tool-specific reqgen exporter** — blocked on naming the target RM
   tool (DOORS / Jama / Polarion / etc.).
4. **reqgen UI** as a file-editor over `config/reqgen.json` (deferred until the
   config schema settles; must remain a view over the file, never a 2nd source
   of state).
5. **Optional:** relabel "PR Ticket" -> "AVS" across the toolchain (deliberate).

### Resolved this session
- **XSD template single-sourcing** — applied. `resources.py` resolves only the
  package copy (+ MEIPASS); repo-root `icdgen/schemas/` deleted; `icdgen.spec`
  and `pyproject.toml` updated; `test_schema_template_copies_in_sync` removed.
  The `priorRevisions`-rejection "stale schema" failure is gone.
- **DiffPanel.jsx casing** — fixed (GitHub restore has the capital-P filename).
- **reqgen** built end-to-end (init/generate/reconcile, CSV exporter, four-state
  reconcile, dual-hash provenance).
- **Examples** are the 3-revision eVTOL ICD (`icd_evtol_revA/B/C.xml`).