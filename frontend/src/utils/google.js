/**
 * utils/google.js — El botón de Google, cargado sólo cuando hace falta.
 *
 * EL ID DE CLIENTE LO DA EL SERVIDOR, NO EL BUNDLE
 *
 *   Se pregunta a `/auth/google/config`. Si viene vacío, no hay botón: así
 *   configurar es poner UNA variable en el servidor, y el orden entre poner
 *   la variable y desplegar el código no importa. Ponerlo en el bundle como
 *   `VITE_...` exigía compilar de nuevo para cambiarlo, y ya se vio lo que
 *   pasa cuando una variable del bundle y el código se desencuentran.
 *
 * EL SCRIPT DE GOOGLE SE CARGA A PEDIDO
 *
 *   No va en `index.html`: sólo las pantallas de entrar y registrarse lo
 *   necesitan, y sólo si hay id de cliente. El resto de la aplicación no le
 *   habla a Google para nada.
 */
import api from './api';

// La dirección exacta que permite la política de contenido del servidor
// (backend/services/csp.py). Si cambia acá, tiene que cambiar allá.
export const URL_DEL_SCRIPT = 'https://accounts.google.com/gsi/client';

let _config = null;

export async function configDeGoogle() {
  if (_config) return _config;
  try {
    const { data } = await api.get('/auth/google/config');
    _config = { clientId: String(data?.client_id || '').trim() };
  } catch {
    _config = { clientId: '' }; // sin el dato no hay botón; la pantalla sigue igual
  }
  return _config;
}

let _carga = null;

export function cargarGoogle() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id);
  if (_carga) return _carga;
  _carga = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = URL_DEL_SCRIPT;
    s.async = true;
    s.defer = true;
    s.onload = () => {
      if (window.google?.accounts?.id) resolve(window.google.accounts.id);
      else reject(new Error('Google no cargó'));
    };
    s.onerror = () => { _carga = null; reject(new Error('No se pudo cargar Google')); };
    document.head.appendChild(s);
  });
  return _carga;
}

/**
 * Dibuja el botón adentro de `elemento`. `alRecibirCredencial` recibe el
 * token firmado por Google, que es lo único que viaja al servidor.
 */
export async function dibujarBotonDeGoogle(elemento, clientId, alRecibirCredencial, { texto = 'continue_with', ancho = 340, oscuro = false } = {}) {
  const id = await cargarGoogle();
  id.initialize({
    client_id: clientId,
    callback: (respuesta) => alRecibirCredencial(respuesta?.credential),
    ux_mode: 'popup',
    auto_select: false,
    itp_support: true,
  });
  // Al cambiar de claro a oscuro se vuelve a dibujar en el mismo lugar: sin
  // vaciarlo antes, quedarían los dos botones, uno encima del otro.
  elemento.replaceChildren();
  id.renderButton(elemento, {
    // `filled_black` es la variante oscura que ofrece Google; el botón vive
    // en un marco suyo y no toma los colores de la página.
    type: 'standard', theme: oscuro ? 'filled_black' : 'outline', size: 'large', shape: 'pill',
    text: texto, width: ancho, locale: 'es',
  });
}
