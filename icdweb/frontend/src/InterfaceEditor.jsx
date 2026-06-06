import React, { useState } from 'react';
import SignalTable from './SignalTable.jsx';

// One collapsible card per interface: identity fields + its signal table.
//
// The identity fields are built from `options.interfaceFields`, which the
// backend derives from the icdgen interface field registry. Adding an interface
// field to the registry makes a new form field appear here automatically.
// The `signals` collection is rendered by SignalTable, not as a scalar field.

export default function InterfaceEditor({ iface, index, options, onChange, onRemove }) {
  const [open, setOpen] = useState(true);
  const set = (jsonName, value) => onChange({ ...iface, [jsonName]: value });

  const fields = (options.interfaceFields || []).filter((f) => f.name !== 'signals');

  const fieldInput = (f) => {
    const v = iface[f.jsonName];
    if (f.kind === 'enum') {
      return (
        <select value={v ?? ''} onChange={(e) => set(f.jsonName, e.target.value)}>
          {(f.enum || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }
    return (
      <input
        value={v ?? ''}
        onChange={(e) => set(f.jsonName, e.target.value === '' ? (f.required ? '' : null) : e.target.value)}
        style={{ fontFamily: 'var(--mono)' }}
      />
    );
  };

  return (
    <div className="card">
      <div className="card-head" style={{ cursor: 'pointer' }} onClick={() => setOpen(!open)}>
        <span className="mono muted">{open ? '▾' : '▸'}</span>
        <h2 style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--ink-0)', fontSize: 14 }}>
          {iface.id || '(no id)'} <span className="muted">— {iface.name || 'unnamed'}</span>
        </h2>
        <span className="tag bus">{iface.busType}</span>
        <span className={`tag dal-${iface.dal}`}>DAL {iface.dal}</span>
        <span className="muted mono" style={{ fontSize: 11 }}>{iface.signals.length} sig</span>
        <span className="spacer" />
        <button className="btn danger sm" onClick={(e) => { e.stopPropagation(); onRemove(); }}>
          Remove interface
        </button>
      </div>
      {open && (
        <div className="card-body">
          <div className="grid cols-3" style={{ marginBottom: 14 }}>
            {fields.map((f) => (
              <div className="field" key={f.jsonName}>
                <label>{f.label}{f.required && <span className="req"> *</span>}</label>
                {fieldInput(f)}
              </div>
            ))}
          </div>
          <SignalTable signals={iface.signals} options={options}
            onChange={(sigs) => set('signals', sigs)} />
        </div>
      )}
    </div>
  );
}
