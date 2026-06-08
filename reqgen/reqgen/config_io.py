"""Read / write / hash the version-controlled reqgen config file.

The config FILE is the record of truth. reqgen drives it: `ensure_config` writes
a fully-populated default if none exists, and `save_config` writes edits back to
the SAME file (this is what the CLI and, later, the UI call — neither holds its
own config state). JSON is used to keep reqgen dependency-free and the output
canonical (sorted keys, fixed separators) so the config hash is stable.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict

from .config_schema import (
    ReqConfig, InterfaceOverride, SignalOverride, default_config,
    ASPECTS_BY_KEY, GRANULARITIES,
)


class ConfigError(Exception):
    """Fatal problem with the config file (bad granularity, unknown aspect...)."""


def _canonical_json(cfg: ReqConfig) -> str:
    """Deterministic JSON text for a config (sorted keys, stable separators)."""
    return json.dumps(asdict(cfg), indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"


def config_hash(cfg: ReqConfig) -> str:
    """SHA-256 of the canonical config text — the provenance anchor."""
    return hashlib.sha256(_canonical_json(cfg).encode("utf-8")).hexdigest()


def _validate(cfg: ReqConfig) -> None:
    if cfg.l3_granularity not in GRANULARITIES:
        raise ConfigError(
            f"l3_granularity must be one of {GRANULARITIES}, "
            f"got '{cfg.l3_granularity}'")
    for key in cfg.l3_aspects + cfg.l4_aspects:
        if key not in ASPECTS_BY_KEY:
            raise ConfigError(f"unknown aspect '{key}'")
    for key in cfg.templates:
        if key not in ASPECTS_BY_KEY:
            raise ConfigError(f"template for unknown aspect '{key}'")


def _from_dict(d: dict) -> ReqConfig:
    """Rebuild a ReqConfig from parsed JSON, restoring nested override types."""
    ifaces = {
        k: InterfaceOverride(
            l3_aspects=v.get("l3_aspects"),
            suppress=list(v.get("suppress", [])),
            templates=dict(v.get("templates", {})),
        )
        for k, v in (d.get("interfaces") or {}).items()
    }
    sigs = {
        k: SignalOverride(
            suppress=list(v.get("suppress", [])),
            templates=dict(v.get("templates", {})),
        )
        for k, v in (d.get("signals") or {}).items()
    }
    base = default_config()
    return ReqConfig(
        config_version=d.get("config_version", base.config_version),
        program_prefix=d.get("program_prefix", base.program_prefix),
        l3_granularity=d.get("l3_granularity", base.l3_granularity),
        l3_aspects=list(d.get("l3_aspects", base.l3_aspects)),
        l4_aspects=list(d.get("l4_aspects", base.l4_aspects)),
        id_format_l3=d.get("id_format_l3", base.id_format_l3),
        id_format_l4=d.get("id_format_l4", base.id_format_l4),
        templates=dict(d.get("templates", {})),
        interfaces=ifaces,
        signals=sigs,
    )


def load_config(path: str) -> ReqConfig:
    """Read and validate the config file. Raises ConfigError on a fatal problem."""
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"config JSON syntax error: {exc.msg} "
                             f"(line {exc.lineno})")
    cfg = _from_dict(data)
    _validate(cfg)
    return cfg


def save_config(path: str, cfg: ReqConfig) -> None:
    """Write the config to the file atomically. This is the ONLY writer; the
    CLI and UI call it so the file stays the single record of truth."""
    _validate(cfg)
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_canonical_json(cfg))
    os.replace(tmp, path)


def ensure_config(path: str) -> ReqConfig:
    """Return the config at `path`, creating a populated default if absent.
    This is how reqgen 'drives the file' — the user never starts from blank."""
    if os.path.isfile(path):
        return load_config(path)
    cfg = default_config()
    save_config(path, cfg)
    return cfg
