# Migration plan: XML → YAML ICD definition format (Scope B/C)

> **Status: executed.** This document is both the plan and the record of the
> completed migration. XML is fully removed; YAML is the sole ICD definition
> format. Determinism is preserved via a hand-rolled, byte-stable YAML emitter.

## 1. Goal & scope

Replace XML as the ICD *definition file* format with YAML, **removing** all XML
input/serialization/validation code (Scope C — full replacement, not a parallel
format). The web API remains JSON over HTTP (that is a transport, not the file
format) and reqgen's own config file remains JSON (its own qualification scope).

Non-goals: changing the domain model, the generated artifacts (DOCX/PDF/C/
Simulink/CSV/XLSX), or reqgen's config schema.

## 2. Why this is tractable

The system was already format-abstracted:

- `fields.py` is the single source of truth; the JSON Schema is *generated* from
  it (`schema_gen.json_*`). YAML parses to the same dict the JSON Schema already
  validated, so **validation needs no new rules** — the XSD path is redundant.
- `IcdModel` is format-neutral; every generator consumes the model, never the
  file.
- The codecs already had a dict path (`*_from_json_dict` / `*_to_json_dict`).

So the migration is: (a) parse YAML → dict → reuse the existing schema + model
construction; (b) add a deterministic `to_yaml` serializer; (c) delete the XML
machinery; (d) migrate examples/tests/docs.

## 3. Determinism strategy (the critical risk)

The value proposition is *byte-identical output* (DO-330 evidence). Rather than
depend on a third-party YAML emitter's formatting/quoting rules, the canonical
serializer is **hand-rolled** (mirroring the previous hand-rolled `to_xml`):

- `serializer._emit_map` / `_emit_seq` emit block-style YAML with fixed key
  order (registry order for signals/interfaces) and 2-space indentation.
- **Every string scalar is double-quoted and escaped** → unambiguous and
  emitter-stable; in particular dates emit as `"2026-06-01"` so YAML never
  coerces them to native `date` objects on re-parse.
- Numbers reuse the existing `_num()` (integers without a trailing `.0`); bools
  emit `true`/`false`.
- Optional/blank fields are dropped via the registry's `emit_if`, so canonical
  YAML is minimal and stable.

Parsing uses PyYAML `safe_load` (parsing does not affect output bytes; the
emitter owns determinism). `PyYAML` is EXACT-pinned like every other dependency.

## 4. File-by-file change map

### Core (`icdgen/icdgen/`)
| File | Change |
|------|--------|
| `fields.py` | Drop `xml_name`, `xml_location`, `XML_ATTRIBUTE/ELEMENT`; keep `json_name` (= YAML key) and `emit_if` (used by the YAML serializer). |
| `schema_gen.py` | Delete all `xsd_*`/`assemble_xsd` helpers; keep the `json_*` schema generators. |
| `signal_codec.py` | Delete the XML parse/emit functions; add registry-driven `*_to_yaml_dict` builders (ordered, `emit_if`-aware). Keep `*_json_dict` (API) + `*_from_values`. |
| `serializer.py` | `to_xml` → `to_yaml` + deterministic `_emit_map`/`_emit_seq`/quoting. |
| `loader.py` | Remove the XML/XSD path and `lxml`; parse YAML via `safe_load`; validate with the generated JSON Schema; add `schema_hash()`; line-approximation adapted to YAML `key:` form. |
| `resources.py` | Remove `xsd_template_path`/`compiled_xsd`/`compiled_xsd_hash`; keep the Jinja template resolution + manifest. |
| `cli.py` | run.log records `schema_sha256` (JSON Schema) instead of `compiled_xsd_sha256`; help text `.xml`→`.yaml`. |
| `schemas/icd-1.0.xsd.template` | **Deleted.** |
| `icdgen.spec` | Drop the XSD data file and the `lxml._elementpath` hidden import. |
| `pyproject.toml` / `requirements.txt` | Replace `lxml==6.0.2` with `PyYAML==6.0.1`; package-data drops `schemas/*.template`. |

### Web backend (`icdweb/backend/app/`)
| File | Change |
|------|--------|
| `service.py` | `to_yaml`; `*.source.yaml`; prior temp files `.prior_*.yaml`; validate via YAML temp. |
| `main.py` | `GET /api/projects/{id}/export.yaml`; import/diff temp suffix `.yaml`; docstrings. |
| `reqgen_service.py` | `icdXml`→`icdYaml`; `_model_from_yaml_text`; hash canonical YAML. |
| `schemas.py` | Docstring: "jsonschema" (no XSD). |

### Frontend (`icdweb/frontend/src/`)
`api.js` (`exportYamlUrl`), `App.jsx` (import label/accept/regex, `uploadYaml`),
`GeneratePanel.jsx` (export label + URL), `MetadataEditor.jsx` (accept),
`DiffPanel.jsx` (accept + copy), `ReqgenPanel.jsx` (`uploadYaml`/`icdYaml`,
accept `.yaml,.yml`).

### reqgen (`reqgen/reqgen/cli.py`)
Help text `.xml`→`.yaml` (loader already format-agnostic).

### Examples, tests, docs
- `icd_evtol_revA/B/C.xml` → `.yaml` (canonical serialization + `#` header;
  `<priorRevision source>` now points at `.yaml`).
- `test_icdgen.py` rewritten to author YAML fixtures; XSD-specific tests
  replaced with JSON-Schema/`to_yaml` equivalents.
- `test_api.py` / `test_reqgen.py` example paths + upload filenames → `.yaml`.
- `AI_README.md` regenerated; `icdweb`/`reqgen` READMEs' XML mentions updated.

## 5. Determinism verification

1. `to_yaml(load(x)) == to_yaml(load(to_yaml_file(x)))` (round-trip idempotent).
2. Generate all artifacts twice; SHA-256 identical (excluding `run.log`).
3. Full test suites (icdgen, icdweb backend, reqgen) green.

## 6. Documented behavior change

Dates (`revisionDate`, revision `date`) validate as strings under the JSON
Schema (the XSD validated `xs:date`). This matches the pre-existing JSON-input
behavior and is the one intentional relaxation.
