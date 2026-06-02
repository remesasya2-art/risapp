import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Wallet, Eye, EyeOff, Plus, ArrowUpRight, Clock, Building2 } from 'lucide-react';
import { fmt, fmtRelative } from '../../utils/format';
import useCountUp from '../../hooks/useCountUp';

/**
 * Balance card with gradient background, eye toggle, count-up animation,
 * dual rate pills, and symmetric action buttons.
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

  return (
    <div
      data-testid="balance-card"
      style={{
        position: 'relative',
        background: 'linear-gradient(135deg, #5B4FE9 0%, #3B3A9E 100%)',
        borderRadius: '24px',
        padding: isMobile ? '24px 20px' : '32px',
        color: '#ffffff',
        overflow: 'hidden',
        boxShadow: '0 12px 30px rgba(91, 79, 233, 0.30), 0 4px 10px rgba(59, 58, 158, 0.18)',
      }}
    >
      {/* Decorative wallet icon - top right */}
      <Wallet
        size={isMobile ? 80 : 100}
        style={{
          position: 'absolute',
          top: isMobile ? '-10px' : '-12px',
          right: isMobile ? '-10px' : '-12px',
          color: 'rgba(255,255,255,0.10)',
          strokeWidth: 1.25,
        }}
      />

      {/* Header: label + eye toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', position: 'relative' }}>
        <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.70)', fontWeight: 500, letterSpacing: '0.02em' }}>
          Saldo Total
        </span>
        <button
          onClick={() => setHidden((h) => !h)}
          data-testid="toggle-balance-visibility"
          aria-label={hidden ? 'Mostrar saldo' : 'Ocultar saldo'}
          style={{
            width: '36px', height: '36px', borderRadius: '12px',
            background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.18)',
            cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            color: 'rgba(255,255,255,0.9)', transition: 'background 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.20)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; }}
        >
          {hidden ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>

      {/* Amount */}
      <div
        style={{
          fontSize: isMobile ? '38px' : '46px',
          fontWeight: 700,
          letterSpacing: '-0.02em',
          margin: '0 0 22px 0',
          fontVariantNumeric: 'tabular-nums',
          lineHeight: 1.05,
          color: '#ffffff',
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'rgba(255,255,255,0.60)', marginBottom: '22px' }}>
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
            background: '#ffffff', color: '#5B4FE9', textDecoration: 'none',
            transition: 'transform 0.2s, box-shadow 0.2s',
            boxShadow: '0 4px 10px rgba(0,0,0,0.10)',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 8px 18px rgba(0,0,0,0.18)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = '0 4px 10px rgba(0,0,0,0.10)'; }}
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
            background: 'transparent', color: '#ffffff', textDecoration: 'none',
            border: '1.5px solid rgba(255,255,255,0.55)',
            transition: 'transform 0.2s, background 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
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
        background: 'rgba(255,255,255,0.15)',
        border: '1px solid rgba(255,255,255,0.10)',
        backdropFilter: 'blur(4px)',
      }}
    >
      {icon && <span style={{ color: 'rgba(255,255,255,0.80)' }}>{icon}</span>}
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
        <span style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff', whiteSpace: 'nowrap' }}>{value}</span>
        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.65)', marginTop: '2px' }}>{label}</span>
      </div>
    </div>
  );
}
