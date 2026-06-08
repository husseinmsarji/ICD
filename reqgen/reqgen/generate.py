"""Generate requirement objects from an ICD model + a ReqConfig.

Pure, deterministic transcription: walk the ICD, for each enabled aspect emit a
Requirement whose ID is a function of the ICD structure (stable across runs) and
whose text is the aspect template with ICD field values substituted.

Precedence (highest wins): per-signal override -> per-interface override ->
global aspect set/template -> aspect default. Only structural facts are
transcribed; nothing here authors engineering intent.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config_schema import ReqConfig, ASPECTS_BY_KEY


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


def _field_values(iface, pkt, sig) -> dict:
    """Flat dict of every substitutable ICD field for the template."""
    vals = {
        "iface": iface.id, "packet": pkt.name if pkt else "",
        "bus_type": iface.bus_type, "dal": iface.dal,
    }
    if sig is not None:
        vals.update({
            "signal": sig.name, "signal_type": sig.signal_type,
            "units": sig.units, "scaling": sig.scaling, "offset": sig.offset,
            "range_min": sig.range_min, "range_max": sig.range_max,
            "update_rate_hz": sig.update_rate_hz,
        })
    elif pkt is not None:
        # L3 rate comes from the packet's signals (use the first signal's rate
        # as the packet rate; structural transcription, not inference).
        rate = next((s.update_rate_hz for s in pkt.signals
                     if s.update_rate_hz is not None), None)
        vals["update_rate_hz"] = rate
    return {k: _fmt_value(v) for k, v in vals.items()}


def _resolve_l3_aspects(cfg: ReqConfig, iface) -> list[str]:
    ov = cfg.interfaces.get(iface.id)
    if ov and ov.l3_aspects is not None:
        return [a for a in ov.l3_aspects if a in ASPECTS_BY_KEY]
    return cfg.l3_aspects


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

        # ---- L3: per-packet (default) or per-port (one per interface) ----
        if cfg.l3_granularity == "packet":
            l3_units = [(iface, pkt) for pkt in iface.packets]
        else:  # "port": collapse to the interface; packet field is blank
            l3_units = [(iface, None)]

        for ifc, pkt in l3_units:
            for aspect in l3_aspects:
                if _is_suppressed(cfg, aspect, ifc.id, None):
                    continue
                vals = _field_values(ifc, pkt, None)
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
                vals = _field_values(iface, pkt, sig)
                for aspect in cfg.l4_aspects:
                    if _is_suppressed(cfg, aspect, iface.id, skey):
                        continue
                    tmpl = _resolve_template(cfg, aspect, iface.id, skey)
                    reqs.append(Requirement(
                        req_id=_make_id(cfg.id_format_l4, cfg, iface, pkt, sig,
                                        aspect),
                        level="L4", aspect=aspect, text=tmpl.format(**vals),
                        iface=iface.id, packet=pkt.name, signal=sig.name,
                    ))
    return reqs
