import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, Loader2, Bitcoin } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

// Monedas de credito disponibles (de cara al usuario: "Creditos")
const CREDIT_OPTIONS = [
  { key: 'usdt', label: 'Creditos USDT', desc: 'Deposita con USDT (red TRON / TRC20)', color: '#26A17B' },
  { key: 'usdc', label: 'Creditos USDC', desc: 'Deposita con USDC (red Ethereum / ERC20)', color: '#2775CA' },
];

export default function CreditsDeposit() {
  const navigate = useNavigate();
  const [currency, setCurrency] = useState('usdt');
  const [amount, setAmount] = useState('');
  const [declared, setDeclared] = useState(false);
  const [loading, setLoading] = useState(false);

  const selected = CREDIT_OPTIONS.find((o) => o.key === currency);
  const amountNum = parseFloat(amount);
  const canContinue = amountNum > 0 && declared && !loading;

  const handleDeposit = async () => {
    if (!canContinue) return;
    setLoading(true);
    try {
      const { data } = await api.post('/credits/deposit', {
        currency,
        amount: amountNum,
        declared_not_restricted: declared,
      });
      if (data?.invoice_url) {
        // Redirigir a la pagina de pago hosteada de NOWPayments
        window.location.href = data.invoice_url;
      } else {
        toast.error('No se pudo iniciar el pago. Intenta de nuevo.');
        setLoading(false);
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || 'No se pudo iniciar el pago. Intenta de nuevo.';
      toast.error(msg);
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ backgroundColor: '#fff', borderBottom: '1px solid #e5e7eb', padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate('/recharge')} style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex' }}>
          <ArrowLeft size={22} color="#374151" />
        </button>
        <h1 style={{ fontSize: 18, fontWeight: 600, color: '#111827', margin: 0 }}>Recargar con cripto</h1>
      </div>

      <div style={{ maxWidth: 480, margin: '0 auto', padding: '20px' }}>
        <p style={{ fontSize: 14, color: '#6b7280', marginBottom: 20 }}>
          Deposita USDT o USDC y recibe creditos en tu cuenta. Se acreditan al confirmarse el pago.
        </p>

        {/* Seleccion de moneda */}
        <label style={{ fontSize: 13, fontWeight: 500, color: '#374151', display: 'block', marginBottom: 8 }}>Tipo de credito</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
          {CREDIT_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setCurrency(opt.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: 14, textAlign: 'left',
                borderRadius: 12, cursor: 'pointer', backgroundColor: '#fff',
                border: currency === opt.key ? `2px solid ${opt.color}` : '1px solid #e5e7eb',
              }}
            >
              <div style={{ width: 40, height: 40, borderRadius: '50%', backgroundColor: `${opt.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Bitcoin size={20} color={opt.color} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 500, color: '#111827' }}>{opt.label}</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{opt.desc}</div>
              </div>
              <div style={{ width: 18, height: 18, borderRadius: '50%', border: currency === opt.key ? `5px solid ${opt.color}` : '2px solid #d1d5db' }} />
            </button>
          ))}
        </div>

        {/* Monto */}
        <label style={{ fontSize: 13, fontWeight: 500, color: '#374151', display: 'block', marginBottom: 8 }}>
          Monto a depositar ({selected?.key.toUpperCase()})
        </label>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.00"
          style={{ width: '100%', boxSizing: 'border-box', padding: '12px 14px', fontSize: 18, fontWeight: 500, color: '#111827', border: '1px solid #d1d5db', borderRadius: 12, marginBottom: 20 }}
        />

        {/* Declaracion de jurisdiccion */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', backgroundColor: '#fef3c7', borderRadius: 12, padding: '12px 14px', marginBottom: 20 }}>
          <input
            type="checkbox"
            checked={declared}
            onChange={(e) => setDeclared(e.target.checked)}
            style={{ marginTop: 3, width: 16, height: 16, flexShrink: 0 }}
          />
          <span style={{ fontSize: 12, color: '#854d0e', lineHeight: 1.5 }}>
            Declaro que no soy residente ni ciudadano de Estados Unidos, la Union Europea o el Reino Unido.
          </span>
        </div>

        {/* Boton */}
        <button
          onClick={handleDeposit}
          disabled={!canContinue}
          style={{
            width: '100%', padding: 14, fontSize: 15, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 12,
            backgroundColor: canContinue ? '#2563eb' : '#93c5fd', cursor: canContinue ? 'pointer' : 'not-allowed',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}
        >
          {loading ? (<><Loader2 size={18} className="animate-spin" /> Iniciando pago...</>) : 'Continuar al pago'}
        </button>

        <p style={{ fontSize: 11, color: '#9ca3af', textAlign: 'center', marginTop: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
          <ShieldCheck size={13} /> Pago procesado de forma segura por NOWPayments
        </p>
      </div>
    </div>
  );
}
