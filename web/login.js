const message = document.querySelector('#message');
const apiBase = (window.APP_CONFIG?.apiBaseUrl || '').replace(/\/$/, '');

function tell(text, error = false) { message.textContent = text; message.className = `mt-4 min-h-6 text-sm ${error ? 'text-red-700' : 'text-emerald-700'}`; }

document.querySelector('#login').addEventListener('submit', async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  sessionStorage.documentAuth = btoa(`${form.get('username')}:${form.get('password')}`);
  try {
    const response = await fetch(`${apiBase}/api/session`, {headers: {Authorization: `Basic ${sessionStorage.documentAuth}`}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No fue posible ingresar');
    window.location.assign('documents.html');
  } catch (error) {
    sessionStorage.removeItem('documentAuth');
    tell(error.message, true);
  }
});
