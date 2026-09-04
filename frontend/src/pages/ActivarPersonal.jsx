/**
 * ActivarPersonal.jsx — El primer acceso de un colaborador.
 *
 * POR QUE EXISTE
 *
 *   Recursos Humanos crea la cuenta con su rol y sus permisos, pero sin
 *   contraseña y sin el correo verificado. Antes eso dejaba a la persona
 *   afuera de la aplicación: el login la rechazaba, el "olvidé mi contraseña"
 *   también, y no había ninguna otra puerta. Esta es esa puerta.
 *
 * LO QUE PASA ACA, EN ORDEN
 *
 *   1. Llega con un enlace de un solo uso que le mandaron por correo.
 *   2. Se comprueba el enlace SIN gastarlo, para saludarla por su nombre.
 *   3. Configura su contraseña.
 *   4. Y sigue derecho al alta de la verificación en dos pasos, que para el
 *      personal es obligatoria: no se entrega una sesión antes de eso.
 *
 * EL TOKEN SALE DE LA BARRA DE DIRECCIONES ENSEGUIDA
 *
 *   Un enlace con la llave adentro queda en el historial del navegador y se
 *   filtra en la cabecera Referer de cualquier recurso que cargue la página.
 *   Se lee una vez, se guarda en memoria y se limpia la URL.
 */
import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { KeyRound, ShieldCheck, AlertCircle, Loader2 } from 'lucide-react';
import api from '../utils/api';
import TwoFactorFlow from '../components/auth/TwoFactorFlow';

const MORADO = '#5B4FE9';

const caja = {
  minHeight: '100vh', display: 'flex', alignItems: 'center',
  justifyContent: 'center', background: '#f7f7fb', padding: 20,
};
const tarjeta = {
  width: '100%', maxWidth: 420, background: '#fff', borderRadius: 16,
  padding: 30, border: '1px solid #ececf3',
};
const campo = {
  width: '100%', padding: '12px 14px', borderRadius: 10,
  border: '1px solid #e5e7eb', fontSize: 15, boxSizing: 'border-box',
};
const boton = {
  width: '100%', padding: '13px 16px', borderRadius: 10, border: 'none',
  background: MORADO, color: '#fff', fontSize: 15, fontWeight: 700,
  cursor: 'pointer', marginTop: 4,
};

export default function ActivarPersonal() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  // El token se toma una sola vez y se saca de la URL enseguida.
  const [token] = useState(() => params.get('token') || '');
  // Sin token no hay nada que consultar, así que el estado ya arranca
  // resuelto. Decidirlo dentro del efecto sería un setState sincrónico que
  // dispara un render en cascada.
  const [mirando, setMirando] = useState(() => Boolean(params.get('token')));
  const [invitacion, setInvitacion] = useState(null);
  const [errorDeEnlace, setErrorDeEnlace] = useState(
    () => (params.get('token') ? '' : 'El enlace está incompleto. Abrilo tal como llegó al correo.'),
  );

  const [clave, setClave] = useState('');
  const [repetida, setRepetida] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState('');

  // Cuando la clave queda lista, el backend devuelve el token de enrolamiento
  // de 2FA y la pantalla pasa a ese paso.
  const [dosPasos, setDosPasos] = useState(null);

  useEffect(() => {
    if (params.get('token')) {
      setParams({}, { replace: true });
    }
    // Se limpia una sola vez, al montar: el token ya está en el estado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let vigente = true;
    if (!token) return undefined;
    api.post('/auth/personal/invitacion', { token })
      .then(({ data }) => { if (vigente) setInvitacion(data); })
      .catch((e) => {
        if (!vigente) return;
        setErrorDeEnlace(
          e.response?.status === 429
            ? 'Demasiados intentos. Esperá unos minutos y volvé a abrir el enlace.'
            : (e.response?.data?.detail
               || 'Este enlace no es válido o ya venció. Pedile a tu administrador que te lo reenvíe.'),
        );
      })
      .finally(() => { if (vigente) setMirando(false); });
    return () => { vigente = false; };
  }, [token]);

  const activar = async (e) => {
    e.preventDefault();
    setError('');
    if (clave !== repetida) {
      setError('Las contraseñas no coinciden');
      return;
    }
    setEnviando(true);
    try {
      const { data } = await api.post('/auth/personal/activar', {
        token, password: clave, confirm_password: repetida,
      });
      setDosPasos({ pendingToken: data.pending_token, email: data.email });
    } catch (e2) {
      setError(
        e2.response?.status === 429
          ? 'Demasiados intentos. Esperá unos minutos.'
          : (e2.response?.data?.detail || 'No se pudo configurar la contraseña'),
      );
    } finally {
      setEnviando(false);
    }
  };

  if (dosPasos) {
    return (
      <div style={caja}>
        <div style={tarjeta}>
          <TwoFactorFlow
            mode="enroll"
            pendingToken={dosPasos.pendingToken}
            email={dosPasos.email}
            onSuccess={() => navigate('/admin')}
          />
        </div>
      </div>
    );
  }

  if (mirando) {
    return (
      <div style={caja}>
        <div style={{ ...tarjeta, textAlign: 'center', color: '#6b7280' }}>
          <Loader2 size={26} color={MORADO} style={{ marginBottom: 10 }} />
          <div style={{ fontSize: 14 }}>Comprobando el enlace…</div>
        </div>
      </div>
    );
  }

  if (errorDeEnlace) {
    return (
      <div style={caja}>
        <div style={tarjeta}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <AlertCircle size={22} color="#dc2626" style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <h2 style={{ margin: '0 0 8px', fontSize: 17, color: '#111827' }}>
                No pudimos abrir tu invitación
              </h2>
              <p style={{ margin: 0, fontSize: 14, color: '#4b5563', lineHeight: 1.6 }}>
                {errorDeEnlace}
              </p>
            </div>
          </div>
          <Link
            to="/login"
            style={{
              display: 'block', textAlign: 'center', marginTop: 22,
              fontSize: 14, color: MORADO, fontWeight: 600,
            }}
          >
            Ir al inicio de sesión
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div style={caja}>
      <div style={tarjeta}>
        <div style={{
          width: 44, height: 44, borderRadius: 12, background: '#f0eeff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: 16,
        }}
        >
          <KeyRound size={22} color={MORADO} />
        </div>

        <h1 style={{ margin: '0 0 6px', fontSize: 21, color: '#111827' }}>
          Hola{invitacion?.nombre ? `, ${invitacion.nombre.split(' ')[0]}` : ''}
        </h1>
        <p style={{ margin: '0 0 22px', fontSize: 14, color: '#6b7280', lineHeight: 1.6 }}>
          {invitacion?.cargo
            ? <>Se creó tu perfil de <strong>{invitacion.cargo}</strong>. </>
            : 'Se creó tu perfil. '}
          Configurá tu contraseña para {invitacion?.email}.
        </p>

        <form onSubmit={activar} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label htmlFor="clave" style={{ fontSize: 13, color: '#374151', fontWeight: 600 }}>
              Contraseña
            </label>
            <input
              id="clave"
              type="password"
              value={clave}
              onChange={(ev) => setClave(ev.target.value)}
              style={{ ...campo, marginTop: 6 }}
              autoComplete="new-password"
              required
            />
          </div>
          <div>
            <label htmlFor="repetida" style={{ fontSize: 13, color: '#374151', fontWeight: 600 }}>
              Repetir contraseña
            </label>
            <input
              id="repetida"
              type="password"
              value={repetida}
              onChange={(ev) => setRepetida(ev.target.value)}
              style={{ ...campo, marginTop: 6 }}
              autoComplete="new-password"
              required
            />
          </div>

          {error && (
            <div style={{
              background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10,
              padding: '10px 12px', fontSize: 13, color: '#b91c1c',
            }}
            >
              {error}
            </div>
          )}

          <div style={{
            display: 'flex', gap: 9, alignItems: 'flex-start',
            background: '#f7f7fb', borderRadius: 10, padding: '11px 12px',
            fontSize: 12.5, color: '#4b5563', lineHeight: 1.55,
          }}
          >
            <ShieldCheck size={16} color={MORADO} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              Al continuar vas a activar la verificación en dos pasos. Es
              obligatoria para todo el personal: tené a mano tu app de
              autenticación.
            </span>
          </div>

          <button type="submit" disabled={enviando} style={{ ...boton, opacity: enviando ? 0.6 : 1 }}>
            {enviando ? 'Configurando…' : 'Configurar mi acceso'}
          </button>
        </form>
      </div>
    </div>
  );
}
