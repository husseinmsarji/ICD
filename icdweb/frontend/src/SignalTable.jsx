import React from 'react';

// Editable per-interface signal table.
//
// Columns are built from `options.signalFields`, which the backend derives from
// the icdgen field registry. Adding a signal field to the registry makes a new
// column appear here automatically — no change to this file.

export default function SignalTable({ signals, options, onChange }) {
  const fields = options.signalFields || [];

  const update = (idx, jsonName, value) => {
    const next = signals.map((s, i) => (i === idx ? { ...s, [jsonName]: value } : s));
    onChange(next);
  };
  const remove = (idx) => onChange(signals.filter((_, i) => i !== idx));

  const add = () => {
    const blank = {};
    for (const f of fields) {
      if (f.kind === 'number') blank[f.jsonName] = f.jsonName === 'updateRateHz' ? 1 : (f.jsonName === 'scaling' ? 1 : 0);
      else if (f.kind === 'bool') blank[f.jsonName] = false;
      else if (f.kind === 'enum') blank[f.jsonName] = f.enum?.[0] ?? '';
      else blank[f.jsonName] = f.required ? '' : null;
    }
    blank.name = `signal_${signals.length + 1}`;
    onChange([...signals, blank]);
  };

  const cellInput = (s, idx, f) => {
    const v = s[f.jsonName];
    if (f.kind === 'enum') {
      return (
        <select value={v ?? ''} onChange={(e) => update(idx, f.jsonName, e.target.value)}>
          {(f.enum || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }
    if (f.kind === 'bool') {
      return (
        <input type="checkbox" style={{ width: 'auto' }} checked={!!v}
          onChange={(e) => update(idx, f.jsonName, e.target.checked)} />
      );
    }
    const isNum = f.kind === 'number';
    return (
      <input
        className={f.uiWidth}
        type={isNum ? 'number' : 'text'}
        step="any"
        value={v ?? ''}
        onChange={(e) => {
          const raw = e.target.value;
          if (isNum) update(idx, f.jsonName, raw === '' ? '' : Number(raw));
          else update(idx, f.jsonName, raw === '' ? (f.required ? '' : null) : raw);
        }}
      />
    );
  };

  return (
    <div>
      <table className="sigtable">
        <thead>
          <tr>
            <th style={{ width: 26 }}>#</th>
            {fields.map((f) => (
              <th key={f.jsonName} className={f.uiWidth}>
                {f.label}{f.required && <span style={{ color: 'var(--amber)' }}> *</span>}
              </th>
            ))}
            <th style={{ width: 30 }}></th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, idx) => (
            <tr key={idx}>
              <td className="muted">{idx + 1}</td>
              {fields.map((f) => (
                <td key={f.jsonName} className={f.uiWidth}
                  style={f.kind === 'bool' ? { textAlign: 'center' } : undefined}>
                  {cellInput(s, idx, f)}
                </td>
              ))}
              <td>
                <button className="btn danger sm" title="Remove signal" onClick={() => remove(idx)}>×</button>
              </td>
            </tr>
          ))}
          {signals.length === 0 && (
            <tr><td colSpan={fields.length + 2} className="muted" style={{ padding: 14, textAlign: 'center' }}>
              No signals. Add one below.
            </td></tr>
          )}
        </tbody>
      </table>
      <div style={{ marginTop: 10 }}>
        <button className="btn sm" onClick={add}>+ Add signal</button>
      </div>
    </div>
  );
}
