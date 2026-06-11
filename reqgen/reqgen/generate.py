"""Generate requirement objects from an ICD model + a ReqConfig.

Pure, deterministic transcription: walk the ICD, for each enabled aspect emit a
Requirement whose ID is a function of the ICD structure (stable across runs) and
whose text is the aspect template with ICD field values substituted.

Precedence (highest wins): per-signal override -> per-interface override ->
global aspect set/template -> aspect default. Only structural facts are
transcribed; nothing here authors engineering intent.

L3 GRANULARITY. The L3 (interface) layer is written at one of two granularities,
mirroring the ICD hierarchy:
  * "port"   -> one L3 row per INTERFACE. Aspects that describe the interface /
                port contract between two LRUs (connectivity, bus/protocol, DAL).
  * "packet" -> one L3 row per PACKET. Aspects that describe the per-message
                layer carried on the interface (the packet exists, its refresh
                rate).
An L3 aspect is only emitted when its declared granularity (see AspectSpec.
granularity) matches the active l3_granularity, so a port requirement never
transcribes a packet-only field (e.g. update_rate_hz) and a packet requirement
never transcribes a port-only field (e.g. source_lru/destination_lru). This is
enforced in addition to suppression and applicability.

APPLICABILITY. An aspect is skipped when any field it `requires` is blank in the
ICD, so no vacuous shall-statement (e.g. "range [, ]") is produced; the skipped
element then shows as a coverage gap in the traceability matrix.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config_schema import ReqConfig, ASPECTS_BY_KEY, aspect_valid_at


@dataclass(frozen=True)
class Requirement:
    req_id: str          # stable, derived from ICD structure
    level: str           # "L3" | "L4"
    aspect: str          # aspect key
    text: str            # transcribed requirement text
    iface: str           # source interface id
    packet: str          # source packet name ("" for port-granularity L3)
    signal: str          # source signal name ("" for L3)


def _sanitize(token: str) -> str:
    """IDs use only ID-safe chars; spaces/dots/etc become underscores so the
    derived ID is stable and tool-portable."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(token))


def _fmt_value(v) -> str:
    """Render an ICD field value for template substitution (None -> blank;
    whole floats without trailing .0, matching the rest of the toolchain)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else repr(v)
    return str(v)


def _raw_field_values(iface, pkt, sig) -> dict:
    """Flat dict of every substitutable ICD field, UNFORMATTED (raw model
    values). Used both for applicability checks (is the field present?) and,
    after formatting, for template substitution."""
    vals = {
        "iface": iface.id,
        "packet": pkt.name if pkt else "",
        "bus_type": iface.bus_type,
        "dal": iface.dal,
        "source_lru": iface.source_lru,
        "destination_lru": iface.destination_lru,
        "owning_document": iface.owning_document,
    }
    if sig is not None:
        vals.update({
            "signal": sig.name, "signal_type": sig.signal_type,
            "units": sig.units, "scaling": sig.scaling, "offset": sig.offset,
            "range_min": sig.range_min, "range_max": sig.range_max,
            "update_rate_hz": sig.update_rate_hz,
        })
    elif pkt is not None:
        # L3 @ packet granularity: the packet's refresh rate comes from its
        # signals (use the first signal's rate as the packet rate; structural
        # transcription, not inference).
        rate = next((s.update_rate_hz for s in pkt.signals
                     if s.update_rate_hz is not None), None)
        vals["update_rate_hz"] = rate
    return vals


def _field_values(iface, pkt, sig) -> dict:
    """Formatted field values for template substitution."""
    return {k: _fmt_value(v) for k, v in _raw_field_values(iface, pkt, sig).items()}


def _applicable(aspect_key: str, raw_vals: dict) -> bool:
    """True when every field the aspect `requires` is present (non-blank) in the
    ICD. A missing required field means the requirement would be vacuous, so the
    aspect is skipped (the element surfaces as a trace-matrix coverage gap)."""
    spec = ASPECTS_BY_KEY[aspect_key]
    for fname in spec.requires:
        v = raw_vals.get(fname)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return False
    return True


def _resolve_l3_aspects(cfg: ReqConfig, iface) -> list[str]:
    """The L3 aspects to attempt for this interface, filtered to those VALID at
    the active granularity. Granularity filtering happens here (not just in the
    UI) so the CLI and any direct API caller are correct too."""
    ov = cfg.interfaces.get(iface.id)
    base = ov.l3_aspects if (ov and ov.l3_aspects is not None) else cfg.l3_aspects
    return [a for a in base
            if a in ASPECTS_BY_KEY
            and aspect_valid_at(a, cfg.l3_granularity)]


def _resolve_template(cfg: ReqConfig, aspect: str, iface_id: str,
                      signal_key: str | None) -> str:
    """Per-signal override -> per-interface override -> global -> default."""
    if signal_key and signal_key in cfg.signals:
        t = cfg.signals[signal_key].templates.get(aspect)
        if t is not None:
            return t
    ov = cfg.interfaces.get(iface_id)
    if ov and aspect in ov.templates:
        return ov.templates[aspect]
    return cfg.template_for(aspect)


def _is_suppressed(cfg: ReqConfig, aspect: str, iface_id: str,
                   signal_key: str | None) -> bool:
    if signal_key and signal_key in cfg.signals:
        if aspect in cfg.signals[signal_key].suppress:
            return True
    ov = cfg.interfaces.get(iface_id)
    if ov and aspect in ov.suppress:
        return True
    return False


def _make_id(fmt: str, cfg: ReqConfig, iface, pkt, sig, aspect: str) -> str:
    return fmt.format(
        prefix=cfg.program_prefix,
        iface=_sanitize(iface.id),
        packet=_sanitize(pkt.name) if pkt else "",
        signal=_sanitize(sig.name) if sig else "",
        aspect=aspect,
    )


def generate_requirements(model, cfg: ReqConfig) -> list[Requirement]:
    """Return all generated requirements in deterministic document order."""
    reqs: list[Requirement] = []

    for iface in model.interfaces:
        l3_aspects = _resolve_l3_aspects(cfg, iface)

        # ---- L3: per-packet (packet granularity) or per-interface (port) ----
        if cfg.l3_granularity == "packet":
            l3_units = [(iface, pkt) for pkt in iface.packets]
        else:  # "port": collapse to the interface; packet field is blank
            l3_units = [(iface, None)]

        for ifc, pkt in l3_units:
            raw = _raw_field_values(ifc, pkt, None)
            vals = {k: _fmt_value(v) for k, v in raw.items()}
            for aspect in l3_aspects:
                if _is_suppressed(cfg, aspect, ifc.id, None):
                    continue
                if not _applicable(aspect, raw):
                    continue
                tmpl = _resolve_template(cfg, aspect, ifc.id, None)
                reqs.append(Requirement(
                    req_id=_make_id(cfg.id_format_l3, cfg, ifc, pkt, None, aspect),
                    level="L3", aspect=aspect, text=tmpl.format(**vals),
                    iface=ifc.id, packet=(pkt.name if pkt else ""), signal="",
                ))

        # ---- L4: per-signal ----
        for pkt in iface.packets:
            for sig in pkt.signals:
                skey = f"{iface.id}/{pkt.name}/{sig.name}"
                raw = _raw_field_values(iface, pkt, sig)
                vals = {k: _fmt_value(v) for k, v in raw.items()}
                for aspect in cfg.l4_aspects:
                    if aspect not in ASPECTS_BY_KEY:
                        continue
                    if _is_suppressed(cfg, aspect, iface.id, skey):
                        continue
                    if not _applicable(aspect, raw):
                        continue
                    tmpl = _resolve_template(cfg, aspect, iface.id, skey)
                    reqs.append(Requirement(
                        req_id=_make_id(cfg.id_format_l4, cfg, iface, pkt, sig,
                                        aspect),
                        level="L4", aspect=aspect, text=tmpl.format(**vals),
                        iface=iface.id, packet=pkt.name, signal=sig.name,
                    ))
    return reqs