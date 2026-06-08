import React, { useState } from 'react';
import PacketEditor from './PacketEditor.jsx';

// One collapsible card per interface: identity fields (built from
// options.interfaceFields) + a list of packets. Each packet holds its own
// signal table. The `packets` collection is structural, not a registry field.

export default function InterfaceEditor({ iface, index, options, onChange, onRemove }) {
  const [open, setOpen] = useState(true);
  const set = (jsonName, value) => onChange({ ...iface, [jsonName]: value });

  const fields = (options.interfaceFields || []).filter(
    (f) => f.name !== 'packets' && f.name !== 'signals');

  const sigCount = iface.packets.reduce((n, p) => n + p.signals.length, 0);

  const fieldInput = (f) => {
    const v = iface[f.jsonName];
    if (f.kind === 'enum') {
      return (
        <select value={v ?? ''} onChange={(e) => set(f.jsonName, e.target.value)}>
          {!f.required && <option value="">(unset)</option>}
          {(f.enum || []).filter((o) => o !== '').map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }
    // Freeform text; a datalist makes it autocomplete-with-freeform (e.g. bus).
    const listId = f.suggestions ? `dl-if-${f.jsonName}` : undefined;
    return (
      <>
        <input
          value={v ?? ''}
          list={listId}
          onChange={(e) => set(f.jsonName, e.target.value === '' ? (f.required ? '' : null) : e.target.value)}
          style={{ fontFamily: 'var(--mono)' }}
        />
        {listId && (
          <datalist id={listId}>
            {f.suggestions.map((o) => <option key={o} value={o} />)}
          </datalist>
        )}
      </>
    );
  };

  const setPacket = (i, pkt) =>
    set('packets', iface.packets.map((x, j) => (j === i ? pkt : x)));
  const removePacket = (i) =>
    set('packets', iface.packets.filter((_, j) => j !== i));
  const addPacket = () =>
    set('packets', [...iface.packets, {
      name: `PACKET_${iface.packets.length + 1}`, description: null, signals: [],
    }]);

  return (
    <div className="card">
      <div className="card-head" style={{ cursor: 'pointer' }} onClick={() => setOpen(!open)}>
        <span className="mono muted">{open ? '▾' : '▸'}</span>
        <h2 style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--ink-0)', fontSize: 14 }}>
          {iface.id || '(no id)'} <span className="muted">— {iface.name || 'unnamed'}</span>
        </h2>
        <span className="tag bus">{iface.busType}</span>
        <span className={`tag dal-${iface.dal}`}>DAL {iface.dal}</span>
        <span className="muted mono" style={{ fontSize: 11 }}>
          {iface.packets.length} pkt / {sigCount} sig
        </span>
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

          <div className="row" style={{ margin: '6px 0 10px' }}>
            <span className="mono muted" style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase' }}>
              Packets
            </span>
            <span className="spacer" />
            <button className="btn sm" onClick={addPacket}>+ Add packet</button>
          </div>

          {iface.packets.map((pkt, i) => (
            <PacketEditor key={i} packet={pkt} options={options}
              onChange={(p) => setPacket(i, p)} onRemove={() => removePacket(i)} />
          ))}
          {iface.packets.length === 0 && (
            <div className="muted" style={{ padding: 12, fontSize: 12 }}>
              No packets. Add one to hold signals.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
