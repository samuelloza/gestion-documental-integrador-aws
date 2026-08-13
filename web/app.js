const message = document.querySelector('#message');
const list = document.querySelector('#documents');
const apiBase = (window.APP_CONFIG?.apiBaseUrl || '').replace(/\/$/, '');
const api = `${apiBase}/api/documents`;
let session;
const roleLabel = {viewer: 'Público', editor: 'Funcionario', admin: 'Administrador'};

function tell(text, error = false) { message.textContent = ` ${text}`; message.className = `mt-4 min-h-6 text-sm ${error ? 'text-red-700' : 'text-emerald-700'}`; }
function headers(extra = {}) { return {...extra, Authorization: `Bearer ${sessionStorage.documentAuth || ''}`}; }
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
async function request(url, options = {}) {
  const response = await fetch(url, {...options, headers: headers(options.headers)}); const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Error inesperado'); return data;
}
async function refresh() {
  try {
    const {items} = await request(api);
    const canEdit = session.role !== 'viewer', canDelete = session.role === 'admin';
    list.innerHTML = items.length ? items.map(doc => `<article class="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-5"><div class="flex flex-col justify-between gap-2 sm:flex-row"><div><strong class="text-lg">${escapeHtml(doc.folio)}</strong><p class="text-slate-700">${escapeHtml(doc.name)}</p><small class="text-slate-500">${escapeHtml(doc.document_type)} · ${escapeHtml(doc.status)} · ${doc.size_bytes ?? 0} bytes</small></div><div class="flex flex-wrap gap-2">${doc.storage_key ? `<button class="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-white" data-download="${doc.id}">Descargar</button>` : ''}${canDelete ? ` <button class="rounded-lg bg-red-700 px-3 py-2 text-sm font-semibold text-white hover:bg-red-800" data-delete="${doc.id}">Eliminar</button>` : ''}</div></div>${canEdit ? `<form class="edit mt-4 grid gap-3 sm:grid-cols-4" data-id="${doc.id}"><input class="rounded-lg border border-slate-300 bg-white px-3 py-2" name="name" value="${escapeHtml(doc.name)}" required><input class="rounded-lg border border-slate-300 bg-white px-3 py-2" name="document_type" value="${escapeHtml(doc.document_type)}" required><select class="rounded-lg border border-slate-300 bg-white px-3 py-2" name="status">${['PENDING_UPLOAD','ACTIVE','ARCHIVED'].map(status => `<option${status === doc.status ? ' selected' : ''}>${status}</option>`).join('')}</select><button class="rounded-lg bg-cyan-800 px-3 py-2 text-sm font-semibold text-white hover:bg-cyan-900">Guardar cambios</button></form><label class="mt-3 block text-sm font-semibold text-slate-700">Subir archivo<input class="mt-1 block w-full text-sm font-normal" type="file" data-id="${doc.id}"></label>` : ''}</article>`).join('') : '<p class="mt-4 rounded-xl border border-dashed border-slate-300 p-6 text-center text-slate-600">No hay documentos.</p>';
  } catch (e) { tell(e.message, true); }
}
document.querySelector('#create').addEventListener('submit', async event => {
  event.preventDefault(); const form = new FormData(event.target);
  try { await request(api, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(Object.fromEntries(form))}); event.target.reset(); tell('Documento creado.'); refresh(); } catch(e) { tell(e.message, true); }
});
list.addEventListener('submit', async event => {
  if (!event.target.matches('form.edit')) return;
  event.preventDefault();
  try { await request(`${api}/${event.target.dataset.id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(Object.fromEntries(new FormData(event.target)))}); tell('Documento actualizado.'); refresh(); } catch(e) { tell(e.message, true); }
});
list.addEventListener('change', async event => {
  if (!event.target.matches('input[type=file]') || !event.target.files[0]) return;
  const file = event.target.files[0];
  try { await request(`${api}/${event.target.dataset.id}/content`, {method:'PUT', headers:{'Content-Type':file.type || 'application/octet-stream'}, body:file}); tell('Archivo subido.'); refresh(); } catch(e) { tell(e.message, true); }
});
list.addEventListener('click', async event => {
  const download = event.target.dataset.download;
  if (download) {
    try {
      const response = await fetch(`${api}/${download}/content`, {headers: headers()});
      if (!response.ok) throw new Error((await response.json()).error || 'Error inesperado');
      if (response.headers.get('Content-Type')?.includes('application/json')) window.open((await response.json()).url, '_blank', 'noopener');
      else window.open(URL.createObjectURL(await response.blob()), '_blank', 'noopener');
    } catch (e) { tell(e.message, true); }
    return;
  }
  const id = event.target.dataset.delete;
  if (!id) return;
  try { await request(`${api}/${id}`, {method:'DELETE'}); tell('Documento eliminado.'); refresh(); } catch(e) { tell(e.message, true); }
});
document.querySelector('#refresh').addEventListener('click', refresh);
document.querySelector('#logout').addEventListener('click', () => {
  sessionStorage.removeItem('documentAuth');
  window.location.assign('index.html');
});

async function loadSession() {
  try {
    session = await request(`${apiBase}/api/session`);
    document.querySelector('#identity').textContent = `${session.username} · ${roleLabel[session.role] || session.role}`;
    document.querySelector('#create').hidden = session.role === 'viewer';
    refresh();
  } catch (error) {
    sessionStorage.removeItem('documentAuth');
    window.location.replace('index.html');
  }
}

loadSession();
