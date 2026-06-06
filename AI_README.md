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

- **Project version:** 1.4.0
- **`icdgen` tool/provenance version:** 1.0.0  (string stamped into artifacts —
  see "Determinism contract"; bump deliberately, it changes nothing in output)
- **Schema version:** 1.0  (XML namespace `urn:icdgen:icd:1.0`)
- **History:**
  - 1.0.0 — initial CLI tool + web app.
  - 1.1.0 — SIGNAL field-registry refactor (single source of truth for signal
    fields; XSD + JSON Schema generated, no longer duplicated).
  - 1.2.0 — INTERFACE field-registry refactor; dependencies EXACT-pinned;
    full-capability demo.
  - 1.2.1 — Dockerfile frontend COPY path bugfix (context is repo root, so
    paths must be `icdweb/frontend/...`). No code/output change.
  - 1.3.0 — Model + UI changes (BREAKING; output format changed):
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
  - 1.4.0 (current) — Output-format changes (BREAKING for byte-baseline; a NEW
    baseline was established and determinism re-verified across all six
    artifacts):
      (a) C header now targets MISRA C:2012 (C ONLY): removed the
          `extern "C"`/`__cplusplus` block; added typed integer-constant
          suffixes (U for unsigned, LL/ULL for 64-bit) on range bounds, and
          `F` suffix on float constants; added a per-signal `_DATA_BITS`
          unsigned macro. Verified to compile under
          `gcc -std=c99 -Wall -Wextra -pedantic`.
      (b) DOCX and PDF now contain EVERY signal field (all 13 columns, in
          registry order) — switched both to LANDSCAPE orientation to fit.
          Columns are sourced from `SIGNAL_FIELDS`, so they cannot drift from
          the model.

---

## What the system is

Two deployable pieces sharing one core library:

1. **`icdgen/`** — the core Python library + CLI. Takes a schema-validated
   XML/JSON ICD definition and deterministically generates: a Word ICD (.docx),
   a PDF ICD, a C header (MISRA C:2012-oriented), a Simulink bus script (.m), a
   traceability matrix (.csv + .xlsx), and a version diff. Also packageable as a
   standalone binary (PyInstaller) and pip-installable.
2. **`icdweb/`** — a web app over the core: FastAPI backend + React form editor,
   containerized with Docker. The editor lets you author interfaces/packets/
   signals in a form (no hand-writing XML); generation/validation/diff call
   straight into the core library.

---

## Repository layout
> **Schema note.** Runtime assembles the XSD in memory from
> `icd-1.0.xsd.template` via `resources.compiled_xsd()` (template + both field
> registries). There is no static full XSD anymore — it cannot drift from the
> registries because it does not exist as a separate artifact.

★ = the files that make "add a field in one place" work. Read these first.

---

## The field registry (the heart of maintainability)

**File: `icdgen/icdgen/fields.py`.** Everything about a signal field AND an
interface field is declared once, here. Downstream representations are
*derived*, never restated. Two registries with identical machinery:
`SIGNAL_FIELDS` and `INTERFACE_FIELDS` (both tuples of `FieldSpec`).

Key objects:
- `DataTypeSpec(name, c_type, simulink_type)` and the `DATA_TYPES` tuple — the
  catalog of signal types, including "enum" (-> C int32_t, Simulink int32).
  `C_TYPE_MAP`, `SIMULINK_TYPE_MAP`, `DATA_TYPE_NAMES` are derived from it.
- `BUS_TYPES`, `DAL_LEVELS`, `DIRECTIONS` — interface-level enums.
- `FieldSpec` — full description of one field: `name` (snake_case), `xml_name`
  (camel), `json_name` (camel), `label`, `py_type` (`str|float|int|bool`),
  `xml_location` (`XML_ATTRIBUTE|XML_ELEMENT`), `required`, `default`,
  `enum`/`enum_source` (`"data_types"` for dynamic), validation hints
  (`positive`, `pattern`, `min_length`), UI hints (`ui_width`, `ui_numeric`),
  and `emit_if` (predicate gating optional element/attr emission for byte-stable
  XML).
- `SIGNAL_FIELDS: tuple[FieldSpec, ...]` — **the registry. Order = column order
  everywhere** (CSV/XLSX, AND now the full DOCX/PDF tables). Currently:
  name, description, signal_type, update_rate_hz, units, data_bits, xmit_bits,
  xmit_bytes, scaling, definition, range_min, range_max, offset.
  (`py_type` may be str, float, int, or bool — `int` used by the *_bits/_bytes.)
- `signal_field_order()`, `SIGNAL_FIELDS_BY_NAME`, `signal_fields_descriptor()`.
- `INTERFACE_FIELDS: tuple[FieldSpec, ...]` — interface registry: id, bus_type,
  dal, name, source_lru, destination_lru, owning_document, description. The
  `<packets>` child collection is NOT in the registry (handled structurally).
- `INTERFACE_FIELDS_BY_NAME`, `interface_fields_descriptor()`.

**File: `icdgen/icdgen/schema_gen.py`.** Pure derivation registry → schemas,
generalized over a registry + a name prefix (`Sig` / `If`). Supporting per-field
simpleTypes are named `{prefix}Enum_*`, `{prefix}Pat_*`, `{prefix}Pos_*`,
`{prefix}Len_*`. Public: `xsd_signal_block()`, `xsd_interface_block()` (appends
`<packets>` structurally), `xsd_enum_types()` (DirectionType), `assemble_xsd()`,
`json_signal_schema()`, `json_interface_schema()`. Note `_XSD_BASE`/`_json_object`
handle `int` (xs:integer / "integer").

**Model hierarchy (`model.py`):** `IcdModel -> Interface -> Packet -> Signal`.
`Packet` is a structural dataclass (name, optional description, signals) — NOT
registry-driven. `IcdModel.all_signals()` yields `(interface, packet, signal)`
triples.

**File: `icdgen/icdgen/signal_codec.py`.** Registry-driven data movement for
signals and interfaces, plus a structural packet codec:
- Signals: `signal_from_values`, `parse_signal_xml`, `signal_xml_lines`
  (handles float/int/bool/str render), `signal_to_json_dict`,
  `signal_from_json_dict`.
- Interfaces: `interface_from_values(values, packets)`, `parse_interface_xml`,
  `interface_open_xml`, `interface_to_json_dict`, `interface_from_json_dict`.
- Packets (structural): `parse_packet_xml`, `packet_xml_lines`,
  `packet_to_json_dict`, `packet_from_json_dict`.

**File: `icdgen/icdgen/gen_code.py`.** MISRA-oriented C header generation.
Helpers `_num_const(sig, x)` and `_float_const(x)` apply integer suffixes
(`U`/`LL`/`ULL` per the field's `signal_type`) and float `F` suffixes; passed
into the template as `num_const` / `float_const`. `_UNSIGNED_TYPES` and
`_LONGLONG_TYPES` drive the suffix choice. One struct/Bus per PACKET.

---

## Data flow

**Authoring (web):** React form → `IcdDTO` (JSON) → `POST /api/projects/{id}` →
`service.save_definition` writes `definition.json`. Live validation:
`POST .../validate` → `service.validate_dto` → `dto_to_model` →
`serializer.to_xml` → `loader.load` (XSD + jsonschema) → issues (with line refs).

**Generation:** `POST .../generate` → `service.generate` serializes the model to
a canonical `*.source.xml`, hashes it (SHA-256), builds a `Provenance`, then runs
each selected builder in `service.ARTIFACT_BUILDERS`. Signals live under packets:
generators iterate `model.all_signals()` or walk `iface.packets[].signals`. The
C header and Simulink emit one struct/Bus per PACKET. DOCX/PDF render the full
13-column signal table (landscape) per packet.

**CLI path:** `cli.py` → `loader.load(path)` → generators in `gen_*` → files +
`run.log`. Same core code as the web path.

**Validation authority:** the XSD (assembled from registry) and the jsonschema
(generated from registry) are the *only* validators. Both the form and a
hand-authored file pass through `loader.load`, so they cannot disagree.

---

## Determinism contract (must never regress)

Identical input ⇒ byte-identical artifacts. Mechanisms:
- No timestamps/hostnames in artifacts; the run log is the only wall-clock place.
- PDF: `reportlab.rl_config.invariant = 1`.
- OOXML (.docx/.xlsx): pinned core-property epoch + ZIP entry normalization
  (`ooxml_determinism.normalize()`).
- Registry order fixes column/field order; appending a field is safe, reordering
  changes output by design.
- C constants are emitted via deterministic helpers (no locale/float drift).
- **Guard tests** (`tests/test_icdgen.py`): `test_registry_schema_sync`,
  `test_interface_registry_schema_sync`, `test_assembled_xsd_compiles`,
  `test_registry_roundtrip_via_codec`, plus determinism + round-trip tests.
  Re-verify the byte baseline after any core change.

---

## How to make common changes (recipes)

### Add a new SIGNAL field
1. Add one `FieldSpec(...)` to `SIGNAL_FIELDS` in `fields.py` (append to keep
   output stable). Set `xml_location`, `required`, `default`, `emit_if`.
2. Add the matching attribute to the `Signal` dataclass in `model.py`.
3. That covers schema, JSON, XML parse/serialize, API options, the UI table
   column, the traceability CSV/XLSX, AND the full DOCX/PDF tables (all sourced
   from the registry). **No other files** for data flow + documents.
4. The C header shows min/max/scale/offset/rate/data_bits macros per signal; if
   a NEW field also needs its own macro, edit `header.h.j2` + a helper in
   `gen_code.py`. (C macro presentation is intentionally human-controlled.)
5. Run tests; re-verify determinism baseline.

### Add a new DATA TYPE / signal type
- Add one `DataTypeSpec(...)` to `DATA_TYPES` in `fields.py`. Flows to the enum,
  C/Simulink maps, schema. If the C type is unsigned, also add the type name to
  `_UNSIGNED_TYPES` in `gen_code.py` (and `_LONGLONG_TYPES` if 64-bit) so range
  constants get the correct suffix.

### Add a new BUS TYPE or DAL level
- Append to `BUS_TYPES` / `DAL_LEVELS` in `fields.py`.

### Add a new ARTIFACT format
1. Write the generator in `icdgen/` (deterministic).
2. Add one entry to `service.ARTIFACT_BUILDERS` + the matching `_write_*` shim.
   The API options list and UI checklist pick it up automatically.

### Add a new INTERFACE-level field
1. Add one `FieldSpec(...)` to `INTERFACE_FIELDS` in `fields.py`.
2. Add the matching attribute to the `Interface` dataclass in `model.py`.
   Flows to XSD, JSON Schema, XML parse/serialize, DTO conversion, the API
   `interfaceFields`, and the React interface form. (The `<packets>` collection
   stays structural — don't add it to the registry.)

### Work with PACKETS (the grouping layer)
- Packets are structural, not registry-driven. To change packet fields
  (currently name + description) edit: `PacketType` in the XSD template, the
  packet JSON-schema block in `loader._json_schema`, the `Packet` dataclass, the
  packet codec functions in `signal_codec.py`, `PacketDTO` in backend
  `schemas.py`, and `PacketEditor.jsx`.
- Signals always belong to a packet. Iterate via `model.all_signals()`.

### Add a new schema version (1.1)
- Namespace is versioned. Add `icd-1.1.xsd.template` (with the markers), register
  `"1.1"` in `loader.SUPPORTED_SCHEMA_VERSIONS`, keep 1.0 working.

### Add a new API endpoint
- Add a function in `service.py` + a thin route in `main.py` + a client method
  in `frontend/src/api.js`.

---

## Build / run / test quick reference

- **Core tests:** `cd icdgen && python -m pytest tests/ -q`  (20 tests)
- **Backend tests:** `cd icdweb/backend && ICDGEN_DATA_DIR=/tmp/t python -m pytest tests/ -q`  (7 tests)
- **Frontend build:** `cd icdweb/frontend && npm install && npm run build`
- **Docker (from repo root):** `docker compose -f icdweb/docker-compose.yml up --build` → http://localhost:8000
- **CLI:** `python -m icdgen {validate|generate|diff} ...`
- **Demo:** `python -m icdgen generate examples/icd_demo.xml -o out` then
  `python -m icdgen diff examples/icd_demo.xml examples/icd_demo_revD.xml -o out`
- **MISRA spot-check:** the generated `.h` compiles under
  `gcc -std=c99 -Wall -Wextra -pedantic`; for full MISRA evidence run it through
  your MISRA checker (Polyspace/LDRA/Coverity) as tool-qualification evidence.
- **Standalone binary:** `cd icdgen && pyinstaller icdgen.spec`

### Env vars (backend)
`ICDGEN_DATA_DIR` (default `/data`), `ICDGEN_STATIC_DIR`, `ICDGEN_CORS_ORIGINS`,
`PORT`.

---

## Known boundaries / not yet built (intentional)

- **No requirement linkage yet.** Signals don't reference requirement IDs, so
  the traceability matrix proves representational consistency (all artifacts
  share one hashed source), not requirements-to-interface trace. This is the
  highest-value next feature (one `FieldSpec` on signals/packets).
- **No auth / multi-tenancy.** Projects are global. First thing to add before a
  second user.
- **Flat-directory storage.** Fine for one user; swap for Postgres + object
  storage when scaling. `service.py` is the only file touching storage.
- **No job queue.** Generation is synchronous.
- **Dependencies are EXACT-pinned** (`==`) in `icdgen/requirements.txt`,
  `icdgen/pyproject.toml`, and `icdweb/backend/requirements.txt`. Dev tools
  (pytest/pyinstaller) stay `>=`. Bump a runtime dep → re-run determinism check;
  a hash change is expected only for a deliberate format change (re-baseline).
- **MISRA compliance is checker-confirmed, not self-certified.** The generated
  header covers the declaration/macro subset of MISRA C:2012 (C-only, fixed-width
  types, parenthesized macros, typed constant suffixes, include guards). Run your
  MISRA tool against it and capture the report as qualification evidence; send
  any flagged rule numbers to adjust the template.
- **DOCX/PDF now contain ALL 13 signal fields** (landscape). The C header still
  shows a curated macro set per signal (min/max/scale/offset/rate/data_bits) by
  design.