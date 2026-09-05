/**
 * Profile.jsx — Mi Perfil.
 *
 * POR QUE SE REHIZO
 *
 *   Era la última pantalla grande con diseño propio: fondo con degradado
 *   violeta y celeste, tarjetas de 20px de radio al lado de tarjetas de 16px,
 *   y cada bloque con su paleta —#dbeafe acá, #dcfce7 allá, #fef3c7 más
 *   abajo—. Al lado de los tres flujos de envío, que ya usan
 *   `components/flujo`, se notaba de otra época.
 *
 *   Ahora usa EL MISMO módulo. No uno parecido.
 *
 * LO QUE NO ERA CUESTION DE ESTILO
 *
 *   1. LA FOTO SE LEIA DE UN CAMPO QUE NO EXISTE (`user.picture`; el modelo
 *      declara `profile_picture`). Ver `utils/perfil.js`.
 *
 *   2. SE MANDABA UNA SELFIE FALSA AL CAMBIAR LA CONTRASEÑA:
 *      `selfie_image: 'data:image/png;base64,placeholder'`. El endpoint no
 *      recibe ese campo —`ChangePasswordRequest` tiene tres— así que Pydantic
 *      lo tiraba. Código que finge un requisito que no existe: el próximo que
 *      lo lea va a buscar la cámara que nunca hubo.
 *
 *   3. LA POLITICA DE CONTRASEÑA VIVIA EN UN `placeholder`. El texto con las
 *      cinco reglas se borraba al escribir la primera letra, justo cuando hace
 *      falta. Ahora es la lista en vivo que ya usa la pantalla de recuperación.
 *
 *   4. EL CAMBIO NO EXIGIA QUE LA CONTRASEÑA FUERA DISTINTA. Ver
 *      `problemaDelCambioDeClave` en `utils/perfil.js`.
 *
 *   5. «VOLVER» SALIA DE LA APLICACION cuando se entraba directo a /perfil
 *      (un enlace, la aplicación instalada): `navigate(-1)` sin historial
 *      propio devuelve al sitio anterior. Ahora cae al inicio.
 *
 *   6. EL PERMISO DENEGADO NO SE EXPLICABA. Si el usuario había bloqueado las
 *      notificaciones, el interruptor se veía apagado y clickearlo no hacía
 *      nada: el navegador ya no vuelve a preguntar. Ahora lo dice y dice dónde
 *      se arregla.
 *
 *   7. «CERRAR SESION» SALIA AL PRIMER TOQUE. Es la única acción de la
 *      pantalla que deshace algo, y estaba a la misma distancia que abrir un
 *      formulario: un toque mal apuntado en la fila de arriba y te vas.
 *      Pregunta en la fila misma —no con `window.confirm`, que se puede
 *      bloquear y devuelve `false` sin que nadie se entere—.
 *
 * QUE NO SE TOCO
 *
 *   Los códigos de respaldo 2FA: misma llamada, mismas validaciones, mismo
 *   flujo. Sólo cambió cómo se ve. Y `logout()` sigue siendo el mismo: lo que
 *   se agregó es la pregunta de antes, no otra forma de salir.
 */
import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  ArrowLeft, Mail, Phone, Shield, Lock, LogOut, Check, ChevronRight,
  Bell, BellOff, Gem, Crown, Users, Gift, IdCard,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { passwordRules } from '../utils/passwordPolicy';
import pushService from '../utils/pushService';
import PinSettings from '../components/PinSettings';
import WebAuthnSettings from '../components/WebAuthnSettings';
import { Boton, Aviso } from '../components/flujo';
import {
  C, HOJA, tarjeta, etiqueta, microEtiqueta, campo, ayuda, iniciales,
} from '../components/flujo/estilos';
import {
  convieneVerificar, cpfDelPerfil, estadoDeVerificacion, fotoDePerfil,
  motivoSinNotificaciones, nombreVisible, panelDelRol, problemaDelCambioDeClave,
} from '../utils/perfil';

/* ─── Piezas de esta pantalla ─────────────────────────────────────────────
   A nivel de módulo y no adentro del componente: React trata un componente
   definido durante el render como un tipo nuevo en cada dibujo, lo desmonta y
   lo vuelve a montar, y el campo que estabas escribiendo pierde el foco a la
   primera tecla. Es el mismo motivo por el que `PinSettings` y
   `WebAuthnSettings` dejaron de declarar su `Header` adentro.            */

const TONOS = {
  exito: [C.exitoSuave, C.exito],
  alerta: [C.alertaSuave, C.alerta],
  error: [C.errorSuave, C.error],
  neutro: [C.fondo, C.suave],
};

function Insignia({ tono, children }) {
  const [fondo, color] = TONOS[tono] || TONOS.neutro;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '4px 10px', borderRadius: '999px', background: fondo, color,
      fontSize: '12px', fontWeight: 700,
    }}>
      {children}
    </span>
  );
}

/** Una fila de dato: el icono, la etiqueta chica y el valor.
 *
 *  El icono se saca de `props` en una línea aparte, y no destructurado en la
 *  firma, por lo mismo que en `components/flujo/index.jsx`: el `no-unused-vars`
 *  de este proyecto no cuenta `<Icono />` como uso, y su `varsIgnorePattern`
 *  perdona las VARIABLES en mayúscula, no los argumentos. */
function Dato(props) {
  const { titulo, valor } = props;
  const Icono = props.Icono;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '12px', padding: '13px 14px',
      background: C.fondo, borderRadius: '12px', minWidth: 0,
    }}>
      <Icono size={18} color={C.tenue} style={{ flexShrink: 0 }} />
      <span style={{ minWidth: 0 }}>
        <span style={{ ...microEtiqueta, display: 'block' }}>{titulo}</span>
        <span style={{
          display: 'block', fontSize: '14.5px', color: C.tinta, fontWeight: 600,
          marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {valor}
        </span>
      </span>
    </div>
  );
}

/** Una fila de la tarjeta de cuenta. Ver la nota de `Dato` sobre el icono. */
function Fila(props) {
  const { texto, detalle, tono = 'neutro', onClick, testid, ultima, flecha = true } = props;
  const Icono = props.Icono;
  const [fondo, color] = TONOS[tono] || TONOS.neutro;
  const cuerpo = (
    <>
      <span style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
        <span style={{
          width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
          background: fondo, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icono size={18} color={color} />
        </span>
        <span style={{ minWidth: 0, textAlign: 'left' }}>
          <span style={{
            display: 'block', fontSize: '14.5px', fontWeight: 600,
            color: tono === 'error' ? C.error : C.tinta,
          }}>
            {texto}
          </span>
          {detalle ? (
            <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
              {detalle}
            </span>
          ) : null}
        </span>
      </span>
      {flecha ? <ChevronRight size={18} color={C.tenue} style={{ flexShrink: 0 }} /> : null}
    </>
  );

  return (
    <button type="button" onClick={onClick} className="env-tap" data-testid={testid}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: '12px', width: '100%', padding: '14px 16px', background: 'transparent',
        border: 'none', borderBottom: ultima ? 'none' : `1px solid ${C.linea}`,
        cursor: 'pointer',
      }}>
      {cuerpo}
    </button>
  );
}

/** El interruptor de las notificaciones. */
function Interruptor({ encendido, onClick, disabled, testid }) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled} data-testid={testid}
      role="switch" aria-checked={encendido} aria-label="Notificaciones push"
      style={{
        width: '50px', height: '28px', borderRadius: '999px', flexShrink: 0,
        border: 'none', position: 'relative', transition: 'background-color .15s ease',
        background: encendido ? C.exito : C.lineaFuerte,
        cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
      }}>
      <span style={{
        position: 'absolute', top: '3px', left: encendido ? '25px' : '3px',
        width: '22px', height: '22px', borderRadius: '50%', background: '#fff',
        transition: 'left .15s ease', boxShadow: '0 1px 3px rgba(16,24,40,.25)',
      }} />
    </button>
  );
}

/** El checklist de la contraseña, en vivo. Las reglas salen de passwordPolicy. */
function ReglasDeClave({ valor }) {
  const reglas = passwordRules(valor);
  const filas = [
    [reglas.length, 'Al menos 8 caracteres'],
    [reglas.uppercase, 'Una mayúscula'],
    [reglas.lowercase, 'Una minúscula'],
    [reglas.number, 'Un número'],
    [reglas.special, 'Un símbolo'],
  ];
  return (
    <ul style={{
      listStyle: 'none', margin: '10px 0 0 0', padding: 0,
      display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px 12px',
    }}>
      {filas.map(([ok, texto]) => (
        <li key={texto} style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          fontSize: '12px', color: ok ? C.exito : C.tenue,
        }}>
          <Check size={13} strokeWidth={3} style={{ flexShrink: 0, opacity: ok ? 1 : 0.35 }} />
          {texto}
        </li>
      ))}
    </ul>
  );
}

/* ─── La pantalla ──────────────────────────────────────────────────────── */

export default function Profile() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [cambiandoClave, setCambiandoClave] = useState(false);
  const [claveALaVista, setClaveALaVista] = useState(false);
  const [clave, setClave] = useState({ actual: '', nueva: '', repetida: '' });
  const [guardando, setGuardando] = useState(false);

  const [pushActivo, setPushActivo] = useState(false);
  const [pushOcupado, setPushOcupado] = useState(false);
  const [pushSoporte, setPushSoporte] = useState(null);

  const [cerrandoSesion, setCerrandoSesion] = useState(false);

  const [ver2FA, setVer2FA] = useState(false);
  const [codigo2FA, setCodigo2FA] = useState('');
  const [respaldos, setRespaldos] = useState(null);
  const [ocupado2FA, setOcupado2FA] = useState(false);

  const estado = estadoDeVerificacion(user?.verification_status);
  const foto = fotoDePerfil(user);
  const cpf = cpfDelPerfil(user);
  const panel = panelDelRol(user?.role);
  const esSuperAdmin = user?.role === 'super_admin';
  const problemaDeLaClave = problemaDelCambioDeClave(clave);
  const empezoAEscribir = Boolean(clave.actual || clave.nueva || clave.repetida);
  const avisoPush = motivoSinNotificaciones(pushSoporte);
  const puedeUsarPush = pushSoporte !== null && !avisoPush;

  // La lectura del estado vive DENTRO del efecto. Definida afuera y llamada
  // acá, el linter ve un setState sincrónico en el cuerpo del efecto —y tiene
  // razón en el caso general—. Adentro queda claro que corre después del
  // montaje y una sola vez.
  useEffect(() => {
    let vigente = true;

    (async () => {
      const info = pushService.getSupportInfo();
      if (vigente) setPushSoporte(info);
      if (!pushService.isSupported()) return;
      try {
        const estadoPush = await pushService.getStatus();
        if (vigente) setPushActivo(Boolean(estadoPush?.enabled && estadoPush?.subscribed));
      } catch {
        // Sin respuesta del servidor se muestra apagado, que es el estado
        // seguro: el usuario puede encenderlo y ahí se entera de si va.
      }
    })();

    // Si el usuario se va antes de que conteste, no se escribe estado sobre
    // una pantalla desmontada.
    return () => { vigente = false; };
  }, []);

  /* ── Volver ──────────────────────────────────────────────────────────
     `navigate(-1)` a secas se va de la aplicación cuando se entró directo a
     esta dirección: un enlace del correo, la aplicación instalada, un
     refresco. La pantalla anterior es el sitio del que venía.            */
  const volver = () => {
    if (window.history.length > 1) navigate(-1);
    else navigate('/');
  };

  const alternarPush = async () => {
    if (avisoPush) return toast.error(avisoPush);
    setPushOcupado(true);
    try {
      if (pushActivo) {
        await pushService.unsubscribe();
        setPushActivo(false);
        toast.success('Notificaciones desactivadas');
      } else {
        await pushService.init();
        await pushService.subscribe();
        setPushActivo(true);
        toast.success('Listo. Te avisamos de tus operaciones.');
      }
    } catch (e) {
      // El permiso se puede haber denegado recién, en el diálogo del
      // navegador. Se relee el soporte para que el cartel diga la verdad, y
      // se avisa con ESE motivo: «Permission denied» —lo que trae el error—
      // no le dice a nadie dónde se arregla.
      const info = pushService.getSupportInfo();
      setPushSoporte(info);
      toast.error(motivoSinNotificaciones(info)
        || e?.message || 'No se pudo cambiar las notificaciones');
    } finally {
      setPushOcupado(false);
    }
  };

  const probarPush = async () => {
    try {
      await pushService.sendTestNotification();
      toast.success('Notificación de prueba enviada');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo enviar la prueba');
    }
  };

  // Cerrar la ventana borra lo escrito. Dejar la contraseña actual cargada en
  // memoria y a la vista —el interruptor de «mostrar» queda como estaba— es
  // regalarla a quien agarre el teléfono con la sesión abierta.
  const cerrarCambioDeClave = () => {
    setCambiandoClave(false);
    setClaveALaVista(false);
    setClave({ actual: '', nueva: '', repetida: '' });
  };

  const cambiarClave = async (e) => {
    e.preventDefault();
    if (problemaDeLaClave) return toast.error(problemaDeLaClave);
    setGuardando(true);
    try {
      await api.post('/auth/change-password', {
        current_password: clave.actual,
        new_password: clave.nueva,
        confirm_password: clave.repetida,
      });
      // El servidor cierra TODAS las otras sesiones al cambiar la contraseña.
      // Es la mitad del sentido de cambiarla, y hasta ahora no se decía: quien
      // la cambia porque sospecha que le entraron no tenía forma de saber que
      // al otro lo acababan de echar.
      toast.success('Contraseña actualizada. Se cerraron las demás sesiones.');
      cerrarCambioDeClave();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo cambiar la contraseña');
    } finally {
      setGuardando(false);
    }
  };

  const regenerarRespaldos = async (e) => {
    e.preventDefault();
    if (codigo2FA.length !== 6) {
      return toast.error('Ingresá el código de 6 dígitos de tu app de autenticación');
    }
    setOcupado2FA(true);
    try {
      const { data } = await api.post('/auth/2fa/regenerate-backup-codes', { code: codigo2FA });
      setRespaldos(data.backup_codes);
      setCodigo2FA('');
      toast.success('Códigos de respaldo regenerados');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudieron regenerar los códigos');
    } finally {
      setOcupado2FA(false);
    }
  };

  const cerrarSesion = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="env" data-testid="profile-page" style={{
      minHeight: '100vh', background: C.fondo,
      fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif',
    }}>
      <style>{HOJA}</style>

      <div style={{ maxWidth: '640px', margin: '0 auto', padding: '20px 16px 44px' }}>

        {/* ── Encabezado ────────────────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
          <button type="button" onClick={volver} aria-label="Volver" className="env-tap"
            data-testid="back-button"
            style={{
              width: '42px', height: '42px', borderRadius: '11px', flexShrink: 0,
              border: `1px solid ${C.linea}`, background: C.lienzo, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
            <ArrowLeft size={19} color={C.texto} />
          </button>
          <h1 style={{
            fontSize: '21px', fontWeight: 700, color: C.tinta, margin: 0,
            letterSpacing: '-.01em',
          }}>
            Mi perfil
          </h1>
        </div>

        {/* ── Quién sos ─────────────────────────────────────────────── */}
        <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
            {foto ? (
              <img src={foto} alt="" style={{
                width: '62px', height: '62px', borderRadius: '50%', flexShrink: 0,
                objectFit: 'cover', border: `1px solid ${C.linea}`,
              }} />
            ) : (
              <span style={{
                width: '62px', height: '62px', borderRadius: '50%', flexShrink: 0,
                background: C.marcaSuave, color: C.marca, fontSize: '21px', fontWeight: 700,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {iniciales(nombreVisible(user))}
              </span>
            )}
            <div style={{ minWidth: 0 }}>
              <h2 style={{
                margin: 0, fontSize: '17px', fontWeight: 700, color: C.tinta,
                lineHeight: 1.3, wordBreak: 'break-word',
              }}>
                {nombreVisible(user)}
              </h2>
              <p style={{ margin: '4px 0 8px 0', fontSize: '13px', color: C.suave }}>
                {user?.email}
              </p>
              <Insignia tono={estado.tono}>
                <Shield size={12} strokeWidth={2.5} /> {estado.texto}
              </Insignia>
            </div>
          </div>

          <div style={{ display: 'grid', gap: '9px' }}>
            <Dato Icono={Mail} titulo="Correo" valor={user?.email || '—'} />
            {user?.phone ? <Dato Icono={Phone} titulo="Teléfono" valor={user.phone} /> : null}
            {/* El CPF va tapado incluso en tu propia pantalla: es la misma
                pantalla que se abre en un colectivo. */}
            {cpf ? <Dato Icono={IdCard} titulo="CPF" valor={cpf} /> : null}
          </div>
        </section>

        {/* ── Verificar la identidad ────────────────────────────────── */}
        {convieneVerificar(user) ? (
          <div style={{ marginBottom: '16px' }}>
            <Aviso tono={estado.clave === 'pendiente' ? 'info' : 'alerta'}
              titulo={estado.clave === 'pendiente' ? 'Estamos revisando tus documentos'
                : 'Verificá tu identidad'}>
              {estado.clave === 'pendiente'
                ? 'Te avisamos apenas esté resuelto. Mientras tanto podés seguir operando con el cupo sin verificar.'
                : 'Sin verificar tenés un cupo limitado por monto y por cantidad de operaciones.'}
              {estado.clave === 'pendiente' ? null : (
                <div style={{ marginTop: '11px' }}>
                  <Boton tipo="primario" onClick={() => navigate('/verification')}
                    Icono={Shield} testid="verify-identity-btn">
                    Verificar identidad
                  </Boton>
                </div>
              )}
            </Aviso>
          </div>
        ) : null}

        {/* ── Notificaciones ────────────────────────────────────────── */}
        <section style={{ ...tarjeta, padding: '18px 20px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{
              width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
              background: pushActivo ? C.exitoSuave : C.fondo,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {pushActivo ? <Bell size={18} color={C.exito} /> : <BellOff size={18} color={C.suave} />}
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
                Notificaciones
              </span>
              <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
                {avisoPush ? 'No disponibles acá'
                  : pushActivo ? 'Activadas' : 'Te avisamos de tus operaciones'}
              </span>
            </span>
            {pushActivo ? (
              <Boton onClick={probarPush} testid="test-notification-btn">Probar</Boton>
            ) : null}
            <Interruptor encendido={pushActivo} onClick={alternarPush}
              disabled={!puedeUsarPush || pushOcupado} testid="toggle-push-btn" />
          </div>

          {avisoPush ? (
            <div style={{ marginTop: '13px' }}>
              <Aviso tono="alerta" testid="push-no-disponible">{avisoPush}</Aviso>
            </div>
          ) : null}
        </section>

        {/* El PIN no aplica a super_admin y la huella depende del navegador:
            cada componente decide si se dibuja. */}
        <PinSettings user={user} />
        <WebAuthnSettings />

        {/* ── Códigos de respaldo 2FA (sólo super_admin) ────────────── */}
        {esSuperAdmin ? (
          <section style={{ ...tarjeta, padding: '18px 20px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <span style={{
                width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
                background: C.fondo, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Shield size={18} color={C.suave} />
              </span>
              <span style={{ flex: 1, minWidth: '160px' }}>
                <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
                  Códigos de respaldo 2FA
                </span>
                <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
                  Diez códigos de un solo uso
                </span>
              </span>
              <Boton onClick={() => { setVer2FA(true); setRespaldos(null); setCodigo2FA(''); }}
                testid="regenerate-2fa-btn">
                Regenerar
              </Boton>
            </div>
          </section>
        ) : null}

        {/* ── El panel del rol ──────────────────────────────────────── */}
        {panel ? (
          <Link to={panel.destino} data-testid="role-panel-btn" style={{
            ...tarjeta, display: 'flex', alignItems: 'center', gap: '13px',
            padding: '18px 20px', marginBottom: '16px', textDecoration: 'none',
            background: C.tinta, border: `1px solid ${C.tinta}`,
          }}>
            <span style={{
              width: '42px', height: '42px', borderRadius: '12px', flexShrink: 0,
              background: 'rgba(255,255,255,.12)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {esSuperAdmin ? <Gem size={20} color="#fff" />
                : user?.role === 'socio' ? <Gift size={20} color="#fff" />
                  : user?.role === 'socio_gestor' ? <Users size={20} color="#fff" />
                    : <Shield size={20} color="#fff" />}
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{
                display: 'flex', alignItems: 'center', gap: '7px',
                fontSize: '15px', fontWeight: 700, color: '#fff',
              }}>
                {panel.titulo}
                {esSuperAdmin ? <Crown size={15} color="#fff" /> : null}
              </span>
              <span style={{ display: 'block', fontSize: '12.5px', color: 'rgba(255,255,255,.72)', marginTop: '2px' }}>
                {panel.detalle}
              </span>
            </span>
            <ChevronRight size={19} color="rgba(255,255,255,.72)" style={{ flexShrink: 0 }} />
          </Link>
        ) : null}

        {/* ── Cuenta ────────────────────────────────────────────────── */}
        <section style={{ ...tarjeta, overflow: 'hidden' }}>
          <Fila Icono={Lock} texto="Cambiar contraseña"
            detalle="Se cierran las demás sesiones"
            onClick={() => setCambiandoClave(true)} testid="change-password-btn" />
          {cerrandoSesion ? (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
              padding: '14px 16px', background: C.errorSuave,
            }}>
              <span style={{
                width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
                background: C.lienzo, display: 'inline-flex',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <LogOut size={18} color={C.error} />
              </span>
              <span style={{ flex: 1, minWidth: '150px' }}>
                <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.error }}>
                  ¿Cerrás la sesión?
                </span>
                <span style={{ display: 'block', fontSize: '12.5px', color: C.texto, marginTop: '1px' }}>
                  Vas a tener que volver a entrar.
                </span>
              </span>
              <span style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                <Boton onClick={() => setCerrandoSesion(false)} testid="logout-cancel">
                  No
                </Boton>
                <Boton tipo="primario" onClick={cerrarSesion} testid="logout-confirm">
                  Cerrar sesión
                </Boton>
              </span>
            </div>
          ) : (
            <Fila Icono={LogOut} texto="Cerrar sesión" tono="error" ultima flecha={false}
              onClick={() => setCerrandoSesion(true)} testid="logout-btn" />
          )}
        </section>
      </div>

      {/* ── Cambiar contraseña ──────────────────────────────────────── */}
      {cambiandoClave ? (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(16,24,40,.55)', zIndex: 60,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
        }}>
          <div role="dialog" aria-modal="true" aria-labelledby="pf-titulo-clave"
            style={{ ...tarjeta, padding: '22px', width: '100%', maxWidth: '420px' }}>
            <h3 id="pf-titulo-clave"
              style={{ margin: '0 0 4px 0', fontSize: '17px', fontWeight: 700, color: C.tinta }}>
              Cambiar contraseña
            </h3>
            <p style={{ ...ayuda, marginBottom: '16px' }}>
              Al guardar se cierran todas tus otras sesiones. Esta no.
            </p>

            <form onSubmit={cambiarClave}>
              <div style={{ marginBottom: '12px' }}>
                <label style={etiqueta} htmlFor="pf-actual">Contraseña actual</label>
                <input id="pf-actual" className="env-campo" style={campo}
                  type={claveALaVista ? 'text' : 'password'}
                  autoComplete="current-password" value={clave.actual}
                  onChange={(e) => setClave((p) => ({ ...p, actual: e.target.value }))} />
              </div>

              <div style={{ marginBottom: '12px' }}>
                <label style={etiqueta} htmlFor="pf-nueva">Contraseña nueva</label>
                <input id="pf-nueva" className="env-campo" style={campo}
                  type={claveALaVista ? 'text' : 'password'}
                  autoComplete="new-password" value={clave.nueva}
                  onChange={(e) => setClave((p) => ({ ...p, nueva: e.target.value }))} />
                <ReglasDeClave valor={clave.nueva} />
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={etiqueta} htmlFor="pf-repetida">Repetí la nueva</label>
                <input id="pf-repetida" className="env-campo"
                  type={claveALaVista ? 'text' : 'password'}
                  autoComplete="new-password" value={clave.repetida}
                  onChange={(e) => setClave((p) => ({ ...p, repetida: e.target.value }))}
                  style={{
                    ...campo,
                    borderColor: clave.repetida && clave.repetida !== clave.nueva
                      ? C.error : C.lineaFuerte,
                  }} />
                {clave.repetida && clave.repetida !== clave.nueva ? (
                  <p style={{ ...ayuda, color: C.error }}>No coincide con la de arriba.</p>
                ) : null}
              </div>

              <label style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                fontSize: '13px', color: C.texto, marginBottom: '16px', cursor: 'pointer',
              }}>
                <input type="checkbox" checked={claveALaVista}
                  onChange={(e) => setClaveALaVista(e.target.checked)} />
                Mostrar lo que escribo
              </label>

              {/* El botón de guardar está apagado mientras haya un problema.
                  Un botón apagado sin motivo a la vista es una pared: acá se
                  dice cuál es, apenas el usuario empezó a escribir. */}
              {empezoAEscribir && problemaDeLaClave ? (
                <div style={{ marginBottom: '14px' }}>
                  <Aviso tono="error" testid="problema-de-la-clave">
                    {problemaDeLaClave}
                  </Aviso>
                </div>
              ) : null}

              <div style={{ display: 'flex', gap: '10px' }}>
                <Boton onClick={cerrarCambioDeClave}>
                  Cancelar
                </Boton>
                <Boton tipo="primario" ancho enviar
                  disabled={guardando || Boolean(problemaDeLaClave)}
                  Icono={Check} testid="save-password-btn">
                  {guardando ? 'Guardando…' : 'Guardar'}
                </Boton>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {/* ── Regenerar códigos 2FA ───────────────────────────────────── */}
      {ver2FA ? (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(16,24,40,.55)', zIndex: 60,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
        }}>
          <div role="dialog" aria-modal="true" aria-labelledby="pf-titulo-2fa"
            style={{ ...tarjeta, padding: '22px', width: '100%', maxWidth: '420px' }}>
            <h3 id="pf-titulo-2fa"
              style={{ margin: '0 0 14px 0', fontSize: '17px', fontWeight: 700, color: C.tinta }}>
              {respaldos ? 'Tus códigos nuevos' : 'Regenerar códigos de respaldo'}
            </h3>

            {respaldos ? (
              <>
                <Aviso tono="alerta" titulo="Guardalos ahora">
                  No se vuelven a mostrar. Los códigos anteriores ya no sirven.
                </Aviso>
                <div style={{
                  margin: '14px 0', padding: '15px', background: C.fondo,
                  border: `1px solid ${C.linea}`, borderRadius: '12px',
                  display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  fontSize: '14px', color: C.tinta,
                }}>
                  {respaldos.map((c) => <span key={c}>{c}</span>)}
                </div>
                <Boton tipo="primario" ancho
                  onClick={() => { setVer2FA(false); setRespaldos(null); }}>
                  Ya los guardé
                </Boton>
              </>
            ) : (
              <form onSubmit={regenerarRespaldos}>
                <p style={{ ...ayuda, margin: '0 0 14px 0' }}>
                  Escribí el código de seis dígitos de tu app de autenticación. Se
                  generan diez códigos nuevos y los anteriores dejan de servir.
                </p>
                <input className="env-campo" inputMode="numeric" maxLength={6}
                  placeholder="000000" value={codigo2FA}
                  onChange={(e) => setCodigo2FA(e.target.value.replace(/\D/g, ''))}
                  style={{
                    ...campo, textAlign: 'center', fontSize: '24px',
                    fontWeight: 700, letterSpacing: '.3em',
                  }} />
                <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                  <Boton onClick={() => setVer2FA(false)}>Cancelar</Boton>
                  <Boton tipo="primario" ancho enviar disabled={ocupado2FA}>
                    {ocupado2FA ? 'Verificando…' : 'Confirmar'}
                  </Boton>
                </div>
              </form>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
