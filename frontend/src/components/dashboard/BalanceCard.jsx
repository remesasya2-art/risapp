import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Wallet, Eye, EyeOff, Plus, ArrowUpRight, Clock, Building2, TrendingUp } from 'lucide-react';
import { fmt, fmtRelative } from '../../utils/format';
import useCountUp from '../../hooks/useCountUp';

/**
 * Balance card RIS — misma familia visual (blanco, borde sutil) que
 * CryptoBalanceCard, pero con jerarquía propia de saldo principal:
 * barra de acento en degradado, insignia con ícono, watermark sutil,
 * píldoras de tasa con mini-insignia y botón primario en degradado
 * (el mismo degradado morado que ya se usa en la landing/CTAs del sitio).
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
        position: 'relative',
        backgroundColor: '#ffffff',
        borderRadius: '22px',
        border: '1px solid #eef0f4',
        boxShadow: '0 8px 24px rgba(91,79,233,0.10), 0 1px 3px rgba(0,0,0,0.03)',
        overflow: 'hidden',
      }}
    >
      {/* Barra de acento superior en degradado */}
      <div style={{ height: '4px', background: 'linear-gradient(90deg, #5B4FE9 0%, #8B7FFF 50%, #3B3A9E 100%)' }} />

      {/* Watermark decorativo, muy sutil */}
      <Wallet
        size={isMobile ? 90 : 110}
        style={{
          position: 'absolute',
          top: isMobile ? '4px' : '0px',
          right: isMobile ? '-14px' : '-16px',
          color: 'rgba(91,79,233,0.045)',
          strokeWidth: 1.25,
        }}
      />

      <div style={{ padding: isMobile ? '20px' : '24px', position: 'relative' }}>
        {/* Header: insignia + label + eye toggle */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: 40, height: 40, borderRadius: 12, backgroundColor: 'rgba(91,79,233,0.10)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Wallet size={20} color={accent} strokeWidth={1.8} />
            </div>
            <div>
              <p style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#111827' }}>Saldo RIS</p>
              <p style={{ margin: 0, fontSize: '11px', color: '#9ca3af' }}>Tu billetera principal</p>
            </div>
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
            fontSize: isMobile ? '34px' : '40px',
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
            icon={<Building2 size={13} />}
            value={`1 RIS = ${fmt(risToVes)} Bs`}
            label="Tasa RIS"
          />
          {bcvUsdVes > 0 && (
            <RatePill
              icon={<TrendingUp size={13} />}
              value={hidden ? 'Bs ••••••' : `Bs ${fmt(animated * bcvUsdVes)}`}
              label="Equivalente BCV de tu saldo"
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
              background: 'linear-gradient(135deg, #5B4FE9 0%, #3B3A9E 100%)', color: '#ffffff', textDecoration: 'none',
              transition: 'transform 0.2s, box-shadow 0.2s',
              boxShadow: '0 6px 16px rgba(91,79,233,0.30)',
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
              background: 'transparent', color: accent, textDecoration: 'none',
              border: '1.5px solid rgba(91,79,233,0.25)',
              transition: 'transform 0.2s, background 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(91,79,233,0.06)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            <ArrowUpRight size={18} strokeWidth={2.5} />
            {isMobile ? 'Gastar' : 'Gastar Saldo'}
          </Link>
        </div>
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
        background: 'linear-gradient(135deg, rgba(91,79,233,0.05) 0%, rgba(59,58,158,0.03) 100%)',
        border: '1px solid #eef0f4',
      }}
    >
      {icon && (
        <span style={{
          width: 26, height: 26, borderRadius: 8, backgroundColor: 'rgba(91,79,233,0.10)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#5B4FE9', flexShrink: 0,
        }}>
          {icon}
        </span>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
        <span style={{ fontSize: '13px', fontWeight: 700, color: '#111827', whiteSpace: 'nowrap' }}>{value}</span>
        <span style={{ fontSize: '11px', color: '#9ca3af', marginTop: '2px' }}>{label}</span>
      </div>
    </div>
  );
}
