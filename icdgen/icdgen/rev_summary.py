"""Per-revision change summaries for the document header.

Given the current IcdModel and its `prior_revisions` mapping (revision letter ->
prior source file), this computes a compact, human-readable change summary for
each revision by running the existing diff engine against the prior file.

Design notes:
  * This module is intentionally standalone and side-effect-light: it loads the
    referenced prior files, diffs them, and returns plain data. The document
    generators (gen_docx / gen_pdf) decide how to render it. Swapping the
    summary wording or adding a new line item is a one-function edit here.
  * Prior-revision sources are resolved relative to `base_dir` (the directory of
    the ICD being generated) so a relative path in the XML works from anywhere.
  * Missing/unreadable prior files never raise: the summary degrades to a short
    note so generation is robust (a draft may reference a file not yet present).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .diff import diff as diff_models
from .model import IcdModel


@dataclass
class RevisionSummary:
    """Resolved change summary for one revision entry."""
    revision: str
    lines: list[str] = field(default_factory=list)   # human-readable bullets
    note: str | None = None                           # e.g. "initial release"

    @property
    def text(self) -> str:
        """One-line compact rendering for table cells."""
        if self.note and not self.lines:
            return self.note
        return "; ".join(self.lines) if self.lines else (self.note or "")


def _counts_line(res) -> list[str]:
    """Turn a DiffResult into short, ordered bullet strings."""
    out: list[str] = []
    if res.added_interfaces:
        out.append(f"+{len(res.added_interfaces)} interface(s)")
    if res.removed_interfaces:
        out.append(f"-{len(res.removed_interfaces)} interface(s)")
    if res.added_signals:
        out.append(f"+{len(res.added_signals)} signal(s)")
    if res.removed_signals:
        out.append(f"-{len(res.removed_signals)} signal(s)")
    if res.modified_signals:
        nfields = sum(len(sc.changes) for sc in res.modified_signals)
        out.append(f"~{len(res.modified_signals)} signal(s) "
                   f"({nfields} field change(s))")
    return out


def _detail_lines(res, limit: int = 12) -> list[str]:
    """Itemized changes, capped so the header stays compact."""
    items: list[str] = []
    for iid, pkt, s in res.added_signals:
        items.append(f"+ {iid}/{pkt}.{s}")
    for iid, pkt, s in res.removed_signals:
        items.append(f"- {iid}/{pkt}.{s}")
    for sc in res.modified_signals:
        flds = ", ".join(c.field for c in sc.changes)
        items.append(f"~ {sc.interface_id}/{sc.packet_name}.{sc.signal_name} "
                     f"({flds})")
    if len(items) > limit:
        extra = len(items) - limit
        items = items[:limit] + [f"... and {extra} more change(s)"]
    return items


def compute_revision_summaries(model: IcdModel, base_dir: str,
                               detailed: bool = False) -> list[RevisionSummary]:
    """Return a RevisionSummary per revision-history entry, newest-last (the
    order they appear in metadata.revision_history).

    The current (latest) revision is diffed against the prior-revision source
    whose letter matches the immediately preceding history entry, if a
    `priorRevisions` mapping for it exists. Earlier entries are summarized from
    chained prior-source diffs where mappings are available; otherwise they get
    a short note. The first entry is always "initial release".
    """
    from .loader import load  # local import avoids a cycle at module load

    prior_by_rev = {pr.revision: pr.source for pr in model.prior_revisions}
    history = list(model.metadata.revision_history)
    summaries: list[RevisionSummary] = []

    # Cache loaded prior models so a file is parsed at most once.
    _cache: dict[str, IcdModel | None] = {}

    def _load_prior(rev: str) -> IcdModel | None:
        src = prior_by_rev.get(rev)
        if not src:
            return None
        if src in _cache:
            return _cache[src]
        path = src if os.path.isabs(src) else os.path.join(base_dir, src)
        try:
            m, _h, _w = load(path)
        except Exception:
            m = None
        _cache[src] = m
        return m

    for idx, entry in enumerate(history):
        rev = entry.revision
        if idx == 0:
            summaries.append(RevisionSummary(rev, note="Initial release."))
            continue

        prev_rev = history[idx - 1].revision
        # The "new" side for this entry: if it is the latest history entry, use
        # the current model; otherwise use that revision's own prior source.
        new_model = model if idx == len(history) - 1 else _load_prior(rev)
        old_model = _load_prior(prev_rev)

        if new_model is None or old_model is None:
            summaries.append(RevisionSummary(
                rev, note="No prior-revision source linked; summary unavailable."))
            continue

        res = diff_models(old_model, new_model)
        if not res.has_changes:
            summaries.append(RevisionSummary(rev, note="No changes detected."))
            continue

        lines = _detail_lines(res) if detailed else _counts_line(res)
        summaries.append(RevisionSummary(rev, lines=lines))

    return summaries