import { useEffect, useState } from 'react';
import { CardPayment, initMercadoPago } from '@mercadopago/sdk-react';
import api from '../utils/api';
import { fmt } from '../utils/format';
import { urlDeArchivoSegura } from '../utils/urlDeArchivo';
import toast from 'react-hot-toast';
import {
  CreditCard, Loader2, CheckCircle, XCircle, AlertTriangle, Info, ExternalLink,
} from 'lucide-react';

/** Country list with risk hint for MP Brazil. */
const COUNTRIES = [
  { code: 'BR', name: 'Brasil', flag: '🇧🇷', risk: 'low' },
  { code: 'AR', name: 'Argentina', flag: '🇦🇷', risk: 'high' },
  { code: 'US', name: 'Estados Unidos', flag: '🇺🇸', risk: 'high' },
  { code: 'EU', name: 'Europa', flag: '🇪🇺', risk: 'high' },
  { code: 'VE', name: 'Venezuela', flag: '🇻🇪', risk: 'high' },
  { code: 'OT', name: 'Otro país', flag: '🌎', risk: 'high' },
];

/** Map MP rejection codes → friendly Spanish messages. */
const MP_REJECT_MESSAGES = {
  cc_rejected_high_risk: 'Tu banco rechazó el pago por seguridad. Probá con otra tarjeta o usá PIX (instantáneo).',
  cc_rejected_other_reason: 'El banco emisor rechazó el pago. Llamá a tu banco para autorizarlo o probá con otra tarjeta.',
  cc_rejected_insufficient_amount: 'Saldo insuficiente en la tarjeta.',
  cc_rejected_bad_filled_card_number: 'Número de tarjeta inválido. Revisá los dígitos.',
  cc_rejected_bad_filled_security_code: 'Código de seguridad (CVV) incorrecto.',
  cc_rejected_bad_filled_date: 'Fecha de vencimiento inválida.',
  cc_rejected_bad_filled_other: 'Algún dato de la tarjeta es incorrecto. Revisá todo.',
  cc_rejected_call_for_authorize: 'Tu banco requiere autorización manual. Llamalos o probá con otra tarjeta.',
  cc_rejected_card_disabled: 'La tarjeta está deshabilitada. Llamá a tu banco.',
  cc_rejected_duplicated_payment: 'Ya hay un pago igual en proceso. Esperá unos minutos.',
  cc_rejected_max_attempts: 'Demasiados intentos fallidos. Probá más tarde.',
  cc_rejected_invalid_installments: 'La tarjeta no admite esa cantidad de cuotas.',
  cc_rejected_blacklist: 'Esta tarjeta no puede ser usada. Probá con otra.',
};

function friendlyReject(detail) {
  return MP_REJECT_MESSAGES[detail] || 'El pago no fue aprobado. Probá con otra tarjeta o usá PIX.';
}

/**
 * El formulario de la tarjeta, con el filtro de país y el aviso de
 * internacionales.
 *
 * DOS COSAS DISTINTAS SE PAGAN CON EL MISMO FORMULARIO
 *
 *   · Sin `envio`: carga saldo. Es lo de siempre, y hoy está cerrado —la
 *     empresa no custodia dinero de terceros, ver `services/recarga_abierta.py`.
 *   · Con `envio`: paga UN envío ya cotizado, que no es custodia: la plata
 *     entra y sale en la misma operación.
 *
 *   Lo que cambia es a qué ruta se manda la tarjeta y de dónde sale el monto.
 *   El filtro de país, el aviso de internacionales, los quince mensajes de
 *   rechazo traducidos y el pedido de la clave pública al servidor son los
 *   mismos, y por eso no se duplican en otro componente: son la parte que
 *   costó hacer bien.
 *
 * Props:
 *  - amountRis, userEmail, userCpf, onSuccess, onBack
 *  - envio: { payment_order_id, credit_card, debit_card } — el desglose lo
 *    calculó el SERVIDOR al cotizar. Acá no se saca ninguna cuenta de dinero:
 *    dos implementaciones de la misma fórmula es ver un número y que te
 *    cobren otro.
 */
export default function CardPaymentBrick({ amountRis, userEmail, userCpf, onSuccess, onBack, envio }) {
  const [country, setCountry] = useState(null);     // selected country
  const [confirmedIntl, setConfirmedIntl] = useState(false); // user clicked "intentar igual"
  const [quote, setQuote] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [paymentType, setPaymentType] = useState('credit_card');
  const [sdkListo, setSdkListo] = useState(false);

  const showBrick = country && (country.risk === 'low' || confirmedIntl);

  // LA CLAVE PUBLICA SE LE PIDE AL SERVIDOR, NO VIENE HORNEADA EN EL PAQUETE.
  //
  // Antes el SDK se arrancaba en `main.jsx` con `VITE_MP_PUBLIC_KEY`, que es
  // una variable de COMPILACION. Al cambiar de aplicación en Mercado Pago, el
  // token del servidor se actualizó y esta clave quedó con la de la aplicación
  // vieja: la tarjeta se tokenizaba bajo una y se cobraba con la otra, y
  // Mercado Pago contestaba «Invalid credentials». Al cliente le aparecía
  // «Pago no aprobado», que le echa la culpa a SU tarjeta.
  //
  // Pidiéndosela al servidor no puede desparejarse del token: las dos salen de
  // las variables de entorno del mismo servicio, y cambiarlas no exige
  // recompilar el frontend.
  //
  // Se arranca ACA y no al abrir la aplicación porque es lo único que lo
  // necesita: quien nunca entra a pagar con tarjeta no le pide nada a Mercado
  // Pago, y una llamada menos en el arranque es una pantalla que abre antes.
  useEffect(() => {
    if (!showBrick) return;
    let cancelado = false;
    (async () => {
      try {
        const res = await api.get('/payments/card/config');
        const clave = res.data?.public_key;
        if (!clave) {
          // Sin clave no hay formulario posible. Se dice, en vez de dejar la
          // pantalla girando para siempre.
          if (!cancelado) toast.error('El pago con tarjeta no está disponible ahora. Usá PIX.');
          return;
        }
        initMercadoPago(clave, { locale: 'pt-BR' });
        if (!cancelado) setSdkListo(true);
      } catch {
        if (!cancelado) toast.error('El pago con tarjeta no está disponible ahora. Usá PIX.');
      }
    })();
    return () => { cancelado = true; };
  }, [showBrick]);

  // Pagando un envío no se cotiza: el desglose ya vino del servidor al
  // cotizar el envío, y volver a pedirlo abriría la puerta a que los dos
  // números no coincidan.
  useEffect(() => {
    if (!showBrick || envio) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.post(
          `/payments/card/quote?amount_ris=${amountRis}&payment_type_id=${paymentType}`
        );
        if (!cancelled) setQuote(res.data);
      } catch (e) {
        if (!cancelled) toast.error(e.response?.data?.detail || 'Error calculando comisión');
      }
    })();
    return () => { cancelled = true; };
  }, [amountRis, paymentType, showBrick, envio]);

  // El desglose que manda: el del envío si lo hay, si no el de la recarga.
  const desglose = envio ? envio[paymentType] : null;
  const totalAPagar = envio ? desglose?.total_brl : quote?.total_charged_brl;
  const listoParaCobrar = envio ? Boolean(desglose) : Boolean(quote);

  const handleSubmit = async (cardFormData) => {
    if (!listoParaCobrar) { toast.error('Aguarda el cálculo de comisión'); return; }
    setProcessing(true);
    try {
      const comun = {
        token: cardFormData.token,
        payment_method_id: cardFormData.payment_method_id,
        payment_type_id: cardFormData.payment_type_id || paymentType,
        payer_email: cardFormData.payer?.email || userEmail,
        identification: {
          type: cardFormData.payer?.identification?.type || 'CPF',
          number: cardFormData.payer?.identification?.number || userCpf,
        },
        issuer_id: cardFormData.issuer_id || null,
      };
      // EL MONTO NO VIAJA CUANDO SE PAGA UN ENVIO. El servidor lo saca de la
      // orden: si lo mandara la pantalla, el cliente elegiría cuánto pagar por
      // su propio envío.
      const payload = envio
        ? { ...comun, payment_order_id: envio.payment_order_id }
        : { ...comun, amount_ris: amountRis };
      const res = await api.post(
        envio ? '/payments/card/envio' : '/payments/card/process', payload);
      setResult(res.data);
      if (res.data.status === 'approved') {
        toast.success(envio ? '¡Pago aprobado! Tu envío ya está en camino.'
                            : '¡Pago aprobado! Saldo acreditado.');
        onSuccess && onSuccess(res.data);
      } else {
        toast.error(friendlyReject(res.data.status_detail), { duration: 6000 });
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error procesando el pago');
      setResult({ status: 'error', status_detail: e.response?.data?.detail });
    } finally {
      setProcessing(false);
    }
  };

  // ── Result screens ─────────────────────────────────────────────────────
  if (result && result.status === 'approved') {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <CheckCircle size={56} style={{ color: 'var(--en-oscuro-exito, #16a34a)', margin: '0 auto 16px' }} />
        <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: 0 }}>¡Pago aprobado!</h2>
        {/* Decirle «se acreditaron X a tu saldo» a quien pagó un envío es
            mandarlo a buscar un saldo que nunca existió: la plata entró y
            salió en la misma operación. */}
        <p style={{ color: 'var(--en-oscuro-texto-2, #6b7280)', marginTop: 8 }} data-testid="card-aprobado-texto">
          {envio
            ? <>Cobramos <b>{fmt(totalAPagar)} BRL</b> y tu envío ya está en camino.</>
            : <>Se acreditaron <b>{fmt(amountRis)} RIS</b> a tu saldo.</>}
        </p>
        <p style={{ color: 'var(--en-oscuro-texto-3, #9ca3af)', fontSize: 12, marginTop: 4 }}>ID: {result.payment_id}</p>
      </div>
    );
  }
  if (result && result.status !== 'approved') {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <XCircle size={56} style={{ color: 'var(--en-oscuro-error, #dc2626)', margin: '0 auto 16px' }} />
        <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: 0 }}>Pago no aprobado</h2>
        <p style={{ color: 'var(--en-oscuro-texto-2, #6b7280)', marginTop: 8, lineHeight: 1.5 }}>{friendlyReject(result.status_detail)}</p>
        {country?.risk === 'high' && <InternationalTips />}
        <button
          onClick={() => { setResult(null); setConfirmedIntl(false); }}
          data-testid="card-retry-btn"
          style={{ marginTop: 16, padding: '10px 20px', borderRadius: 10, border: '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)', background: 'var(--en-oscuro-superficie, #fff)', cursor: 'pointer' }}
        >
          Intentar otra vez
        </button>
      </div>
    );
  }

  // ── Step 0: Country selector ───────────────────────────────────────────
  if (!country) {
    return (
      <div data-testid="card-country-selector">
        <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: '0 0 6px' }}>
          ¿Desde qué país estás pagando?
        </h3>
        <p style={{ fontSize: 13, color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '0 0 16px' }}>
          Esto nos ayuda a darte la mejor experiencia y avisarte si tu tarjeta podría tener problemas.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {COUNTRIES.map((c) => (
            <button
              key={c.code}
              onClick={() => setCountry(c)}
              data-testid={`country-${c.code}`}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '14px 16px', borderRadius: 12,
                border: c.risk === 'low' ? '2px solid #16a34a' : '1px solid var(--en-oscuro-linea, #e5e7eb)',
                background: c.risk === 'low' ? 'var(--en-oscuro-exito-suave, #f0fdf4)' : 'var(--en-oscuro-superficie, #fff)',
                cursor: 'pointer', textAlign: 'left',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 15, fontWeight: 600, color: 'var(--en-oscuro-texto, #111827)' }}>
                <span style={{ fontSize: 22 }}>{c.flag}</span> {c.name}
              </span>
              {c.risk === 'low' && (
                <span style={{ fontSize: 11, padding: '2px 8px', background: '#16a34a', color: '#fff', borderRadius: 999, fontWeight: 700 }}>
                  RECOMENDADO
                </span>
              )}
            </button>
          ))}
        </div>
        <button
          onClick={onBack}
          data-testid="card-country-back"
          style={{ marginTop: 16, width: '100%', padding: 12, borderRadius: 10, border: '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)', background: 'var(--en-oscuro-superficie, #fff)', cursor: 'pointer' }}
        >
          Volver
        </button>
      </div>
    );
  }

  // ── Step 0.5: International advisory ──────────────────────────────────
  if (country.risk === 'high' && !confirmedIntl) {
    return (
      <div data-testid="card-intl-advisory">
        <div style={{ background: 'var(--en-oscuro-alerta-suave, #fefce8)', border: '1.5px solid #facc15', borderRadius: 14, padding: 18, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
            <AlertTriangle size={22} style={{ color: 'var(--en-oscuro-alerta, #ca8a04)', flexShrink: 0, marginTop: 2 }} />
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--en-oscuro-alerta, #854d0e)', margin: 0 }}>
                Aviso importante para tarjetas internacionales
              </h3>
              <p style={{ fontSize: 13, color: 'var(--en-oscuro-alerta, #713f12)', marginTop: 6, lineHeight: 1.55 }}>
                Mercado Pago procesa principalmente tarjetas brasileñas. Tu tarjeta de <b>{country.name}</b> puede
                ser rechazada por tu banco emisor o por el sistema anti-fraude de MP. La tasa de aprobación
                internacional suele estar entre <b>10% y 25%</b>.
              </p>
            </div>
          </div>
        </div>

        <InternationalTips />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 16 }}>
          <button
            onClick={() => setConfirmedIntl(true)}
            data-testid="card-intl-continue"
            style={{ padding: '14px', borderRadius: 12, border: 'none', background: 'var(--en-oscuro-acento, #7c3aed)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 15 }}
          >
            Intentar igual con tarjeta
          </button>
          <button
            onClick={() => setCountry(null)}
            data-testid="card-intl-back"
            style={{ padding: 12, borderRadius: 10, border: '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)', background: 'var(--en-oscuro-superficie, #fff)', cursor: 'pointer' }}
          >
            Elegir otro país
          </button>
        </div>
      </div>
    );
  }

  // ── Step 1: Brick ──────────────────────────────────────────────────────
  return (
    <div data-testid="card-payment-brick">
      {country.risk === 'high' && (
        <div style={{ background: 'var(--en-oscuro-alerta-suave, #fffbeb)', border: '1px solid var(--en-oscuro-alerta-borde, #fde68a)', borderRadius: 10, padding: 10, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--en-oscuro-alerta, #854d0e)' }}>
          <Info size={16} />
          Estás pagando con tarjeta de <b>{country.name}</b>. Si falla, usá las opciones del aviso anterior.
        </div>
      )}

      {/* Quote summary */}
      <div style={{ background: 'var(--en-oscuro-superficie-2, #f9fafb)', borderRadius: 12, padding: 16, marginBottom: 16, border: '1px solid var(--en-oscuro-linea, #e5e7eb)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <CreditCard size={20} style={{ color: 'var(--en-oscuro-acento, #6366f1)' }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--en-oscuro-texto, #111827)' }}>Resumen del pago</span>
        </div>
        {/* «Recibirás X RIS» es verdad cargando saldo y mentira pagando un
            envío: ahí no recibe nada, paga lo que ya cotizó. */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 14 }}>
          <span style={{ color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{envio ? 'Tu envío' : 'Recibirás'}</span>
          <span style={{ fontWeight: 600 }}>
            {envio ? `R$ ${fmt(desglose?.envio_brl ?? 0)}` : `${fmt(amountRis)} RIS`}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 14 }}>
          <span style={{ color: 'var(--en-oscuro-texto-2, #6b7280)' }}>Comisión Mercado Pago</span>
          <span style={{ color: 'var(--en-oscuro-error, #dc2626)' }} data-testid="card-comision">
            +R$ {fmt(envio ? (desglose?.comision_brl ?? 0) : (quote?.fee_brl ?? 0))}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid var(--en-oscuro-linea, #e5e7eb)', fontSize: 16 }}>
          <span style={{ fontWeight: 700 }}>Total a cobrar</span>
          <span style={{ fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)' }} data-testid="card-total">
            R$ {fmt(totalAPagar ?? amountRis)}
          </span>
        </div>
        {/* Con PIX no hay comisión. Decirlo acá, con el número al lado, es lo
            que evita el «me cobraron de más» que llega después por soporte. */}
        {envio ? (
          <p style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '10px 0 0 0', lineHeight: 1.5 }}
             data-testid="card-vs-pix">
            Con PIX este envío sale R$ {fmt(desglose?.envio_brl ?? 0)}, sin
            comisión. La tarjeta la cobra Mercado Pago, no nosotros.
          </p>
        ) : null}
      </div>

      {/* Payment type toggle */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setPaymentType('credit_card')}
          data-testid="select-credit-card"
          style={{
            flex: 1, padding: 12, borderRadius: 10,
            border: paymentType === 'credit_card' ? '2px solid var(--en-oscuro-acento, #6366f1)' : '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)',
            background: paymentType === 'credit_card' ? 'var(--en-oscuro-acento-suave, #eef2ff)' : 'var(--en-oscuro-superficie, #fff)',
            fontWeight: 600, cursor: 'pointer', fontSize: 14,
          }}
        >Crédito</button>
        <button
          onClick={() => setPaymentType('debit_card')}
          data-testid="select-debit-card"
          style={{
            flex: 1, padding: 12, borderRadius: 10,
            border: paymentType === 'debit_card' ? '2px solid var(--en-oscuro-acento, #6366f1)' : '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)',
            background: paymentType === 'debit_card' ? 'var(--en-oscuro-acento-suave, #eef2ff)' : 'var(--en-oscuro-superficie, #fff)',
            fontWeight: 600, cursor: 'pointer', fontSize: 14,
          }}
        >Débito</button>
      </div>

      {listoParaCobrar && sdkListo && (
        <CardPayment
          initialization={{
            amount: totalAPagar,
            payer: { email: userEmail },
          }}
          customization={{
            paymentMethods: { maxInstallments: 1, minInstallments: 1 },
            visual: { style: { theme: 'default' } },
          }}
          onSubmit={async (cardFormData) => { await handleSubmit(cardFormData); }}
          onReady={() => {}}
          onError={(err) => {
            console.error('Brick error:', err);
          }}
        />
      )}

      {processing && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10 }}>
          <Loader2 size={32} className="animate-spin" style={{ color: 'var(--en-oscuro-acento, #6366f1)' }} />
        </div>
      )}

      <button
        onClick={() => { setCountry(null); setConfirmedIntl(false); setQuote(null); }}
        data-testid="card-back-btn"
        style={{ marginTop: 16, width: '100%', padding: 12, borderRadius: 10, border: '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)', background: 'var(--en-oscuro-superficie, #fff)', cursor: 'pointer' }}
      >
        Volver
      </button>
    </div>
  );
}

// ── Reusable advisory block ──────────────────────────────────────────────
function InternationalTips() {
  const tips = [
    {
      title: 'Wise',
      desc: 'Enviá BRL desde tu cuenta en USDI/EUR. Llegan como PIX en minutos.',
      url: 'https://wise.com/send-money/send-money-to-brazil',
    },
    {
      title: 'Remitly',
      desc: 'Transferencia internacional rápida a Brasil con buena tasa de cambio.',
      url: 'https://www.remitly.com/us/en/brazil',
    },
    {
      title: 'Revolut',
      desc: 'Si tenés cuenta Revolut, podés mandar BRL directamente vía PIX.',
      url: 'https://www.revolut.com/',
    },
  ];
  return (
    <div data-testid="intl-tips" style={{ background: 'var(--en-oscuro-info-suave, #f0f9ff)', border: '1px solid var(--en-oscuro-info-borde, #bae6fd)', borderRadius: 12, padding: 16, marginTop: 12 }}>
      <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 700, color: 'var(--en-oscuro-info, #075985)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <Info size={16} /> Alternativas para clientes internacionales
      </h4>
      <p style={{ fontSize: 12, color: 'var(--en-oscuro-info, #0369a1)', margin: '0 0 12px', lineHeight: 1.5 }}>
        Si tu tarjeta falla, podés usar estos servicios para enviar PIX desde el exterior. Llega en minutos y
        casi siempre con mejor tasa que pagar con tarjeta extranjera.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {tips.map((t) => (
          <a
            key={t.title}
            href={urlDeArchivoSegura(t.url)}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', borderRadius: 8, background: 'var(--en-oscuro-superficie, #fff)', border: '1px solid var(--en-oscuro-info-borde, #e0f2fe)',
              textDecoration: 'none', color: 'var(--en-oscuro-info, #0c4a6e)',
            }}
          >
            <span>
              <b style={{ display: 'block', fontSize: 13 }}>{t.title}</b>
              <span style={{ fontSize: 11, color: 'var(--en-oscuro-info, #0369a1)' }}>{t.desc}</span>
            </span>
            <ExternalLink size={14} style={{ color: 'var(--en-oscuro-info, #0284c7)' }} />
          </a>
        ))}
      </div>
      <p style={{ fontSize: 11, color: 'var(--en-oscuro-info, #0c4a6e)', marginTop: 10, marginBottom: 0, lineHeight: 1.4 }}>
        💡 También podés pedirle a un familiar/amigo en Brasil que pague por PIX — es instantáneo y sin comisión.
      </p>
    </div>
  );
}
