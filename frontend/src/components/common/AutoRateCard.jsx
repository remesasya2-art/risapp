import { useState, useEffect } from 'react';
import { Clock, Zap } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { RateHistoryButton } from './RateHistoryButton';

const DAY_NAMES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

const NB = '#e0e5ec';
const RAISED = '5px 5px 10px #a3b1c6, -5px -5px 10px #ffffff';
const RAISED_SM = '3px 3px 6px #a3b1c6, -3px -3px 6px #ffffff';
const INSET = 'inset 3px 3px 6px #a3b1c6, inset -3px -3px 6px #ffffff';
const INK = '#2b3a5c';
const SOFT = '#5a6a88';
const AMBER = '#b3730d';
const GREEN = '#1f9d6b';
const BLUE = '#2f6fd6';

export const AutoRateCard = ({ baseRisToVes, baseVesToRis, onChange, userRole }) => {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const res = await api.get('/admin/auto-rate');
      setConfig(res.data);
    } catch (e) {
      toast.error('No se pudo cargar configuración');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (patch) => {
    setSaving(true);
    try {
      const res = await api.post('/admin/auto-rate', patch);
      toast.success('Configuración guardada');
      setConfig(c => ({ ...c, ...res.data }));
      await load();
      if (onChange) onChange();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return null;
  if (!config) return null;

  const workDaysSet = new Set(config.work_days || []);
  const toggleDay = (d) => {
    const next = new Set(workDaysSet);
    if (next.has(d)) next.delete(d); else next.add(d);
    save({ work_days: Array.from(next).sort() });
  };

  const effectiveRisToVes = config.enabled && config.is_off_hours_now
    ? (baseRisToVes ?? 0) - Number(config.delta_brl_ves || 0)
    : baseRisToVes;
  const effectiveVesToRis = config.enabled && config.is_off_hours_now
    ? (baseVesToRis ?? 0) + Number(config.delta_ves_brl || 0)
    : baseVesToRis;

  const on = !!config.enabled;
  const off = !!config.is_off_hours_now;

  return (
    <div data-testid="auto-rate-card" style={{ background: NB, borderRadius: '18px', boxShadow: RAISED, padding: '16px 18px', marginTop: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
        <div style={{ width: '34px', height: '34px', borderRadius: '11px', boxShadow: RAISED_SM, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Zap style={{ width: '17px', height: '17px', color: GREEN }} />
        </div>
        <h3 style={{ fontSize: '15px', fontWeight: 700, color: INK, margin: 0, flex: 1 }}>Tasa automática</h3>
        <div onClick={() => !saving && save({ enabled: !on })} data-testid="auto-rate-toggle"
          style={{ width: '46px', height: '26px', borderRadius: '16px', boxShadow: INSET, background: on ? '#d1f0e3' : '#dfe4ec', position: 'relative', cursor: 'pointer', flexShrink: 0 }}>
          <div style={{ position: 'absolute', top: '3px', left: on ? '23px' : '3px', width: '20px', height: '20px', borderRadius: '50%', background: on ? GREEN : '#9aa7bf', boxShadow: '1px 1px 3px rgba(0,0,0,.25)', transition: 'left .2s' }} />
        </div>
        <span style={{ fontSize: '12px', fontWeight: 700, color: on ? GREEN : SOFT, flexShrink: 0 }}>{on ? 'Activo' : 'Inactivo'}</span>
        <RateHistoryButton userRole={userRole} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', borderRadius: '11px', boxShadow: INSET, marginBottom: '14px', fontSize: '12px', fontWeight: 600, color: off ? AMBER : BLUE }}>
        <Clock style={{ width: '15px', height: '15px' }} />
        {off ? 'Fuera de horario' : 'Dentro de horario'}
        <span style={{ color: SOFT, fontWeight: 500, marginLeft: 'auto' }}>
          Caracas {new Date(config.current_caracas_time).toLocaleTimeString('es-VE', { timeZone: 'America/Caracas', hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '14px' }}>
        <div style={{ padding: '10px 12px', borderRadius: '12px', boxShadow: RAISED_SM }}>
          <div style={{ fontSize: '10px', letterSpacing: '.05em', color: SOFT, fontWeight: 700, textTransform: 'uppercase' }}>BRL → VES</div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: INK, marginTop: '3px' }}>
            {fmt(baseRisToVes)}<span style={{ color: SOFT, fontWeight: 500, margin: '0 5px' }}>→</span><span style={{ color: on && off ? AMBER : INK }}>{fmt(effectiveRisToVes)}</span>
          </div>
        </div>
        <div style={{ padding: '10px 12px', borderRadius: '12px', boxShadow: RAISED_SM }}>
          <div style={{ fontSize: '10px', letterSpacing: '.05em', color: SOFT, fontWeight: 700, textTransform: 'uppercase' }}>VES → BRL</div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: INK, marginTop: '3px' }}>
            {fmt(baseVesToRis)}<span style={{ color: SOFT, fontWeight: 500, margin: '0 5px' }}>→</span><span style={{ color: on && off ? AMBER : INK }}>{fmt(effectiveVesToRis)}</span>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '9px', marginBottom: '14px' }}>
        <div>
          <label style={{ fontSize: '10px', color: SOFT, fontWeight: 600, display: 'block', marginBottom: '5px', textAlign: 'center' }}>− BRL→VES</label>
          <input type="number" step="0.01" defaultValue={config.delta_brl_ves} disabled={saving}
            onBlur={e => { const v = parseFloat(e.target.value); if (!isNaN(v) && v !== config.delta_brl_ves) save({ delta_brl_ves: v }); }}
            data-testid="delta-brl-ves"
            style={{ width: '100%', padding: '9px 6px', borderRadius: '10px', border: 'none', background: NB, boxShadow: INSET, fontSize: '14px', color: INK, textAlign: 'center', fontWeight: 600, outline: 'none', boxSizing: 'border-box' }} />
        </div>
        <div>
          <label style={{ fontSize: '10px', color: SOFT, fontWeight: 600, display: 'block', marginBottom: '5px', textAlign: 'center' }}>+ VES→BRL</label>
          <input type="number" step="0.01" defaultValue={config.delta_ves_brl} disabled={saving}
            onBlur={e => { const v = parseFloat(e.target.value); if (!isNaN(v) && v !== config.delta_ves_brl) save({ delta_ves_brl: v }); }}
            data-testid="delta-ves-brl"
            style={{ width: '100%', padding: '9px 6px', borderRadius: '10px', border: 'none', background: NB, boxShadow: INSET, fontSize: '14px', color: INK, textAlign: 'center', fontWeight: 600, outline: 'none', boxSizing: 'border-box' }} />
        </div>
        <div>
          <label style={{ fontSize: '10px', color: SOFT, fontWeight: 600, display: 'block', marginBottom: '5px', textAlign: 'center' }}>Inicio</label>
          <select value={config.work_start_hour} onChange={e => save({ work_start_hour: parseInt(e.target.value) })} disabled={saving} data-testid="work-start"
            style={{ width: '100%', padding: '9px 4px', borderRadius: '10px', border: 'none', background: NB, boxShadow: INSET, fontSize: '13px', color: INK, textAlign: 'center', fontWeight: 600, outline: 'none' }}>
            {Array.from({length: 24}, (_, i) => <option key={i} value={i}>{String(i).padStart(2,'0')}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: '10px', color: SOFT, fontWeight: 600, display: 'block', marginBottom: '5px', textAlign: 'center' }}>Fin</label>
          <select value={config.work_end_hour} onChange={e => save({ work_end_hour: parseInt(e.target.value) })} disabled={saving} data-testid="work-end"
            style={{ width: '100%', padding: '9px 4px', borderRadius: '10px', border: 'none', background: NB, boxShadow: INSET, fontSize: '13px', color: INK, textAlign: 'center', fontWeight: 600, outline: 'none' }}>
            {Array.from({length: 24}, (_, i) => <option key={i} value={i}>{String(i).padStart(2,'0')}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label style={{ fontSize: '10px', color: SOFT, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: '8px', display: 'block' }}>Días laborales</label>
        <div style={{ display: 'flex', gap: '6px' }}>
          {DAY_NAMES.map((name, idx) => {
            const active = workDaysSet.has(idx);
            return (
              <button key={idx} onClick={() => toggleDay(idx)} disabled={saving} data-testid={`work-day-${idx}`}
                style={{ flex: 1, height: '36px', borderRadius: '11px', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, background: NB, boxShadow: active ? INSET : RAISED_SM, color: active ? BLUE : SOFT }}
              >{name.slice(0,2)}</button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
