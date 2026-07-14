import { Link } from 'react-router-dom';
import { Plus, Clock } from 'lucide-react';

/**
 * Tarjetas de saldo de creditos cripto (USDT/USDC), separadas del saldo RIS.
 * Se refrescan "en tiempo real" via polling en Dashboard.jsx (refreshUser cada 15s).
 */
export default function CryptoBalanceCard({ usdt = 0, usdc = 0, isMobile = false }) {
  const fmtCrypto = (n) =>
    Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(2, minmax(0, 240px))',
      gap: '12px',
    }}>
      <CryptoMini label="Créditos USDTRIS" color="#26A17B" amount={fmtCrypto(usdt)} />
      <CryptoMini label="Créditos USDCRIS" color="#2775CA" amount={fmtCrypto(usdc)} />
    </div>
  );
}

function CryptoMini({ label, color, amount }) {
  return (
    <div style={{
      backgroundColor: '#ffffff', borderRadius: '16px', padding: '16px',
      border: '1px solid #eef0f4', boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
      display: 'flex', flexDirection: 'column', gap: '8px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '12px', fontWeight: 600, color: '#6b7280' }}>{label}</span>
        <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: color }} />
      </div>
      <span style={{ fontSize: '22px', fontWeight: 700, color: '#111827', fontVariantNumeric: 'tabular-nums' }}>
        {amount}
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Link
          to="/credits/deposit"
          style={{ fontSize: '12px', fontWeight: 600, color, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          <Plus size={12} strokeWidth={3} /> Recargar
        </Link>
        <Link
          to="/history?filter=cripto"
          style={{ fontSize: '12px', fontWeight: 600, color: '#6b7280', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          <Clock size={12} strokeWidth={3} /> Historial
        </Link>
      </div>
    </div>
  );
}
