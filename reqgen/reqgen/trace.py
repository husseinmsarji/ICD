"""Requirements traceability matrix: ICD elements <-> generated requirements.

This is the completeness-evidence artifact for a certification program: one
row per L3 element (interface/packet) and one row per signal, listing every
requirement ID that covers it. An element with NO covering requirement (because
all of its aspects were suppressed, or skipped by applicability rules — e.g. a
signal with no declared range) is reported as NOT COVERED, so an intentional
gap is a visible line item to be closed by a human-authored requirement in the
RM tool, never a silent omission.

Joins:
  * (Interface ID, Packet, Signal) is the shared key with icdgen's
    traceability matrix, so the two CSVs join into end-to-end
    signal -> requirement -> LRU/DAL/owning-document traceability without
    coupling the two tools' qualification scopes.
  * Requirement ID is the join key into the RM tool (same stable IDs as the
    requirements export).

Deterministic: document order, no timestamps, dual-hash (ICD + config)
provenance in every row, exactly like the requirements export.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from .provenance import ReqProvenance

_HEADERS = [
    "Interface ID", "Packet", "Signal", "Level",
    "Covering Requirement IDs", "Requirement Count", "Coverage",
    "ICD SHA-256", "Config SHA-256",
]

COVERED = "COVERED"
NOT_COVERED = "NOT COVERED"


@dataclass
class TraceRow:
    iface: str
    packet: str
    signal: str          # "" for an L3 row
    level: str           # "L3" | "L4"
    req_ids: list[str] = field(default_factory=list)

    @property
    def covered(self) -> bool:
        return bool(self.req_ids)


def build_trace_rows(model, reqs) -> list[TraceRow]:
    """One row per L3 element and per signal, document order.

    L3 rows are emitted per packet when any requirement carries a packet name,
    plus a per-interface row when port-granularity requirements (blank packet)
    exist for that interface — so the matrix matches whichever granularity the
    config used, without re-reading the config.
    """
    # Index requirements by their structural key.
    by_l3: dict[tuple[str, str], list[str]] = {}
    by_l4: dict[tuple[str, str, str], list[str]] = {}
    for r in reqs:
        if r.level == "L3":
            by_l3.setdefault((r.iface, r.packet), []).append(r.req_id)
        else:
            by_l4.setdefault((r.iface, r.packet, r.signal), []).append(r.req_id)

    port_ifaces = {i for (i, p) in by_l3 if p == ""}

    rows: list[TraceRow] = []
    for iface in model.interfaces:
        if iface.id in port_ifaces:
            rows.append(TraceRow(iface.id, "", "", "L3",
                                 sorted(by_l3.get((iface.id, ""), []))))
        for pkt in iface.packets:
            if iface.id not in port_ifaces:
                rows.append(TraceRow(iface.id, pkt.name, "", "L3",
                                     sorted(by_l3.get((iface.id, pkt.name), []))))
            for sig in pkt.signals:
                rows.append(TraceRow(
                    iface.id, pkt.name, sig.name, "L4",
                    sorted(by_l4.get((iface.id, pkt.name, sig.name), []))))
    return rows


def render_trace_csv(model, reqs, prov: ReqProvenance) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(_HEADERS)
    for row in build_trace_rows(model, reqs):
        w.writerow([
            row.iface, row.packet, row.signal, row.level,
            ";".join(row.req_ids), len(row.req_ids),
            COVERED if row.covered else NOT_COVERED,
            prov.icd_hash, prov.config_hash,
        ])
    return buf.getvalue()


def coverage_summary(rows: list[TraceRow]) -> dict:
    """Counts for the CLI/CI gate: total / covered / uncovered per level."""
    out = {"L3": {"total": 0, "covered": 0, "uncovered": []},
           "L4": {"total": 0, "covered": 0, "uncovered": []}}
    for r in rows:
        bucket = out[r.level]
        bucket["total"] += 1
        if r.covered:
            bucket["covered"] += 1
        else:
            key = f"{r.iface}/{r.packet}" + (f".{r.signal}" if r.signal else "")
            bucket["uncovered"].append(key)
    return out