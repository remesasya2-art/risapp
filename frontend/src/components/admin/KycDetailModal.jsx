import { useEffect, useState } from 'react';
import { X, CheckCircle2, XCircle, AlertCircle, Loader, Eye, Image as ImageIcon, Phone, Mail, User as UserIcon, FileText, Calendar, Save, History } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import ImageLightbox from '../common/ImageLightbox';
import KycRejectModal from './KycRejectModal';
import { formatRelativeTime, formatAbsoluteTime } from '../../utils/dates';

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
 * Document tile with click-to-open lightbox.
 * Shows a clear OK / fail indicator.
 */
function DocTile({ label, url, onOpen, autoRotate = 0 }) {
  const ok = !!url;
  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: '14px', overflow: 'hidden', backgroundColor: '#fff' }}>
      <div style={{ padding: '10px 12px', backgroundColor: '#f9fafb', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: '#374151' }}>{label}</span>
        {ok ? (
          <span style={{ fontSize: '11px', color: '#166534', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 600 }}>
            <CheckCircle2 size={14} /> Cargado
          </span>
        ) : (
          <span style={{ fontSize: '11px', color: '#991b1b', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 600 }}>
            <AlertCircle size={14} /> Faltante
          </span>
        )}
      </div>
      {ok ? (
        <button
          onClick={onOpen}
          title="Click para ampliar"
          style={{
            display: 'block', width: '100%', height: '210px',
            padding: 0, border: 'none', cursor: 'zoom-in',
            backgroundColor: '#0f172a', overflow: 'hidden'
          }}
        >
          <img
            src={url}
            alt={label}
            style={{
              width: '100%', height: '100%', objectFit: 'contain',
              transform: `rotate(${autoRotate}deg)`,
              transition: 'transform 0.2s',
              backgroundColor: '#0f172a',
              imageOrientation: 'from-image',
            }}
          />
        </button>
      ) : (
        <div style={{ height: '210px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', backgroundColor: '#f9fafb', gap: '8px' }}>
          <ImageIcon size={28} />
          <span style={{ fontSize: '12px' }}>No disponible</span>
        </div>
      )}
    </div>
  );
}

export default function KycDetailModal({ verification, onClose, onChanged }) {
  const [working, setWorking] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [note, setNote] = useState(verification?.admin_note || '');
  const [noteSaving, setNoteSaving] = useState(false);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const v = verification || {};
  const status = v.status || 'pending';
  const badge = STATUS_BADGE[status] || STATUS_BADGE.pending;

  useEffect(() => {
    setNote(v.admin_note || '');
  }, [v.verification_id, v.admin_note]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !rejectOpen && lightboxIndex === null) onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, rejectOpen, lightboxIndex]);

  const loadHistory = async () => {
    try {
      const res = await api.get(`/admin/kyc/${v.verification_id}/history`);
      setHistory(res.data?.history || []);
      setShowHistory(true);
    } catch {
      toast.error('No se pudo cargar el historial');
    }
  };

  const approve = async () => {
    if (!v.verification_id) return;
    setWorking(true);
    try {
      await api.post(`/admin/kyc/${v.verification_id}/approve`);
      toast.success('KYC aprobado');
      onChanged?.();
      onClose?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al aprobar');
    } finally {
      setWorking(false);
    }
  };

  const saveNote = async () => {
    if (!v.verification_id) return;
    setNoteSaving(true);
    try {
      await api.patch(`/admin/kyc/${v.verification_id}/note`, { note });
      toast.success('Nota guardada');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al guardar nota');
    } finally {
      setNoteSaving(false);
    }
  };

  const DOCS_NEEDING_BACK = new Set(['rg', 'cnh', 'rnm']);
  const requiresBack = DOCS_NEEDING_BACK.has(v.document_type);

  const docs = [
    { url: v.id_document_image,      label: `${v.document_type_label || 'Documento'} (frente)`, autoRotate: 0 },
    ...(requiresBack ? [{ url: v.id_document_image_back, label: `${v.document_type_label || 'Documento'} (reverso)`, autoRotate: 0 }] : []),
    { url: v.cpf_image,              label: 'CPF',                                                 autoRotate: 0 },
    { url: v.selfie_image,           label: 'Selfie',                                              autoRotate: 0 },
  ];
  const availableDocs = docs.filter((d) => !!d.url);

  const openLightbox = (label) => {
    const idx = availableDocs.findIndex((d) => d.label === label);
    if (idx >= 0) setLightboxIndex(idx);
  };

  return (
    <>
      <div
        style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px' }}
        onClick={(e) => { if (e.target === e.currentTarget && !rejectOpen) onClose?.(); }}
      >
        <div style={{ backgroundColor: '#fff', borderRadius: '20px', width: '100%', maxWidth: '960px', maxHeight: '92vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
          {/* Header */}
          <div style={{ position: 'sticky', top: 0, backgroundColor: '#fff', zIndex: 5, padding: '20px 24px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <h2 style={{ fontSize: '19px', fontWeight: 700, color: '#111827', margin: 0 }}>
                  {v.full_name || 'Usuario'}
                </h2>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: '4px',
                  padding: '4px 10px', borderRadius: '999px',
                  fontSize: '12px', fontWeight: 600,
                  backgroundColor: badge.bg, color: badge.fg
                }}>
                  {badge.label}
                </span>
                {v.document_type_label && (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: '4px',
                    padding: '4px 10px', borderRadius: '999px',
                    fontSize: '12px', fontWeight: 600,
                    backgroundColor: '#eef2ff', color: '#4338ca',
                    border: '1px solid #c7d2fe'
                  }}>
                    {v.document_type_label}
                  </span>
                )}
              </div>
              <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
                {v.email || '—'} {v.phone_number ? ` • ${v.phone_number}` : ''}
              </p>
              {v.submitted_at && (
                <p style={{ fontSize: '12px', color: '#9ca3af', margin: '4px 0 0 0' }}>
                  Enviado {formatRelativeTime(v.submitted_at)} • {formatAbsoluteTime(v.submitted_at)}
                </p>
              )}
            </div>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 8, marginLeft: 'auto', position: 'relative', zIndex: 10 }} aria-label="Cerrar">
              <X size={22} color="#6b7280" />
            </button>
          </div>

          <div style={{ padding: '20px 24px' }}>
            {/* Documents */}
            <h3 style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6b7280', margin: '0 0 12px 0' }}>Documentos</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '14px' }}>
              {docs.map((d) => (
                <DocTile
                  key={d.label}
                  label={d.label}
                  url={d.url}
                  autoRotate={d.autoRotate}
                  onOpen={() => openLightbox(d.label)}
                />
              ))}
            </div>
            <div style={{ fontSize: '12px', color: '#9ca3af', marginTop: '8px', textAlign: 'right' }}>
              Tip: haz click en una imagen para ampliar, hacer zoom y rotar.
            </div>

            {/* User data */}
            <h3 style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6b7280', margin: '24px 0 12px 0' }}>Datos del Usuario</h3>
            <div style={{ backgroundColor: '#f9fafb', borderRadius: '14px', padding: '16px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', fontSize: '14px' }}>
              <Field icon={UserIcon} label="Nombre completo" value={v.full_name} />
              <Field icon={FileText} label="Número de documento" value={v.document_number} />
              <Field icon={FileText} label="CPF" value={maskCPF(v.cpf_number)} />
              <Field icon={Phone}    label="Teléfono" value={v.phone_number} />
              <Field icon={Mail}     label="Email" value={v.email} />
              <Field icon={Calendar} label="Fecha de envío" value={v.submitted_at ? formatAbsoluteTime(v.submitted_at) : '—'} />
            </div>

            {/* Rejection reason (if any) */}
            {status === 'rejected' && v.rejection_reason && (
              <div style={{ marginTop: '16px', padding: '14px 16px', borderRadius: '12px', backgroundColor: '#fef2f2', border: '1px solid #fecaca' }}>
                <p style={{ fontSize: '12px', fontWeight: 700, color: '#991b1b', margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Motivo del rechazo
                </p>
                <p style={{ fontSize: '14px', color: '#7f1d1d', margin: '6px 0 0 0' }}>
                  {v.rejection_reason}
                </p>
                {v.processed_by_name && (
                  <p style={{ fontSize: '12px', color: '#9b1c1c', margin: '6px 0 0 0' }}>
                    Por {v.processed_by_name} — {v.processed_at ? formatRelativeTime(v.processed_at) : '—'}
                  </p>
                )}
              </div>
            )}
            {(status === 'approved' || status === 'verified') && v.processed_by_name && (
              <div style={{ marginTop: '16px', padding: '14px 16px', borderRadius: '12px', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0' }}>
                <p style={{ fontSize: '13px', color: '#166534', margin: 0 }}>
                  <strong>Aprobado</strong> por {v.processed_by_name} — {v.processed_at ? formatRelativeTime(v.processed_at) : ''}
                </p>
              </div>
            )}

            {/* Internal note */}
            <h3 style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6b7280', margin: '24px 0 8px 0' }}>
              Nota interna <span style={{ textTransform: 'none', letterSpacing: 0, color: '#9ca3af' }}>(solo visible para admins)</span>
            </h3>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="Comentarios internos sobre este KYC…"
              style={{ width: '100%', padding: '12px 14px', borderRadius: '12px', border: '1.5px solid #e5e7eb', fontSize: '14px', fontFamily: 'inherit', outline: 'none', resize: 'vertical', boxSizing: 'border-box' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px' }}>
              <button
                onClick={loadHistory}
                style={{ background: 'none', border: 'none', color: '#6366f1', fontSize: '13px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px', padding: 0 }}
              >
                <History size={14} /> Ver historial de auditoría
              </button>
              <button
                onClick={saveNote}
                disabled={noteSaving}
                style={{ padding: '8px 16px', borderRadius: '10px', backgroundColor: '#1f2937', color: '#fff', border: 'none', fontSize: '13px', fontWeight: 600, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px', opacity: noteSaving ? 0.6 : 1 }}
              >
                {noteSaving ? <Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={14} />}
                Guardar nota
              </button>
            </div>

            {showHistory && (
              <div style={{ marginTop: '14px', padding: '14px', borderRadius: '12px', backgroundColor: '#f9fafb', border: '1px solid #e5e7eb' }}>
                <p style={{ fontSize: '12px', fontWeight: 700, color: '#374151', margin: '0 0 10px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Historial</p>
                {history.length === 0 ? (
                  <p style={{ fontSize: '13px', color: '#9ca3af', margin: 0 }}>Sin eventos.</p>
                ) : (
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {history.map((h) => (
                      <li key={h.audit_id} style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '13px', color: '#374151', paddingBottom: '10px', borderBottom: '1px dashed #e5e7eb' }}>
                        <div style={{ display: 'flex', gap: '10px', alignItems: 'baseline' }}>
                          <span style={{ minWidth: '90px', color: '#6b7280' }}>{formatRelativeTime(h.created_at)}</span>
                          <span>
                            <strong>{ACTION_LABEL[h.action] || h.action}</strong>
                            {h.admin_name ? ` — ${h.admin_name}` : ''}
                            {h.details?.final_reason ? ` (${h.details.final_reason})` : ''}
                          </span>
                        </div>
                        {h.action === 'note_updated' && (h.details?.previous_value !== undefined || h.details?.new_value !== undefined) && (
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginLeft: '100px', marginTop: '4px' }}>
                            <div style={{ padding: '8px 10px', backgroundColor: '#fef2f2', borderLeft: '3px solid #ef4444', borderRadius: '6px', fontSize: '12px' }}>
                              <div style={{ fontSize: '10px', fontWeight: 700, color: '#991b1b', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>Antes</div>
                              <div style={{ color: '#7f1d1d', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                {h.details.previous_value || <em style={{ color: '#9ca3af' }}>(vacío)</em>}
                              </div>
                            </div>
                            <div style={{ padding: '8px 10px', backgroundColor: '#f0fdf4', borderLeft: '3px solid #22c55e', borderRadius: '6px', fontSize: '12px' }}>
                              <div style={{ fontSize: '10px', fontWeight: 700, color: '#166534', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>Después</div>
                              <div style={{ color: '#14532d', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                {h.details.new_value || <em style={{ color: '#9ca3af' }}>(vacío)</em>}
                              </div>
                            </div>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Footer actions */}
          {status === 'pending' && (
            <div style={{ position: 'sticky', bottom: 0, backgroundColor: '#fff', padding: '16px 24px', borderTop: '1px solid #e5e7eb', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                onClick={() => setRejectOpen(true)}
                disabled={working}
                style={{ padding: '12px 22px', borderRadius: '12px', backgroundColor: '#fff', color: '#dc2626', border: '1.5px solid #dc2626', fontWeight: 600, cursor: 'pointer', fontSize: '14px', display: 'inline-flex', alignItems: 'center', gap: '8px' }}
              >
                <XCircle size={18} /> Rechazar
              </button>
              <button
                onClick={approve}
                disabled={working}
                style={{ padding: '12px 22px', borderRadius: '12px', backgroundColor: '#16a34a', color: '#fff', border: 'none', fontWeight: 600, cursor: 'pointer', fontSize: '14px', display: 'inline-flex', alignItems: 'center', gap: '8px', opacity: working ? 0.7 : 1 }}
              >
                {working ? <Loader size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <CheckCircle2 size={18} />}
                Aprobar KYC
              </button>
            </div>
          )}
        </div>
      </div>

      {lightboxIndex !== null && (
        <ImageLightbox
          images={availableDocs.map((d) => ({ url: d.url, label: d.label }))}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}

      {rejectOpen && (
        <KycRejectModal
          verification={v}
          onClose={() => setRejectOpen(false)}
          onSuccess={() => { onChanged?.(); onClose?.(); }}
        />
      )}
    </>
  );
}

const ACTION_LABEL = {
  submitted: 'Documentos enviados',
  approved: 'Aprobado',
  rejected: 'Rechazado',
  note_updated: 'Nota interna actualizada',
};

function Field({ icon: Icon, label, value }) {
  return (
    <div>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#6b7280', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>
        {Icon && <Icon size={13} />} {label}
      </div>
      <div style={{ color: '#111827', fontWeight: 500, fontSize: '14px', wordBreak: 'break-word' }}>{value || '—'}</div>
    </div>
  );
}
