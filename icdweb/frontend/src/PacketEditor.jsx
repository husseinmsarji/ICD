import React, { useState } from 'react';
import SignalTable from './SignalTable.jsx';

// One packet within an interface: a name, an optional description, and the
// signal table for the signals grouped under this packet.

export default function PacketEditor({ packet, options, onChange, onRemove }) {
  const [open, setOpen] = useState(true);
  const set = (key, value) => onChange({ ...packet, [key]: value });

  return (
    <div className="packet">
      <div className="packet-head" onClick={() => setOpen(!open)}>
        <span className="mono muted">{open ? '▾' : '▸'}</span>
        <span className="packet-tag">PACKET</span>
        <input
          className="packet-name"
          value={packet.name ?? ''}
          placeholder="packet_name"
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => set('name', e.target.value)}
        />
        <span className="muted mono" style={{ fontSize: 11 }}>
          {packet.signals.length} sig
        </span>
        <span className="spacer" />
        <button className="btn danger sm" onClick={(e) => { e.stopPropagation(); onRemove(); }}>
          Remove packet
        </button>
      </div>
      {open && (
        <div className="packet-body">
          <div className="field" style={{ marginBottom: 12 }}>
            <label>Packet Description</label>
            <input
              value={packet.description ?? ''}
              placeholder="(optional)"
              onChange={(e) => set('description', e.target.value === '' ? null : e.target.value)}
            />
          </div>
          <SignalTable
            signals={packet.signals}
            options={options}
            onChange={(sigs) => set('signals', sigs)}
          />
        </div>
      )}
    </div>
  );
}
