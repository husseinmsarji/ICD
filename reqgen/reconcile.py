"""Reconcile a freshly-generated requirement set against a previously-exported
one (e.g. what's already loaded in the RM tool). The four-state report is the
high-value output: it tells an engineer exactly which RM objects to add, update,
or retire after an ICD or config change.

Matching is by stable Requirement ID; change detection is by text. Both come
free from the generator's deterministic IDs.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field


@dataclass
class Reconciliation:
    added: list[str] = field(default_factory=list)      # new IDs
    removed: list[str] = field(default_factory=list)    # orphaned IDs
    changed: list[tuple[str, str, str]] = field(default_factory=list)  # id,old,new
    unchanged: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def _prior_index(prior_csv: str) -> dict[str, str]:
    """Map req_id -> text from a previously-exported reqgen CSV."""
    out: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(prior_csv))
    for row in reader:
        rid = row.get("Requirement ID")
        if rid:
            out[rid] = row.get("Text", "")
    return out


def reconcile(reqs, prior_csv: str) -> Reconciliation:
    """Compare current requirements against a prior export (CSV text)."""
    prior = _prior_index(prior_csv)
    current = {r.req_id: r.text for r in reqs}
    rec = Reconciliation()
    for rid in sorted(set(current) | set(prior)):
        if rid in current and rid not in prior:
            rec.added.append(rid)
        elif rid in prior and rid not in current:
            rec.removed.append(rid)
        elif current[rid] != prior[rid]:
            rec.changed.append((rid, prior[rid], current[rid]))
        else:
            rec.unchanged.append(rid)
    return rec


def render_text(rec: Reconciliation) -> str:
    lines = ["REQUIREMENT RECONCILIATION REPORT", ""]
    lines.append(f"  added:     {len(rec.added)}")
    lines.append(f"  removed:   {len(rec.removed)}")
    lines.append(f"  changed:   {len(rec.changed)}")
    lines.append(f"  unchanged: {len(rec.unchanged)}")
    lines.append("")
    if rec.added:
        lines.append("ADDED (create in RM tool):")
        lines += [f"  + {i}" for i in rec.added]
    if rec.removed:
        lines.append("REMOVED (retire in RM tool):")
        lines += [f"  - {i}" for i in rec.removed]
    if rec.changed:
        lines.append("CHANGED (update text in RM tool):")
        for rid, old, new in rec.changed:
            lines.append(f"  ~ {rid}")
            lines.append(f"      was: {old}")
            lines.append(f"      now: {new}")
    return "\n".join(lines) + "\n"
