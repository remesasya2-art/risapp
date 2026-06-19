import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { BcvRatesCard } from '../common/BcvRatesCard';
import { Bitcoin, RefreshCw, Info } from 'lucide-react';

// Sección unificada de la ruta BTC → USDI → VES (editable) + referencias
// informativas (BCV y precio BTC). Respeta margen y comisión existentes.
export default function TasasBtcSection() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [margen, setMargen] = useState('');
  const [comision, setComision] = useState('');
  const [tasaUsdiVes, setTasaUsdiVes] = useState('');

  const cargar = async () => {
    try {
      const res = await api.get('/admin/btc/config');
      const d = res.data || {};
      setCfg(d);
      setMargen(String(d.margen ?? ''));
      setComision(String(d.comision ?? ''));
      setTasaUsdiVes(String(d.tasa_usd_ves ?? ''));
    } catch (e) {
      toast.error('No se pudo cargar la configuración BTC');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const guardar = async () => {
    const m = parseFloat(margen);
    const c = parseFloat(comision);
    const t = parseFloat(tasaUsdiVes);
    if (!(m > 0 && m <= 1)) { toast.error('Margen debe ser mayor que 0 y hasta 1'); return; }
    if (!(c >= 1 && c <= 2)) { toast.error('Comisión debe estar entre 1 y 2'); return; }
    if (!(t > 0)) { toast.error('La tasa USDI → VES debe ser mayor que 0'); return; }
    try {
      setBusy(true);
      await api.patch('/admin/btc/config', { margen: m, comision: c, tasa_usd_ves: t });
      toast.success('Ruta BTC → USDI → VES actualizada');
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al guardar');
    } finally {
      setBusy(false);
    }
  };

  const restablecer = () => {
    const d = cfg?.defaults || {};
    setMargen(String(d.margen ?? ''));
    setComision(String(d.comision ?? ''));
    setTasaUsdiVes(String(d.tasa_usd_ves ?? ''));
    toast('Valores por defecto cargados (recuerda Guardar)', { icon: 'ℹ️' });
  };

  const card = { backgroundColor: '#fff', borderRadius: '16px', padding: '20px', border: '1px solid #eef0f4', marginBottom: '16px' };
  const input = { width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', boxSizing: 'border-box' };
  const help = { fontSize: '12px', color: '#6b7280', margin: '6px 0 0 0' };
  const lbl = { display: 'block', fontSize: '13px', fontWeight: 700, color: '#374151', marginBottom: '8px' };
  const ej = cfg?.example;

  return (
    <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: '24px', marginTop: '24px' }}>
      <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#374151', margin: '0 0 4px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Bitcoin size={18} color="#EA580C" /> Ruta BTC → USDI → VES
      </h4>
      <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 16px 0' }}>
        Estos valores se aplican a cada nueva transacción BTC. La BCV y el precio BTC son solo de referencia.
      </p>

      {/* Referencias informativas (solo lectura) */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ ...card, backgroundColor: '#FFF7ED', border: '1px solid #FED7AA' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Bitcoin size={22} color="#EA580C" />
              <div>
                <p style={{ fontSize: '12px', color: '#9A3412', fontWeight: 700, margin: 0, letterSpacing: '0.5px' }}>PRECIO BTC ACTUAL (informativo)</p>
                <p style={{ fontSize: '24px', fontWeight: 800, color: '#9A3412', margin: '2px 0 0 0' }}>
                  {cfg?.btc_price_usd ? `$${Number(cfg.btc_price_usd).toLocaleString('es-VE', { minimumFractionDigits: 2 })}` : '—'} <span style={{ fontSize: '13px', fontWeight: 600 }}>USDI</span>
                </p>
                <p style={{ fontSize: '11px', color: '#C2410C', margin: '2px 0 0 0' }}>Fuente: blockchain.info/ticker</p>
              </div>
            </div>
            <button onClick={cargar} disabled={loading} style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '8px 12px', borderRadius: '10px',
              border: '1px solid #FB923C', backgroundColor: '#fff', color: '#EA580C', fontWeight: 600, cursor: 'pointer',
            }}><RefreshCw size={14} /> Refrescar</button>
          </div>
        </div>

        {/* BCV de referencia (componente existente, solo lectura) */}
        <BcvRatesCard />
      </div>

      {/* Parámetros editables */}
      <div style={card}>
        <p style={{ fontSize: '14px', fontWeight: 700, color: '#111827', margin: '0 0 16px 0' }}>Parámetros editables</p>

        <label style={lbl}>Margen (interno)</label>
        <input type="number" step="0.01" value={margen} onChange={(e) => setMargen(e.target.value)} style={input} placeholder="0.99" />
        <p style={help}>Multiplica el precio BTC para nuestro beneficio (ej. 0.99 = 1% de margen).</p>

        <div style={{ height: '16px' }} />

        <label style={lbl}>Comisión (cliente)</label>
        <input type="number" step="0.01" value={comision} onChange={(e) => setComision(e.target.value)} style={input} placeholder="1.03" />
        <p style={help}>Multiplica el USDI que paga el cliente (ej. 1.03 = 3% de comisión).</p>

        <div style={{ height: '16px' }} />

        <label style={lbl}>Tasa USDI → VES</label>
        <input type="number" step="0.01" value={tasaUsdiVes} onChange={(e) => setTasaUsdiVes(e.target.value)} style={input} placeholder="677" />
        <p style={help}>Tasa de cambio usada para convertir USDI a Bolívares al beneficiario.</p>

        <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
          <button onClick={restablecer} disabled={busy} style={{
            padding: '12px 16px', borderRadius: '10px', border: '1px solid #e5e7eb', backgroundColor: '#fff',
            color: '#374151', fontWeight: 600, cursor: 'pointer',
          }}>Restablecer defaults</button>
          <button onClick={guardar} disabled={busy} style={{
            flex: 1, padding: '12px', borderRadius: '10px', border: 'none', backgroundColor: '#16a34a',
            color: '#fff', fontWeight: 700, cursor: 'pointer', opacity: busy ? 0.6 : 1,
          }}>{busy ? 'Guardando…' : 'Guardar cambios'}</button>
        </div>
      </div>

      {/* Vista previa con los valores actuales */}
      {ej && (
        <div style={{ ...card, backgroundColor: '#F9FAFB' }}>
          <p style={{ fontSize: '13px', fontWeight: 700, color: '#374151', margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Info size={15} /> Vista previa: un cliente paga 1 USDI
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div style={{ padding: '12px', borderRadius: '10px', backgroundColor: '#fff', border: '1px solid #eef0f4' }}>
              <p style={{ fontSize: '11px', color: '#9ca3af', margin: 0 }}>CLIENTE PAGA</p>
              <p style={{ fontSize: '18px', fontWeight: 800, color: '#EA580C', margin: '2px 0 0 0' }}>{ej.usd} USDI</p>
            </div>
            <div style={{ padding: '12px', borderRadius: '10px', backgroundColor: '#fff', border: '1px solid #eef0f4' }}>
              <p style={{ fontSize: '11px', color: '#9ca3af', margin: 0 }}>BTC A ENVIAR</p>
              <p style={{ fontSize: '16px', fontWeight: 800, color: '#EA580C', margin: '2px 0 0 0' }}>{ej.sats} sats</p>
            </div>
            <div style={{ padding: '12px', borderRadius: '10px', backgroundColor: '#fff', border: '1px solid #eef0f4' }}>
              <p style={{ fontSize: '11px', color: '#9ca3af', margin: 0 }}>BENEFICIARIO RECIBE</p>
              <p style={{ fontSize: '18px', fontWeight: 800, color: '#16a34a', margin: '2px 0 0 0' }}>{Number(ej.ves).toLocaleString('es-VE', { minimumFractionDigits: 2 })} Bs</p>
              <p style={{ fontSize: '11px', color: '#9ca3af', margin: '2px 0 0 0' }}>Tasa {tasaUsdiVes} Bs/USDI</p>
            </div>
            <div style={{ padding: '12px', borderRadius: '10px', backgroundColor: '#fff', border: '1px solid #eef0f4' }}>
              <p style={{ fontSize: '11px', color: '#9ca3af', margin: 0 }}>PRECIO CON MARGEN</p>
              <p style={{ fontSize: '18px', fontWeight: 800, color: '#2563eb', margin: '2px 0 0 0' }}>${Number(ej.precio_con_margen).toLocaleString('es-VE', { minimumFractionDigits: 2 })}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
