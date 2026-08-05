# reqgen

Deterministic **requirement generator** that sits *beside* `icdgen`, not inside
it. It reads an icdgen ICD (the canonical XML/JSON) as a library input and emits
a requirements module for an RM tool (DOORS / Jama / Polarion / etc.), a
**requirements-to-signals traceability matrix**, and a reconciliation report. It
never writes back into the ICD and shares no mutable state with icdgen, so the
two tools keep **independent DO-330 qualification scopes**.

> The authoritative architecture map is [`../AI_README.md`](../AI_README.md)
> (see §9.6 on L3 granularity and §9.7 on the trace matrix).

## What it does

1. **`init`** — writes a fully-populated config file from code defaults. You do
   not hand-author the file; reqgen drives it.
2. **`generate`** — ICD + config → a requirements export. Every requirement has
   a **stable ID derived from the ICD structure**, so regeneration is idempotent
   and an RM-tool import updates in place.
3. **`trace`** — ICD + config → a requirements-to-signals traceability matrix
   plus a coverage summary. This is the **completeness artifact**: any element
   with no covering requirement shows as a visible gap. `trace` exits **2** on
   any gap (a CI gate), **1** on input error, **0** when fully covered.
4. **`reconcile`** — ICD + config + a prior export → a four-state report
   (added / removed / changed / unchanged) telling you exactly which RM objects
   to create, retire, or update after an ICD or config change.

## Aspects (structural requirements only)

Aspects are structural requirement types in a registry (`config_schema.py`, in
the same spirit as icdgen's field registry). The **L3 (interface) layer is
granularity-aware**, mirroring the ICD hierarchy:

- **L3, port granularity** — one requirement *per interface* (the port
  contract): `CONNECT` (source→destination LRUs), `BUS` (bus/protocol), `DAL`.
- **L3, packet granularity** — one requirement *per packet* (the message layer):
  `EXISTS` (the packet is provided over the bus), `RATE` (refresh rate — a
  per-message property), `DAL`.
- **L4 (signal)**: `TYPE`, `RANGE`, `SCALE`, `UNITS`.

Each `AspectSpec` declares a `granularity` (`port` / `packet` / `both`).
`generate` only emits an L3 aspect when its granularity matches the active
`l3_granularity`, and `save_config` **rejects** a config that lists an L3 aspect
invalid at its granularity (a "port" config naming `RATE` is a clear error, not
a silent no-op). The default config is packet granularity with
`l3_aspects = [EXISTS, DAL]`.

Toggle which aspects are generated; override wording per aspect, per interface,
or per signal. Precedence: per-signal → per-interface → global → aspect default.

### Applicability (no vacuous requirements)

`AspectSpec.requires` declares which ICD fields must be present for an aspect to
emit (RANGE needs both bounds, TYPE a type, RATE a rate, UNITS units).
`generate` skips an aspect whose required fields are blank instead of emitting
"range [, ]"; the skipped element then shows as a trace-matrix gap to close with
a human-authored requirement. This is what makes the trace matrix a real
completeness check rather than a rubber stamp.

**The bright line (DO-330):** templates substitute *only* ICD field values. They
transcribe structural facts; they never encode engineering intent. Behavioral
requirements ("when X, signal Y shall be Z") stay human-authored in the RM tool —
reqgen only links to them by ID.

## The config drives the file

The config *schema* lives in code (`config_schema.py`). The version-controlled
config *file* is generated from it (`config_io.ensure_config`) and round-trips
deterministically (canonical JSON, sorted keys → stable hash). Edits go through
`save_config`, the only writer — CLI or web UI, always writing the same file,
enforcing both the bright line and the L3 granularity-consistency rule.

## Provenance

A generated module traces to **three anchors**: the reqgen tool version, the
SHA-256 of the exact ICD it read, and the SHA-256 of the exact config that drove
it. Two inputs, both hashed → reproducible from a known ICD + known config. The
trace matrix carries the same dual hash per row, and shares its join key
`(Interface ID, Packet, Signal)` with icdgen's traceability matrix, so the two
CSVs join into end-to-end signal → requirement → LRU/DAL traceability.

## Config location (baked into the code)

The config of record lives at **`reqgen/config/reqgen.json`** — a `config/`
folder inside the reqgen project (alongside `pyproject.toml`), NOT at the repo
root. It is a version-controlled qualification artifact.

- The CLI resolves the default relative to the reqgen package itself
  (`paths.py`), so it points at `reqgen/config/reqgen.json` regardless of the
  current directory.
- `init` creates that file (and the `config/` folder) on first run.
- Override with `$REQGEN_CONFIG` or an explicit `-c PATH`.

Commit `reqgen/config/reqgen.json`: the dual-hash provenance is only meaningful
if the config a requirement traces to is itself under configuration control.

## Layout requirement

The importable package is the **inner** `reqgen/reqgen/` folder (same
double-nesting as `icdgen/icdgen/`). `pyproject.toml` declares
`packages = ["reqgen"]`, so a flattened tree fails to install with a clear error
rather than shipping a broken command. `test_package_is_properly_nested` guards
this in CI.

## Usage

```bash
pip install -e ./icdgen        # the upstream tool (library dependency)
pip install -e ./reqgen

reqgen init                                          # creates config/reqgen.json from defaults
reqgen generate ICD.xml -o out                       # -> out/<docid>_requirements.csv
reqgen trace    ICD.xml -o out                       # -> out/<docid>_req_trace.csv (exit 2 on gaps)
reqgen reconcile ICD.xml out/<docid>_requirements.csv
```

`generate` / `trace` / `reconcile` auto-create the config from defaults if it is
absent, so the first run is one command. Pass `-c PATH` to point at a
non-standard location. For example, revC produces 80 requirements and a 40-row
trace matrix (L3 9/9, L4 31/31 covered).

## Web UI

reqgen is surfaced as the **Requirements** tab of the `icdweb` editor: edit the
config, see a live requirements preview, view the coverage/traceability matrix
(All rows / Gaps only) with a CSV download, and run reconcile. The UI remains a
*view/editor* over the config file — never a second source of state.

## Exporters

CSV today (universal RM-tool import). Add a format = one entry in
`export.EXPORTERS`; the generator is format-agnostic (requirements are an
intermediate representation). ReqIF or a tool-specific exporter slots in here
once the target RM tool is chosen.

## Tests

```bash
# from the repo root, with icdgen installed:
cd icdgen && PYTHONPATH=../reqgen python -m pytest ../reqgen/tests/ -q     # 25 passed
```

Covers the aspect registry, the L3 port/packet granularity model, applicability,
the trace matrix + coverage, reconciliation, provenance, and the layout guard.

## Not yet built (intentional, by sequence)

- **ReqIF / tool-specific export** — pending the target RM tool.
- **Behavioral-requirement linking** — reqgen references human-authored
  requirements by ID; it does not author them.
