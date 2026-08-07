import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import PinConfirm from '../components/PinConfirm';

const API = import.meta.env.VITE_API_URL || '';

const CURRENCIES = [
  { key: 'USDT', label: 'USDTRIS', color: '#26a17b', rateField: 'usdtris_to_ves' },
  { key: 'USDC', label: 'USDCRIS', color: '#2775ca', rateField: 'usdcris_to_ves' },
];

export default function SendCrypto() {
  const [searchParams] = useSearchParams();
  const initial = (searchParams.get('currency') || 'USDT').toUpperCase();
  const [currency, setCurrency] = useState(CURRENCIES.some(c => c.key === initial) ? initial : 'USDT');
  const [rates, setRates] = useState({});
  const [balances, setBalances] = useState({ USDT: 0, USDC: 0 });
  const [amount, setAmount] = useState('');
  const [beneficiary, setBeneficiary] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPin, setShowPin] = useState(false);
  const [idemRef] = useState(() => 'crypto-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10));

  const load = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: 'Bearer ' + token };
      const [ratesRes, meRes] = await Promise.all([
        axios.get(API + '/rates', { headers }),
        axios.get(API + '/me', { headers }),
      ]);
      setRates(ratesRes.data || {});
      setBalances({
        USDT: Number(meRes.data.balance_usdt || 0),
        USDC: Number(meRes.data.balance_usdc || 0),
      });
    } catch (e) {
      // silencioso
    }
  };

  useEffect(() => { load(); }, []);

  const active = CURRENCIES.find(c => c.key === currency);
  const rate = rates[active.rateField];
  const balance = balances[currency];

  const vesToReceive = useMemo(() => {
    const a = Number(amount || 0);
    if (!a || !rate) return 0;
    return a * Number(rate);
  }, [amount, rate]);

  const doSend = async (pin) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post(API + '/withdraw-crypto', {
        currency,
        amount: Number(amount),
        beneficiary,
        pin,
        idempotency_ref: idemRef,
      }, {
        headers: { Authorization: 'Bearer ' + token },
      });
      toast.success('Envio creado. Queda pendiente de procesar.');
      setAmount('');
      setBeneficiary('');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al crear el envio');
    } finally {
      setLoading(false);
      setShowPin(false);
    }
  };

  const onSubmit = (e) => {
    e.preventDefault();
    const a = Number(amount || 0);
    if (!a || a <= 0) { toast.error('Monto invalido'); return; }
    if (a > balance) { toast.error('Saldo insuficiente'); return; }
    if (!rate) { toast.error('Tasa no configurada para esta moneda'); return; }
    if (!beneficiary.trim()) { toast.error('Indica el beneficiario'); return; }
    setShowPin(true);
  };

  return (
    <div style={{ maxWidth: 480, margin: '0 auto', padding: 16 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Enviar cripto a beneficiario</h2>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        {CURRENCIES.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => setCurrency(c.key)}
            style={{
              flex: 1,
              padding: 12,
              borderRadius: 12,
              border: currency === c.key ? `2px solid ${c.color}` : '1px solid #e5e7eb',
              backgroundColor: currency === c.key ? `${c.color}14` : '#fff',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
        Saldo disponible: {balance.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {active.label}
      </div>

      <form onSubmit={onSubmit}>
        <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>Monto ({currency})</label>
        <input
          type="number"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db', marginBottom: 12 }}
        />

        <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>Beneficiario</label>
        <input
          type="text"
          value={beneficiary}
          onChange={(e) => setBeneficiary(e.target.value)}
          placeholder="Datos del beneficiario en VES"
          style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db', marginBottom: 12 }}
        />

        <div style={{ background: '#f9fafb', borderRadius: 10, padding: 12, marginBottom: 16, fontSize: 14 }}>
          <div>Tasa: {rate ? rate + ' VES por 1 ' + currency : 'no configurada'}</div>
          <div style={{ fontWeight: 700, marginTop: 4 }}>
            Recibe: {vesToReceive.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} VES
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          style={{ width: '100%', background: active.color, color: '#fff', border: 'none', borderRadius: 10, padding: 14, fontSize: 15, fontWeight: 700, cursor: 'pointer' }}
        >
          {loading ? 'Enviando...' : 'Enviar'}
        </button>
      </form>

      {showPin && (
        <PinConfirm
          onConfirm={doSend}
          onCancel={() => setShowPin(false)}
        />
      )}
    </div>
  );
}
