/**
 * PinSettings.jsx — El PIN con el que se confirman los envíos.
 *
 * LO QUE SE ARREGLA ACA, Y NO ES COSMETICO
 *
 *   1. LA CONTRASEÑA SE PEDIA CON `window.prompt`. Para desactivar el PIN se
 *      abría el cuadro nativo del navegador y ahí se escribía la contraseña de
 *      la cuenta. Ese cuadro NO enmascara: la contraseña queda a la vista de
 *      cualquiera que esté mirando la pantalla. Encima algunos navegadores lo
 *      bloquean —y en una aplicación instalada como PWA a veces no aparece—,
 *      así que el botón «Desactivar» podía no hacer absolutamente nada, sin
 *      error ni aviso. Ahora es un campo `type="password"` dentro de la misma
 *      tarjeta.
 *
 *   2. EL COMPONENTE DEFINIA `Header` ADENTRO DEL CUERPO. React trata un
 *      componente declarado durante el render como un tipo nuevo en cada
 *      dibujo: lo desmonta y lo vuelve a montar. Acá no rompía nada porque el
 *      encabezado no tiene estado, pero es la misma construcción que hace
 *      perder el foco de un campo a la primera tecla, y estaba a dos líneas de
 *      los campos del formulario.
 *
 *   3. EL PIN NO SE COMPROBABA MIENTRAS SE ESCRIBIA. Cuatro dígitos repetidos
 *      dos veces, y el «no coinciden» aparecía recién al apretar Guardar.
 *
 * QUE NO SE TOCO
 *
 *   Las llamadas: `/pin/status`, `/pin/set`, `/pin/disable`. Mismos campos.
 */
import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Lock, ShieldCheck } from 'lucide-react';
import api from '../utils/api';
import { Boton, Aviso } from './flujo';
import { C, tarjeta, etiqueta, campo, ayuda } from './flujo/estilos';

/* A nivel de módulo, no adentro del componente. Ver el punto 2 de arriba. */
function Encabezado() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
      <span style={{
        width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
        background: C.marcaSuave, display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <Lock size={18} color={C.marca} />
      </span>
      <span>
        <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
          PIN de seguridad
        </span>
        <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
          Para confirmar tus envíos
        </span>
      </span>
    </div>
  );
}

const soloDigitos = (v) => String(v || '').replace(/\D/g, '').slice(0, 4);

export default function PinSettings({ user }) {
  const [estado, setEstado] = useState(null);
  const [formulario, setFormulario] = useState(null); // null | 'definir' | 'desactivar'
  const [password, setPassword] = useState('');
  const [pin, setPin] = useState('');
  const [pin2, setPin2] = useState('');
  const [ocupado, setOcupado] = useState(false);

  // El super_admin está exento de confirmar transacciones con PIN.
  const esSuperAdmin = user?.role === 'super_admin';
  const verificado = user?.verification_status === 'verified';

  // Arranca en «cargando» sólo si de verdad va a haber una consulta. Puesto en
  // `true` y apagado desde el efecto, el primer dibujo dice «Cargando…» para
  // algo que nunca se pidió, y el linter marca —con razón— un setState
  // sincrónico en el cuerpo del efecto.
  const [cargando, setCargando] = useState(!esSuperAdmin && verificado);

  useEffect(() => {
    let vigente = true;
    if (esSuperAdmin || !verificado) return undefined;

    (async () => {
      try {
        const res = await api.get('/pin/status');
        if (vigente) setEstado(res.data);
      } catch {
        // Sin respuesta se asume que no hay PIN: la tarjeta ofrece
        // configurarlo y el servidor decide si ya existía.
      } finally {
        if (vigente) setCargando(false);
      }
    })();

    return () => { vigente = false; };
  }, [esSuperAdmin, verificado]);

  if (esSuperAdmin) return null;

  const releerEstado = async () => {
    try {
      const res = await api.get('/pin/status');
      setEstado(res.data);
    } catch { /* ver el efecto */ }
  };

  const limpiar = () => { setPassword(''); setPin(''); setPin2(''); setFormulario(null); };

  const problemaDelPin = !password ? 'Escribí tu contraseña.'
    : pin.length !== 4 ? 'El PIN son cuatro dígitos.'
      : pin !== pin2 ? 'Los dos PIN no coinciden.'
        : null;

  const guardar = async (e) => {
    e.preventDefault();
    if (problemaDelPin) return toast.error(problemaDelPin);
    try {
      setOcupado(true);
      await api.post('/pin/set', { password, pin });
      toast.success(estado?.has_pin ? 'PIN cambiado' : 'PIN configurado');
      limpiar();
      await releerEstado();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo configurar el PIN');
    } finally {
      setOcupado(false);
    }
  };

  const desactivar = async (e) => {
    e.preventDefault();
    if (!password) return toast.error('Escribí tu contraseña.');
    try {
      setOcupado(true);
      await api.post('/pin/disable', { password });
      toast.success('PIN desactivado');
      limpiar();
      await releerEstado();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo desactivar el PIN');
    } finally {
      setOcupado(false);
    }
  };

  const caja = { ...tarjeta, padding: '18px 20px', marginBottom: '16px' };

  if (cargando) {
    return (
      <section style={caja}>
        <Encabezado />
        <p style={{ ...ayuda, margin: 0 }}>Cargando…</p>
      </section>
    );
  }

  if (!verificado) {
    return (
      <section style={caja}>
        <Encabezado />
        <p style={{ ...ayuda, margin: 0 }}>
          Vas a poder configurar tu PIN cuando se verifique tu identidad.
        </p>
      </section>
    );
  }

  return (
    <section style={caja} data-testid="pin-settings">
      <Encabezado />

      {estado?.must_reset ? (
        <div style={{ marginBottom: '13px' }}>
          <Aviso tono="error">
            Tu PIN se desactivó por seguridad después de varios intentos fallidos.
            Configuralo de nuevo.
          </Aviso>
        </div>
      ) : estado?.locked ? (
        <div style={{ marginBottom: '13px' }}>
          <Aviso tono="alerta">
            Tu PIN está bloqueado un rato por intentos fallidos.
          </Aviso>
        </div>
      ) : null}

      {formulario === 'definir' ? (
        <form onSubmit={guardar}>
          <div style={{ marginBottom: '12px' }}>
            <label style={etiqueta} htmlFor="pin-password">Contraseña de tu cuenta</label>
            <input id="pin-password" className="env-campo" style={campo} type="password"
              autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: '1fr 1fr' }} className="env-dos">
            <div>
              <label style={etiqueta} htmlFor="pin-nuevo">PIN nuevo</label>
              <input id="pin-nuevo" className="env-campo" type="password" inputMode="numeric"
                autoComplete="off" placeholder="••••" value={pin}
                onChange={(e) => setPin(soloDigitos(e.target.value))}
                style={{ ...campo, textAlign: 'center', letterSpacing: '.4em' }} />
            </div>
            <div>
              <label style={etiqueta} htmlFor="pin-repetido">Repetilo</label>
              <input id="pin-repetido" className="env-campo" type="password" inputMode="numeric"
                autoComplete="off" placeholder="••••" value={pin2}
                onChange={(e) => setPin2(soloDigitos(e.target.value))}
                style={{
                  ...campo, textAlign: 'center', letterSpacing: '.4em',
                  borderColor: pin2 && pin2 !== pin ? C.error : C.lineaFuerte,
                }} />
            </div>
          </div>
          {pin2 && pin2 !== pin ? (
            <p style={{ ...ayuda, color: C.error }}>Los dos PIN no coinciden.</p>
          ) : null}
          <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
            <Boton onClick={limpiar}>Cancelar</Boton>
            <Boton tipo="primario" ancho enviar disabled={ocupado || Boolean(problemaDelPin)}
              testid="pin-guardar">
              {ocupado ? 'Guardando…' : 'Guardar PIN'}
            </Boton>
          </div>
        </form>
      ) : formulario === 'desactivar' ? (
        <form onSubmit={desactivar}>
          <div style={{ marginBottom: '13px' }}>
            <Aviso tono="alerta">
              Sin PIN, tus envíos se confirman sin ese segundo paso.
            </Aviso>
          </div>
          <label style={etiqueta} htmlFor="pin-baja">Contraseña de tu cuenta</label>
          <input id="pin-baja" className="env-campo" style={campo} type="password"
            autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
          <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
            <Boton onClick={limpiar}>Cancelar</Boton>
            <Boton tipo="primario" ancho enviar disabled={ocupado || !password}
              testid="pin-desactivar-confirmar">
              {ocupado ? 'Desactivando…' : 'Desactivar el PIN'}
            </Boton>
          </div>
        </form>
      ) : estado?.has_pin && !estado?.must_reset ? (
        <>
          <p style={{
            display: 'flex', alignItems: 'center', gap: '7px', margin: '0 0 14px 0',
            fontSize: '13.5px', fontWeight: 600, color: C.exito,
          }}>
            <ShieldCheck size={17} /> PIN activo
          </p>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <Boton onClick={() => setFormulario('definir')} testid="pin-cambiar">Cambiar PIN</Boton>
            <Boton onClick={() => setFormulario('desactivar')} testid="pin-desactivar">Desactivar</Boton>
          </div>
        </>
      ) : (
        <>
          <p style={{ ...ayuda, margin: '0 0 13px 0' }}>
            Todavía no tenés PIN. Es el segundo paso que se pide al confirmar un envío.
          </p>
          <Boton tipo="primario" onClick={() => setFormulario('definir')} Icono={Lock}
            testid="pin-configurar">
            Configurar PIN
          </Boton>
        </>
      )}
    </section>
  );
}
