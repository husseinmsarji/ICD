"""Read / write / hash the version-controlled reqgen config file.

The config FILE is the record of truth. reqgen drives it: `ensure_config` writes
a fully-populated default if none exists, and `save_config` writes edits back to
the SAME file (this is what the CLI and the UI call -- neither holds its own
config state). JSON is used to keep reqgen dependency-free and the output
canonical (sorted keys, fixed separators) so the config hash is stable.

`save_config` is the ONLY writer, so `_validate` is where the rules are
enforced:
  * the bright line -- every template (global, per-interface, per-signal) may
    reference only the placeholders its aspect declares;
  * L3 granularity consistency -- an L3 aspect listed in the enabled set (or an
    interface override) must be VALID at the configured l3_granularity. A "port"
    config may not enable a packet-only aspect like RATE, and a "packet" config
    may not enable a port-only aspect like CONNECT/BUS. This stops a config that
    would silently generate nothing for that aspect (the generator filters it
    out) -- a confusing, hard-to-debug no-op -- and turns it into a clear error.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict

from .config_schema import (
    ReqConfig, InterfaceOverride, SignalOverride, default_config,
    ASPECTS_BY_KEY, GRANULARITIES, ID_FORMAT_TOKENS,
    invalid_placeholders, template_placeholders,
    aspect_valid_at, l3_aspects_for,
)


class ConfigError(Exception):
    """Fatal problem with the config file (bad granularity, unknown aspect,
    a granularity mismatch, or a template that crosses the bright line)."""


def _canonical_json(cfg: ReqConfig) -> str:
    """Deterministic JSON text for a config (sorted keys, stable separators)."""
    return json.dumps(asdict(cfg), indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"


def config_hash(cfg: ReqConfig) -> str:
    """SHA-256 of the canonical config text -- the provenance anchor."""
    return hashlib.sha256(_canonical_json(cfg).encode("utf-8")).hexdigest()


def _check_template(aspect_key: str, template: str, where: str) -> None:
    """Reject a template whose placeholders leave the aspect's allowed set."""
    bad = invalid_placeholders(aspect_key, template)
    if bad:
        allowed = ", ".join(f"{{{f}}}" for f in ASPECTS_BY_KEY[aspect_key].fields)
        shown = ", ".join(f"{{{b}}}" if b else "{}" for b in bad)
        raise ConfigError(
            f"{where}: template for aspect '{aspect_key}' uses placeholder(s) "
            f"{shown} that are not allowed for this aspect. Allowed: "
            f"{allowed or '(none)'}. A requirement may only transcribe its own "
            f"aspect's ICD fields (bright line).")


def _check_id_format(fmt: str, where: str) -> None:
    """Reject an ID format that references unknown tokens."""
    allowed = set(ID_FORMAT_TOKENS)
    bad = [n for n in template_placeholders(fmt)
           if n == "" or n not in allowed]
    if bad:
        shown = ", ".join(f"{{{b}}}" if b else "{}" for b in bad)
        tokens = ", ".join(f"{{{t}}}" for t in ID_FORMAT_TOKENS)
        raise ConfigError(
            f"{where}: ID format uses unknown token(s) {shown}. "
            f"Allowed tokens: {tokens}.")


def _check_l3_granularity_fit(aspect_key: str, granularity: str,
                              where: str) -> None:
    """Reject an L3 aspect that is not valid at the configured granularity."""
    spec = ASPECTS_BY_KEY[aspect_key]
    if spec.level != "L3":
        return
    if not aspect_valid_at(aspect_key, granularity):
        valid = ", ".join(l3_aspects_for(granularity)) or "(none)"
        raise ConfigError(
            f"{where}: L3 aspect '{aspect_key}' is not valid at "
            f"l3_granularity '{granularity}' (it is a "
            f"'{spec.granularity}'-granularity aspect). Aspects valid at "
            f"'{granularity}': {valid}.")


def _validate(cfg: ReqConfig) -> None:
    if cfg.l3_granularity not in GRANULARITIES:
        raise ConfigError(
            f"l3_granularity must be one of {GRANULARITIES}, "
            f"got '{cfg.l3_granularity}'")
    for key in cfg.l3_aspects + cfg.l4_aspects:
        if key not in ASPECTS_BY_KEY:
            raise ConfigError(f"unknown aspect '{key}'")

    # Enabled L3 aspects must be valid at the configured granularity.
    for key in cfg.l3_aspects:
        _check_l3_granularity_fit(key, cfg.l3_granularity, "l3_aspects")

    # ID formats reference only structural tokens.
    _check_id_format(cfg.id_format_l3, "id_format_l3")
    _check_id_format(cfg.id_format_l4, "id_format_l4")

    # Global template overrides: known aspect + bright-line placeholders.
    for key, tmpl in cfg.templates.items():
        if key not in ASPECTS_BY_KEY:
            raise ConfigError(f"template for unknown aspect '{key}'")
        _check_template(key, tmpl, f"templates['{key}']")

    # Per-interface overrides.
    for iface_id, ov in cfg.interfaces.items():
        if ov.l3_aspects is not None:
            for key in ov.l3_aspects:
                if key not in ASPECTS_BY_KEY:
                    raise ConfigError(
                        f"interfaces['{iface_id}'].l3_aspects: unknown aspect "
                        f"'{key}'")
                _check_l3_granularity_fit(
                    key, cfg.l3_granularity,
                    f"interfaces['{iface_id}'].l3_aspects")
        for key in ov.suppress:
            if key not in ASPECTS_BY_KEY:
                raise ConfigError(
                    f"interfaces['{iface_id}'].suppress: unknown aspect '{key}'")
        for key, tmpl in ov.templates.items():
            if key not in ASPECTS_BY_KEY:
                raise ConfigError(
                    f"interfaces['{iface_id}'].templates: unknown aspect '{key}'")
            _check_template(key, tmpl,
                            f"interfaces['{iface_id}'].templates['{key}']")

    # Per-signal overrides.
    for sig_key, ov in cfg.signals.items():
        for key in ov.suppress:
            if key not in ASPECTS_BY_KEY:
                raise ConfigError(
                    f"signals['{sig_key}'].suppress: unknown aspect '{key}'")
        for key, tmpl in ov.templates.items():
            if key not in ASPECTS_BY_KEY:
                raise ConfigError(
                    f"signals['{sig_key}'].templates: unknown aspect '{key}'")
            _check_template(key, tmpl,
                            f"signals['{sig_key}'].templates['{key}']")


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


def config_from_dict(d: dict) -> ReqConfig:
    """Public: rebuild and VALIDATE a ReqConfig from a parsed JSON dict.

    Used by the web layer to turn a posted draft into a config object without
    writing it (preview / pre-save validation). Raises ConfigError on a fatal
    problem, including a bright-line placeholder violation or an L3 aspect that
    does not fit the configured granularity."""
    cfg = _from_dict(d)
    _validate(cfg)
    return cfg


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
    This is how reqgen 'drives the file' -- the user never starts from blank."""
    if os.path.isfile(path):
        return load_config(path)
    cfg = default_config()
    save_config(path, cfg)
    return cfg