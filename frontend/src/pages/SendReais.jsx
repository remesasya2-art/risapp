/**
 * SendReais.jsx — Enviar a Brasil (RIS → reales, por PIX).
 *
 * POR QUE SE REHIZO
 *
 *   Era la última de las tres pantallas de envío con diseño propio: tarjeta de
 *   saldo con degradado violeta, todo en una sola vista sin pasos, la bandera
 *   como emoji en el título, y «R$ 0,00» en ocre antes de que el usuario
 *   escribiera nada. Al lado de enviar a Venezuela y de enviar con Bitcoin
 *   —la misma tarea, el mismo usuario, el mismo dinero— se notaba de otra
 *   época.
 *
 *   Ahora usa `components/flujo`, EL MISMO módulo que las otras dos. No uno
 *   parecido.
 *
 * TRES COSAS QUE NO ERAN FEAS, ESTABAN MAL
 *
 *   1. EL PIN SE PEDIA PARA NADA. La pantalla sólo comprobaba «mayor que cero
 *      y menor que el saldo». El mínimo, el máximo y el cupo de la cuenta sin
 *      verificar los hacía cumplir el servidor —y bien—, pero recién DESPUES
 *      del PIN. O sea: el usuario elegía beneficiario, escribía el monto,
 *      ponía su PIN, y ahí se enteraba de que el monto no iba. Ahora se
 *      comprueba antes, contra `/limits/me`, que es el mismo módulo que el
 *      servidor usa para rechazar.
 *
 *   2. EL CPF NO SE VALIDABA. Al guardar un beneficiario sólo se miraba que el
 *      campo no estuviera vacío. Un CPF mal tipeado es plata que sale hacia
 *      una llave que no existe, y se entera alguien días después. El CPF trae
 *      dos dígitos verificadores: el error se detecta al escribirlo.
 *
 *   3. EL CPF Y LA LLAVE PIX SE MOSTRABAN ENTEROS en la lista. Son datos de un
 *      tercero, en una pantalla que se abre en un teléfono y en un colectivo.
 *      Para reconocer a quién le mandás alcanza con el nombre y las últimas
 *      cifras.
 *
 * QUE NO SE TOCO
 *
 *   La idempotencia, el descuento de saldo, el PIN y las llamadas a la API son
 *   las mismas. El cambio es cuándo se valida y cómo se ve.
 */
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  ArrowLeft, ArrowRight, Plus, X, User, Check, Wallet, ShieldCheck,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import PinConfirm from '../components/PinConfirm';
import { fmt } from '../utils/format';
import { Boton, Aviso, Progreso } from '../components/flujo';
import {
  C, HOJA, tarjeta, etiqueta, microEtiqueta, campo, ayuda, iniciales,
} from '../components/flujo/estilos';
import {
  NOMBRE_DE_LA_LLAVE, PASOS, aNumero, cpfAbreviado, cpfLegible, cpfValido, formatearCpf,
  llaveAbreviada, tipoDeLlave, ultimoPasoAlcanzable, validarMonto,
} from '../utils/envioABrasil';

/* ─── Piezas de esta pantalla ─────────────────────────────────────────────
   A nivel de módulo y no adentro del componente: React trata un componente
   definido durante el render como un tipo nuevo en cada dibujo, lo desmonta y
   lo vuelve a montar, y el campo que estabas escribiendo pierde el foco a la
   primera tecla.                                                            */

function FichaBeneficiario({ b, compacta, soloNombre }) {
  const tipo = tipoDeLlave(b?.pix_key);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
      <span style={{
        width: compacta ? '36px' : '42px', height: compacta ? '36px' : '42px',
        borderRadius: '50%', flexShrink: 0, background: C.marcaSuave,
        color: C.marca, fontSize: compacta ? '13px' : '14.5px', fontWeight: 700,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {iniciales(b?.full_name)}
      </span>
      <span style={{ minWidth: 0 }}>
        <span style={{
          display: 'block', fontSize: '15px', fontWeight: 700, color: C.tinta,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {b?.full_name || '—'}
        </span>
        {/* En la pantalla de confirmar, los datos completos ya están abajo
            en su propia lista. Repetirlos acá abreviados es ruido justo donde
            la persona tiene que leer con atención. */}
        {soloNombre ? null : (
          <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
            CPF {cpfAbreviado(b?.cpf)} · {NOMBRE_DE_LA_LLAVE[tipo]} {llaveAbreviada(b?.pix_key)}
          </span>
        )}
      </span>
    </div>
  );
}

/** Una clave por intento de envío, para que un doble clic no mande dos veces.
 *
 *  Vive acá afuera y no adentro del componente porque `Date.now()` y
 *  `Math.random()` llamados desde el cuerpo de un componente son impuros para
 *  el linter, con razón: si alguna vez se evaluaran durante el render darían
 *  un valor distinto en cada dibujo. Desde una función de módulo llamada por
 *  un manejador, no hay ambigüedad.
 */
function nuevaClaveDeEnvio() {
  return window.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function Marco({ navigate, children }) {
  return (
    <div className="env" style={{
      minHeight: '100vh', background: C.fondo,
      fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif',
    }}>
      <style>{HOJA}</style>
      <header style={{
        background: C.lienzo, borderBottom: `1px solid ${C.linea}`,
        position: 'sticky', top: 0, zIndex: 20,
      }}>
        <div style={{
          maxWidth: '640px', margin: '0 auto', padding: '0 16px', height: '60px',
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <button type="button" onClick={() => navigate(-1)} className="env-tap"
            aria-label="Volver"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px',
              height: '38px', padding: '0 12px', borderRadius: '10px',
              border: `1px solid ${C.linea}`, background: C.lienzo,
              color: C.texto, fontSize: '14px', fontWeight: 600, cursor: 'pointer',
            }}>
            <ArrowLeft size={17} /> Volver
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: '15.5px', fontWeight: 700, color: C.tinta }}>
              Enviar a Brasil
            </p>
            <p style={{ margin: 0, fontSize: '12px', color: C.tenue }}>Por PIX</p>
          </div>
          <NotificationBell />
        </div>
      </header>
      <main style={{ maxWidth: '640px', margin: '0 auto', padding: '20px 16px 44px' }}>
        {children}
      </main>
    </div>
  );
}

/* ─── La pantalla ──────────────────────────────────────────────────────── */

export default function SendReais() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const idemRef = useRef(null);

  const [paso, setPaso] = useState(1);
  const [beneficiarios, setBeneficiarios] = useState([]);
  const [elegido, setElegido] = useState(null);
  const [monto, setMonto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [mostrarPin, setMostrarPin] = useState(false);
  const [mostrarNuevo, setMostrarNuevo] = useState(false);
  const [nuevo, setNuevo] = useState({ full_name: '', cpf: '', pix_key: '' });
  const [limites, setLimites] = useState(null);
  const [cupo, setCupo] = useState(null);
  const [hecho, setHecho] = useState(null);

  const saldo = user?.balance_ris || 0;
  const montoNum = aNumero(monto);
  const problemaDelMonto = validarMonto({ monto: montoNum, saldo, limites, cupo });
  const montoOk = montoNum > 0 && !problemaDelMonto;
  const alcanzable = ultimoPasoAlcanzable({ beneficiario: elegido, montoOk });

  const cargarBeneficiarios = async () => {
    try {
      const res = await api.get('/beneficiaries/br');
      setBeneficiarios(Array.isArray(res.data) ? res.data : []);
    } catch {
      // La lista vacía es un estado legítimo de esta pantalla: quien todavía no
      // cargó a nadie ve el mismo cartel que quien no pudo cargarla. Un aviso
      // de error acá asustaría sin darle nada que hacer.
    }
  };

  // Las dos cargas del arranque viven DENTRO del efecto. Definidas afuera y
  // llamadas acá, el linter ve un setState sincrónico en el cuerpo del efecto
  // —y tiene razón en el caso general—. Adentro queda claro que corren después
  // del montaje y una sola vez.
  useEffect(() => {
    let vigente = true;

    (async () => {
      try {
        const res = await api.get('/beneficiaries/br');
        if (vigente) setBeneficiarios(Array.isArray(res.data) ? res.data : []);
      } catch { /* ver cargarBeneficiarios */ }
    })();

    (async () => {
      try {
        const res = await api.get('/limits/me');
        if (!vigente) return;
        setLimites(res.data);
        setCupo(res.data?.cupo_kyc || null);
      } catch {
        // Sin límites no se inventa ninguno: la pantalla deja pasar y el
        // servidor decide, que es exactamente lo que hacía antes. Lo que se
        // pierde es avisar temprano, no la protección.
      }
    })();

    // Si el usuario se va antes de que contesten, no se escribe estado sobre
    // una pantalla desmontada.
    return () => { vigente = false; };
  }, []);

  const guardarBeneficiario = async () => {
    const nombre = nuevo.full_name.trim();
    const cpf = nuevo.cpf.trim();
    const llave = nuevo.pix_key.trim();

    if (!nombre) return toast.error('Escribí el nombre del beneficiario');
    if (!cpfValido(cpf)) {
      return toast.error(cpf
        ? 'Ese CPF no es válido. Revisá que no falte ni sobre un número.'
        : 'Escribí el CPF del beneficiario');
    }
    if (!llave) return toast.error('Escribí la llave PIX');

    try {
      setEnviando(true);
      const res = await api.post('/beneficiaries/br', {
        full_name: nombre, cpf: cpfLegible(cpf), pix_key: llave,
      });
      toast.success('Beneficiario guardado');
      setMostrarNuevo(false);
      setNuevo({ full_name: '', cpf: '', pix_key: '' });
      await cargarBeneficiarios();
      if (res.data?.beneficiary_id) setElegido(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo guardar el beneficiario');
    } finally {
      setEnviando(false);
    }
  };

  const pedirConfirmacion = () => {
    if (!elegido) return toast.error('Elegí a quién le enviás');
    if (problemaDelMonto) return toast.error(problemaDelMonto);
    setMostrarPin(true);
  };

  const enviar = async () => {
    if (!elegido || problemaDelMonto) return;
    if (!idemRef.current) idemRef.current = nuevaClaveDeEnvio();
    try {
      setEnviando(true);
      await api.post('/reais/send', {
        beneficiary_id: elegido.beneficiary_id,
        amount: montoNum,
        idempotency_key: idemRef.current,
      });
      idemRef.current = null;
      setHecho({ monto: montoNum, nombre: elegido.full_name });
      setPaso(4);
      if (refreshUser) await refreshUser();
      try {
        const h = await api.post('/pin/hint-check');
        if (h.data?.hint) {
          toast(h.data.message || 'Configurá tu PIN para mayor seguridad, en tu perfil.',
            { icon: '🔒' });
        }
      } catch {
        // El recordatorio del PIN es un extra sobre un envío que ya salió
        // bien. Que falle no puede ensuciar la pantalla de confirmación.
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo registrar el envío');
    } finally {
      setEnviando(false);
    }
  };

  const irAPaso = (n) => { if (n <= alcanzable && n < 4) setPaso(n); };

  /* ── Cerrado: el envío salió ──────────────────────────────────────── */
  if (paso === 4 && hecho) {
    return (
      <Marco navigate={navigate}>
        <section style={{ ...tarjeta, padding: '32px 24px', textAlign: 'center' }}>
          <span style={{
            width: '58px', height: '58px', borderRadius: '50%', background: C.exitoSuave,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: '14px',
          }}>
            <Check size={28} color={C.exito} strokeWidth={2.5} />
          </span>
          <h2 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: 700, color: C.tinta }}>
            Envío registrado
          </h2>
          <p style={{ margin: '0 0 22px 0', fontSize: '14.5px', color: C.suave, lineHeight: 1.6 }}>
            <strong style={{ color: C.tinta }}>R$ {fmt(hecho.monto)}</strong> para{' '}
            <strong style={{ color: C.tinta }}>{hecho.nombre}</strong>. El equipo lo paga
            por PIX y te avisamos cuando esté hecho.
          </p>
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
            <Boton onClick={() => navigate('/history')}>Ver mis operaciones</Boton>
            <Boton tipo="primario" onClick={() => {
              setHecho(null); setPaso(1); setElegido(null); setMonto('');
            }}>
              Hacer otro envío
            </Boton>
          </div>
        </section>
      </Marco>
    );
  }

  return (
    <Marco navigate={navigate}>
      <Progreso pasos={PASOS} paso={paso} alcanzable={alcanzable} irA={irAPaso} />

      {/* El saldo viaja arriba en todos los pasos: es la cifra contra la que
          el usuario decide, y esconderla al pasar de paso lo obliga a volver. */}
      <div style={{
        ...tarjeta, background: C.fondo, padding: '13px 16px', marginBottom: '16px',
        display: 'flex', alignItems: 'center', gap: '11px',
      }}>
        <Wallet size={17} color={C.suave} />
        <span style={{ ...microEtiqueta, margin: 0 }}>Saldo disponible</span>
        <span style={{ flex: 1 }} />
        <strong style={{ fontSize: '16px', fontWeight: 700, color: C.tinta }}>
          RI$ {fmt(saldo)}
        </strong>
      </div>

      {/* ── Paso 1: a quién ───────────────────────────────────────────── */}
      {paso === 1 && (
        <>
          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              gap: '12px', marginBottom: '14px',
            }}>
              <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: C.tinta }}>
                ¿A quién le enviás?
              </h2>
              <button type="button" className="env-chip"
                onClick={() => setMostrarNuevo((s) => !s)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '8px 13px', borderRadius: '9px', background: C.lienzo,
                  border: `1px solid ${C.lineaFuerte}`, color: C.texto,
                  fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                }}>
                {mostrarNuevo ? <><X size={14} /> Cancelar</> : <><Plus size={14} /> Nuevo</>}
              </button>
            </div>

            {mostrarNuevo && (
              <div style={{
                background: C.fondo, border: `1px solid ${C.linea}`,
                borderRadius: '14px', padding: '16px', marginBottom: '16px',
              }}>
                <p style={{ ...microEtiqueta, marginBottom: '13px' }}>Nuevo beneficiario</p>

                <div style={{ marginBottom: '12px' }}>
                  <label style={etiqueta} htmlFor="br-nombre">Nombre completo</label>
                  <input id="br-nombre" className="env-campo" style={campo}
                    placeholder="Como figura en su cuenta"
                    value={nuevo.full_name}
                    onChange={(e) => setNuevo((p) => ({ ...p, full_name: e.target.value }))} />
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <label style={etiqueta} htmlFor="br-cpf">CPF</label>
                  <input id="br-cpf" className="env-campo" inputMode="numeric"
                    style={{
                      ...campo,
                      // Se marca en rojo mientras se escribe, no al guardar.
                      // Once dígitos se tipean mal seguido, y enterarse al
                      // apretar el botón obliga a buscar dónde estuvo el error.
                      borderColor: nuevo.cpf && !cpfValido(nuevo.cpf) ? C.error : C.lineaFuerte,
                    }}
                    placeholder="000.000.000-00"
                    value={nuevo.cpf}
                    onChange={(e) => setNuevo((p) => ({ ...p, cpf: formatearCpf(e.target.value) }))} />
                  {nuevo.cpf && !cpfValido(nuevo.cpf) ? (
                    <p style={{ ...ayuda, color: C.error }}>
                      Este CPF no cierra. Revisá que no falte ni sobre un número.
                    </p>
                  ) : (
                    <p style={ayuda}>Se comprueba acá mismo, antes de guardarlo.</p>
                  )}
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label style={etiqueta} htmlFor="br-llave">Llave PIX</label>
                  <input id="br-llave" className="env-campo" style={campo}
                    placeholder="CPF, teléfono, correo o llave aleatoria"
                    value={nuevo.pix_key}
                    onChange={(e) => setNuevo((p) => ({ ...p, pix_key: e.target.value }))} />
                  {nuevo.pix_key ? (
                    <p style={ayuda}>
                      Se enviará a esta {NOMBRE_DE_LA_LLAVE[tipoDeLlave(nuevo.pix_key)].toLowerCase()}.
                    </p>
                  ) : null}
                </div>

                <Boton tipo="primario" ancho onClick={guardarBeneficiario}
                  disabled={enviando} Icono={Check} testid="br-guardar-beneficiario">
                  {enviando ? 'Guardando…' : 'Guardar beneficiario'}
                </Boton>
              </div>
            )}

            {beneficiarios.length === 0 && !mostrarNuevo ? (
              <div style={{ textAlign: 'center', padding: '26px 8px' }}>
                <User size={30} color={C.tenue} />
                <p style={{ margin: '10px 0 0 0', fontSize: '14px', color: C.suave }}>
                  Todavía no tenés beneficiarios en Brasil.
                </p>
                <p style={{ ...ayuda, marginTop: '3px' }}>Agregá uno con el botón «Nuevo».</p>
              </div>
            ) : (
              <div role="radiogroup" style={{ display: 'grid', gap: '9px' }}>
                {beneficiarios.map((b) => {
                  const sel = elegido?.beneficiary_id === b.beneficiary_id;
                  return (
                    <button key={b.beneficiary_id} type="button" role="radio" aria-checked={sel}
                      onClick={() => setElegido(b)} className="env-op env-tap"
                      style={{
                        display: 'flex', alignItems: 'center', gap: '12px', width: '100%',
                        padding: '14px', borderRadius: '14px', textAlign: 'left', cursor: 'pointer',
                        border: `1px solid ${sel ? C.marca : C.linea}`,
                        background: sel ? C.marcaSuave : C.lienzo,
                        boxShadow: sel ? '0 0 0 3px rgba(79,70,229,.10)' : 'none',
                      }}>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <FichaBeneficiario b={b} compacta />
                      </span>
                      <span style={{
                        width: '20px', height: '20px', borderRadius: '50%', flexShrink: 0,
                        border: `2px solid ${sel ? C.marca : C.lineaFuerte}`,
                        background: sel ? C.marca : 'transparent',
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        {sel ? <Check size={12} color="#fff" strokeWidth={3} /> : null}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <Boton tipo="primario" ancho onClick={() => setPaso(2)}
            disabled={!elegido} Icono={ArrowRight} iconoDerecha testid="br-continuar">
            Continuar
          </Boton>
        </>
      )}

      {/* ── Paso 2: cuánto ────────────────────────────────────────────── */}
      {paso === 2 && (
        <>
          <div style={{
            ...tarjeta, background: C.fondo, padding: '14px 16px', marginBottom: '16px',
            display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
          }}>
            <span style={{ flex: 1, minWidth: '200px' }}>
              <FichaBeneficiario b={elegido} compacta />
            </span>
            <button type="button" onClick={() => setPaso(1)} className="env-chip"
              style={{
                padding: '8px 13px', borderRadius: '9px', background: C.lienzo,
                border: `1px solid ${C.lineaFuerte}`, color: C.texto,
                fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              }}>
              Cambiar
            </button>
          </div>

          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <h2 style={{ margin: '0 0 14px 0', fontSize: '17px', fontWeight: 700, color: C.tinta }}>
              ¿Cuánto querés enviar?
            </h2>
            <label style={etiqueta} htmlFor="br-monto">Monto en RIS</label>
            <input id="br-monto" type="number" inputMode="decimal" min="0"
              className="env-campo" placeholder="0" value={monto}
              onChange={(e) => setMonto(e.target.value)} data-testid="br-monto"
              style={{
                ...campo, fontSize: '30px', fontWeight: 700, textAlign: 'center',
                padding: '16px',
                borderColor: monto && problemaDelMonto ? C.error : C.lineaFuerte,
              }} />

            {montoNum > 0 ? (
              <div style={{
                marginTop: '16px', padding: '15px 16px', borderRadius: '12px',
                background: C.fondo, border: `1px solid ${C.linea}`,
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '14px',
              }}>
                <span style={{ fontSize: '13.5px', color: C.suave }}>
                  El beneficiario recibe
                </span>
                <strong style={{ fontSize: '20px', fontWeight: 700, color: C.exito }}>
                  R$ {fmt(montoNum)}
                </strong>
              </div>
            ) : (
              <p style={{ ...ayuda, marginTop: '13px' }}>
                Un RIS equivale a un real. Lo que escribas es lo que recibe.
              </p>
            )}

            {monto && problemaDelMonto ? (
              <div style={{ marginTop: '13px' }}>
                <Aviso tono="error" testid="br-problema">{problemaDelMonto}</Aviso>
              </div>
            ) : null}

            {cupo?.aplica && !problemaDelMonto ? (
              <div style={{ marginTop: '13px' }}>
                <Aviso tono="info">
                  Sin verificar tu identidad te quedan{' '}
                  <strong>RI$ {fmt(cupo.ris_restantes)}</strong> de cupo y{' '}
                  <strong>{cupo.ops_restantes}</strong>{' '}
                  {cupo.ops_restantes === 1 ? 'operación' : 'operaciones'}.
                </Aviso>
              </div>
            ) : null}
          </section>

          <div style={{ display: 'flex', gap: '10px' }}>
            <Boton onClick={() => setPaso(1)} Icono={ArrowLeft}>Atrás</Boton>
            <Boton tipo="primario" ancho onClick={() => setPaso(3)}
              disabled={!montoOk} Icono={ArrowRight} iconoDerecha testid="br-revisar">
              Revisar
            </Boton>
          </div>
        </>
      )}

      {/* ── Paso 3: confirmar ─────────────────────────────────────────── */}
      {paso === 3 && (
        <>
          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <p style={{ ...microEtiqueta, marginBottom: '13px' }}>Vas a enviar</p>
            <p style={{
              margin: '0 0 4px 0', fontSize: '34px', fontWeight: 700,
              color: C.tinta, letterSpacing: '-.02em',
            }}>
              R$ {fmt(montoNum)}
            </p>
            <p style={{ ...ayuda, marginBottom: '18px' }}>
              Se descuentan RI$ {fmt(montoNum)} de tu saldo.
            </p>

            <div style={{
              paddingTop: '16px', borderTop: `1px solid ${C.linea}`,
              display: 'grid', gap: '14px',
            }}>
              <FichaBeneficiario b={elegido} soloNombre />
              <div style={{ display: 'grid', gap: '9px' }}>
                {[
                  ['CPF', cpfLegible(elegido?.cpf)],
                  ['Llave PIX', elegido?.pix_key],
                ].map(([k, v]) => (
                  <div key={k} style={{
                    display: 'flex', justifyContent: 'space-between', gap: '14px',
                  }}>
                    <span style={{ fontSize: '13.5px', color: C.suave }}>{k}</span>
                    <span style={{
                      fontSize: '13.5px', fontWeight: 600, color: C.texto,
                      wordBreak: 'break-all', textAlign: 'right',
                    }}>
                      {v || '—'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Los datos completos aparecen SOLO acá, en el momento de
              confirmar, que es cuando hacen falta para comprobarlos. En la
              lista van abreviados. */}
          <div style={{ marginBottom: '16px' }}>
            <Aviso tono="alerta" titulo="Revisá el CPF y la llave antes de confirmar">
              El pago sale por PIX a esa llave. Si es la de otra persona, el
              dinero llega igual y no se puede deshacer.
            </Aviso>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <Boton onClick={() => setPaso(2)} Icono={ArrowLeft}>Atrás</Boton>
            <Boton tipo="exito" ancho onClick={pedirConfirmacion}
              disabled={enviando || !montoOk} Icono={ShieldCheck} testid="br-enviar">
              {enviando ? 'Enviando…' : 'Confirmar envío'}
            </Boton>
          </div>

          <p style={{ ...ayuda, textAlign: 'center', marginTop: '14px' }}>
            Sin comisión adicional · El pago lo procesa el equipo por PIX
          </p>
        </>
      )}

      <PinConfirm open={mostrarPin} onClose={() => setMostrarPin(false)} onVerified={enviar} />
    </Marco>
  );
}
