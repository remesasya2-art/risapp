import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, ArrowLeft, Gift } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { validarPassword, PASSWORD_HELP_TEXT } from '../utils/passwordPolicy';
import { formatearCpf, normalizarCpf, queLeFaltaAlCpf } from '../utils/cpf';
import EntrarConGoogle from '../components/auth/EntrarConGoogle';
import CompletarRegistroGoogle from '../components/auth/CompletarRegistroGoogle';
import TwoFactorFlow from '../components/auth/TwoFactorFlow';
import SelectorDeApariencia from '../components/tema/SelectorDeApariencia';
import { useTema } from '../contexts/TemaContext';

export default function Register() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { tema } = useTema();
  
  // Form fields
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [cpf, setCpf] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [referralCode, setReferralCode] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  
  // Verification step
  const [step, setStep] = useState(1); // 1 = form, 2 = verification
  // Con Google: sin cuenta todavía (falta CPF y términos), o una cuenta de
  // personal que tiene que pasar por el segundo factor.
  const [googlePendiente, setGooglePendiente] = useState(null);
  const [twoFactorState, setTwoFactorState] = useState(null);

  const entrarConSesion = () => {
    // Ya tenía cuenta: entra. Recarga entera, como al confirmar el código.
    localStorage.setItem('has_session', '1');
    localStorage.setItem('last_activity', Date.now().toString());
    toast.success('¡Bienvenido!');
    window.location.href = '/';
  };
  const pedirDosPasos = (data) => setTwoFactorState({
    mode: data.two_factor_required ? 'verify' : 'enroll',
    pendingToken: data.pending_token, email: data.email,
  });
  const [verificationCode, setVerificationCode] = useState('');
  const [resending, setResending] = useState(false);

  // Check for referral code in URL
  useEffect(() => {
    const refCode = searchParams.get('ref');
    if (refCode) {
      setReferralCode(refCode.toUpperCase());
    }
  }, [searchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!acceptedTerms) {
      toast.error('Debes aceptar los Términos y la Política de Privacidad');
      return;
    }
    
    if (!name || !email || !cpf || !password || !confirmPassword) {
      toast.error('Por favor completa todos los campos');
      return;
    }

    // El CPF se comprueba de verdad —los dos dígitos verificadores— y no sólo
    // contando once cifras. El servidor lo vuelve a comprobar: esto es para
    // que se entere antes de mandar el formulario, no después.
    const errorCpf = queLeFaltaAlCpf(cpf);
    if (errorCpf) {
      toast.error(errorCpf);
      return;
    }
    
    const errorPassword = validarPassword(password);
    if (errorPassword) {
      toast.error(errorPassword);
      return;
    }
    
    if (password !== confirmPassword) {
      toast.error('Las contraseñas no coinciden');
      return;
    }
    
    setLoading(true);
    try {
      const response = await api.post('/auth/register', {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        // Normalizado: «123.456.789-09» y «12345678909» son el mismo
        // documento, y el servidor tiene que recibir siempre la misma forma.
        cpf_number: normalizarCpf(cpf),
        password,
        confirm_password: confirmPassword,
        referral_code: referralCode.trim().toUpperCase() || null
      });
      
      toast.success(response.data.message || 'Código de verificación enviado');
      setStep(2); // Move to verification step
    } catch (error) {
      console.error('Register error:', error);
      toast.error(error.response?.data?.detail || 'Error al registrar');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async (e) => {
    e.preventDefault();
    
    if (!verificationCode || verificationCode.length !== 6) {
      toast.error('Ingresa el código de 6 dígitos');
      return;
    }
    
    setLoading(true);
    try {
      const response = await api.post('/auth/verify-email', {
        email: email.trim().toLowerCase(),
        code: verificationCode
      });
      
      // Save session token and redirect
      if (response.data.session_token) {
        localStorage.setItem('has_session', '1');
        localStorage.setItem('last_activity', Date.now().toString());
        toast.success('¡Cuenta creada exitosamente!');
        // Force page reload to update auth state
        window.location.href = '/';
      } else {
        toast.success('Registro completado. Por favor inicia sesión.');
        navigate('/login');
      }
    } catch (error) {
      console.error('Verification error:', error);
      toast.error(error.response?.data?.detail || 'Código inválido');
    } finally {
      setLoading(false);
    }
  };

  const handleResendCode = async () => {
    setResending(true);
    try {
      const response = await api.post('/auth/resend-verification-code', {
        email: email.trim().toLowerCase()
      });
      toast.success(response.data.message || 'Código reenviado');
    } catch (error) {
      console.error('Resend error:', error);
      toast.error(error.response?.data?.detail || 'Error al reenviar código');
    } finally {
      setResending(false);
    }
  };

  // LOS CAMPOS SE MARCAN CON CSS, NO CON `onFocus`/`onBlur`.
  //
  //   Antes cada campo pintaba su borde a mano al entrar y al salir, con los
  //   colores escritos (`#6366f1`, `#d1d5db`). En modo oscuro ese gris claro
  //   volvía a aparecer cada vez que se salía de un campo. La regla de
  //   `ESTILOS` hace lo mismo y respeta el modo.
  const inputStyle = {
    width: '100%',
    padding: '15px 16px',
    borderRadius: '14px',
    border: '1px solid transparent',
    fontSize: '16px',
    color: 'var(--t-texto)',
    backgroundColor: 'var(--t-campo)',
    outline: 'none',
    font: 'inherit',
  };

  const labelStyle = {
    display: 'block',
    fontSize: '14px',
    fontWeight: '600',
    color: 'var(--t-texto)',
    marginBottom: '8px'
  };

  const ayudaStyle = { fontSize: '12.5px', color: 'var(--t-texto-2)', margin: '6px 0 0 0' };

  const ojoStyle = {
    position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
    width: '36px', height: '36px', display: 'grid', placeItems: 'center',
    background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--t-texto-3)',
  };

  // Mismo criterio que en el login: el segundo factor y el alta con Google
  // siguen al modo con sus colores «en oscuro / el de siempre».
  const intermedia = (contenido) => (
    <Pantalla>
      <div style={{ position: 'relative', zIndex: 1, width: '100%', display: 'flex', justifyContent: 'center' }}>
        {contenido}
      </div>
    </Pantalla>
  );

  if (twoFactorState) {
    return intermedia(
      <TwoFactorFlow mode={twoFactorState.mode} pendingToken={twoFactorState.pendingToken} email={twoFactorState.email}
        onSuccess={() => { toast.success('¡Bienvenido!'); navigate('/'); }} />,
    );
  }

  if (googlePendiente) {
    return intermedia(
      <div style={{ width: '100%', maxWidth: '420px', background: 'var(--en-oscuro-superficie, #fff)', color: 'var(--en-oscuro-texto, #111827)', borderRadius: '28px', boxShadow: 'var(--t-sombra)', padding: '40px 32px' }}>
        <CompletarRegistroGoogle pendiente={googlePendiente} referralInicial={referralCode} onVolver={() => setGooglePendiente(null)} />
      </div>,
    );
  }

  // Verification Code Step (Step 2)
  if (step === 2) {
    return (
      <Pantalla>
        <Tarjeta>
          {/* Back Button */}
          <button
            type="button"
            onClick={() => setStep(1)}
            className="t-enlace"
            style={{
              display: 'flex', alignItems: 'center', gap: '6px', background: 'none', border: 'none',
              font: 'inherit', fontSize: '15px', fontWeight: 500, cursor: 'pointer', padding: 0, marginBottom: '20px',
            }}
          >
            <ArrowLeft size={18} />
            Volver
          </button>

          <Encabezado titulo="Verifica tu cuenta">
            Ingresa el código de 6 dígitos enviado a <br/>
            <span style={{ color: 'var(--t-acento)', fontWeight: 600 }}>{email}</span>
          </Encabezado>

          <form onSubmit={handleVerifyCode} data-testid="verification-form">
            {/* Verification Code Input */}
            <div style={{ marginBottom: '20px' }}>
              <label htmlFor="registro-codigo" style={labelStyle}>
                Código de verificación
              </label>
              <input
                id="registro-codigo"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={verificationCode}
                onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                data-testid="verification-code-input"
                className="r-campo"
                style={{
                  ...inputStyle,
                  textAlign: 'center',
                  fontSize: '26px',
                  letterSpacing: '10px',
                  fontWeight: '600'
                }}
              />
            </div>

            {/* Verify Button */}
            <button
              type="submit"
              disabled={loading || verificationCode.length !== 6}
              data-testid="verify-submit-btn"
              className="t-boton t-primario"
              style={{ width: '100%', minHeight: '54px', fontSize: '17px' }}
            >
              {loading ? 'Verificando...' : 'Verificar Código'}
            </button>
          </form>

          {/* Resend Code */}
          <div style={{ textAlign: 'center', marginTop: '22px' }}>
            <p style={{ fontSize: '14px', color: 'var(--t-texto-2)', margin: '0 0 6px 0' }}>
              ¿No recibiste el código?
            </p>
            <button
              type="button"
              onClick={handleResendCode}
              disabled={resending}
              className="t-enlace"
              style={{
                background: 'none', border: 'none', font: 'inherit', fontSize: '15px',
                cursor: resending ? 'not-allowed' : 'pointer', opacity: resending ? 0.6 : 1
              }}
            >
              {resending ? 'Reenviando...' : 'Reenviar código'}
            </button>
          </div>

          <PieDeLaTarjeta />
        </Tarjeta>
      </Pantalla>
    );
  }

  // Registration Form (Step 1)
  return (
    <Pantalla>
      <Tarjeta>
        <Encabezado titulo="Crear Cuenta">Comienza con tu billetera digital</Encabezado>

        {/* Con Google: sólo aparece si el servidor tiene id de cliente. */}
        <EntrarConGoogle texto="signup_with" oscuro={tema === 'oscuro'} onSesion={entrarConSesion} onDosPasos={pedirDosPasos} onRegistroIncompleto={setGooglePendiente} />

        {/* Divider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', margin: '4px 0 20px', color: 'var(--t-texto-3)', fontSize: '13px' }}>
          <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--t-linea)' }}></div>
          O continúa con email
          <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--t-linea)' }}></div>
        </div>

        <form onSubmit={handleSubmit} data-testid="register-form">
          {/* Name */}
          <div style={{ marginBottom: '18px' }}>
            <label htmlFor="registro-nombre" style={labelStyle}>
              Nombre completo
            </label>
            <input
              id="registro-nombre"
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="name-input"
              className="r-campo"
              style={inputStyle}
            />
          </div>

          {/* CPF — se pide acá porque es lo que ata la cuenta a una persona:
              un CPF, una cuenta. Y porque la recarga lo necesita igual, así
              que pedirlo una sola vez evita que lo tipee dos veces. */}
          <div style={{ marginBottom: '18px' }}>
            <label htmlFor="registro-cpf" style={labelStyle}>
              CPF
            </label>
            <input
              id="registro-cpf"
              type="text"
              inputMode="numeric"
              value={cpf}
              onChange={(e) => setCpf(formatearCpf(e.target.value))}
              placeholder="000.000.000-00"
              data-testid="cpf-input"
              className="r-campo"
              style={inputStyle}
            />
            <p style={ayudaStyle}>
              Es con el que vas a recargar. No vas a tener que cargarlo de nuevo
              al verificar tu cuenta.
            </p>
          </div>

          {/* Email */}
          <div style={{ marginBottom: '18px' }}>
            <label htmlFor="registro-correo" style={labelStyle}>
              Correo electrónico
            </label>
            <input
              id="registro-correo"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              data-testid="email-input"
              className="r-campo"
              style={inputStyle}
            />
          </div>

          {/* Password */}
          <div style={{ marginBottom: '18px' }}>
            <label htmlFor="registro-clave" style={labelStyle}>
              Contraseña
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="registro-clave"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="password-input"
                className="r-campo"
                style={{ ...inputStyle, paddingRight: '52px' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                style={ojoStyle}
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            <p style={ayudaStyle}>{PASSWORD_HELP_TEXT}</p>
          </div>

          {/* Confirm Password */}
          <div style={{ marginBottom: '20px' }}>
            <label htmlFor="registro-clave-2" style={labelStyle}>
              Confirmar contraseña
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="registro-clave-2"
                type={showConfirmPassword ? 'text' : 'password'}
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                data-testid="confirm-password-input"
                className="r-campo"
                style={{ 
                  ...inputStyle, 
                  paddingRight: '52px',
                  borderColor: confirmPassword && password !== confirmPassword ? 'var(--t-rojo)' : 'transparent'
                }}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                aria-label={showConfirmPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                style={ojoStyle}
              >
                {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            {confirmPassword && password !== confirmPassword && (
              <p style={{ ...ayudaStyle, color: 'var(--t-rojo)' }}>Las contraseñas no coinciden</p>
            )}
            {confirmPassword && password === confirmPassword && !validarPassword(password) && (
              <p style={{ ...ayudaStyle, color: 'var(--t-verde)' }}>Las contraseñas coinciden</p>
            )}
          </div>

          {/* Referral Code Field */}
          <div style={{ marginBottom: '18px' }}>
            <label htmlFor="registro-referido" style={labelStyle}>Código de referido (opcional)</label>
            <div style={{ position: 'relative' }}>
              <div style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', color: 'var(--t-texto-3)', display: 'grid' }}>
                <Gift size={20} />
              </div>
              <input
                id="registro-referido"
                type="text"
                value={referralCode}
                onChange={(e) => setReferralCode(e.target.value.toUpperCase())}
                placeholder="Ej: REF3A9F2B01"
                data-testid="register-referral-input"
                className="r-campo"
                style={{
                  ...inputStyle,
                  paddingLeft: '48px',
                  textTransform: 'uppercase'
                }}
              />
            </div>
            {/* DECIA «¡Código aplicado! Tu referidor recibirá una bonificación»,
                y mentía dos veces a la vez.
                  · «Aplicado» lo decidía el navegador, apenas la persona
                    escribía una letra. El servidor recién comprueba que el
                    código exista al pulsar Continuar, y si no existe devuelve
                    un 400. O sea que el cartel verde y el error rojo aparecían
                    juntos, en la misma pantalla.
                  · La bonificación no existe: todavía no está construida.
                    Prometer plata que la aplicación no sabe pagar es la clase
                    de cartel que después hay que explicarle a un cliente.
                Ahora dice lo único que es cierto mientras se escribe. */}
            {referralCode && (
              <p style={{ ...ayudaStyle, color: 'var(--t-acento)' }}>
                Te vas a registrar con esta invitación.
              </p>
            )}
          </div>

          {/* Aceptar términos */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', margin: '0 0 18px 0' }}>
            <input
              type="checkbox"
              id="acceptTerms"
              checked={acceptedTerms}
              onChange={(e) => setAcceptedTerms(e.target.checked)}
              style={{ marginTop: '3px', cursor: 'pointer', width: '18px', height: '18px', accentColor: 'var(--t-acento)' }}
            />
            <label htmlFor="acceptTerms" style={{ fontSize: '13.5px', color: 'var(--t-texto-2)', lineHeight: 1.5, cursor: 'pointer' }}>
              He leído y acepto los{' '}
              <a href="/legal#terminos" target="_blank" rel="noopener noreferrer" className="t-enlace" style={{ textDecoration: 'underline' }}>Términos y Condiciones</a>
              {' '}y la{' '}
              <a href="/legal#privacidad" target="_blank" rel="noopener noreferrer" className="t-enlace" style={{ textDecoration: 'underline' }}>Política de Privacidad</a>.
            </label>
          </div>
          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading || !acceptedTerms}
            data-testid="register-submit-btn"
            className="t-boton t-primario"
            style={{ width: '100%', minHeight: '54px', fontSize: '17px' }}
          >
            {loading ? 'Enviando código...' : 'Continuar'}
          </button>
        </form>

        <PieDeLaTarjeta />
      </Tarjeta>
    </Pantalla>
  );
}

const ESTILOS = `
  .r-campo { transition: border-color .15s ease, box-shadow .15s ease; }
  .r-campo:focus { border-color: var(--t-acento) !important; box-shadow: 0 0 0 3px rgba(91,79,233,.18); }
  .r-campo::placeholder { color: var(--t-texto-3); }
`;

// Las piezas van a nivel de módulo y no adentro de `Register`: un componente
// definido durante el render es un tipo nuevo en cada dibujo, React lo
// desmonta y lo vuelve a montar, y el campo que se estaba escribiendo pierde
// el foco a la primera tecla.
function Pantalla({ children }) {
  return (
    <div className="con-tema t-base" style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
      <style>{ESTILOS}</style>
      <div className="t-pared" aria-hidden="true">
        <i style={{ width: 520, height: 520, left: -180, top: -140, background: 'var(--t-mancha-1)' }} />
        <i style={{ width: 440, height: 440, right: -160, top: '30%', background: 'var(--t-mancha-2)' }} />
        <i style={{ width: 480, height: 480, left: '10%', bottom: -160, background: 'var(--t-mancha-3)' }} />
      </div>
      <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 5 }}>
        <SelectorDeApariencia />
      </div>
      <main style={{ position: 'relative', zIndex: 1, minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '72px 16px 40px' }}>
        {children}
      </main>
    </div>
  );
}

function Tarjeta({ children }) {
  return (
    <div className="t-vidrio" style={{ width: '100%', maxWidth: '440px', borderRadius: '32px', padding: '32px 24px' }}>
      {children}
    </div>
  );
}

function Encabezado({ titulo, children }) {
  return (
    <div style={{ textAlign: 'center', marginBottom: '26px' }}>
      <img src="/logo-ris.png" alt="RISApp" width={64} height={64} className="t-logo" style={{ borderRadius: '17px' }} />
      <h1 style={{ fontSize: '30px', fontWeight: 700, letterSpacing: '-.035em', margin: '18px 0 6px' }}>
        {titulo}
      </h1>
      <p style={{ fontSize: '16px', color: 'var(--t-texto-2)', margin: 0, lineHeight: 1.45 }}>
        {children}
      </p>
    </div>
  );
}

function PieDeLaTarjeta() {
  return (
    <p style={{ textAlign: 'center', fontSize: '15px', color: 'var(--t-texto-2)', margin: '24px 0 0' }}>
      ¿Ya tienes cuenta?{' '}
      <Link to="/login" className="t-enlace">
        Inicia sesión
      </Link>
    </p>
  );
}
