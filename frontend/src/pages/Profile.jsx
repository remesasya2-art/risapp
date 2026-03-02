import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, User, Mail, Phone, Shield, Lock, LogOut, 
  CheckCircle, AlertCircle, Clock, ChevronRight
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

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
    if (passwordData.newPassword.length < 7) {
      toast.error('La contraseña debe tener al menos 7 caracteres');
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
                  <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>{user.cpf_number}</p>
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
          <div style={{ marginTop: '16px', padding: '16px', background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)', borderRadius: '16px', color: '#ffffff' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Shield style={{ width: '20px', height: '20px' }} />
              </div>
              <div>
                <p style={{ fontSize: '14px', fontWeight: '600', margin: 0 }}>{user.role === 'super_admin' ? 'Super Administrador' : 'Administrador'}</p>
                <p style={{ fontSize: '12px', color: '#94a3b8', margin: '2px 0 0 0' }}>Acceso al panel de administración</p>
              </div>
            </div>
          </div>
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
                <input type="password" value={passwordData.newPassword} onChange={(e) => setPasswordData({...passwordData, newPassword: e.target.value})} style={inputStyle} placeholder="Mínimo 7 caracteres" />
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
