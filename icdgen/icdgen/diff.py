"""Version diff: compare a new ICD definition against a previous one.

Reports added, removed, and modified signals (and interface-level add/remove).
A signal is keyed by (interface id, signal name); a modification lists each
changed field with old/new values. Output is a deterministic, sorted text +
CSV report suitable for inclusion in a change package.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from .model import IcdModel, Signal

# Signal fields compared for modification detection.
_COMPARED_FIELDS = [
    "data_type", "direction", "units", "range_min", "range_max",
    "update_rate_hz", "scaling", "offset", "encoding", "optional",
]


@dataclass
class FieldChange:
    field: str
    old: object
    new: object


@dataclass
class SignalChange:
    interface_id: str
    signal_name: str
    changes: list[FieldChange] = field(default_factory=list)


@dataclass
class DiffResult:
    added_interfaces: list[str] = field(default_factory=list)
    removed_interfaces: list[str] = field(default_factory=list)
    added_signals: list[tuple[str, str]] = field(default_factory=list)
    removed_signals: list[tuple[str, str]] = field(default_factory=list)
    modified_signals: list[SignalChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any([
            self.added_interfaces, self.removed_interfaces,
            self.added_signals, self.removed_signals, self.modified_signals,
        ])


def _signal_index(model: IcdModel) -> dict[tuple[str, str], Signal]:
    return {(iface.id, sig.name): sig
            for iface in model.interfaces for sig in iface.signals}


def diff(old: IcdModel, new: IcdModel) -> DiffResult:
    res = DiffResult()

    old_ifaces = {i.id for i in old.interfaces}
    new_ifaces = {i.id for i in new.interfaces}
    res.added_interfaces = sorted(new_ifaces - old_ifaces)
    res.removed_interfaces = sorted(old_ifaces - new_ifaces)

    old_sigs = _signal_index(old)
    new_sigs = _signal_index(new)
    old_keys = set(old_sigs)
    new_keys = set(new_sigs)

    res.added_signals = sorted(new_keys - old_keys)
    res.removed_signals = sorted(old_keys - new_keys)

    for key in sorted(old_keys & new_keys):
        o, n = old_sigs[key], new_sigs[key]
        changes = [
            FieldChange(f, getattr(o, f), getattr(n, f))
            for f in _COMPARED_FIELDS
            if getattr(o, f) != getattr(n, f)
        ]
        if changes:
            res.modified_signals.append(SignalChange(key[0], key[1], changes))

    return res


def render_text(res: DiffResult, old_hash: str, new_hash: str) -> str:
    lines = [
        "ICD DIFF REPORT",
        f"  Previous input SHA-256: {old_hash}",
        f"  New input SHA-256:      {new_hash}",
        "",
    ]
    if not res.has_changes:
        lines.append("No differences detected.")
        return "\n".join(lines) + "\n"

    if res.added_interfaces:
        lines.append("ADDED INTERFACES:")
        lines += [f"  + {i}" for i in res.added_interfaces]
    if res.removed_interfaces:
        lines.append("REMOVED INTERFACES:")
        lines += [f"  - {i}" for i in res.removed_interfaces]
    if res.added_signals:
        lines.append("ADDED SIGNALS:")
        lines += [f"  + {iid}.{sname}" for iid, sname in res.added_signals]
    if res.removed_signals:
        lines.append("REMOVED SIGNALS:")
        lines += [f"  - {iid}.{sname}" for iid, sname in res.removed_signals]
    if res.modified_signals:
        lines.append("MODIFIED SIGNALS:")
        for sc in res.modified_signals:
            lines.append(f"  ~ {sc.interface_id}.{sc.signal_name}")
            for ch in sc.changes:
                lines.append(f"      {ch.field}: {ch.old!r} -> {ch.new!r}")
    return "\n".join(lines) + "\n"


def render_csv(res: DiffResult) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Change Type", "Interface ID", "Signal", "Field", "Old", "New"])
    for i in res.added_interfaces:
        w.writerow(["INTERFACE_ADDED", i, "", "", "", ""])
    for i in res.removed_interfaces:
        w.writerow(["INTERFACE_REMOVED", i, "", "", "", ""])
    for iid, sname in res.added_signals:
        w.writerow(["SIGNAL_ADDED", iid, sname, "", "", ""])
    for iid, sname in res.removed_signals:
        w.writerow(["SIGNAL_REMOVED", iid, sname, "", "", ""])
    for sc in res.modified_signals:
        for ch in sc.changes:
            w.writerow(["SIGNAL_MODIFIED", sc.interface_id, sc.signal_name,
                        ch.field, ch.old, ch.new])
    return buf.getvalue()
