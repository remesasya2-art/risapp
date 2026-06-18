import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { Lock, ShieldCheck, AlertTriangle } from 'lucide-react';

export default function PinSettings({ user }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [password, setPassword] = useState('');
  const [pin, setPin] = useState('');
  const [pin2, setPin2] = useState('');
  const [busy, setBusy] = useState(false);

  const esSuperAdmin = user?.role === 'super_admin';
  const verificado = user?.verification_status === 'verified';

  const cargarEstado = async () => {
    try {
      const res = await api.get('/pin/status');
      setStatus(res.data);
    } catch (e) {
      // si falla, se asume sin PIN
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!esSuperAdmin && verificado) cargarEstado();
    else setLoading(false);
  }, []);

  // El PIN no aplica a super_admin (exento de confirmar transacciones con PIN)
  if (esSuperAdmin) return null;

  const onlyDigits = (v) => v.replace(/\D/g, '').slice(0, 4);

  const limpiar = () => { setPassword(''); setPin(''); setPin2(''); setShowForm(false); };

  const guardar = async () => {
    if (!password) { toast.error('Ingresa tu contraseña'); return; }
    if (pin.length !== 4) { toast.error('El PIN debe ser de 4 dígitos'); return; }
    if (pin !== pin2) { toast.error('Los PIN no coinciden'); return; }
    try {
      setBusy(true);
      await api.post('/pin/set', { password, pin });
      toast.success('PIN configurado');
      limpiar();
      await cargarEstado();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al configurar el PIN');
    } finally {
      setBusy(false);
    }
  };

  const desactivar = async () => {
    const pwd = window.prompt('Para desactivar el PIN, ingresa tu contraseña:');
    if (pwd === null) return;
    if (!pwd) { toast.error('Contraseña requerida'); return; }
    try {
      setBusy(true);
      await api.post('/pin/disable', { password: pwd });
      toast.success('PIN desactivado');
      await cargarEstado();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al desactivar el PIN');
    } finally {
      setBusy(false);
    }
  };

  const card = {
    backgroundColor: '#fff', borderRadius: '16px', padding: '20px',
    border: '1px solid #eef0f4', marginBottom: '16px',
  };
  const input = {
    width: '100%', padding: '12px 14px', borderRadius: '10px',
    border: '1px solid #e5e7eb', fontSize: '15px', boxSizing: 'border-box',
  };
  const label = { fontSize: '13px', fontWeight: 600, color: '#374151', margin: '0 0 6px 0', display: 'block' };

  const Header = () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
      <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Lock size={20} color="#4F46E5" />
      </div>
      <div>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#111827', margin: 0 }}>PIN de seguridad</h3>
        <p style={{ fontSize: '12.5px', color: '#6b7280', margin: '2px 0 0 0' }}>Para confirmar tus envíos y operaciones</p>
      </div>
    </div>
  );

  if (loading) {
    return (<div style={card}><Header /><p style={{ color: '#9ca3af', fontSize: '13px', margin: 0 }}>Cargando…</p></div>);
  }

  if (!verificado) {
    return (
      <div style={card}>
        <Header />
        <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
          Podrás configurar tu PIN cuando tu cuenta esté verificada.
        </p>
      </div>
    );
  }

  const Formulario = (
    <div style={{ marginTop: '12px' }}>
      <label style={label}>Contraseña de tu cuenta</label>
      <input type="password" style={input} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Tu contraseña" />
      <div style={{ height: '12px' }} />
      <label style={label}>Nuevo PIN (4 dígitos)</label>
      <input type="password" inputMode="numeric" style={input} value={pin}
        onChange={(e) => setPin(onlyDigits(e.target.value))} placeholder="••••" />
      <div style={{ height: '12px' }} />
      <label style={label}>Repite el PIN</label>
      <input type="password" inputMode="numeric" style={input} value={pin2}
        onChange={(e) => setPin2(onlyDigits(e.target.value))} placeholder="••••" />
      <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
        <button onClick={guardar} disabled={busy} style={{
          flex: 1, padding: '12px', borderRadius: '10px', border: 'none',
          backgroundColor: '#6366f1', color: '#fff', fontWeight: 700, cursor: 'pointer',
        }}>{busy ? 'Guardando…' : 'Guardar PIN'}</button>
        <button onClick={limpiar} disabled={busy} style={{
          padding: '12px 16px', borderRadius: '10px', border: '1px solid #e5e7eb',
          backgroundColor: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer',
        }}>Cancelar</button>
      </div>
    </div>
  );

  return (
    <div style={card}>
      <Header />
      {status?.must_reset && (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '10px 12px', backgroundColor: '#FEF2F2', border: '1px solid #FECACA', borderRadius: '10px', marginBottom: '12px' }}>
          <AlertTriangle size={16} color="#dc2626" style={{ marginTop: '1px', flexShrink: 0 }} />
          <span style={{ fontSize: '13px', color: '#b91c1c' }}>Tu PIN fue desactivado por seguridad tras varios intentos fallidos. Configúralo de nuevo.</span>
        </div>
      )}
      {status?.locked && !status?.must_reset && (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '10px 12px', backgroundColor: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: '10px', marginBottom: '12px' }}>
          <AlertTriangle size={16} color="#D97706" />
          <span style={{ fontSize: '13px', color: '#92400e' }}>Tu PIN está bloqueado temporalmente por intentos fallidos.</span>
        </div>
      )}
      {showForm ? (
        Formulario
      ) : status?.has_pin && !status?.must_reset ? (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#059669', fontSize: '14px', fontWeight: 600, marginBottom: '14px' }}>
            <ShieldCheck size={18} /> PIN activo
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button onClick={() => setShowForm(true)} style={{
              padding: '10px 16px', borderRadius: '10px', border: '1px solid #6366f1',
              backgroundColor: '#fff', color: '#4F46E5', fontWeight: 700, cursor: 'pointer',
            }}>Cambiar PIN</button>
            <button onClick={desactivar} disabled={busy} style={{
              padding: '10px 16px', borderRadius: '10px', border: '1.5px solid #dc2626',
              backgroundColor: '#fff', color: '#dc2626', fontWeight: 700, cursor: 'pointer',
            }}>Desactivar</button>
          </div>
        </div>
      ) : (
        <div>
          <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 12px 0' }}>
            Aún no tienes un PIN. Configúralo para confirmar tus operaciones de forma más segura.
          </p>
          <button onClick={() => setShowForm(true)} style={{
            padding: '12px 18px', borderRadius: '10px', border: 'none',
            backgroundColor: '#6366f1', color: '#fff', fontWeight: 700, cursor: 'pointer',
          }}>Configurar PIN</button>
        </div>
      )}
    </div>
  );
}
