import api from '../../utils/api';
import { fmt } from './constants';

export const UsdtLedgerPanel = ({
  usdtLedger, setUsdtLedger, usdtLedgerPage, setUsdtLedgerPage,
  activeRoute, routeLabel
}) => {
  const changePage = async (p) => {
    setUsdtLedgerPage(p);
    const res = await api.get(`/admin/accounting/usdt-ledger?route=${activeRoute}&page=${p}`);
    setUsdtLedger(res.data);
  };

  return (
    <div style={{ backgroundColor: '#e0f2fe', border: '1px solid #7dd3fc', borderRadius: '14px', padding: '16px', marginBottom: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h4 style={{ fontSize: '15px', fontWeight: '700', color: '#0c4a6e', margin: 0 }}>
          Libro USDT ({routeLabel}) - Saldo: <span style={{ color: '#0369a1' }}>{fmt(usdtLedger.balance)} USDT</span>
        </h4>
      </div>
      {usdtLedger.entries.length > 0 ? (
        <>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', backgroundColor: '#fff', borderRadius: '8px', overflow: 'hidden' }}>
            <thead>
              <tr style={{ backgroundColor: '#0369a1' }}>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'left' }}>Fecha</th>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'center' }}>Tipo</th>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'left' }}>Concepto</th>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'right' }}>Tasa</th>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'right' }}>Entrada USDT</th>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'right' }}>Salida USDT</th>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'right' }}>Total Fiat</th>
                <th style={{ padding: '8px', color: '#fff', textAlign: 'right' }}>Saldo USDT</th>
              </tr>
            </thead>
            <tbody>
              {usdtLedger.entries.map((e, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #e0f2fe' }}>
                  <td style={{ padding: '8px', color: '#6b7280' }}>{e.date}</td>
                  <td style={{ padding: '8px', textAlign: 'center' }}>
                    <span style={{ padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600', backgroundColor: e.type === 'entrada' ? '#dcfce7' : '#fef2f2', color: e.type === 'entrada' ? '#16a34a' : '#dc2626' }}>
                      {e.type === 'entrada' ? 'COMPRA' : 'VENTA'}
                    </span>
                  </td>
                  <td style={{ padding: '8px', color: '#374151', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.concept}</td>
                  <td style={{ padding: '8px', textAlign: 'right', color: '#6b7280' }}>{fmt(e.rate, 4)}</td>
                  <td style={{ padding: '8px', textAlign: 'right', color: '#16a34a', fontWeight: '600' }}>
                    {e.type === 'entrada' ? `+${fmt(e.amount_usdt)}` : ''}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: '#dc2626', fontWeight: '600' }}>
                    {e.type === 'salida' ? `-${fmt(e.amount_usdt)}` : ''}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: '#6b7280' }}>{fmt(e.total_fiat)}</td>
                  <td style={{ padding: '8px', textAlign: 'right', fontWeight: '700', color: '#0c4a6e' }}>{fmt(e.balance_after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {usdtLedger.pages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '10px' }}>
              <button disabled={usdtLedgerPage === 1} onClick={() => changePage(usdtLedgerPage - 1)}
                style={{ padding: '6px 12px', borderRadius: '8px', border: '1px solid #7dd3fc', cursor: 'pointer', fontSize: '12px' }}>Anterior</button>
              <span style={{ padding: '6px', fontSize: '12px', color: '#0c4a6e' }}>{usdtLedgerPage} / {usdtLedger.pages}</span>
              <button disabled={usdtLedgerPage === usdtLedger.pages} onClick={() => changePage(usdtLedgerPage + 1)}
                style={{ padding: '6px 12px', borderRadius: '8px', border: '1px solid #7dd3fc', cursor: 'pointer', fontSize: '12px' }}>Siguiente</button>
            </div>
          )}
        </>
      ) : (
        <p style={{ textAlign: 'center', color: '#0c4a6e', fontSize: '13px', padding: '16px 0' }}>No hay movimientos de USDT registrados</p>
      )}
    </div>
  );
};
