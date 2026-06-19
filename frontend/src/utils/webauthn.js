import api from './api';

// --- Conversores base64url <-> ArrayBuffer (la API del navegador usa buffers) ---
function bufToB64url(buf) {
  const bytes = new Uint8Array(buf);
  let str = '';
  for (let i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64urlToBuf(b64url) {
  const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/');
  const pad = b64.length % 4 ? '='.repeat(4 - (b64.length % 4)) : '';
  const str = atob(b64 + pad);
  const bytes = new Uint8Array(str.length);
  for (let i = 0; i < str.length; i++) bytes[i] = str.charCodeAt(i);
  return bytes.buffer;
}

export function webauthnSupported() {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential && !!navigator.credentials;
}

function prepRegistration(options) {
  return {
    ...options,
    challenge: b64urlToBuf(options.challenge),
    user: { ...options.user, id: b64urlToBuf(options.user.id) },
    excludeCredentials: (options.excludeCredentials || []).map((c) => ({
      ...c, id: b64urlToBuf(c.id),
    })),
  };
}

function prepAuthentication(options) {
  return {
    ...options,
    challenge: b64urlToBuf(options.challenge),
    allowCredentials: (options.allowCredentials || []).map((c) => ({
      ...c, id: b64urlToBuf(c.id),
    })),
  };
}

// Activar huella en este dispositivo (usuario con sesión iniciada)
export async function activarHuella(label) {
  const { data: options } = await api.post('/webauthn/register/options');
  const publicKey = prepRegistration(options);
  const cred = await navigator.credentials.create({ publicKey });
  const payload = {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64url(cred.response.clientDataJSON),
      attestationObject: bufToB64url(cred.response.attestationObject),
    },
    clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
  };
  if (cred.response.getTransports) {
    try { payload.response.transports = cred.response.getTransports(); } catch (_) { /* opcional */ }
  }
  const { data } = await api.post('/webauthn/register/verify', { credential: payload, label });
  return data;
}

// Entrar con huella (sin sesión: requiere el email para ubicar las credenciales)
export async function loginConHuella(email) {
  const { data: options } = await api.post('/webauthn/login/options', { email });
  const publicKey = prepAuthentication(options);
  const cred = await navigator.credentials.get({ publicKey });
  const payload = {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64url(cred.response.clientDataJSON),
      authenticatorData: bufToB64url(cred.response.authenticatorData),
      signature: bufToB64url(cred.response.signature),
      userHandle: cred.response.userHandle ? bufToB64url(cred.response.userHandle) : null,
    },
    clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
  };
  const { data } = await api.post('/webauthn/login/verify', { email, credential: payload });
  return data;
}
