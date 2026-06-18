import { useState } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { Download, FileText, Calendar } from 'lucide-react';

const PERIODOS = [
  { key: 'day', label: 'Día' },
  { key: 'month', label: 'Mes' },
  { key: 'year', label: 'Año' },
];

export default function ReportesProcesados() {
  const hoy = new Date().toISOString().slice(0, 10);
  const [period, setPeriod] = useState('day');
  const [date, setDate] = useState(hoy);
  const [loading, setLoading] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const [data, setData] = useState(null);

  const generar = async () => {
    setLoading(true);
    setData(null);
    try {
      const res = await api.get('/admin/reportes/procesados', { params: { period, date, formato: 'json' } });
      setData(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo generar el reporte');
    } finally {
      setLoading(false);
    }
  };

  const descargarCSV = async () => {
    setDescargando(true);
    try {
      const res = await api.get('/admin/reportes/procesados', {
        params: { period, date, formato: 'csv' },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `reporte_${period}_${date}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('No se pudo descargar el CSV');
    } finally {
      setDescargando(false);
    }
  };

  const inputStyle = {
    padding: '10px 12px', borderRadius: '10px', border: '1px solid #e5e7eb',
    fontSize: '14px', boxSizing: 'border-box',
  };

  return (
    <div>
      <div style={{ marginBottom: '16px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', margin: 0 }}>Reportes de procesados</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
          Todo lo procesado (BTC→VES, RIS→VES, VES→RIS, RIS→Reais) por día, mes o año. Exportable a CSV.
        </p>
      </div>

      {/* Controles */}
      <div style={{
        backgroundColor: '#fff', borderRadius: '14px', padding: '16px',
        border: '1px solid #eef0f4', marginBottom: '16px',
        display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'flex-end',
      }}>
        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>Período</label>
          <div style={{ display: 'inline-flex', borderRadius: '10px', border: '1px solid #e5e7eb', overflow: 'hidden' }}>
            {PERIODOS.map((p) => (
              <button key={p.key} onClick={() => setPeriod(p.key)} style={{
                padding: '10px 16px', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '14px',
                backgroundColor: period === p.key ? '#6366f1' : '#fff',
                color: period === p.key ? '#fff' : '#374151',
              }}>{p.label}</button>
            ))}
          </div>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
            <Calendar size={12} style={{ verticalAlign: 'middle' }} /> Fecha dentro del período
          </label>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} style={inputStyle} />
        </div>
        <button onClick={generar} disabled={loading} style={{
          padding: '10px 18px', borderRadius: '10px', border: 'none', cursor: 'pointer',
          backgroundColor: '#6366f1', color: '#fff', fontWeight: 700, fontSize: '14px',
          display: 'inline-flex', alignItems: 'center', gap: '6px',
        }}>
          <FileText size={16} /> {loading ? 'Generando…' : 'Generar'}
        </button>
        <button onClick={descargarCSV} disabled={descargando} style={{
          padding: '10px 18px', borderRadius: '10px', cursor: 'pointer',
          backgroundColor: '#fff', color: '#059669', border: '1.5px solid #059669', fontWeight: 700, fontSize: '14px',
          display: 'inline-flex', alignItems: 'center', gap: '6px',
        }}>
          <Download size={16} /> {descargando ? 'Descargando…' : 'Descargar CSV'}
        </button>
      </div>

      {/* Resultado */}
      {data && (
        <div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '14px' }}>
            <div style={{
              padding: '12px 16px', borderRadius: '12px', backgroundColor: '#EEF2FF',
              color: '#4F46E5', fontWeight: 700,
            }}>
              Total procesado: {data.total}
            </div>
            {Object.entries(data.totales_por_flujo || {}).map(([flujo, n]) => (
              <div key={flujo} style={{
                padding: '12px 16px', borderRadius: '12px', backgroundColor: '#F3F4F6', color: '#374151', fontWeight: 600,
              }}>{flujo}: {n}</div>
            ))}
          </div>

          {data.total === 0 ? (
            <p style={{ color: '#9ca3af' }}>No hay órdenes procesadas en este período.</p>
          ) : (
            <div style={{ overflowX: 'auto', border: '1px solid #eef0f4', borderRadius: '12px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ backgroundColor: '#F9FAFB', textAlign: 'left' }}>
                    {['Fecha', 'Flujo', 'Ref.', 'Usuario', 'Beneficiario', 'Origen', 'Destino', 'Procesó'].map((h) => (
                      <th key={h} style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i} style={{ borderTop: '1px solid #f1f2f6' }}>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', color: '#6b7280' }}>{r.fecha_procesado}</td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', fontWeight: 600, color: '#111827' }}>{r.flujo}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{r.referencia}</td>
                      <td style={{ padding: '10px 12px' }}>{r.usuario}</td>
                      <td style={{ padding: '10px 12px' }}>{r.beneficiario || '—'}</td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>{r.monto_origen} {r.unidad_origen}</td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>{r.monto_destino} {r.unidad_destino}</td>
                      <td style={{ padding: '10px 12px', color: '#9ca3af', whiteSpace: 'nowrap' }}>{r.procesado_por || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
