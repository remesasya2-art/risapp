import { useEffect, useState } from 'react';
import { Save, RefreshCw, Bitcoin, DollarSign, Percent, Info, Loader, RotateCcw } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { formatRelativeTime } from '../../utils/dates';

export default function BtcAdminConfig() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(null);
  const [margen, setMargen] = useState(0.99);
  const [comision, setComision] = useState(1.02);
  const [tasaUsdVes, setTasaUsdVes] = useState(680);
  const [lastFetch, setLastFetch] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/btc/config');
      setData(res.data);
      setMargen(res.data.margen);
      setComision(res.data.comision);
      setTasaUsdVes(res.data.tasa_usd_ves);
      setLastFetch(new Date());
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al cargar configuración');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleSave = async () => {
    const m = parseFloat(margen);
    const c = parseFloat(comision);
    const t = parseFloat(tasaUsdVes);
    if (isNaN(m) || m <= 0 || m > 1)        return toast.error('Margen debe ser un número entre 0 (exclusivo) y 1 (sin margen)');
    if (isNaN(c) || c < 1 || c > 2)         return toast.error('Comisión debe ser un número entre 1 (sin comisión) y 2');
    if (isNaN(t) || t <= 0)                  return toast.error('Tasa USDI-VES debe ser un número positivo');
    setSaving(true);
    try {
      await api.patch('/admin/btc/config', { margen: m, comision: c, tasa_usd_ves: t });
      toast.success('Configuración guardada');
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!data?.defaults) return;
    setMargen(data.defaults.margen);
    setComision(data.defaults.comision);
    setTasaUsdVes(data.defaults.tasa_usd_ves);
  };

  if (loading) {
    return (
      <div style={{ padding: '48px', textAlign: 'center' }}>
        <RefreshCw size={28} style={{ color: '#F7931A', animation: 'spin 1s linear infinite' }} />
      </div>
    );
  }

  const cardStyle = {
    backgroundColor: '#ffffff', borderRadius: '16px',
    border: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    padding: '20px',
  };

  const m = parseFloat(margen);
  const c = parseFloat(comision);
  const t = parseFloat(tasaUsdVes);
  const validInputs = !isNaN(m) && !isNaN(c) && !isNaN(t) && m > 0 && m <= 1 && c >= 1 && c <= 2 && t > 0;
  const btcPrice = data?.btc_price_usd || 0;
  // Live preview: 1 USD client → BTC and VES
  const previewBtc = btcPrice > 0 && validInputs ? ((1.0 * c) / (btcPrice * m)) : 0;
  const previewSats = Math.round(previewBtc * 100_000_000);
  const previewVes = validInputs ? (1.0 * t) : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Live BTC Price */}
      <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #FEF3C7 0%, #FED7AA 100%)', borderColor: '#FCD34D' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{ width: '48px', height: '48px', borderRadius: '12px', backgroundColor: '#F7931A', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bitcoin size={28} color="#fff" />
            </div>
            <div>
              <p style={{ fontSize: '12px', color: '#92400E', margin: 0, textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>Precio Bitcoin actual</p>
              <p style={{ fontSize: '28px', color: '#7C2D12', margin: '2px 0 0 0', fontWeight: 800, fontVariantNumeric: 'tabular-nums' }}>
                ${btcPrice > 0 ? fmt(btcPrice, 2) : '—'} USDI
              </p>
              <p style={{ fontSize: '11px', color: '#92400E', margin: '2px 0 0 0' }}>
                Fuente: {data?.btc_price_source || 'blockchain.info'}{lastFetch ? ` · Actualizado ${formatRelativeTime(lastFetch)}` : ''}
              </p>
            </div>
          </div>
          <button
            onClick={load}
            style={{ padding: '10px 16px', borderRadius: '12px', backgroundColor: '#fff', border: '1.5px solid #FCD34D', cursor: 'pointer', color: '#92400E', fontSize: '13px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <RefreshCw size={14} /> Refrescar precio
          </button>
        </div>
      </div>

      {/* Editable parameters */}
      <div style={cardStyle}>
        <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', margin: '0 0 4px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Percent size={16} /> Parámetros editables
        </h3>
        <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 18px 0' }}>
          Estos valores se aplican automáticamente a cada nueva transacción BTC.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
          <Field
            label="Margen (interno)"
            help={`Multiplica el precio BTC para nuestro beneficio. ${m === 1 ? 'Sin margen.' : `${((1 - m) * 100).toFixed(2)}% de margen.`}`}
            value={margen}
            onChange={(v) => setMargen(v)}
            min={0.5} max={1.0} step={0.001}
            placeholder={`Default: ${data?.defaults?.margen || 0.99}`}
            invalid={isNaN(m) || m <= 0 || m > 1}
            dataTestId="btc-config-margen"
          />
          <Field
            label="Comisión (cliente)"
            help={`Multiplica el USDI que el cliente paga. ${c === 1 ? 'Sin comisión.' : `${((c - 1) * 100).toFixed(2)}% de comisión al cliente.`}`}
            value={comision}
            onChange={(v) => setComision(v)}
            min={1.0} max={2.0} step={0.001}
            placeholder={`Default: ${data?.defaults?.comision || 1.02}`}
            invalid={isNaN(c) || c < 1 || c > 2}
            dataTestId="btc-config-comision"
          />
          <Field
            label="Tasa USDI → VES"
            help="Tasa de cambio usada para convertir USDI a Bolívares al beneficiario."
            value={tasaUsdVes}
            onChange={(v) => setTasaUsdVes(v)}
            min={0} step={0.01}
            placeholder={`Default: ${data?.defaults?.tasa_usd_ves || 680}`}
            invalid={isNaN(t) || t <= 0}
            unit="Bs"
            dataTestId="btc-config-tasa"
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
          <button
            onClick={handleReset}
            disabled={saving}
            style={{ padding: '10px 16px', borderRadius: '10px', backgroundColor: '#f3f4f6', color: '#374151', border: 'none', fontWeight: 600, fontSize: '13px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <RotateCcw size={14} /> Restablecer defaults
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !validInputs}
            data-testid="btc-config-save"
            style={{ padding: '10px 18px', borderRadius: '10px', backgroundColor: !validInputs ? '#fca5a5' : '#16a34a', color: '#fff', border: 'none', fontWeight: 600, fontSize: '13px', cursor: !validInputs ? 'not-allowed' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            {saving ? <Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={14} />}
            Guardar cambios
          </button>
        </div>
      </div>

      {/* Live preview */}
      <div style={{ ...cardStyle, backgroundColor: '#f9fafb' }}>
        <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', margin: '0 0 4px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Info size={16} /> Vista previa con los valores actuales
        </h3>
        <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 14px 0' }}>
          Ejemplo: un cliente paga <strong>1 USDI</strong> → recibe lo siguiente con tus parámetros:
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
          <Stat
            color="#F7931A"
            label="Cliente paga"
            value="$ 1.00"
            sub="USDI nominal"
          />
          <Stat
            color="#F7931A"
            label="BTC a enviar"
            value={btcPrice > 0 ? `₿ ${previewBtc.toFixed(8)}` : '—'}
            sub={btcPrice > 0 ? `${fmt(previewSats, 0)} sats` : ''}
          />
          <Stat
            color="#16a34a"
            label="Beneficiario recibe"
            value={`${fmt(previewVes)} Bs`}
            sub={`Tasa ${fmt(t || 0)} Bs/USDI`}
          />
          <Stat
            color="#3b82f6"
            label="Precio con margen"
            value={btcPrice > 0 && validInputs ? `$ ${fmt(btcPrice * m, 2)}` : '—'}
            sub={btcPrice > 0 ? `Real $ ${fmt(btcPrice, 2)}` : ''}
          />
        </div>
      </div>
    </div>
  );
}

function Field({ label, help, value, onChange, invalid, placeholder, unit, dataTestId, ...rest }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label}
      </label>
      <div style={{ position: 'relative' }}>
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          data-testid={dataTestId}
          {...rest}
          style={{
            width: '100%', padding: '10px 12px',
            paddingRight: unit ? '40px' : '12px',
            borderRadius: '10px',
            border: invalid ? '1.5px solid #ef4444' : '1.5px solid #e5e7eb',
            fontSize: '15px', fontWeight: 600, color: '#111827',
            outline: 'none', boxSizing: 'border-box',
            fontVariantNumeric: 'tabular-nums',
          }}
        />
        {unit && (
          <span style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', color: '#6b7280', fontSize: '13px', fontWeight: 500 }}>
            {unit}
          </span>
        )}
      </div>
      <p style={{ fontSize: '11px', color: '#6b7280', margin: '6px 0 0 0', lineHeight: 1.35 }}>
        {help}
      </p>
    </div>
  );
}

function Stat({ label, value, sub, color = '#374151' }) {
  return (
    <div style={{ backgroundColor: '#fff', borderRadius: '12px', padding: '12px 14px', border: '1px solid #e5e7eb' }}>
      <p style={{ fontSize: '11px', color: '#6b7280', margin: 0, textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>{label}</p>
      <p style={{ fontSize: '17px', color, margin: '4px 0 0 0', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</p>
      {sub && <p style={{ fontSize: '11px', color: '#9ca3af', margin: '2px 0 0 0' }}>{sub}</p>}
    </div>
  );
}
