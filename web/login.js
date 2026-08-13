const message = document.querySelector('#message');
const apiBase = (window.APP_CONFIG?.apiBaseUrl || '').replace(/\/$/, '');

function tell(text, error = false) { message.textContent = text; message.className = `mt-4 min-h-6 text-sm ${error ? 'text-red-700' : 'text-emerald-700'}`; }

document.querySelector('#login').addEventListener('submit', async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const response = await fetch(`https://cognito-idp.${window.APP_CONFIG.cognitoRegion}.amazonaws.com/`, {
      method: 'POST',
      headers: {'Content-Type': 'application/x-amz-json-1.1', 'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth'},
      body: JSON.stringify({AuthFlow: 'USER_PASSWORD_AUTH', ClientId: window.APP_CONFIG.cognitoClientId, AuthParameters: {USERNAME: form.get('username'), PASSWORD: form.get('password')}})
    });
    const data = await response.json();
    if (!response.ok || !data.AuthenticationResult?.AccessToken) throw new Error(data.message || 'No fue posible ingresar');
    sessionStorage.documentAuth = data.AuthenticationResult.AccessToken;
    const sessionResponse = await fetch(`${apiBase}/api/session`, {headers: {Authorization: `Bearer ${sessionStorage.documentAuth}`}});
    if (!sessionResponse.ok) throw new Error((await sessionResponse.json()).error || 'No fue posible ingresar');
    window.location.assign('documents.html');
  } catch (error) {
    sessionStorage.removeItem('documentAuth');
    tell(error.message, true);
  }
});
