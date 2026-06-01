import { useState, useEffect } from 'react';
import { TrendingUp, RefreshCw, DollarSign } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';

const CURRENCY_META = {
  dolar: { label: 'USD', flag: '🇺🇸', name: 'Dólar' },
  euro: { label: 'EUR', flag: '🇪🇺', name: 'Euro' },
  yuan: { label: 'CNY', flag: '🇨🇳', name: 'Yuan' },
  lira: { label: 'TRY', flag: '🇹🇷', name: 'Lira' },
  rublo: { label: 'RUB', flag: '🇷🇺', name: 'Rublo' },
};

export const BcvRatesCard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const res = await api.get('/admin/bcv-rates');
      setData(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const res = await api.post('/admin/bcv-rates/refresh');
      setData(res.data.latest);
      toast.success(res.data.saved_new_snapshot ? 'Tasas BCV actualizadas' : 'Sin cambios en BCV');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error al refrescar');
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) return null;

  const rates = data?.rates || {};
  const fetchedAt = data?.fetched_at
    ? new Date(data.fetched_at).toLocaleString('es-VE', { timeZone: 'America/Caracas', dateStyle: 'short', timeStyle: 'short' })
    : '—';
  const hasData = Object.keys(rates).length > 0;

  return (
    <div data-testid="bcv-rates-card" style={{
      backgroundColor: '#fff',
      borderRadius: '16px',
      padding: '20px',
      border: '1px solid #e5e7eb',
      marginTop: '16px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <TrendingUp style={{ width: '22px', height: '22px', color: '#ca8a04' }} />
          </div>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: 0 }}>Tasas BCV</h3>
            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
              Banco Central de Venezuela — auto-actualización cada hora
            </p>
          </div>
        </div>
        <button onClick={refresh} disabled={refreshing}
          style={{ padding: '8px 14px', borderRadius: '10px', border: '1px solid #ca8a04', backgroundColor: '#fff', color: '#ca8a04', fontSize: '13px', fontWeight: '600', cursor: refreshing ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
          data-testid="bcv-refresh-btn"
        >
          <RefreshCw style={{ width: '14px', height: '14px', animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
          {refreshing ? 'Actualizando...' : 'Actualizar ahora'}
        </button>
      </div>

      {!hasData ? (
        <div style={{ padding: '24px', textAlign: 'center', backgroundColor: '#f9fafb', borderRadius: '10px' }}>
          <DollarSign style={{ width: '40px', height: '40px', color: '#9ca3af', margin: '0 auto 8px' }} />
          <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
            Aún no hay datos. Haz click en Actualizar ahora para obtener las tasas.
          </p>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px', marginBottom: '12px' }}>
            {Object.entries(rates).map(([key, val]) => {
              const meta = CURRENCY_META[key] || { label: key.toUpperCase(), flag: '', name: key };
              return (
                <div key={key} style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '10px', border: '1px solid #e5e7eb' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                    <span style={{ fontSize: '18px' }}>{meta.flag}</span>
                    <span style={{ fontSize: '11px', color: '#6b7280', fontWeight: '600', textTransform: 'uppercase' }}>{meta.name}</span>
                  </div>
                  <p style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>
                    Bs. {fmt(val, 4)}
                  </p>
                  <p style={{ fontSize: '10px', color: '#9ca3af', margin: '2px 0 0 0' }}>
                    1 {meta.label} = {fmt(val, 4)} VES
                  </p>
                </div>
              );
            })}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#6b7280', paddingTop: '8px', borderTop: '1px solid #e5e7eb' }}>
            <span>{data?.value_date ? `Valor: ${data.value_date}` : ''}</span>
            <span>Actualizado: {fetchedAt}</span>
          </div>
        </>
      )}
    </div>
  );
};
