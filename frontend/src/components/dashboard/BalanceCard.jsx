import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Eye, EyeOff, Plus, ArrowUpRight, Clock, Building2 } from 'lucide-react';
import { fmt, fmtRelative } from '../../utils/format';
import useCountUp from '../../hooks/useCountUp';

/**
 * Balance card RIS — mismo lenguaje visual (blanco, borde sutil, sombra suave,
 * punto de color indicador) que CryptoBalanceCard, para armonía visual entre
 * las 3 billeteras (RIS, USDTRIS, USDCRIS) del Dashboard.
 *
 * Props:
 *   balance: number
 *   risToVes: number (1 RIS = X Bs)
 *   bcvUsdVes: number (1 USD = X Bs)
 *   updatedAt: Date | string  (when rates were last updated)
 *   isMobile: boolean
 */
export default function BalanceCard({
  balance = 0,
  risToVes = 0,
  bcvUsdVes = 0,
  updatedAt = null,
  isMobile = false,
}) {
  const [hidden, setHidden] = useState(false);
  const animated = useCountUp(balance, 900);
  const accent = '#5B4FE9';

  return (
    <div
      data-testid="balance-card"
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '20px',
        border: '1px solid #eef0f4',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        padding: isMobile ? '20px' : '24px',
      }}
    >
      {/* Header: label con punto de color + eye toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: accent }} />
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#6b7280' }}>Saldo RIS</span>
        </div>
        <button
          onClick={() => setHidden((h) => !h)}
          data-testid="toggle-balance-visibility"
          aria-label={hidden ? 'Mostrar saldo' : 'Ocultar saldo'}
          style={{
            width: '32px', height: '32px', borderRadius: '10px',
            background: '#f3f4f6', border: 'none',
            cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            color: '#6b7280', transition: 'background 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = '#e5e7eb'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = '#f3f4f6'; }}
        >
          {hidden ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>

      {/* Amount */}
      <div
        style={{
          fontSize: isMobile ? '32px' : '38px',
          fontWeight: 700,
          letterSpacing: '-0.02em',
          margin: '0 0 18px 0',
          fontVariantNumeric: 'tabular-nums',
          lineHeight: 1.05,
          color: '#111827',
        }}
      >
        {hidden ? (
          <span style={{ letterSpacing: '0.15em' }}>RI$ ••••••</span>
        ) : (
          <span>RI$ {fmt(animated)}</span>
        )}
      </div>

      {/* Rate pills */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr 1fr' : 'auto auto',
          gap: '10px',
          marginBottom: '14px',
        }}
      >
        <RatePill
          icon={<Building2 size={14} />}
          value={`1 RIS = ${fmt(risToVes)} Bs`}
          label="Tasa RIS"
        />
        {bcvUsdVes > 0 && (
          <RatePill
            value={`1 USD = Bs. ${fmt(bcvUsdVes)}`}
            label="Tasa BCV"
          />
        )}
      </div>

      {/* Updated time */}
      {updatedAt && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#9ca3af', marginBottom: '20px' }}>
          <Clock size={13} />
          <span>Actualizado: {fmtRelative(updatedAt)}</span>
        </div>
      )}

      {/* Buttons */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '12px',
        }}
      >
        <Link
          to="/recharge"
          data-testid="recharge-button"
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
            padding: '14px 16px', borderRadius: '12px', fontWeight: 700, fontSize: '15px',
            background: accent, color: '#ffffff', textDecoration: 'none',
            transition: 'transform 0.2s, box-shadow 0.2s',
            boxShadow: '0 4px 10px rgba(91,79,233,0.25)',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-1px)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0)'; }}
        >
          <Plus size={18} strokeWidth={2.5} />
          {isMobile ? 'Recargar' : 'Recargar Saldo'}
        </Link>
        <Link
          to="/send"
          data-testid="send-button"
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
            padding: '14px 16px', borderRadius: '12px', fontWeight: 700, fontSize: '15px',
            background: 'transparent', color: '#374151', textDecoration: 'none',
            border: '1.5px solid #e5e7eb',
            transition: 'transform 0.2s, background 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = '#f9fafb'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.transform = 'translateY(0)'; }}
        >
          <ArrowUpRight size={18} strokeWidth={2.5} />
          {isMobile ? 'Enviar' : 'Enviar Dinero'}
        </Link>
      </div>
    </div>
  );
}

function RatePill({ icon, value, label }) {
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: '10px',
        padding: '10px 14px',
        borderRadius: '12px',
        background: '#f9fafb',
        border: '1px solid #eef0f4',
      }}
    >
      {icon && <span style={{ color: '#9ca3af' }}>{icon}</span>}
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
        <span style={{ fontSize: '13px', fontWeight: 700, color: '#111827', whiteSpace: 'nowrap' }}>{value}</span>
        <span style={{ fontSize: '11px', color: '#9ca3af', marginTop: '2px' }}>{label}</span>
      </div>
    </div>
  );
}
