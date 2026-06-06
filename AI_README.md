# AI_README — icdgen architecture map

> **Purpose of this file.** This is the single document to paste back to Claude
> when requesting changes. It describes every file, its responsibilities, key
> functions/classes, the data flow, the invariants that must hold, and the
> recipes for common changes — so source files do not need to be re-sent.
>
> **Maintenance rule.** Claude regenerates/updates this file at the end of every
> change so it always matches the code. Treat it as the source of truth for
> "what version are we on and how is it built." If this file and the code
> disagree, the code wins and this file must be corrected.

---

## Version

- **Project version:** 1.3.0
- **`icdgen` tool/provenance version:** 1.0.0  (string stamped into artifacts —
  see "Determinism contract"; bump deliberately, it changes nothing in output)
- **Schema version:** 1.0  (XML namespace `urn:icdgen:icd:1.0`)
- **History:**
  - 1.0.0 — initial CLI tool + web app.
  - 1.1.0 — SIGNAL field-registry refactor (single source of truth for signal
    fields; XSD + JSON Schema generated, no longer duplicated).
  - 1.2.x — INTERFACE field-registry refactor; dependencies EXACT-pinned;
    full-capability demo; Dockerfile frontend COPY path bugfix (1.2.1).
  - 1.3.0 (current) — Model + UI changes (BREAKING; output format changed,
    so 1.2.x baseline hashes intentionally no longer apply — a NEW baseline was
    established and determinism re-verified):
      (a) Removed the signal `optional` field entirely.
      (b) Added a PACKET grouping layer: Interface -> Packets -> Signals. A
          packet has a name + optional description and holds the signals. New
          XML: <interface><packets><packet name=".."><signals>... New UI:
          PacketEditor inside InterfaceEditor.
      (c) New signal field set + order: Signal Name, Description, Signal Type,
          Rate (Hz), Units, Data Bits, Xmit Bits, Xmit Bytes, Scale, Definition,
          Range Min, Range Max, Offset. Renamed data_type -> signal_type and
          added "enum" as a data type (C int32_t / Simulink int32). Added new
          int fields data_bits/xmit_bits/xmit_bytes and free-text definition.
          Removed direction and encoding from signals.
  - 1.2.1 (current) — Bugfix: the Dockerfile frontend stage used context paths
    `frontend/...` but the build context is the repo root, so they must be
    `icdweb/frontend/...`. Fixed all frontend COPY lines. No code/output change;
    determinism unaffected. (Backend COPY lines were already correct.)

---

## What the system is

Two deployable pieces sharing one core library:

1. **`icdgen/`** — the core Python library + CLI. Takes a schema-validated
   XML/JSON ICD definition and deterministically generates: a Word ICD (.docx),
   a PDF ICD, a C/C++ header, a Simulink bus script (.m), a traceability matrix
   (.csv + .xlsx), and a version diff. Also packageable as a standalone binary
   (PyInstaller) and pip-installable.
2. **`icdweb/`** — a web app over the core: FastAPI backend + React form editor,
   containerized with Docker. The editor lets you author interfaces/signals in a
   form (no hand-writing XML); generation/validation/diff call straight into the
   core library.

---

## Repository layout

```
<repo root>/
├── AI_README.md                     ← this file
├── .dockerignore
├── icdgen/                          ← CORE library + CLI (pip-installable)
│   ├── pyproject.toml               package metadata; entry point icdgen.cli:main
│   ├── requirements.txt
│   ├── run.py                       PyInstaller launcher (absolute import)
│   ├── icdgen.spec                  PyInstaller build spec (bundles schema+templates)
│   ├── pyi_rth_docx.py              runtime hook: fixes python-docx template path when frozen
│   ├── README.md                    human-facing CLI readme
│   ├── schemas/
│   │   └── icd-1.0.xsd.template      XSD TEMPLATE: @SIGNAL_TYPES@/@INTERFACE_TYPE@/@ENUM_TYPES@ markers; PacketsType/PacketType structural
│   ├── examples/
│   │   ├── icd_example.xml           small 2-interface example
│   │   ├── icd_example.json
│   │   ├── icd_demo.xml          ★ full-capability demo (6 buses, all DAL, 25 signals)
│   │   └── icd_demo_revD.xml         a changed version of the demo, for diffing
│   ├── icdgen/                      ← the package
│   │   ├── __init__.py              exposes __version__
│   │   ├── __main__.py              `python -m icdgen` → cli.main
│   │   ├── cli.py                   argparse CLI: validate | generate | diff
│   │   ├── fields.py        ★ SINGLE SOURCE OF TRUTH: SIGNAL_FIELDS + INTERFACE_FIELDS + enums
│   │   ├── schema_gen.py    ★ derives XSD fragments + JSON Schema from the registry
│   │   ├── signal_codec.py  ★ registry-driven Signal/Interface + structural Packet codecs
│   │   ├── model.py                 frozen dataclasses (Signal/Packet/Interface/.../IcdModel)
│   │   ├── loader.py                validate (XSD+jsonschema) + parse → IcdModel; hashing
│   │   ├── serializer.py            IcdModel → canonical XML (inverse of loader)
│   │   ├── provenance.py            tool/version/hash stamp (timestamp-free)
│   │   ├── resources.py             resolves schema template + templates dir; assembles XSD
│   │   ├── gen_code.py              C header + Simulink .m via Jinja2 templates
│   │   ├── gen_docx.py              DOCX ICD (python-docx)
│   │   ├── gen_pdf.py               PDF ICD (ReportLab, invariant mode)
│   │   ├── gen_trace.py             traceability CSV + XLSX (openpyxl)
│   │   ├── diff.py                  version diff engine + text/CSV reports
│   │   ├── ooxml_determinism.py     ZIP-normalizes .docx/.xlsx for byte-identical output
│   │   ├── schemas/                 in-package copy of the template (for pip installs)
│   │   └── templates/
│   │       ├── header.h.j2
│   │       └── simulink_bus.m.j2
│   └── tests/test_icdgen.py         20 tests (validation, determinism, registry sync, packets, enum)
└── icdweb/
    ├── Dockerfile                   multi-stage: build React → serve from FastAPI
    ├── docker-compose.yml           local run; build context = repo root
    ├── README.md                    human-facing web readme
    ├── backend/
    │   ├── requirements.txt         fastapi, uvicorn, python-multipart (icdgen installed separately)
    │   ├── app/
    │   │   ├── __init__.py
    │   │   ├── main.py              FastAPI routes (thin); serves built frontend at /
    │   │   ├── schemas.py          Pydantic DTOs + DTO↔model conversion (signal parts use codec)
    │   │   └── service.py          project storage + validate/generate/diff orchestration
    │   └── tests/test_api.py        7 tests (in-process TestClient)
    └── frontend/
        ├── package.json, package-lock.json, vite.config.js, index.html
        └── src/
            ├── main.jsx             React entry
            ├── api.js               one function per backend endpoint
            ├── App.jsx              app shell, state, sidebar, save/validate loop
            ├── MetadataEditor.jsx   document metadata + revision history
            ├── InterfaceEditor.jsx  ★ identity fields (registry) + list of PacketEditors
            ├── PacketEditor.jsx     packet name + description + a SignalTable
            ├── SignalTable.jsx  ★ columns BUILT FROM options.signalFields
            ├── GeneratePanel.jsx    format checklist + artifact downloads
            └── styles.css           avionics instrument-panel design system
```

> **Schema note.** Runtime assembles the XSD in memory from
> `icd-1.0.xsd.template` via `resources.compiled_xsd()` (template + both field
> registries). There is no static full XSD anymore — it cannot drift from the
> registries because it does not exist as a separate artifact.

★ = the files that make "add a field in one place" work. Read these first.

---

## The field registry (the heart of maintainability)

**File: `icdgen/icdgen/fields.py`.** Everything about a signal field AND an
interface field is declared once, here. Downstream representations are
*derived*, never restated. There are two registries with identical machinery:
`SIGNAL_FIELDS` and `INTERFACE_FIELDS` (both tuples of `FieldSpec`).

Key objects:
- `DataTypeSpec(name, c_type, simulink_type)` and the `DATA_TYPES` tuple — the
  catalog of signal types, including "enum" (-> C int32_t, Simulink int32).
  `C_TYPE_MAP`, `SIMULINK_TYPE_MAP`, `DATA_TYPE_NAMES` are derived from it.
- `BUS_TYPES`, `DAL_LEVELS`, `DIRECTIONS` — interface-level enums.
- `FieldSpec` — full description of one signal field. Fields of note:
  `name` (snake_case, Python/`Signal` attribute), `xml_name` (camelCase),
  `json_name` (camelCase, API/DTO), `label` (UI header), `py_type`
  (`str|float|bool`), `xml_location` (`XML_ATTRIBUTE|XML_ELEMENT`), `required`,
  `default`, `enum`/`enum_source` (`"data_types"` for dynamic), validation hints
  (`positive`, `pattern`, `min_length`), UI hints (`ui_width`, `ui_numeric`),
  and `emit_if` (predicate controlling whether an optional element/attr is
  written — preserves byte-stable XML).
- `SIGNAL_FIELDS: tuple[FieldSpec, ...]` — **the registry. Order = column order
  everywhere.** Currently (v1.3.0): name, description, signal_type,
  update_rate_hz, units, data_bits, xmit_bits, xmit_bytes, scaling, definition,
  range_min, range_max, offset. (`py_type` may be str, float, int, or bool —
  `int` used by the *_bits/_bytes fields.)
- `signal_field_order()`, `SIGNAL_FIELDS_BY_NAME`, `signal_fields_descriptor()`
  (JSON descriptor consumed by the API/UI).
- `INTERFACE_FIELDS: tuple[FieldSpec, ...]` — the interface registry. Order =
  XSD element order + form field order. Currently: id, bus_type, dal, name,
  source_lru, destination_lru, owning_document, description. The `<signals>`
  child collection is NOT in the registry (it is a collection, not a scalar
  field) and is handled structurally by the XSD template + codec.
- `INTERFACE_FIELDS_BY_NAME`, `interface_fields_descriptor()`.

**File: `icdgen/icdgen/schema_gen.py`.** Pure derivation registry → schemas,
generalized over a registry + a name prefix (`Sig` / `If`) so one set of helpers
serves both signal and interface fields. Supporting per-field simpleTypes are
named `{prefix}Enum_*`, `{prefix}Pat_*`, `{prefix}Pos_*`, `{prefix}Len_*`
(minLength). Public functions:
- `xsd_signal_block()` → `<xs:complexType name="SignalType">` + its simpleTypes.
- `xsd_interface_block()` → `<xs:complexType name="InterfaceType">` (with the
  `<signals>` child appended structurally) + its simpleTypes.
- `xsd_enum_types()` → `DirectionType` (Bus/DAL are generated inline as
  `IfEnum_*` by the interface block).
- `assemble_xsd(template_text)` → injects `@SIGNAL_TYPES@`, `@INTERFACE_TYPE@`,
  `@ENUM_TYPES@` markers in the template.
- `json_signal_schema()`, `json_interface_schema()` → JSON-Schema objects.

**Model hierarchy (`model.py`):** `IcdModel -> Interface -> Packet -> Signal`.
`Packet` is a structural dataclass (name, optional description, signals) — it
is NOT registry-driven because it has no extensible scalar fields.
`IcdModel.all_signals()` yields `(interface, packet, signal)` triples.

**File: `icdgen/icdgen/signal_codec.py`.** Registry-driven data movement for
signals and interfaces, plus a structural packet codec:
- Signals: `signal_from_values`, `parse_signal_xml(sig_el, ns, text_of)`,
  `signal_xml_lines(sig, indent, esc, num)`, `signal_to_json_dict(sig)`,
  `signal_from_json_dict(d)`.
- Interfaces: `interface_from_values(values, packets)`,
  `parse_interface_xml(iface_el, ns, text_of, packets)`,
  `interface_open_xml(iface, indent, esc)` → (open-tag, child-element-lines)
  with the caller appending `<packets>` + close tag,
  `interface_to_json_dict(iface)`, `interface_from_json_dict(d)`.
- Packets (structural): `parse_packet_xml(pkt_el, ns, text_of, signals)`,
  `packet_xml_lines(pkt, indent, esc, signal_lines_fn)`,
  `packet_to_json_dict(pkt)`, `packet_from_json_dict(d)`.
All honor `xml_location` + `emit_if`. camelCase dicts are used by backend DTOs.

---

## Data flow

**Authoring (web):** React form → `IcdDTO` (JSON) → `POST /api/projects/{id}` →
`service.save_definition` writes `definition.json`. Live validation:
`POST .../validate` → `service.validate_dto` → `dto_to_model` →
`serializer.to_xml` → `loader.load` (XSD + jsonschema) → issues (with line refs).

**Generation:** `POST .../generate` → `service.generate` serializes the model to
a canonical `*.source.xml`, hashes it (SHA-256), builds a `Provenance`, then runs
each selected builder in `service.ARTIFACT_BUILDERS`. Artifacts land in the
project's `out/` dir; downloaded via `GET .../artifacts/{filename}`.
Signals live under packets: generators iterate `model.all_signals()` (yields
interface, packet, signal) or walk `iface.packets[].signals`. The C header emits
one struct per PACKET (`<iface>_<packet>_t`); Simulink emits one Bus per packet.

**CLI path:** `cli.py` → `loader.load(path)` → generators in `gen_*` → files +
`run.log`. Same core code as the web path.

**Validation authority:** the XSD (assembled from registry) and the jsonschema
(generated from registry) are the *only* validators. Both the form and a
hand-authored file pass through `loader.load`, so they cannot disagree.

---

## Determinism contract (must never regress)

The whole tool's value is reproducible output. Identical input ⇒ byte-identical
artifacts. Mechanisms:
- No timestamps/hostnames in artifacts; the run log is the only place a wall
  clock appears (`cli.py` / `service.py`).
- PDF: `reportlab.rl_config.invariant = 1` (fixes random /ID + dates) — `gen_pdf.py`.
- OOXML (.docx/.xlsx): pinned core-property epoch + ZIP entry normalization —
  `ooxml_determinism.normalize()` and core.xml date rewrite.
- Registry order fixes column/field order; appending a field is safe, reordering
  changes output by design.
- **Guard tests** (`tests/test_icdgen.py`): `test_registry_schema_sync`,
  `test_assembled_xsd_compiles`, `test_registry_roundtrip_via_codec`, plus the
  determinism and round-trip tests. **Baseline hashes are re-verified after any
  core change.**

---

## How to make common changes (recipes)

### Add a new SIGNAL field
1. Add one `FieldSpec(...)` to `SIGNAL_FIELDS` in `fields.py` (append to keep
   output stable). Set `xml_location`, `required`, `default`, and `emit_if` for
   optionals.
2. Add the matching attribute to the `Signal` dataclass in `model.py` (one line;
   needed for type safety/IDE).
3. That's it for schema, JSON, XML parse/serialize, API options, and the UI
   table column. **No other files.**
4. If the field should also appear as a `#define` or column in the DOCX/PDF/
   header/Simulink output, edit the relevant `gen_*`/template — presentation is
   intentionally human-controlled, not auto-generated.
5. Run tests; re-verify determinism baseline.

### Add a new DATA TYPE (e.g. float128)
- Add one `DataTypeSpec(...)` to `DATA_TYPES` in `fields.py`. Flows to the
  enum, C/Simulink maps, schema. Done.

### Add a new BUS TYPE or DAL level
- Append to `BUS_TYPES` / `DAL_LEVELS` in `fields.py`.

### Add a new ARTIFACT format
1. Write the generator in `icdgen/` (follow `gen_*` patterns; keep it
   deterministic).
2. Add one entry to `service.ARTIFACT_BUILDERS` (key → (suffix, builder shim))
   and the matching `_write_*` shim. The API options list and the UI format
   checklist pick it up automatically.

### Add a new INTERFACE-level field (not signal)
- Same as signal fields, now that interfaces are registry-driven:
  1. Add one `FieldSpec(...)` to `INTERFACE_FIELDS` in `fields.py`.
  2. Add the matching attribute to the `Interface` dataclass in `model.py`.
  That flows to the XSD, JSON Schema, XML parse/serialize, DTO conversion, the
  API `interfaceFields`, and the React interface form automatically.
  (The `<signals>` collection is special and stays structural — don't add it to
  the registry.)

### Work with PACKETS (the grouping layer)
- Packets are structural, not registry-driven. To change a packet's own fields
  (currently just name + description) edit: `PacketType` in the XSD template,
  the packet JSON-schema block in `loader._json_schema`, the `Packet` dataclass
  in `model.py`, the packet codec functions in `signal_codec.py`, `PacketDTO` in
  backend `schemas.py`, and `PacketEditor.jsx`. (This is the same multi-file
  pattern signals had before they were registry-driven — if packet fields start
  to churn, give packets their own registry.)
- Signals always belong to a packet. Iterate via `model.all_signals()` →
  `(interface, packet, signal)`.

### Add a new schema version (1.1)
- Namespace is versioned. Add `icd-1.1.xsd.template` (with the `@SIGNAL_TYPES@`,
  `@INTERFACE_TYPE@`, `@ENUM_TYPES@` markers), register `"1.1"` in
  `loader.SUPPORTED_SCHEMA_VERSIONS`, keep 1.0 working (additive-only within a
  major version; required fields only in a major bump).

### Add a new API endpoint
- Add a function in `service.py` (logic) + a thin route in `main.py` + a client
  method in `frontend/src/api.js`.

---

## Build / run / test quick reference

- **Core tests:** `cd icdgen && python -m pytest tests/ -q`  (20 tests)
- **Backend tests:** `cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/t python -m pytest tests/ -q`  (7 tests)
- **Frontend build:** `cd icdweb/frontend && npm install && npm run build`
- **Docker (from repo root):** `docker compose -f icdweb/docker-compose.yml up --build` → http://localhost:8000
- **CLI:** `python -m icdgen {validate|generate|diff} ...`
- **Demo:** `python -m icdgen generate examples/icd_demo.xml -o out` then
  `python -m icdgen diff examples/icd_demo.xml examples/icd_demo_revD.xml -o out`
- **Standalone binary:** `cd icdgen && pyinstaller icdgen.spec`

### Env vars (backend)
`ICDGEN_DATA_DIR` (project storage, default `/data`), `ICDGEN_STATIC_DIR`
(built frontend), `ICDGEN_CORS_ORIGINS`, `PORT`.

---

## Known boundaries / not yet built (intentional)

- **No auth / multi-tenancy.** Projects are global; anyone can edit/delete any.
  This is the first thing to add before a second user. Gates all other
  multi-user work.
- **Flat-directory storage.** Fine for one user; swap for Postgres + object
  storage when scaling to the 50–100 user target. `service.py` is the only file
  that touches storage, by design.
- **No job queue.** Generation is synchronous. The `/generate` result object
  could become a job handle without frontend changes when needed.
- **Dependencies are EXACT-pinned** (`==`) in `icdgen/requirements.txt`,
  `icdgen/pyproject.toml`, and `icdweb/backend/requirements.txt` — the versions
  that produced the verified baseline. Dev tools (pytest/pyinstaller) stay `>=`
  since they don't affect output bytes. To bump a runtime dep: change the pin,
  rebuild, re-run the determinism check; if a hash changes, that's expected only
  for a deliberate format change and the baseline must be re-recorded.
- **DOCX/PDF/header presentation** of new fields is manual (see recipe step 4).
  The DOCX/PDF show a curated subset of the 13 signal columns (page-width
  limited); the traceability CSV/XLSX carry the full set.
- **C header / Simulink map one struct/Bus per PACKET** (named
  `<iface>_<packet>_t` / `Bus_<iface>_<packet>`).
