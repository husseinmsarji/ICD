"""Pluggable exporters for a generated requirement set.

Requirements are an intermediate representation; exporters serialize them to
whatever the RM tool ingests. CSV is the universal fallback (every RM tool
imports it); ReqIF or tool-specific exporters can be added without touching the
generator. All exporters are deterministic (no timestamps, stable ordering).
"""
from __future__ import annotations

import csv
import hashlib
import io

from .provenance import ReqProvenance


def _content_hash(text: str) -> str:
    """Short hash of requirement text, so an RM-side import can detect 'text
    changed' vs 'unchanged' by ID without storing full history."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def to_csv(reqs, prov: ReqProvenance) -> str:
    """One row per requirement. Columns chosen for generic RM-tool import:
    the stable ID is the join key; ContentHash drives reconciliation; the
    provenance hashes travel in every row for traceability."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([
        "Requirement ID", "Level", "Aspect", "Text",
        "Interface", "Packet", "Signal",
        "Content Hash", "ICD SHA-256", "Config SHA-256",
    ])
    for r in reqs:
        w.writerow([
            r.req_id, r.level, r.aspect, r.text,
            r.iface, r.packet, r.signal,
            _content_hash(r.text), prov.icd_hash, prov.config_hash,
        ])
    return buf.getvalue()


# Exporter registry: format key -> (file suffix, callable). Adding a format is
# one entry here (mirrors icdgen's ARTIFACT_BUILDERS pattern).
EXPORTERS = {
    "csv": (".csv", to_csv),
}
