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
   page, revision history, interface overview, per-interface signal tables, notes.
2. **C / C++ header** — `struct` definitions and `#define` macros per signal
   (min/max/scale/offset/rate). Compiles clean under C99 and C++11.
3. **Simulink bus object script** (`.m`) — one `Simulink.Bus` per interface for
   MathWorks integration.
4. **Traceability matrix** — CSV and XLSX mapping each signal to its parent
   interface, LRUs, DAL, owning document, and input hash.
5. **Diff report** — compares two input versions, classifying added / removed /
   modified signals (and interface add/remove) with old→new field values.

## Install

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# or: pip install .
```

Python 3.10+. No cloud dependencies — fully offline. Runs on Windows and macOS.

## Usage

```bash
# Validate only (exit 1 on any schema/semantic error, with a line reference)
python -m icdgen validate examples/icd_example.xml

# Generate all artifacts into ./out
python -m icdgen generate examples/icd_example.xml -o out

# Generate a subset
python -m icdgen generate input.json -o out -f header trace-csv pdf

# Diff two versions (exit 2 when differences are found — useful for CI gating)
python -m icdgen diff old.xml new.xml -o out
```

Artifact format keys: `docx pdf header simulink trace-csv trace-xlsx`.

## Certification properties

- **Traceability.** Every artifact carries the tool version, input schema
  version, and the SHA-256 of the exact input file (document footers, source
  comment banners, and a dedicated CSV column).
- **Completeness, no silent failures.** Missing required fields raise a
  validation error with a file/line reference (XSD line for XML; located key for
  JSON), never a default-filled silent pass.
- **Determinism.** Identical inputs produce byte-identical outputs. Verified at
  the SHA-256 level across all six artifacts. This required pinning ReportLab's
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

The XSD (`schemas/icd-1.0.xsd`) and the equivalent jsonschema (in `loader.py`)
are kept in lockstep; both converge on the same canonical, immutable model.

## Build a standalone executable

For distribution to programs without a Python environment:

```bash
pip install pyinstaller
pyinstaller icdgen.spec          # -> dist/icdgen (icdgen.exe on Windows)
```

The spec bundles the XSD and Jinja templates as data; `resources.py` resolves
them whether running from source, an installed package, or a PyInstaller bundle
(`sys._MEIPASS`).

## Project layout

```
icdgen/
  __main__.py            python -m icdgen / PyInstaller entry
  cli.py                 argparse CLI: validate | generate | diff
  loader.py              XML(XSD) + JSON(jsonschema) validation, line refs, hashing
  model.py               frozen dataclasses (canonical model) + type maps
  provenance.py          tool/version/hash stamp (timestamp-free)
  gen_docx.py            DOCX ICD (python-docx)
  gen_pdf.py             PDF ICD (ReportLab, invariant mode)
  gen_code.py            C/C++ header + Simulink .m (Jinja2)
  gen_trace.py           traceability CSV + XLSX (openpyxl)
  diff.py                version diff engine + text/CSV reports
  ooxml_determinism.py   ZIP normalization for byte-identical OOXML
  resources.py           schema/template path resolution
  templates/             header.h.j2, simulink_bus.m.j2
schemas/icd-1.0.xsd      versioned input schema
examples/                icd_example.xml, icd_example.json
tests/                   pytest suite
icdgen.spec              PyInstaller build spec
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```

Covers validation success/failure (XML and JSON), line references, enum and
range checks, duplicate detection, determinism, provenance stamping, traceability
row counts, and CLI exit codes.
