import React, { useState } from 'react';
import { api } from './api.js';

const LABELS = {
  'docx': 'ICD Document (.docx)',
  'pdf': 'ICD Document (.pdf)',
  'header': 'C/C++ Header (.h)',
  'simulink': 'Simulink Bus (.m)',
  'trace-csv': 'Traceability (.csv)',
  'trace-xlsx': 'Traceability (.xlsx)',
};

export default function GeneratePanel({ projectId, definition, options, priorFiles, onToast }) {
  const all = options.artifactFormats || [];
  const [selected, setSelected] = useState(new Set(all));
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const toggle = (f) => {
    const next = new Set(selected);
    next.has(f) ? next.delete(f) : next.add(f);
    setSelected(next);
  };

  const run = async () => {
    setBusy(true); setResult(null);
    try {
      const r = await api.generate(projectId, definition, [...selected], priorFiles);
      setResult(r);
      if (!r.ok) onToast('Validation failed — fix errors before generating', true);
      else onToast(`Generated ${r.artifacts.length} artifact(s)`);
    } catch (e) {
      onToast(String(e.message || e), true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="card-head">
        <h2>Generate Artifacts</h2>
        <span className="spacer" />
        <a className="btn ghost sm" href={api.exportXmlUrl(projectId)} target="_blank" rel="noreferrer">
          Export source XML
        </a>
      </div>
      <div className="card-body">
        <div className="checkbox-row" style={{ marginBottom: 14 }}>
          {all.map((f) => (
            <span key={f} className={`chk ${selected.has(f) ? 'on' : ''}`} onClick={() => toggle(f)}>
              <span>{selected.has(f) ? '◉' : '○'}</span> {LABELS[f] || f}
            </span>
          ))}
        </div>
        <button className="btn primary" disabled={busy || selected.size === 0} onClick={run}>
          {busy ? 'Generating…' : `Generate ${selected.size} artifact(s)`}
        </button>

        {result?.ok && (
          <div style={{ marginTop: 18 }}>
            <div className="muted mono" style={{ fontSize: 11, marginBottom: 10 }}>
              INPUT SHA-256 <span className="hash">{result.inputHash}</span> · schema {result.schemaVersion}
            </div>
            <div className="grid cols-2">
              {result.artifacts.map((a) => (
                <a key={a.filename} className="btn" href={api.artifactUrl(projectId, a.filename)}
                  download style={{ justifyContent: 'space-between' }}>
                  <span>{LABELS[a.format] || a.format}</span>
                  <span className="mono muted" style={{ fontSize: 11 }}>↓ {a.filename}</span>
                </a>
              ))}
            </div>
          </div>
        )}

        {result && !result.ok && (
          <div style={{ marginTop: 16 }}>
            {result.issues.map((iss, i) => (
              <div className="issue" key={i}>
                {iss.line != null && <span className="ln">L{iss.line}</span>}
                <span>{iss.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}