import { useEffect, useState } from 'react';
import { X, AlertCircle, Loader } from 'lucide-react';
import api from '../../utils/api';
import toast from 'react-hot-toast';

const FALLBACK_REASONS = [
  { code: 'illegible',       label: 'Documento ilegible o borroso' },
  { code: 'expired',         label: 'Documento vencido' },
  { code: 'data_mismatch',   label: 'Datos no coinciden con el documento' },
  { code: 'selfie_mismatch', label: 'Selfie no coincide con el documento' },
  { code: 'wrong_doc_type',  label: 'Documento no aceptado (tipo incorrecto)' },
  { code: 'other',           label: 'Otro motivo' },
];

/**
 * Modal to reject a KYC, requiring a reason code and (optionally) free text.
 *
 * Props:
 *   verification: { verification_id, full_name, ... }
 *   onClose: () => void
 *   onSuccess: () => void  // called after successful rejection
 */
export default function KycRejectModal({ verification, onClose, onSuccess }) {
  const [reasons, setReasons] = useState(FALLBACK_REASONS);
  const [code, setCode] = useState('');
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancel = false;
    api.get('/admin/kyc/rejection-reasons')
      .then((res) => { if (!cancel && Array.isArray(res.data) && res.data.length) setReasons(res.data); })
      .catch(() => { /* keep fallback */ });
    return () => { cancel = true; };
  }, []);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const canSubmit = code && (code !== 'other' || text.trim().length > 0) && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit || !verification?.verification_id) return;
    setSubmitting(true);
    try {
      await api.post(`/admin/kyc/${verification.verification_id}/reject`, {
        reason_code: code,
        reason_text: text.trim() || null,
      });
      toast.success('KYC rechazado');
      onSuccess?.();
      onClose?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al rechazar');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, padding: '20px' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
    >
      <div style={{ backgroundColor: '#fff', borderRadius: '20px', width: '100%', maxWidth: '520px', maxHeight: '90vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
        {/* Header */}
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
            <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <AlertCircle size={22} color="#dc2626" />
            </div>
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 700, color: '#111827', margin: 0 }}>Rechazar verificación</h2>
              <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
                {verification?.full_name ? `Usuario: ${verification.full_name}` : 'Selecciona un motivo'}
              </p>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <X size={20} color="#6b7280" />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px 24px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '8px' }}>
            Motivo del rechazo <span style={{ color: '#dc2626' }}>*</span>
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {reasons.map((r) => {
              const checked = code === r.code;
              return (
                <label
                  key={r.code}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 14px',
                    borderRadius: '12px', cursor: 'pointer',
                    border: checked ? '2px solid #dc2626' : '1px solid #e5e7eb',
                    backgroundColor: checked ? '#fef2f2' : '#fff',
                    transition: 'all 0.15s'
                  }}
                >
                  <input
                    type="radio"
                    name="kyc-reason"
                    value={r.code}
                    checked={checked}
                    onChange={() => setCode(r.code)}
                    style={{ accentColor: '#dc2626', cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: '14px', color: '#111827' }}>{r.label}</span>
                </label>
              );
            })}
          </div>

          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#374151', margin: '18px 0 8px 0' }}>
            Comentario {code === 'other' && <span style={{ color: '#dc2626' }}>* (obligatorio)</span>}
            <span style={{ color: '#9ca3af', fontWeight: 400, marginLeft: '6px' }}>(visible para el usuario)</span>
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            maxLength={500}
            placeholder={code === 'other' ? 'Describe el motivo del rechazo…' : 'Detalles adicionales (opcional)…'}
            style={{
              width: '100%', padding: '12px 14px', borderRadius: '12px',
              border: '1.5px solid #e5e7eb', fontSize: '14px',
              fontFamily: 'inherit', outline: 'none', resize: 'vertical',
              boxSizing: 'border-box'
            }}
          />
          <div style={{ fontSize: '11px', color: '#9ca3af', marginTop: '4px', textAlign: 'right' }}>
            {text.length} / 500
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '16px 24px', borderTop: '1px solid #e5e7eb', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            onClick={onClose}
            disabled={submitting}
            style={{
              padding: '10px 20px', borderRadius: '12px',
              backgroundColor: '#f3f4f6', color: '#374151',
              border: 'none', fontWeight: 600, cursor: 'pointer',
              opacity: submitting ? 0.6 : 1, fontSize: '14px'
            }}
          >
            Cancelar
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              padding: '10px 20px', borderRadius: '12px',
              backgroundColor: !canSubmit ? '#fca5a5' : '#dc2626',
              color: 'white', border: 'none', fontWeight: 600,
              cursor: !canSubmit ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              display: 'inline-flex', alignItems: 'center', gap: '8px'
            }}
          >
            {submitting && <Loader size={16} style={{ animation: 'spin 1s linear infinite' }} />}
            Confirmar rechazo
          </button>
        </div>
      </div>
    </div>
  );
}
