import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { Wallet } from 'lucide-react';

// Sección de tasas para envíos con saldo cripto (USDTRIS/USDCRIS → VES).
// Usa los mismos endpoints genéricos de tasas (GET/POST /admin/rates), solo
// agregando sus dos campos propios. No lleva ajuste automático por horario.
export default function TasasCriptoSection() {
  const [rates, setRates] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyUsdt, setBusyUsdt] = useState(false);
  const [busyUsdc, setBusyUsdc] = useState(false);
  const [usdtInput, setUsdtInput] = useState('');
  const [usdcInput, setUsdcInput] = useState('');

  const cargar = async () => {
    try {
      const res = await api.get('/admin/rates');
      setRates(res.data || {});
    } catch (e) {
      toast.error('No se pudo cargar la tasa cripto');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const guardarUsdt = async () => {
    const v = parseFloat(usdtInput);
    if (!(v > 0)) { toast.error('La tasa debe ser mayor que 0'); return; }
    try {
      setBusyUsdt(true);
      await api.post('/admin/rates', { usdtris_to_ves: v });
      toast.success('Tasa USDTRIS → VES actualizada');
      setUsdtInput('');
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al guardar');
    } finally { setBusyUsdt(false); }
  };

  const guardarUsdc = async () => {
    const v = parseFloat(usdcInput);
    if (!(v > 0)) { toast.error('La tasa debe ser mayor que 0'); return; }
    try {
      setBusyUsdc(true);
      await api.post('/admin/rates', { usdcris_to_ves: v });
      toast.success('Tasa USDCRIS → VES actualizada');
      setUsdcInput('');
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al guardar');
    } finally { setBusyUsdc(false); }
  };

  if (loading) return null;

  return (
    <div style={{ marginTop: '24px', paddingTop: '24px', borderTop: '1px solid #e5e7eb' }}>
      <h4 style={{ fontSize: '16px', fontWeight: '600', color: '#374151', margin: '0 0 16px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Wallet size={18} /> Envíos con saldo cripto (USDTRIS / USDCRIS → VES)
      </h4>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        <div style={{ padding: '20px', backgroundColor: '#f0fdfa', borderRadius: '14px', border: '1px solid #99f6e4' }}>
          <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#0d9488', marginBottom: '12px' }}>
            USDTRIS → VES
          </label>
          <p style={{ fontSize: '13px', color: '#374151', margin: '0 0 12px 0' }}>
            Actual: {rates?.usdtris_to_ves ? `1 USDT = ${rates.usdtris_to_ves} VES` : 'sin configurar'}
          </p>
          <input
            type="number" step="0.01"
            value={usdtInput}
            onChange={(e) => setUsdtInput(e.target.value)}
            placeholder={rates?.usdtris_to_ves != null ? String(rates.usdtris_to_ves) : '0'}
            style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
          />
          <button onClick={guardarUsdt} disabled={busyUsdt}
            style={{ width: '100%', height: '44px', borderRadius: '10px', border: 'none', backgroundColor: '#0d9488', color: '#fff', fontWeight: 700, fontSize: '14px', cursor: busyUsdt ? 'not-allowed' : 'pointer', opacity: busyUsdt ? 0.6 : 1 }}>
            Actualizar USDTRIS → VES
          </button>
        </div>
        <div style={{ padding: '20px', backgroundColor: '#eff6ff', borderRadius: '14px', border: '1px solid #bfdbfe' }}>
          <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#2563eb', marginBottom: '12px' }}>
            USDCRIS → VES
          </label>
          <p style={{ fontSize: '13px', color: '#374151', margin: '0 0 12px 0' }}>
            Actual: {rates?.usdcris_to_ves ? `1 USDC = ${rates.usdcris_to_ves} VES` : 'sin configurar'}
          </p>
          <input
            type="number" step="0.01"
            value={usdcInput}
            onChange={(e) => setUsdcInput(e.target.value)}
            placeholder={rates?.usdcris_to_ves != null ? String(rates.usdcris_to_ves) : '0'}
            style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
          />
          <button onClick={guardarUsdc} disabled={busyUsdc}
            style={{ width: '100%', height: '44px', borderRadius: '10px', border: 'none', backgroundColor: '#2563eb', color: '#fff', fontWeight: 700, fontSize: '14px', cursor: busyUsdc ? 'not-allowed' : 'pointer', opacity: busyUsdc ? 0.6 : 1 }}>
            Actualizar USDCRIS → VES
          </button>
        </div>
      </div>
      <p style={{ fontSize: '12px', color: '#9ca3af', margin: '12px 0 0 0' }}>
        Esta tasa no aplica el ajuste automático fuera de horario (a diferencia de RIS → VES). Es un valor fijo que configuras aquí, y mientras no la configures los usuarios no podrán enviar con ese saldo.
      </p>
    </div>
  );
}
