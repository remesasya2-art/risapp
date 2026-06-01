import toast from 'react-hot-toast';
import { Trash2 } from 'lucide-react';
import api from '../../utils/api';
import { fmt, VES_BANKS, BRL_BANKS } from './constants';

export const BankManager = ({
  banks, newBank, setNewBank,
  selectedBank, setSelectedBank,
  ledger, setLedger, ledgerPage, setLedgerPage,
  manualEntry, setManualEntry,
  selectedDate, addBank, deleteBank, loadBanks
}) => {
  const submitManualEntry = async () => {
    if (!manualEntry.amount || !manualEntry.concept) { toast.error('Monto y concepto requeridos'); return; }
    try {
      await api.post('/admin/accounting/banks/ledger/manual', {
        bank_id: selectedBank.bank_id, type: manualEntry.type,
        amount: parseFloat(manualEntry.amount), concept: manualEntry.concept,
        date: selectedDate, notes: manualEntry.notes
      });
      toast.success('Movimiento registrado');
      setManualEntry({ type: 'salida', amount: '', concept: '', notes: '' });
      loadBanks();
      const res = await api.get(`/admin/accounting/banks/${selectedBank.bank_id}/ledger?page=1`);
      setLedger(res.data);
      setSelectedBank(res.data.bank);
    } catch (e) { toast.error(e.response?.data?.detail || 'Error'); }
  };

  const changePage = async (p) => {
    setLedgerPage(p);
    const res = await api.get(`/admin/accounting/banks/${selectedBank.bank_id}/ledger?page=${p}`);
    setLedger(res.data);
  };

  return (
    <div style={{ backgroundColor: '#f5f3ff', border: '1px solid #c4b5fd', borderRadius: '14px', padding: '16px', marginBottom: '16px' }}>
      <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#5b21b6', margin: '0 0 12px 0' }}>Bancos Registrados</h4>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
        {banks.map(b => (
          <div key={b.bank_id} style={{
            padding: '8px 14px', borderRadius: '10px', border: selectedBank?.bank_id === b.bank_id ? '2px solid #7c3aed' : '1px solid #e5e7eb',
            backgroundColor: selectedBank?.bank_id === b.bank_id ? '#ede9fe' : '#fff', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer'
          }} onClick={async () => {
            setSelectedBank(b);
            setLedgerPage(1);
            try {
              const res = await api.get(`/admin/accounting/banks/${b.bank_id}/ledger?page=1`);
              setLedger(res.data);
            } catch (e) { console.error(e); }
          }}>
            <span style={{ fontSize: '13px', fontWeight: '600' }}>{b.name}</span>
            <span style={{ fontSize: '12px', color: '#16a34a', fontWeight: '700' }}>{fmt(b.balance)} {b.currency}</span>
            <button onClick={(e) => { e.stopPropagation(); deleteBank(b.bank_id); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px' }}>
              <Trash2 style={{ width: '14px', height: '14px', color: '#dc2626' }} />
            </button>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <input type="text" placeholder="Nombre del banco" value={newBank.name} onChange={e => setNewBank(n => ({ ...n, name: e.target.value }))}
          list="bank-suggestions"
          style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', flex: 1 }} data-testid="bank-name-input"
        />
        <datalist id="bank-suggestions">
          {(newBank.currency === 'VES' ? VES_BANKS : BRL_BANKS).map(name => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <select value={newBank.currency} onChange={e => setNewBank(n => ({ ...n, currency: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px' }}
          data-testid="bank-currency-select"
        >
          <option value="VES">VES (Bolivares)</option>
          <option value="BRL">BRL (Reais)</option>
        </select>
        <input type="number" placeholder="Saldo inicial" value={newBank.initial_balance || ''} onChange={e => setNewBank(n => ({ ...n, initial_balance: parseFloat(e.target.value) || 0 }))}
          style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '120px' }}
        />
        <button onClick={addBank}
          style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', backgroundColor: '#7c3aed', color: '#fff', fontSize: '13px', fontWeight: '600', cursor: 'pointer' }}
          data-testid="add-bank-btn"
        >Agregar</button>
      </div>

      {selectedBank && (
        <div style={{ backgroundColor: '#fff', borderRadius: '12px', padding: '16px', border: '1px solid #e5e7eb' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <h5 style={{ fontSize: '14px', fontWeight: '700', color: '#111827', margin: 0 }}>
              Libro Diario - {selectedBank.name} (Saldo: {fmt(selectedBank.balance)} {selectedBank.currency})
            </h5>
            <button onClick={() => setSelectedBank(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '18px', color: '#6b7280' }}>X</button>
          </div>

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px', padding: '10px', backgroundColor: '#f9fafb', borderRadius: '8px' }}>
            <select value={manualEntry.type} onChange={e => setManualEntry(m => ({ ...m, type: e.target.value }))}
              style={{ padding: '8px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '13px' }}
              data-testid="manual-entry-type"
            >
              <option value="entrada">Entrada</option>
              <option value="salida">Salida</option>
            </select>
            <input type="number" step="0.01" placeholder="Monto" value={manualEntry.amount}
              onChange={e => setManualEntry(m => ({ ...m, amount: e.target.value }))}
              style={{ padding: '8px', borderRadius: '8px', border: '1px solid #d1d5db', width: '120px', fontSize: '13px' }}
              data-testid="manual-entry-amount"
            />
            <input type="text" placeholder="Concepto (ej: Pago beneficiario Juan)" value={manualEntry.concept}
              onChange={e => setManualEntry(m => ({ ...m, concept: e.target.value }))}
              style={{ padding: '8px', borderRadius: '8px', border: '1px solid #d1d5db', flex: 1, fontSize: '13px' }}
              data-testid="manual-entry-concept"
            />
            <button onClick={submitManualEntry}
              style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', backgroundColor: '#374151', color: '#fff', fontSize: '13px', fontWeight: '600', cursor: 'pointer' }}
              data-testid="manual-entry-submit"
            >Registrar</button>
          </div>

          {ledger.entries.length > 0 ? (
            <>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f3f4f6' }}>
                    <th style={{ padding: '8px', textAlign: 'left', fontWeight: '600', color: '#374151' }}>Fecha</th>
                    <th style={{ padding: '8px', textAlign: 'center', fontWeight: '600', color: '#374151' }}>Tipo</th>
                    <th style={{ padding: '8px', textAlign: 'left', fontWeight: '600', color: '#374151' }}>Concepto</th>
                    <th style={{ padding: '8px', textAlign: 'right', fontWeight: '600', color: '#374151' }}>Entrada</th>
                    <th style={{ padding: '8px', textAlign: 'right', fontWeight: '600', color: '#374151' }}>Salida</th>
                    <th style={{ padding: '8px', textAlign: 'right', fontWeight: '600', color: '#374151' }}>Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.entries.map((entry, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '8px', color: '#6b7280' }}>{entry.date}</td>
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600',
                          backgroundColor: entry.type === 'entrada' ? '#dcfce7' : '#fef2f2',
                          color: entry.type === 'entrada' ? '#16a34a' : '#dc2626'
                        }}>{entry.type === 'entrada' ? 'ENTRADA' : 'SALIDA'}</span>
                      </td>
                      <td style={{ padding: '8px', color: '#374151', maxWidth: '250px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.concept}</td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#16a34a', fontWeight: '600' }}>
                        {entry.type === 'entrada' ? `+${fmt(entry.amount)}` : ''}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#dc2626', fontWeight: '600' }}>
                        {entry.type === 'salida' ? `-${fmt(entry.amount)}` : ''}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontWeight: '700', color: '#111827' }}>
                        {fmt(entry.balance_after)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {ledger.pages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '10px' }}>
                  <button disabled={ledgerPage === 1} onClick={() => changePage(ledgerPage - 1)}
                    style={{ padding: '6px 12px', borderRadius: '8px', border: '1px solid #d1d5db', cursor: 'pointer', fontSize: '12px' }}>Anterior</button>
                  <span style={{ padding: '6px', fontSize: '12px', color: '#6b7280' }}>{ledgerPage} / {ledger.pages}</span>
                  <button disabled={ledgerPage === ledger.pages} onClick={() => changePage(ledgerPage + 1)}
                    style={{ padding: '6px 12px', borderRadius: '8px', border: '1px solid #d1d5db', cursor: 'pointer', fontSize: '12px' }}>Siguiente</button>
                </div>
              )}
            </>
          ) : (
            <p style={{ textAlign: 'center', color: '#9ca3af', fontSize: '13px', padding: '20px 0' }}>No hay movimientos registrados</p>
          )}
        </div>
      )}
    </div>
  );
};
