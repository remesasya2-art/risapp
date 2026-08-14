import React from 'react';
import { Link } from 'react-router-dom';

function CryptoMini({ currency, label, balance, color }) {
  const bal = Number(balance || 0);
  return (
    <div style={{
      flex: 1,
      background: '#fff',
      border: '1px solid #e5e7eb',
      borderRadius: 14,
      padding: '14px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 28, height: 28, borderRadius: '50%',
          background: color, color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, fontWeight: 700,
        }}>{label[0]}</div>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>{label}</span>
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: '#111827' }}>
        {bal.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      <Link
        to={`/send-crypto?currency=${currency}`}
        style={{
          marginTop: 4,
          textAlign: 'center',
          background: color,
          color: '#fff',
          borderRadius: 10,
          padding: '8px 0',
          fontSize: 13,
          fontWeight: 600,
          textDecoration: 'none',
        }}
      >
        Enviar
      </Link>
    </div>
  );
}

export default function CryptoBalanceCard({ balanceUsdt, balanceUsdc }) {
  return (
    <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
      <CryptoMini currency="USDT" label="USDTRIS" balance={balanceUsdt} color="#26a17b" />
      <CryptoMini currency="USDC" label="USDCRIS" balance={balanceUsdc} color="#2775ca" />
    </div>
  );
}
