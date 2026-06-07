// Thin API client. One function per backend endpoint, so adding a feature is
// adding one function here plus the component that calls it.

const J = { 'Content-Type': 'application/json' };

async function req(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
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
  generate: (id, definition, formats) =>
    req(`/api/projects/${id}/generate`, { method: 'POST', headers: J, body: JSON.stringify({ definition, formats }) }),
  artifactUrl: (id, filename) => `/api/projects/${id}/artifacts/${encodeURIComponent(filename)}`,
  exportXmlUrl: (id) => `/api/projects/${id}/export.xml`,

  importFile: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return req('/api/import', { method: 'POST', body: fd });
  },

  diff: (oldDef, newDef) =>
    req('/api/diff', { method: 'POST', headers: J, body: JSON.stringify({ old: oldDef, new: newDef }) }),

  diffFiles: (oldFile, newFile) => {
    const fd = new FormData();
    fd.append('old', oldFile);
    fd.append('new', newFile);
    return req('/api/diff-files', { method: 'POST', body: fd });
  },

  // Diff the current (in-memory) definition against an uploaded file.
  diffAgainstFile: (currentDef, file) => {
    const fd = new FormData();
    fd.append('file', file);
    return req('/api/import', { method: 'POST', body: fd }).then((r) => {
      if (!r.ok) throw new Error(r.issues?.[0]?.message || 'Import failed');
      return req('/api/diff', {
        method: 'POST', headers: J,
        body: JSON.stringify({ old: r.definition, new: currentDef }),
      });
    });
  },
};