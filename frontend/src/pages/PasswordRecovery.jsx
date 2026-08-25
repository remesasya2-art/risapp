import { useState } from 'react';
import { ArrowLeft, Mail, User, Phone, FileText, Lock, CheckCircle, AlertCircle, MessageSquare, Send, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { passwordRules as evaluarReglasPassword, PASSWORD_SPECIAL_CHARS, PASSWORD_HELP_TEXT } from '../utils/passwordPolicy';

export default function PasswordRecovery({ onBack, onSuccess }) {
  const [step, setStep] = useState(1); // 1: Identity, 2: Code, 3: New Password, 4: Success
  const [loading, setLoading] = useState(false);
  const [showSupport, setShowSupport] = useState(false);
  
  // Step 1: Identity verification
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [cpf, setCpf] = useState('');
  const [documentNumber, setDocumentNumber] = useState('');
  
  // Step 2: Code verification
  const [code, setCode] = useState('');
  const [maskedEmail, setMaskedEmail] = useState('');
  
  // Step 3: New password
  const [recoveryToken, setRecoveryToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  // Support form
  const [supportEmail, setSupportEmail] = useState('');
  const [supportSubject, setSupportSubject] = useState('');
  const [supportPhone, setSupportPhone] = useState('');
  const [supportMessage, setSupportMessage] = useState('');

  const formatCpf = (value) => {
    const numbers = value.replace(/\D/g, '');
    if (numbers.length <= 3) return numbers;
    if (numbers.length <= 6) return `${numbers.slice(0, 3)}.${numbers.slice(3)}`;
    if (numbers.length <= 9) return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6)}`;
    return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6, 9)}-${numbers.slice(9, 11)}`;
  };

  // Password validation — las reglas salen de utils/passwordPolicy.js, que espeja al backend.
  const passwordRules = evaluarReglasPassword(newPassword);
  const allRulesPass = Object.values(passwordRules).every(Boolean);

  const handleVerifyIdentity = async () => {
    if (!email || !fullName || !phoneNumber || !cpf || !documentNumber) {
      toast.error('Completa todos los campos');
      return;
    }
    
    setLoading(true);
    try {
      const response = await api.post('/recovery/verify-identity', {
        email,
        full_name: fullName,
        phone_number: phoneNumber,
        cpf: cpf.replace(/\D/g, ''),
        document_number: documentNumber
      });
      
      setMaskedEmail(response.data.email_masked);
      toast.success('Código enviado a tu correo');
      setStep(2);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al verificar identidad');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async () => {
    if (!code || code.length !== 6) {
      toast.error('Ingresa el código de 6 dígitos');
      return;
    }
    
    setLoading(true);
    try {
      const response = await api.post('/recovery/verify-code', {
        email,
        code
      });
      
      setRecoveryToken(response.data.recovery_token);
      toast.success('Código verificado');
      setStep(3);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Código incorrecto');
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (newPassword !== confirmPassword) {
      toast.error('Las contraseñas no coinciden');
      return;
    }
    
    if (!allRulesPass) {
      toast.error('La contraseña no cumple los requisitos');
      return;
    }
    
    setLoading(true);
    try {
      await api.post('/recovery/reset-password', {
        email,
        recovery_token: recoveryToken,
        new_password: newPassword
      });
      
      // Mostrar pantalla de éxito
      setStep(4);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al cambiar contraseña');
    } finally {
      setLoading(false);
    }
  };

  const handleSupportSubmit = async () => {
    if (!supportEmail || !supportSubject || !supportPhone || !supportMessage) {
      toast.error('Completa todos los campos');
      return;
    }
    
    if (supportMessage.length > 200) {
      toast.error('El mensaje no puede exceder 200 caracteres');
      return;
    }
    
    setLoading(true);
    try {
      await api.post('/recovery/support-contact', {
        email: supportEmail,
        subject: supportSubject,
        phone_number: supportPhone,
        message: supportMessage
      });
      
      toast.success('Solicitud enviada. Te contactaremos pronto.');
      setShowSupport(false);
      setSupportEmail('');
      setSupportSubject('');
      setSupportPhone('');
      setSupportMessage('');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al enviar solicitud');
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    width: '100%',
    padding: '14px 16px',
    borderRadius: '12px',
    border: '1px solid #e5e7eb',
    fontSize: '16px',
    outline: 'none',
    boxSizing: 'border-box',
    transition: 'border-color 0.2s',
  };

  const buttonStyle = {
    width: '100%',
    padding: '14px',
    borderRadius: '12px',
    border: 'none',
    fontSize: '16px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s',
  };

  // Support Modal
  if (showSupport) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
        <div style={{ width: '100%', maxWidth: '440px', backgroundColor: 'white', borderRadius: '24px', boxShadow: '0 4px 24px rgba(0,0,0,0.08)', padding: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
            <button onClick={() => setShowSupport(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }}>
              <X style={{ width: '24px', height: '24px', color: '#6b7280' }} />
            </button>
            <div style={{ width: '48px', height: '48px', borderRadius: '12px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <MessageSquare style={{ width: '24px', height: '24px', color: '#2563eb' }} />
            </div>
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Contactar Soporte</h2>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>Te responderemos pronto</p>
            </div>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <Mail style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Correo electrónico
              </label>
              <input
                type="email"
                value={supportEmail}
                onChange={(e) => setSupportEmail(e.target.value)}
                style={inputStyle}
                placeholder="tu@correo.com"
              />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <FileText style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Asunto
              </label>
              <input
                type="text"
                value={supportSubject}
                onChange={(e) => setSupportSubject(e.target.value)}
                style={inputStyle}
                placeholder="Motivo de tu consulta"
              />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <Phone style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Número de contacto
              </label>
              <input
                type="tel"
                value={supportPhone}
                onChange={(e) => setSupportPhone(e.target.value)}
                style={inputStyle}
                placeholder="+55 11 99999-9999"
              />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                Mensaje ({supportMessage.length}/200)
              </label>
              <textarea
                value={supportMessage}
                onChange={(e) => e.target.value.length <= 200 && setSupportMessage(e.target.value)}
                style={{ ...inputStyle, minHeight: '100px', resize: 'vertical' }}
                placeholder="Describe brevemente tu situación..."
              />
            </div>
            
            <button
              onClick={handleSupportSubmit}
              disabled={loading}
              style={{ ...buttonStyle, backgroundColor: '#2563eb', color: 'white', opacity: loading ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
            >
              <Send style={{ width: '18px', height: '18px' }} />
              {loading ? 'Enviando...' : 'Enviar Solicitud'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
      <div style={{ width: '100%', maxWidth: '440px', backgroundColor: 'white', borderRadius: '24px', boxShadow: '0 4px 24px rgba(0,0,0,0.08)', padding: '32px' }}>
        
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
          <button onClick={step === 1 ? onBack : () => setStep(step - 1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }}>
            <ArrowLeft style={{ width: '24px', height: '24px', color: '#6b7280' }} />
          </button>
          <div>
            <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>
              {step === 1 && 'Verificar Identidad'}
              {step === 2 && 'Código de Verificación'}
              {step === 3 && 'Nueva Contraseña'}
            </h2>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>Paso {step} de 3</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
          {[1, 2, 3].map((s) => (
            <div key={s} style={{ flex: 1, height: '4px', borderRadius: '2px', backgroundColor: s <= step ? '#6366f1' : '#e5e7eb', transition: 'background-color 0.3s' }} />
          ))}
        </div>

        {/* Step 1: Identity Verification */}
        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 8px 0' }}>
              Confirma tus datos personales registrados para recuperar tu contraseña.
            </p>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <Mail style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Correo electrónico
              </label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={inputStyle} placeholder="tu@correo.com" data-testid="recovery-email" />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <User style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Nombre completo
              </label>
              <input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} style={inputStyle} placeholder="Nombre como está registrado" data-testid="recovery-fullname" />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <Phone style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Número de teléfono
              </label>
              <input type="tel" value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} style={inputStyle} placeholder="+55 11 99999-9999" data-testid="recovery-phone" />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <FileText style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                CPF
              </label>
              <input type="text" value={cpf} onChange={(e) => setCpf(formatCpf(e.target.value))} style={inputStyle} placeholder="000.000.000-00" maxLength={14} data-testid="recovery-cpf" />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <FileText style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                RNM / CI / Pasaporte
              </label>
              <input type="text" value={documentNumber} onChange={(e) => setDocumentNumber(e.target.value)} style={inputStyle} placeholder="Número de documento" data-testid="recovery-document" />
            </div>
            
            <button onClick={handleVerifyIdentity} disabled={loading} style={{ ...buttonStyle, backgroundColor: '#6366f1', color: 'white', opacity: loading ? 0.7 : 1, marginTop: '8px' }} data-testid="recovery-verify-btn">
              {loading ? 'Verificando...' : 'Verificar y Enviar Código'}
            </button>
          </div>
        )}

        {/* Step 2: Code Verification */}
        {step === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ textAlign: 'center', padding: '20px', backgroundColor: '#f0fdf4', borderRadius: '14px' }}>
              <Mail style={{ width: '40px', height: '40px', color: '#16a34a', margin: '0 auto 12px' }} />
              <p style={{ fontSize: '14px', color: '#374151', margin: 0 }}>
                Enviamos un código de 6 dígitos a<br />
                <strong>{maskedEmail}</strong>
              </p>
            </div>
            
            <div style={{ padding: '12px', backgroundColor: '#fef3c7', borderRadius: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle style={{ width: '18px', height: '18px', color: '#d97706', flexShrink: 0 }} />
              <p style={{ fontSize: '13px', color: '#92400e', margin: 0 }}>El código expira en 5 minutos. Tienes 3 intentos.</p>
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Código de verificación</label>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                style={{ ...inputStyle, textAlign: 'center', fontSize: '24px', letterSpacing: '8px', fontWeight: '700' }}
                placeholder="000000"
                maxLength={6}
                data-testid="recovery-code"
              />
            </div>
            
            <button onClick={handleVerifyCode} disabled={loading || code.length !== 6} style={{ ...buttonStyle, backgroundColor: '#6366f1', color: 'white', opacity: (loading || code.length !== 6) ? 0.5 : 1 }} data-testid="recovery-verify-code-btn">
              {loading ? 'Verificando...' : 'Verificar Código'}
            </button>
            
            <button onClick={() => setStep(1)} style={{ ...buttonStyle, backgroundColor: 'transparent', color: '#6b7280', border: '1px solid #e5e7eb' }}>
              Reenviar código
            </button>
          </div>
        )}

        {/* Step 3: New Password */}
        {step === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ textAlign: 'center', padding: '16px', backgroundColor: '#f0fdf4', borderRadius: '14px' }}>
              <CheckCircle style={{ width: '40px', height: '40px', color: '#16a34a', margin: '0 auto 8px' }} />
              <p style={{ fontSize: '14px', color: '#374151', margin: 0 }}>Identidad verificada. Crea tu nueva contraseña.</p>
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <Lock style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Nueva contraseña
              </label>
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={inputStyle} placeholder={PASSWORD_HELP_TEXT} data-testid="recovery-new-password" />
            </div>
            
            {/* Password Rules */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '13px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: passwordRules.length ? '#16a34a' : '#9ca3af' }}>
                <CheckCircle style={{ width: '14px', height: '14px' }} /> 8+ caracteres
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: passwordRules.uppercase ? '#16a34a' : '#9ca3af' }}>
                <CheckCircle style={{ width: '14px', height: '14px' }} /> Una mayúscula
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: passwordRules.lowercase ? '#16a34a' : '#9ca3af' }}>
                <CheckCircle style={{ width: '14px', height: '14px' }} /> Una minúscula
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: passwordRules.number ? '#16a34a' : '#9ca3af' }}>
                <CheckCircle style={{ width: '14px', height: '14px' }} /> Un número
              </div>
              <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: '6px', color: passwordRules.special ? '#16a34a' : '#9ca3af' }}>
                <CheckCircle style={{ width: '14px', height: '14px' }} /> {`Un símbolo (${PASSWORD_SPECIAL_CHARS})`}
              </div>
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                <Lock style={{ width: '14px', height: '14px', display: 'inline', marginRight: '6px' }} />
                Confirmar contraseña
              </label>
              <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} style={{ ...inputStyle, borderColor: confirmPassword && newPassword !== confirmPassword ? '#ef4444' : '#e5e7eb' }} placeholder="Repite la contraseña" data-testid="recovery-confirm-password" />
              {confirmPassword && newPassword !== confirmPassword && (
                <p style={{ fontSize: '12px', color: '#ef4444', margin: '4px 0 0 0' }}>Las contraseñas no coinciden</p>
              )}
            </div>
            
            <button
              onClick={handleResetPassword}
              disabled={loading || !allRulesPass || newPassword !== confirmPassword}
              style={{ ...buttonStyle, backgroundColor: '#16a34a', color: 'white', opacity: (loading || !allRulesPass || newPassword !== confirmPassword) ? 0.5 : 1, marginTop: '8px' }}
              data-testid="recovery-reset-btn"
            >
              {loading ? 'Actualizando...' : 'Cambiar Contraseña'}
            </button>
          </div>
        )}

        {/* Step 4: Success */}
        {step === 4 && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px', padding: '20px 0' }}>
            <div style={{ width: '80px', height: '80px', borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCircle style={{ width: '48px', height: '48px', color: '#16a34a' }} />
            </div>
            
            <div style={{ textAlign: 'center' }}>
              <h3 style={{ fontSize: '24px', fontWeight: '700', color: '#16a34a', margin: '0 0 8px 0' }}>
                ¡Contraseña Cambiada con Éxito!
              </h3>
              <p style={{ fontSize: '16px', color: '#6b7280', margin: 0 }}>
                Tu contraseña ha sido actualizada correctamente.
              </p>
            </div>
            
            <div style={{ backgroundColor: '#f0fdf4', padding: '16px 24px', borderRadius: '12px', textAlign: 'center' }}>
              <p style={{ fontSize: '14px', color: '#166534', margin: 0 }}>
                Ya puedes iniciar sesión con tu nueva contraseña.
              </p>
            </div>
            
            <button
              onClick={onBack}
              style={{ ...buttonStyle, backgroundColor: '#6366f1', color: 'white', marginTop: '8px' }}
              data-testid="recovery-go-to-login-btn"
            >
              Ir a Iniciar Sesión
            </button>
          </div>
        )}

        {/* Support Button - only show on steps 1-3 */}
        {step < 4 && (
          <div style={{ marginTop: '24px', paddingTop: '24px', borderTop: '1px solid #e5e7eb', textAlign: 'center' }}>
            <button onClick={() => setShowSupport(true)} style={{ background: 'none', border: 'none', color: '#6366f1', fontSize: '14px', fontWeight: '500', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <MessageSquare style={{ width: '16px', height: '16px' }} />
              Comunícate con Soporte
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
