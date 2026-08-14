import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { ArrowLeft, ArrowRight, AlertCircle, User } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import PinConfirm from '../components/PinConfirm';
import { fmt } from '../utils/format';

const CURRENCIES = [
  { key: 'usdt', label: 'USDTRIS', color: '#26A17B', balanceField: 'balance_usdt', rateField: 'usdtris_to_ves' },
  { key: 'usdc', label: 'USDCRIS', color: '#2775CA', balanceField: 'balance_usdc', rateField: 'usdcris_to_ves' },
];

export default function SendCrypto() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();

  const initialCurrency = CURRENCIES.some((c) => c.key === searchParams.get('currency'))
    ? searchParams.get('currency')
    : 'usdt';

  const [currency, setCurrency] = useState(initialCurrency);
  const [amount, setAmount] = useState('');
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showPin, setShowPin] = useState(false);
  const idemRef = useRef(null);

  const cfg = CURRENCIES.find((c) => c.key === currency);
  const balance = user?.[cfg.balanceField] || 0;
  const rate = rates?.[cfg.rateField] || 0;
  const amountVes = amount ? parseFloat(amount) * rate : 0;
  const isValidAmount = amount && parseFloat(amount) > 0 && parseFloat(amount) <= balance;
  const rateAvailable = rate > 0;

  useEffect(() => { loadBeneficiaries(); }, []);

  const loadBeneficiaries = async () => {
    try {
      const response = await api.get('/beneficiaries');
      setBeneficiaries(response.data || []);
    } catch (error) {
      console.error('Error loading beneficiaries:', error);
    }
  };

  const pedirConfirmacion = () => {
    if (!rateAvailable) {
      toast.error('La tasa no está disponible en este momento. Intenta más tarde.');
      return;
    }
    if (!isValidAmount) {
      toast.error('Verifica el monto: debe ser mayor a 0 y no superar tu saldo.');
      return;
    }
    if (!selectedBeneficiary) {
      toast.error('Selecciona un beneficiario');
      return;
    }
    setShowPin(true);
  };

  const handleSend = async () => {
    if (!idemRef.current) idemRef.current = (window.crypto?.randomUUID?.() || (Date.now() + '-' + Math.random().toString(16).slice(2)));
    setLoading(true);
    try {
      await api.post('/withdraw-crypto', {
        currency,
        amount: parseFloat(amount),
        beneficiary_id: selectedBeneficiary.beneficiary_id,
        idempotency_key: idemRef.current,
      });
      idemRef.current = null;
      toast.success('¡Envío registrado! Será procesado pronto.');
      await refreshUser();
      navigate('/history');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar envío');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', paddingBottom: '40px' }}>
      <header style={{ backgroundColor: '#fff', borderBottom: '1px solid #e5e7eb', padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button onClick={() => navigate('/dashboard')} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
        </button>
        <h1 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Enviar con saldo cripto</h1>
      </header>

      <div style={{ maxWidth: '600px', margin: '24px auto', padding: '0 20px' }}>
        <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
          {CURRENCIES.map((c) => (
            <button
              key={c.key}
              onClick={() => setCurrency(c.key)}
              style={{
                flex: 1, padding: '14px', borderRadius: '14px', cursor: 'pointer',
                border: currency === c.key ? `2px solid ${c.color}` : '1px solid #e5e7eb',
                backgroundColor: currency === c.key ? `${c.color}14` : '#fff',
                fontWeight: 700, fontSize: '14px', color: currency === c.key ? c.color : '#6b7280',
              }}
            >
              {c.label}
              <div style={{ fontSize: '12px', fontWeight: 500, marginTop: '4px', color: '#6b7280' }}>
                Saldo: {fmt(user?.[c.balanceField] || 0)}
              </div>
            </button>
          ))}
        </div>

        <div style={{ backgroundColor: '#fff', borderRadius: '16px', padding: '20px', border: '1px solid #eef0f4', marginBottom: '16px' }}>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', display: 'block', marginBottom: '8px' }}>
            Monto en {cfg.label}
          </label>
          <input
            type="number" step="0.01" min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '20px', outline: 'none', boxSizing: 'border-box', fontWeight: 700 }}
          />
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '8px 0 0 0' }}>
            Saldo disponible: {fmt(balance)} {cfg.label}
          </p>
          {!rateAvailable ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px', padding: '10px 12px', backgroundColor: '#fef2f2', borderRadius: '10px', color: '#dc2626', fontSize: '13px' }}>
              <AlertCircle size={16} /> La tasa de {cfg.label} → VES no está configurada todavía.
            </div>
          ) : amount ? (
            <div style={{ marginTop: '12px', padding: '10px 12px', backgroundColor: '#f0fdf4', borderRadius: '10px', color: '#16a34a', fontSize: '14px', fontWeight: 600 }}>
              ≈ {fmt(amountVes)} VES
            </div>
          ) : null}
        </div>

        <div style={{ backgroundColor: '#fff', borderRadius: '16px', padding: '20px', border: '1px solid #eef0f4', marginBottom: '20px' }}>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', display: 'block', marginBottom: '12px' }}>
            Beneficiario en Venezuela
          </label>
          {beneficiaries.length === 0 ? (
            <p style={{ fontSize: '13px', color: '#6b7280' }}>
              No tienes beneficiarios guardados todavía. Puedes crear uno desde la pantalla de{' '}
              <a href="/send" style={{ color: '#4338ca', fontWeight: 600 }}>Enviar RIS</a> y luego volver aquí.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {beneficiaries.map((b) => (
                <button
                  key={b.beneficiary_id}
                  onClick={() => setSelectedBeneficiary(b)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 14px', borderRadius: '10px',
                    border: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '2px solid #4338ca' : '1px solid #e5e7eb',
                    backgroundColor: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '#eef2ff' : '#fff',
                    cursor: 'pointer', textAlign: 'left',
                  }}
                >
                  <User size={18} color="#6b7280" />
                  <div>
                    <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>{b.full_name}</div>
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>{b.bank || b.payment_type} · {b.account_number || b.phone_number}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={pedirConfirmacion}
          disabled={loading}
          style={{
            width: '100%', padding: '16px', borderRadius: '14px', border: 'none',
            backgroundColor: cfg.color, color: '#fff', fontWeight: 700, fontSize: '16px',
            cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.6 : 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
          }}
        >
          {loading ? 'Enviando...' : <>Enviar {cfg.label} <ArrowRight size={18} /></>}
        </button>

        <PinConfirm open={showPin} onClose={() => setShowPin(false)} onVerified={handleSend} />
      </div>
    </div>
  );
}
