import { useState, useEffect } from 'react';
import { TrendingUp, RefreshCw, DollarSign, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt, fmtAntiguedadHoras } from '../../utils/format';

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

  // POR QUE ESTA PANTALLA AHORA DICE DE CUANDO ES EL DATO
  //
  // El raspador del BCV estuvo roto semanas —al sitio le falta una pieza de su
  // cadena de certificados— y esta tarjeta mostraba el ultimo numero que habia
  // traido como si fuera el de hoy. No decia nada. Y peor: la contabilidad
  // preferia ese numero congelado antes que el que el operador carga a mano.
  //
  // Un dato viejo presentado como de hoy miente por omision. Ahora la
  // antiguedad la calcula el servidor (`vigencia` en bcv_scraper.py) y viaja
  // con el dato, asi que la pantalla dice exactamente lo mismo que uso la
  // contabilidad para decidir.
  const vencida = data?.vencida === true;
  const antiguedad = fmtAntiguedadHoras(data?.edad_horas);

  return (
    <div data-testid="bcv-rates-card" style={{
      backgroundColor: 'var(--en-oscuro-superficie, #fff)',
      borderRadius: '16px',
      padding: '20px',
      border: '1px solid var(--en-oscuro-linea, #e5e7eb)',
      marginTop: '16px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: 'var(--en-oscuro-alerta-suave, #fef3c7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <TrendingUp style={{ width: '22px', height: '22px', color: 'var(--en-oscuro-alerta, #ca8a04)' }} />
          </div>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: 'var(--en-oscuro-texto, #111827)', margin: 0 }}>Tasas BCV</h3>
            <p style={{ fontSize: '12px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '2px 0 0 0' }}>
              Banco Central de Venezuela — auto-actualización cada hora
            </p>
          </div>
        </div>
        <button onClick={refresh} disabled={refreshing}
          style={{ padding: '8px 14px', borderRadius: '10px', border: '1px solid var(--en-oscuro-alerta, #ca8a04)', backgroundColor: 'var(--en-oscuro-superficie, #fff)', color: 'var(--en-oscuro-alerta, #ca8a04)', fontSize: '13px', fontWeight: '600', cursor: refreshing ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
          data-testid="bcv-refresh-btn"
        >
          <RefreshCw style={{ width: '14px', height: '14px', animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
          {refreshing ? 'Actualizando...' : 'Actualizar ahora'}
        </button>
      </div>

      {hasData && vencida && (
        <div data-testid="bcv-vencida" style={{
          display: 'flex', alignItems: 'flex-start', gap: '10px',
          padding: '12px 14px', marginBottom: '14px', borderRadius: '10px',
          backgroundColor: 'var(--en-oscuro-error-suave, #fef2f2)', border: '1px solid var(--en-oscuro-error-borde, #fecaca)'
        }}>
          <AlertTriangle style={{ width: '18px', height: '18px', color: 'var(--en-oscuro-error, #dc2626)', flexShrink: 0, marginTop: '1px' }} />
          <div>
            <p style={{ fontSize: '13px', fontWeight: 700, color: 'var(--en-oscuro-error, #991b1b)', margin: 0 }}>
              Este dato es {antiguedad} y dejó de usarse
            </p>
            <p style={{ fontSize: '12px', color: 'var(--en-oscuro-error, #b91c1c)', margin: '4px 0 0 0', lineHeight: 1.45 }}>
              El límite está en {data?.horas_de_vigencia ?? 24}{(data?.horas_de_vigencia ?? 24) === 1 ? ' hora' : ' horas'}. La contabilidad
              está usando el dólar que vos cargás a mano en Tasas, no éste.
              Probá «Actualizar ahora»; si sigue sin traer nada, el registro del
              servidor dice por qué. El límite se cambia en Configuración.
            </p>
          </div>
        </div>
      )}

      {!hasData ? (
        <div style={{ padding: '24px', textAlign: 'center', backgroundColor: 'var(--en-oscuro-superficie-2, #f9fafb)', borderRadius: '10px' }}>
          <DollarSign style={{ width: '40px', height: '40px', color: 'var(--en-oscuro-texto-3, #9ca3af)', margin: '0 auto 8px' }} />
          <p style={{ fontSize: '13px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: 0 }}>
            Aún no hay datos. Haz click en Actualizar ahora para obtener las tasas.
          </p>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px', marginBottom: '12px' }}>
            {Object.entries(rates).map(([key, val]) => {
              const meta = CURRENCY_META[key] || { label: key.toUpperCase(), flag: '', name: key };
              return (
                <div key={key} style={{ padding: '12px', backgroundColor: 'var(--en-oscuro-superficie-2, #f9fafb)', borderRadius: '10px', border: '1px solid var(--en-oscuro-linea, #e5e7eb)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                    <span style={{ fontSize: '18px' }}>{meta.flag}</span>
                    <span style={{ fontSize: '11px', color: 'var(--en-oscuro-texto-2, #6b7280)', fontWeight: '600', textTransform: 'uppercase' }}>{meta.name}</span>
                  </div>
                  <p style={{ fontSize: '18px', fontWeight: '700', color: 'var(--en-oscuro-texto, #111827)', margin: 0 }}>
                    Bs. {fmt(val, 4)}
                  </p>
                  <p style={{ fontSize: '10px', color: 'var(--en-oscuro-texto-3, #9ca3af)', margin: '2px 0 0 0' }}>
                    1 {meta.label} = {fmt(val, 4)} VES
                  </p>
                </div>
              );
            })}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--en-oscuro-texto-2, #6b7280)', paddingTop: '8px', borderTop: '1px solid var(--en-oscuro-linea, #e5e7eb)' }}>
            <span>{data?.value_date ? `Valor: ${data.value_date}` : ''}</span>
            <span style={{ color: vencida ? 'var(--en-oscuro-error, #b91c1c)' : 'var(--en-oscuro-texto-2, #6b7280)', fontWeight: vencida ? 700 : 400 }}>
              Actualizado: {fetchedAt}{hasData ? ` · ${antiguedad}` : ''}
            </span>
          </div>
        </>
      )}
    </div>
  );
};
