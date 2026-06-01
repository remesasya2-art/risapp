import { RefreshCw, FileSpreadsheet } from 'lucide-react';
import { fmt } from './constants';

export const ReportTable = ({ report, loading }) => {
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '40px' }}>
        <RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} />
      </div>
    );
  }

  if (!report) return null;

  return (
    <>
      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '20px' }}>
        <div style={{ backgroundColor: '#fff', borderRadius: '14px', padding: '16px', border: '1px solid #e5e7eb' }}>
          <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Transacciones</p>
          <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>{report.total_transactions}</p>
        </div>
        <div style={{ backgroundColor: '#fff', borderRadius: '14px', padding: '16px', border: '1px solid #e5e7eb' }}>
          <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Ganancia USDT</p>
          <p style={{ fontSize: '24px', fontWeight: '700', color: report.total_ganancia_usdt >= 0 ? '#16a34a' : '#dc2626', margin: 0 }}>
            ${fmt(report.total_ganancia_usdt)}
          </p>
        </div>
        <div style={{ backgroundColor: '#fff', borderRadius: '14px', padding: '16px', border: '1px solid #e5e7eb' }}>
          <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Periodo</p>
          <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{report.start_date} - {report.end_date}</p>
        </div>
      </div>

      {/* Report Table */}
      {report.rows.length > 0 ? (
        <div style={{ backgroundColor: '#fff', borderRadius: '14px', border: '1px solid #e5e7eb', overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#4caf50' }}>
                {['#', 'Fecha', 'ID', 'Cliente', 'Ruta', 'Valor TX', 'Moneda', 'Tasa Dia', 'Cant. Entregar', 'Tasa Compra', 'USDT Comprados', 'Pais', 'USDT Vendidos', 'Tasa Venta', 'Total Entregado', 'Ganancia USDT'].map((h, i) => (
                  <th key={i} style={{ padding: '10px 6px', color: '#fff', fontWeight: '600', textAlign: 'center', whiteSpace: 'nowrap', borderBottom: '2px solid #388e3c' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row, idx) => (
                <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? '#f1f8e9' : '#e8f5e9' }}>
                  <td style={{ padding: '8px 6px', textAlign: 'center', fontWeight: '600' }}>{idx + 1}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'center' }}>{row.fecha}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'center', fontWeight: '600' }}>{row.id_usuario}</td>
                  <td style={{ padding: '8px 6px', whiteSpace: 'nowrap' }}>{row.cliente}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'center', backgroundColor: '#2e7d32', color: '#fff', fontWeight: '600' }}>{row.ruta_remesa}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right', fontWeight: '500' }}>{fmt(row.valor_transaccion)}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'center', backgroundColor: '#2e7d32', color: '#fff', fontWeight: '600' }}>{row.moneda}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right' }}>{fmt(row.tasa_dia)}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right', fontWeight: '500' }}>{fmt(row.cantidad_entregar)}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right' }}>{row.tasa_compra}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right', fontWeight: '500' }}>{fmt(row.usdt_comprados)}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'center', backgroundColor: '#ffff00', fontWeight: '600' }}>{row.pais_destino}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right', fontWeight: '500' }}>{fmt(row.usdt_vendidos)}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right' }}>{fmt(row.tasa_venta)}</td>
                  <td style={{ padding: '8px 6px', textAlign: 'right', fontWeight: '500' }}>{fmt(row.total_entregado)}</td>
                  <td style={{
                    padding: '8px 6px', textAlign: 'right', fontWeight: '700',
                    color: row.ganancia_usdt >= 0 ? '#2e7d32' : '#c62828'
                  }}>${fmt(row.ganancia_usdt)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ backgroundColor: '#1b5e20' }}>
                <td colSpan={15} style={{ padding: '10px', color: '#fff', fontWeight: '700', textAlign: 'right', fontSize: '13px' }}>
                  TOTAL GANANCIA ({report.rows.length} transacciones)
                </td>
                <td style={{ padding: '10px', color: '#fff', fontWeight: '700', textAlign: 'right', fontSize: '14px' }}>
                  ${fmt(report.total_ganancia_usdt)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '60px', backgroundColor: '#fff', borderRadius: '14px', border: '1px solid #e5e7eb' }}>
          <FileSpreadsheet style={{ width: '48px', height: '48px', color: '#d1d5db', margin: '0 auto 12px' }} />
          <p style={{ fontSize: '16px', fontWeight: '500', color: '#6b7280' }}>No hay transacciones para este periodo</p>
          <p style={{ fontSize: '13px', color: '#9ca3af' }}>Selecciona otro rango de fechas</p>
        </div>
      )}
    </>
  );
};
