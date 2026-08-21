// Item del historial cripto unificado. Recibe items de dos formas, marcadas por
// `kind`: "deposit" (colección crypto_deposits) y "send" (transactions de tipo
// withdrawal en USDT/USDC). El backend ya los normaliza a una forma común, así
// que acá solo cambia la presentación.

const STATUS_STYLES = {
  finished: { label: 'Acreditado', bg: '#dcfce7', color: '#16a34a' },
  manual: { label: 'Acreditado', bg: '#dcfce7', color: '#16a34a' },
  pending: { label: 'Pendiente', bg: '#fef3c7', color: '#d97706' },
  waiting: { label: 'Pendiente', bg: '#fef3c7', color: '#d97706' },
  confirming: { label: 'Confirmando', bg: '#fef3c7', color: '#d97706' },
  sending: { label: 'Procesando', bg: '#fef3c7', color: '#d97706' },
  partially_paid: { label: 'Pago parcial', bg: '#fef3c7', color: '#d97706' },
  failed: { label: 'Fallido', bg: '#fee2e2', color: '#dc2626' },
  expired: { label: 'Expirado', bg: '#fee2e2', color: '#dc2626' },
  refunded: { label: 'Reembolsado', bg: '#fee2e2', color: '#dc2626' },
  error: { label: 'Error', bg: '#fee2e2', color: '#dc2626' },
};

// Los envíos tienen su propia máquina de estados; `pending` acá no significa
// "esperando el depósito" sino "en cola para pagarse en VES".
const SEND_STATUS_STYLES = {
  pending: { label: 'En proceso', bg: '#fef3c7', color: '#d97706' },
  awaiting_payment: { label: 'Esperando pago', bg: '#fef3c7', color: '#d97706' },
  awaiting_topup: { label: 'Falta completar', bg: '#fef3c7', color: '#d97706' },
  underpaid_review: { label: 'En revisión', bg: '#fef3c7', color: '#d97706' },
  processing: { label: 'Procesando', bg: '#fef3c7', color: '#d97706' },
  completed: { label: 'Enviado', bg: '#dcfce7', color: '#16a34a' },
  rejected: { label: 'Rechazado', bg: '#fee2e2', color: '#dc2626' },
  cancelled: { label: 'Cancelado', bg: '#fee2e2', color: '#dc2626' },
  payment_failed: { label: 'Pago fallido', bg: '#fee2e2', color: '#dc2626' },
  expired: { label: 'Expirado', bg: '#fee2e2', color: '#dc2626' },
};

const CURRENCY_META = {
  usdt: { label: 'USDT', color: '#26A17B' },
  usdc: { label: 'USDC', color: '#2775CA' },
};

const fmtCrypto = (n) =>
  Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtVes = (n) =>
  Number(n || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function CryptoHistoryItem({ item, formatDate }) {
  const meta = CURRENCY_META[item.currency] || { label: (item.currency || '').toUpperCase(), color: '#6b7280' };
  const isSend = item.kind === 'send';

  const styleMap = isSend ? SEND_STATUS_STYLES : STATUS_STYLES;
  const statusInfo = styleMap[item.status] || { label: item.status || 'Desconocido', bg: '#f3f4f6', color: '#6b7280' };

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
        backgroundColor: '#ffffff', borderRadius: '16px', padding: '16px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
      data-testid={`crypto-history-${isSend ? 'send' : 'deposit'}`}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 12, backgroundColor: `${meta.color}18`,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            fontSize: 12, fontWeight: 800, color: meta.color,
          }}>
            {meta.label.slice(0, 2)}
          </div>
          <div style={{ minWidth: 0 }}>
            <p style={{
              margin: '0 0 2px 0', fontSize: '14px', fontWeight: 700, color: '#111827',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {isSend ? `Envío ${meta.label} · ${destino}` : `Depósito ${meta.label}`}
            </p>
            <p style={{ margin: 0, fontSize: '12px', color: '#8E8E9A' }}>
              {subtitle}
            </p>
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <p style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: '#111827' }}>
            {isSend ? '−' : ''}{fmtCrypto(shownAmount)} {meta.label}
          </p>
          {isSend && item.amount_output ? (
            <p style={{ margin: '0 0 4px 0', fontSize: '12px', color: '#8E8E9A' }}>
              {fmtVes(item.amount_output)} {item.currency_output || 'VES'}
            </p>
          ) : null}
          <span style={{
            display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
            fontSize: '11px', fontWeight: 700, backgroundColor: statusInfo.bg, color: statusInfo.color,
          }}>
            {statusInfo.label}
          </span>
        </div>
      </div>

      {refunded && (
        <p
          style={{
            margin: '12px 0 0 0', paddingTop: '10px', borderTop: '1px solid #F1F2F6',
            fontSize: '12px', fontWeight: 600, color: '#16a34a',
          }}
          data-testid="crypto-history-refund-note"
        >
          Se devolvieron {fmtCrypto(item.refund_amount)} {meta.label} a tu saldo
        </p>
      )}
    </div>
  );
}
