import { useState } from 'react';
import { ShieldCheck, Bitcoin } from 'lucide-react';
import ReconciliacionLedger from './ReconciliacionLedger';
import LibroBtc from './LibroBtc';

// Envoltorio del "Libro mayor": dos libros separados por naturaleza de dinero.
// - RIS: reconciliación del saldo de los usuarios.
// - BTC: órdenes directas (no tocan saldo RIS).

export default function LibroMayor() {
  const [sub, setSub] = useState('ris');

  const tabBtn = (key, label, Icon, color) => {
    const active = sub === key;
    return (
      <button
        onClick={() => setSub(key)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px',
          padding: '8px 14px', borderRadius: '10px', fontWeight: 700, fontSize: '14px', cursor: 'pointer',
          border: active ? `1px solid ${color}` : '1px solid #e5e7eb',
          backgroundColor: active ? `${color}14` : '#fff',
          color: active ? color : '#6b7280',
        }}
      >
        <Icon size={15} /> {label}
      </button>
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '18px', flexWrap: 'wrap' }}>
        {tabBtn('ris', 'Saldo RIS', ShieldCheck, '#4F46E5')}
        {tabBtn('btc', 'Órdenes BTC', Bitcoin, '#EA580C')}
      </div>
      {sub === 'ris' ? <ReconciliacionLedger /> : <LibroBtc />}
    </div>
  );
}
