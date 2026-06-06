# AI_README — icdgen architecture map

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

## 1. Version & history

- **Project version:** 1.5.0
- **`icdgen` tool/provenance version:** 1.0.0 — the string stamped into
  artifacts (`provenance.TOOL_VERSION`). Bump it deliberately; it is independent
  of the project version and changing it changes artifact bytes (re-baseline).
- **Schema version:** 1.0 — XML namespace `urn:icdgen:icd:1.0`, `schemaVersion`
  attribute pinned to `1.x`.
- **Note:** `icdgen/pyproject.toml` currently still reads `version = "1.3.0"`.
  This is a known lag; bump it to `1.5.0` at release. It is a string only and
  has **no effect on generated output** (provenance uses `TOOL_VERSION`).

### History
- **1.0.0** — initial CLI tool + web app.
- **1.1.0** — SIGNAL field-registry refactor (single source of truth for signal
  fields; XSD + JSON Schema generated, no longer hand-duplicated).
- **1.2.0** — INTERFACE field-registry refactor; dependencies EXACT-pinned;
  full-capability demo.
- **1.2.1** — Dockerfile frontend COPY path bugfix (build context is the repo
  root, so paths must be `icdweb/frontend/...`). No code/output change.
- **1.3.0** — BREAKING (output format changed):
  (a) removed the signal `optional` field;
  (b) added a PACKET grouping layer: Interface -> Packets -> Signals (a packet
  has a name + optional description and holds the signals);
  (c) new signal field set + order; renamed `data_type` -> `signal_type`; added
  the `enum` data type; added `data_bits`/`xmit_bits`/`xmit_bytes` and a
  free-text `definition`; removed `direction` and `encoding` from signals.
- **1.4.0** — BREAKING (new byte baseline established + re-verified):
  (a) C header targets MISRA C:2012 (C-only; integer-constant suffixes `U`/`LL`/
  `ULL`; float `F` suffix; per-signal `_DATA_BITS` macro);
  (b) DOCX + PDF render EVERY signal field (all 13 columns, registry order) in
  LANDSCAPE orientation.
- **1.5.0 (current)** — Permissive draft-ICD support + a non-fatal **WARNINGS**
  channel. **BREAKING API: `loader.load()` now returns a 3-tuple**
  `(model, hash, warnings)`. Determinism re-verified on both fully-specified and
  partially-specified inputs. Details in section 9.

---

## 2. What the system is

Two deployable pieces sharing one core library:

1. **`icdgen/`** — the core Python library + CLI. Takes a single
   schema-validated XML/JSON ICD definition and deterministically generates six
   artifacts: a Word ICD (`.docx`), a PDF ICD, a C header (MISRA C:2012-oriented),
   a Simulink bus script (`.m`), a traceability matrix (`.csv` + `.xlsx`), and a
   version diff report. Also pip-installable and packageable as a standalone
   binary via PyInstaller.
2. **`icdweb/`** — a web app over the core: FastAPI backend + React form editor,
   containerized with Docker. The editor lets a user author
   interfaces/packets/signals in a form (no hand-writing XML); validation,
   generation, and diff call straight into the core library — never reimplemented.

**Core value proposition:** one input file is the single source of truth; every
downstream artifact is generated from it, so an interface change is made once and
propagated everywhere. **Identical input => byte-identical output** (SHA-256
verified across all six artifacts), which is what makes the tool usable as
DO-330 tool-qualification evidence.

**Domain:** certifiable avionics interface control under ARP4754A / DO-178C /
DO-254, with DO-330 provenance stamped into every artifact.

---

## 3. Repository layout

```
<repo root>/
├── AI_README.md                  ← this file
├── TESTING.md                    step-by-step verify/run instructions
├── .dockerignore
│
├── icdgen/                       ← CORE library + CLI (pip-installable)
│   ├── pyproject.toml            packaging; EXACT-pinned runtime deps
│   ├── requirements.txt          same pins (lxml, jsonschema, python-docx,
│   │                             reportlab, Jinja2, openpyxl)
│   ├── icdgen.spec               PyInstaller build spec (bundles schema+templates)
│   ├── run.py                    PyInstaller entry (absolute import)
│   ├── pyi_rth_docx.py           PyInstaller runtime hook for python-docx templates
│   ├── README.md
│   ├── schemas/
│   │   └── icd-1.0.xsd.template  XSD TEMPLATE with @INTERFACE_TYPE@/@SIGNAL_TYPES@/
│   │                             @ENUM_TYPES@ markers; PacketsType/PacketType are
│   │                             structural (hand-written in the template)
│   ├── examples/
│   │   ├── icd_example.xml       small: 1 interface, 2 packets, 4 signals
│   │   ├── icd_example.json      JSON equivalent (smaller)
│   │   ├── icd_demo.xml      ★   full: 3 interfaces, 4 packets, 10 signals,
│   │   │                         multiple bus types/DALs, the "enum" data type
│   │   └── icd_demo_revD.xml     diff target (1 added, 1 removed, 1 modified)
│   ├── tests/
│   │   └── test_icdgen.py        24 tests
│   └── icdgen/                   ← the importable package
│       ├── __init__.py           exposes __version__ (= TOOL_VERSION)
│       ├── __main__.py           `python -m icdgen` entry
│       ├── cli.py                argparse CLI: validate | generate | diff
│       ├── fields.py        ★    SINGLE SOURCE OF TRUTH: SIGNAL_FIELDS +
│       │                         INTERFACE_FIELDS + data-type catalog + enums
│       ├── schema_gen.py    ★    derives XSD + JSON Schema from the registries
│       ├── signal_codec.py  ★    registry-driven Signal/Interface codecs +
│       │                         structural Packet codec (XML/JSON/dict)
│       ├── model.py              frozen dataclasses: Signal/Packet/Interface/
│       │                         Metadata/RevisionEntry/IcdModel + type maps
│       ├── loader.py             validate (XSD + jsonschema) + parse -> IcdModel;
│       │                         hashing; semantic checks; WARNINGS channel
│       ├── serializer.py         IcdModel -> canonical schema-valid XML
│       ├── provenance.py         tool/version/hash stamp (timestamp-free)
│       ├── resources.py          resolve schema template + Jinja dir (source or
│       │                         PyInstaller bundle); assemble XSD in memory
│       ├── gen_code.py           C header + Simulink .m (Jinja2); MISRA helpers
│       ├── gen_docx.py           DOCX ICD (python-docx); landscape; 13 columns
│       ├── gen_pdf.py            PDF ICD (ReportLab, invariant); landscape; 13 cols
│       ├── gen_trace.py          traceability CSV + XLSX (openpyxl)
│       ├── diff.py               version diff engine + text/CSV reports
│       ├── ooxml_determinism.py  ZIP-normalizes .docx/.xlsx for byte-stability
│       ├── templates/
│       │   ├── header.h.j2       MISRA C:2012 header; unspecified-value comments
│       │   └── simulink_bus.m.j2 one Simulink.Bus per packet
│       └── schemas/
│           └── icd-1.0.xsd.template  (packaged copy for installed/bundled runs)
│
└── icdweb/                       ← WEB app (FastAPI + React)
    ├── Dockerfile                multi-stage; build context = repo root
    ├── docker-compose.yml        build context = .. (repo root)
    ├── README.md
    ├── backend/
    │   ├── requirements.txt      fastapi, uvicorn, python-multipart, pydantic (pinned)
    │   ├── app/
    │   │   ├── __init__.py
    │   │   ├── main.py           FastAPI routes; serves built frontend at /
    │   │   ├── schemas.py        Pydantic DTOs + DTO<->domain conversions
    │   │   └── service.py        project storage; validate/generate/diff;
    │   │                         ARTIFACT_BUILDERS dispatch
    │   └── tests/
    │       └── test_api.py       7 tests (in-process TestClient)
    └── frontend/
        ├── index.html
        ├── package.json / package-lock.json
        ├── vite.config.js        dev proxy /api -> :8000
        └── src/
            ├── main.jsx          React root
            ├── App.jsx           shell, project state, debounced validation,
            │                     status bar (errors + warnings), import
            ├── MetadataEditor.jsx     document metadata + revision history
            ├── InterfaceEditor.jsx ★  identity fields from registry + packets;
            │                          freeform fields use <datalist> suggestions
            ├── PacketEditor.jsx       packet name + description + SignalTable
            ├── SignalTable.jsx   ★    columns from options.signalFields; blank
            │                          enums, optional numerics->null, suggestions
            ├── GeneratePanel.jsx      format checklist + downloads + warnings
            ├── api.js                 one function per backend endpoint
            └── styles.css             avionics instrument-panel design system
```

> **Schema note.** The full XSD does **not** exist as a static file. At load
> time `resources.compiled_xsd()` reads `icd-1.0.xsd.template` and injects the
> registry-derived `<interface>` and `<signal>` complexTypes plus enum types at
> the marker comments. It therefore *cannot* drift from the registries.

★ = the files that make "add a field in one place" actually work. Read those first.

---

## 4. The field registry (the heart of maintainability)

**File: `icdgen/icdgen/fields.py`.** Everything about a signal field AND an
interface field is declared exactly once, here, as a `FieldSpec`. The XSD
fragment, the JSON Schema fragment, the editable form column/input, the API
descriptor, the XML/JSON serialization, the parsing logic, the CSV/XLSX columns,
AND the DOCX/PDF tables are all *derived* from this registry — never restated.

### Data-type catalog
- `DataTypeSpec(name, c_type, simulink_type)` and the `DATA_TYPES` tuple — the
  catalog of signal types including `"enum"` (-> C `int32_t`, Simulink `int32`).
- Derived maps: `DATA_TYPE_NAMES`, `C_TYPE_MAP`, `SIMULINK_TYPE_MAP`.

### Interface-level lists
- `BUS_TYPES` — **suggestions only** as of 1.5.0 (bus type is freeform). Served
  to the UI as autocomplete options; not an enforced enum.
- `DAL_LEVELS` — still an enforced enum (`A`-`E`).
- `DIRECTIONS` — `("TX","RX")`, retained for namespace stability (DirectionType
  in the XSD); not currently a signal field.

### `FieldSpec` (one field, fully described)
Fields: `name` (snake_case), `xml_name` (camel), `json_name` (camel), `label`,
`py_type` (`str|float|int|bool`), `xml_location` (`XML_ATTRIBUTE|XML_ELEMENT`),
`required`, `default`, `enum`/`enum_source` (`"data_types"` for the dynamic type
list), plus:
- **Validation hints:** `positive` (> 0 exclusive), `min_inclusive`
  (>= value — **new in 1.5.0**), `pattern` (regex), `min_length`.
- **UI hints:** `ui_width` (`auto|narrow|tiny`), `ui_numeric`,
  `suggestions` (freeform autocomplete list — **new in 1.5.0**).
- **Serialization:** `emit_if` predicate gating optional element/attribute
  emission so XML stays byte-stable (optional fields are omitted unless they
  carry a meaningful value).
- `enum_values()` resolves `enum_source="data_types"` -> `DATA_TYPE_NAMES`, else
  returns the static `enum`.

### The registries
- `SIGNAL_FIELDS: tuple[FieldSpec, ...]` — **order = column order everywhere.**
  Current order:
  `name, description, signal_type, update_rate_hz, units, data_bits, xmit_bits,
  xmit_bytes, scaling, definition, range_min, range_max, offset`.
- `INTERFACE_FIELDS: tuple[FieldSpec, ...]` — order:
  `id, bus_type, dal, name, source_lru, destination_lru, owning_document,
  description`. The `<packets>` child collection is NOT in the registry (handled
  structurally).
- Convenience: `SIGNAL_FIELDS_BY_NAME`, `INTERFACE_FIELDS_BY_NAME`,
  `signal_field_order()`.

### Descriptors (registry -> UI/API)
`_fields_descriptor(fields)` emits a JSON-serializable list of
`{name, jsonName, label, kind, enum, suggestions, required, uiWidth}`. `kind` is
`enum | bool | number | text` (both `float` and `int` map to `number`). Exposed
as `signal_fields_descriptor()` and `interface_fields_descriptor()`, served at
`/api/meta/options` so the React form builds itself from the registry. Adding a
field makes a new column/input appear with no frontend change.

### Schema derivation — `icdgen/icdgen/schema_gen.py`
Pure derivation from a registry + a name prefix (`Sig` / `If`), so the same code
serves signals and interfaces. Supporting per-field simpleTypes are named
`{prefix}Enum_*`, `{prefix}Pat_*`, `{prefix}Pos_*`, `{prefix}Inc_*`,
`{prefix}Len_*`.
- XSD: `xsd_signal_block()`, `xsd_interface_block()` (appends the structural
  `<packets>` element), `xsd_enum_types()` (DirectionType), `assemble_xsd()`
  (injects the three blocks at the template markers).
- JSON Schema: `json_signal_schema()`, `json_interface_schema()` via the generic
  `_json_object()`. `_XSD_BASE` / `_json_object` handle `int` (xs:integer /
  "integer") and the `min_inclusive` facet (xs:minInclusive / JSON `minimum`).
- **Optional enum fields** automatically also accept `""` in BOTH schemas (so a
  blank `signalType` validates). Pattern values are emitted via `quoteattr()` so
  a regex containing quotes (the signal-name pattern does) cannot break the XSD
  attribute.

---

## 5. Domain model — `icdgen/icdgen/model.py`

Hierarchy: `IcdModel -> Interface -> Packet -> Signal`. All dataclasses are
**frozen** to reinforce determinism (a generator cannot mutate the model).

- `Signal` — registry-backed scalar fields. As of 1.5.0 the optional fields
  default to permissive values: `signal_type=""`, `update_rate_hz=None`,
  `range_min=None`, `range_max=None` (plus the already-optional
  `data_bits/xmit_bits/xmit_bytes`, `scaling=1.0`, `offset=0.0`,
  `description/definition=None`). Properties:
  - `has_concrete_type` -> True iff `signal_type` is in `C_TYPE_MAP`.
  - `c_type` -> `C_TYPE_MAP.get(signal_type, "uint8_t")` (placeholder when blank).
  - `simulink_type` -> `SIMULINK_TYPE_MAP.get(signal_type, "uint8")`.
- `Packet` — structural: `name`, `signals` (tuple), optional `description`.
  NOT registry-driven.
- `Interface` — registry-backed scalars + a `packets` tuple.
- `RevisionEntry`, `Metadata` — document metadata + revision history.
- `IcdModel.all_signals()` — yields `(interface, packet, signal)` triples in
  document order; the canonical iteration for generators.

---

## 6. Codecs — `icdgen/icdgen/signal_codec.py`

Registry-driven data movement so adding a field needs no edits here.
- `_coerce(spec, value)` — None -> `spec.default`; else cast by `py_type`
  (`float`/`int`/`bool`/`str`). This is what makes optional numerics arrive as
  `None` cleanly.
- **Signals:** `signal_from_values`, `parse_signal_xml`, `signal_xml_lines`
  (renders float/int/bool/str; honors `emit_if`), `signal_to_json_dict`,
  `signal_from_json_dict`.
- **Interfaces:** `interface_from_values(values, packets)`, `parse_interface_xml`,
  `interface_open_xml`, `interface_to_json_dict`, `interface_from_json_dict`.
- **Packets (structural):** `parse_packet_xml`, `packet_xml_lines`,
  `packet_to_json_dict`, `packet_from_json_dict`.

`serializer.py` composes these into a full canonical XML document
(`to_xml(model)`), the inverse of the loader and the single source of truth for
the wire format shared by CLI and web.

---

## 7. Loading & validation — `icdgen/icdgen/loader.py`

Two outcome channels:
- **FATAL** -> raises `ValidationError(message, line, source)`; the file does not
  load. Sources of fatals: XML syntax, XSD violation, JSON syntax, jsonschema
  violation (with an approximate line), unsupported `schemaVersion`, duplicate
  interface id / packet name / signal name, and `rangeMin > rangeMax` *when both
  are present*.
- **NON-FATAL** -> returned as `list[ValidationWarning(message, line)]`. Current
  warnings: a signal with **no `signal_type`** (header will use a `uint8_t`
  placeholder) and a signal **name that is not a valid C identifier** (won't
  compile in the C header as-is).

`load(path) -> (IcdModel, sha256_hex, list[ValidationWarning])`. **This 3-tuple
is the 1.5.0 breaking change** — every caller unpacks three values. Format is
inferred from the extension (`.json` -> JSON path, otherwise XML).

Validation authority: the XSD (assembled from the registry) and the jsonschema
(generated from the registry) are the *only* validators, and both the form and a
hand-authored file pass through `loader.load`, so they cannot disagree. The raw
input bytes are SHA-256 hashed *before* parsing so the provenance stamp traces to
the exact authored file.

---

## 8. Data flow

**Authoring (web):** React form -> `IcdDTO` (JSON) -> `POST /api/projects/{id}` ->
`service.save_definition` writes `definition.json`. Live validation (debounced):
`POST .../validate` -> `service.validate_dto` -> `dto_to_model` ->
`serializer.to_xml` -> `loader.load` -> `(errors, warnings)` surfaced to the UI
with line refs.

**Generation:** `POST .../generate` -> `service.generate` serializes the model to
a canonical `*.source.xml`, hashes it, builds a `Provenance`, then runs each
selected builder in `service.ARTIFACT_BUILDERS`. The response includes
`inputHash`, `schemaVersion`, the artifact list, and a `warnings` array.

**CLI path:** `cli.py` -> `loader.load(path)` -> generators -> files + `run.log`.
Same core code as the web path. Warnings print to stderr; exit code stays 0.

**Generators** iterate `model.all_signals()` (or walk `iface.packets[].signals`).
The C header and Simulink emit **one struct/Bus per PACKET**. DOCX/PDF render the
full 13-column signal table (landscape) per packet. CSV/XLSX emit one row per
signal.

---

## 9. What 1.5.0 changed (permissive drafts + warnings)

### Five schema relaxations (so partial/draft ICDs upload and edit in the tool)
1. **busType is freeform** — enum dropped; any non-empty string. `BUS_TYPES`
   survives as a UI suggestion list via `FieldSpec.suggestions` (rendered as a
   `<datalist>`). Backend `InterfaceDTO.busType` is now `str` (was a `Literal`).
2. **signalType is optional** — may be blank for an in-progress signal. A blank
   type can't map to a real C/Simulink type, so it renders the `uint8_t`/`uint8`
   placeholder and raises a WARNING. (Decision: blank-allowed, **not** a literal
   `"unknown"` enum value.) Backend `SignalDTO.signalType` is `str = ""`.
3. **updateRateHz is optional + non-negative (>= 0)** — blank allowed, zero
   allowed, negatives rejected by schema (`FieldSpec.min_inclusive=0.0` ->
   xs:minInclusive / JSON `minimum`). Backend DTO: `Optional[float] = None`.
4. **Signal name pattern relaxed** to `[^\s"'<>]+` (allows `-`, `#`, `.`, ...).
   Names that aren't valid C identifiers still load but WARN; the C header emits
   the raw name (won't compile as-is, by design).
5. **rangeMin / rangeMax optional** — the `rangeMin > rangeMax` check runs only
   when both are present. The C header emits `/* ..._MIN: unspecified */`
   comments instead of `#define`s when a bound is absent. Backend DTO:
   `Optional[float] = None` for both.

### Warnings system (core -> CLI -> backend -> frontend)
- `loader.py`: `ValidationWarning` dataclass; `_semantic_checks()` returns a
  warning list (still raises on fatals); `load()` returns the 3-tuple.
- `cli.py`: prints `WARNING:` to stderr in `validate` and `generate`; exit 0.
- Backend: `service.validate_dto()` returns `(errors, warnings)`; `/validate`,
  `/generate`, and `/import` responses carry `warnings: [{message, line}]`.
- Frontend: amber `N WARNING(S)` in the status bar; GeneratePanel lists warnings
  with the `.issue.warn` style; import toast notes the warning count;
  `SignalTable`/`InterfaceEditor` render optional enums with an `(unset)` option,
  optional numerics as blank->`null`, and freeform fields with a `<datalist>`.

### Backend DTO posture (`schemas.py`)
DTO validation is intentionally **loose** (busType freeform, signalType blank,
numerics optional) because the authoritative validator is always
`icdgen.loader`. Only `Dal` remains a `Literal`. This lets a half-complete ICD
round-trip through the API and be finished in the editor.

### Files NOT changed
`gen_docx.py` and `gen_pdf.py` needed no change — their `_cell()` already renders
`None` as blank. (`gen_trace.py` *was* changed to blank optional numerics rather
than print `"None"`.)

---

## 10. The web layer

**`icdweb/backend/app/`**
- `main.py` — thin HTTP routing. Endpoints: `GET /api/health`,
  `GET /api/meta/options` (enums + both field descriptors + artifact formats),
  projects CRUD (`GET/POST /api/projects`, `GET/PUT/DELETE /api/projects/{id}`),
  `POST /api/projects/{id}/validate`, `POST /api/projects/{id}/generate`,
  `GET /api/projects/{id}/artifacts/{file}`, `GET /api/projects/{id}/export.xml`,
  `POST /api/import`, `POST /api/diff`. Mounts the built frontend at `/` when
  `ICDGEN_STATIC_DIR` exists.
- `schemas.py` — Pydantic DTOs (`SignalDTO`, `PacketDTO`, `InterfaceDTO`,
  `MetadataDTO`, `RevisionEntryDTO`, `IcdDTO`) + `dto_to_model` / `model_to_dto`
  (which delegate to the codecs).
- `service.py` — flat-directory project storage under `ICDGEN_DATA_DIR`;
  `validate_dto` -> `(errors, warnings)`; `generate` (serialize -> hash ->
  provenance -> `ARTIFACT_BUILDERS`); `diff`; atomic writes; `_empty_definition`.
  `ARTIFACT_BUILDERS` maps an artifact key -> `(suffix, builder-fn-name)`; the
  API and UI enumerate it, so a new format surfaces automatically.

**`icdweb/frontend/src/`** — React (Vite). Builds all form columns/inputs from
`/api/meta/options`, so the registry drives the UI. `api.js` has one function per
endpoint. `styles.css` is the avionics instrument-panel design system (phosphor
green = valid/TX, cyan = RX, amber = caution/warning, red = error, violet =
modified).

---

## 11. Determinism contract (must never regress)

Identical input => byte-identical artifacts. Mechanisms:
- No timestamps/hostnames in artifacts; `run.log` is the only wall-clock place
  (it is provenance metadata, not an artifact — never hash it).
- PDF: `reportlab.rl_config.invariant = 1` (pins the document `/ID` + dates).
- OOXML (`.docx`/`.xlsx`): pinned core-property epoch + ZIP entry normalization
  in `ooxml_determinism.normalize()` (fixed entry timestamps, stable ordering,
  normalized `core.xml` dates).
- Registry order fixes column/field order: appending a field is safe; reordering
  changes output by design (a deliberate, reviewable act).
- C constants via deterministic helpers (`_num_const`/`_float_const`) — no locale
  or float-repr drift.
- **Guard tests** in `tests/test_icdgen.py`: `test_registry_schema_sync`,
  `test_interface_registry_schema_sync`, `test_assembled_xsd_compiles`,
  `test_registry_roundtrip_via_codec`, plus determinism + round-trip tests.

**Re-verify the byte baseline after any core change.** A hash change is expected
only for a deliberate format change — when that happens, establish a new baseline.

---

## 12. How to make common changes (recipes)

### Add a new SIGNAL field
1. Add one `FieldSpec(...)` to `SIGNAL_FIELDS` in `fields.py` (**append** to keep
   output stable). Set `xml_location`, `required`, `default`, and `emit_if` if
   optional.
2. Add the matching attribute to the `Signal` dataclass in `model.py`.
3. That covers schema (XSD + JSON), XML/JSON parse + serialize, API descriptor,
   the UI table column, the traceability CSV/XLSX, AND the full DOCX/PDF tables.
   **No other files** for data flow + documents.
4. The C header shows a curated macro set per signal (min/max/scale/offset/rate/
   data_bits). If a NEW field also needs its own macro, edit `header.h.j2`
   (+ a helper in `gen_code.py` if it needs special formatting). C macro
   presentation is intentionally human-controlled.
5. Run tests; re-verify the determinism baseline.

### Add a new DATA TYPE / signal type
- Add one `DataTypeSpec(...)` to `DATA_TYPES` in `fields.py`. Flows to the enum,
  C/Simulink maps, and schema. If the C type is unsigned, also add the name to
  `_UNSIGNED_TYPES` in `gen_code.py` (and `_LONGLONG_TYPES` if 64-bit) so range
  constants get the correct suffix.

### Add a BUS-TYPE suggestion or DAL level
- Append to `BUS_TYPES` (suggestion only) or `DAL_LEVELS` (enforced) in
  `fields.py`.

### Add a new ARTIFACT format
1. Write a deterministic generator in `icdgen/`.
2. Add one entry to `service.ARTIFACT_BUILDERS` + the matching `_write_*` shim.
   The API options list and the UI checklist pick it up automatically. (For the
   CLI, add the format key to `cli.ALL_FORMATS` and a branch in `cmd_generate`.)

### Add a new INTERFACE-level field
1. Add one `FieldSpec(...)` to `INTERFACE_FIELDS` in `fields.py`.
2. Add the matching attribute to the `Interface` dataclass in `model.py`.
   Flows to XSD, JSON Schema, XML/JSON parse + serialize, DTO conversion, the API
   `interfaceFields`, and the React interface form. Keep `<packets>` structural —
   don't add it to the registry. If the field needs a strict DTO type, also
   adjust `InterfaceDTO` in backend `schemas.py`.

### Work with PACKETS (the grouping layer)
- Packets are structural, not registry-driven. To change packet fields (currently
  name + description) edit: `PacketType` in the XSD template, the packet block in
  `loader._json_schema`, the `Packet` dataclass, the packet codec functions in
  `signal_codec.py`, `PacketDTO` in backend `schemas.py`, and `PacketEditor.jsx`.

### Add a new VALIDATION rule
- **Schema-expressible** (enum, pattern, range, presence): add a facet to the
  relevant `FieldSpec` (`enum`, `pattern`, `positive`, `min_inclusive`,
  `min_length`, `required`). It flows to both XSD and JSON Schema automatically.
- **Cross-field / semantic:** add it to `loader._semantic_checks` — raise
  `ValidationError` for a fatal, or append a `ValidationWarning` for a non-fatal.

### Add a new schema version (1.1)
- The namespace is versioned. Add `icd-1.1.xsd.template` (with the markers),
  register `"1.1"` in `loader.SUPPORTED_SCHEMA_VERSIONS`, keep 1.0 working.

### Add a new API endpoint
- Add a function in `service.py` + a thin route in `main.py` + a client method in
  `frontend/src/api.js`.

---

## 13. Build / run / test quick reference

- **Install (core):** `pip install -e ./icdgen`
- **Core tests:** `cd icdgen && python -m pytest tests/ -q` -> **24 passed**
- **Backend tests:**
  `cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/t python -m pytest tests/ -q` ->
  **7 passed**
- **Frontend build:** `cd icdweb/frontend && npm install && npm run build`
- **Docker (from repo root):**
  `docker compose -f icdweb/docker-compose.yml up --build` -> http://localhost:8000
- **CLI:** `python -m icdgen {validate|generate|diff} ...`
  - `python -m icdgen validate examples/icd_demo.xml`
  - `python -m icdgen generate examples/icd_demo.xml -o out`
  - `python -m icdgen diff examples/icd_demo.xml examples/icd_demo_revD.xml -o out`
    (exit code 2 when differences exist — useful for CI gates)
- **Determinism check:** generate twice into different dirs, compare SHA-256 of
  all six artifacts (skip `run.log`).
- **MISRA spot-check:** generated `.h` compiles under
  `gcc -std=c99 -Wall -Wextra -pedantic`; run a full MISRA checker
  (Polyspace/LDRA/Coverity) for qualification evidence.
- **Standalone binary:** `cd icdgen && pyinstaller icdgen.spec`

### Backend env vars
`ICDGEN_DATA_DIR` (default `/data`), `ICDGEN_STATIC_DIR` (default `/app/static`),
`ICDGEN_CORS_ORIGINS` (comma-separated, default `*`), `PORT` (default `8000`).

---

## 14. Known boundaries / not yet built (intentional)

- **No requirement linkage yet.** Signals don't reference requirement IDs, so the
  traceability matrix proves representational consistency (all artifacts share
  one hashed source), not requirements-to-interface trace. This is the
  highest-value next feature — one `FieldSpec` on signals/packets.
- **No auth / multi-tenancy.** Projects are global. First thing to add before a
  second user.
- **Flat-directory storage.** Fine for one user; swap for Postgres + object
  storage when scaling. `service.py` is the only file touching storage.
- **No job queue.** Generation is synchronous. `/generate` already returns a
  result object that could become a job handle without touching the frontend.
- **Dependencies are EXACT-pinned** (`==`) in `icdgen/requirements.txt`,
  `icdgen/pyproject.toml`, and `icdweb/backend/requirements.txt`. Dev tools stay
  `>=`. Bump a runtime dep -> re-run the determinism check (a hash change is
  expected only for a deliberate format change).
- **MISRA compliance is checker-confirmed, not self-certified.** The header
  covers the declaration/macro subset of MISRA C:2012. Run your MISRA tool and
  capture the report as qualification evidence; send flagged rule numbers to
  adjust the template.
- **Permissive signal-name pattern (1.5.0).** The pattern is now `[^\s"'<>]+`;
  the "valid C identifier" enforcement lives entirely in the WARNING channel.
  Tighten the pattern in `fields.py` if you want a stricter allowed set.
- **`pyproject.toml` version lag.** Reads `1.3.0`; bump to `1.5.0` at release
  (string only; no output impact).