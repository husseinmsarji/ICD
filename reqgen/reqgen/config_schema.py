"""Requirement-generation config: the schema lives HERE in code (single source
of truth), and the version-controlled config file is *generated from* this
schema. You never hand-write the file from scratch; reqgen writes a fully
populated default, and edits (CLI or UI) round-trip through it.

Design mirrors icdgen's field-registry philosophy: declare the knobs once, derive
the file, the validation, and the UI descriptor from that one place.

THE BRIGHT LINE (DO-330): templates substitute ONLY ICD field values. They
transcribe structural facts (type/range/rate/...); they must never encode
engineering intent. Behavioral requirements stay human-authored in the RM tool.

Each aspect declares the exact ICD fields it is ALLOWED to transcribe (its
`fields`). The UI and the save path enforce that a template's {placeholders}
stay within that set (plus the structural ID tokens), so a TYPE requirement can
never quietly start pulling in, say, {dal} — that would cross the bright line.

APPLICABILITY (`requires`): each aspect also declares which of its fields must
be PRESENT (non-blank) in the ICD for the requirement to be emitted. A signal
with no range must not produce "shall represent values in the range [, ]" — a
vacuous shall-statement is a certification finding. The generator skips the
aspect instead, and the trace matrix (reqgen trace) reports the element as a
coverage gap so the omission is visible, never silent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# ASPECT REGISTRY — the catalog of structural requirements reqgen can derive.
# Each aspect names the ICD field(s) it transcribes and ships a default
# template. Adding an aspect is a one-entry change here; it then flows to the
# default config, the resolver, and the UI descriptor.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AspectSpec:
    key: str                 # stable token used in IDs and config (e.g. "RANGE")
    level: str               # "L3" (interface/packet) or "L4" (signal)
    label: str               # human label for the UI
    fields: tuple[str, ...]  # ICD model attributes this aspect transcribes
    default_template: str    # default wording; {placeholders} are ICD fields
    default_on: bool = True  # generated unless a config/override disables it
    requires: tuple[str, ...] = ()  # fields that must be non-blank to emit


# L3 = the interface/packet contract between LRUs.
# L4 = the encoding/behavior of an individual signal.
ASPECTS: tuple[AspectSpec, ...] = (
    # ---- L3 (interface / packet granularity) ----
    AspectSpec(
        key="EXISTS", level="L3", label="Packet exists",
        fields=("iface", "packet", "bus_type"),
        default_template="The {iface} interface shall provide the {packet} "
                         "packet over {bus_type}.",
    ),
    AspectSpec(
        key="RATE", level="L3", label="Packet rate",
        fields=("packet", "update_rate_hz"),
        default_template="The {packet} packet shall be transmitted at "
                         "{update_rate_hz} Hz.",
        default_on=False,   # many programs fold rate into EXISTS; off by default
        requires=("update_rate_hz",),
    ),
    AspectSpec(
        key="DAL", level="L3", label="Assurance level",
        fields=("iface", "dal"),
        default_template="The {iface} interface shall be developed to DAL "
                         "{dal}.",
    ),
    # ---- L4 (signal granularity) ----
    AspectSpec(
        key="TYPE", level="L4", label="Signal data type",
        fields=("signal", "signal_type"),
        default_template="The {signal} signal shall be encoded as "
                         "{signal_type}.",
        requires=("signal_type",),
    ),
    AspectSpec(
        key="RANGE", level="L4", label="Signal range",
        fields=("signal", "range_min", "range_max", "units"),
        default_template="The {signal} signal shall represent values in the "
                         "range [{range_min}, {range_max}] {units}.",
        requires=("range_min", "range_max"),
    ),
    AspectSpec(
        key="SCALE", level="L4", label="Signal scaling",
        fields=("signal", "scaling", "offset"),
        default_template="The {signal} signal shall apply a scale of {scaling} "
                         "and an offset of {offset}.",
        default_on=False,   # only meaningful for scaled signals
    ),
    AspectSpec(
        key="UNITS", level="L4", label="Signal units",
        fields=("signal", "units"),
        default_template="The {signal} signal shall be expressed in {units}.",
        default_on=False,   # usually folded into RANGE; off by default
        requires=("units",),
    ),
)

ASPECTS_BY_KEY: dict[str, AspectSpec] = {a.key: a for a in ASPECTS}
L3_ASPECTS: tuple[str, ...] = tuple(a.key for a in ASPECTS if a.level == "L3")
L4_ASPECTS: tuple[str, ...] = tuple(a.key for a in ASPECTS if a.level == "L4")
GRANULARITIES: tuple[str, ...] = ("packet", "port")

# ID-format tokens. These are structural locators (not ICD content), so they
# are always allowed in an id_format string regardless of aspect.
ID_FORMAT_TOKENS: tuple[str, ...] = (
    "prefix", "iface", "packet", "signal", "aspect",
)


# ---------------------------------------------------------------------------
# CONFIG MODEL — the in-memory shape of the config file. Built by code (the
# default generator below), edited via CLI/UI, serialized to JSON.
# ---------------------------------------------------------------------------
@dataclass
class SignalOverride:
    """Per-signal tweaks, keyed in config by 'IFACE/PACKET/signal'."""
    suppress: list[str] = field(default_factory=list)     # aspect keys to skip
    templates: dict[str, str] = field(default_factory=dict)  # aspect -> wording


@dataclass
class InterfaceOverride:
    """Per-interface tweaks, keyed in config by interface id."""
    l3_aspects: Optional[list[str]] = None    # replace the global L3 aspect set
    suppress: list[str] = field(default_factory=list)
    templates: dict[str, str] = field(default_factory=dict)


@dataclass
class ReqConfig:
    """The full requirement-generation profile."""
    config_version: str = "1.0"
    program_prefix: str = "REQ"
    l3_granularity: str = "packet"            # "packet" | "port"
    l3_aspects: list[str] = field(default_factory=lambda: list(
        a.key for a in ASPECTS if a.level == "L3" and a.default_on))
    l4_aspects: list[str] = field(default_factory=lambda: list(
        a.key for a in ASPECTS if a.level == "L4" and a.default_on))
    id_format_l3: str = "{prefix}-L3-{iface}-{packet}-{aspect}"
    id_format_l4: str = "{prefix}-L4-{iface}-{packet}-{signal}-{aspect}"
    templates: dict[str, str] = field(default_factory=dict)   # aspect -> override
    interfaces: dict[str, InterfaceOverride] = field(default_factory=dict)
    signals: dict[str, SignalOverride] = field(default_factory=dict)

    def template_for(self, aspect_key: str) -> str:
        """Resolved default-or-global-override template (before per-entry)."""
        return self.templates.get(aspect_key,
                                  ASPECTS_BY_KEY[aspect_key].default_template)


def default_config() -> ReqConfig:
    """A complete, valid config built from the aspect registry. This is what
    reqgen writes when no config file exists yet — so the user never starts from
    a blank file."""
    return ReqConfig()


# ---------------------------------------------------------------------------
# Bright-line placeholder enforcement.
#
# A template may only reference the placeholders its aspect declares. The L3
# `iface`/`packet`/`bus_type`/`dal` and L4 `signal`/... names come from the
# aspect's `fields`. This is the mechanism that keeps a TYPE requirement from
# silently transcribing, e.g., {dal}: the field is not in TYPE.fields, so a
# template using it is rejected (see config_io._validate / the web layer).
# ---------------------------------------------------------------------------
import string as _string


def template_placeholders(template: str) -> list[str]:
    """Return the {placeholder} names referenced by a template string.

    Uses the same parser as str.format, so it sees exactly what generation will
    try to substitute. Positional/empty fields ('{}') are reported as '' so the
    caller can reject them (generation needs named fields).
    """
    names: list[str] = []
    for _literal, field_name, _spec, _conv in _string.Formatter().parse(template):
        if field_name is None:
            continue
        # Take the base name before any attribute/index access ('a.b' -> 'a').
        base = field_name.split(".")[0].split("[")[0]
        names.append(base)
    return names


def allowed_placeholders(aspect_key: str) -> tuple[str, ...]:
    """The placeholders a template for this aspect may use."""
    return ASPECTS_BY_KEY[aspect_key].fields


def invalid_placeholders(aspect_key: str, template: str) -> list[str]:
    """Placeholders in `template` that are NOT allowed for `aspect_key`.

    An empty list means the template is bright-line-clean. A non-empty list is
    the set of offending names (including '' for a bare '{}'). The caller turns
    this into a fatal ConfigError on save and a preview guard.
    """
    allowed = set(allowed_placeholders(aspect_key))
    bad: list[str] = []
    for name in template_placeholders(template):
        if name == "" or name not in allowed:
            if name not in bad:
                bad.append(name)
    return bad


# ---------------------------------------------------------------------------
# UI / API descriptor: JSON-serializable description of the config schema,
# consumed by the reqgen editor so it builds itself from the aspect registry
# (adding an aspect here surfaces it in the UI with no UI edit), exactly like
# icdgen.fields.signal_fields_descriptor() drives the ICD form.
# ---------------------------------------------------------------------------
def config_descriptor() -> dict:
    """Everything the UI needs to render and validate the config editor."""
    aspects = []
    for a in ASPECTS:
        aspects.append({
            "key": a.key,
            "level": a.level,
            "label": a.label,
            "fields": list(a.fields),            # = allowed template placeholders
            "requires": list(a.requires),        # fields gating applicability
            "defaultTemplate": a.default_template,
            "defaultOn": a.default_on,
        })
    return {
        "aspects": aspects,
        "l3Aspects": list(L3_ASPECTS),
        "l4Aspects": list(L4_ASPECTS),
        "granularities": list(GRANULARITIES),
        "idFormatTokens": list(ID_FORMAT_TOKENS),
        # Default formats so the UI can offer a one-click "reset to default".
        "defaultIdFormatL3": ReqConfig().id_format_l3,
        "defaultIdFormatL4": ReqConfig().id_format_l4,
    }