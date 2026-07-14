import { useRate } from '../../contexts/RateContext';
import { fmt } from '../../utils/format';

/**
 * Indicadores de mercado (BCV USD/VES, EUR/VES) — solo visibles post-login.
 * Se removieron de la landing publica (evitar apariencia de casa de cambio);
 * aqui el usuario ya esta autenticado, es informacion de referencia general,
 * no la tasa de ninguna operacion especifica de la plataforma.
 */
export default function MarketRatesStrip({ isMobile = false }) {
  const { rates, loading } = useRate();
  const items = [
    { label: 'USD / VES', value: rates?.bcv_usd_ves },
    { label: 'EUR / VES', value: rates?.bcv_eur_ves },
  ].filter((i) => i.value);

  if (loading || items.length === 0) return null;

  return (
    <div style={{
      backgroundColor: '#ffffff', borderRadius: '16px', border: '1px solid #eef0f4',
      boxShadow: '0 1px 3px rgba(0,0,0,0.03)', padding: '14px 16px',
      display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: '11px', fontWeight: 700, color: '#9ca3af', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
        Indicadores
      </span>
      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', flex: 1 }}>
        {items.map((i) => (
          <div key={i.label} style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '11px', color: '#9ca3af', fontWeight: 600 }}>{i.label}</span>
            <span style={{ fontSize: '15px', fontWeight: 700, color: '#111827', fontVariantNumeric: 'tabular-nums' }}>
              {fmt(i.value)}
            </span>
          </div>
        ))}
      </div>
      <span style={{ fontSize: '10.5px', color: '#9ca3af' }}>Referencial · BCV</span>
    </div>
  );
}
