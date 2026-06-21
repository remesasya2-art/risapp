import { ArrowUpRight, ArrowDownLeft, Clock, CheckCircle2, XCircle, Eye, Building2 } from 'lucide-react';
import { fmt, formatAccountNumber } from '../../utils/format';

/**
 * Status pill (Pendiente / Aprobado / Rechazado / En revisión)
 */
const STATUS_CONFIG = {
  completed:                { label: 'Aprobado',  bg: '#ECFDF5', fg: '#10B981', Icon: CheckCircle2 },
  approved:                 { label: 'Aprobado',  bg: '#ECFDF5', fg: '#10B981', Icon: CheckCircle2 },
  verified:                 { label: 'Aprobado',  bg: '#ECFDF5', fg: '#10B981', Icon: CheckCircle2 },
  pending:                  { label: 'Pendiente', bg: '#FFF8E1', fg: '#F59E0B', Icon: Clock },
  pending_manual_approval:  { label: 'En revisión', bg: '#FFF8E1', fg: '#F59E0B', Icon: Clock },
  rejected:                 { label: 'Rechazado', bg: '#FEF2F2', fg: '#EF4444', Icon: XCircle },
  failed:                   { label: 'Fallida',   bg: '#FEF2F2', fg: '#EF4444', Icon: XCircle },
  // Estados en español (transacciones BTC y otras que guardan 'estado' en español)
  procesando:               { label: 'Procesando', bg: '#FFF8E1', fg: '#F59E0B', Icon: Clock },
  pendiente:                { label: 'Pendiente',  bg: '#FFF8E1', fg: '#F59E0B', Icon: Clock },
  completado:               { label: 'Enviado',    bg: '#ECFDF5', fg: '#10B981', Icon: CheckCircle2 },
  enviado:                  { label: 'Enviado',    bg: '#ECFDF5', fg: '#10B981', Icon: CheckCircle2 },
  cancelado:                { label: 'Cancelado',  bg: '#FEF2F2', fg: '#EF4444', Icon: XCircle },
  expirado:                 { label: 'Expirado',   bg: '#FEF2F2', fg: '#EF4444', Icon: XCircle },
  fallido:                  { label: 'Fallida',    bg: '#FEF2F2', fg: '#EF4444', Icon: XCircle },
};

export function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const { Icon } = cfg;
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '5px',
        padding: '4px 10px', borderRadius: '20px',
        backgroundColor: cfg.bg, color: cfg.fg,
        fontSize: '12px', fontWeight: 600,
        lineHeight: 1,
      }}
    >
      <Icon size={12} strokeWidth={2.5} />
      {cfg.label}
    </span>
  );
}

function formatShort(dateString) {
  if (!dateString) return '';
  const d = new Date(dateString);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/**
 * Single transaction card.
 *
 * Props:
 *   tx: transaction object
 *   rates: { bcv_usd_ves } (optional, for $ conversion)
 *   onViewVoucher: (tx) => void
 */
export default function TransactionItem({ tx, rates, onViewVoucher }) {
  // Normalizar nombres de campo: unas transacciones usan inglés
  // (type/status/amount_input) y otras español (tipo/estado/amount), p.ej. las de BTC.
  const txType = String(tx.type || tx.tipo || '').toLowerCase();
  const txStatus = tx.status || tx.estado || 'pending';
  const isBtc = txType.includes('btc') || tx.subtipo === 'btc_lightning';
  const isWithdrawal = ['withdrawal', 'send', 'envio', 'envío'].includes(txType) || isBtc;
  const isRecharge = txType.startsWith('recharge') || txType.startsWith('recarga');
  const sign = isWithdrawal ? '-' : '+';
  const amountColor = isWithdrawal ? '#E53E3E' : '#38A169';
  const iconBg = isWithdrawal ? '#FFF0F0' : '#F0FFF4';
  const iconColor = isWithdrawal ? '#E53E3E' : '#38A169';
  const IconArrow = isWithdrawal ? ArrowUpRight : ArrowDownLeft;

  const beneficiary = tx.beneficiary_data || {};
  const account = beneficiary.account_number || beneficiary.phone || '';
// El ojito aparece en CUALQUIER transacción con un comprobante cargado
  // (el admin lo sube en los envíos; el usuario en las recargas), sin importar el tipo ni el estado.
  const showVoucher = (tx.proof_images && tx.proof_images.length > 0) || tx.proof_image || tx.comprobante_pago;

  // Monto principal y unidad según el flujo (busca el primer campo con valor)
  let mainAmount, mainUnit;
  if (isBtc) {
    mainAmount = Math.abs(Number(tx.amount_ves ?? tx.amount_output ?? 0));
    mainUnit = 'VES';
  } else {
    mainAmount = Math.abs(Number(tx.amount_input ?? tx.amount_ris ?? tx.amount ?? tx.amount_output ?? 0));
    mainUnit = 'RIS';
  }

  // Etiqueta: "Recarga" SOLO para entradas (PIX / bolívares); el resto es envío
  const title = isBtc
    ? (beneficiary.full_name ? `Envío BTC · ${beneficiary.full_name}` : 'Envío BTC')
    : isWithdrawal
      ? (beneficiary.full_name || tx.beneficiario || 'Envío')
      : isRecharge
        ? 'Recarga'
        : (sign === '+' ? 'Recarga' : 'Envío');

  return (
    <div
      data-testid={`recent-tx-${tx.transaction_id}`}
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        padding: '16px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        transition: 'background-color 0.2s, transform 0.05s',
        cursor: showVoucher ? 'default' : 'default',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#F8F8FF'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#ffffff'; }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        {/* Category icon */}
        <div style={{
          width: '44px', height: '44px', borderRadius: '50%',
          backgroundColor: iconBg, color: iconColor,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <IconArrow size={20} strokeWidth={2.5} />
        </div>

        {/* Body */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Row 1: Name / Date — Amount / sub-amount */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{
                fontSize: '15px', fontWeight: 700, color: '#1A1A2E',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {title}
              </div>
              <div style={{ fontSize: '12px', color: '#8E8E9A', marginTop: '2px' }}>
                {formatShort(tx.created_at)}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{
                fontSize: '16px', fontWeight: 700, color: amountColor,
                fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
              }}>
                {sign}{fmt(mainAmount)} {mainUnit}
              </div>
              {isWithdrawal && !isBtc && tx.amount_output && (
                <div style={{ fontSize: '11px', color: '#8E8E9A', marginTop: '2px', whiteSpace: 'nowrap' }}>
                  {fmt(tx.amount_output)} VES
                  {rates?.bcv_usd_ves > 0 && (
                    <> = ${fmt(tx.amount_output / rates.bcv_usd_ves, 2)} BCV</>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Beneficiary block for withdrawals */}
          {isWithdrawal && (beneficiary.bank || account) && (
            <div style={{
              marginTop: '10px', padding: '10px 12px',
              backgroundColor: '#FAFAFC', borderRadius: '10px',
              border: '1px solid #EFEFF5',
              display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap',
            }}>
              {beneficiary.bank && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#8E8E9A' }}>
                  <Building2 size={13} />
                  <span style={{ color: '#374151', fontWeight: 500 }}>{beneficiary.bank}</span>
                </span>
              )}
              {account && (
                <span style={{
                  fontSize: '12px', color: '#374151', fontVariantNumeric: 'tabular-nums',
                  letterSpacing: '0.04em', fontWeight: 500,
                }}>
                  {formatAccountNumber(account) || account}
                </span>
              )}
            </div>
          )}

          {/* Bottom row: badge + voucher button */}
          <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <StatusBadge status={txStatus} />
            {showVoucher && (
              <button
                onClick={() => onViewVoucher?.(tx)}
                data-testid={`view-voucher-${tx.transaction_id}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '5px',
                  padding: '4px 10px', borderRadius: '20px',
                  fontSize: '12px', fontWeight: 600, cursor: 'pointer',
                  backgroundColor: '#EEF2FF', color: '#5B4FE9', border: 'none',
                  lineHeight: 1,
                }}
              >
                <Eye size={12} />
                Ver comprobante
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
