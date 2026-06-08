// Thin API client. One function per backend endpoint, so adding a feature is
// adding one function here plus the component that calls it.

const J = { 'Content-Type': 'application/json' };

async function req(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    // Prefer FastAPI's {detail: ...} message when present (e.g. a 400 from a
    // bright-line config violation), so the UI can show the specific reason.
    let detail = '';
    try {
      const j = await res.clone().json();
      if (j && j.detail) detail = j.detail;
    } catch { /* not json */ }
    if (!detail) detail = await res.text().catch(() => '');
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export const api = {
  health: () => req('/api/health'),
  options: () => req('/api/meta/options'),

  listProjects: () => req('/api/projects'),
  createProject: (name, definition) =>
    req('/api/projects', { method: 'POST', headers: J, body: JSON.stringify({ name, definition }) }),
  getProject: (id) => req(`/api/projects/${id}`),
  saveProject: (id, name, definition) =>
    req(`/api/projects/${id}`, { method: 'PUT', headers: J, body: JSON.stringify({ name, definition }) }),
  deleteProject: (id) => req(`/api/projects/${id}`, { method: 'DELETE' }),

  validate: (id, definition) =>
    req(`/api/projects/${id}/validate`, { method: 'POST', headers: J, body: JSON.stringify({ definition }) }),
  generate: (id, definition, formats, priorFiles) =>
    req(`/api/projects/${id}/generate`, { method: 'POST', headers: J,
      body: JSON.stringify({ definition, formats, priorFiles: priorFiles || undefined }) }),
  artifactUrl: (id, filename) => `/api/projects/${id}/artifacts/${encodeURIComponent(filename)}`,
  exportXmlUrl: (id) => `/api/projects/${id}/export.xml`,

  importFile: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return req('/api/import', { method: 'POST', body: fd });
  },

  diff: (oldDef, newDef) =>
    req('/api/diff', { method: 'POST', headers: J, body: JSON.stringify({ old: oldDef, new: newDef }) }),

  // Two-file diff -> downloads a formatted PDF change report (no JSON).
  // Throws with the server's message (e.g. which side failed to parse).
  diffReportPdf: async (oldFile, newFile) => {
    const fd = new FormData();
    fd.append('old', oldFile);
    fd.append('new', newFile);
    const res = await fetch('/api/diff-report', { method: 'POST', body: fd });
    if (!res.ok) {
      let msg = `${res.status} ${res.statusText}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch { /* not json */ }
      throw new Error(msg);
    }
    const blob = await res.blob();
    // Pull the filename from the Content-Disposition header when present.
    const cd = res.headers.get('content-disposition') || '';
    const m = cd.match(/filename="?([^"]+)"?/);
    const filename = m ? m[1] : 'icd_diff.pdf';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    return filename;
  },

  // ---- reqgen config editor ----
  // The config file is the single record of truth; these mirror it. `saveReqgenConfig`
  // is the only mutating call and the backend rejects (400) a bright-line violation.
  reqgenMeta: () => req('/api/reqgen/meta'),
  reqgenConfig: () => req('/api/reqgen/config'),
  saveReqgenConfig: (config) =>
    req('/api/reqgen/config', { method: 'PUT', headers: J, body: JSON.stringify({ config }) }),
  reqgenPreview: (config, icd) =>
    req('/api/reqgen/preview', { method: 'POST', headers: J,
      body: JSON.stringify({ config, ...icd }) }),   // icd = {icdProjectId} | {icdXml}
  reqgenReconcile: (config, icd) =>
    req('/api/reqgen/reconcile', { method: 'POST', headers: J,
      body: JSON.stringify({ config, ...icd }) }),
};