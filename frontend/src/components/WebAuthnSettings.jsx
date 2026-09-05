/**
 * WebAuthnSettings.jsx — Los dispositivos que entran con huella.
 *
 * LO QUE SE ARREGLA ACA, Y NO ES COSMETICO
 *
 *   1. EL NOMBRE DEL DISPOSITIVO SE PEDIA CON `window.prompt`, Y ADENTRO DEL
 *      MISMO CLICK QUE ABRE EL LECTOR DE HUELLA. El navegador exige que
 *      `navigator.credentials.create()` salga de un gesto del usuario; algunos
 *      cortan esa cadena cuando en el medio hubo un cuadro modal nativo, y
 *      entonces la huella fallaba con un error que no explicaba nada. Ahora el
 *      nombre se escribe en un campo de la tarjeta y el botón llama al lector
 *      directamente.
 *
 *   2. AL BORRAR SE TIRABA EL MOTIVO DEL SERVIDOR. `catch` mostraba siempre
 *      «No se pudo eliminar», tapando el `detail` que decía por qué.
 *
 *   3. NO SE VEIA CUANDO SE AGREGO CADA DISPOSITIVO. El servidor ya devuelve
 *      `created_at` y la lista lo tiraba. Es el dato con el que uno reconoce
 *      —o no reconoce— un dispositivo de la lista: si tenés tres «Mi
 *      dispositivo», la fecha es lo único que los distingue.
 *
 *   4. BORRAR SE CONFIRMABA CON `window.confirm`, Y NO AVISABA CUANDO ERA EL
 *      ULTIMO. El cuadro nativo falla igual de callado que el `window.prompt`
 *      del PIN: si el navegador lo bloquea devuelve `false`, y el botón de la
 *      papelera no hace nada, sin error ni aviso. Ahora la pregunta aparece en
 *      la fila misma, y dice cuándo el dispositivo que estás sacando es el
 *      único que te queda.
 *
 * QUE NO SE TOCO
 *
 *   Las llamadas: `/webauthn/credentials` y su DELETE, y `activarHuella`.
 */
import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Fingerprint, Trash2, Plus } from 'lucide-react';
import api from '../utils/api';
import { activarHuella, webauthnSupported } from '../utils/webauthn';
import { Boton, Aviso } from './flujo';
import { C, tarjeta, etiqueta, campo, ayuda } from './flujo/estilos';

/* A nivel de módulo: un componente declarado durante el render se desmonta y
   se vuelve a montar en cada dibujo, y el campo del nombre perdería el foco a
   la primera tecla. */
function Encabezado() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
      <span style={{
        width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
        background: C.marcaSuave, display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <Fingerprint size={18} color={C.marca} />
      </span>
      <span>
        <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
          Ingreso con huella
        </span>
        <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
          Entrar sin escribir la contraseña
        </span>
      </span>
    </div>
  );
}

/**
 * Los dispositivos registrados, o null si no se pudo leer.
 *
 * Devuelve el dato en vez de escribirlo: la usan el efecto del montaje y el
 * refresco de después de activar o borrar, sin copiar la llamada.
 */
async function traerCredenciales() {
  try {
    const res = await api.get('/webauthn/credentials');
    return res.data?.credentials || [];
  } catch {
    // Sin credenciales o sin respuesta: la tarjeta ofrece activar. Un error
    // acá asustaría sin dar nada que hacer.
    return null;
  }
}

/** «Agregado el 4 de septiembre». Si la fecha no vino o no se entiende, nada. */
function agregadoEl(valor) {
  if (!valor) return null;
  const fecha = new Date(valor);
  if (Number.isNaN(fecha.getTime())) return null;
  return `Agregado el ${fecha.toLocaleDateString('es-AR', { day: 'numeric', month: 'long' })}`;
}

export default function WebAuthnSettings() {
  const [soportado] = useState(webauthnSupported());
  const [creds, setCreds] = useState([]);
  // Ver la nota de PinSettings: «cargando» sólo si va a haber consulta.
  const [cargando, setCargando] = useState(soportado);
  const [ocupado, setOcupado] = useState(false);
  const [nombrando, setNombrando] = useState(false);
  const [nombre, setNombre] = useState('');
  const [porBorrar, setPorBorrar] = useState(null);

  useEffect(() => {
    let vigente = true;
    if (!soportado) return undefined;

    (async () => {
      const leidas = await traerCredenciales();
      if (!vigente) return;
      if (leidas) setCreds(leidas);
      setCargando(false);
    })();

    return () => { vigente = false; };
  }, [soportado]);

  const releer = async () => {
    const leidas = await traerCredenciales();
    if (leidas) setCreds(leidas);
  };

  const activar = async () => {
    try {
      setOcupado(true);
      // El lector se abre en el mismo gesto que este click, sin ningún cuadro
      // nativo en el medio. Ver el punto 1 del encabezado.
      await activarHuella(nombre.trim() || 'Mi dispositivo');
      toast.success('Huella activada en este dispositivo');
      setNombre('');
      setNombrando(false);
      await releer();
    } catch (err) {
      toast.error(err?.response?.data?.detail
        || 'No se pudo activar la huella en este dispositivo');
    } finally {
      setOcupado(false);
    }
  };

  const eliminar = async (cred) => {
    try {
      setOcupado(true);
      await api.delete(`/webauthn/credentials/${encodeURIComponent(cred.credential_id)}`);
      toast.success('Dispositivo eliminado');
      setPorBorrar(null);
      await releer();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo eliminar el dispositivo');
    } finally {
      setOcupado(false);
    }
  };

  const caja = { ...tarjeta, padding: '18px 20px', marginBottom: '16px' };

  if (!soportado) {
    return (
      <section style={caja}>
        <Encabezado />
        <p style={{ ...ayuda, margin: 0 }}>
          Este navegador o este dispositivo no permite entrar con huella.
        </p>
      </section>
    );
  }

  return (
    <section style={caja} data-testid="webauthn-settings">
      <Encabezado />

      {cargando ? (
        <p style={{ ...ayuda, margin: 0 }}>Cargando…</p>
      ) : (
        <>
          {creds.length > 0 ? (
            <div style={{ display: 'grid', gap: '8px', marginBottom: '14px' }}>
              {creds.map((c) => {
                const nombreDe = c.label || 'Dispositivo';
                const fecha = agregadoEl(c.created_at);
                const confirmando = porBorrar === c.credential_id;
                return (
                  <div key={c.credential_id} style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    padding: '11px 13px', borderRadius: '11px',
                    background: confirmando ? C.errorSuave : C.fondo,
                    border: `1px solid ${confirmando ? C.errorBorde : C.linea}`,
                    flexWrap: 'wrap',
                  }}>
                    <Fingerprint size={16} color={C.marca} style={{ flexShrink: 0 }} />
                    <span style={{ flex: 1, minWidth: '140px' }}>
                      <span style={{
                        display: 'block', fontSize: '13.5px', fontWeight: 600, color: C.texto,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {nombreDe}
                      </span>
                      <span style={{
                        display: 'block', fontSize: '11.5px', marginTop: '1px',
                        color: confirmando ? C.error : C.tenue,
                      }}>
                        {confirmando
                          ? (creds.length === 1
                            ? 'Es el único que te queda: vas a entrar sólo con tu contraseña.'
                            : '¿Lo sacamos de la lista?')
                          : fecha}
                      </span>
                    </span>
                    {confirmando ? (
                      <span style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                        <Boton onClick={() => setPorBorrar(null)} testid="webauthn-borrar-no">
                          No
                        </Boton>
                        <Boton tipo="primario" onClick={() => eliminar(c)} disabled={ocupado}
                          testid="webauthn-borrar-si">
                          {ocupado ? 'Sacando…' : 'Sacar'}
                        </Boton>
                      </span>
                    ) : (
                      <button type="button" onClick={() => setPorBorrar(c.credential_id)}
                        disabled={ocupado} aria-label={`Eliminar ${nombreDe}`}
                        style={{
                          border: 'none', background: 'none', padding: '5px', flexShrink: 0,
                          color: C.error, cursor: ocupado ? 'not-allowed' : 'pointer',
                          display: 'inline-flex',
                        }}>
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p style={{ ...ayuda, margin: '0 0 13px 0' }}>
              Activala para entrar más rápido en este dispositivo, sin escribir la
              contraseña cada vez.
            </p>
          )}

          {nombrando ? (
            <div>
              <label style={etiqueta} htmlFor="wa-nombre">¿Cómo se llama este dispositivo?</label>
              <input id="wa-nombre" className="env-campo" style={campo}
                placeholder="Mi teléfono" value={nombre} maxLength={40}
                onChange={(e) => setNombre(e.target.value)} />
              <p style={ayuda}>Sirve para reconocerlo en esta lista y poder sacarlo.</p>
              {creds.length > 0 ? (
                <div style={{ marginTop: '12px' }}>
                  <Aviso tono="info">
                    Se activa en el dispositivo que estás usando ahora, no en los de
                    la lista.
                  </Aviso>
                </div>
              ) : null}
              <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
                <Boton onClick={() => { setNombrando(false); setNombre(''); }}>Cancelar</Boton>
                <Boton tipo="primario" ancho onClick={activar} disabled={ocupado}
                  Icono={Fingerprint} testid="webauthn-activar">
                  {ocupado ? 'Esperando la huella…' : 'Activar acá'}
                </Boton>
              </div>
            </div>
          ) : (
            <Boton tipo="primario" onClick={() => setNombrando(true)} Icono={Plus}
              testid="webauthn-nuevo">
              {creds.length > 0 ? 'Activar en otro dispositivo' : 'Activar en este dispositivo'}
            </Boton>
          )}
        </>
      )}
    </section>
  );
}
