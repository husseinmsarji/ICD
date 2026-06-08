import React, { useEffect, useRef, useState, useCallback } from 'react';
import { api } from './api.js';
import MetadataEditor from './MetadataEditor.jsx';
import InterfaceEditor from './InterfaceEditor.jsx';
import GeneratePanel from './GeneratePanel.jsx';
import DiffPanel from './DiffPanel.jsx';
import ReqgenPanel from './ReqgenPanel.jsx';

export default function App() {
  const [options, setOptions] = useState(null);
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [definition, setDefinition] = useState(null);
  const [projectName, setProjectName] = useState('');
  const [issues, setIssues] = useState([]);
  const [valid, setValid] = useState(null);     // null=unknown, true, false
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [priorFiles, setPriorFiles] = useState({});  // {revision: {content, name}}, transient (Flow A)
  const [view, setView] = useState('editor');    // 'editor' | 'reqgen'
  const fileRef = useRef();

  const showToast = useCallback((msg, err = false) => {
    setToast({ msg, err });
    setTimeout(() => setToast(null), 3200);
  }, []);

  // bootstrap
  useEffect(() => {
    api.options().then(setOptions).catch((e) => showToast(String(e), true));
    refreshProjects();
  }, []);

  const refreshProjects = () => api.listProjects().then(setProjects).catch(() => {});

  const openProject = async (id) => {
    const { meta, definition } = await api.getProject(id);
    setActiveId(id);
    setDefinition(definition);
    setProjectName(meta.name);
    setDirty(false);
    setValid(null);
    setIssues([]);
    setPriorFiles({});
    setView('editor');
  };

  const newProject = async () => {
    const meta = await api.createProject('Untitled ICD');
    await refreshProjects();
    openProject(meta.id);
    showToast('Project created');
  };

  // Debounced live validation whenever the definition changes.
  useEffect(() => {
    if (!definition || !activeId) return;
    const t = setTimeout(async () => {
      try {
        const r = await api.validate(activeId, definition);
        setValid(r.ok);
        setIssues(r.issues);
      } catch { /* ignore transient */ }
    }, 450);
    return () => clearTimeout(t);
  }, [definition, activeId]);

  const save = async () => {
    if (!activeId || !definition) return;
    setSaving(true);
    try {
      await api.saveProject(activeId, projectName, definition);
      setDirty(false);
      await refreshProjects();
      showToast('Saved');
    } catch (e) { showToast(String(e.message || e), true); }
    finally { setSaving(false); }
  };

  const del = async () => {
    if (!activeId) return;
    if (!confirm('Delete this project? This cannot be undone.')) return;
    await api.deleteProject(activeId);
    setActiveId(null); setDefinition(null);
    await refreshProjects();
    showToast('Project deleted');
  };

  const onImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const r = await api.importFile(file);
      if (!r.ok) { showToast(r.issues?.[0]?.message || 'Import failed', true); return; }
      const meta = await api.createProject(file.name.replace(/\.(xml|json)$/i, ''), r.definition);
      await refreshProjects();
      openProject(meta.id);
      showToast('Imported & created project');
    } catch (err) { showToast(String(err.message || err), true); }
    finally { e.target.value = ''; }
  };

  const updateDef = (patch) => { setDefinition(patch); setDirty(true); };
  const setPriorFile = (revision, content, name) =>
    setPriorFiles((prev) => ({ ...prev, [revision]: { content, name } }));

  const setMeta = (metadata) => updateDef({ ...definition, metadata });
  const setIface = (idx, iface) =>
    updateDef({ ...definition, interfaces: definition.interfaces.map((x, i) => i === idx ? iface : x) });
  const addIface = () => {
    // Seed a new interface from the interface field descriptors, so a new
    // registry field gets a sensible default with no change here.
    const blank = { packets: [] };
    for (const f of (options.interfaceFields || [])) {
      if (f.name === 'packets' || f.name === 'signals') continue;
      if (f.kind === 'enum') blank[f.jsonName] = f.enum?.[0] ?? '';
      else blank[f.jsonName] = f.required ? '' : null;
    }
    blank.id = `IF-${definition.interfaces.length + 1}`;
    blank.name = 'New Interface';
    if ('owningDocument' in blank) blank.owningDocument = definition.metadata.documentId;
    updateDef({ ...definition, interfaces: [...definition.interfaces, blank] });
  };
  const removeIface = (idx) =>
    updateDef({ ...definition, interfaces: definition.interfaces.filter((_, i) => i !== idx) });

  if (!options) return <div className="empty">Connecting…</div>;

  const sigCount = definition ? definition.interfaces.reduce((n, i) => n + i.packets.reduce((m, p) => m + p.signals.length, 0), 0) : 0;

  return (
    <div className="app">
      <div className="brand">
        <span className="dot" />
        <span className="name">ICDGEN</span>
        <span className="ver">v{options.toolVersion}</span>
      </div>

      <div className="topbar">
        <div className="tabs">
          <button className={`tab ${view === 'editor' ? 'active' : ''}`} onClick={() => setView('editor')}>
            ICD Editor
          </button>
          <button className={`tab ${view === 'reqgen' ? 'active' : ''}`} onClick={() => setView('reqgen')}>
            Requirements (reqgen)
          </button>
        </div>
        <span className="spacer" />
        {view === 'editor' && definition && (
          <>
            <input value={projectName} onChange={(e) => { setProjectName(e.target.value); setDirty(true); }}
              style={{ width: 280, fontFamily: 'var(--sans)', fontWeight: 600 }} />
            <button className="btn primary" disabled={saving || !dirty} onClick={save}>
              {saving ? 'Saving…' : dirty ? 'Save' : 'Saved'}
            </button>
            <button className="btn danger" onClick={del}>Delete</button>
          </>
        )}
      </div>

      <div className="sidebar">
        <div className="side-head">
          <span>Projects</span>
          <button className="btn sm" onClick={newProject}>+ New</button>
        </div>
        <div style={{ padding: '0 16px 10px' }}>
          <button className="btn ghost sm" style={{ width: '100%' }} onClick={() => fileRef.current.click()}>
            Import XML / JSON
          </button>
          <input ref={fileRef} type="file" accept=".xml,.json" style={{ display: 'none' }} onChange={onImport} />
        </div>
        {projects.map((p) => (
          <div key={p.id} className={`proj ${p.id === activeId && view === 'editor' ? 'active' : ''}`} onClick={() => openProject(p.id)}>
            <div className="pname">{p.name}</div>
            <div className="pmeta">{p.documentId} · rev {p.revision} · {p.interfaceCount} if / {p.signalCount} sig</div>
          </div>
        ))}
        {projects.length === 0 && <div className="muted" style={{ padding: 16, fontSize: 12 }}>No projects yet.</div>}
      </div>

      <div className="main">
        {view === 'reqgen' ? (
          <ReqgenPanel projects={projects} onToast={showToast} />
        ) : !definition ? (
          <>
            <div className="empty" style={{ height: 'auto', paddingTop: 40, paddingBottom: 30 }}>
              <div style={{ fontSize: 40 }}>⌖</div>
              <div>No project open.</div>
              <div className="row">
                <button className="btn primary" onClick={newProject}>Create new ICD</button>
                <button className="btn" onClick={() => fileRef.current.click()}>Import a file</button>
              </div>
            </div>
            <DiffPanel onToast={showToast} />
          </>
        ) : (
          <>
            <MetadataEditor meta={definition.metadata} onChange={setMeta}
              onPriorFile={setPriorFile} priorFiles={priorFiles} />

            <div className="row" style={{ margin: '20px 0 10px' }}>
              <h2 style={{ fontSize: 13, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--ink-1)' }}>
                Interfaces ({definition.interfaces.length})
              </h2>
              <span className="spacer" />
              <button className="btn sm" onClick={addIface}>+ Add interface</button>
            </div>

            {definition.interfaces.map((iface, idx) => (
              <InterfaceEditor key={idx} iface={iface} index={idx} options={options}
                onChange={(x) => setIface(idx, x)} onRemove={() => removeIface(idx)} />
            ))}
            {definition.interfaces.length === 0 && (
              <div className="muted" style={{ padding: 16 }}>No interfaces. Add one to begin.</div>
            )}

            <div style={{ marginTop: 22 }}>
              <GeneratePanel projectId={activeId} definition={definition} options={options}
                priorFiles={priorFiles} onToast={showToast} />
            </div>

            <div style={{ marginTop: 22 }}>
              <DiffPanel onToast={showToast} />
            </div>
          </>
        )}
      </div>

      <div className="statusbar">
        {view === 'reqgen' ? (
          <span className="muted">REQGEN · config editor · the file is the single source of truth</span>
        ) : definition ? (
          <>
            <span>{definition.metadata.documentId}</span>
            <span className="sep">│</span>
            <span>{definition.interfaces.length} interfaces · {sigCount} signals</span>
            <span className="sep">│</span>
            {valid === null ? <span className="muted">validating…</span>
              : valid ? <span className="ok">● SCHEMA VALID</span>
                : <span className="bad">● {issues.length} VALIDATION ERROR(S)</span>}
            {!valid && issues[0] && (
              <>
                <span className="sep">│</span>
                <span className="bad">{issues[0].line != null ? `L${issues[0].line}: ` : ''}{issues[0].message.slice(0, 90)}</span>
              </>
            )}
            <span className="spacer" />
            <span className={dirty ? 'bad' : 'ok'}>{dirty ? '○ UNSAVED' : '● SAVED'}</span>
          </>
        ) : <span className="muted">READY</span>}
      </div>

      {toast && <div className={`toast ${toast.err ? 'err' : ''}`}>{toast.msg}</div>}
    </div>
  );
}