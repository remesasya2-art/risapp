import { useState, useEffect } from 'react';
import { Clock, Zap } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { RateHistoryButton } from './RateHistoryButton';

const DAY_NAMES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

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

  return (
    <div data-testid="auto-rate-card" style={{
      backgroundColor: '#fff',
      borderRadius: '16px',
      padding: '20px',
      border: '1px solid #e5e7eb',
      marginTop: '16px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: config.enabled ? '#dcfce7' : '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Zap style={{ width: '22px', height: '22px', color: config.enabled ? '#16a34a' : '#6b7280' }} />
          </div>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: 0 }}>Tasa Automática</h3>
            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
              Ajuste automático fuera de horario, domingos y feriados venezolanos
            </p>
          </div>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
          <input type="checkbox" checked={config.enabled || false}
            onChange={e => save({ enabled: e.target.checked })}
            disabled={saving}
            data-testid="auto-rate-toggle"
            style={{ width: '20px', height: '20px', cursor: 'pointer' }}
          />
          <span style={{ fontSize: '13px', fontWeight: '600', color: config.enabled ? '#16a34a' : '#6b7280' }}>
            {config.enabled ? 'Activo' : 'Inactivo'}
          </span>
        </label>
        <RateHistoryButton userRole={userRole} />
      </div>

      {/* Status current */}
      <div style={{ padding: '12px 14px', borderRadius: '10px', backgroundColor: config.is_off_hours_now ? '#fef3c7' : '#dbeafe', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Clock style={{ width: '18px', height: '18px', color: config.is_off_hours_now ? '#ca8a04' : '#2563eb' }} />
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: '13px', fontWeight: '600', color: '#111827', margin: 0 }}>
            {config.is_off_hours_now ? 'FUERA de horario laboral' : 'DENTRO de horario laboral'}
          </p>
          <p style={{ fontSize: '11px', color: '#6b7280', margin: '2px 0 0 0' }}>
            Hora Caracas: {new Date(config.current_caracas_time).toLocaleString('es-VE', { timeZone: 'America/Caracas', dateStyle: 'short', timeStyle: 'medium' })}
          </p>
        </div>
      </div>

      {/* Current rates (base + effective) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
        <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '10px', border: '1px solid #e5e7eb' }}>
          <p style={{ fontSize: '11px', color: '#6b7280', margin: '0 0 4px 0', textTransform: 'uppercase', fontWeight: '600' }}>BRL → VES</p>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>Base: <strong>{fmt(baseRisToVes)}</strong></p>
          <p style={{ fontSize: '18px', fontWeight: '700', color: config.is_off_hours_now && config.enabled ? '#ca8a04' : '#111827', margin: '2px 0 0 0' }}>
            Actual: {fmt(effectiveRisToVes)}
          </p>
        </div>
        <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '10px', border: '1px solid #e5e7eb' }}>
          <p style={{ fontSize: '11px', color: '#6b7280', margin: '0 0 4px 0', textTransform: 'uppercase', fontWeight: '600' }}>VES → BRL</p>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>Base: <strong>{fmt(baseVesToRis)}</strong></p>
          <p style={{ fontSize: '18px', fontWeight: '700', color: config.is_off_hours_now && config.enabled ? '#ca8a04' : '#111827', margin: '2px 0 0 0' }}>
            Actual: {fmt(effectiveVesToRis)}
          </p>
        </div>
      </div>

      {/* Deltas */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
        <div>
          <label style={{ fontSize: '12px', color: '#374151', fontWeight: '500', display: 'block', marginBottom: '4px' }}>
            BRL→VES: restar fuera de horario
          </label>
          <input type="number" step="0.01"
            defaultValue={config.delta_brl_ves}
            onBlur={e => {
              const v = parseFloat(e.target.value);
              if (!isNaN(v) && v !== config.delta_brl_ves) save({ delta_brl_ves: v });
            }}
            disabled={saving}
            style={{ width: '100%', padding: '8px 10px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box' }}
            data-testid="delta-brl-ves"
          />
        </div>
        <div>
          <label style={{ fontSize: '12px', color: '#374151', fontWeight: '500', display: 'block', marginBottom: '4px' }}>
            VES→BRL: sumar fuera de horario
          </label>
          <input type="number" step="0.01"
            defaultValue={config.delta_ves_brl}
            onBlur={e => {
              const v = parseFloat(e.target.value);
              if (!isNaN(v) && v !== config.delta_ves_brl) save({ delta_ves_brl: v });
            }}
            disabled={saving}
            style={{ width: '100%', padding: '8px 10px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box' }}
            data-testid="delta-ves-brl"
          />
        </div>
      </div>

      {/* Work hours */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
        <div>
          <label style={{ fontSize: '12px', color: '#374151', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Inicio horario</label>
          <select value={config.work_start_hour} onChange={e => save({ work_start_hour: parseInt(e.target.value) })}
            disabled={saving}
            style={{ width: '100%', padding: '8px 10px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px' }}
            data-testid="work-start"
          >
            {Array.from({length: 24}, (_, i) => <option key={i} value={i}>{String(i).padStart(2,'0')}:00</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: '12px', color: '#374151', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Fin horario</label>
          <select value={config.work_end_hour} onChange={e => save({ work_end_hour: parseInt(e.target.value) })}
            disabled={saving}
            style={{ width: '100%', padding: '8px 10px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px' }}
            data-testid="work-end"
          >
            {Array.from({length: 24}, (_, i) => <option key={i} value={i}>{String(i).padStart(2,'0')}:00</option>)}
          </select>
        </div>
      </div>

      {/* Working days */}
      <div>
        <label style={{ fontSize: '12px', color: '#374151', fontWeight: '500', display: 'block', marginBottom: '8px' }}>Días laborales</label>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {DAY_NAMES.map((name, idx) => {
            const active = workDaysSet.has(idx);
            return (
              <button key={idx} onClick={() => toggleDay(idx)} disabled={saving}
                style={{
                  padding: '6px 14px', borderRadius: '8px', border: 'none',
                  backgroundColor: active ? '#2563eb' : '#f3f4f6',
                  color: active ? '#fff' : '#6b7280',
                  fontSize: '12px', fontWeight: '600', cursor: 'pointer',
                  minWidth: '48px'
                }}
                data-testid={`work-day-${idx}`}
              >{name}</button>
            );
          })}
        </div>
        <p style={{ fontSize: '11px', color: '#9ca3af', margin: '8px 0 0 0' }}>
          Feriados venezolanos aplican automáticamente como fuera de horario.
        </p>
      </div>
    </div>
  );
};
