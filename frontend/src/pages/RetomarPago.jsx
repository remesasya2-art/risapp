/**
 * RetomarPago — volver a la pantalla de pago de un pedido que quedó a medias.
 *
 * POR QUE EXISTE
 *
 *   El cliente cotiza, le aparece el QR (o el formulario de la tarjeta, o los
 *   datos del banco) y cierra la pantalla. Se le corta el teléfono, se le
 *   vence la sesión, lo llaman.
 *
 *   Hasta ahora eso era el final: esa pantalla se dibujaba una sola vez, con
 *   lo que devolvía la cotización, y no había a dónde volver. El pedido
 *   quedaba en el historial y no se podía retomar.
 *
 * TODO LO DECIDE EL SERVIDOR, Y ESTO SOLO LO DIBUJA
 *
 *   Si ya venció, con qué se paga, cuántos segundos quedan, y qué decirle.
 *   Acá no se calcula nada de eso — ver `services/volver_al_pago.py`.
 *
 *   El reloj es el ejemplo claro: se pide en segundos al servidor y se
 *   descuenta localmente. Calcularlo contra la hora del teléfono le mostraría
 *   «expirado» a cualquiera que la tenga corrida.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AlertCircle, ArrowLeft, Clock, CreditCard, Upload } from 'lucide-react';
import api from '../utils/api';
import { useAuth } from '../contexts/AuthContext';
import CardPaymentBrick from '../components/CardPaymentBrick';
import NotificationBell from '../components/NotificationBell';
import { Aviso, Boton } from '../components/flujo';
import { C, HOJA, tarjeta } from '../components/flujo/estilos';
import { fmt } from '../utils/format';

/** mm:ss. Sin ceros a la izquierda en los minutos, como cualquier reloj. */
function reloj(segundos) {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function Hoja({ children, testid }) {
  return (
    <div className="env" data-testid={testid}
      style={{ minHeight: '100vh', background: C.fondo,
        fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' }}>
      <style>{HOJA}</style>
      <div style={{ padding: '20px 16px 48px', maxWidth: '620px', margin: '0 auto' }}>
        {children}
      </div>
    </div>
  );
}

export default function RetomarPago() {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();

  const [pago, setPago] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  const [quedan, setQuedan] = useState(0);
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    const mia = ++peticion.current;
    setCargando(true);
    try {
      const { data } = await api.get(`/envios/${transactionId}/como-pagar`);
      if (mia !== peticion.current) return;
      setPago(data);
      setQuedan(data.segundos_restantes || 0);
      setNoSeLeyo(null);
    } catch (e) {
      if (mia !== peticion.current) return;
      setNoSeLeyo(e.response?.data?.detail || 'No pudimos abrir este pedido.');
    } finally {
      if (mia === peticion.current) setCargando(false);
    }
  }, [transactionId]);

  // EL PRIMER PEDIDO SALE EN UN MICROTASK y no en el cuerpo del efecto: así
  // el `setState` de adentro no ocurre de forma sincrónica durante el montaje.
  // Es el mismo patrón que usa `Send.jsx` para su reloj, y por el mismo
  // motivo.
  useEffect(() => {
    const t = setTimeout(() => { cargar(); }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  // EL RELOJ SE DESCUENTA SOLO, Y AL LLEGAR A CERO SE LE VUELVE A PREGUNTAR
  // AL SERVIDOR.
  //
  //   No se cambia el estado por nuestra cuenta: el servidor es el que sabe
  //   si el cobro sigue vivo. Descontar en pantalla es sólo para que el
  //   número se mueva; quien decide es él.
  useEffect(() => {
    if (!pago?.se_puede_pagar || quedan <= 0) return undefined;
    const t = setTimeout(() => {
      setQuedan((q) => {
        if (q <= 1) { cargar(); return 0; }
        return q - 1;
      });
    }, 1000);
    return () => clearTimeout(t);
  }, [pago, quedan, cargar]);

  if (cargando && !pago) {
    return (
      <Hoja testid="retomar-cargando">
        <p style={{ color: C.suave, textAlign: 'center', padding: '40px 0' }}>
          Abriendo tu pedido…
        </p>
      </Hoja>
    );
  }

  if (noSeLeyo) {
    return (
      <Hoja>
        <div style={{ ...tarjeta, padding: '22px' }} data-testid="retomar-error">
          <Aviso tono="error">{noSeLeyo}</Aviso>
          <div style={{ marginTop: '14px' }}>
            <Boton ancho onClick={() => navigate('/history')}>Ir al historial</Boton>
          </div>
        </div>
      </Hoja>
    );
  }

  const esVenezuela = pago.corredor === 'venezuela';

  return (
    <Hoja testid="retomar-pago">
      <header style={{ display: 'flex', alignItems: 'center', gap: '12px',
        marginBottom: '16px' }}>
        <button type="button" onClick={() => navigate('/history')}
          data-testid="retomar-volver"
          style={{ background: '#fff', border: `1px solid ${C.linea}`,
            borderRadius: '12px', width: '40px', height: '40px', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          <ArrowLeft size={18} color={C.tinta} />
        </button>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: '19px', fontWeight: 700, color: C.tinta, margin: 0 }}>
            Tu pedido {pago.display_id ? `Nº ${pago.display_id}` : ''}
          </h1>
          <p style={{ fontSize: '13px', color: C.suave, margin: '2px 0 0 0' }}>
            {esVenezuela ? 'Envío a Venezuela' : 'Envío a Brasil'}
          </p>
        </div>
        <NotificationBell />
      </header>

      {/* Cuánto es y a quién va. Va SIEMPRE, vencido o no: es lo que le deja
          reconocer de qué pedido se trata. */}
      <section style={{ ...tarjeta, padding: '18px', marginBottom: '14px' }}
        data-testid="retomar-resumen">
        <div style={{ display: 'flex', justifyContent: 'space-between',
          gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <p style={{ fontSize: '11.5px', color: C.suave, margin: 0,
              textTransform: 'uppercase', letterSpacing: '0.04em' }}>Enviás</p>
            <p style={{ fontSize: '19px', fontWeight: 700, color: C.tinta, margin: '2px 0 0 0' }}>
              {fmt(pago.amount_input)} <span style={{ fontSize: '13px', color: C.suave }}>{pago.currency_input}</span>
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontSize: '11.5px', color: C.suave, margin: 0,
              textTransform: 'uppercase', letterSpacing: '0.04em' }}>Recibe</p>
            <p style={{ fontSize: '19px', fontWeight: 700, color: '#059669', margin: '2px 0 0 0' }}>
              {fmt(pago.amount_output)} <span style={{ fontSize: '13px', color: C.suave }}>{pago.currency_output}</span>
            </p>
          </div>
        </div>
        {pago.beneficiary_data?.full_name ? (
          <p style={{ fontSize: '13px', color: C.suave, margin: '12px 0 0 0' }}>
            Para <strong style={{ color: C.tinta }}>{pago.beneficiary_data.full_name}</strong>
          </p>
        ) : null}
      </section>

      {/* ── No se puede pagar: el motivo, y qué hacer ───────────────────── */}
      {!pago.se_puede_pagar ? (
        <section style={{ ...tarjeta, padding: '22px' }} data-testid="retomar-vencido">
          <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start',
            marginBottom: '14px' }}>
            <AlertCircle size={20} color="#DC2626" style={{ flexShrink: 0, marginTop: '1px' }} />
            <p style={{ fontSize: '14px', color: C.tinta, margin: 0, lineHeight: 1.6 }}>
              {pago.motivo}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <Boton ancho onClick={() => navigate('/history')}>Ir al historial</Boton>
            <Boton tipo="primario" ancho testid="retomar-nuevo"
              onClick={() => navigate(esVenezuela ? '/send' : '/send-reais')}>
              Hacer un pedido nuevo
            </Boton>
          </div>
        </section>
      ) : null}

      {/* ── Todavía se puede: el reloj y con qué ────────────────────────── */}
      {pago.se_puede_pagar ? (
        <>
          <section style={{ ...tarjeta, padding: '14px 18px', marginBottom: '14px',
            display: 'flex', alignItems: 'center', gap: '10px' }}
            data-testid="retomar-reloj">
            <Clock size={18} color={quedan < 60 ? '#DC2626' : C.marca} />
            <p style={{ margin: 0, fontSize: '13.5px', color: C.tinta }}>
              Te quedan <strong style={{ fontVariantNumeric: 'tabular-nums',
                color: quedan < 60 ? '#DC2626' : C.tinta }}>{reloj(quedan)}</strong> para
              pagarlo. La tasa de arriba te la respetamos hasta entonces.
            </p>
          </section>

          {esVenezuela && pago.metodo !== 'tarjeta' ? (
            <section style={{ ...tarjeta, padding: '22px' }} data-testid="retomar-pix">
              <h2 style={{ fontSize: '16px', fontWeight: 700, color: C.tinta, margin: '0 0 4px 0' }}>
                Pagá con PIX
              </h2>
              <p style={{ fontSize: '13.5px', color: C.suave, margin: '0 0 18px 0', lineHeight: 1.55 }}>
                Escaneá el código con tu banco, o copiá el texto y pegalo en
                «PIX Copia e Cola». En cuanto se acredite, despachamos.
              </p>
              {pago.qr_code_base64 ? (
                <div style={{ textAlign: 'center', marginBottom: '16px' }}>
                  <img src={`data:image/png;base64,${pago.qr_code_base64}`}
                    alt="Código QR para pagar con PIX" data-testid="retomar-qr"
                    style={{ width: '210px', height: '210px', display: 'block', margin: '0 auto' }} />
                </div>
              ) : null}
              <p style={{ fontSize: '13px', color: C.suave, margin: '0 0 14px 0' }}>
                Pagás <strong style={{ color: C.tinta }}>R$ {fmt(pago.monto_a_pagar)}</strong>
              </p>
              {/* EL «COPIA Y PEGA» NO ES OPCIONAL: en una computadora el QR no
                  se puede escanear, y ahí es donde más gente cierra la
                  pantalla y vuelve después. */}
              <Boton ancho testid="retomar-copiar" onClick={() => {
                navigator.clipboard?.writeText(pago.copy_paste_code || '');
                toast.success('Código copiado');
              }}>
                Copiar el código
              </Boton>
            </section>
          ) : null}

          {esVenezuela && pago.metodo === 'tarjeta' ? (
            <section style={{ ...tarjeta, padding: '22px' }} data-testid="retomar-tarjeta">
              <CardPaymentBrick
                envio={pago}
                userEmail={user?.email}
                userCpf=""
                onSuccess={() => { refreshUser?.(); navigate('/history'); }}
                onBack={() => navigate('/history')}
              />
            </section>
          ) : null}

          {!esVenezuela ? (
            <section style={{ ...tarjeta, padding: '22px' }} data-testid="retomar-bolivares">
              <h2 style={{ fontSize: '16px', fontWeight: 700, color: C.tinta, margin: '0 0 4px 0' }}>
                Transferí en bolívares
              </h2>
              <p style={{ fontSize: '13.5px', color: C.suave, margin: '0 0 16px 0', lineHeight: 1.55 }}>
                Transferí <strong style={{ color: C.tinta }}>{fmt(pago.amount_input)} VES</strong> a
                uno de estos bancos y subí el comprobante antes de que se
                termine el tiempo.
              </p>
              {(pago.bancos || []).length ? (
                <ul style={{ margin: '0 0 16px 0', padding: 0, listStyle: 'none',
                  display: 'grid', gap: '8px' }} data-testid="retomar-bancos">
                  {pago.bancos.map((b) => (
                    <li key={b.id || b.nombre} style={{ padding: '10px 12px',
                      background: C.fondo, borderRadius: '10px', fontSize: '13.5px',
                      color: C.tinta }}>
                      <strong>{b.nombre || b.banco}</strong>
                      {b.numero ? <span style={{ color: C.suave }}> · {b.numero}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              {/* El comprobante se sube en la pantalla del envío, que es donde
                  vive ese formulario. Duplicarlo acá sería tener dos sitios
                  donde arreglar el mismo campo. */}
              <Boton tipo="primario" ancho Icono={Upload} testid="retomar-subir"
                onClick={() => navigate(`/send-reais?retomar=${transactionId}`)}>
                Subir el comprobante
              </Boton>
            </section>
          ) : null}

          <p style={{ fontSize: '12px', color: C.suave, textAlign: 'center',
            margin: '16px 0 0 0', display: 'flex', alignItems: 'center',
            justifyContent: 'center', gap: '6px' }}>
            <CreditCard size={13} />
            Podés cerrar esta pantalla: el pedido te espera en el historial.
          </p>
        </>
      ) : null}
    </Hoja>
  );
}
