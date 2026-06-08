# reqgen

Deterministic **requirement generator** that sits *beside* `icdgen`, not inside
it. It reads an icdgen ICD (the canonical XML/JSON) as a library input and emits
a requirements module for an RM tool (DOORS / Jama / Polarion / etc.), plus a
reconciliation report. It never writes back into the ICD and shares no mutable
state with icdgen, so the two tools keep **independent DO-330 qualification
scopes**.

## What it does

1. **`init`** — writes a fully-populated config file from code defaults. You do
   not hand-author the file; reqgen drives it. (A UI will later edit this same
   file — the file stays the single record of truth.)
2. **`generate`** — ICD + config → a requirements export. Every requirement has
   a **stable ID derived from the ICD structure**, so regeneration is idempotent
   and an RM-tool import updates in place.
3. **`reconcile`** — ICD + config + a prior export → a four-state report
   (added / removed / changed / unchanged) telling you exactly which RM objects
   to create, retire, or update after an ICD or config change.

## The config drives the file

The config *schema* lives in code (`config_schema.py`, an aspect registry in the
same spirit as icdgen's field registry). The version-controlled config *file* is
generated from it (`config_io.ensure_config`) and round-trips deterministically
(canonical JSON, sorted keys → stable hash). Edits go through `save_config`,
which is the only writer — CLI today, UI later, always writing the same file.

## Aspects (structural requirements only)

- **L3** (interface/packet): `EXISTS`, `RATE`, `DAL`
- **L4** (signal): `TYPE`, `RANGE`, `SCALE`, `UNITS`

Toggle which are generated; override wording per aspect, per interface, or per
signal. Precedence: per-signal → per-interface → global → aspect default.

**The bright line (DO-330):** templates substitute *only* ICD field values. They
transcribe structural facts; they never encode engineering intent. Behavioral
requirements ("when X, signal Y shall be Z") stay human-authored in the RM tool —
reqgen only links to them by ID.

## Provenance

A generated module traces to **three anchors**: the reqgen tool version, the
SHA-256 of the exact ICD it read, and the SHA-256 of the exact config that drove
it. Two inputs, both hashed → reproducible from a known ICD + known config.

## Usage

```bash
pip install -e ./icdgen        # the upstream tool (library dependency)
pip install -e ./reqgen

reqgen -c reqgen.json init                              # create the config file
reqgen -c reqgen.json generate ICD.xml -o out          # -> out/<docid>_requirements.csv
reqgen -c reqgen.json reconcile ICD.xml out/<docid>_requirements.csv
```

`generate` and `reconcile` auto-create the config from defaults if it is absent,
so the first run is one command.

## Exporters

CSV today (universal RM-tool import). Add a format = one entry in
`export.EXPORTERS` (the generator is format-agnostic; requirements are an
intermediate representation). ReqIF or a tool-specific exporter slots in here
once the target RM tool is chosen.

## Tests

```bash
cd reqgen && python -m pytest tests/ -q     # 13 passed
```

## Not yet built (intentional, by sequence)

- **UI** — deferred until the config schema settles; it will be a *view/editor*
  over the config file, never a second source of state.
- **ReqIF / tool-specific export** — pending the target RM tool.
- **Behavioral-requirement linking** — reqgen references human-authored
  requirements by ID; it does not author them.
