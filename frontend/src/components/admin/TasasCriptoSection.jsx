import React, { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';

const API = import.meta.env.VITE_API_URL || '';

export default function TasasCriptoSection() {
  const [rates, setRates] = useState({ usdtris_to_ves: '', usdcris_to_ves: '' });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(API + '/admin/rates', {
        headers: { Authorization: 'Bearer ' + token },
      });
      setRates({
        usdtris_to_ves: response.data.usdtris_to_ves ?? '',
        usdcris_to_ves: response.data.usdcris_to_ves ?? '',
      });
    } catch (e) {
      // silencioso
    }
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post(API + '/admin/rates', {
        usdtris_to_ves: rates.usdtris_to_ves === '' ? null : Number(rates.usdtris_to_ves),
        usdcris_to_ves: rates.usdcris_to_ves === '' ? null : Number(rates.usdcris_to_ves),
      }, {
        headers: { Authorization: 'Bearer ' + token },
      });
      toast.success('Tasas cripto actualizadas');
      load();
    } catch (e) {
      toast.error('Error al guardar tasas cripto');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ background: '#fff', borderRadius: 14, padding: 20, marginTop: 16, border: '1px solid #e5e7eb' }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>Tasas de envio cripto (VES)</h3>

      <label style={{ display: 'block', fontSize: 13, color: '#374151', marginBottom: 4 }}>USDTRIS &rarr; VES</label>
      <input
        type="number"
        value={rates.usdtris_to_ves}
        onChange={(e) => setRates({ ...rates, usdtris_to_ves: e.target.value })}
        style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db', marginBottom: 4 }}
      />
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        {rates.usdtris_to_ves ? `1 USDT = ${rates.usdtris_to_ves} VES` : 'Sin configurar'}
      </div>

      <label style={{ display: 'block', fontSize: 13, color: '#374151', marginBottom: 4 }}>USDCRIS &rarr; VES</label>
      <input
        type="number"
        value={rates.usdcris_to_ves}
        onChange={(e) => setRates({ ...rates, usdcris_to_ves: e.target.value })}
        style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db', marginBottom: 4 }}
      />
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        {rates.usdcris_to_ves ? `1 USDC = ${rates.usdcris_to_ves} VES` : 'Sin configurar'}
      </div>

      <button
        onClick={save}
        disabled={loading}
        style={{ background: '#111827', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 16px', fontWeight: 600, cursor: 'pointer' }}
      >
        {loading ? 'Guardando...' : 'Guardar tasas cripto'}
      </button>
    </div>
  );
}
