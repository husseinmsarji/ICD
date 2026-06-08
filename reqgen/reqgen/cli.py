"""reqgen CLI: init | generate | reconcile.

  init      Create/refresh the version-controlled config file from code defaults.
  generate  ICD + config -> requirements export (and the resolved config hash).
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
from .provenance import TOOL_NAME, TOOL_VERSION, ReqProvenance
from .reconcile import reconcile, render_text


def _eprint(*a):
    print(*a, file=sys.stderr)


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


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
        model, icd_hash, _warns = load(args.icd)
    except ValidationError as exc:
        _eprint(f"ICD VALIDATION ERROR: {exc}")
        return 1
    try:
        cfg = ensure_config(args.config)
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


def cmd_reconcile(args) -> int:
    try:
        model, _icd_hash, _warns = load(args.icd)
    except ValidationError as exc:
        _eprint(f"ICD VALIDATION ERROR: {exc}")
        return 1
    try:
        cfg = ensure_config(args.config)
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
                    "export, reconciliation).")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("-c", "--config", default="reqgen.json",
                   help="config file (created from defaults if absent)")
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

    pr = sub.add_parser("reconcile", help="Diff current reqs vs a prior export.")
    pr.add_argument("icd", help="ICD definition (.xml or .json)")
    pr.add_argument("prior", help="previously exported reqgen CSV")
    pr.set_defaults(func=cmd_reconcile)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
