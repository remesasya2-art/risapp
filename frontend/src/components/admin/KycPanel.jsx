import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  Search, RefreshCw, Eye, CheckCircle2, XCircle, Clock, ShieldCheck,
  ShieldAlert, ShieldX, ImageOff, User as UserIcon, Download
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import KycDetailModal from './KycDetailModal';
import KycRejectModal from './KycRejectModal';
import { formatRelativeTime } from '../../utils/dates';

const TABS = [
  { key: 'pending',  label: 'Pendientes',  icon: Clock,         color: '#d97706', bg: '#fef3c7' },
  { key: 'approved', label: 'Aprobados',   icon: ShieldCheck,   color: '#16a34a', bg: '#dcfce7' },
  { key: 'rejected', label: 'Rechazados',  icon: ShieldX,       color: '#dc2626', bg: '#fee2e2' },
];

const STATUS_BADGE = {
  pending:  { bg: '#fef3c7', fg: '#92400e', label: 'Pendiente' },
  approved: { bg: '#dcfce7', fg: '#166534', label: 'Aprobado' },
  verified: { bg: '#dcfce7', fg: '#166534', label: 'Aprobado' },
  rejected: { bg: '#fee2e2', fg: '#991b1b', label: 'Rechazado' },
};

function maskCPF(cpf) {
  if (!cpf) return '—';
  const c = String(cpf).replace(/\D/g, '');
  if (c.length < 3) return cpf;
  const last = c.slice(-3);
  return `***.***.**${last.charAt(0)}-${last.slice(1)}`;
}

/**
 * KYC management panel for the admin.
 * Self-contained: fetches its own data and emits onChange when something is decided
 * so the parent can refresh global stats.
 */
export default function KycPanel({ onChange }) {
  const [status, setStatus] = useState('pending');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({ pending: 0, approved: 0, rejected: 0 });
  const [selected, setSelected] = useState(null);
  const [quickReject, setQuickReject] = useState(null);
  const abortRef = useRef(null);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/kyc/list', {
        params: { status, search: debouncedSearch || undefined, limit: 200 },
      });
      setItems(res.data?.items || []);
      setCounts(res.data?.counts || { pending: 0, approved: 0, rejected: 0 });
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al cargar KYC');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [status, debouncedSearch]);

  useEffect(() => {
    load();
  }, [load]);

  const handleQuickApprove = async (v) => {
    if (!v?.verification_id) return;
    try {
      await api.post(`/admin/kyc/${v.verification_id}/approve`);
      toast.success('KYC aprobado');
      await load();
      onChange?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al aprobar');
    }
  };

  const handleExportCsv = async () => {
    try {
      const res = await api.get('/admin/kyc/export.csv', {
        params: { status, search: debouncedSearch || undefined },
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      a.download = `kyc_${status}_${ts}.csv`;
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
    backgroundColor: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e5e7eb',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Tabs + counts */}
      <div style={{ ...cardStyle, padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = status === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setStatus(t.key)}
                data-testid={`kyc-tab-${t.key}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '8px',
                  padding: '10px 16px', borderRadius: '12px',
                  border: active ? `2px solid ${t.color}` : '1px solid #e5e7eb',
                  backgroundColor: active ? t.bg : '#fff',
                  color: active ? t.color : '#374151',
                  fontWeight: 600, fontSize: '14px', cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                <Icon size={16} />
                <span>{t.label}</span>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  minWidth: '22px', height: '22px', borderRadius: '999px',
                  padding: '0 7px', fontSize: '12px', fontWeight: 700,
                  backgroundColor: active ? '#fff' : '#f3f4f6',
                  color: active ? t.color : '#6b7280',
                }}>
                  {counts[t.key] ?? 0}
                </span>
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nombre, email o documento…"
              data-testid="kyc-search"
              style={{
                width: '320px', maxWidth: '50vw',
                padding: '10px 12px 10px 38px',
                borderRadius: '12px', border: '1.5px solid #e5e7eb',
                fontSize: '14px', outline: 'none',
              }}
            />
          </div>
          <button
            onClick={load}
            title="Recargar"
            style={{
              padding: '10px 12px', borderRadius: '12px',
              backgroundColor: '#fff', border: '1.5px solid #e5e7eb',
              cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px',
              color: '#374151', fontSize: '13px', fontWeight: 600,
            }}
          >
            <RefreshCw size={16} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Actualizar
          </button>
          <button
            onClick={handleExportCsv}
            title="Exportar CSV con filtros aplicados"
            data-testid="kyc-export-csv"
            disabled={items.length === 0}
            style={{
              padding: '10px 14px', borderRadius: '12px',
              backgroundColor: items.length === 0 ? '#f3f4f6' : '#1f2937',
              border: 'none', cursor: items.length === 0 ? 'not-allowed' : 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              color: items.length === 0 ? '#9ca3af' : '#fff',
              fontSize: '13px', fontWeight: 600,
            }}
          >
            <Download size={16} /> Exportar CSV
          </button>
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}>
          <RefreshCw size={28} style={{ color: '#6366f1', animation: 'spin 1s linear infinite' }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}>
          <ShieldAlert size={32} style={{ color: '#9ca3af', marginBottom: '8px' }} />
          <p style={{ color: '#6b7280', margin: 0 }}>
            {debouncedSearch
              ? `No se encontraron resultados para "${debouncedSearch}"`
              : status === 'pending' ? 'No hay verificaciones pendientes'
              : status === 'approved' ? 'No hay verificaciones aprobadas'
              : 'No hay verificaciones rechazadas'}
          </p>
        </div>
      ) : (
        items.map((v) => {
          const badge = STATUS_BADGE[v.status] || STATUS_BADGE.pending;
          return (
            <div key={v.verification_id} style={{ ...cardStyle, padding: '18px' }} data-testid={`kyc-${v.verification_id}`}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
                {/* Selfie thumbnail (or placeholder) */}
                <div style={{
                  width: '72px', height: '72px', borderRadius: '14px',
                  overflow: 'hidden', flexShrink: 0,
                  border: '2px solid #e5e7eb', backgroundColor: '#f3f4f6',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer',
                }}
                onClick={() => setSelected(v)}
                title="Ver documentos"
                >
                  {v.has_selfie ? (
                    <span style={{ fontSize: '24px', fontWeight: 700, color: '#6b7280' }}>
                      {(v.full_name || '?').trim().charAt(0).toUpperCase()}
                    </span>
                  ) : (
                    <ImageOff size={22} color="#9ca3af" />
                  )}
                </div>

                <div style={{ flex: 1, minWidth: '220px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                    <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#111827', margin: 0 }}>
                      {v.full_name || 'Sin nombre'}
                    </h3>
                    <span style={{
                      display: 'inline-flex', padding: '3px 9px',
                      borderRadius: '999px', fontSize: '11px', fontWeight: 600,
                      backgroundColor: badge.bg, color: badge.fg,
                    }}>
                      {badge.label}
                    </span>
                    {v.blacklist_match && (
                      <span style={{ display: 'inline-flex', padding: '3px 9px', borderRadius: '999px', fontSize: '11px', fontWeight: 700, backgroundColor: '#fee2e2', color: '#b91c1c' }}>
                        ⚠ Lista negra
                      </span>
                    )}
                  </div>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 6px 0' }}>{v.email || '—'}</p>
                  <p style={{ fontSize: '13px', color: '#374151', margin: 0 }}>
                    CPF: <strong>{maskCPF(v.cpf_number)}</strong>
                    {v.document_number ? <> &nbsp;•&nbsp; Doc: <strong>{v.document_number}</strong></> : null}
                    {v.phone_number ? <> &nbsp;•&nbsp; Tel: {v.phone_number}</> : null}
                  </p>
                  {v.submitted_at && (
                    <p style={{ fontSize: '12px', color: '#9ca3af', margin: '6px 0 0 0', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={12} /> Enviado {formatRelativeTime(v.submitted_at)}
                    </p>
                  )}
                  {v.status === 'rejected' && v.rejection_reason && (
                    <p style={{ fontSize: '12px', color: '#991b1b', margin: '6px 0 0 0', fontStyle: 'italic' }}>
                      ✗ {v.rejection_reason}
                    </p>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button
                    onClick={() => setSelected(v)}
                    data-testid={`kyc-view-${v.verification_id}`}
                    style={btnPrimary}
                  >
                    <Eye size={15} /> Ver Docs
                  </button>
                  {v.status === 'pending' && (
                    <>
                      <button
                        onClick={() => handleQuickApprove(v)}
                        data-testid={`kyc-approve-${v.verification_id}`}
                        style={btnSuccess}
                      >
                        <CheckCircle2 size={15} /> Aprobar
                      </button>
                      <button
                        onClick={() => setQuickReject(v)}
                        data-testid={`kyc-reject-${v.verification_id}`}
                        style={btnDanger}
                      >
                        <XCircle size={15} /> Rechazar
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })
      )}

      {/* Detail Modal */}
      {selected && (
        <KycDetailModal
          verification={selected}
          onClose={() => setSelected(null)}
          onChanged={async () => { await load(); onChange?.(); }}
        />
      )}

      {/* Quick Reject (from card, without opening detail) */}
      {quickReject && (
        <KycRejectModal
          verification={quickReject}
          onClose={() => setQuickReject(null)}
          onSuccess={async () => { await load(); onChange?.(); }}
        />
      )}
    </div>
  );
}

const btnBase = {
  display: 'inline-flex', alignItems: 'center', gap: '6px',
  padding: '8px 14px', borderRadius: '10px',
  fontSize: '13px', fontWeight: 600, cursor: 'pointer',
  border: 'none', transition: 'transform 0.05s',
};
const btnPrimary = { ...btnBase, backgroundColor: '#6366f1', color: '#fff' };
const btnSuccess = { ...btnBase, backgroundColor: '#16a34a', color: '#fff' };
const btnDanger  = { ...btnBase, backgroundColor: '#fff', color: '#dc2626', border: '1.5px solid #dc2626' };
