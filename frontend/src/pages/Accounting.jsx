import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import toast from 'react-hot-toast';
import api from '../utils/api';
import {
  ArrowLeft, TrendingUp, DollarSign, Building, FileSpreadsheet
} from 'lucide-react';
import { BuySellForms } from '../components/accounting/BuySellForms';
import { BankManager } from '../components/accounting/BankManager';
import { UsdtLedgerPanel } from '../components/accounting/UsdtLedgerPanel';
import { ReportTable } from '../components/accounting/ReportTable';
import { WipeButton } from '../components/common/WipeButton';
import { RestoreButton } from '../components/common/RestoreButton';

export default function Accounting() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeRoute, setActiveRoute] = useState('brl_ves');
  const [period, setPeriod] = useState('day');
  const getLocalDate = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const [selectedDate, setSelectedDate] = useState(getLocalDate());
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [banks, setBanks] = useState([]);
  const [showRateForm, setShowRateForm] = useState(false);
  const [showBankForm, setShowBankForm] = useState(false);
  const [newBank, setNewBank] = useState({ name: '', currency: 'VES', initial_balance: 0 });
  const [exporting, setExporting] = useState(false);
  const [buyForm, setBuyForm] = useState({ amount_fiat: '', rate: '', bank_id: '', provider: '' });
  const [sellForm, setSellForm] = useState({ amount_fiat: '', rate: '', bank_id: '', provider: '' });
  const [recentOps, setRecentOps] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [selectedBank, setSelectedBank] = useState(null);
  const [ledger, setLedger] = useState({ entries: [], total: 0, pages: 1 });
  const [ledgerPage, setLedgerPage] = useState(1);
  const [manualEntry, setManualEntry] = useState({ type: 'salida', amount: '', concept: '', notes: '' });
  const [usdtLedger, setUsdtLedger] = useState({ balance: 0, entries: [], total: 0, pages: 1 });
  const [usdtLedgerPage, setUsdtLedgerPage] = useState(1);
  const [showUsdtLedger, setShowUsdtLedger] = useState(false);

  useEffect(() => { loadReport(); loadBanks(); loadOps(); loadUsdtLedger(); }, [activeRoute, period, selectedDate]);

  const loadReport = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/accounting/report?route=${activeRoute}&period=${period}&date=${selectedDate}`);
      setReport(res.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const loadBanks = async () => {
    try {
      const res = await api.get('/admin/accounting/banks');
      setBanks(res.data || []);
    } catch (e) { console.error(e); }
  };

  const loadOps = async () => {
    try {
      const res = await api.get(`/admin/accounting/operations?route=${activeRoute}&limit=10`);
      setRecentOps(res.data || []);
    } catch (e) { console.error(e); }
  };

  const loadUsdtLedger = async () => {
    try {
      const res = await api.get(`/admin/accounting/usdt-ledger?route=${activeRoute}&page=${usdtLedgerPage}`);
      setUsdtLedger(res.data || { balance: 0, entries: [], total: 0, pages: 1 });
    } catch (e) { console.error(e); }
  };

  const registerBuy = async () => {
    if (!buyForm.amount_fiat || !buyForm.rate) { toast.error('Completa monto y tasa de compra'); return; }
    if (!buyForm.bank_id) { toast.error('Selecciona el banco origen'); return; }
    const rate = parseFloat(buyForm.rate);
    const usdt = parseFloat(buyForm.amount_fiat) / rate;
    setSubmitting(true);
    try {
      await api.post('/admin/accounting/operations', {
        date: selectedDate, route: activeRoute, operation_type: 'buy',
        amount_usdt: parseFloat(usdt.toFixed(2)), rate,
        bank_id: buyForm.bank_id, notes: buyForm.provider ? `Proveedor: ${buyForm.provider}` : ''
      });
      toast.success(`Compra registrada: ${usdt.toFixed(2)} USDT`);
      setBuyForm({ amount_fiat: '', rate: '', bank_id: '', provider: '' });
      loadOps(); loadBanks(); loadUsdtLedger();
    } catch (e) { toast.error(e.response?.data?.detail || 'Error al registrar'); }
    finally { setSubmitting(false); }
  };

  const registerSell = async () => {
    if (!sellForm.amount_fiat || !sellForm.rate) { toast.error('Completa monto recibido y tasa de venta'); return; }
    if (!sellForm.bank_id) { toast.error('Selecciona el banco receptor'); return; }
    const rate = parseFloat(sellForm.rate);
    const usdt = parseFloat(sellForm.amount_fiat) / rate;
    setSubmitting(true);
    try {
      await api.post('/admin/accounting/operations', {
        date: selectedDate, route: activeRoute, operation_type: 'sell',
        amount_usdt: parseFloat(usdt.toFixed(2)), rate,
        bank_id: sellForm.bank_id, notes: sellForm.provider ? `Proveedor: ${sellForm.provider}` : ''
      });
      toast.success(`Venta registrada: ${usdt.toFixed(2)} USDT vendidos`);
      setSellForm({ amount_fiat: '', rate: '', bank_id: '', provider: '' });
      loadOps(); loadBanks(); loadUsdtLedger();
    } catch (e) { toast.error(e.response?.data?.detail || 'Error al registrar'); }
    finally { setSubmitting(false); }
  };

  const addBank = async () => {
    if (!newBank.name) { toast.error('Nombre del banco requerido'); return; }
    try {
      await api.post('/admin/accounting/banks', newBank);
      toast.success('Banco agregado');
      setNewBank({ name: '', currency: newBank.currency, initial_balance: 0 });
      loadBanks();
    } catch (e) { toast.error('Error al agregar banco'); }
  };

  const deleteBank = async (bankId) => {
    if (!confirm('Eliminar este banco?')) return;
    try { await api.delete(`/admin/accounting/banks/${bankId}`); loadBanks(); } catch (e) { toast.error('Error'); }
  };

  const exportExcel = async () => {
    setExporting(true);
    try {
      const res = await api.get(`/admin/accounting/export?route=${activeRoute}&period=${period}&date=${selectedDate}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url;
      a.download = `Reporte_${activeRoute === 'brl_ves' ? 'BRL_a_VES' : 'VES_a_BRL'}.xlsx`;
      a.click(); window.URL.revokeObjectURL(url);
      toast.success('Excel descargado');
    } catch (e) { toast.error('Error al exportar'); }
    finally { setExporting(false); }
  };

  const routeLabel = activeRoute === 'brl_ves' ? 'BRL -> VES' : 'VES -> BRL';
  const currencyTarget = activeRoute === 'brl_ves' ? 'VES' : 'BRL';

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8f9fc', padding: '16px' }} data-testid="accounting-page">
      <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
          <button onClick={() => navigate('/admin')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }}>
            <ArrowLeft style={{ width: '24px', height: '24px', color: '#374151' }} />
          </button>
          <div>
            <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Contabilidad</h1>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Reportes financieros y control de liquidez</p>
          </div>
        </div>

        {/* Route Tabs */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
          {[
            { key: 'brl_ves', label: 'BRL -> VES', color: '#2563eb' },
            { key: 'ves_brl', label: 'VES -> BRL', color: '#059669' }
          ].map(tab => (
            <button key={tab.key} onClick={() => setActiveRoute(tab.key)}
              style={{
                padding: '10px 24px', borderRadius: '12px', border: 'none', fontSize: '14px', fontWeight: '600',
                cursor: 'pointer', transition: 'all 0.2s',
                backgroundColor: activeRoute === tab.key ? tab.color : '#f3f4f6',
                color: activeRoute === tab.key ? '#fff' : '#6b7280'
              }}
              data-testid={`route-tab-${tab.key}`}
            >{tab.label}</button>
          ))}
        </div>

        {/* Controls Row */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '20px', alignItems: 'center' }}>
          <select value={period} onChange={e => setPeriod(e.target.value)}
            style={{ padding: '10px 14px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '14px', backgroundColor: '#fff' }}
            data-testid="period-select"
          >
            <option value="day">Dia</option>
            <option value="week">Semana</option>
            <option value="biweekly">Quincenal</option>
            <option value="month">Mes</option>
            <option value="year">Anio</option>
          </select>
          <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)}
            style={{ padding: '10px 14px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '14px' }}
            data-testid="date-input"
          />
          <button onClick={() => setShowRateForm(!showRateForm)}
            style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: '#f59e0b', color: '#fff', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
            data-testid="set-rates-btn"
          >
            <DollarSign style={{ width: '16px', height: '16px' }} /> Registro Compra/Venta USDT
          </button>
          <button onClick={() => { setShowBankForm(!showBankForm); setNewBank(n => ({ ...n, currency: currencyTarget })); }}
            style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: '#8b5cf6', color: '#fff', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
            data-testid="manage-banks-btn"
          >
            <Building style={{ width: '16px', height: '16px' }} /> Bancos
          </button>
          <button onClick={() => { setShowUsdtLedger(!showUsdtLedger); loadUsdtLedger(); }}
            style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: '#0ea5e9', color: '#fff', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
            data-testid="usdt-ledger-btn"
          >
            <TrendingUp style={{ width: '16px', height: '16px' }} /> Libro USDT
          </button>
          <button onClick={exportExcel} disabled={exporting}
            style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: '#16a34a', color: '#fff', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', marginLeft: 'auto', opacity: exporting ? 0.6 : 1 }}
            data-testid="export-excel-btn"
          >
            <FileSpreadsheet style={{ width: '16px', height: '16px' }} /> {exporting ? 'Exportando...' : 'Exportar Excel'}
          </button>
          <WipeButton
            mode="accounting"
            userRole={user?.role}
            onSuccess={() => { loadReport(); loadBanks(); loadOps(); loadUsdtLedger(); }}
          />
          <RestoreButton
            userRole={user?.role}
            onSuccess={() => { loadReport(); loadBanks(); loadOps(); loadUsdtLedger(); }}
          />
        </div>

        {showRateForm && (
          <BuySellForms
            activeRoute={activeRoute}
            buyForm={buyForm} setBuyForm={setBuyForm}
            sellForm={sellForm} setSellForm={setSellForm}
            banks={banks} recentOps={recentOps}
            submitting={submitting}
            registerBuy={registerBuy} registerSell={registerSell}
          />
        )}

        {showBankForm && (
          <BankManager
            banks={banks} newBank={newBank} setNewBank={setNewBank}
            selectedBank={selectedBank} setSelectedBank={setSelectedBank}
            ledger={ledger} setLedger={setLedger}
            ledgerPage={ledgerPage} setLedgerPage={setLedgerPage}
            manualEntry={manualEntry} setManualEntry={setManualEntry}
            selectedDate={selectedDate}
            addBank={addBank} deleteBank={deleteBank} loadBanks={loadBanks}
          />
        )}

        {showUsdtLedger && (
          <UsdtLedgerPanel
            usdtLedger={usdtLedger} setUsdtLedger={setUsdtLedger}
            usdtLedgerPage={usdtLedgerPage} setUsdtLedgerPage={setUsdtLedgerPage}
            activeRoute={activeRoute} routeLabel={routeLabel}
          />
        )}

        <ReportTable report={report} loading={loading} />
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
