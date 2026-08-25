import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Lock, Shield } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { useAuth } from '../contexts/AuthContext';
import { validarPassword, PASSWORD_HELP_TEXT } from '../utils/passwordPolicy';

export default function ForceChangePassword() {
  const navigate = useNavigate();
  const { logout, clearMustChangePassword, refreshUser } = useAuth();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!newPassword || !confirmPassword) {
      toast.error('Completa todos los campos');
      return;
    }
    
    const errorPassword = validarPassword(newPassword);
    if (errorPassword) {
      toast.error(errorPassword);
      return;
    }
    
    if (newPassword !== confirmPassword) {
      toast.error('Las contraseñas no coinciden');
      return;
    }
    
    setLoading(true);
    try {
      await api.post('/auth/set-new-password', {
        new_password: newPassword,
        confirm_password: confirmPassword
      });
      
      // Clear the must_change_password flag and refresh user data
      clearMustChangePassword();
      await refreshUser();
      
      toast.success('¡Contraseña actualizada exitosamente!');
      navigate('/');
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

  const inputStyle = {
    width: '100%',
    padding: '16px 48px 16px 16px',
    borderRadius: '14px',
    border: '1px solid #d1d5db',
    fontSize: '16px',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s'
  };

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#f5f5f5',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px'
    }}>
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '24px',
        padding: '40px 32px',
        width: '100%',
        maxWidth: '420px',
        boxShadow: '0 4px 24px rgba(0,0,0,0.08)'
      }}>
        {/* Icon */}
        <div style={{
          width: '72px',
          height: '72px',
          borderRadius: '20px',
          background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 24px'
        }}>
          <Shield style={{ width: '36px', height: '36px', color: '#d97706' }} />
        </div>

        {/* Title */}
        <h1 style={{
          fontSize: '24px',
          fontWeight: '700',
          color: '#111827',
          textAlign: 'center',
          margin: '0 0 8px 0'
        }}>
          Cambiar Contraseña
        </h1>
        
        <p style={{
          fontSize: '15px',
          color: '#6b7280',
          textAlign: 'center',
          margin: '0 0 32px 0',
          lineHeight: '1.5'
        }}>
          Tu contraseña ha sido restablecida por un administrador. Por seguridad, debes establecer una nueva contraseña.
        </p>

        <form onSubmit={handleSubmit}>
          {/* New Password */}
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '8px' }}>
              Nueva contraseña
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder={PASSWORD_HELP_TEXT}
                style={inputStyle}
                data-testid="new-password-input"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '16px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#6b7280'
                }}
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
          </div>

          {/* Confirm Password */}
          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '8px' }}>
              Confirmar contraseña
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showConfirm ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repite la contraseña"
                style={inputStyle}
                data-testid="confirm-password-input"
              />
              <button
                type="button"
                onClick={() => setShowConfirm(!showConfirm)}
                style={{
                  position: 'absolute',
                  right: '16px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#6b7280'
                }}
              >
                {showConfirm ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            {confirmPassword && newPassword !== confirmPassword && (
              <p style={{ fontSize: '13px', color: '#ef4444', margin: '6px 0 0 0' }}>Las contraseñas no coinciden</p>
            )}
            {confirmPassword && newPassword === confirmPassword && !validarPassword(newPassword) && (
              <p style={{ fontSize: '13px', color: '#16a34a', margin: '6px 0 0 0' }}>✓ Las contraseñas coinciden</p>
            )}
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading || !newPassword || !confirmPassword || newPassword !== confirmPassword}
            style={{
              width: '100%',
              padding: '16px',
              borderRadius: '14px',
              border: 'none',
              backgroundColor: '#6366f1',
              color: '#ffffff',
              fontSize: '16px',
              fontWeight: '700',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading || !newPassword || !confirmPassword || newPassword !== confirmPassword ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px'
            }}
            data-testid="submit-new-password"
          >
            {loading ? (
              <>
                <div style={{
                  width: '20px',
                  height: '20px',
                  border: '2px solid #ffffff',
                  borderTopColor: 'transparent',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite'
                }} />
                Guardando...
              </>
            ) : (
              <>
                <Lock size={20} />
                Establecer Nueva Contraseña
              </>
            )}
          </button>
        </form>

        {/* Logout Option */}
        <button
          onClick={handleLogout}
          style={{
            width: '100%',
            padding: '14px',
            marginTop: '16px',
            borderRadius: '14px',
            border: '1px solid #e5e7eb',
            backgroundColor: 'transparent',
            color: '#6b7280',
            fontSize: '14px',
            fontWeight: '500',
            cursor: 'pointer'
          }}
        >
          Cerrar sesión
        </button>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
