import { useState, useEffect, useCallback } from 'react';
import {
  Search, RefreshCw, Wallet, Clock, CheckCircle2, XCircle, AlertTriangle, PlusCircle,
  Download, FileText,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar } from '../flujo/confirmar.js';
import { formatRelativeTime, formatAbsoluteTime } from '../../utils/dates';
import conAlfa from '../../tema/conAlfa';

// Estados posibles en crypto_deposits (reales via NOWPayments + acreditaciones manuales)
const TABS = [
  { key: 'all',      label: 'Todos',      color: 'var(--en-oscuro-texto, #374151)', bg: 'var(--en-oscuro-superficie-2, #F3F4F6)' },
  { key: 'pending',  label: 'Pendientes', color: 'var(--en-oscuro-alerta, #92400E)', bg: 'var(--en-oscuro-alerta-suave, #FEF3C7)', Icon: Clock },
  { key: 'finished', label: 'Acreditados', color: 'var(--en-oscuro-exito, #166534)', bg: 'var(--en-oscuro-exito-suave, #DCFCE7)', Icon: CheckCircle2 },
  { key: 'manual',   label: 'Manuales',   color: 'var(--en-oscuro-acento, #3730A3)', bg: 'var(--en-oscuro-acento-suave, #E0E7FF)', Icon: PlusCircle },
  { key: 'failed',   label: 'Fallidos',   color: 'var(--en-oscuro-error, #991B1B)', bg: 'var(--en-oscuro-error-suave, #FEE2E2)', Icon: XCircle },
  { key: 'expired',  label: 'Expirados',  color: 'var(--en-oscuro-texto-2, #6B7280)', bg: 'var(--en-oscuro-superficie-2, #F3F4F6)', Icon: AlertTriangle },
];

const STATUS_STYLE = {
  pending:   { bg: 'var(--en-oscuro-alerta-suave, #FEF3C7)', fg: 'var(--en-oscuro-alerta, #92400E)', Icon: Clock,        label: 'Pendiente' },
  finished:  { bg: 'var(--en-oscuro-exito-suave, #DCFCE7)', fg: 'var(--en-oscuro-exito, #166534)', Icon: CheckCircle2, label: 'Acreditado' },
  manual:    { bg: 'var(--en-oscuro-acento-suave, #E0E7FF)', fg: 'var(--en-oscuro-acento, #3730A3)', Icon: PlusCircle,   label: 'Manual' },
  failed:    { bg: 'var(--en-oscuro-error-suave, #FEE2E2)', fg: 'var(--en-oscuro-error, #991B1B)', Icon: XCircle,      label: 'Fallido' },
  error:     { bg: 'var(--en-oscuro-error-suave, #FEE2E2)', fg: 'var(--en-oscuro-error, #991B1B)', Icon: XCircle,      label: 'Error' },
  expired:   { bg: 'var(--en-oscuro-superficie-2, #F3F4F6)', fg: 'var(--en-oscuro-texto-2, #6B7280)', Icon: AlertTriangle, label: 'Expirado' },
  refunded:  { bg: 'var(--en-oscuro-superficie-2, #F3F4F6)', fg: 'var(--en-oscuro-texto-2, #6B7280)', Icon: AlertTriangle, label: 'Reembolsado' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_STYLE[status] || STATUS_STYLE.pending;
  const Icon = cfg.Icon;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '4px 10px', borderRadius: '20px',
      backgroundColor: cfg.bg, color: cfg.fg,
      fontSize: '12px', fontWeight: 600, lineHeight: 1,
    }}>
      <Icon size={12} strokeWidth={2.5} />
      {cfg.label}
    </span>
  );
}

function Th({ children, align = 'left' }) {
  return (
    <th style={{
      padding: '10px 14px', textAlign: align, fontSize: '11px',
      textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--en-oscuro-texto-2, #6b7280)',
      fontWeight: 600,
    }}>
      {children}
    </th>
  );
}

function Td({ children, align = 'left' }) {
  return (
    <td style={{ padding: '10px 14px', textAlign: align, verticalAlign: 'top', color: 'var(--en-oscuro-texto, #374151)' }}>
      {children}
    </td>
  );
}

export default function CreditsAdminPanel() {
  // --- Formulario de acreditacion manual ---
  const [email, setEmail] = useState('');
  const [currency, setCurrency] = useState('usdt');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [crediting, setCrediting] = useState(false);

  // --- Historial ---
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);

  // --- Reporte (diario o por rango de fechas) ---
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/credits/deposits', {
        params: {
          status, search: debouncedSearch || undefined, limit: 100,
          date_from: dateFrom || undefined, date_to: dateTo || undefined,
        },
      });
      setItems(res.data?.items || []);
      setCounts(res.data?.counts || {});
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al cargar historial de créditos');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [status, debouncedSearch, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const totalCount = Object.values(counts).reduce((a, b) => a + b, 0);

  const handleManualCredit = async () => {
    const amountNum = parseFloat(amount);
    if (!email.trim()) {
      toast.error('Ingresa el email del usuario');
      return;
    }
    if (!amountNum || amountNum <= 0) {
      toast.error('El monto debe ser mayor a 0');
      return;
    }
    const confirmado = await confirmar({
      titulo: `¿Acreditar ${amountNum} ${currency.toUpperCase()} a ${email.trim()}?`,
      detalle: 'Toca sólo los créditos cripto. El saldo RIS del usuario no se modifica.',
      accion: 'Acreditar',
    });
    if (!confirmado) return;

    setCrediting(true);
    try {
      const { data } = await api.post('/admin/credits/manual-credit', {
        email: email.trim(),
        currency,
        amount: amountNum,
        note: note.trim() || undefined,
      });
      toast.success(`Acreditado: ${data.amount} ${data.currency.toUpperCase()} a ${data.user_email}`);
      setEmail('');
      setAmount('');
      setNote('');
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo acreditar');
    } finally {
      setCrediting(false);
    }
  };

  const generateReport = async () => {
    if (!dateFrom || !dateTo) {
      toast.error('Selecciona fecha "Desde" y "Hasta" para generar el reporte (usa la misma fecha para un reporte diario)');
      return;
    }
    setReportLoading(true);
    try {
      const { data } = await api.get('/admin/credits/report', {
        params: { date_from: dateFrom, date_to: dateTo, currency: 'all' },
      });
      setReport(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo generar el reporte');
    } finally {
      setReportLoading(false);
    }
  };

  const downloadReportCsv = async () => {
    if (!dateFrom || !dateTo) {
      toast.error('Selecciona fecha "Desde" y "Hasta" para descargar el reporte');
      return;
    }
    try {
      const response = await api.get('/admin/credits/report', {
        params: { date_from: dateFrom, date_to: dateTo, currency: 'all', format: 'csv' },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `reporte_cripto_${dateFrom}_a_${dateTo}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error('No se pudo descargar el CSV');
    }
  };

  const cardStyle = {
    backgroundColor: 'var(--en-oscuro-superficie, #ffffff)', borderRadius: '16px',
    border: '1px solid var(--en-oscuro-linea, #e5e7eb)', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  };

  const inputStyle = {
    padding: '10px 12px', borderRadius: '10px', border: '1.5px solid var(--en-oscuro-linea, #e5e7eb)',
    fontSize: '14px', outline: 'none', boxSizing: 'border-box',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Formulario de acreditacion manual */}
      <div style={{ ...cardStyle, padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
          <Wallet size={18} style={{ color: 'var(--en-oscuro-acento, #6366f1)' }} />
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: 0 }}>
            Acreditar créditos manualmente
          </h3>
        </div>
        <p style={{ fontSize: '13px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '0 0 16px 0' }}>
          Para soporte o pruebas (ej. acreditar a tu propia cuenta). Usa el mismo camino atómico
          que el webhook de NOWPayments. Nunca toca balance_ris.
        </p>

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--en-oscuro-texto, #374151)' }}>Email del usuario</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="usuario@ejemplo.com"
              data-testid="credits-admin-email"
              style={{ ...inputStyle, width: '240px' }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--en-oscuro-texto, #374151)' }}>Moneda</label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              data-testid="credits-admin-currency"
              style={{ ...inputStyle, width: '110px' }}
            >
              <option value="usdt">USDT</option>
              <option value="usdc">USDC</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--en-oscuro-texto, #374151)' }}>Monto</label>
            <input
              type="number"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              data-testid="credits-admin-amount"
              style={{ ...inputStyle, width: '120px' }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1, minWidth: '200px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--en-oscuro-texto, #374151)' }}>Nota (opcional)</label>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Motivo / referencia interna"
              data-testid="credits-admin-note"
              style={{ ...inputStyle, width: '100%' }}
            />
          </div>

          <button
            onClick={handleManualCredit}
            disabled={crediting}
            data-testid="credits-admin-submit"
            style={{
              padding: '11px 20px', borderRadius: '10px', border: 'none',
              backgroundColor: crediting ? '#a5b4fc' : 'var(--en-oscuro-acento, #6366f1)', color: '#fff',
              fontSize: '14px', fontWeight: 700, cursor: crediting ? 'not-allowed' : 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: '6px', height: '42px',
            }}
          >
            <PlusCircle size={16} />
            {crediting ? 'Acreditando...' : 'Acreditar'}
          </button>
        </div>
      </div>

      {/* Reporte diario / por rango de fechas */}
      <div style={{ ...cardStyle, padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
          <FileText size={18} style={{ color: 'var(--en-oscuro-acento, #6366f1)' }} />
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: 0 }}>
            Reporte de operaciones (diario o por fechas)
          </h3>
        </div>
        <p style={{ fontSize: '13px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '0 0 16px 0' }}>
          Usa la misma fecha en "Desde" y "Hasta" para un reporte de un solo día, o un rango
          para un período. Solo cuenta operaciones ya acreditadas.
        </p>

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: report ? '16px' : 0 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--en-oscuro-texto, #374151)' }}>Desde</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              data-testid="credits-admin-date-from"
              style={{ ...inputStyle, width: '150px' }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--en-oscuro-texto, #374151)' }}>Hasta</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              data-testid="credits-admin-date-to"
              style={{ ...inputStyle, width: '150px' }}
            />
          </div>
          <button
            onClick={generateReport}
            disabled={reportLoading}
            data-testid="credits-admin-generate-report"
            style={{
              padding: '11px 18px', borderRadius: '10px', border: 'none',
              backgroundColor: reportLoading ? '#a5b4fc' : 'var(--en-oscuro-acento, #6366f1)', color: '#fff',
              fontSize: '14px', fontWeight: 700, cursor: reportLoading ? 'not-allowed' : 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: '6px', height: '42px',
            }}
          >
            <FileText size={16} />
            {reportLoading ? 'Generando...' : 'Generar reporte'}
          </button>
          <button
            onClick={downloadReportCsv}
            data-testid="credits-admin-download-csv"
            style={{
              padding: '11px 18px', borderRadius: '10px', border: '1.5px solid var(--en-oscuro-linea, #e5e7eb)',
              backgroundColor: 'var(--en-oscuro-superficie, #fff)', color: 'var(--en-oscuro-texto, #374151)',
              fontSize: '14px', fontWeight: 700, cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: '6px', height: '42px',
            }}
          >
            <Download size={16} />
            Descargar CSV
          </button>
        </div>

        {report && (
          <div>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
              <SummaryPill label="Total USDT" value={`${report.totals.usdt} USDT`} tono="#26A17B" />
              <SummaryPill label="Total USDC" value={`${report.totals.usdc} USDC`} tono="#2775CA" />
              <SummaryPill label="Operaciones" value={report.totals.count} tono="var(--en-oscuro-acento, #6366f1)" />
            </div>
            {report.by_day.length > 0 && (
              <div style={{ overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead style={{ backgroundColor: 'var(--en-oscuro-superficie-2, #F9FAFB)', borderBottom: '1px solid var(--en-oscuro-linea, #e5e7eb)' }}>
                    <tr>
                      <Th>Fecha</Th>
                      <Th align="right">USDT</Th>
                      <Th align="right">USDC</Th>
                      <Th align="right">Operaciones</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.by_day.map((row) => (
                      <tr key={row.date} style={{ borderBottom: '1px solid var(--en-oscuro-linea, #f3f4f6)' }}>
                        <Td>{row.date}</Td>
                        <Td align="right">{row.usdt}</Td>
                        <Td align="right">{row.usdc}</Td>
                        <Td align="right">{row.count}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tabs + search */}
      <div style={{ ...cardStyle, padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {TABS.map((t) => {
            const active = status === t.key;
            const Icon = t.Icon;
            const count = t.key === 'all' ? totalCount : (counts[t.key] || 0);
            return (
              <button
                key={t.key}
                onClick={() => setStatus(t.key)}
                data-testid={`credits-admin-tab-${t.key}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '8px 12px', borderRadius: '10px',
                  border: active ? `2px solid ${t.color}` : '1px solid var(--en-oscuro-linea, #e5e7eb)',
                  backgroundColor: active ? t.bg : 'var(--en-oscuro-superficie, #fff)',
                  color: active ? t.color : 'var(--en-oscuro-texto, #374151)',
                  fontWeight: 600, fontSize: '13px', cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                {Icon && <Icon size={14} />}
                {t.label}
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  minWidth: '20px', height: '20px', borderRadius: '999px',
                  padding: '0 6px', fontSize: '11px', fontWeight: 700,
                  backgroundColor: active ? 'var(--en-oscuro-superficie, #fff)' : 'var(--en-oscuro-superficie-2, #f3f4f6)',
                  color: active ? t.color : 'var(--en-oscuro-texto-2, #6b7280)',
                }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ position: 'relative' }}>
            <Search size={15} style={{ position: 'absolute', left: '11px', top: '50%', transform: 'translateY(-50%)', color: 'var(--en-oscuro-texto-3, #9ca3af)' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar email, nombre, order_id…"
              data-testid="credits-admin-search"
              style={{
                width: '260px', maxWidth: '50vw',
                padding: '9px 12px 9px 34px',
                borderRadius: '10px', border: '1.5px solid var(--en-oscuro-linea, #e5e7eb)',
                fontSize: '13px', outline: 'none',
              }}
            />
          </div>
          <button
            onClick={load}
            title="Recargar"
            style={{ padding: '9px 11px', borderRadius: '10px', backgroundColor: 'var(--en-oscuro-superficie, #fff)', border: '1.5px solid var(--en-oscuro-linea, #e5e7eb)', cursor: 'pointer', color: 'var(--en-oscuro-texto, #374151)', display: 'inline-flex', alignItems: 'center' }}
          >
            <RefreshCw size={15} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>
      </div>

      {/* Tabla */}
      <div style={{ ...cardStyle, overflow: 'auto' }}>
        {loading ? (
          <div style={{ padding: '48px', textAlign: 'center' }}>
            <RefreshCw size={28} style={{ color: 'var(--en-oscuro-acento, #6366f1)', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding: '48px', textAlign: 'center', color: 'var(--en-oscuro-texto-2, #6b7280)', fontSize: '14px' }}>
            No hay depósitos que coincidan con los filtros.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead style={{ backgroundColor: 'var(--en-oscuro-superficie-2, #F9FAFB)', borderBottom: '1px solid var(--en-oscuro-linea, #e5e7eb)' }}>
              <tr>
                <Th>Fecha</Th>
                <Th>Usuario</Th>
                <Th align="right">Monto</Th>
                <Th>Origen</Th>
                <Th>Order ID</Th>
                <Th>Estado</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.order_id} style={{ borderBottom: '1px solid var(--en-oscuro-linea, #f3f4f6)' }} data-testid={`credits-tx-${d.order_id}`}>
                  <Td>
                    <div style={{ color: 'var(--en-oscuro-texto, #111827)', fontWeight: 500 }}>{formatAbsoluteTime(d.created_at)}</div>
                    <div style={{ color: 'var(--en-oscuro-texto-3, #9ca3af)', fontSize: '11px' }}>{formatRelativeTime(d.created_at)}</div>
                  </Td>
                  <Td>
                    <div style={{ color: 'var(--en-oscuro-texto, #111827)', fontWeight: 500 }}>{d.user_name || '—'}</div>
                    <div style={{ color: 'var(--en-oscuro-texto-2, #6b7280)', fontSize: '12px' }}>{d.user_email || '—'}</div>
                  </Td>
                  <Td align="right">
                    <div style={{ color: 'var(--en-oscuro-texto, #111827)', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                      {d.amount} {(d.currency || '').toUpperCase()}
                    </div>
                  </Td>
                  <Td>
                    {d.source === 'admin_manual' ? (
                      <span style={{ color: 'var(--en-oscuro-acento, #3730A3)', fontWeight: 500 }}>Manual (admin)</span>
                    ) : (
                      <span style={{ color: 'var(--en-oscuro-exito, #166534)', fontWeight: 500 }}>NOWPayments</span>
                    )}
                    {d.admin_note && (
                      <div style={{ color: 'var(--en-oscuro-texto-3, #9ca3af)', fontSize: '11px' }}>{d.admin_note}</div>
                    )}
                  </Td>
                  <Td>
                    <span style={{ fontFamily: 'monospace', fontSize: '11px', color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{d.order_id}</span>
                  </Td>
                  <Td><StatusBadge status={d.status} /></Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// Recibe `tono` y no `color` a propósito: una etiqueta con mayúscula y
// `color=` se lee como un ícono, y la herramienta que pasó los íconos a
// `style` para el modo oscuro le movió el dato a un estilo que nadie lee: la
// barra salía violeta en vez de celeste, también en claro.
function SummaryPill({ label, value, tono: color }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: '4px',
      padding: '10px 16px', borderRadius: '12px',
      backgroundColor: 'var(--en-oscuro-superficie-2, #F9FAFB)', border: `1px solid ${conAlfa(color, '30')}`,
      minWidth: '140px',
    }}>
      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--en-oscuro-texto-2, #6b7280)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>{label}</span>
      <span style={{ fontSize: '18px', fontWeight: 700, color }}>{value}</span>
    </div>
  );
}
