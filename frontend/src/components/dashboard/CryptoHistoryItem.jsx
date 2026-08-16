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

const CURRENCY_META = {
  usdt: { label: 'USDT', color: '#26A17B' },
  usdc: { label: 'USDC', color: '#2775CA' },
};

const fmtCrypto = (n) =>
  Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function CryptoHistoryItem({ item, formatDate }) {
  const meta = CURRENCY_META[item.currency] || { label: (item.currency || '').toUpperCase(), color: '#6b7280' };
  const statusInfo = STATUS_STYLES[item.status] || { label: item.status || 'Desconocido', bg: '#f3f4f6', color: '#6b7280' };
  const shownAmount = item.credited ? (item.credit_amount ?? item.amount) : item.amount;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
      backgroundColor: '#ffffff', borderRadius: '16px', padding: '16px',
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 12, backgroundColor: `${meta.color}18`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          fontSize: 12, fontWeight: 800, color: meta.color,
        }}>
          {meta.label.slice(0, 2)}
        </div>
        <div style={{ minWidth: 0 }}>
          <p style={{ margin: '0 0 2px 0', fontSize: '14px', fontWeight: 700, color: '#111827' }}>
            Depósito {meta.label}
          </p>
          <p style={{ margin: 0, fontSize: '12px', color: '#8E8E9A' }}>
            {formatDate(item.credited_at || item.created_at)}
            {item.network ? ` · ${item.network}` : ''}
          </p>
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <p style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 700, color: '#111827' }}>
          {fmtCrypto(shownAmount)} {meta.label}
        </p>
        <span style={{
          display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
          fontSize: '11px', fontWeight: 700, backgroundColor: statusInfo.bg, color: statusInfo.color,
        }}>
          {statusInfo.label}
        </span>
      </div>
    </div>
  );
}
