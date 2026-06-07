import React, { useRef, useState } from 'react';
import { api } from './api.js';

// Version diff viewer. Two modes:
//   * "files"   — compare two uploaded XML/JSON files (old vs new).
//   * "current" — compare an uploaded file (old) against the open project (new).
// Renders the same DiffResult the CLI/`/api/diff` produce, using the avionics
// .diff-row styles already in the design system. Self-contained: drop it
// anywhere a project is open (or even with no project, in files mode).

export default function DiffPanel({ definition, onToast }) {
  const [mode, setMode] = useState(definition ? 'current' : 'files');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const oldRef = useRef();
  const newRef = useRef();
  const againstRef = useRef();

  const run = async (fn) => {
    setBusy(true); setResult(null);
    try {
      const r = await fn();
      if (r.ok === false) {
        onToast(`${r.side || ''} file: ${r.issue?.message || 'parse error'}`.trim(), true);
        return;
      }
      setResult(r);
      if (!r.hasChanges) onToast('No differences detected');
    } catch (e) {
      onToast(String(e.message || e), true);
    } finally {
      setBusy(false);
    }
  };

  const runFiles = () => {
    const o = oldRef.current.files?.[0];
    const n = newRef.current.files?.[0];
    if (!o || !n) { onToast('Pick both an old and a new file', true); return; }
    run(() => api.diffFiles(o, n));
  };

  const runAgainst = () => {
    const f = againstRef.current.files?.[0];
    if (!f) { onToast('Pick a file to compare against', true); return; }
    run(() => api.diffAgainstFile(definition, f));
  };

  const hasResult = result && result.hasChanges;

  return (
    <div className="card">
      <div className="card-head">
        <h2>Compare Revisions</h2>
        <span className="spacer" />
        <div className="checkbox-row">
          {definition && (
            <span className={`chk ${mode === 'current' ? 'on' : ''}`} onClick={() => { setMode('current'); setResult(null); }}>
              <span>{mode === 'current' ? '◉' : '○'}</span> File vs current project
            </span>
          )}
          <span className={`chk ${mode === 'files' ? 'on' : ''}`} onClick={() => { setMode('files'); setResult(null); }}>
            <span>{mode === 'files' ? '◉' : '○'}</span> Two files
          </span>
        </div>
      </div>
      <div className="card-body">
        {mode === 'files' ? (
          <div className="grid cols-3" style={{ alignItems: 'end' }}>
            <div className="field">
              <label>Old (previous revision)</label>
              <input ref={oldRef} type="file" accept=".xml,.json" />
            </div>
            <div className="field">
              <label>New (this revision)</label>
              <input ref={newRef} type="file" accept=".xml,.json" />
            </div>
            <button className="btn primary" disabled={busy} onClick={runFiles}>
              {busy ? 'Comparing…' : 'Compare files'}
            </button>
          </div>
        ) : (
          <div className="grid cols-3" style={{ alignItems: 'end' }}>
            <div className="field" style={{ gridColumn: 'span 2' }}>
              <label>Old revision file (compared against the open project)</label>
              <input ref={againstRef} type="file" accept=".xml,.json" />
            </div>
            <button className="btn primary" disabled={busy} onClick={runAgainst}>
              {busy ? 'Comparing…' : 'Compare to project'}
            </button>
          </div>
        )}

        {result && !result.hasChanges && (
          <div className="muted mono" style={{ marginTop: 14, fontSize: 12 }}>
            No differences detected.
          </div>
        )}

        {hasResult && (
          <div style={{ marginTop: 16 }}>
            <DiffSummary result={result} />
            <div style={{ marginTop: 12 }}>
              {result.addedInterfaces.map((i) => (
                <div className="diff-row add" key={`ai-${i}`}>
                  <span className="badge">+ IFACE</span><span>{i}</span>
                </div>
              ))}
              {result.removedInterfaces.map((i) => (
                <div className="diff-row rem" key={`ri-${i}`}>
                  <span className="badge">- IFACE</span><span>{i}</span>
                </div>
              ))}
              {result.addedSignals.map((s, k) => (
                <div className="diff-row add" key={`as-${k}`}>
                  <span className="badge">+ SIGNAL</span>
                  <span>{s.interface}/{s.packet}.{s.signal}</span>
                </div>
              ))}
              {result.removedSignals.map((s, k) => (
                <div className="diff-row rem" key={`rs-${k}`}>
                  <span className="badge">- SIGNAL</span>
                  <span>{s.interface}/{s.packet}.{s.signal}</span>
                </div>
              ))}
              {result.modifiedSignals.map((s, k) => (
                <div className="diff-row mod" key={`ms-${k}`}>
                  <span className="badge">~ SIGNAL</span>
                  <span>
                    {s.interface}/{s.packet}.{s.signal}
                    <span className="muted">  —  </span>
                    {s.changes.map((c, j) => (
                      <span key={j} className="mono" style={{ fontSize: 11 }}>
                        {j > 0 ? ', ' : ''}{c.field}: {c.old} → {c.new}
                      </span>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DiffSummary({ result }) {
  const counts = [
    ['+', result.addedInterfaces.length + result.addedSignals.length, 'added'],
    ['-', result.removedInterfaces.length + result.removedSignals.length, 'removed'],
    ['~', result.modifiedSignals.length, 'modified'],
  ];
  return (
    <div className="mono muted" style={{ fontSize: 11, letterSpacing: '.06em' }}>
      {counts.map(([sym, n, label], i) => (
        <span key={label}>
          {i > 0 ? '  ·  ' : ''}{sym}{n} {label}
        </span>
      ))}
    </div>
  );
}