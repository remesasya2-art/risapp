import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, TrendingUp, Wallet, DollarSign, Package, ScrollText, Activity,
  AlertCircle, CheckCircle, RefreshCw, Plus, X,
} from 'lucide-react';
import api from '../utils/api';
import { fmt } from '../utils/format';
import toast from 'react-hot-toast';

// ─────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────
const todayStr = () => {
  const d = new Date();
  // Caracas tz adjustment
  const carDate = new Date(d.getTime() - 4 * 3600 * 1000);
  return carDate.toISOString().slice(0, 10);
};
const daysAgoStr = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return new Date(d.getTime() - 4 * 3600 * 1000).toISOString().slice(0, 10);
};

const COLOR = {
  bg: '#f9fafb',
  card: '#ffffff',
  border: '#e5e7eb',
  text: '#111827',
  muted: '#6b7280',
  brand: '#4f46e5',
  good: '#16a34a',
  bad: '#dc2626',
  warn: '#d97706',
  info: '#0284c7',
};

// ─────────────────────────────────────────
// Reusable bits
// ─────────────────────────────────────────
function MetricCard({ icon: Icon, title, value, sub, tone = 'default', testId }) {
  const accent = {
    default: '#6366f1', good: COLOR.good, bad: COLOR.bad, warn: COLOR.warn, info: COLOR.info,
  }[tone];
  return (
    <div style={S.metricCard} data-testid={testId}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, color: COLOR.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>{title}</span>
        {Icon && <Icon size={18} color={accent} />}
      </div>
      <div style={{ fontSize: 24, fontWeight: 800, color: COLOR.text, marginTop: 8 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: COLOR.muted, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function Section({ title, children, action }) {
  return (
    <div style={S.section}>
      <div style={S.sectionHeader}>
        <h3 style={S.sectionTitle}>{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

function DateRange({ start, end, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <label style={S.label}>Desde</label>
      <input type="date" value={start} onChange={(e) => onChange(e.target.value, end)} style={S.dateInput} data-testid="acc-v2-date-start" />
      <label style={S.label}>Hasta</label>
      <input type="date" value={end} onChange={(e) => onChange(start, e.target.value)} style={S.dateInput} data-testid="acc-v2-date-end" />
    </div>
  );
}

// ─────────────────────────────────────────
// TAB 1 — Resumen Ejecutivo
// ─────────────────────────────────────────
function ExecutiveSummary({ start, end, onRange }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/accounting/v2/executive-report?start=${start}&end=${end}`);
      setData(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error al cargar reporte');
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  useEffect(() => { void load(); }, [load]);

  if (loading || !data) {
    return <div style={S.loadingBox}><RefreshCw className="anim-spin" size={20} /> Cargando reporte...</div>;
  }

  const L = data.liabilities, A = data.corporate_liquidity, P = data.arbitrage_performance, G = data.gateway_operational_expenses, B = data.local_bank_expenses;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <DateRange start={start} end={end} onChange={onRange} />

      <Section title="🏦 Pasivos (lo que la empresa debe)">
        <div style={S.grid3}>
          <MetricCard icon={Wallet} title="RIS en circulación" value={`${fmt(L.circulation_ris)} RI$`} sub="Saldo activo de todos los usuarios" testId="acc-v2-liab-ris" />
          <MetricCard icon={Activity} title="Retiros pendientes" value={`${fmt(L.escrow_withdrawing_ves)} VES`} sub="Comprometidos en bancos VE" tone="warn" />
          <MetricCard icon={DollarSign} title="Pasivo total ajustado" value={`${fmt(L.total_adjusted_liability_ves)} VES`} sub="Valorado a tasa interna" tone="bad" />
        </div>
      </Section>

      <Section title="💰 Liquidez corporativa (saldos en bancos)">
        <div style={S.grid2}>
          <MetricCard icon={Wallet} title="Disponible VES" value={`${fmt(A.available_ves)} VES`} sub="Suma de bancos Venezuela" tone="info" />
          <MetricCard icon={Wallet} title="Disponible BRL" value={`R$ ${fmt(A.available_brl)}`} sub="Suma de bancos Brasil" tone="info" />
        </div>
      </Section>

      <Section title="📊 Mesa de arbitraje P2P">
        <div style={S.grid3}>
          <MetricCard icon={Package} title="Volumen vendido" value={`${fmt(P.volume_usdt_sold)} USDT`} />
          <MetricCard icon={TrendingUp} title="Ganancia bruta" value={`${fmt(P.gross_profit_usdt_p2p)} USDT`} tone="good" />
          <MetricCard icon={DollarSign} title="Fees pasarela (USDT eq.)" value={`${fmt(P.gateway_fees_usdt_equivalent)} USDT`} tone="warn" />
        </div>
        <div style={{ ...S.grid2, marginTop: 12 }}>
          <MetricCard icon={CheckCircle} title="GANANCIA NETA REAL" value={`${fmt(P.real_net_profit_usdt)} USDT`} sub="Después de comisiones pasarela" tone={P.real_net_profit_usdt >= 0 ? 'good' : 'bad'} testId="acc-v2-real-profit" />
          <MetricCard icon={Activity} title="ROI ponderado real" value={P.weighted_net_real_roi} sub={`ROI promedio simple: ${P.simple_average_roi}`} tone="good" />
        </div>
      </Section>

      <Section title="💳 Comisiones de pasarela">
        <div style={S.grid3}>
          <MetricCard icon={Activity} title="Volumen procesado" value={`R$ ${fmt(G.total_volume_processed_brl)}`} />
          <MetricCard icon={X} title="Fees pagadas" value={`R$ ${fmt(G.total_fees_paid_brl)}`} tone="bad" />
          <MetricCard icon={CheckCircle} title="Eficiencia real" value={G.real_fiat_efficiency_percentage} sub="Bruto → Neto al banco" tone="good" />
        </div>
        {G.total_fees_paid_by_currency?.length > 0 && (
          <div style={{ marginTop: 12, padding: 12, backgroundColor: COLOR.bg, borderRadius: 10, fontSize: 13 }}>
            <strong>Desglose multi-moneda:</strong>
            <ul style={{ margin: '6px 0 0 18px', color: COLOR.muted }}>
              {G.total_fees_paid_by_currency.map((c) => (
                <li key={c.currency}>{c.currency}: bruto {fmt(c.gross_volume)} • fees {fmt(c.fees_paid)}</li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      <Section title="🇻🇪 Gastos bancarios locales (Venezuela)">
        <MetricCard icon={DollarSign} title="Fees de retiros VES (IGTF + bancos)" value={`${fmt(B.total_withdrawal_outbound_fees_ves)} VES`} sub={B.audit_note} tone="warn" />
      </Section>

      <div style={S.footer}>
        Reporte generado en {data.reporting_timezone} · Rango: {data.filter_range.from.slice(0, 10)} → {data.filter_range.to.slice(0, 10)}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────
// TAB 2 — Inventario USDT
// ─────────────────────────────────────────
function UsdtInventory() {
  const [summary, setSummary] = useState(null);
  const [lots, setLots] = useState([]);
  const [onlyActive, setOnlyActive] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ initial_usdt: '', cost_per_usdt_brl: '', purchase_id: '' });

  const load = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        api.get('/admin/accounting/v2/usdt-inventory-summary'),
        api.get(`/admin/accounting/v2/usdt-lots?only_active=${onlyActive}`),
      ]);
      setSummary(s.data);
      setLots(l.data.lots);
    } catch (e) {
      toast.error('Error al cargar inventario');
    }
  }, [onlyActive]);

  useEffect(() => { void load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post('/admin/accounting/v2/usdt-lots', {
        initial_usdt: parseFloat(form.initial_usdt),
        cost_per_usdt_brl: parseFloat(form.cost_per_usdt_brl),
        purchase_id: form.purchase_id || null,
      });
      toast.success('Lote registrado');
      setShowForm(false);
      setForm({ initial_usdt: '', cost_per_usdt_brl: '', purchase_id: '' });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error al registrar lote');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {summary && (
        <div style={S.grid3}>
          <MetricCard icon={Package} title="USDT disponibles" value={`${fmt(summary.total_usdt_remaining)} USDT`} tone="info" testId="acc-v2-usdt-total" />
          <MetricCard icon={DollarSign} title="Costo total en BRL" value={`R$ ${fmt(summary.total_cost_brl_locked)}`} />
          <MetricCard icon={TrendingUp} title="Costo promedio" value={`R$ ${fmt(summary.weighted_avg_cost_brl_per_usdt, 4)} / USDT`} sub={`${summary.lots_count} lotes activos`} />
        </div>
      )}

      <Section title="Lotes FIFO" action={
        <div style={{ display: 'flex', gap: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <input type="checkbox" checked={onlyActive} onChange={(e) => setOnlyActive(e.target.checked)} /> Solo activos
          </label>
          <button onClick={() => setShowForm(!showForm)} style={S.primaryBtn} data-testid="acc-v2-add-lot-btn">
            <Plus size={14} /> Registrar lote
          </button>
        </div>
      }>
        {showForm && (
          <form onSubmit={submit} style={S.formBox}>
            <div style={S.grid3}>
              <div>
                <label style={S.label}>USDT comprados</label>
                <input type="number" step="0.01" required value={form.initial_usdt} onChange={(e) => setForm({ ...form, initial_usdt: e.target.value })} style={S.input} placeholder="100" />
              </div>
              <div>
                <label style={S.label}>Costo por USDT (BRL)</label>
                <input type="number" step="0.0001" required value={form.cost_per_usdt_brl} onChange={(e) => setForm({ ...form, cost_per_usdt_brl: e.target.value })} style={S.input} placeholder="5.20" />
              </div>
              <div>
                <label style={S.label}>ID compra (opcional)</label>
                <input type="text" value={form.purchase_id} onChange={(e) => setForm({ ...form, purchase_id: e.target.value })} style={S.input} placeholder="binance_p2p_42..." />
              </div>
            </div>
            <button type="submit" style={{ ...S.primaryBtn, marginTop: 12, width: '100%' }} data-testid="acc-v2-add-lot-submit">Guardar lote</button>
          </form>
        )}
        <table style={S.table}>
          <thead><tr>
            <th style={S.th}>Fecha</th><th style={S.th}>Compra ID</th><th style={S.th}>Inicial</th><th style={S.th}>Remanente</th><th style={S.th}>Costo/USDT</th><th style={S.th}>Estado</th>
          </tr></thead>
          <tbody>
            {lots.length === 0 ? <tr><td colSpan={6} style={S.empty}>Sin lotes registrados</td></tr> :
              lots.map((l, i) => (
                <tr key={i}>
                  <td style={S.td}>{l.created_at?.slice(0, 10)}</td>
                  <td style={S.td}>{l.purchase_id || '—'}</td>
                  <td style={S.td}>{fmt(l.initial_usdt)} USDT</td>
                  <td style={S.td}>{fmt(l.remaining_usdt)} USDT</td>
                  <td style={S.td}>R$ {fmt(l.cost_per_usdt_brl, 4)}</td>
                  <td style={S.td}>{l.is_exhausted ? <span style={S.tagBad}>Agotado</span> : <span style={S.tagGood}>Activo</span>}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}

// ─────────────────────────────────────────
// TAB 3 — Mesa P2P
// ─────────────────────────────────────────
function P2PMesa() {
  const [sales, setSales] = useState([]);
  const [banks, setBanks] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ amount_usdt_to_sell: '', amount_ves_received: '', bank_account_id: '' });

  const load = useCallback(async () => {
    try {
      const [s, b] = await Promise.all([
        api.get('/admin/accounting/v2/p2p-sales?limit=100'),
        api.get('/admin/accounting/banks?currency=VES'),
      ]);
      setSales(s.data.sales);
      setBanks(b.data);
    } catch (e) {
      toast.error('Error al cargar ventas P2P');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post('/admin/accounting/v2/p2p-sales', {
        amount_usdt_to_sell: parseFloat(form.amount_usdt_to_sell),
        amount_ves_received: parseFloat(form.amount_ves_received),
        bank_account_id: form.bank_account_id,
      });
      const profit = res.data.net_profit_usdt;
      toast.success(`Venta registrada — Ganancia: ${fmt(profit)} USDT (${fmt(res.data.profit_percentage)}%)`);
      setShowForm(false);
      setForm({ amount_usdt_to_sell: '', amount_ves_received: '', bank_account_id: '' });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error al ejecutar venta');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Section title="Operaciones P2P" action={
        <button onClick={() => setShowForm(!showForm)} style={S.primaryBtn} data-testid="acc-v2-add-sale-btn">
          <Plus size={14} /> Nueva venta P2P
        </button>
      }>
        {showForm && (
          <form onSubmit={submit} style={S.formBox}>
            <p style={{ fontSize: 13, color: COLOR.muted, margin: '0 0 12px 0' }}>El motor consumirá USDT de los lotes FIFO más antiguos automáticamente.</p>
            <div style={S.grid3}>
              <div>
                <label style={S.label}>USDT a vender</label>
                <input type="number" step="0.01" required value={form.amount_usdt_to_sell} onChange={(e) => setForm({ ...form, amount_usdt_to_sell: e.target.value })} style={S.input} placeholder="120" />
              </div>
              <div>
                <label style={S.label}>VES recibidos</label>
                <input type="number" step="0.01" required value={form.amount_ves_received} onChange={(e) => setForm({ ...form, amount_ves_received: e.target.value })} style={S.input} placeholder="60000" />
              </div>
              <div>
                <label style={S.label}>Acreditar en banco VES</label>
                <select required value={form.bank_account_id} onChange={(e) => setForm({ ...form, bank_account_id: e.target.value })} style={S.input}>
                  <option value="">— Seleccionar —</option>
                  {banks.map((b) => <option key={b.bank_id} value={b.bank_id}>{b.name} ({fmt(b.balance)} VES)</option>)}
                </select>
              </div>
            </div>
            <button type="submit" style={{ ...S.primaryBtn, marginTop: 12, width: '100%' }} data-testid="acc-v2-add-sale-submit">Ejecutar venta P2P</button>
          </form>
        )}
        <table style={S.table}>
          <thead><tr>
            <th style={S.th}>Fecha</th><th style={S.th}>USDT vendido</th><th style={S.th}>VES recibido</th><th style={S.th}>Tasa P2P</th><th style={S.th}>Costo FIFO</th><th style={S.th}>Ganancia</th><th style={S.th}>ROI</th>
          </tr></thead>
          <tbody>
            {sales.length === 0 ? <tr><td colSpan={7} style={S.empty}>Sin ventas registradas</td></tr> :
              sales.map((s) => (
                <tr key={s.sale_id}>
                  <td style={S.td}>{s.created_at?.slice(0, 16).replace('T', ' ')}</td>
                  <td style={S.td}>{fmt(s.usdt_amount)} USDT</td>
                  <td style={S.td}>{fmt(s.ves_received)} VES</td>
                  <td style={S.td}>{fmt(s.rate_sell_ves_usdt, 2)}</td>
                  <td style={S.td}>R$ {fmt(s.fifo_cost_brl)}</td>
                  <td style={S.td}><strong style={{ color: s.net_profit_usdt >= 0 ? COLOR.good : COLOR.bad }}>{fmt(s.net_profit_usdt)} USDT</strong></td>
                  <td style={S.td}><span style={s.profit_percentage >= 0 ? S.tagGood : S.tagBad}>{fmt(s.profit_percentage)}%</span></td>
                </tr>
              ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}

// ─────────────────────────────────────────
// TAB 4 — Auditoría
// ─────────────────────────────────────────
function AuditLog() {
  const [entries, setEntries] = useState([]);
  const [severity, setSeverity] = useState('');

  const load = useCallback(async () => {
    try {
      const q = severity ? `?severity=${severity}` : '';
      const { data } = await api.get(`/admin/accounting/v2/audit-log${q}`);
      setEntries(data.entries);
    } catch (e) {
      toast.error('Error al cargar auditoría');
    }
  }, [severity]);

  useEffect(() => { void load(); }, [load]);

  const sevColor = (s) => s === 'CRITICAL' ? COLOR.bad : s === 'WARNING' ? COLOR.warn : COLOR.info;
  const sevBg = (s) => s === 'CRITICAL' ? '#fef2f2' : s === 'WARNING' ? '#fef3c7' : '#eff6ff';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Section title="Registro de auditoría" action={
        <select value={severity} onChange={(e) => setSeverity(e.target.value)} style={{ ...S.input, width: 180 }} data-testid="acc-v2-audit-severity">
          <option value="">Todas las severidades</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
      }>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {entries.length === 0 ? <div style={S.empty}>Sin registros</div> :
            entries.map((e, i) => (
              <div key={i} style={{ ...S.auditCard, backgroundColor: sevBg(e.severity), borderLeftColor: sevColor(e.severity) }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <span style={{ ...S.sevBadge, color: sevColor(e.severity), backgroundColor: '#fff' }}>{e.severity}</span>
                    <strong style={{ marginLeft: 8 }}>{e.action}</strong>
                  </div>
                  <span style={{ fontSize: 11, color: COLOR.muted }}>{e.created_at?.slice(0, 19).replace('T', ' ')}</span>
                </div>
                <div style={{ fontSize: 12, color: COLOR.muted, marginTop: 4 }}>
                  ref: <code>{e.reference_id}</code> · actor: {e.actor}
                </div>
                {e.current_state && (
                  <details style={{ marginTop: 6, fontSize: 11 }}>
                    <summary style={{ cursor: 'pointer', color: COLOR.brand }}>Ver detalles</summary>
                    <pre style={{ marginTop: 4, padding: 8, backgroundColor: '#fff', borderRadius: 6, overflow: 'auto', fontSize: 11 }}>
                      {JSON.stringify({ previous: e.previous_state, current: e.current_state }, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
        </div>
      </Section>
    </div>
  );
}

// ─────────────────────────────────────────
// Main page
// ─────────────────────────────────────────
export default function AccountingV2() {
  const navigate = useNavigate();
  const [tab, setTab] = useState('summary');
  const [start, setStart] = useState(daysAgoStr(30));
  const [end, setEnd] = useState(todayStr());

  const TABS = [
    { id: 'summary', label: 'Resumen Ejecutivo', icon: TrendingUp },
    { id: 'usdt', label: 'Inventario USDT', icon: Package },
    { id: 'p2p', label: 'Mesa P2P', icon: DollarSign },
    { id: 'audit', label: 'Auditoría', icon: ScrollText },
  ];

  return (
    <div style={{ minHeight: '100vh', backgroundColor: COLOR.bg, paddingBottom: 60 }}>
      <div style={S.header}>
        <button onClick={() => navigate('/admin')} style={S.backBtn} data-testid="acc-v2-back-btn"><ArrowLeft size={20} /></button>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: COLOR.text, margin: 0 }}>Contabilidad Enterprise v2</h1>
          <p style={{ fontSize: 12, color: COLOR.muted, margin: '2px 0 0 0' }}>Motor FIFO · P2P · Auditoría · Reporte Ejecutivo</p>
        </div>
      </div>

      <div style={S.tabs}>
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`acc-v2-tab-${t.id}`}
              style={{ ...S.tab, ...(active ? S.tabActive : {}) }}>
              <Icon size={16} /> {t.label}
            </button>
          );
        })}
      </div>

      <div style={S.content}>
        {tab === 'summary' && <ExecutiveSummary start={start} end={end} onRange={(s, e) => { setStart(s); setEnd(e); }} />}
        {tab === 'usdt' && <UsdtInventory />}
        {tab === 'p2p' && <P2PMesa />}
        {tab === 'audit' && <AuditLog />}
      </div>

      <style>{`.anim-spin{animation:s 1s linear infinite}@keyframes s{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

// ─────────────────────────────────────────
// Styles
// ─────────────────────────────────────────
const S = {
  header: { display: 'flex', alignItems: 'center', gap: 12, padding: '18px 20px', backgroundColor: '#fff', borderBottom: `1px solid ${COLOR.border}` },
  backBtn: { width: 36, height: 36, borderRadius: '50%', border: `1px solid ${COLOR.border}`, backgroundColor: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' },
  tabs: { display: 'flex', gap: 4, padding: '12px 16px', backgroundColor: '#fff', borderBottom: `1px solid ${COLOR.border}`, overflowX: 'auto' },
  tab: { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 10, border: 'none', backgroundColor: 'transparent', color: COLOR.muted, fontSize: 13, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' },
  tabActive: { backgroundColor: COLOR.brand, color: '#fff' },
  content: { padding: 16, maxWidth: 1280, margin: '0 auto' },
  section: { backgroundColor: '#fff', border: `1px solid ${COLOR.border}`, borderRadius: 14, padding: 16 },
  sectionHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, gap: 8, flexWrap: 'wrap' },
  sectionTitle: { fontSize: 14, fontWeight: 700, color: COLOR.text, margin: 0 },
  metricCard: { padding: 14, borderRadius: 12, backgroundColor: '#fff', border: `1px solid ${COLOR.border}` },
  grid2: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 },
  grid3: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 },
  label: { display: 'block', fontSize: 12, fontWeight: 600, color: COLOR.muted, marginBottom: 4 },
  input: { width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${COLOR.border}`, fontSize: 13, outline: 'none', boxSizing: 'border-box' },
  dateInput: { padding: '6px 8px', borderRadius: 8, border: `1px solid ${COLOR.border}`, fontSize: 13 },
  primaryBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 10, border: 'none', backgroundColor: COLOR.brand, color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' },
  formBox: { padding: 12, backgroundColor: COLOR.bg, borderRadius: 10, marginBottom: 12 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { textAlign: 'left', padding: '8px 10px', backgroundColor: COLOR.bg, color: COLOR.muted, fontWeight: 600, fontSize: 11, textTransform: 'uppercase', borderBottom: `1px solid ${COLOR.border}` },
  td: { padding: '10px', borderBottom: `1px solid ${COLOR.border}` },
  empty: { padding: '20px', textAlign: 'center', color: COLOR.muted, fontSize: 13 },
  tagGood: { padding: '2px 8px', borderRadius: 6, backgroundColor: '#dcfce7', color: COLOR.good, fontSize: 11, fontWeight: 600 },
  tagBad: { padding: '2px 8px', borderRadius: 6, backgroundColor: '#fee2e2', color: COLOR.bad, fontSize: 11, fontWeight: 600 },
  loadingBox: { display: 'flex', alignItems: 'center', gap: 8, padding: 40, justifyContent: 'center', color: COLOR.muted, fontSize: 14 },
  footer: { fontSize: 11, color: COLOR.muted, textAlign: 'center', marginTop: 8 },
  auditCard: { padding: 12, borderRadius: 10, borderLeft: '4px solid' },
  sevBadge: { padding: '2px 8px', borderRadius: 6, fontSize: 10, fontWeight: 700, letterSpacing: 0.5 },
};
