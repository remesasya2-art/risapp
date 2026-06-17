import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, Shield, Camera, Upload, User, CreditCard, 
  FileText, CheckCircle, AlertCircle, Loader, X
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';

export default function Verification() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const videoRef = useRef(null);
  const [stream, setStream] = useState(null);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [phoneCountry, setPhoneCountry] = useState('+55'); // Brasil por defecto
  
  const [formData, setFormData] = useState({
    full_name: user?.full_name || user?.name || '',
    document_type: 'rg', // rg | cnh | rnm | passport
    document_number: '',
    cpf_number: '',
    phone_number: '',
    id_document_image: null,
    id_document_image_back: null, // required for rg/cnh/rnm
    cpf_image: null,
    selfie_image: null,
  });

  // Catalog of accepted document types and whether they need the back side
  const DOCUMENT_TYPES = [
    { code: 'rg',       label: 'RG (Registro Geral)',                       requires_back: true  },
    { code: 'cnh',      label: 'CNH (Carteira Nacional de Habilitação)',     requires_back: true  },
    { code: 'rnm',      label: 'RNM (Registro Nacional Migratório)',        requires_back: true  },
    { code: 'passport', label: 'Pasaporte',                                  requires_back: false },
  ];
  const currentDocType = DOCUMENT_TYPES.find(d => d.code === formData.document_type) || DOCUMENT_TYPES[0];
  const requiresBack = currentDocType.requires_back;

  // Styles
  const pageStyle = {
    minHeight: '100vh',
    backgroundColor: '#f8fafc',
  };

  const headerStyle = {
    background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
    padding: '16px 20px',
    color: 'white',
  };

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '20px',
    padding: '24px',
    boxShadow: '0 2px 12px rgba(0, 0, 0, 0.04)',
    border: '1px solid #f1f5f9',
  };

  const inputStyle = {
    width: '100%',
    padding: '14px 16px',
    fontSize: '15px',
    border: '2px solid #e2e8f0',
    borderRadius: '14px',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
    backgroundColor: '#ffffff',
  };

  const labelStyle = {
    display: 'block',
    fontSize: '14px',
    fontWeight: '600',
    color: '#374151',
    marginBottom: '8px',
  };

  const buttonPrimaryStyle = {
    width: '100%',
    padding: '16px',
    fontSize: '16px',
    fontWeight: '600',
    color: 'white',
    background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
    border: 'none',
    borderRadius: '14px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    transition: 'transform 0.2s, box-shadow 0.2s',
  };

  const buttonSecondaryStyle = {
    width: '100%',
    padding: '14px',
    fontSize: '15px',
    fontWeight: '600',
    color: '#6366f1',
    backgroundColor: '#eef2ff',
    border: 'none',
    borderRadius: '14px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
  };

  const uploadAreaStyle = (hasImage) => ({
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
    height: '200px',
    border: `2px dashed ${hasImage ? '#22c55e' : '#d1d5db'}`,
    borderRadius: '16px',
    cursor: 'pointer',
    backgroundColor: hasImage ? '#f0fdf4' : '#fafafa',
    transition: 'all 0.2s',
    overflow: 'hidden',
    position: 'relative',
  });

  const handleFileChange = (field) => (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        toast.error('La imagen no debe superar 5MB');
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        setFormData({ ...formData, [field]: reader.result });
      };
      reader.readAsDataURL(file);
    }
  };

  // Conecta el stream al <video> en cuanto ambos existen. Esto corrige la
  // carrera por la que en el primer intento el <video> aún no estaba montado
  // cuando se pedía la cámara (y por eso no se veía nada hasta el 2º intento).
  useEffect(() => {
    if (stream && videoRef.current) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(() => {});
    }
  }, [stream]);

  const startCamera = async () => {
    setCameraLoading(true);
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }
      });
      setStream(mediaStream);
    } catch (error) {
      toast.error('No se pudo acceder a la cámara. Revisa que el navegador tenga permiso de cámara y que estés en una conexión segura (HTTPS).');
    } finally {
      setCameraLoading(false);
    }
  };

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      setStream(null);
    }
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    if (!video) return;
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) {
      toast.error('La cámara aún se está iniciando. Espera un segundo e intenta de nuevo.');
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    // Espejar para que la foto coincida con lo que el usuario ve en la vista previa
    ctx.translate(w, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, w, h);
    const selfieData = canvas.toDataURL('image/jpeg', 0.85);
    if (!selfieData || selfieData.length < 1000) {
      toast.error('No se pudo capturar la selfie. Intenta de nuevo con buena luz.');
      return;
    }
    setFormData((prev) => ({ ...prev, selfie_image: selfieData }));
    stopCamera();
  };

  const handleSubmit = async () => {
    if (!formData.full_name || !formData.document_number || !formData.cpf_number || !formData.phone_number) {
      toast.error('Completa todos los campos');
      return;
    }
    if (!formData.id_document_image || !formData.cpf_image || !formData.selfie_image) {
      toast.error('Sube todos los documentos requeridos');
      return;
    }
    if (formData.selfie_image.length < 1000) {
      toast.error('La selfie no se capturó correctamente. Vuelve a tomarla.');
      setStep(3);
      return;
    }
    if (requiresBack && !formData.id_document_image_back) {
      toast.error(`Para ${currentDocType.label.split(' ')[0]} es obligatorio adjuntar también el reverso del documento`);
      setStep(2);
      return;
    }

    setLoading(true);
    try {
      // Include full phone number with country code
      const submitData = {
        ...formData,
        phone_number: `${phoneCountry}${formData.phone_number}`,
        // Strip the back side if the document type doesn't need it
        id_document_image_back: requiresBack ? formData.id_document_image_back : null,
      };
      
      await api.post('/verification/submit', submitData);
      toast.success('¡Documentos enviados! Tu verificación está en proceso.');
      await refreshUser();
      // Show success state instead of navigating away immediately
      setStep(5); // Step 5 will be success state
    } catch (error) {
      console.error('Verification error:', error);
      toast.error(error.response?.data?.detail || 'Error al enviar documentos');
    } finally {
      setLoading(false);
    }
  };

  // Already verified
  if (user?.verification_status === 'verified') {
    return (
      <div style={{ ...pageStyle, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
        <div style={{ ...cardStyle, textAlign: 'center', maxWidth: '400px' }}>
          <div style={{ 
            width: '80px', height: '80px', borderRadius: '50%', 
            backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', 
            justifyContent: 'center', margin: '0 auto 20px' 
          }}>
            <CheckCircle style={{ width: '40px', height: '40px', color: '#16a34a' }} />
          </div>
          <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', marginBottom: '8px' }}>¡Cuenta verificada!</h2>
          <p style={{ fontSize: '15px', color: '#6b7280', marginBottom: '24px' }}>Tu identidad ha sido verificada exitosamente.</p>
          <button onClick={() => navigate('/')} style={buttonPrimaryStyle}>
            Ir al inicio
          </button>
        </div>
      </div>
    );
  }

  // Pending verification
  if (user?.verification_status === 'pending') {
    return (
      <div style={{ ...pageStyle, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
        <div style={{ ...cardStyle, textAlign: 'center', maxWidth: '400px' }}>
          <div style={{ 
            width: '80px', height: '80px', borderRadius: '50%', 
            backgroundColor: '#fef3c7', display: 'flex', alignItems: 'center', 
            justifyContent: 'center', margin: '0 auto 20px' 
          }}>
            <Loader style={{ width: '40px', height: '40px', color: '#d97706', animation: 'spin 1s linear infinite' }} />
          </div>
          <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', marginBottom: '8px' }}>Verificación en proceso</h2>
          <p style={{ fontSize: '15px', color: '#6b7280', marginBottom: '24px' }}>
            Tu documentación está siendo revisada. Te notificaremos cuando esté lista.
          </p>
          <button onClick={() => navigate('/')} style={buttonSecondaryStyle}>
            Volver al inicio
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={pageStyle} data-testid="verification-page">
      {/* Header */}
      <header style={headerStyle}>
        <div style={{ maxWidth: '600px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button 
              onClick={() => navigate(-1)} 
              style={{ background: 'rgba(255,255,255,0.15)', border: 'none', borderRadius: '12px', padding: '10px', cursor: 'pointer', display: 'flex' }}
            >
              <ArrowLeft style={{ width: '20px', height: '20px', color: 'white' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '20px', fontWeight: '700', margin: 0 }}>Verificación KYC</h1>
              <p style={{ fontSize: '13px', color: 'rgba(255,255,255,0.8)', margin: '2px 0 0 0' }}>Paso {step} de 4</p>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Shield style={{ width: '24px', height: '24px', opacity: 0.9 }} />
            <NotificationBell />
          </div>
        </div>
      </header>

      <main style={{ maxWidth: '600px', margin: '0 auto', padding: '20px' }}>
        {/* Progress Bar */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
          {[1, 2, 3, 4].map((s) => (
            <div
              key={s}
              style={{
                flex: 1,
                height: '6px',
                borderRadius: '3px',
                backgroundColor: step >= s ? (step === 5 ? '#22c55e' : '#6366f1') : '#e2e8f0',
                transition: 'background-color 0.3s',
              }}
            />
          ))}
        </div>

        {/* Step 1: Personal Info */}
        {step === 1 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ 
                width: '56px', height: '56px', borderRadius: '16px', 
                background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)', 
                display: 'flex', alignItems: 'center', justifyContent: 'center' 
              }}>
                <User style={{ width: '28px', height: '28px', color: '#6366f1' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Datos personales</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Ingresa tu información personal</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={labelStyle}>Nombre completo</label>
                <input
                  type="text"
                  value={formData.full_name}
                  onChange={(e) => setFormData({...formData, full_name: e.target.value})}
                  style={inputStyle}
                  placeholder="Como aparece en tu documento"
                />
              </div>

              <div>
                <label style={labelStyle}>Tipo de documento</label>
                <select
                  value={formData.document_type}
                  onChange={(e) => setFormData({ ...formData, document_type: e.target.value, id_document_image: null, id_document_image_back: null })}
                  data-testid="document-type-select"
                  style={{
                    ...inputStyle,
                    cursor: 'pointer',
                    appearance: 'none',
                    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
                    backgroundRepeat: 'no-repeat',
                    backgroundPosition: 'right 14px center',
                    paddingRight: '40px',
                  }}
                >
                  {DOCUMENT_TYPES.map((d) => (
                    <option key={d.code} value={d.code}>{d.label}</option>
                  ))}
                </select>
                {requiresBack && (
                  <p style={{ fontSize: '12px', color: '#92400e', margin: '6px 0 0 0', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertCircle style={{ width: '14px', height: '14px' }} />
                    Necesitarás subir <strong style={{ marginLeft: '3px' }}>frente y reverso</strong>
                  </p>
                )}
              </div>

              <div>
                <label style={labelStyle}>Número de documento</label>
                <input
                  type="text"
                  value={formData.document_number}
                  onChange={(e) => setFormData({...formData, document_number: e.target.value})}
                  style={inputStyle}
                  placeholder={
                    formData.document_type === 'cnh' ? 'Número de la CNH' :
                    formData.document_type === 'rnm' ? 'Número del RNM' :
                    formData.document_type === 'passport' ? 'Número de pasaporte' :
                    'Número del RG'
                  }
                />
              </div>

              <div>
                <label style={labelStyle}>CPF</label>
                <input
                  type="text"
                  value={formData.cpf_number}
                  onChange={(e) => setFormData({...formData, cpf_number: e.target.value})}
                  style={inputStyle}
                  placeholder="000.000.000-00"
                />
              </div>

              <div>
                <label style={labelStyle}>Número de teléfono</label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <select
                    value={phoneCountry}
                    onChange={(e) => setPhoneCountry(e.target.value)}
                    style={{
                      ...inputStyle,
                      width: '120px',
                      cursor: 'pointer',
                      appearance: 'none',
                      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
                      backgroundRepeat: 'no-repeat',
                      backgroundPosition: 'right 12px center',
                      paddingRight: '36px',
                    }}
                  >
                    <option value="+55">🇧🇷 +55</option>
                    <option value="+58">🇻🇪 +58</option>
                  </select>
                  <input
                    type="tel"
                    value={formData.phone_number}
                    onChange={(e) => setFormData({...formData, phone_number: e.target.value.replace(/\D/g, '')})}
                    style={{ ...inputStyle, flex: 1 }}
                    placeholder={phoneCountry === '+55' ? '11 99999-9999' : '412 1234567'}
                  />
                </div>
              </div>

              <button
                onClick={() => setStep(2)}
                disabled={!formData.full_name || !formData.document_number || !formData.cpf_number || !formData.phone_number}
                style={{ ...buttonPrimaryStyle, opacity: (!formData.full_name || !formData.document_number || !formData.cpf_number || !formData.phone_number) ? 0.5 : 1 }}
              >
                Continuar
              </button>
            </div>

            {/* Info Box */}
            <div style={{ 
              marginTop: '20px', padding: '16px', backgroundColor: '#eff6ff', 
              borderRadius: '14px', borderLeft: '4px solid #3b82f6' 
            }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                <AlertCircle style={{ width: '20px', height: '20px', color: '#3b82f6', flexShrink: 0, marginTop: '2px' }} />
                <div>
                  <p style={{ fontSize: '14px', fontWeight: '600', color: '#1e40af', margin: '0 0 6px 0' }}>Información importante</p>
                  <ul style={{ fontSize: '13px', color: '#3b82f6', margin: 0, paddingLeft: '16px' }}>
                    <li>Tus documentos serán revisados manualmente</li>
                    <li>La verificación puede tomar de 5 a 30 minutos</li>
                    <li>Tu selfie será tu foto de perfil permanente</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 2: ID Document (front + back when applicable) */}
        {step === 2 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ 
                width: '56px', height: '56px', borderRadius: '16px', 
                background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)', 
                display: 'flex', alignItems: 'center', justifyContent: 'center' 
              }}>
                <CreditCard style={{ width: '28px', height: '28px', color: '#6366f1' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Documento de identidad</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>
                  {currentDocType.label}{requiresBack ? ' — frente y reverso' : ' — solo frente'}
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* FRONT */}
              <div>
                <label style={{ ...labelStyle, marginBottom: '6px' }}>
                  Frente del documento <span style={{ color: '#dc2626' }}>*</span>
                </label>
                <input type="file" accept="image/*" onChange={handleFileChange('id_document_image')} style={{ display: 'none' }} id="id-upload-front" />
                <label htmlFor="id-upload-front" style={uploadAreaStyle(formData.id_document_image)} data-testid="upload-id-front">
                  {formData.id_document_image ? (
                    <>
                      <img src={formData.id_document_image} alt="ID frente" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      <div style={{ position: 'absolute', top: '8px', right: '8px', backgroundColor: '#22c55e', borderRadius: '50%', padding: '6px' }}>
                        <CheckCircle style={{ width: '16px', height: '16px', color: 'white' }} />
                      </div>
                    </>
                  ) : (
                    <>
                      <Upload style={{ width: '40px', height: '40px', color: '#9ca3af', marginBottom: '12px' }} />
                      <p style={{ fontSize: '15px', fontWeight: '600', color: '#374151', margin: '0 0 4px 0' }}>Subir frente</p>
                      <p style={{ fontSize: '13px', color: '#9ca3af', margin: 0 }}>JPG o PNG (máx. 5MB)</p>
                    </>
                  )}
                </label>
              </div>

              {/* BACK (only for rg, cnh, rnm) */}
              {requiresBack && (
                <div>
                  <label style={{ ...labelStyle, marginBottom: '6px' }}>
                    Reverso del documento <span style={{ color: '#dc2626' }}>*</span>
                    <span style={{ fontSize: '12px', fontWeight: 400, color: '#6b7280', marginLeft: '6px' }}>(obligatorio)</span>
                  </label>
                  <input type="file" accept="image/*" onChange={handleFileChange('id_document_image_back')} style={{ display: 'none' }} id="id-upload-back" />
                  <label htmlFor="id-upload-back" style={uploadAreaStyle(formData.id_document_image_back)} data-testid="upload-id-back">
                    {formData.id_document_image_back ? (
                      <>
                        <img src={formData.id_document_image_back} alt="ID reverso" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        <div style={{ position: 'absolute', top: '8px', right: '8px', backgroundColor: '#22c55e', borderRadius: '50%', padding: '6px' }}>
                          <CheckCircle style={{ width: '16px', height: '16px', color: 'white' }} />
                        </div>
                      </>
                    ) : (
                      <>
                        <Upload style={{ width: '40px', height: '40px', color: '#9ca3af', marginBottom: '12px' }} />
                        <p style={{ fontSize: '15px', fontWeight: '600', color: '#374151', margin: '0 0 4px 0' }}>Subir reverso</p>
                        <p style={{ fontSize: '13px', color: '#9ca3af', margin: 0 }}>JPG o PNG (máx. 5MB)</p>
                      </>
                    )}
                  </label>
                </div>
              )}

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setStep(1)} style={{ ...buttonSecondaryStyle, flex: 1 }}>
                  Atrás
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!formData.id_document_image || (requiresBack && !formData.id_document_image_back)}
                  style={{ ...buttonPrimaryStyle, flex: 2, opacity: (!formData.id_document_image || (requiresBack && !formData.id_document_image_back)) ? 0.5 : 1 }}
                >
                  Continuar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: CPF Document */}
        {step === 3 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ 
                width: '56px', height: '56px', borderRadius: '16px', 
                background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)', 
                display: 'flex', alignItems: 'center', justifyContent: 'center' 
              }}>
                <FileText style={{ width: '28px', height: '28px', color: '#6366f1' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Documento CPF</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Foto del documento CPF</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <input type="file" accept="image/*" onChange={handleFileChange('cpf_image')} style={{ display: 'none' }} id="cpf-upload" />
              <label htmlFor="cpf-upload" style={uploadAreaStyle(formData.cpf_image)}>
                {formData.cpf_image ? (
                  <>
                    <img src={formData.cpf_image} alt="CPF" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    <div style={{ position: 'absolute', top: '8px', right: '8px', backgroundColor: '#22c55e', borderRadius: '50%', padding: '6px' }}>
                      <CheckCircle style={{ width: '16px', height: '16px', color: 'white' }} />
                    </div>
                  </>
                ) : (
                  <>
                    <Upload style={{ width: '40px', height: '40px', color: '#9ca3af', marginBottom: '12px' }} />
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#374151', margin: '0 0 4px 0' }}>Subir CPF</p>
                    <p style={{ fontSize: '13px', color: '#9ca3af', margin: 0 }}>JPG, PNG o PDF (máx. 5MB)</p>
                  </>
                )}
              </label>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setStep(2)} style={{ ...buttonSecondaryStyle, flex: 1 }}>
                  Atrás
                </button>
                <button
                  onClick={() => setStep(4)}
                  disabled={!formData.cpf_image}
                  style={{ ...buttonPrimaryStyle, flex: 2, opacity: !formData.cpf_image ? 0.5 : 1 }}
                >
                  Continuar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Selfie */}
        {step === 4 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ 
                width: '56px', height: '56px', borderRadius: '16px', 
                background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)', 
                display: 'flex', alignItems: 'center', justifyContent: 'center' 
              }}>
                <Camera style={{ width: '28px', height: '28px', color: '#6366f1' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Selfie de verificación</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Toma una foto de tu rostro</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Camera/Selfie Area */}
              <div style={{ 
                width: '100%', height: '280px', borderRadius: '16px', 
                backgroundColor: '#1f2937', overflow: 'hidden', position: 'relative' 
              }}>
                {formData.selfie_image ? (
                  <>
                    <img src={formData.selfie_image} alt="Selfie" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    <button
                      onClick={() => setFormData({ ...formData, selfie_image: null })}
                      style={{
                        position: 'absolute', top: '12px', right: '12px',
                        backgroundColor: 'rgba(0,0,0,0.5)', border: 'none', borderRadius: '50%',
                        padding: '8px', cursor: 'pointer', display: 'flex'
                      }}
                    >
                      <X style={{ width: '20px', height: '20px', color: 'white' }} />
                    </button>
                  </>
                ) : stream ? (
                  <>
                    <video ref={videoRef} autoPlay playsInline style={{ width: '100%', height: '100%', objectFit: 'cover', transform: 'scaleX(-1)' }} />
                    <button
                      onClick={capturePhoto}
                      style={{
                        position: 'absolute', bottom: '16px', left: '50%', transform: 'translateX(-50%)',
                        width: '64px', height: '64px', borderRadius: '50%',
                        backgroundColor: 'white', border: '4px solid #6366f1',
                        cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center'
                      }}
                    >
                      <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#6366f1' }} />
                    </button>
                  </>
                ) : (
                  <div style={{ 
                    width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center', color: '#9ca3af'
                  }}>
                    <Camera style={{ width: '48px', height: '48px', marginBottom: '12px' }} />
                    <p style={{ fontSize: '15px', fontWeight: '500', margin: 0 }}>{cameraLoading ? 'Iniciando cámara…' : 'Cámara no activa'}</p>
                  </div>
                )}
              </div>

              {!formData.selfie_image && !stream && (
                <button onClick={startCamera} disabled={cameraLoading} style={{ ...buttonSecondaryStyle, opacity: cameraLoading ? 0.7 : 1 }}>
                  <Camera style={{ width: '20px', height: '20px' }} />
                  {cameraLoading ? 'Iniciando cámara…' : 'Activar cámara'}
                </button>
              )}

              {stream && !formData.selfie_image && (
                <button onClick={stopCamera} style={{ ...buttonSecondaryStyle, color: '#dc2626', backgroundColor: '#fef2f2' }}>
                  <X style={{ width: '20px', height: '20px' }} />
                  Cancelar
                </button>
              )}

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => { stopCamera(); setStep(3); }} style={{ ...buttonSecondaryStyle, flex: 1 }}>
                  Atrás
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={!formData.selfie_image || loading}
                  style={{ ...buttonPrimaryStyle, flex: 2, opacity: (!formData.selfie_image || loading) ? 0.5 : 1 }}
                >
                  {loading ? (
                    <>
                      <Loader style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} />
                      Enviando...
                    </>
                  ) : (
                    <>
                      <CheckCircle style={{ width: '20px', height: '20px' }} />
                      Enviar verificación
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Success Tips */}
            <div style={{ 
              marginTop: '20px', padding: '16px', backgroundColor: '#f0fdf4', 
              borderRadius: '14px', borderLeft: '4px solid #22c55e' 
            }}>
              <p style={{ fontSize: '14px', fontWeight: '600', color: '#166534', margin: '0 0 8px 0' }}>Tips para una buena foto:</p>
              <ul style={{ fontSize: '13px', color: '#15803d', margin: 0, paddingLeft: '16px' }}>
                <li>Buena iluminación en tu rostro</li>
                <li>Mira directamente a la cámara</li>
                <li>Sin lentes ni accesorios que cubran tu cara</li>
              </ul>
            </div>
          </div>
        )}

        {/* Step 5: Success - Submitted */}
        {step === 5 && (
          <div style={cardStyle}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ 
                width: '100px', height: '100px', borderRadius: '50%', 
                background: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)', 
                display: 'flex', alignItems: 'center', justifyContent: 'center', 
                margin: '0 auto 24px' 
              }}>
                <CheckCircle style={{ width: '56px', height: '56px', color: '#16a34a' }} />
              </div>
              
              <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: '0 0 8px 0' }}>
                ¡Documentos Enviados!
              </h2>
              <p style={{ fontSize: '15px', color: '#6b7280', margin: '0 0 24px 0' }}>
                Tu verificación está siendo procesada
              </p>

              <div style={{ 
                padding: '20px', backgroundColor: '#fef3c7', 
                borderRadius: '16px', marginBottom: '24px',
                border: '1px solid #fcd34d'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: 'center' }}>
                  <Loader style={{ width: '24px', height: '24px', color: '#d97706', animation: 'spin 1s linear infinite' }} />
                  <p style={{ fontSize: '15px', fontWeight: '600', color: '#92400e', margin: 0 }}>
                    En revisión
                  </p>
                </div>
                <p style={{ fontSize: '13px', color: '#b45309', margin: '12px 0 0 0' }}>
                  El proceso puede tomar de 5 a 30 minutos en horario laboral.
                  Te notificaremos cuando esté listo.
                </p>
              </div>

              <button 
                onClick={() => navigate('/')} 
                style={buttonPrimaryStyle}
              >
                Ir al inicio
              </button>
            </div>
          </div>
        )}
      </main>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
