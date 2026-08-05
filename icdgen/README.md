# icdgen

Deterministic Interface Control Document (ICD) artifact generator for
certifiable avionics programs developed under ARP4754A and DO-178C / DO-254.

A single, schema-validated interface definition file (XML or JSON) is the
**single source of truth**. From it, `icdgen` generates every downstream
artifact simultaneously, so an interface change is made once and propagated
everywhere. That preserves traceability and removes the manual, multi-document
update step that creates DER audit risk.

`icdgen` is the core library. Two sibling tools build on it: **`reqgen/`** (a
separate requirement generator that imports icdgen) and **`icdweb/`** (a web
editor). Architecture for all three is documented in
[`../AI_README.md`](../AI_README.md).

## The input model

An ICD is a three-level hierarchy: **Interface → Packet → Signal**. An interface
is the physical/protocol/connectivity contract between two LRUs; a packet is a
message on that interface; a signal is a field within a packet.

Every signal and interface field is declared **once** in a field registry
(`icdgen/fields.py`). The XSD, the JSON Schema, the serializer, the parser, the
document tables, and the CSV/XLSX columns are all derived from it — add a field
in one place and it flows everywhere. Signal fields include `signal_type`
(with a `data_bits`/`xmit_bits`/`xmit_bytes` transmission model), `scaling`,
`offset`, `range_min`/`range_max`, free-text `definition`, and `pr_ticket` (the
PR/change ticket that last touched a signal). The `enum` signal type is
supported.

## What it generates

From one input file:

1. **Formatted ICD document** — DOCX (python-docx) and PDF (ReportLab): cover
   page, revision history (with an auto-computed **Change Summary Report**
   column when prior revisions are linked), interface overview, per-packet
   signal tables (landscape), notes.
2. **C header** — `struct` definitions and `#define` macros per packet/signal
   (min/max/scale/offset/rate). **MISRA C:2012-oriented: C only** (no C++
   constructs), fixed-width integer types, fully parenthesized macros. Macro
   names are sanitized.
3. **Simulink bus object script** (`.m`) — one `Simulink.Bus` per packet for
   MathWorks integration (quote-escaped).
4. **Traceability matrix** — CSV and XLSX mapping each signal to its parent
   interface, packet, LRUs, DAL, owning document, **PR Ticket**, and input hash.
5. **Diff reports** — compare two input versions, classifying added / removed /
   modified signals (and interface add/remove) with old→new field values, as
   **text, CSV, and a deterministic PDF change report**.

## Install

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                                    # or: pip install -r requirements.txt
```

Python 3.10+. No cloud dependencies — fully offline. Deps are EXACT-pinned to
protect byte-determinism. Runs on Windows and macOS.

## Usage

```bash
# Validate only (exit 1 on any schema/semantic error, with a line reference)
python -m icdgen validate examples/icd_evtol_revC.xml

# Generate all artifacts into ./out
python -m icdgen generate examples/icd_evtol_revC.xml -o out

# Generate a subset
python -m icdgen generate input.json -o out -f header trace-csv pdf

# Release gate: turn every non-fatal warning fatal, generate nothing on warnings
python -m icdgen generate examples/icd_evtol_revC.xml -o out --strict

# Diff two versions (exit 2 when differences are found — useful for CI gating);
# writes *_diff.txt, *_diff.csv, and *_diff.pdf
python -m icdgen diff examples/icd_evtol_revB.xml examples/icd_evtol_revC.xml -o out
```

Artifact format keys: `docx pdf header simulink trace-csv trace-xlsx`.

### Warnings channel (permissive drafts)

Non-fatal issues (blank `signal_type`, a signal name that is not a valid C
identifier, a missing `pr_ticket` on a post-Rev-A ICD) are reported as
**warnings** on stderr with exit code 0, so drafts stay authorable. `--strict`
promotes them to fatal for a release build.

## Certification properties

- **Traceability.** Every artifact carries the tool version, input schema
  version, and the SHA-256 of the exact input (document footers, source comment
  banners, and a dedicated CSV column).
- **Completeness, no silent failures.** Missing required fields raise a
  validation error with a file/line reference (XSD line for XML; located key for
  JSON), never a default-filled silent pass.
- **Determinism.** Identical inputs produce byte-identical outputs, verified at
  the SHA-256 level across every artifact. This pins ReportLab's document `/ID`
  and timestamps (`rl_config.invariant` — covers the ICD PDF and the diff PDF),
  pins OOXML core-property timestamps, and normalizes `.docx`/`.xlsx` ZIP entry
  timestamps and ordering (`ooxml_determinism.py`). `run.log` is the *only*
  place a wall-clock timestamp appears, and it is provenance metadata, not an
  artifact.
- **DO-330 tool-qualification evidence.** Generated documents embed a tool
  version identifier and input hash. `run.log` records each invocation (tool
  version, input hash, schema version, artifacts, the compiled-XSD hash, the
  active template directory, and a per-template hash manifest).

## Schema and extensibility

The input schema is **versioned** via an XML namespace (`urn:icdgen:icd:1.0`)
and a `schemaVersion` attribute. Extensibility contract:

- Additive-only within a major version: new **optional** elements/attributes may
  appear in a minor revision; required fields are only added in a major bump, so
  existing files never break.
- An `<extensions>` element (lax processing) lets a program carry custom payload
  without a schema change.

The full XSD is **assembled in memory at load time** from one template plus both
field registries (`resources.compiled_xsd()`), so it cannot drift from the
registries. The template is a single physical file — package data at
`icdgen/schemas/icd-1.0.xsd.template` — and the equivalent jsonschema (in
`loader.py`) is kept in lockstep; both converge on the same canonical model.
Set `ICDGEN_TEMPLATE_DIR` to point the Jinja templates at a program-specific
copy (recorded in `run.log` under provenance).

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
icdgen/
  fields.py              signal + interface field registry (single source of truth)
  schema_gen.py          derives the XSD + JSON Schema from the registries
  signal_codec.py        registry-driven Signal/Interface + structural Packet codecs
  model.py               frozen dataclasses (Interface -> Packet -> Signal, PriorRevision)
  loader.py              XML(XSD)+JSON(jsonschema) validation; line refs; WARNINGS channel
  serializer.py          IcdModel -> canonical XML
  provenance.py          tool/version/hash stamp (timestamp-free)
  resources.py           schema/template resolution; ICDGEN_TEMPLATE_DIR override
  gen_docx.py            DOCX ICD (landscape; Change Summary Report column)
  gen_pdf.py             PDF ICD (ReportLab, invariant mode)
  gen_code.py            C header (MISRA C:2012) + Simulink .m (Jinja2)
  gen_trace.py           traceability CSV + XLSX (openpyxl; incl. PR Ticket)
  gen_diff_pdf.py        standalone PDF change report
  rev_summary.py         per-revision Change Summary Report cells
  diff.py                version diff engine + text/CSV reports
  ooxml_determinism.py   ZIP normalization for byte-identical OOXML
  schemas/icd-1.0.xsd.template   the one XSD template (package data)
  templates/             header.h.j2, simulink_bus.m.j2
cli.py                   argparse CLI: validate | generate | diff (+ --strict)
examples/                icd_evtol_revA/B/C.xml (three revisions of ICD-EVTOL-AVS-200)
tests/                   pytest suite (36 tests)
icdgen.spec              PyInstaller build spec
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -q       # 36 passed
```

Covers validation success/failure (XML and JSON), line references, enum and
range checks, duplicate detection, determinism, provenance stamping,
traceability row counts (incl. the PR Ticket column), the prior-revision
auto-diff summaries, and CLI exit codes. See [`../TESTING.md`](../TESTING.md)
for the full run/verify walkthrough across all three tools.
