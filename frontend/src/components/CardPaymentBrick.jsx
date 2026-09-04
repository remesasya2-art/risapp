import { useEffect, useState } from 'react';
import { CardPayment } from '@mercadopago/sdk-react';
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
 * Card Payment Brick wrapper with country gate and international advisory.
 *
 * Props:
 *  - amountRis, userEmail, userCpf, onSuccess, onBack
 */
export default function CardPaymentBrick({ amountRis, userEmail, userCpf, onSuccess, onBack }) {
  const [country, setCountry] = useState(null);     // selected country
  const [confirmedIntl, setConfirmedIntl] = useState(false); // user clicked "intentar igual"
  const [quote, setQuote] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [paymentType, setPaymentType] = useState('credit_card');

  const showBrick = country && (country.risk === 'low' || confirmedIntl);

  // Fetch quote only when we will actually show the Brick
  useEffect(() => {
    if (!showBrick) return;
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
  }, [amountRis, paymentType, showBrick]);

  const handleSubmit = async (cardFormData) => {
    if (!quote) { toast.error('Aguarda el cálculo de comisión'); return; }
    setProcessing(true);
    try {
      const payload = {
        token: cardFormData.token,
        amount_ris: amountRis,
        payment_method_id: cardFormData.payment_method_id,
        payment_type_id: cardFormData.payment_type_id || paymentType,
        payer_email: cardFormData.payer?.email || userEmail,
        identification: {
          type: cardFormData.payer?.identification?.type || 'CPF',
          number: cardFormData.payer?.identification?.number || userCpf,
        },
        issuer_id: cardFormData.issuer_id || null,
      };
      const res = await api.post('/payments/card/process', payload);
      setResult(res.data);
      if (res.data.status === 'approved') {
        toast.success('¡Pago aprobado! Saldo acreditado.');
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
        <CheckCircle size={56} color="#16a34a" style={{ margin: '0 auto 16px' }} />
        <h2 style={{ fontSize: 22, fontWeight: 700, color: '#111827', margin: 0 }}>¡Pago aprobado!</h2>
        <p style={{ color: '#6b7280', marginTop: 8 }}>
          Se acreditaron <b>{fmt(amountRis)} RIS</b> a tu saldo.
        </p>
        <p style={{ color: '#9ca3af', fontSize: 12, marginTop: 4 }}>ID: {result.payment_id}</p>
      </div>
    );
  }
  if (result && result.status !== 'approved') {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <XCircle size={56} color="#dc2626" style={{ margin: '0 auto 16px' }} />
        <h2 style={{ fontSize: 22, fontWeight: 700, color: '#111827', margin: 0 }}>Pago no aprobado</h2>
        <p style={{ color: '#6b7280', marginTop: 8, lineHeight: 1.5 }}>{friendlyReject(result.status_detail)}</p>
        {country?.risk === 'high' && <InternationalTips />}
        <button
          onClick={() => { setResult(null); setConfirmedIntl(false); }}
          data-testid="card-retry-btn"
          style={{ marginTop: 16, padding: '10px 20px', borderRadius: 10, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}
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
        <h3 style={{ fontSize: 18, fontWeight: 700, color: '#111827', margin: '0 0 6px' }}>
          ¿Desde qué país estás pagando?
        </h3>
        <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 16px' }}>
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
                border: c.risk === 'low' ? '2px solid #16a34a' : '1px solid #e5e7eb',
                background: c.risk === 'low' ? '#f0fdf4' : '#fff',
                cursor: 'pointer', textAlign: 'left',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 15, fontWeight: 600, color: '#111827' }}>
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
          style={{ marginTop: 16, width: '100%', padding: 12, borderRadius: 10, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}
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
        <div style={{ background: '#fefce8', border: '1.5px solid #facc15', borderRadius: 14, padding: 18, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
            <AlertTriangle size={22} color="#ca8a04" style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: '#854d0e', margin: 0 }}>
                Aviso importante para tarjetas internacionales
              </h3>
              <p style={{ fontSize: 13, color: '#713f12', marginTop: 6, lineHeight: 1.55 }}>
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
            style={{ padding: '14px', borderRadius: 12, border: 'none', background: '#7c3aed', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 15 }}
          >
            Intentar igual con tarjeta
          </button>
          <button
            onClick={() => setCountry(null)}
            data-testid="card-intl-back"
            style={{ padding: 12, borderRadius: 10, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}
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
        <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10, padding: 10, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#854d0e' }}>
          <Info size={16} />
          Estás pagando con tarjeta de <b>{country.name}</b>. Si falla, usá las opciones del aviso anterior.
        </div>
      )}

      {/* Quote summary */}
      <div style={{ background: '#f9fafb', borderRadius: 12, padding: 16, marginBottom: 16, border: '1px solid #e5e7eb' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <CreditCard size={20} color="#6366f1" />
          <span style={{ fontSize: 14, fontWeight: 600, color: '#111827' }}>Resumen del pago</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 14 }}>
          <span style={{ color: '#6b7280' }}>Recibirás</span>
          <span style={{ fontWeight: 600 }}>{fmt(amountRis)} RIS</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 14 }}>
          <span style={{ color: '#6b7280' }}>Comisión Mercado Pago</span>
          <span style={{ color: '#dc2626' }}>+R$ {fmt(quote?.fee_brl ?? 0)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid #e5e7eb', fontSize: 16 }}>
          <span style={{ fontWeight: 700 }}>Total a cobrar</span>
          <span style={{ fontWeight: 700, color: '#111827' }}>R$ {fmt(quote?.total_charged_brl ?? amountRis)}</span>
        </div>
      </div>

      {/* Payment type toggle */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setPaymentType('credit_card')}
          data-testid="select-credit-card"
          style={{
            flex: 1, padding: 12, borderRadius: 10,
            border: paymentType === 'credit_card' ? '2px solid #6366f1' : '1px solid #d1d5db',
            background: paymentType === 'credit_card' ? '#eef2ff' : '#fff',
            fontWeight: 600, cursor: 'pointer', fontSize: 14,
          }}
        >Crédito</button>
        <button
          onClick={() => setPaymentType('debit_card')}
          data-testid="select-debit-card"
          style={{
            flex: 1, padding: 12, borderRadius: 10,
            border: paymentType === 'debit_card' ? '2px solid #6366f1' : '1px solid #d1d5db',
            background: paymentType === 'debit_card' ? '#eef2ff' : '#fff',
            fontWeight: 600, cursor: 'pointer', fontSize: 14,
          }}
        >Débito</button>
      </div>

      {quote && (
        <CardPayment
          initialization={{
            amount: quote.total_charged_brl,
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
          <Loader2 size={32} className="animate-spin" color="#6366f1" />
        </div>
      )}

      <button
        onClick={() => { setCountry(null); setConfirmedIntl(false); setQuote(null); }}
        data-testid="card-back-btn"
        style={{ marginTop: 16, width: '100%', padding: 12, borderRadius: 10, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}
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
    <div data-testid="intl-tips" style={{ background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 12, padding: 16, marginTop: 12 }}>
      <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 700, color: '#075985', display: 'flex', alignItems: 'center', gap: 6 }}>
        <Info size={16} /> Alternativas para clientes internacionales
      </h4>
      <p style={{ fontSize: 12, color: '#0369a1', margin: '0 0 12px', lineHeight: 1.5 }}>
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
              padding: '10px 12px', borderRadius: 8, background: '#fff', border: '1px solid #e0f2fe',
              textDecoration: 'none', color: '#0c4a6e',
            }}
          >
            <span>
              <b style={{ display: 'block', fontSize: 13 }}>{t.title}</b>
              <span style={{ fontSize: 11, color: '#0369a1' }}>{t.desc}</span>
            </span>
            <ExternalLink size={14} color="#0284c7" />
          </a>
        ))}
      </div>
      <p style={{ fontSize: 11, color: '#0c4a6e', marginTop: 10, marginBottom: 0, lineHeight: 1.4 }}>
        💡 También podés pedirle a un familiar/amigo en Brasil que pague por PIX — es instantáneo y sin comisión.
      </p>
    </div>
  );
}
