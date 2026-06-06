import React from 'react';

// Document metadata + revision history table.

export default function MetadataEditor({ meta, onChange }) {
  const set = (key, value) => onChange({ ...meta, [key]: value });
  const setRev = (idx, key, value) =>
    onChange({ ...meta, revisionHistory: meta.revisionHistory.map((r, i) => i === idx ? { ...r, [key]: value } : r) });
  const addRev = () =>
    onChange({ ...meta, revisionHistory: [...meta.revisionHistory, { revision: '', date: new Date().toISOString().slice(0, 10), author: meta.author || '', description: '' }] });
  const removeRev = (idx) =>
    onChange({ ...meta, revisionHistory: meta.revisionHistory.filter((_, i) => i !== idx) });

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
          <thead><tr><th style={{ width: 80 }}>Rev</th><th style={{ width: 130 }}>Date</th><th style={{ width: 160 }}>Author</th><th>Description</th><th style={{ width: 30 }}></th></tr></thead>
          <tbody>
            {meta.revisionHistory.map((r, i) => (
              <tr key={i}>
                <td><input value={r.revision} onChange={(e) => setRev(i, 'revision', e.target.value)} /></td>
                <td><input type="date" value={r.date} onChange={(e) => setRev(i, 'date', e.target.value)} /></td>
                <td><input value={r.author} onChange={(e) => setRev(i, 'author', e.target.value)} /></td>
                <td><input value={r.description} onChange={(e) => setRev(i, 'description', e.target.value)} /></td>
                <td><button className="btn danger sm" onClick={() => removeRev(i)}>×</button></td>
              </tr>
            ))}
          </tbody>
        </table>
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
