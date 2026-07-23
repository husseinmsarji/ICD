import React from 'react';

// Document metadata + revision history table.
//
// Each revision row carries an optional "baseline file" upload (Flow A): the
// ICD as it was AT that revision. It is read as text and handed up via
// onPriorFile(revision, content, name); it is NOT saved with the project — it
// rides along just-in-time with the next Generate call to compute the
// "Change Summary Report" column for the FOLLOWING revision.

export default function MetadataEditor({ meta, onChange, onPriorFile, priorFiles }) {
  const set = (key, value) => onChange({ ...meta, [key]: value });
  const setRev = (idx, key, value) =>
    onChange({ ...meta, revisionHistory: meta.revisionHistory.map((r, i) => i === idx ? { ...r, [key]: value } : r) });
  const addRev = () =>
    onChange({ ...meta, revisionHistory: [...meta.revisionHistory, { revision: '', date: new Date().toISOString().slice(0, 10), author: meta.author || '', description: '' }] });
  const removeRev = (idx) =>
    onChange({ ...meta, revisionHistory: meta.revisionHistory.filter((_, i) => i !== idx) });

  const onFile = (revision, e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => onPriorFile?.(revision, String(reader.result || ''), file.name);
    reader.readAsText(file);
    // Reset the native input so re-selecting the same filename still fires
    // onChange. The captured filename is surfaced in our own UI below, so the
    // (now-cleared) native "No file chosen" text is hidden behind a styled label.
    e.target.value = '';
  };

  const priors = priorFiles || {};

  return (
    <div className="card">
      <div className="card-head"><h2>Document Metadata</h2></div>
      <div className="card-body">
        <div className="grid cols-3">
          <F label="Document ID" req v={meta.documentId} set={(x) => set('documentId', x)} mono />
          <F label="Title" req v={meta.documentTitle} set={(x) => set('documentTitle', x)} span={2} />
          <F label="Program" req v={meta.program} set={(x) => set('program', x)} />
          <F label="Revision" req v={meta.revision} set={(x) => set('revision', x)} mono />
          <F label="Revision Date" req v={meta.revisionDate} set={(x) => set('revisionDate', x)} type="date" />
          <F label="Author" req v={meta.author} set={(x) => set('author', x)} span={3} />
        </div>

        <div className="row" style={{ margin: '18px 0 8px' }}>
          <label style={{ fontFamily: 'var(--mono)', fontSize: 10.5, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>
            Revision History
          </label>
          <span className="spacer" />
          <button className="btn sm" onClick={addRev}>+ Add entry</button>
        </div>
        <table className="sigtable">
          <thead>
            <tr>
              <th style={{ width: 70 }}>Rev</th>
              <th style={{ width: 120 }}>Date</th>
              <th style={{ width: 140 }}>Author</th>
              <th>Description</th>
              <th style={{ width: 240 }}>Baseline file (state at this revision)</th>
              <th style={{ width: 30 }}></th>
            </tr>
          </thead>
          <tbody>
            {meta.revisionHistory.map((r, i) => {
              const prior = priors[r.revision];
              const priorName = prior ? (prior.name || 'attached file') : null;
              return (
                <tr key={i}>
                  <td><input value={r.revision} onChange={(e) => setRev(i, 'revision', e.target.value)} /></td>
                  <td><input type="date" value={r.date} onChange={(e) => setRev(i, 'date', e.target.value)} /></td>
                  <td><input value={r.author} onChange={(e) => setRev(i, 'author', e.target.value)} /></td>
                  <td><input value={r.description} onChange={(e) => setRev(i, 'description', e.target.value)} /></td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <label className="btn ghost sm" style={{ cursor: 'pointer', margin: 0 }}
                        title="Upload the ICD as it was at this revision; the next revision's Change Summary Report is computed from it.">
                        {priorName ? 'Replace file' : 'Choose file'}
                        <input type="file" accept=".yaml,.yml" style={{ display: 'none' }}
                          onChange={(e) => onFile(r.revision, e)} />
                      </label>
                      {priorName ? (
                        <span className="ok mono" style={{ fontSize: 10.5, display: 'inline-flex', alignItems: 'center', gap: 4, maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                          title={priorName}>
                          ✓ {priorName}
                        </span>
                      ) : (
                        <span className="muted mono" style={{ fontSize: 10.5 }}>none</span>
                      )}
                    </div>
                  </td>
                  <td><button className="btn danger sm" onClick={() => removeRev(i)}>×</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
          Optional: attach the ICD file as it was at a revision. The <em>next</em>{' '}
          revision's “Change Summary Report” column is auto-computed by diffing
          against it. Files are used only for the next Generate — they are not saved.
        </div>
      </div>
    </div>
  );
}

function F({ label, v, set, req, mono, span, type }) {
  return (
    <div className="field" style={span ? { gridColumn: `span ${span}` } : undefined}>
      <label>{label}{req && <span className="req"> *</span>}</label>
      <input type={type || 'text'} value={v} onChange={(e) => set(e.target.value)}
        style={mono ? { fontFamily: 'var(--mono)' } : undefined} />
    </div>
  );
}