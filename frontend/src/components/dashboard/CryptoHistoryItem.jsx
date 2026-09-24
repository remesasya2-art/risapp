// Item del historial cripto unificado. Recibe items de dos formas, marcadas por
// `kind`: "deposit" (colección crypto_deposits) y "send" (transactions de tipo
// withdrawal en USDT/USDC). El backend ya los normaliza a una forma común, así
// que acá solo cambia la presentación.

const STATUS_STYLES = {
  finished: { label: 'Acreditado', bg: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #16a34a)' },
  manual: { label: 'Acreditado', bg: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #16a34a)' },
  pending: { label: 'Pendiente', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  waiting: { label: 'Pendiente', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  confirming: { label: 'Confirmando', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  sending: { label: 'Procesando', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  partially_paid: { label: 'Pago parcial', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  failed: { label: 'Fallido', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
  expired: { label: 'Expirado', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
  refunded: { label: 'Reembolsado', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
  error: { label: 'Error', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
};

// Los envíos tienen su propia máquina de estados; `pending` acá no significa
// "esperando el depósito" sino "en cola para pagarse en VES".
const SEND_STATUS_STYLES = {
  pending: { label: 'En proceso', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  awaiting_payment: { label: 'Esperando pago', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  awaiting_topup: { label: 'Falta completar', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  underpaid_review: { label: 'En revisión', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  processing: { label: 'Procesando', bg: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #d97706)' },
  completed: { label: 'Enviado', bg: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #16a34a)' },
  rejected: { label: 'Rechazado', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
  cancelled: { label: 'Cancelado', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
  payment_failed: { label: 'Pago fallido', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
  expired: { label: 'Expirado', bg: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #dc2626)' },
};

// El fondo del ícono va escrito entero (el color con `18` de transparencia)
// y no armado pegándole «18» al final del color en una plantilla: la guarda de la
// paleta prohíbe ese patrón, porque con una variable adentro el valor queda
// inválido y el fondo desaparece sin que nada avise. Son colores de marca,
// de tono medio, y se leen bien en los dos modos.
// Los estados que terminaron bien, en los dos catálogos de arriba.
const TERMINADOS_BIEN = new Set(['finished', 'manual', 'completed']);

const CURRENCY_META = {
  usdt: { label: 'USDT', color: '#26A17B', fondo: '#26A17B18' },
  usdc: { label: 'USDC', color: '#2775CA', fondo: '#2775CA18' },
};

const fmtCrypto = (n) =>
  Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtVes = (n) =>
  Number(n || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function CryptoHistoryItem({ item, formatDate }) {
  const meta = CURRENCY_META[item.currency] || { label: (item.currency || '').toUpperCase(), color: '#6b7280', fondo: '#6b728018' };
  const isSend = item.kind === 'send';

  const styleMap = isSend ? SEND_STATUS_STYLES : STATUS_STYLES;
  const statusInfo = styleMap[item.status] || { label: item.status || 'Desconocido', bg: 'var(--en-oscuro-superficie-2, #f3f4f6)', color: '#6b7280' };

  const shownAmount = isSend
    ? item.amount
    : (item.credited ? (item.credit_amount ?? item.amount) : item.amount);

  // Para un envío el destino es el beneficiario; si el dato no viajó (envíos
  // viejos sin beneficiary_data), se cae al display_id para no dejar la línea vacía.
  const beneficiary = item.beneficiary_data || {};
  const destino = beneficiary.full_name || beneficiary.bank || (item.display_id ? `Envío #${item.display_id}` : 'Envío');

  const subtitle = isSend
    ? `${formatDate(item.completed_at || item.date || item.created_at)}${item.funded_from === 'balance' ? ' · desde saldo' : ''}`
    : `${formatDate(item.credited_at || item.date || item.created_at)}${item.network ? ` · ${item.network}` : ''}`;

  const refunded = item.refunded_to_balance === true && Number(item.refund_amount || 0) > 0;

  return (
    <div
      style={{
        backgroundColor: 'var(--en-oscuro-superficie, #ffffff)', borderRadius: '16px', padding: '16px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
      data-testid={`crypto-history-${isSend ? 'send' : 'deposit'}`}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 12, backgroundColor: meta.fondo,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            fontSize: 12, fontWeight: 800, color: meta.color,
          }}>
            {meta.label.slice(0, 2)}
          </div>
          <div style={{ minWidth: 0 }}>
            <p style={{
              margin: '0 0 2px 0', fontSize: '14px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {isSend ? `Envío ${meta.label} · ${destino}` : `Depósito ${meta.label}`}
            </p>
            <p style={{ margin: 0, fontSize: '12px', color: 'var(--en-oscuro-texto-2, #8E8E9A)' }}>
              {subtitle}
            </p>
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <p style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)' }}>
            {isSend ? '−' : ''}{fmtCrypto(shownAmount)} {meta.label}
          </p>
          {isSend && item.amount_output ? (
            <p style={{ margin: '0 0 4px 0', fontSize: '12px', color: 'var(--en-oscuro-texto-2, #8E8E9A)' }}>
              {fmtVes(item.amount_output)} {item.currency_output || 'VES'}
            </p>
          ) : null}
          {/* Texto con un punto, como las demás filas del historial: lo que
              salió bien en gris, y en color sólo lo que pide atención. Ver
              `EstadoEnTexto` en TransactionItem.jsx. */}
          <span data-testid="estado-en-texto" style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            fontSize: '12px', fontWeight: 600, lineHeight: 1,
            color: TERMINADOS_BIEN.has(item.status) ? 'var(--en-oscuro-texto-2, #8E8E9A)' : statusInfo.color,
          }}>
            <span aria-hidden="true" style={{
              width: '7px', height: '7px', borderRadius: '50%', flexShrink: 0, backgroundColor: statusInfo.color,
            }} />
            {statusInfo.label}
          </span>
        </div>
      </div>

      {refunded && (
        <p
          style={{
            margin: '12px 0 0 0', paddingTop: '10px', borderTop: '1px solid var(--en-oscuro-linea, #F1F2F6)',
            fontSize: '12px', fontWeight: 600, color: 'var(--en-oscuro-exito, #16a34a)',
          }}
          data-testid="crypto-history-refund-note"
        >
          Se devolvieron {fmtCrypto(item.refund_amount)} {meta.label} a tu saldo
        </p>
      )}
    </div>
  );
}
