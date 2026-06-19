import { useState, useEffect, useCallback } from 'react';
import {
  Search, RefreshCw, Download, Clock, CheckCircle2, XCircle,
  Send, AlertTriangle, ChevronLeft, ChevronRight
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { formatRelativeTime, formatAbsoluteTime } from '../../utils/dates';

const TABS = [
  { key: 'all',       label: 'Todas',     color: '#374151', bg: '#F3F4F6' },
  { key: 'pendiente', label: 'Pendientes', color: '#92400E', bg: '#FEF3C7', Icon: Clock },
  { key: 'pagado',    label: 'Pagadas',    color: '#1E3A8A', bg: '#DBEAFE', Icon: Send },
  { key: 'enviado',   label: 'Enviadas',   color: '#166534', bg: '#DCFCE7', Icon: CheckCircle2 },
  { key: 'cancelado', label: 'Canceladas', color: '#991B1B', bg: '#FEE2E2', Icon: XCircle },
  { key: 'expirado',  label: 'Expiradas',  color: '#6B7280', bg: '#F3F4F6', Icon: AlertTriangle },
];

const STATUS_STYLE = {
  pendiente: { bg: '#FEF3C7', fg: '#92400E', Icon: Clock,       label: 'Pendiente' },
  pagado:    { bg: '#DBEAFE', fg: '#1E3A8A', Icon: Send,        label: 'Pagado' },
  enviado:   { bg: '#DCFCE7', fg: '#166534', Icon: CheckCircle2, label: 'Enviado' },
  cancelado: { bg: '#FEE2E2', fg: '#991B1B', Icon: XCircle,     label: 'Cancelado' },
  expirado:  { bg: '#F3F4F6', fg: '#6B7280', Icon: AlertTriangle, label: 'Expirado' },
  fallido:   { bg: '#FEE2E2', fg: '#991B1B', Icon: XCircle,     label: 'Fallido' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_STYLE[status] || STATUS_STYLE.pendiente;
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

export default function BtcAdminHistorial() {
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/btc/transacciones', {
        params: { status, search: debouncedSearch || undefined, page, page_size: 25 },
      });
      setItems(res.data?.items || []);
      setCounts(res.data?.counts || {});
      setTotalPages(res.data?.total_pages || 1);
      setTotal(res.data?.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al cargar historial BTC');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [status, debouncedSearch, page]);

  useEffect(() => { load(); }, [load]);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [status, debouncedSearch]);

  const handleExport = async () => {
    try {
      const res = await api.get('/admin/btc/transacciones.csv', {
        params: { status, search: debouncedSearch || undefined },
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `btc_${status}_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('CSV descargado');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al exportar');
    }
  };

  const cardStyle = {
    backgroundColor: '#ffffff', borderRadius: '16px',
    border: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      {/* Tabs + search + export */}
      <div style={{ ...cardStyle, padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {TABS.map((t) => {
            const active = status === t.key;
            const Icon = t.Icon;
            const count = t.key === 'all' ? (counts.total || 0) : (counts[t.key] || 0);
            return (
              <button
                key={t.key}
                onClick={() => setStatus(t.key)}
                data-testid={`btc-admin-tab-${t.key}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '8px 12px', borderRadius: '10px',
                  border: active ? `2px solid ${t.color}` : '1px solid #e5e7eb',
                  backgroundColor: active ? t.bg : '#fff',
                  color: active ? t.color : '#374151',
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
                  backgroundColor: active ? '#fff' : '#f3f4f6',
                  color: active ? t.color : '#6b7280',
                }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ position: 'relative' }}>
            <Search size={15} style={{ position: 'absolute', left: '11px', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar usuario, beneficiario, cuenta…"
              data-testid="btc-admin-search"
              style={{
                width: '280px', maxWidth: '50vw',
                padding: '9px 12px 9px 34px',
                borderRadius: '10px', border: '1.5px solid #e5e7eb',
                fontSize: '13px', outline: 'none',
              }}
            />
          </div>
          <button
            onClick={load}
            title="Recargar"
            style={{ padding: '9px 11px', borderRadius: '10px', backgroundColor: '#fff', border: '1.5px solid #e5e7eb', cursor: 'pointer', color: '#374151', display: 'inline-flex', alignItems: 'center' }}
          >
            <RefreshCw size={15} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>
          <button
            onClick={handleExport}
            disabled={items.length === 0}
            data-testid="btc-admin-export"
            style={{
              padding: '9px 14px', borderRadius: '10px',
              backgroundColor: items.length === 0 ? '#f3f4f6' : '#1f2937',
              border: 'none', cursor: items.length === 0 ? 'not-allowed' : 'pointer',
              color: items.length === 0 ? '#9ca3af' : '#fff',
              fontSize: '13px', fontWeight: 600,
              display: 'inline-flex', alignItems: 'center', gap: '6px',
            }}
          >
            <Download size={15} /> CSV
          </button>
        </div>
      </div>

      {/* Table */}
      <div style={{ ...cardStyle, overflow: 'auto' }}>
        {loading ? (
          <div style={{ padding: '48px', textAlign: 'center' }}>
            <RefreshCw size={28} style={{ color: '#6366f1', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding: '48px', textAlign: 'center', color: '#6b7280', fontSize: '14px' }}>
            No hay transacciones que coincidan con los filtros.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead style={{ backgroundColor: '#F9FAFB', borderBottom: '1px solid #e5e7eb' }}>
              <tr>
                <Th>Fecha</Th>
                <Th>Usuario</Th>
                <Th align="right">BTC pagado</Th>
                <Th align="right">Tasa BTC-USDI</Th>
                <Th align="right">Monto VES</Th>
                <Th>Beneficiario</Th>
                <Th>Pago BTC</Th>
                <Th>Envío VES</Th>
                <Th>Estado</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((tx) => (
                <tr key={tx.remesa_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`btc-tx-${tx.remesa_id}`}>
                  <Td>
                    <div style={{ color: '#111827', fontWeight: 500 }}>{formatAbsoluteTime(tx.creado_en)}</div>
                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>{formatRelativeTime(tx.creado_en)}</div>
                  </Td>
                  <Td>
                    <div style={{ color: '#111827', fontWeight: 500 }}>{tx.user_name || '—'}</div>
                    <div style={{ color: '#6b7280', fontSize: '12px' }}>{tx.user_email}</div>
                    <div style={{ color: '#9ca3af', fontSize: '11px', fontFamily: 'monospace' }}>{tx.user_id}</div>
                  </Td>
                  <Td align="right">
                    <div style={{ color: '#111827', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                      ₿ {tx.btc_pagar.toFixed(8)}
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: '11px', fontVariantNumeric: 'tabular-nums' }}>
                      {fmt(tx.sats, 0)} sats
                    </div>
                  </Td>
                  <Td align="right">
                    <div style={{ color: '#111827', fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}>
                      ${fmt(tx.precio_btc_usado, 2)}
                    </div>
                    {tx.precio_con_margen > 0 && (
                      <div style={{ color: '#9ca3af', fontSize: '11px' }}>
                        c/margen: ${fmt(tx.precio_con_margen, 2)}
                      </div>
                    )}
                  </Td>
                  <Td align="right">
                    <div style={{ color: '#16a34a', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                      {fmt(tx.ves_recibe)} Bs
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>
                      USDI ${fmt(tx.usd_cliente)}
                    </div>
                  </Td>
                  <Td>
                    <div style={{ color: '#111827', fontWeight: 500 }}>{tx.beneficiario?.full_name || '—'}</div>
                    {tx.beneficiario?.id_document && (
                      <div style={{ color: '#6b7280', fontSize: '11px' }}>{tx.beneficiario.id_document}</div>
                    )}
                    {(tx.beneficiario?.bank || tx.beneficiario?.phone || tx.beneficiario?.account_number) && (
                      <div style={{ color: '#9ca3af', fontSize: '11px' }}>
                        {tx.beneficiario.bank}{tx.beneficiario.phone ? ` · ${tx.beneficiario.phone}` : ''}{tx.beneficiario.account_number ? ` · ${tx.beneficiario.account_number}` : ''}
                      </div>
                    )}
                  </Td>
                  <Td>
                    {tx.pagado_en
                      ? <span style={{ color: '#1E3A8A', fontWeight: 500 }}>{formatAbsoluteTime(tx.pagado_en)}</span>
                      : <span style={{ color: '#d1d5db' }}>—</span>}
                  </Td>
                  <Td>
                    {tx.enviado_en
                      ? <>
                          <span style={{ color: '#166534', fontWeight: 500 }}>{formatAbsoluteTime(tx.enviado_en)}</span>
                          {tx.operador_id && (
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>op: {tx.operador_id}</div>
                          )}
                        </>
                      : <span style={{ color: '#d1d5db' }}>—</span>}
                  </Td>
                  <Td><StatusBadge status={tx.estado} /></Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 4px' }}>
          <div style={{ fontSize: '13px', color: '#6b7280' }}>
            Mostrando página {page} de {totalPages} ({total} registros)
          </div>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{ padding: '8px 12px', borderRadius: '10px', border: '1px solid #e5e7eb', backgroundColor: page === 1 ? '#f3f4f6' : '#fff', color: page === 1 ? '#9ca3af' : '#374151', cursor: page === 1 ? 'not-allowed' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '13px', fontWeight: 600 }}
            >
              <ChevronLeft size={14} /> Anterior
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              style={{ padding: '8px 12px', borderRadius: '10px', border: '1px solid #e5e7eb', backgroundColor: page === totalPages ? '#f3f4f6' : '#fff', color: page === totalPages ? '#9ca3af' : '#374151', cursor: page === totalPages ? 'not-allowed' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '13px', fontWeight: 600 }}
            >
              Siguiente <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Th({ children, align = 'left' }) {
  return (
    <th style={{
      padding: '10px 14px', textAlign: align, fontSize: '11px',
      textTransform: 'uppercase', letterSpacing: '0.04em', color: '#6b7280',
      fontWeight: 600,
    }}>
      {children}
    </th>
  );
}

function Td({ children, align = 'left' }) {
  return (
    <td style={{ padding: '10px 14px', textAlign: align, verticalAlign: 'top', color: '#374151' }}>
      {children}
    </td>
  );
}
