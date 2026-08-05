import React, { useRef, useState } from 'react';
import { api } from './api.js';

// Two-file "Compare Revisions" panel. Pick an OLD and a NEW ICD (YAML);
// the backend diffs them and returns a formatted PDF change report, which is
// downloaded directly. There is no on-screen diff view — the report is the
// deliverable (suitable for a change package).
//
// (The per-revision "Change Summary Report" column inside a generated ICD
// document is a separate feature, driven by the <priorRevisions> linkage in the
// ICD itself; see gen_docx/gen_pdf + rev_summary.)

export default function DiffPanel({ onToast }) {
  const [busy, setBusy] = useState(false);
  const oldRef = useRef();
  const newRef = useRef();

  const run = async () => {
    const o = oldRef.current.files?.[0];
    const n = newRef.current.files?.[0];
    if (!o || !n) { onToast('Pick both an old and a new file', true); return; }
    setBusy(true);
    try {
      const fname = await api.diffReportPdf(o, n);
      onToast(`Downloaded ${fname}`);
    } catch (e) {
      onToast(String(e.message || e), true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="card-head">
        <h2>Compare Revisions</h2>
        <span className="spacer" />
        <span className="muted mono" style={{ fontSize: 11 }}>
          two files &rarr; PDF change report
        </span>
      </div>
      <div className="card-body">
        <div className="grid cols-3" style={{ alignItems: 'end' }}>
          <div className="field">
            <label>Old (previous revision)</label>
            <input ref={oldRef} type="file" accept=".yaml,.yml" />
          </div>
          <div className="field">
            <label>New (this revision)</label>
            <input ref={newRef} type="file" accept=".yaml,.yml" />
          </div>
          <button className="btn primary" disabled={busy} onClick={run}>
            {busy ? 'Building report…' : 'Download diff report (PDF)'}
          </button>
        </div>
        <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
          The report lists added, removed, and modified signals with old &rarr; new
          field values, plus the SHA-256 of each input file for traceability.
        </div>
      </div>
    </div>
  );
}