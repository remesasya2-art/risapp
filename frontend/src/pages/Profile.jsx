import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, User, Mail, Phone, Shield, Lock, LogOut, 
  CheckCircle, AlertCircle, Clock, ChevronRight, Bell, BellOff, Gem, Crown, Settings, Users, Gift
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { validarPassword, PASSWORD_HELP_TEXT } from '../utils/passwordPolicy';
import pushService from '../utils/pushService';
import PinSettings from '../components/PinSettings';
import WebAuthnSettings from '../components/WebAuthnSettings';

// Función para enmascarar el CPF (solo muestra últimos 3 dígitos)
const maskCPF = (cpf) => {
  if (!cpf) return '';
  const cleanCPF = cpf.replace(/\D/g, '');
  if (cleanCPF.length < 3) return cpf;
  const lastThree = cleanCPF.slice(-3);
  return `***.***.**${lastThree.charAt(0)}-${lastThree.slice(1)}`;
};

// Verificar si es SuperAdmin Diamante
const isSuperAdminDiamond = (email) => {
  return email === 'marshalljulio46@gmail.com';
};

export default function Profile() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [passwordData, setPasswordData] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [loading, setLoading] = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushLoading, setPushLoading] = useState(false);
  const [pushSupported, setPushSupported] = useState(true);
  const [pushMessage, setPushMessage] = useState('');
  const [showRegenerate2FA, setShowRegenerate2FA] = useState(false);
  const [twoFACode, setTwoFACode] = useState('');
  const [newBackupCodes, setNewBackupCodes] = useState(null);
  const [loading2FA, setLoading2FA] = useState(false);

  useEffect(() => {
    checkPushStatus();
  }, []);

  const checkPushStatus = async () => {
    const supportInfo = pushService.getSupportInfo();
    
    if (!pushService.isSupported()) {
      setPushSupported(false);
      // Set specific message for iOS
      if (supportInfo.isIOS && !supportInfo.isPWA) {
        setPushMessage('En iPhone/iPad, instala la app desde Safari: "Compartir" → "Agregar a inicio"');
      } else {
        setPushMessage('Tu navegador no soporta notificaciones');
      }
      return;
    }
    
    try {
      const status = await pushService.getStatus();
      setPushEnabled(status.enabled && status.subscribed);
    } catch (error) {
      console.error('Error checking push status:', error);
    }
  };

  const handleTogglePush = async () => {
    if (!pushSupported) {
      toast.error(pushMessage || 'Tu navegador no soporta notificaciones push');
      return;
    }
    
    setPushLoading(true);
    try {
      if (pushEnabled) {
        await pushService.unsubscribe();
        setPushEnabled(false);
        toast.success('Notificaciones desactivadas');
      } else {
        await pushService.init();
        await pushService.subscribe();
        setPushEnabled(true);
        toast.success('¡Notificaciones activadas! Recibirás alertas de tus transacciones.');
      }
    } catch (error) {
      console.error('Push toggle error:', error);
      if (error.message?.includes('denegado') || error.message?.includes('Permiso')) {
        toast.error('Debes permitir las notificaciones en la configuración de tu navegador');
      } else {
        toast.error(error.message || 'Error al cambiar notificaciones');
      }
    } finally {
      setPushLoading(false);
    }
  };

  const handleTestNotification = async () => {
    try {
      await pushService.sendTestNotification();
      toast.success('Notificación de prueba enviada');
    } catch (error) {
      toast.error('Error al enviar notificación de prueba');
    }
  };

  const getVerificationStatus = () => {
    switch (user?.verification_status) {
      case 'verified': return { icon: CheckCircle, color: '#16a34a', bg: '#dcfce7', text: 'Verificado' };
      case 'pending': return { icon: Clock, color: '#d97706', bg: '#fef3c7', text: 'Pendiente' };
      case 'rejected': return { icon: AlertCircle, color: '#dc2626', bg: '#fee2e2', text: 'Rechazado' };
      default: return { icon: Shield, color: '#6b7280', bg: '#f3f4f6', text: 'Sin verificar' };
    }
  };

  const status = getVerificationStatus();
  const StatusIcon = status.icon;

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      toast.error('Las contraseñas no coinciden');
      return;
    }
    const errorPassword = validarPassword(passwordData.newPassword);
    if (errorPassword) {
      toast.error(errorPassword);
      return;
    }
    setLoading(true);
    try {
      await api.post('/auth/change-password', {
        current_password: passwordData.currentPassword,
        new_password: passwordData.newPassword,
        confirm_password: passwordData.confirmPassword,
        selfie_image: 'data:image/png;base64,placeholder',
      });
      toast.success('Contraseña actualizada');
      setShowChangePassword(false);
      setPasswordData({ currentPassword: '', newPassword: '', confirmPassword: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al cambiar contraseña');
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerateBackupCodes = async (e) => {
    e.preventDefault();
    if (twoFACode.length !== 6) {
      toast.error('Ingresa el código de 6 dígitos de tu app de autenticación');
      return;
    }
    setLoading2FA(true);
    try {
      const { data } = await api.post('/auth/2fa/regenerate-backup-codes', { code: twoFACode });
      setNewBackupCodes(data.backup_codes);
      setTwoFACode('');
      toast.success('Códigos de respaldo regenerados');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al regenerar códigos');
    } finally {
      setLoading2FA(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const pageStyle = {
    minHeight: '100vh',
    background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)',
    fontFamily: 'Inter, Helvetica, -apple-system, sans-serif'
  };

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
    border: '1px solid #e5e7eb'
  };

  const inputStyle = {
    width: '100%',
    padding: '14px 16px',
    borderRadius: '12px',
    border: '1px solid #d1d5db',
    fontSize: '14px',
    outline: 'none'
  };

  return (
    <div style={pageStyle}>
      <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
          <button 
            onClick={() => navigate(-1)} 
            style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.8)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          >
            <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
          </button>
          <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Mi Perfil</h1>
        </div>

        {/* Profile Card */}
        <div style={{ ...cardStyle, padding: '24px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
            {user?.picture ? (
              <img src={user.picture} alt={user.name} style={{ width: '80px', height: '80px', borderRadius: '50%', objectFit: 'cover', border: '4px solid #ffffff', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />
            ) : (
              <div style={{ width: '80px', height: '80px', borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ffffff', fontSize: '28px', fontWeight: '700', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}>
                {user?.name?.charAt(0)?.toUpperCase() || 'U'}
              </div>
            )}
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: '0 0 4px 0' }}>{user?.full_name || user?.name}</h2>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 8px 0' }}>{user?.email}</p>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 10px', borderRadius: '9999px', backgroundColor: status.bg, color: status.color, fontSize: '12px', fontWeight: '600' }}>
                <StatusIcon style={{ width: '14px', height: '14px' }} />
                {status.text}
              </div>
            </div>
          </div>

          {/* Info Items */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
              <Mail style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
              <div>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: 0 }}>Email</p>
                <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>{user?.email}</p>
              </div>
            </div>
            {user?.phone && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                <Phone style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                <div>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: 0 }}>Teléfono</p>
                  <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>{user.phone}</p>
                </div>
              </div>
            )}
            {user?.cpf_number && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                <Shield style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                <div>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: 0 }}>CPF</p>
                  <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>{maskCPF(user.cpf_number)}</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Verification Card */}
        {user?.verification_status !== 'verified' && (
          <button onClick={() => navigate('/verification')} style={{ width: '100%', padding: '16px', backgroundColor: '#fef3c7', border: '1px solid #fcd34d', borderRadius: '16px', cursor: 'pointer', marginBottom: '16px', textAlign: 'left' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#fde68a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Shield style={{ width: '20px', height: '20px', color: '#d97706' }} />
                </div>
                <div>
                  <p style={{ fontSize: '14px', fontWeight: '600', color: '#92400e', margin: 0 }}>Verificar identidad</p>
                  <p style={{ fontSize: '12px', color: '#a16207', margin: '2px 0 0 0' }}>Desbloquea todas las funciones</p>
                </div>
              </div>
              <ChevronRight style={{ width: '20px', height: '20px', color: '#d97706' }} />
            </div>
          </button>
        )}

        {/* Notifications Card */}
        <div style={{ ...cardStyle, padding: '20px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: pushEnabled ? '#dcfce7' : '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s' }}>
                {pushEnabled ? <Bell style={{ width: '20px', height: '20px', color: '#16a34a' }} /> : <BellOff style={{ width: '20px', height: '20px', color: '#6b7280' }} />}
              </div>
              <div>
                <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>Notificaciones Push</p>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                  {!pushSupported ? 'No soportado' : pushEnabled ? 'Activadas' : 'Desactivadas'}
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {pushEnabled && (
                <button 
                  onClick={handleTestNotification}
                  style={{ padding: '8px 12px', backgroundColor: '#f3f4f6', borderRadius: '8px', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: '500', color: '#374151' }}
                  data-testid="test-notification-btn"
                >
                  Probar
                </button>
              )}
              <button
                onClick={handleTogglePush}
                disabled={!pushSupported || pushLoading}
                style={{
                  width: '52px', height: '28px', borderRadius: '14px', border: 'none', cursor: pushSupported ? 'pointer' : 'not-allowed',
                  backgroundColor: pushEnabled ? '#16a34a' : '#d1d5db', position: 'relative', transition: 'all 0.2s',
                  opacity: pushLoading || !pushSupported ? 0.5 : 1
                }}
                data-testid="toggle-push-btn"
              >
                <div style={{
                  width: '24px', height: '24px', borderRadius: '50%', backgroundColor: '#ffffff',
                  position: 'absolute', top: '2px', left: pushEnabled ? '26px' : '2px',
                  transition: 'all 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)'
                }} />
              </button>
            </div>
          </div>
          {!pushSupported && pushMessage && (
            <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#fef3c7', borderRadius: '8px', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <AlertCircle style={{ width: '16px', height: '16px', color: '#d97706', flexShrink: 0, marginTop: '2px' }} />
              <p style={{ fontSize: '12px', color: '#92400e', margin: 0, lineHeight: '1.4' }}>{pushMessage}</p>
            </div>
          )}
        </div>

        {/* PIN de seguridad */}
        <PinSettings user={user} />

        {/* Ingreso con huella */}
        <WebAuthnSettings />
        {/* Gestionar 2FA (solo super_admin) */}
        {isSuperAdminDiamond(user?.email) && (
          <div style={{ ...cardStyle, padding: '20px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Shield style={{ width: '20px', height: '20px', color: '#6b7280' }} />
                </div>
                <div>
                  <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>Códigos de respaldo 2FA</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>Genera 10 nuevos códigos de un solo uso</p>
                </div>
              </div>
              <button
                onClick={() => { setShowRegenerate2FA(true); setNewBackupCodes(null); setTwoFACode(''); }}
                style={{ padding: '10px 16px', backgroundColor: '#f3f4f6', border: 'none', borderRadius: '10px', cursor: 'pointer', fontSize: '13px', fontWeight: '600', color: '#374151' }}
              >
                Regenerar
              </button>
            </div>
          </div>
        )}

        {showRegenerate2FA && (
          <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', zIndex: 1000 }}>
            <div style={{ ...cardStyle, padding: '24px', width: '100%', maxWidth: '400px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: '0 0 16px 0' }}>Regenerar códigos de respaldo</h3>
              {!newBackupCodes ? (
                <form onSubmit={handleRegenerateBackupCodes} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Ingresa el código de 6 dígitos de tu app de autenticación para generar 10 nuevos códigos. Los códigos anteriores dejarán de funcionar.</p>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="000000"
                    value={twoFACode}
                    onChange={(e) => setTwoFACode(e.target.value.replace(/\D/g, ''))}
                    style={{ ...inputStyle, textAlign: 'center', fontSize: '20px', letterSpacing: '4px' }}
                  />
                  <div style={{ display: 'flex', gap: '12px' }}>
                    <button type="button" onClick={() => setShowRegenerate2FA(false)} style={{ flex: 1, padding: '14px', backgroundColor: '#f3f4f6', border: 'none', borderRadius: '12px', cursor: 'pointer', fontSize: '14px', fontWeight: '600', color: '#374151' }}>Cancelar</button>
                    <button type="submit" disabled={loading2FA} style={{ flex: 1, padding: '14px', backgroundColor: '#6366f1', border: 'none', borderRadius: '12px', cursor: 'pointer', fontSize: '14px', fontWeight: '600', color: '#ffffff', opacity: loading2FA ? 0.6 : 1 }}>
                      {loading2FA ? 'Verificando...' : 'Confirmar'}
                    </button>
                  </div>
                </form>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <p style={{ fontSize: '13px', color: '#dc2626', fontWeight: '600', margin: 0 }}>Guarda estos códigos en un lugar seguro. No se mostrarán de nuevo.</p>
                  <div style={{ backgroundColor: '#f8f9fa', borderRadius: '12px', padding: '16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontFamily: 'monospace', fontSize: '14px' }}>
                    {newBackupCodes.map((code, i) => (
                      <div key={i} style={{ color: '#111827' }}>{code}</div>
                    ))}
                  </div>
                  <button onClick={() => { setShowRegenerate2FA(false); setNewBackupCodes(null); }} style={{ padding: '14px', backgroundColor: '#6366f1', border: 'none', borderRadius: '12px', cursor: 'pointer', fontSize: '14px', fontWeight: '600', color: '#ffffff' }}>
                    Ya guardé mis códigos
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Partner Dashboard Button (only for socios) */}
        {user?.role === 'socio' && (
          <Link to="/partner" style={{ textDecoration: 'none' }}>
            <div style={{ 
              ...cardStyle, 
              padding: '20px', 
              marginBottom: '16px',
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              color: '#ffffff',
              cursor: 'pointer'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '48px', height: '48px', borderRadius: '14px', backgroundColor: 'rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Gift style={{ width: '24px', height: '24px', color: '#ffffff' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '16px', fontWeight: '600', margin: 0 }}>Panel de Socio</p>
                    <p style={{ fontSize: '13px', opacity: 0.9, margin: '4px 0 0 0' }}>Ver referidos y ganancias</p>
                  </div>
                </div>
                <ChevronRight style={{ width: '24px', height: '24px', opacity: 0.9 }} />
              </div>
            </div>
          </Link>
        )}

        {/* Gestor Dashboard Button (only for socio_gestor) */}
        {user?.role === 'socio_gestor' && (
          <Link to="/gestor" style={{ textDecoration: 'none' }}>
            <div style={{ 
              ...cardStyle, 
              padding: '20px', 
              marginBottom: '16px',
              background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
              color: '#ffffff',
              cursor: 'pointer'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '48px', height: '48px', borderRadius: '14px', backgroundColor: 'rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Users style={{ width: '24px', height: '24px', color: '#ffffff' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '16px', fontWeight: '600', margin: 0 }}>Panel Gestor</p>
                    <p style={{ fontSize: '13px', opacity: 0.9, margin: '4px 0 0 0' }}>Procesar envíos de terceros</p>
                  </div>
                </div>
                <ChevronRight style={{ width: '24px', height: '24px', opacity: 0.9 }} />
              </div>
            </div>
          </Link>
        )}

        {/* Actions */}
        <div style={{ ...cardStyle, overflow: 'hidden' }}>
          <button onClick={() => setShowChangePassword(true)} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', backgroundColor: 'transparent', border: 'none', borderBottom: '1px solid #e5e7eb', cursor: 'pointer' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Lock style={{ width: '20px', height: '20px', color: '#2563eb' }} />
              </div>
              <span style={{ fontSize: '14px', fontWeight: '500', color: '#111827' }}>Cambiar contraseña</span>
            </div>
            <ChevronRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
          </button>
          <button onClick={handleLogout} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', backgroundColor: 'transparent', border: 'none', cursor: 'pointer' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <LogOut style={{ width: '20px', height: '20px', color: '#dc2626' }} />
              </div>
              <span style={{ fontSize: '14px', fontWeight: '500', color: '#dc2626' }}>Cerrar sesión</span>
            </div>
          </button>
        </div>

        {/* Role Badge */}
        {(user?.role === 'admin' || user?.role === 'super_admin') && (
          isSuperAdminDiamond(user?.email) ? (
            // SuperAdministrador Diamante - Diseño Premium
            <div style={{ 
              marginTop: '16px', 
              padding: '20px', 
              background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)', 
              borderRadius: '20px', 
              color: '#ffffff',
              position: 'relative',
              overflow: 'hidden',
              border: '2px solid rgba(168, 216, 234, 0.3)'
            }}>
              {/* Efecto de brillo */}
              <div style={{
                position: 'absolute',
                top: '-50%',
                left: '-50%',
                width: '200%',
                height: '200%',
                background: 'linear-gradient(45deg, transparent 40%, rgba(168, 216, 234, 0.1) 50%, transparent 60%)',
                animation: 'shimmer 3s infinite'
              }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', position: 'relative', zIndex: 1, marginBottom: '16px' }}>
                <div style={{ 
                  width: '56px', 
                  height: '56px', 
                  borderRadius: '16px', 
                  background: 'linear-gradient(135deg, #a8d8ea 0%, #89c4e1 50%, #5eb1d8 100%)',
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  boxShadow: '0 4px 15px rgba(168, 216, 234, 0.4)'
                }}>
                  <Gem style={{ width: '28px', height: '28px', color: '#1a1a2e' }} />
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <p style={{ fontSize: '18px', fontWeight: '700', margin: 0, background: 'linear-gradient(90deg, #a8d8ea, #ffffff, #a8d8ea)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                      SuperAdministrador Diamante
                    </p>
                    <Crown style={{ width: '18px', height: '18px', color: '#a8d8ea' }} />
                  </div>
                  <p style={{ fontSize: '13px', color: '#a8d8ea', margin: 0 }}>Acceso total al sistema • Máximo nivel</p>
                </div>
              </div>
              {/* Botón Panel de Administración */}
              <Link
                to="/admin"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  width: '100%',
                  padding: '14px 20px',
                  background: 'linear-gradient(135deg, #a8d8ea 0%, #5eb1d8 100%)',
                  borderRadius: '12px',
                  color: '#1a1a2e',
                  fontWeight: '600',
                  fontSize: '15px',
                  textDecoration: 'none',
                  position: 'relative',
                  zIndex: 1,
                  boxShadow: '0 4px 15px rgba(168, 216, 234, 0.3)',
                  transition: 'all 0.2s'
                }}
                data-testid="admin-panel-btn"
              >
                <Settings style={{ width: '20px', height: '20px' }} />
                Acceder al Panel de Control
              </Link>
              <style>{`
                @keyframes shimmer {
                  0% { transform: translateX(-100%) rotate(45deg); }
                  100% { transform: translateX(100%) rotate(45deg); }
                }
              `}</style>
            </div>
          ) : (
            // Administrador normal
            <Link
              to="/admin"
              style={{ 
                marginTop: '16px', 
                padding: '16px', 
                background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)', 
                borderRadius: '16px', 
                color: '#ffffff',
                textDecoration: 'none',
                display: 'block'
              }}
              data-testid="admin-panel-btn"
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Shield style={{ width: '20px', height: '20px' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '14px', fontWeight: '600', margin: 0 }}>Administrador</p>
                    <p style={{ fontSize: '12px', color: '#94a3b8', margin: '2px 0 0 0' }}>Acceder al panel de administración</p>
                  </div>
                </div>
                <ChevronRight style={{ width: '20px', height: '20px', color: '#94a3b8' }} />
              </div>
            </Link>
          )
        )}
      </div>

      {/* Change Password Modal */}
      {showChangePassword && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', width: '100%', maxWidth: '400px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
              <div style={{ width: '48px', height: '48px', borderRadius: '14px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Lock style={{ width: '24px', height: '24px', color: '#2563eb' }} />
              </div>
              <div>
                <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Cambiar contraseña</h3>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>Ingresa tu contraseña actual y la nueva</p>
              </div>
            </div>
            <form onSubmit={handleChangePassword} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Contraseña actual</label>
                <input type="password" value={passwordData.currentPassword} onChange={(e) => setPasswordData({...passwordData, currentPassword: e.target.value})} style={inputStyle} placeholder="••••••••" />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Nueva contraseña</label>
                <input type="password" value={passwordData.newPassword} onChange={(e) => setPasswordData({...passwordData, newPassword: e.target.value})} style={inputStyle} placeholder={PASSWORD_HELP_TEXT} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Confirmar nueva contraseña</label>
                <input type="password" value={passwordData.confirmPassword} onChange={(e) => setPasswordData({...passwordData, confirmPassword: e.target.value})} style={inputStyle} placeholder="••••••••" />
              </div>
              <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                <button type="button" onClick={() => setShowChangePassword(false)} style={{ flex: 1, padding: '14px', backgroundColor: '#f3f4f6', color: '#374151', borderRadius: '14px', border: 'none', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}>Cancelar</button>
                <button type="submit" disabled={loading} style={{ flex: 1, padding: '14px', backgroundColor: '#6366f1', color: '#ffffff', borderRadius: '14px', border: 'none', fontSize: '14px', fontWeight: '600', cursor: 'pointer', opacity: loading ? 0.5 : 1 }}>{loading ? 'Guardando...' : 'Guardar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
