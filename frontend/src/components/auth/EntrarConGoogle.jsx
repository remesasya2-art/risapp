/**
 * EntrarConGoogle — el botón, y qué hacer con lo que contesta el servidor.
 *
 * Tres salidas, y el que lo usa decide qué hacer con cada una:
 *   · `onSesion(data)`             entró: viene la sesión y el usuario.
 *   · `onDosPasos(data)`           es personal o administrador: falta el
 *                                  segundo factor, igual que con contraseña.
 *   · `onRegistroIncompleto(data)` no había cuenta: falta CPF y términos.
 *
 * Sin id de cliente no dibuja nada. No es un error: es que no está
 * configurado, y la pantalla sigue con correo y contraseña como siempre.
 */
import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { configDeGoogle, dibujarBotonDeGoogle } from '../../utils/google';

export default function EntrarConGoogle({ onSesion, onDosPasos, onRegistroIncompleto, texto = 'continue_with', oscuro = false }) {
  const [clientId, setClientId] = useState('');
  const [falla, setFalla] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const caja = useRef(null);
  // Los callbacks viven en un ref: el botón se dibuja una sola vez y tiene
  // que llamar a la versión de HOY de cada uno, no a la del primer render.
  const manejadores = useRef({});
  manejadores.current = { onSesion, onDosPasos, onRegistroIncompleto };

  useEffect(() => {
    let vigente = true;
    configDeGoogle().then((c) => { if (vigente) setClientId(c.clientId); });
    return () => { vigente = false; };
  }, []);

  useEffect(() => {
    if (!clientId || !caja.current) return;
    const alRecibir = async (credential) => {
      if (!credential) return;
      setOcupado(true);
      try {
        const { data } = await api.post('/auth/google', { credential });
        const m = manejadores.current;
        if (data?.registro_incompleto) return m.onRegistroIncompleto?.(data);
        if (data?.two_factor_required || data?.two_factor_enrollment_required) return m.onDosPasos?.(data);
        if (data?.session_token) return m.onSesion?.(data);
        toast.error('No pudimos entrar con Google.');
      } catch (e) {
        if (e?.response?.status === 429) toast.error('Demasiados intentos. Esperá unos minutos e intentá de nuevo.');
        else toast.error(e?.response?.data?.detail || 'No pudimos entrar con Google.');
      } finally {
        setOcupado(false);
      }
    };
    dibujarBotonDeGoogle(caja.current, clientId, alRecibir, { texto, oscuro }).catch(() => setFalla(true));
  }, [clientId, texto, oscuro]);

  if (!clientId) return null;

  return (
    <div data-testid="entrar-con-google" style={{ marginBottom: '24px' }}>
      <div ref={caja} style={{ display: 'flex', justifyContent: 'center', minHeight: '44px', opacity: ocupado ? 0.6 : 1 }} />
      {falla ? (
        <p style={{ fontSize: '13px', color: 'var(--t-texto-2)', textAlign: 'center', margin: '8px 0 0 0' }}>
          No se pudo cargar el botón de Google. Podés entrar con tu correo.
        </p>
      ) : null}
    </div>
  );
}
