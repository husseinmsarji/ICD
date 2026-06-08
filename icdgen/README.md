# icdgen

Deterministic Interface Control Document (ICD) artifact generator for
certifiable avionics programs developed under ARP4754A and DO-178C / DO-254.

A single, schema-validated interface definition file (XML or JSON) is the
**single source of truth**. From it, `icdgen` generates every downstream
artifact simultaneously, so an interface change is made once and propagated
everywhere — preserving traceability and removing the manual, multi-document
update step that creates DER audit risk.

## What it generates

From one input file:

1. **Formatted ICD document** — DOCX (python-docx) and PDF (ReportLab): cover
   page, revision history (with an auto "Change Summary Report" column when
   prior revisions are linked), interface overview, per-packet signal tables,
   notes.
2. **C / C++ header** — `struct` definitions and `#define` macros per signal
   (min/max/scale/offset/rate), MISRA C:2012-oriented. Compiles clean under C99.
3. **Simulink bus object script** (`.m`) — one `Simulink.Bus` per packet for
   MathWorks integration.
4. **Traceability matrix** — CSV and XLSX mapping each signal to its parent
   interface, packet, LRUs, DAL, owning document, PR/change ticket, and input
   hash.
5. **Diff report** — compares two input versions, classifying added / removed /
   modified signals (and interface add/remove) with old->new field values; text,
   CSV, and a formatted PDF.

## Install

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

Python 3.10+. No cloud dependencies — fully offline. Runs on Windows and macOS.

## Usage

```bash
# Validate only (exit 1 on any schema/semantic error, with a line reference)
python -m icdgen validate examples/icd_evtol_revC.xml

# Generate all artifacts into ./out
python -m icdgen generate examples/icd_evtol_revC.xml -o out

# Generate a subset
python -m icdgen generate input.json -o out -f header trace-csv pdf

# Diff two versions (exit 2 when differences are found — useful for CI gating)
python -m icdgen diff examples/icd_evtol_revB.xml examples/icd_evtol_revC.xml -o out
```

Artifact format keys: `docx pdf header simulink trace-csv trace-xlsx`.

The bundled examples are three revisions of one demonstration ICD
(`ICD-EVTOL-AVS-200`): `icd_evtol_revA.xml` (initial release), `icd_evtol_revB.xml`
(adds the AHRS bus), and `icd_evtol_revC.xml` (the current revision: 6 interfaces,
9 packets, 31 signals). revB links revA and revC links revB via `<priorRevisions>`,
so generating revB or revC populates the Change Summary Report column.

## Certification properties

- **Traceability.** Every artifact carries the tool version, input schema
  version, and the SHA-256 of the exact input file (document footers, source
  comment banners, and a dedicated CSV column).
- **Completeness, no silent failures.** Missing required fields raise a
  validation error with a file/line reference (XSD line for XML; located key for
  JSON), never a default-filled silent pass.
- **Determinism.** Identical inputs produce byte-identical outputs. Verified at
  the SHA-256 level across all artifacts. This required pinning ReportLab's
  document `/ID` and timestamps (`rl_config.invariant`), pinning OOXML
  core-property timestamps, and normalizing `.docx`/`.xlsx` ZIP entry timestamps
  and ordering (`ooxml_determinism.py`). The run log is the *only* place a
  wall-clock timestamp appears, and it is provenance metadata, not an artifact.
- **DO-330 tool-qualification evidence.** Generated documents embed a tool
  version identifier and input file hash in the footer. A timestamped `run.log`
  records each invocation (tool version, input hash, schema version, artifacts).

## Schema and extensibility

The input schema is **versioned** via an XML namespace (`urn:icdgen:icd:1.0`)
and a `schemaVersion` attribute. Extensibility contract:

- Additive-only within a major version: new **optional** elements/attributes may
  appear in a minor revision; required fields are only added in a major bump, so
  existing files never break.
- An `<extensions>` element (lax processing) lets a program carry custom payload
  without a schema change.

The XSD is assembled at load time from a single template
(`icdgen/schemas/icd-1.0.xsd.template`) plus the field registries, and the
equivalent jsonschema (in `loader.py`) is generated from those same registries.
Both converge on the same canonical, immutable model and cannot drift from each
other or from the registry. The template is shipped as package data, so one copy
serves source checkouts, pip wheels, and PyInstaller bundles alike — there is no
second copy to keep in sync.

## Build a standalone executable

For distribution to programs without a Python environment:

```bash
pip install pyinstaller
pyinstaller icdgen.spec          # -> dist/icdgen (icdgen.exe on Windows)
```

The spec bundles the XSD template and Jinja templates as data; `resources.py`
resolves them whether running from source, an installed package, or a
PyInstaller bundle (`sys._MEIPASS`).

## Project layout

```
icdgen/                    project root (packaging, spec, examples, tests)
  pyproject.toml           packaging; EXACT-pinned runtime deps
  icdgen.spec              PyInstaller build spec
  examples/                icd_evtol_revA.xml, _revB.xml, _revC.xml
  tests/test_icdgen.py     pytest suite
  icdgen/                  the importable package
    __main__.py            python -m icdgen / PyInstaller entry
    cli.py                 argparse CLI: validate | generate | diff
    fields.py              SINGLE SOURCE OF TRUTH: signal + interface registries
    schema_gen.py          derives XSD + JSON Schema from the registries
    signal_codec.py        registry-driven Signal/Interface/Packet codecs
    loader.py              XML(XSD) + JSON(jsonschema) validation, line refs, hashing
    model.py               frozen dataclasses (canonical model) + type maps
    serializer.py          IcdModel -> canonical XML
    provenance.py          tool/version/hash stamp (timestamp-free)
    resources.py           single-sourced schema/template path resolution
    gen_docx.py            DOCX ICD (python-docx)
    gen_pdf.py             PDF ICD (ReportLab, invariant mode)
    gen_code.py            C/C++ header + Simulink .m (Jinja2)
    gen_trace.py           traceability CSV + XLSX (openpyxl)
    gen_diff_pdf.py        standalone PDF change report
    rev_summary.py         per-revision Change Summary Report
    diff.py                version diff engine + text/CSV reports
    ooxml_determinism.py   ZIP normalization for byte-identical OOXML
    schemas/icd-1.0.xsd.template   the one XSD template (package data)
    templates/             header.h.j2, simulink_bus.m.j2
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -q        # 36 passed
```

Covers validation success/failure (XML and JSON), line references, enum and
range checks, duplicate detection, determinism, provenance stamping, traceability
row counts, the PR-ticket change-control field, prior-revision summaries, the
diff PDF, the serializer quote-escaping regression, and CLI exit codes.
