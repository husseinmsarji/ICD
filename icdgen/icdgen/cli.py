"""icdgen command-line interface.

Subcommands:
  validate   Validate an input file (exit 1 on FATAL error; warnings printed).
  generate   Validate then emit all artifacts to an output directory.
  diff       Compare two input files and emit a diff report.

Non-fatal warnings (e.g. missing signal type, non-C-identifier name) are printed
to stderr but do not change the exit code, so partially-complete ICDs still work.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys

from . import gen_code, gen_docx, gen_pdf, gen_trace
from .diff import diff as diff_models
from .diff import render_csv as diff_csv
from .diff import render_text as diff_text
from .loader import ValidationError, load
from .provenance import TOOL_NAME, TOOL_VERSION, Provenance


def _eprint(*a):
    print(*a, file=sys.stderr)


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def cmd_validate(args) -> int:
    try:
        model, file_hash, warnings = load(args.input)
    except ValidationError as exc:
        _eprint(f"VALIDATION ERROR: {exc}")
        return 1
    n_sig = sum(len(p.signals) for i in model.interfaces for p in i.packets)
    n_pkt = sum(len(i.packets) for i in model.interfaces)
    print(f"OK: {args.input}")
    print(f"  schema version : {model.schema_version}")
    print(f"  interfaces     : {len(model.interfaces)}")
    print(f"  packets        : {n_pkt}")
    print(f"  signals        : {n_sig}")
    print(f"  input SHA-256  : {file_hash}")
    for w in warnings:
        _eprint(f"  WARNING: {w.message}")
    return 0


def cmd_generate(args) -> int:
    try:
        model, file_hash, warnings = load(args.input)
    except ValidationError as exc:
        _eprint(f"VALIDATION ERROR: {exc}")
        return 1
    for w in warnings:
        _eprint(f"WARNING: {w.message}")

    prov = Provenance.create(file_hash, model.schema_version)
    out = args.output
    os.makedirs(out, exist_ok=True)
    base = model.metadata.document_id

    produced = []

    formats = set(args.formats)
    if "header" in formats:
        p = os.path.join(out, f"{base}.h")
        _write(p, gen_code.render_header(model, prov))
        produced.append(p)
    if "simulink" in formats:
        p = os.path.join(out, f"{base}_bus.m")
        _write(p, gen_code.render_simulink(model, prov))
        produced.append(p)
    if "trace-csv" in formats:
        p = os.path.join(out, f"{base}_traceability.csv")
        _write(p, gen_trace.render_csv(model, prov))
        produced.append(p)
    if "trace-xlsx" in formats:
        p = os.path.join(out, f"{base}_traceability.xlsx")
        gen_trace.write_xlsx(model, prov, p)
        produced.append(p)
    if "docx" in formats:
        p = os.path.join(out, f"{base}.docx")
        gen_docx.build_docx(model, prov, p)
        produced.append(p)
    if "pdf" in formats:
        p = os.path.join(out, f"{base}.pdf")
        gen_pdf.build_pdf(model, prov, p)
        produced.append(p)

    _write_run_log(out, args.input, prov, produced)
    print(f"Generated {len(produced)} artifact(s) in {out}:")
    for p in produced:
        print(f"  {os.path.basename(p)}")
    return 0


def cmd_diff(args) -> int:
    try:
        old_model, old_hash, _ = load(args.old)
        new_model, new_hash, _ = load(args.new)
    except ValidationError as exc:
        _eprint(f"VALIDATION ERROR: {exc}")
        return 1

    result = diff_models(old_model, new_model)
    text = diff_text(result, old_hash, new_hash)

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        base = new_model.metadata.document_id
        txt_path = os.path.join(args.output, f"{base}_diff.txt")
        csv_path = os.path.join(args.output, f"{base}_diff.csv")
        _write(txt_path, text)
        _write(csv_path, diff_csv(result))
        print(f"Diff written to {txt_path} and {csv_path}")
    else:
        print(text, end="")

    return 2 if result.has_changes else 0


def _write_run_log(out_dir: str, input_path: str, prov: Provenance,
                   produced: list[str]) -> None:
    log_path = os.path.join(out_dir, "run.log")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = [
        f"timestamp_utc   : {now}",
        f"tool            : {prov.tool_name} v{prov.tool_version}",
        f"input_file      : {os.path.abspath(input_path)}",
        f"input_sha256    : {prov.input_hash}",
        f"schema_version  : {prov.schema_version}",
        "artifacts:",
    ]
    lines += [f"  - {os.path.basename(p)}" for p in produced]
    with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n---\n")


ALL_FORMATS = ["docx", "pdf", "header", "simulink", "trace-csv", "trace-xlsx"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description=f"{TOOL_NAME} v{TOOL_VERSION} - deterministic ICD artifact "
                    "generator for certifiable avionics (ARP4754A / DO-178C / "
                    "DO-254). DO-330 tool-qualification provenance is stamped "
                    "into every artifact.")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    pv = sub.add_parser("validate", help="Validate an input file.")
    pv.add_argument("input", help="Input ICD definition (.xml or .json)")
    pv.set_defaults(func=cmd_validate)

    pg = sub.add_parser("generate", help="Generate artifacts.")
    pg.add_argument("input", help="Input ICD definition (.xml or .json)")
    pg.add_argument("-o", "--output", default="icd_out",
                    help="Output directory (default: ./icd_out)")
    pg.add_argument("-f", "--formats", nargs="+", choices=ALL_FORMATS,
                    default=ALL_FORMATS,
                    help="Subset of artifacts to generate (default: all)")
    pg.set_defaults(func=cmd_generate)

    pd = sub.add_parser("diff", help="Diff two input versions.")
    pd.add_argument("old", help="Previous input file")
    pd.add_argument("new", help="New input file")
    pd.add_argument("-o", "--output", default=None,
                    help="Output directory for diff report (default: stdout)")
    pd.set_defaults(func=cmd_diff)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())