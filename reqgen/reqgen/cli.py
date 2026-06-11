"""reqgen CLI: init | generate | trace | reconcile.

  init      Create/refresh the version-controlled config file from code defaults.
  generate  ICD + config -> requirements export (and the resolved config hash).
  trace     ICD + config -> requirements traceability matrix (signal <->
            requirement IDs, with NOT COVERED gaps). Exit 2 when any ICD
            element has no covering requirement, so CI can gate a release on
            full structural coverage.
  reconcile ICD + config + prior export -> four-state change report.

reqgen imports icdgen as a library; it never mutates the ICD.
"""
from __future__ import annotations

import argparse
import os
import sys

from icdgen.loader import ValidationError, load

from .config_io import ConfigError, config_hash, ensure_config, load_config
from .export import EXPORTERS
from .generate import generate_requirements
from .paths import ENV_VAR, default_config_path
from .provenance import TOOL_NAME, TOOL_VERSION, ReqProvenance
from .reconcile import reconcile, render_text
from .trace import build_trace_rows, coverage_summary, render_trace_csv


def _eprint(*a):
    print(*a, file=sys.stderr)


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _load_inputs(args):
    """(model, icd_hash, cfg) or raises SystemExit-style int via caller."""
    model, icd_hash, _warns = load(args.icd)
    cfg = ensure_config(args.config)
    return model, icd_hash, cfg


def cmd_init(args) -> int:
    """Drive the config file: write a populated default if it doesn't exist."""
    existed = os.path.isfile(args.config)
    cfg = ensure_config(args.config)
    verb = "exists" if existed else "created"
    print(f"Config {verb}: {args.config}")
    print(f"  L3 granularity : {cfg.l3_granularity}")
    print(f"  L3 aspects     : {', '.join(cfg.l3_aspects)}")
    print(f"  L4 aspects     : {', '.join(cfg.l4_aspects)}")
    print(f"  config SHA-256 : {config_hash(cfg)}")
    return 0


def cmd_generate(args) -> int:
    try:
        model, icd_hash, cfg = _load_inputs(args)
    except ValidationError as exc:
        _eprint(f"ICD VALIDATION ERROR: {exc}")
        return 1
    except ConfigError as exc:
        _eprint(f"CONFIG ERROR: {exc}")
        return 1

    prov = ReqProvenance.create(icd_hash, config_hash(cfg))
    reqs = generate_requirements(model, cfg)
    suffix, exporter = EXPORTERS[args.format]
    text = exporter(reqs, prov)

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        base = model.metadata.document_id
        path = os.path.join(args.output, f"{base}_requirements{suffix}")
        _write(path, text)
        print(f"Generated {len(reqs)} requirement(s) -> {path}")
        print(f"  ICD SHA-256    : {prov.icd_hash}")
        print(f"  config SHA-256 : {prov.config_hash}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_trace(args) -> int:
    """Requirements traceability matrix + coverage gate.

    Exit codes: 0 = full coverage, 1 = input error, 2 = coverage gaps exist
    (mirrors `icdgen diff`'s changes-found convention for CI gating).
    """
    try:
        model, icd_hash, cfg = _load_inputs(args)
    except ValidationError as exc:
        _eprint(f"ICD VALIDATION ERROR: {exc}")
        return 1
    except ConfigError as exc:
        _eprint(f"CONFIG ERROR: {exc}")
        return 1

    prov = ReqProvenance.create(icd_hash, config_hash(cfg))
    reqs = generate_requirements(model, cfg)
    rows = build_trace_rows(model, reqs)
    text = render_trace_csv(model, reqs, prov)

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        base = model.metadata.document_id
        path = os.path.join(args.output, f"{base}_req_trace.csv")
        _write(path, text)
        print(f"Trace matrix ({len(rows)} row(s)) -> {path}")
    else:
        sys.stdout.write(text)

    summary = coverage_summary(rows)
    gaps = 0
    for level in ("L3", "L4"):
        s = summary[level]
        gaps += len(s["uncovered"])
        _eprint(f"{level}: {s['covered']}/{s['total']} covered")
        for key in s["uncovered"]:
            _eprint(f"  NOT COVERED: {key}")
    return 2 if gaps else 0


def cmd_reconcile(args) -> int:
    try:
        model, _icd_hash, cfg = _load_inputs(args)
    except ValidationError as exc:
        _eprint(f"ICD VALIDATION ERROR: {exc}")
        return 1
    except ConfigError as exc:
        _eprint(f"CONFIG ERROR: {exc}")
        return 1
    with open(args.prior, encoding="utf-8") as fh:
        prior_csv = fh.read()
    reqs = generate_requirements(model, cfg)
    rec = reconcile(reqs, prior_csv)
    sys.stdout.write(render_text(rec))
    return 2 if rec.has_changes else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description=f"{TOOL_NAME} v{TOOL_VERSION} - deterministic requirement "
                    "generator over an icdgen ICD (config-driven, RM-tool "
                    "export, traceability matrix, reconciliation).")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("-c", "--config", default=None,
                   help=f"config file. Default: the conventional "
                        f"config/reqgen.json inside the reqgen project "
                        f"(override with ${ENV_VAR}). Created from defaults "
                        f"if absent.")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("init", help="Create/refresh the config file.")
    pi.set_defaults(func=cmd_init)

    pg = sub.add_parser("generate", help="Generate a requirements export.")
    pg.add_argument("icd", help="ICD definition (.xml or .json)")
    pg.add_argument("-o", "--output", default=None,
                    help="output dir (default: stdout)")
    pg.add_argument("-f", "--format", default="csv", choices=list(EXPORTERS),
                    help="export format (default: csv)")
    pg.set_defaults(func=cmd_generate)

    pt = sub.add_parser("trace",
                        help="Requirements traceability matrix + coverage "
                             "gate (exit 2 on gaps).")
    pt.add_argument("icd", help="ICD definition (.xml or .json)")
    pt.add_argument("-o", "--output", default=None,
                    help="output dir (default: stdout)")
    pt.set_defaults(func=cmd_trace)

    pr = sub.add_parser("reconcile", help="Diff current reqs vs a prior export.")
    pr.add_argument("icd", help="ICD definition (.xml or .json)")
    pr.add_argument("prior", help="previously exported reqgen CSV")
    pr.set_defaults(func=cmd_reconcile)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "config", None) is None:
        args.config = default_config_path()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())