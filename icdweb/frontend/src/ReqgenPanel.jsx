import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { api } from './api.js';

// ============================================================================
// reqgen config editor — a VIEW/EDITOR over reqgen/config/reqgen.json.
//
// Invariant: the config FILE is the single record of truth. This component
// holds only a transient DRAFT; the single writer (backend save_config) is
// reached via Save. It never persists state any other way.
//
// STATE OWNERSHIP: all editor state (draft, chosen ICD source, preview, trace,
// reconcile) lives in App via the `state`/`patch` props, NOT in this
// component's own useState. App keeps this panel mounted across tab switches
// (display:none when inactive), so lifting the state there is what makes the
// reqgen draft survive a switch to the ICD Editor tab and back. This component
// is now a controlled view over `state`.
//
// The editor builds itself from /api/reqgen/meta (the aspect registry
// descriptor) exactly like the ICD form builds from the field registry, so a
// new aspect in config_schema.py appears here with no change to this file.
//
// Bright line: a template may use only its aspect's declared fields as
// {placeholders}. We check that client-side for instant feedback AND the
// backend re-checks on save (400). Both must agree.
// ============================================================================

// Extract {placeholder} base names from a template (mirrors the server parser:
// base name before any .attr / [idx]). Bare {} -> '' so we can flag it.
function placeholdersOf(tmpl) {
  const out = [];
  const re = /\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(tmpl || '')) !== null) {
    const base = m[1].split('.')[0].split('[')[0];
    out.push(base);
  }
  return out;
}

function badPlaceholders(tmpl, allowed) {
  const set = new Set(allowed);
  const bad = [];
  for (const p of placeholdersOf(tmpl)) {
    if (p === '' || !set.has(p)) { if (!bad.includes(p)) bad.push(p); }
  }
  return bad;
}

const ID_TOKENS_FALLBACK = ['prefix', 'iface', 'packet', 'signal', 'aspect'];

export default function ReqgenPanel({ projects, onToast, state, patch }) {
  // Pull everything from the lifted state. `patch` merges a slice back into it.
  const {
    meta, draft, savedHash, path,
    icdProjectId, uploadXml, preview, recon, trace, filter, loaded,
  } = state;

  // Transient UI-only flags that need not survive a tab switch can stay local.
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);

  const setDraft = useCallback((updater) => {
    patch((prev) => ({
      ...prev,
      draft: typeof updater === 'function' ? updater(prev.draft) : updater,
    }));
  }, [patch]);

  // ---- bootstrap: descriptor + config of record (ONCE; guarded by loaded) ----
  useEffect(() => {
    if (loaded) return;
    (async () => {
      try {
        const [m, c] = await Promise.all([api.reqgenMeta(), api.reqgenConfig()]);
        patch({ meta: m, draft: c.config, savedHash: c.configHash, path: c.path, loaded: true });
      } catch (e) { onToast?.(String(e.message || e), true); }
    })();
  }, [loaded, patch, onToast]);

  // An L3 aspect is valid at a granularity when its `granularity` is that mode
  // or "both"; L4 aspects are always valid. This is the client mirror of the
  // backend `aspect_valid_at`, so the editor only OFFERS aspects that actually
  // generate at the chosen granularity (port no longer shows the packet-only
  // RATE; packet no longer shows the port-only CONNECT/BUS).
  const aspectValidAt = useCallback((a, gran) => {
    if (a.level !== 'L3') return true;
    return a.granularity === 'both' || a.granularity === gran;
  }, []);

  const gran = draft?.l3_granularity || 'packet';

  // L3 aspects are filtered to the active granularity; L4 is shown in full.
  const aspectsByLevel = useMemo(() => {
    const g = { L3: [], L4: [] };
    (meta?.aspects || []).forEach((a) => {
      if (a.level === 'L3' && !aspectValidAt(a, gran)) return;
      g[a.level]?.push(a);
    });
    return g;
  }, [meta, gran, aspectValidAt]);

  const aspectByKey = useMemo(() => {
    const o = {};
    (meta?.aspects || []).forEach((a) => { o[a.key] = a; });
    return o;
  }, [meta]);

  // Resolve the effective template for an aspect (global override or default).
  const effTemplate = useCallback((key) => {
    if (!draft || !aspectByKey[key]) return '';
    return (draft.templates && draft.templates[key] != null)
      ? draft.templates[key]
      : aspectByKey[key].defaultTemplate;
  }, [draft, aspectByKey]);

  // ---- mutate the draft (pure; never writes) ----
  const patchDraft = (p) => setDraft((d) => ({ ...d, ...p }));

  // Switching granularity must re-seed the enabled L3 set: the old set may hold
  // aspects invalid at the new granularity (which the backend would reject) and
  // is missing the new granularity's aspects. We keep any still-valid enabled
  // aspect and add the new granularity's defaults, preserving registry order.
  const setGranularity = (next) => {
    const validNext = new Set((meta.l3AspectsByGranularity?.[next]) || []);
    const kept = (draft.l3_aspects || []).filter((k) => validNext.has(k));
    const defaults = (meta.defaultL3AspectsByGranularity?.[next]) || [];
    const merged = new Set([...kept, ...defaults]);
    const ordered = (meta.l3AspectsByGranularity?.[next] || meta.l3Aspects || [])
      .filter((k) => merged.has(k));
    patchDraft({ l3_granularity: next, l3_aspects: ordered });
  };

  const toggleAspect = (level, key) => {
    const field = level === 'L3' ? 'l3_aspects' : 'l4_aspects';
    const cur = new Set(draft[field] || []);
    cur.has(key) ? cur.delete(key) : cur.add(key);
    // Preserve registry order for determinism. For L3, order by the
    // granularity-filtered list so only currently-valid aspects are retained.
    const order = level === 'L3'
      ? (meta.l3AspectsByGranularity?.[gran] || meta.l3Aspects)
      : meta.l4Aspects;
    const ordered = order.filter((k) => cur.has(k));
    patchDraft({ [field]: ordered });
  };

  const setTemplate = (key, value) => {
    const templates = { ...(draft.templates || {}) };
    if (value === aspectByKey[key].defaultTemplate || value === '') {
      delete templates[key];   // empty / equal-to-default => no override stored
    } else {
      templates[key] = value;
    }
    patchDraft({ templates });
  };

  const resetTemplate = (key) => {
    const templates = { ...(draft.templates || {}) };
    delete templates[key];
    patchDraft({ templates });
  };

  // ---- dirty + client-side bright-line validity ----
  const templateErrors = useMemo(() => {
    if (!draft || !meta) return [];
    const errs = [];
    const check = (key, tmpl, where) => {
      const bad = badPlaceholders(tmpl, aspectByKey[key]?.fields || []);
      if (bad.length) {
        errs.push({ where, key,
          bad: bad.map((b) => (b === '' ? '{}' : `{${b}}`)).join(', '),
          allowed: (aspectByKey[key]?.fields || []).map((f) => `{${f}}`).join(', ') });
      }
    };
    Object.entries(draft.templates || {}).forEach(([k, t]) => check(k, t, `global ${k}`));
    Object.entries(draft.interfaces || {}).forEach(([iid, ov]) =>
      Object.entries(ov.templates || {}).forEach(([k, t]) => check(k, t, `${iid} ${k}`)));
    Object.entries(draft.signals || {}).forEach(([sid, ov]) =>
      Object.entries(ov.templates || {}).forEach(([k, t]) => check(k, t, `${sid} ${k}`)));
    // ID format tokens.
    const idTokens = meta.idFormatTokens || ID_TOKENS_FALLBACK;
    [['id_format_l3', draft.id_format_l3], ['id_format_l4', draft.id_format_l4]]
      .forEach(([f, v]) => {
        const bad = badPlaceholders(v, idTokens);
        if (bad.length) errs.push({ where: f, key: null,
          bad: bad.map((b) => (b === '' ? '{}' : `{${b}}`)).join(', '),
          allowed: idTokens.map((t) => `{${t}}`).join(', ') });
      });
    return errs;
  }, [draft, meta, aspectByKey]);

  const canSave = templateErrors.length === 0 && !saving;

  // ---- ICD source payload for preview/reconcile/trace ----
  const icdPayload = () => {
    if (uploadXml) return { icdXml: uploadXml.text };
    if (icdProjectId) return { icdProjectId };
    return null;
  };

  const runPreview = async () => {
    const icd = icdPayload();
    if (!icd) { onToast?.('Pick a project or upload an ICD first', true); return; }
    setBusy(true);
    patch({ preview: null, recon: null, trace: null });
    try {
      const [p, r, t] = await Promise.all([
        api.reqgenPreview(draft, icd),
        api.reqgenReconcile(draft, icd).catch(() => null),
        api.reqgenTrace(draft, icd).catch(() => null),
      ]);
      if (!p.ok) { onToast?.(p.error || 'Preview failed', true); }
      patch({
        preview: p.ok ? p : null,
        recon: r && r.ok ? r : null,
        trace: t && t.ok ? t : null,
      });
    } catch (e) { onToast?.(String(e.message || e), true); }
    finally { setBusy(false); }
  };

  const downloadTraceCsv = async () => {
    const icd = icdPayload();
    if (!icd) { onToast?.('Pick a project or upload an ICD first', true); return; }
    try {
      const fname = await api.reqgenTraceCsv(draft, icd);
      onToast?.(`Downloaded ${fname}`);
    } catch (e) { onToast?.(String(e.message || e), true); }
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.saveReqgenConfig(draft);
      patch({ savedHash: r.configHash });
      onToast?.('Config saved');
    } catch (e) {
      // Backend bright-line / schema rejection (400) lands here with its message.
      onToast?.(String(e.message || e), true);
    } finally { setSaving(false); }
  };

  const onUpload = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => patch({ uploadXml: { text: String(reader.result || ''), name: f.name }, icdProjectId: '' });
    reader.readAsText(f);
    e.target.value = '';
  };

  const setFilter = (updater) =>
    patch((prev) => ({ ...prev, filter: typeof updater === 'function' ? updater(prev.filter) : updater }));

  if (!meta || !draft) return <div className="muted" style={{ padding: 20 }}>Loading reqgen config…</div>;

  const filteredReqs = (preview?.requirements || []).filter((r) =>
    (filter.level === 'ALL' || r.level === filter.level) &&
    (filter.iface === 'ALL' || r.iface === filter.iface));
  const ifaceOptions = Array.from(new Set((preview?.requirements || []).map((r) => r.iface)));

  return (
    <div>
      {/* ---- Global generation knobs ---- */}
      <div className="card">
        <div className="card-head">
          <h2>Requirement Generation — Config</h2>
          <span className="spacer" />
          <span className="muted mono" style={{ fontSize: 11 }}>{path}</span>
        </div>
        <div className="card-body">
          <div className="grid cols-3">
            <div className="field">
              <label>Program Prefix</label>
              <input value={draft.program_prefix}
                onChange={(e) => patchDraft({ program_prefix: e.target.value })}
                style={{ fontFamily: 'var(--mono)' }} />
            </div>
            <div className="field">
              <label>L3 Granularity</label>
              <select value={draft.l3_granularity}
                onChange={(e) => setGranularity(e.target.value)}>
                {meta.granularities.map((g) => (
                  <option key={g} value={g}>
                    {g === 'port' ? 'port — interface contract' : 'packet — per-message'}
                  </option>
                ))}
              </select>
              <span className="muted mono" style={{ fontSize: 10 }}>
                {gran === 'port'
                  ? 'one L3 requirement per interface (connectivity, bus, DAL)'
                  : 'one L3 requirement per packet (exists, refresh rate)'}
              </span>
            </div>
            <div className="field">
              <label>Config SHA-256 (saved)</label>
              <input readOnly value={savedHash || ''} className="hash"
                style={{ fontSize: 11 }} />
            </div>
          </div>
          <div className="grid cols-2" style={{ marginTop: 12 }}>
            <IdFormatField label="L3 ID Format" value={draft.id_format_l3}
              tokens={meta.idFormatTokens} dflt={meta.defaultIdFormatL3}
              onChange={(v) => patchDraft({ id_format_l3: v })} />
            <IdFormatField label="L4 ID Format" value={draft.id_format_l4}
              tokens={meta.idFormatTokens} dflt={meta.defaultIdFormatL4}
              onChange={(v) => patchDraft({ id_format_l4: v })} />
          </div>
        </div>
      </div>

      {/* ---- Aspect sections ---- */}
      {['L3', 'L4'].map((level) => (
        <div className="card" key={level}>
          <div className="card-head">
            <h2>{level} Aspects — {level === 'L3'
              ? (gran === 'port' ? 'Interface / Port' : 'Packet / Message')
              : 'Signal'}</h2>
            <span className="spacer" />
            <span className="muted mono" style={{ fontSize: 11 }}>
              {(level === 'L3' ? draft.l3_aspects : draft.l4_aspects)
                .filter((k) => level === 'L4' || (aspectByKey[k] && aspectValidAt(aspectByKey[k], gran)))
                .length} enabled
            </span>
          </div>
          <div className="card-body">
            {aspectsByLevel[level].map((a) => {
              const on = (level === 'L3' ? draft.l3_aspects : draft.l4_aspects).includes(a.key);
              const tmpl = effTemplate(a.key);
              const overridden = draft.templates && draft.templates[a.key] != null;
              const bad = badPlaceholders(tmpl, a.fields);
              return (
                <div key={a.key} className="aspect-row">
                  <div className="row" style={{ alignItems: 'center' }}>
                    <span className={`chk ${on ? 'on' : ''}`} onClick={() => toggleAspect(level, a.key)}>
                      <span>{on ? '◉' : '○'}</span> {a.key}
                    </span>
                    <span className="muted" style={{ fontSize: 12 }}>{a.label}</span>
                    <span className="spacer" />
                    <span className="muted mono" style={{ fontSize: 10.5 }}>
                      fields: {a.fields.map((f) => `{${f}}`).join(' ')}
                    </span>
                  </div>
                  {on && (
                    <div style={{ marginTop: 8 }}>
                      <div className="row" style={{ marginBottom: 4 }}>
                        <label style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>
                          Template{overridden && <span className="ok"> · overridden</span>}
                        </label>
                        <span className="spacer" />
                        {overridden && (
                          <button className="btn ghost sm" onClick={() => resetTemplate(a.key)}>
                            Reset to default
                          </button>
                        )}
                      </div>
                      <input value={tmpl} onChange={(e) => setTemplate(a.key, e.target.value)}
                        className={bad.length ? 'err' : ''}
                        style={{ fontFamily: 'var(--mono)', fontSize: 12 }} />
                      {bad.length > 0 && (
                        <div className="bright-line-warn">
                          ✕ {bad.map((b) => (b === '' ? '{}' : `{${b}}`)).join(', ')} not allowed for {a.key}.
                          Allowed: {a.fields.map((f) => `{${f}}`).join(', ')} — a {a.key} requirement may only transcribe its own fields.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* ---- Overrides (interface + signal) ---- */}
      <OverridesEditor draft={draft} setDraft={setDraft} meta={meta}
        aspectByKey={aspectByKey} />

      {/* ---- Live preview ---- */}
      <div className="card">
        <div className="card-head">
          <h2>Live Preview</h2>
          <span className="spacer" />
          {templateErrors.length > 0
            ? <span className="bad mono" style={{ fontSize: 11 }}>● {templateErrors.length} bright-line error(s)</span>
            : <span className="ok mono" style={{ fontSize: 11 }}>● bright-line clean</span>}
        </div>
        <div className="card-body">
          <div className="grid cols-3" style={{ alignItems: 'end' }}>
            <div className="field">
              <label>ICD from project</label>
              <select value={icdProjectId}
                onChange={(e) => patch({ icdProjectId: e.target.value, uploadXml: null })}>
                <option value="">(choose a project)</option>
                {(projects || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} — {p.documentId} rev {p.revision}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>…or upload an ICD {uploadXml && <span className="ok">✓ {uploadXml.name}</span>}</label>
              <input type="file" accept=".xml,.json" onChange={onUpload} />
            </div>
            <button className="btn primary" disabled={busy} onClick={runPreview}>
              {busy ? 'Generating…' : 'Preview requirements'}
            </button>
          </div>

          {recon && (recon.added.length || recon.removed.length || recon.changed.length) > 0 && (
            <div className="recon-strip">
              <span className="mono" style={{ fontSize: 11 }}>vs saved config:</span>
              <span className="ok">+{recon.added.length} added</span>
              <span className="bad">-{recon.removed.length} removed</span>
              <span className="violet">~{recon.changed.length} changed</span>
              <span className="muted">{recon.unchangedCount} unchanged</span>
            </div>
          )}

          {preview && (
            <>
              <div className="row" style={{ margin: '14px 0 8px', flexWrap: 'wrap', gap: 8 }}>
                <span className="mono muted" style={{ fontSize: 11 }}>
                  {preview.documentId} · {preview.count} requirement(s)
                </span>
                <span className="spacer" />
                <select value={filter.level} onChange={(e) => setFilter((f) => ({ ...f, level: e.target.value }))}
                  style={{ width: 'auto' }}>
                  <option value="ALL">All levels</option>
                  <option value="L3">L3</option>
                  <option value="L4">L4</option>
                </select>
                <select value={filter.iface} onChange={(e) => setFilter((f) => ({ ...f, iface: e.target.value }))}
                  style={{ width: 'auto' }}>
                  <option value="ALL">All interfaces</option>
                  {ifaceOptions.map((i) => <option key={i} value={i}>{i}</option>)}
                </select>
              </div>
              <div style={{ maxHeight: 420, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--r)' }}>
                <table className="sigtable">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}>Lvl</th>
                      <th style={{ width: 70 }}>Aspect</th>
                      <th>Requirement ID</th>
                      <th>Text</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReqs.map((r) => (
                      <tr key={r.reqId}>
                        <td><span className={`tag ${r.level === 'L3' ? 'rx' : 'tx'}`}>{r.level}</span></td>
                        <td className="mono">{r.aspect}</td>
                        <td className="mono" style={{ fontSize: 11 }}>{r.reqId}</td>
                        <td style={{ fontFamily: 'var(--sans)' }}>{r.text}</td>
                      </tr>
                    ))}
                    {filteredReqs.length === 0 && (
                      <tr><td colSpan={4} className="muted" style={{ padding: 14, textAlign: 'center' }}>
                        No requirements match the filter.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ---- Requirements-to-signals traceability matrix ---- */}
      <TraceMatrix trace={trace} onDownload={downloadTraceCsv} hasSource={!!icdPayload()} />

      {/* ---- Save bar ---- */}
      <div className="card">
        <div className="card-body row">
          {templateErrors.length > 0 ? (
            <span className="bad mono" style={{ fontSize: 12 }}>
              Fix {templateErrors.length} template/ID error(s) before saving:
              {' '}{templateErrors[0].where} uses {templateErrors[0].bad}
            </span>
          ) : (
            <span className="muted mono" style={{ fontSize: 12 }}>
              Saving writes the config of record ({path}) via the single writer.
            </span>
          )}
          <span className="spacer" />
          <button className="btn primary" disabled={!canSave} onClick={save}>
            {saving ? 'Saving…' : 'Save config'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Traceability matrix card (signal <-> requirement coverage) ----
function TraceMatrix({ trace, onDownload, hasSource }) {
  const [show, setShow] = useState('ALL');   // ALL | GAPS
  const summary = trace?.summary;
  const rows = trace?.rows || [];
  const visible = rows.filter((r) => (show === 'ALL' ? true : !r.covered));

  const gapCount = summary
    ? (summary.L3?.uncovered?.length || 0) + (summary.L4?.uncovered?.length || 0)
    : 0;

  return (
    <div className="card">
      <div className="card-head">
        <h2>Traceability Matrix — signals → requirements</h2>
        <span className="spacer" />
        {trace ? (
          gapCount === 0
            ? <span className="ok mono" style={{ fontSize: 11 }}>● full coverage</span>
            : <span className="bad mono" style={{ fontSize: 11 }}>● {gapCount} NOT COVERED</span>
        ) : (
          <span className="muted mono" style={{ fontSize: 11 }}>run a preview to populate</span>
        )}
      </div>
      <div className="card-body">
        <div className="row" style={{ marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <span className="muted" style={{ fontSize: 12 }}>
            One row per packet (L3) and per signal (L4), each listing the requirement IDs that
            cover it. An element with no covering requirement is a coverage gap to close with a
            human-authored requirement in the RM tool.
          </span>
          <span className="spacer" />
          {trace && (
            <>
              <select value={show} onChange={(e) => setShow(e.target.value)} style={{ width: 'auto' }}>
                <option value="ALL">All rows</option>
                <option value="GAPS">Gaps only</option>
              </select>
              <button className="btn" onClick={onDownload} disabled={!hasSource}>
                ↓ Download trace matrix (CSV)
              </button>
            </>
          )}
          {!trace && (
            <button className="btn" onClick={onDownload} disabled={!hasSource}>
              ↓ Download trace matrix (CSV)
            </button>
          )}
        </div>

        {summary && (
          <div className="recon-strip" style={{ borderLeftColor: 'var(--phos)' }}>
            <span className="mono" style={{ fontSize: 11 }}>coverage:</span>
            <span className="ok">L3 {summary.L3.covered}/{summary.L3.total}</span>
            <span className="ok">L4 {summary.L4.covered}/{summary.L4.total}</span>
            {gapCount > 0 && <span className="bad">{gapCount} gap(s)</span>}
          </div>
        )}

        {trace && (
          <div style={{ maxHeight: 460, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--r)', marginTop: 12 }}>
            <table className="sigtable">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>Lvl</th>
                  <th>Interface</th>
                  <th>Packet</th>
                  <th>Signal</th>
                  <th style={{ width: 50 }}>#Req</th>
                  <th>Covering Requirement IDs</th>
                  <th style={{ width: 100 }}>Coverage</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r, i) => (
                  <tr key={`${r.iface}/${r.packet}/${r.signal}/${i}`}
                    style={!r.covered ? { background: 'rgba(255,92,92,.06)' } : undefined}>
                    <td><span className={`tag ${r.level === 'L3' ? 'rx' : 'tx'}`}>{r.level}</span></td>
                    <td className="mono">{r.iface}</td>
                    <td className="mono">{r.packet}</td>
                    <td className="mono">{r.signal}</td>
                    <td className="mono">{r.reqCount}</td>
                    <td className="mono" style={{ fontSize: 10.5 }}>{r.reqIds.join('; ')}</td>
                    <td>
                      {r.covered
                        ? <span className="ok mono" style={{ fontSize: 11 }}>COVERED</span>
                        : <span className="bad mono" style={{ fontSize: 11 }}>NOT COVERED</span>}
                    </td>
                  </tr>
                ))}
                {visible.length === 0 && (
                  <tr><td colSpan={7} className="muted" style={{ padding: 14, textAlign: 'center' }}>
                    {show === 'GAPS' ? 'No coverage gaps — every element is covered.' : 'No rows.'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---- ID format field with a token legend ----
function IdFormatField({ label, value, tokens, dflt, onChange }) {
  const bad = badPlaceholders(value, tokens || ID_TOKENS_FALLBACK);
  return (
    <div className="field">
      <label>{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        className={bad.length ? 'err' : ''} style={{ fontFamily: 'var(--mono)', fontSize: 12 }} />
      <span className="muted mono" style={{ fontSize: 10 }}>
        tokens: {(tokens || ID_TOKENS_FALLBACK).map((t) => `{${t}}`).join(' ')}
        {value !== dflt && <button className="btn ghost sm" style={{ marginLeft: 8 }} onClick={() => onChange(dflt)}>reset</button>}
      </span>
    </div>
  );
}

// ---- per-interface / per-signal override editor ----
function OverridesEditor({ draft, setDraft, meta, aspectByKey }) {
  const [open, setOpen] = useState(false);
  const [newIface, setNewIface] = useState('');
  const [newSig, setNewSig] = useState('');

  const patch = (p) => setDraft((d) => ({ ...d, ...p }));

  const addIface = () => {
    const id = newIface.trim();
    if (!id) return;
    patch({ interfaces: { ...(draft.interfaces || {}), [id]: { l3_aspects: null, suppress: [], templates: {} } } });
    setNewIface('');
  };
  const rmIface = (id) => {
    const x = { ...(draft.interfaces || {}) }; delete x[id]; patch({ interfaces: x });
  };
  const setIfaceOv = (id, ov) => patch({ interfaces: { ...(draft.interfaces || {}), [id]: ov } });

  const addSig = () => {
    const id = newSig.trim();
    if (!id) return;   // expected form: IFACE/PACKET/signal
    patch({ signals: { ...(draft.signals || {}), [id]: { suppress: [], templates: {} } } });
    setNewSig('');
  };
  const rmSig = (id) => {
    const x = { ...(draft.signals || {}) }; delete x[id]; patch({ signals: x });
  };
  const setSigOv = (id, ov) => patch({ signals: { ...(draft.signals || {}), [id]: ov } });

  const allAspects = meta.aspects.map((a) => a.key);

  return (
    <div className="card">
      <div className="card-head" style={{ cursor: 'pointer' }} onClick={() => setOpen(!open)}>
        <span className="mono muted">{open ? '▾' : '▸'}</span>
        <h2>Overrides (per interface / per signal)</h2>
        <span className="spacer" />
        <span className="muted mono" style={{ fontSize: 11 }}>
          {Object.keys(draft.interfaces || {}).length} iface · {Object.keys(draft.signals || {}).length} sig
        </span>
      </div>
      {open && (
        <div className="card-body">
          <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            Overrides take precedence: per-signal → per-interface → global → aspect default.
            Suppress drops that aspect; a template here replaces the wording for matching items.
          </div>

          {/* interface overrides */}
          <div className="ovr-section">
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="mono muted" style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase' }}>Interface overrides</span>
              <span className="spacer" />
              <input placeholder="IF-NAV-STATE" value={newIface}
                onChange={(e) => setNewIface(e.target.value)} style={{ width: 200, fontFamily: 'var(--mono)' }} />
              <button className="btn sm" onClick={addIface}>+ Add</button>
            </div>
            {Object.entries(draft.interfaces || {}).map(([id, ov]) => (
              <OverrideCard key={id} id={id} ov={ov} aspects={allAspects}
                aspectByKey={aspectByKey} hasL3Aspects
                l3Keys={meta.l3Aspects}
                onChange={(x) => setIfaceOv(id, x)} onRemove={() => rmIface(id)} />
            ))}
          </div>

          {/* signal overrides */}
          <div className="ovr-section" style={{ marginTop: 16 }}>
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="mono muted" style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase' }}>Signal overrides</span>
              <span className="spacer" />
              <input placeholder="IF-NAV-STATE/POSITION/latitude" value={newSig}
                onChange={(e) => setNewSig(e.target.value)} style={{ width: 280, fontFamily: 'var(--mono)' }} />
              <button className="btn sm" onClick={addSig}>+ Add</button>
            </div>
            {Object.entries(draft.signals || {}).map(([id, ov]) => (
              <OverrideCard key={id} id={id} ov={ov} aspects={allAspects}
                aspectByKey={aspectByKey}
                onChange={(x) => setSigOv(id, x)} onRemove={() => rmSig(id)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function OverrideCard({ id, ov, aspects, aspectByKey, onChange, onRemove, hasL3Aspects, l3Keys }) {
  const toggleSuppress = (key) => {
    const s = new Set(ov.suppress || []);
    s.has(key) ? s.delete(key) : s.add(key);
    onChange({ ...ov, suppress: aspects.filter((k) => s.has(k)) });
  };
  const setTmpl = (key, value) => {
    const t = { ...(ov.templates || {}) };
    if (value === '') delete t[key]; else t[key] = value;
    onChange({ ...ov, templates: t });
  };
  return (
    <div className="ovr-card">
      <div className="row">
        <span className="mono" style={{ fontSize: 12, color: 'var(--ink-0)' }}>{id}</span>
        <span className="spacer" />
        <button className="btn danger sm" onClick={onRemove}>Remove</button>
      </div>
      <div style={{ marginTop: 8 }}>
        <span className="muted mono" style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase' }}>Suppress aspects</span>
        <div className="checkbox-row" style={{ marginTop: 6 }}>
          {aspects.map((k) => (
            <span key={k} className={`chk ${(ov.suppress || []).includes(k) ? 'on' : ''}`}
              onClick={() => toggleSuppress(k)} style={{ fontSize: 11 }}>
              {k}
            </span>
          ))}
        </div>
      </div>
      <div style={{ marginTop: 10 }}>
        <span className="muted mono" style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase' }}>Template overrides</span>
        {aspects.map((k) => {
          const v = (ov.templates || {})[k];
          if (v == null) return null;
          const bad = badPlaceholders(v, aspectByKey[k]?.fields || []);
          return (
            <div key={k} style={{ marginTop: 6 }}>
              <div className="row" style={{ marginBottom: 2 }}>
                <span className="mono" style={{ fontSize: 11 }}>{k}</span>
                <span className="muted mono" style={{ fontSize: 10, marginLeft: 8 }}>
                  {(aspectByKey[k]?.fields || []).map((f) => `{${f}}`).join(' ')}
                </span>
                <span className="spacer" />
                <button className="btn ghost sm" onClick={() => setTmpl(k, '')}>×</button>
              </div>
              <input value={v} onChange={(e) => setTmpl(k, e.target.value)}
                className={bad.length ? 'err' : ''} style={{ fontFamily: 'var(--mono)', fontSize: 12 }} />
              {bad.length > 0 && (
                <div className="bright-line-warn">
                  ✕ {bad.map((b) => (b === '' ? '{}' : `{${b}}`)).join(', ')} not allowed for {k}.
                </div>
              )}
            </div>
          );
        })}
        <div className="row" style={{ marginTop: 6, gap: 6 }}>
          <select onChange={(e) => { if (e.target.value) { setTmpl(e.target.value, aspectByKey[e.target.value].defaultTemplate); e.target.value = ''; } }}
            defaultValue="" style={{ width: 'auto' }}>
            <option value="">+ override a template…</option>
            {aspects.filter((k) => (ov.templates || {})[k] == null)
              .map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}