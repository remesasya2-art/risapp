import { useState } from 'react';
import { Shield, Smartphone, AlertCircle, Copy, CheckCircle2, KeyRound } from 'lucide-react';
import api from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import toast from 'react-hot-toast';

/**
 * Two-Factor Authentication Flow (enrollment or verify).
 *
 * Props:
 *   mode: 'enroll' | 'verify'
 *   pendingToken: string (received from /auth/login-password)
 *   email: string
 *   onSuccess: () => void   (called after session is set)
 */
export default function TwoFactorFlow({ mode, pendingToken, email, onSuccess }) {
  const { completeTwoFactorLogin } = useAuth();
  const [step, setStep] = useState(mode === 'enroll' ? 'init' : 'verify');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [code, setCode] = useState('');

  // Enrollment state
  const [qrUrl, setQrUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [backupCodes, setBackupCodes] = useState([]);

  const startEnroll = async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await api.post('/auth/2fa/enroll-init', { pending_token: pendingToken });
      setQrUrl(data.qr_code_data_url);
      setSecret(data.secret);
      setStep('scan');
    } catch (e) {
      setError(e.response?.data?.detail || 'Error al generar QR');
    } finally {
      setLoading(false);
    }
  };

  const confirmEnroll = async (e) => {
    e?.preventDefault?.();
    if (code.length !== 6) return;
    setLoading(true);
    setError('');
    try {
      const { data } = await api.post('/auth/2fa/enroll-confirm', {
        pending_token: pendingToken,
        code,
      });
      setBackupCodes(data.backup_codes);
      completeTwoFactorLogin(data.session_token, data.user);
      setStep('backup');
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Código incorrecto');
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async (e) => {
    e?.preventDefault?.();
    if (code.length < 6) return;
    setLoading(true);
    setError('');
    try {
      const { data } = await api.post('/auth/2fa/verify', {
        pending_token: pendingToken,
        code: code.trim().toUpperCase(),
      });
      completeTwoFactorLogin(data.session_token, data.user);
      if (data.used_backup_code) {
        toast.warning(`Código de respaldo usado. Te quedan ${data.backup_codes_remaining}.`);
      }
      onSuccess?.();
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Código inválido');
    } finally {
      setLoading(false);
    }
  };

  const copy = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copiado al portapapeles');
  };

  // ----- Render: enrollment intro -----
  if (step === 'init') {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <Shield size={48} color="#dc2626" />
          <h2 style={styles.title}>Configura 2FA</h2>
          <p style={styles.subtitle}>
            Como super administrador debes configurar autenticación en dos pasos para proteger tu cuenta.
          </p>
        </div>
        <div style={styles.info}>
          <Smartphone size={20} color="#6366f1" />
          <div>
            <p style={{ fontWeight: 600, margin: 0 }}>Necesitas una app de autenticación:</p>
            <p style={styles.appList}>Google Authenticator · Authy · Microsoft Authenticator</p>
          </div>
        </div>
        {error && <div style={styles.error}><AlertCircle size={16} /> {error}</div>}
        <button data-testid="2fa-start-enroll-btn" onClick={startEnroll} disabled={loading} style={styles.primaryBtn}>
          {loading ? 'Generando QR...' : 'Comenzar configuración'}
        </button>
      </div>
    );
  }

  // ----- Render: QR scan -----
  if (step === 'scan') {
    return (
      <div style={styles.container}>
        <h2 style={styles.title}>Escanea el código QR</h2>
        <p style={styles.subtitle}>Abre tu app de autenticación y escanea esta imagen:</p>
        <div style={styles.qrBox}>
          <img src={qrUrl} alt="QR Code 2FA" style={{ width: 220, height: 220 }} data-testid="2fa-qr-image" />
        </div>
        <div style={styles.secretBox}>
          <p style={{ fontSize: 12, color: '#6b7280', margin: 0 }}>O ingresa este código manualmente:</p>
          <div style={styles.secretRow}>
            <code data-testid="2fa-secret-text" style={styles.secretText}>{secret}</code>
            <button onClick={() => copy(secret)} style={styles.copyBtn}><Copy size={14} /></button>
          </div>
        </div>
        <form onSubmit={confirmEnroll}>
          <label style={styles.label}>Ingresa el código de 6 dígitos que aparece en tu app:</label>
          <input
            data-testid="2fa-enroll-code-input"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            style={styles.codeInput}
            autoFocus
          />
          {error && <div style={styles.error}><AlertCircle size={16} /> {error}</div>}
          <button data-testid="2fa-enroll-confirm-btn" type="submit" disabled={loading || code.length !== 6} style={styles.primaryBtn}>
            {loading ? 'Verificando...' : 'Confirmar y activar'}
          </button>
        </form>
      </div>
    );
  }

  // ----- Render: backup codes -----
  if (step === 'backup') {
    return (
      <div style={styles.container}>
        <div style={styles.success}>
          <CheckCircle2 size={48} color="#16a34a" />
          <h2 style={styles.title}>2FA activado</h2>
        </div>
        <div style={styles.warningBox}>
          <strong style={{ color: '#92400e' }}>⚠️ GUARDA ESTOS CÓDIGOS DE RESPALDO</strong>
          <p style={{ fontSize: 13, color: '#78350f', margin: '8px 0' }}>
            Úsalos si pierdes acceso a tu app. Cada uno funciona una sola vez. NO se mostrarán de nuevo.
          </p>
        </div>
        <div style={styles.backupGrid} data-testid="2fa-backup-codes-list">
          {backupCodes.map((c) => (
            <code key={c} style={styles.backupCode}>{c}</code>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button onClick={() => copy(backupCodes.join('\n'))} style={styles.secondaryBtn}>
            <Copy size={14} /> Copiar todos
          </button>
          <button data-testid="2fa-finish-enroll-btn" onClick={() => onSuccess?.()} style={styles.primaryBtn}>
            Continuar
          </button>
        </div>
      </div>
    );
  }

  // ----- Render: login verify -----
  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <Shield size={48} color="#dc2626" />
        <h2 style={styles.title}>Verificación 2FA</h2>
        <p style={styles.subtitle}>
          Ingresa el código de 6 dígitos de tu app de autenticación para acceder a la cuenta de <strong>{email}</strong>
        </p>
      </div>
      <form onSubmit={verifyCode}>
        <input
          data-testid="2fa-verify-code-input"
          type="text"
          maxLength={10}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="123456 ó CÓDIGO RESPALDO"
          style={styles.codeInput}
          autoFocus
        />
        {error && <div style={styles.error}><AlertCircle size={16} /> {error}</div>}
        <button data-testid="2fa-verify-submit-btn" type="submit" disabled={loading || code.length < 6} style={styles.primaryBtn}>
          {loading ? 'Verificando...' : 'Verificar'}
        </button>
      </form>
      <div style={{ marginTop: 16, textAlign: 'center', fontSize: 12, color: '#6b7280' }}>
        <KeyRound size={12} style={{ display: 'inline', marginRight: 4 }} />
        ¿Perdiste tu app? Usa uno de tus códigos de respaldo (10 caracteres).
      </div>
    </div>
  );
}

const styles = {
  container: { maxWidth: 440, margin: '0 auto', padding: '24px', backgroundColor: '#fff', borderRadius: 16, border: '1px solid #e5e7eb' },
  header: { textAlign: 'center', marginBottom: 24 },
  success: { textAlign: 'center', marginBottom: 16 },
  title: { fontSize: 22, fontWeight: 700, margin: '12px 0 6px', color: '#111827' },
  subtitle: { fontSize: 14, color: '#6b7280', margin: 0, lineHeight: 1.4 },
  info: { display: 'flex', gap: 10, padding: 12, backgroundColor: '#eef2ff', borderRadius: 10, marginBottom: 16 },
  appList: { fontSize: 12, color: '#4338ca', margin: '4px 0 0 0' },
  error: { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', backgroundColor: '#fef2f2', color: '#991b1b', borderRadius: 8, fontSize: 13, marginTop: 12 },
  primaryBtn: { width: '100%', padding: '12px', borderRadius: 10, border: 'none', backgroundColor: '#dc2626', color: '#fff', fontSize: 14, fontWeight: 700, cursor: 'pointer', marginTop: 12 },
  secondaryBtn: { flex: 1, padding: '12px', borderRadius: 10, border: '1px solid #d1d5db', backgroundColor: '#fff', color: '#374151', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 },
  qrBox: { display: 'flex', justifyContent: 'center', padding: 16, backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, margin: '12px 0' },
  secretBox: { padding: 12, backgroundColor: '#f9fafb', borderRadius: 10, marginBottom: 16 },
  secretRow: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 },
  secretText: { flex: 1, fontFamily: 'monospace', fontSize: 13, color: '#111827', letterSpacing: 0.5, wordBreak: 'break-all' },
  copyBtn: { padding: 6, borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff', cursor: 'pointer' },
  label: { fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 },
  codeInput: { width: '100%', padding: '14px', fontSize: 22, textAlign: 'center', letterSpacing: 6, fontFamily: 'monospace', border: '2px solid #e5e7eb', borderRadius: 10, outline: 'none', boxSizing: 'border-box' },
  warningBox: { padding: 12, backgroundColor: '#fef3c7', border: '1px solid #fde68a', borderRadius: 10, marginBottom: 12 },
  backupGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, fontFamily: 'monospace' },
  backupCode: { padding: '8px 10px', backgroundColor: '#f3f4f6', borderRadius: 6, fontSize: 13, textAlign: 'center', letterSpacing: 1 },
};
