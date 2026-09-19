/**
 * DosPasosSettings.jsx — La verificación en dos pasos, para quien la quiera.
 *
 * POR QUE APARECE RECIEN AHORA
 *
 *   Esta pantalla existió antes y se retiró. Encendía la marca en la cuenta,
 *   pero las puertas de entrada NO la miraban cuando el dueño era un cliente:
 *   se la exigían sólo al personal. O sea que quien la usaba quedaba con una
 *   protección que el ingreso ignoraba, y que encima no podía apagar sin un
 *   código del teléfono. Protección que no protege y de la que no se sale.
 *
 *   Vuelve porque ahora el ingreso sí la mira (`personal.pide_dos_pasos` en el
 *   backend) y porque Recursos Humanos puede reiniciársela a quien pierda el
 *   teléfono. La pantalla nunca fue el problema.
 *
 * DOS DECISIONES DE ESTA PANTALLA
 *
 *   LOS CODIGOS DE RESPALDO SE MUESTRAN UNA SOLA VEZ, y por eso no se cierra
 *   sola al activarla: se queda mostrándolos hasta que la persona diga que los
 *   guardó. Cerrar con un `toast` de éxito los perdería, y sin ellos quien
 *   pierde el teléfono queda afuera hasta que un administrador lo destrabe.
 *
 *   NO SE OFRECE A QUIEN YA ESTA OBLIGADO. El personal la tiene puesta desde
 *   el ingreso; dibujarle un botón de «activar» sería ofrecerle algo que ya
 *   hizo. `is_required` viene de la misma regla que aplica el login.
 */
import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { ShieldCheck, Copy } from 'lucide-react';
import api from '../utils/api';
import { Boton, Aviso } from './flujo';
import { C, tarjeta, etiqueta, campo, ayuda } from './flujo/estilos';

function Encabezado({ activo }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
      <span style={{
        width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
        background: C.fondo, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <ShieldCheck size={18} color={activo ? '#16a34a' : C.suave} />
      </span>
      <span style={{ flex: 1, minWidth: '160px' }}>
        <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
          Verificación en dos pasos
        </span>
        <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
          {activo
            ? 'Activa: al entrar te pedimos un código de tu teléfono'
            : 'Un código de tu teléfono, además de la contraseña'}
        </span>
      </span>
    </div>
  );
}

export default function DosPasosSettings() {
  const [estado, setEstado] = useState(null);
  const [paso, setPaso] = useState('mirando');   // mirando | qr | respaldos
  const [alta, setAlta] = useState(null);
  const [codigo, setCodigo] = useState('');
  const [respaldos, setRespaldos] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let vigente = true;
    api.get('/auth/2fa/status')
      .then((r) => { if (vigente) setEstado(r.data || null); })
      .catch(() => { if (vigente) setEstado(null); });
    return () => { vigente = false; };
  }, []);

  // Mientras no se sepa el estado no se dibuja nada: mostrar «desactivada» y
  // corregirlo medio segundo después invita a apretar el botón de más.
  if (!estado) return null;
  // Al personal no se le ofrece: ya la tiene, y obligada.
  if (estado.is_required) return null;

  const empezar = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/auth/2fa/activar-init');
      setAlta(r.data);
      setPaso('qr');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo empezar');
    } finally {
      setOcupado(false);
    }
  };

  const confirmar = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/auth/2fa/activar-confirm', { code: codigo });
      setRespaldos(r.data?.backup_codes || []);
      setPaso('respaldos');
      setEstado({ ...estado, enabled: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Código incorrecto');
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section style={{ ...tarjeta, padding: '18px 20px', marginBottom: '16px' }}
      data-testid="dos-pasos">
      <Encabezado activo={estado.enabled} />

      {estado.enabled && paso !== 'respaldos' ? (
        <Aviso tono="exito" testid="dos-pasos-activa">
          Ya está activa. Para desactivarla vas a necesitar un código de tu
          aplicación de autenticación.
        </Aviso>
      ) : null}

      {!estado.enabled && paso === 'mirando' ? (
        <>
          <p style={{ ...ayuda, marginTop: 0 }}>
            Con esto, saber tu contraseña no alcanza para entrar a tu cuenta:
            también hace falta tu teléfono. Necesitás una aplicación de
            autenticación, como las que ya usás para el banco.
          </p>
          <Boton onClick={empezar} disabled={ocupado} testid="dos-pasos-activar">
            {ocupado ? 'Un momento…' : 'Activar'}
          </Boton>
        </>
      ) : null}

      {paso === 'qr' && alta ? (
        <>
          <p style={{ ...ayuda, marginTop: 0 }}>
            Escaneá este código con tu aplicación de autenticación y después
            escribí el número de seis dígitos que te muestre.
          </p>
          <img src={alta.qr_code_data_url} alt="Código QR"
            data-testid="dos-pasos-qr"
            style={{ width: '180px', height: '180px', display: 'block', margin: '8px 0 12px' }} />

          {/* ¿Y SI ESTA EN EL TELEFONO? El QR se escanea con la cámara de OTRO
              aparato. Quien abre esto desde el celular no puede apuntarse a sí
              mismo, y sin esta parte se queda trabado mirando un código que no
              tiene cómo leer. Van las tres salidas, de la más cómoda a la más
              trabajosa: abrir la app directo, copiar la clave a mano, o la
              captura de pantalla. */}
          <div style={{
            background: C.fondo, borderRadius: '10px', padding: '12px',
            marginBottom: '12px',
          }} data-testid="dos-pasos-desde-el-telefono">
            <span style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: C.tinta, marginBottom: '6px' }}>
              ¿Estás en el teléfono y no podés escanear?
            </span>
            <span style={{ display: 'block', ...ayuda, marginTop: 0, marginBottom: '10px' }}>
              El código QR se lee con la cámara de otro aparato. Si estás en el
              mismo teléfono, hacé cualquiera de estas tres:
            </span>

            <a href={alta.otpauth_url} data-testid="dos-pasos-abrir-app"
              style={{
                display: 'inline-block', fontSize: '13.5px', fontWeight: 600,
                color: C.marca, textDecoration: 'none', marginBottom: '10px',
              }}>
              1 · Abrir mi aplicación de autenticación →
            </a>

            <span style={{ display: 'block', ...ayuda, marginTop: 0, marginBottom: '4px' }}>
              2 · O copiá esta clave y pegala a mano en tu aplicación, con la
              opción «ingresar clave» o «introducir código de configuración»:
            </span>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '10px' }}>
              <code data-testid="dos-pasos-clave" style={{
                fontSize: '13px', wordBreak: 'break-all', background: '#fff',
                border: `1px solid ${C.linea}`, borderRadius: '8px', padding: '6px 8px',
              }}>{alta.secret}</code>
              <Boton tono="suave" onClick={() => {
                navigator.clipboard?.writeText(alta.secret);
                toast.success('Clave copiada');
              }} testid="dos-pasos-copiar-clave">
                <Copy size={14} /> Copiar
              </Boton>
            </div>

            <span style={{ display: 'block', ...ayuda, marginTop: 0 }}>
              3 · O sacá una captura de esta pantalla y, en tu aplicación de
              autenticación, elegí agregar una cuenta desde una imagen de la
              galería.
            </span>
          </div>
          <label style={etiqueta} htmlFor="dos-pasos-codigo">Código de seis dígitos</label>
          <input id="dos-pasos-codigo" style={campo} inputMode="numeric" maxLength={6}
            value={codigo} data-testid="dos-pasos-codigo"
            onChange={(e) => setCodigo(e.target.value.replace(/\D/g, '').slice(0, 6))} />
          <div style={{ marginTop: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <Boton onClick={confirmar} disabled={ocupado || codigo.length !== 6}
              testid="dos-pasos-confirmar">
              {ocupado ? 'Comprobando…' : 'Confirmar'}
            </Boton>
            <Boton tono="suave" onClick={() => { setPaso('mirando'); setCodigo(''); }}>
              Cancelar
            </Boton>
          </div>
        </>
      ) : null}

      {paso === 'respaldos' && respaldos ? (
        <>
          <Aviso tono="alerta" testid="dos-pasos-guarda-los-codigos">
            Guardá estos códigos ahora. Son la única forma de entrar si perdés
            el teléfono, y no se muestran de nuevo.
          </Aviso>
          <div data-testid="dos-pasos-respaldos" style={{
            fontFamily: 'monospace', fontSize: '14px', background: C.fondo,
            borderRadius: '10px', padding: '12px', margin: '12px 0',
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '6px',
          }}>
            {respaldos.map((c) => <span key={c}>{c}</span>)}
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <Boton tono="suave" onClick={() => {
              navigator.clipboard?.writeText(respaldos.join('\n'));
              toast.success('Copiados');
            }}>
              <Copy size={14} /> Copiar
            </Boton>
            <Boton onClick={() => setPaso('mirando')} testid="dos-pasos-ya-los-guarde">
              Ya los guardé
            </Boton>
          </div>
        </>
      ) : null}
    </section>
  );
}
