import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { activarHuella, webauthnSupported } from '../utils/webauthn';
import { Fingerprint, Trash2, Plus } from 'lucide-react';

export default function WebAuthnSettings() {
  const [soportado] = useState(webauthnSupported());
  const [creds, setCreds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const cargar = async () => {
    try {
      const res = await api.get('/webauthn/credentials');
      setCreds(res.data?.credentials || []);
    } catch (e) {
      // sin credenciales o error: lista vacía
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (soportado) cargar();
    else setLoading(false);
  }, []);

  const onActivar = async () => {
    try {
      setBusy(true);
      const label = window.prompt('Nombre para este dispositivo (ej. "Mi teléfono"):', 'Mi dispositivo');
      if (label === null) { setBusy(false); return; }
      await activarHuella(label || 'Mi dispositivo');
      toast.success('Huella activada en este dispositivo');
      await cargar();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(detail || 'No se pudo activar la huella en este dispositivo');
    } finally {
      setBusy(false);
    }
  };

  const onEliminar = async (credId) => {
    if (!window.confirm('¿Eliminar el acceso con huella de este dispositivo?')) return;
    try {
      setBusy(true);
      await api.delete(`/webauthn/credentials/${encodeURIComponent(credId)}`);
      toast.success('Dispositivo eliminado');
      await cargar();
    } catch (e) {
      toast.error('No se pudo eliminar');
    } finally {
      setBusy(false);
    }
  };

  const card = {
    backgroundColor: '#fff', borderRadius: '16px', padding: '20px',
    border: '1px solid #eef0f4', marginBottom: '16px',
  };

  const Header = () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
      <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#ECFEFF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Fingerprint size={20} color="#0891B2" />
      </div>
      <div>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#111827', margin: 0 }}>Ingreso con huella</h3>
        <p style={{ fontSize: '12.5px', color: '#6b7280', margin: '2px 0 0 0' }}>Desbloqueo rápido en este dispositivo</p>
      </div>
    </div>
  );

  if (!soportado) {
    return (
      <div style={card}>
        <Header />
        <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
          Este dispositivo o navegador no permite ingreso con huella.
        </p>
      </div>
    );
  }

  return (
    <div style={card}>
      <Header />
      {loading ? (
        <p style={{ color: '#9ca3af', fontSize: '13px', margin: 0 }}>Cargando…</p>
      ) : (
        <>
          {creds.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
              {creds.map((c) => (
                <div key={c.credential_id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 12px', borderRadius: '10px', border: '1px solid #f1f2f6', backgroundColor: '#FAFAFA',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <Fingerprint size={16} color="#0891B2" />
                    <span style={{ fontSize: '13.5px', color: '#374151', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {c.label || 'Dispositivo'}
                    </span>
                  </div>
                  <button onClick={() => onEliminar(c.credential_id)} disabled={busy} style={{
                    border: 'none', background: 'none', cursor: 'pointer', color: '#dc2626', display: 'inline-flex', padding: '4px',
                  }} title="Eliminar"><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 14px 0' }}>
              Activa la huella para entrar más rápido en este dispositivo, sin escribir tu contraseña cada vez.
            </p>
          )}
          <button onClick={onActivar} disabled={busy} style={{
            display: 'inline-flex', alignItems: 'center', gap: '8px',
            padding: '12px 18px', borderRadius: '10px', border: 'none',
            backgroundColor: '#0891B2', color: '#fff', fontWeight: 700, cursor: 'pointer', opacity: busy ? 0.6 : 1,
          }}>
            <Plus size={16} /> {creds.length > 0 ? 'Activar en otro dispositivo' : 'Activar huella en este dispositivo'}
          </button>
        </>
      )}
    </div>
  );
}
