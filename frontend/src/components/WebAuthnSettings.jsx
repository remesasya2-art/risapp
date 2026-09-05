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
 *   4. BORRAR EL ULTIMO NO AVISABA QUE ERA EL ULTIMO. Se pedía la misma
 *      confirmación para el segundo de tres que para el único que quedaba.
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

  useEffect(() => {
    let vigente = true;
    if (!soportado) return undefined;

    (async () => {
      try {
        const res = await api.get('/webauthn/credentials');
        if (vigente) setCreds(res.data?.credentials || []);
      } catch {
        // Sin credenciales o sin respuesta: lista vacía, y la tarjeta ofrece
        // activar. Un error acá asustaría sin dar nada que hacer.
      } finally {
        if (vigente) setCargando(false);
      }
    })();

    return () => { vigente = false; };
  }, [soportado]);

  const releer = async () => {
    try {
      const res = await api.get('/webauthn/credentials');
      setCreds(res.data?.credentials || []);
    } catch { /* ver el efecto */ }
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
    const ultimo = creds.length === 1;
    const pregunta = ultimo
      ? `«${cred.label || 'Dispositivo'}» es el único que te queda. Si lo sacás, vas a entrar sólo con tu contraseña. ¿Lo sacamos?`
      : `¿Sacar «${cred.label || 'Dispositivo'}» de la lista?`;
    if (!window.confirm(pregunta)) return;
    try {
      setOcupado(true);
      await api.delete(`/webauthn/credentials/${encodeURIComponent(cred.credential_id)}`);
      toast.success('Dispositivo eliminado');
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
              {creds.map((c) => (
                <div key={c.credential_id} style={{
                  display: 'flex', alignItems: 'center', gap: '10px',
                  padding: '11px 13px', borderRadius: '11px',
                  background: C.fondo, border: `1px solid ${C.linea}`,
                }}>
                  <Fingerprint size={16} color={C.marca} style={{ flexShrink: 0 }} />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{
                      display: 'block', fontSize: '13.5px', fontWeight: 600, color: C.texto,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {c.label || 'Dispositivo'}
                    </span>
                    {agregadoEl(c.created_at) ? (
                      <span style={{ display: 'block', fontSize: '11.5px', color: C.tenue, marginTop: '1px' }}>
                        {agregadoEl(c.created_at)}
                      </span>
                    ) : null}
                  </span>
                  <button type="button" onClick={() => eliminar(c)} disabled={ocupado}
                    aria-label={`Eliminar ${c.label || 'dispositivo'}`}
                    style={{
                      border: 'none', background: 'none', padding: '5px', flexShrink: 0,
                      color: C.error, cursor: ocupado ? 'not-allowed' : 'pointer',
                      display: 'inline-flex',
                    }}>
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
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
