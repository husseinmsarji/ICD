"""Requirement-generation config: the schema lives HERE in code (single source
of truth), and the version-controlled config file is *generated from* this
schema. You never hand-write the file from scratch; reqgen writes a fully
populated default, and edits (CLI or UI) round-trip through it.

Design mirrors icdgen's field-registry philosophy: declare the knobs once, derive
the file, the validation, and (later) the UI descriptor from that one place.

THE BRIGHT LINE (DO-330): templates substitute ONLY ICD field values. They
transcribe structural facts (type/range/rate/...); they must never encode
engineering intent. Behavioral requirements stay human-authored in the RM tool.
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
    ),
    AspectSpec(
        key="RANGE", level="L4", label="Signal range",
        fields=("signal", "range_min", "range_max", "units"),
        default_template="The {signal} signal shall represent values in the "
                         "range [{range_min}, {range_max}] {units}.",
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
    ),
)

ASPECTS_BY_KEY: dict[str, AspectSpec] = {a.key: a for a in ASPECTS}
L3_ASPECTS: tuple[str, ...] = tuple(a.key for a in ASPECTS if a.level == "L3")
L4_ASPECTS: tuple[str, ...] = tuple(a.key for a in ASPECTS if a.level == "L4")
GRANULARITIES: tuple[str, ...] = ("packet", "port")


# ---------------------------------------------------------------------------
# CONFIG MODEL — the in-memory shape of the config file. Built by code (the
# default generator below), edited via CLI/UI, serialized to YAML/JSON.
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
