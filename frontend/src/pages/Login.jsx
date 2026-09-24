import { useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, Fingerprint } from 'lucide-react';
import toast from 'react-hot-toast';
import PasswordRecovery from './PasswordRecovery';
import TwoFactorFlow from '../components/auth/TwoFactorFlow';
import Footer from '../components/Footer';
import { loginConHuella, webauthnSupported } from '../utils/webauthn';
import EntrarConGoogle from '../components/auth/EntrarConGoogle';
import CompletarRegistroGoogle from '../components/auth/CompletarRegistroGoogle';
import SelectorDeApariencia from '../components/tema/SelectorDeApariencia';
import { useTema } from '../contexts/TemaContext';

export default function Login() {
  const navigate = useNavigate();
  const { login, completeTwoFactorLogin } = useAuth();
  const { tema } = useTema();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [huellaLoading, setHuellaLoading] = useState(false);
  const [soportaHuella] = useState(webauthnSupported());
  const emailRef = useRef(null);
  const [showRecovery, setShowRecovery] = useState(false);
  const [twoFactorState, setTwoFactorState] = useState(null); // { mode, pendingToken, email }
  // Entró con Google y no tenía cuenta: falta CPF y términos.
  const [googlePendiente, setGooglePendiente] = useState(null);

  const entrarConSesion = (data) => {
    completeTwoFactorLogin(data.session_token, data.user);
    if (data.must_change_password) {
      toast.success('Por favor establece una nueva contraseña');
      navigate('/force-change-password');
    } else {
      toast.success('¡Bienvenido!');
      navigate('/');
    }
  };
  const pedirDosPasos = (data) => setTwoFactorState({
    mode: data.two_factor_required ? 'verify' : 'enroll',
    pendingToken: data.pending_token, email: data.email,
  });

  const handleHuella = async () => {
    if (!email) {
      toast.error('Escribe tu correo para entrar con huella');
      emailRef.current?.focus();
      emailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setHuellaLoading(true);
    try {
      const data = await loginConHuella(email);
      completeTwoFactorLogin(data.session_token, data.user);
      if (data.must_change_password) {
        toast.success('Por favor establece una nueva contraseña');
        navigate('/force-change-password');
      } else {
        toast.success('¡Bienvenido!');
        navigate('/');
      }
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(detail || 'No se pudo entrar con huella. Usa tu contraseña.');
    } finally {
      setHuellaLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Por favor completa todos los campos');
      return;
    }
    setLoading(true);
    try {
      const response = await login(email, password);

      // Handle 2FA challenge or enrollment
      if (response.two_factor_required) {
        setTwoFactorState({ mode: 'verify', pendingToken: response.pending_token, email: response.email });
        return;
      }
      if (response.two_factor_enrollment_required) {
        setTwoFactorState({ mode: 'enroll', pendingToken: response.pending_token, email: response.email });
        return;
      }

      // Normal flow
      if (response.must_change_password) {
        toast.success('Por favor establece una nueva contraseña');
        navigate('/force-change-password');
      } else {
        toast.success('¡Bienvenido!');
        navigate('/');
      }
    } catch (error) {
      // 429 Rate limit (slowapi devuelve {"error": "..."} no {"detail": "..."})
      if (error.response?.status === 429) {
        toast.error('Demasiados intentos. Espera unos minutos e intenta de nuevo.', { duration: 5000 });
      } else {
        toast.error(error.response?.data?.detail || 'Error al iniciar sesión');
      }
    } finally {
      setLoading(false);
    }
  };

  // LAS PANTALLAS INTERMEDIAS VAN SOBRE EL MISMO FONDO QUE EL LOGIN.
  //
  //   El segundo factor y el alta con Google todavía no pasaron al estilo
  //   nuevo: sus tarjetas son blancas y sus letras oscuras, escritas a mano.
  //   Por eso el fondo es la pared de colores pero la tarjeta sigue blanca en
  //   los dos modos. Si se pintara oscura, esas letras oscuras quedarían
  //   sobre negro. Cuando pasen, se quita el `background: '#fff'`.
  const intermedia = (contenido) => (
    <div className="con-tema t-base" style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <Pared />
      {/* `colorScheme: light` por lo mismo: sin él, en modo oscuro el
          navegador pintaría oscuros los campos de esa tarjeta blanca. */}
      <div style={{ position: 'relative', zIndex: 1, colorScheme: 'light' }}>{contenido}</div>
    </div>
  );

  if (twoFactorState) {
    return intermedia(
      <TwoFactorFlow
        mode={twoFactorState.mode}
        pendingToken={twoFactorState.pendingToken}
        email={twoFactorState.email}
        onSuccess={() => {
          toast.success('¡Bienvenido!');
          navigate('/');
        }}
      />,
    );
  }

  if (googlePendiente) {
    return intermedia(
      <div className="w-full max-w-md" style={{ background: '#fff', color: '#111827', borderRadius: '28px', boxShadow: 'var(--t-sombra)', padding: '40px 32px' }}>
        <CompletarRegistroGoogle pendiente={googlePendiente} onVolver={() => setGooglePendiente(null)} />
      </div>,
    );
  }

  // Show password recovery flow
  if (showRecovery) {
    return (
      <PasswordRecovery 
        onBack={() => setShowRecovery(false)} 
        onSuccess={() => {
          setShowRecovery(false);
          toast.success('Ahora puedes iniciar sesión con tu nueva contraseña');
        }}
      />
    );
  }

  const campo = {
    display: 'block', width: '100%', border: 0, outline: 'none', background: 'transparent',
    color: 'var(--t-texto)', font: 'inherit', fontSize: 17, padding: '2px 0 0',
  };

  return (
    <div className="con-tema t-base" style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
      <style>{ESTILOS}</style>
      <Pared />

      <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 5 }}>
        <SelectorDeApariencia />
      </div>

      <main style={{ position: 'relative', zIndex: 1, minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '72px 16px 40px' }}>
        <div style={{ width: '100%', maxWidth: 420, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <img
            src="/logo-ris.png"
            alt="RISApp"
            width={84}
            height={84}
            className="t-logo"
            style={{ borderRadius: 22 }}
          />

          <h1 style={{ fontSize: 34, fontWeight: 700, letterSpacing: '-.04em', margin: '22px 0 6px', textAlign: 'center' }}>
            Iniciar Sesión
          </h1>
          <p style={{ fontSize: 17, color: 'var(--t-texto-2)', margin: 0, textAlign: 'center' }}>
            Accede a tu cuenta
          </p>

          <div className="t-vidrio" style={{ width: '100%', borderRadius: 32, padding: 20, marginTop: 28 }}>
            {soportaHuella && (
              <button
                type="button"
                onClick={handleHuella}
                disabled={huellaLoading}
                className="t-boton t-secundario"
                style={{ width: '100%', minHeight: 52, marginBottom: 12, background: 'var(--t-vidrio-fuerte)', border: '1px solid var(--t-borde-vidrio)' }}
              >
                <Fingerprint size={20} style={{ color: 'var(--t-acento)' }} />
                {huellaLoading ? 'Verificando huella…' : 'Entrar con huella'}
              </button>
            )}

            {/* Con Google: sólo aparece si el servidor tiene id de cliente. */}
            <EntrarConGoogle texto="signin_with" oscuro={tema === 'oscuro'} onSesion={entrarConSesion} onDosPasos={pedirDosPasos} onRegistroIncompleto={setGooglePendiente} />

            {/* Divider */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0 14px', color: 'var(--t-texto-3)', fontSize: 13 }}>
              <div style={{ flex: 1, height: 1, background: 'var(--t-linea)' }} />
              O continúa con email
              <div style={{ flex: 1, height: 1, background: 'var(--t-linea)' }} />
            </div>

            <form onSubmit={handleSubmit} data-testid="login-form">
              {/* Los dos campos en un solo bloque, como en el iPhone. La
                  etiqueta va adentro y queda unida al campo por `htmlFor`:
                  tocarla pone el cursor en el campo, y el lector de pantalla
                  la lee al llegar. */}
              <div className="l-campos" style={{ borderRadius: 16, background: 'var(--t-campo)', overflow: 'hidden' }}>
                <div className="l-campo" style={{ padding: '10px 16px' }}>
                  <label htmlFor="login-email" style={{ display: 'block', fontSize: 12, color: 'var(--t-texto-2)' }}>
                    Correo electrónico
                  </label>
                  <input
                    id="login-email"
                    type="email"
                    autoComplete="email"
                    ref={emailRef}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    data-testid="email-input"
                    style={campo}
                  />
                </div>
                <div className="l-campo" style={{ padding: '10px 52px 10px 16px', position: 'relative', borderTop: '1px solid var(--t-linea)' }}>
                  <label htmlFor="login-clave" style={{ display: 'block', fontSize: 12, color: 'var(--t-texto-2)' }}>
                    Contraseña
                  </label>
                  <input
                    id="login-clave"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    data-testid="password-input"
                    style={campo}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                    data-testid="toggle-password"
                    style={{
                      position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                      width: 36, height: 36, display: 'grid', placeItems: 'center',
                      background: 'transparent', border: 0, cursor: 'pointer', color: 'var(--t-texto-3)',
                    }}
                  >
                    {showPassword ? <EyeOff size={20} strokeWidth={1.6} /> : <Eye size={20} strokeWidth={1.6} />}
                  </button>
                </div>
              </div>

              {/* Forgot Password Link */}
              <div style={{ textAlign: 'right', margin: '12px 4px 18px' }}>
                <button
                  type="button"
                  onClick={() => setShowRecovery(true)}
                  className="t-enlace"
                  style={{ background: 'transparent', border: 0, cursor: 'pointer', font: 'inherit', fontSize: 15, fontWeight: 500, padding: 0 }}
                  data-testid="forgot-password-link"
                >
                  ¿Olvidaste tu contraseña?
                </button>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                data-testid="login-submit-btn"
                className="t-boton t-primario"
                style={{ width: '100%', minHeight: 54, fontSize: 17 }}
              >
                {loading ? 'Iniciando sesión...' : 'Iniciar Sesión'}
              </button>
            </form>
          </div>

          {/* Register Link */}
          <p style={{ textAlign: 'center', color: 'var(--t-texto-2)', fontSize: 15, margin: '22px 0 0' }}>
            ¿No tienes cuenta?{' '}
            <Link to="/register" className="t-enlace" data-testid="register-link">
              Regístrate
            </Link>
          </p>
        </div>
      </main>
      <Footer />
    </div>
  );
}

// El foco del campo se marca en el bloque entero, no en el borde del campo:
// el campo no tiene borde, y un anillo alrededor de medio bloque se ve roto.
const ESTILOS = `
  .l-campos .l-campo:focus-within { box-shadow: inset 0 0 0 2px var(--t-acento); border-radius: 16px; }
  .l-campos input:focus-visible { outline: none; }
`;

function Pared() {
  return (
    <div className="t-pared" aria-hidden="true">
      <i style={{ width: 520, height: 520, left: -180, top: -140, background: 'var(--t-mancha-1)' }} />
      <i style={{ width: 440, height: 440, right: -160, top: '30%', background: 'var(--t-mancha-2)' }} />
      <i style={{ width: 480, height: 480, left: '10%', bottom: -160, background: 'var(--t-mancha-3)' }} />
    </div>
  );
}
