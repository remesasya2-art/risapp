import { useState } from 'react';
import { Trash2, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';

/**
 * Super admin only. Wipes transactional data after typed confirmation.
 *
 * Props:
 *  - mode: 'all' | 'accounting'
 *  - label: button text (default based on mode)
 *  - onSuccess: callback fired after successful wipe
 *  - userRole: current user role — component hides itself unless 'super_admin'
 *  - size: 'sm' | 'md' (default 'md')
 */
export const WipeButton = ({ mode = 'all', label, onSuccess, userRole, size = 'md' }) => {
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [loading, setLoading] = useState(false);

  if (userRole !== 'super_admin') return null;

  const config = mode === 'accounting'
    ? {
        endpoint: '/admin/accounting/wipe',
        title: 'Limpiar Datos de Contabilidad',
        warning: 'Se eliminarán: bancos registrados, libro USDT, libro de bancos, operaciones de compra/venta USDT y tasas. NO se tocan las transacciones de usuarios ni sus saldos.',
        defaultLabel: 'Limpiar Contabilidad'
      }
    : {
        endpoint: '/admin/wipe-all',
        title: 'Limpiar TODA la App',
        warning: 'Se eliminarán TODAS las transacciones, pagos, retiros, verificaciones pendientes, contabilidad completa, notificaciones, mensajes de soporte y se resetean los saldos de TODOS los usuarios a 0. Los usuarios, tasas y configuración se conservan.',
        defaultLabel: 'Limpiar TODO'
      };

  const handleWipe = async () => {
    if (confirmText !== 'CONFIRMAR') {
      toast.error('Debes escribir CONFIRMAR exactamente');
      return;
    }
    setLoading(true);
    try {
      const res = await api.post(config.endpoint, { confirmation: 'CONFIRMAR' });
      toast.success(`${res.data.total_deleted || 0} registros eliminados`);
      setOpen(false);
      setConfirmText('');
      if (onSuccess) onSuccess();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error al limpiar');
    } finally {
      setLoading(false);
    }
  };

  const btnStyle = size === 'sm'
    ? { padding: '8px 12px', fontSize: '12px' }
    : { padding: '10px 16px', fontSize: '13px' };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        style={{
          ...btnStyle,
          borderRadius: '10px', border: '1px solid #dc2626',
          backgroundColor: '#fff', color: '#dc2626',
          fontWeight: '600', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: '6px',
          transition: 'all 0.15s'
        }}
        onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#fef2f2'; }}
        onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#fff'; }}
        data-testid={`wipe-${mode}-btn`}
      >
        <Trash2 style={{ width: '14px', height: '14px' }} /> {label || config.defaultLabel}
      </button>

      {open && (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999, padding: '16px'
        }} onClick={() => !loading && setOpen(false)}>
          <div onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: '#fff', borderRadius: '16px', padding: '28px',
              maxWidth: '480px', width: '100%',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
            }}
            data-testid="wipe-modal"
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{
                width: '48px', height: '48px', borderRadius: '12px',
                backgroundColor: '#fef2f2', display: 'flex',
                alignItems: 'center', justifyContent: 'center'
              }}>
                <AlertTriangle style={{ width: '24px', height: '24px', color: '#dc2626' }} />
              </div>
              <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>
                {config.title}
              </h3>
            </div>

            <p style={{ fontSize: '14px', color: '#374151', lineHeight: '1.5', margin: '0 0 16px 0' }}>
              {config.warning}
            </p>

            <div style={{ padding: '12px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '10px', marginBottom: '16px' }}>
              <p style={{ fontSize: '13px', color: '#991b1b', fontWeight: '600', margin: 0 }}>
                Esta acción NO se puede deshacer.
              </p>
            </div>

            <label style={{ fontSize: '13px', color: '#374151', fontWeight: '500', display: 'block', marginBottom: '6px' }}>
              Para confirmar, escribe <strong>CONFIRMAR</strong> a continuación:
            </label>
            <input
              type="text" value={confirmText}
              onChange={e => setConfirmText(e.target.value)}
              placeholder="CONFIRMAR"
              style={{
                width: '100%', padding: '12px', borderRadius: '10px',
                border: '1px solid #d1d5db', fontSize: '15px',
                boxSizing: 'border-box', marginBottom: '16px',
                fontFamily: 'monospace', letterSpacing: '1px'
              }}
              autoFocus
              data-testid="wipe-confirm-input"
            />

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button onClick={() => { setOpen(false); setConfirmText(''); }}
                disabled={loading}
                style={{
                  padding: '10px 18px', borderRadius: '10px',
                  border: '1px solid #d1d5db', backgroundColor: '#fff',
                  color: '#374151', fontSize: '13px', fontWeight: '600',
                  cursor: loading ? 'not-allowed' : 'pointer'
                }}
                data-testid="wipe-cancel-btn"
              >Cancelar</button>
              <button onClick={handleWipe}
                disabled={loading || confirmText !== 'CONFIRMAR'}
                style={{
                  padding: '10px 18px', borderRadius: '10px',
                  border: 'none',
                  backgroundColor: confirmText === 'CONFIRMAR' ? '#dc2626' : '#fca5a5',
                  color: '#fff', fontSize: '13px', fontWeight: '700',
                  cursor: (loading || confirmText !== 'CONFIRMAR') ? 'not-allowed' : 'pointer'
                }}
                data-testid="wipe-confirm-btn"
              >
                {loading ? 'Limpiando...' : 'Sí, eliminar todo'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
