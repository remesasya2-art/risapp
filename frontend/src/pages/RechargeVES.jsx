import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Copy, CheckCircle, Upload, Clock, Building2, 
  CreditCard, Smartphone, ChevronDown, AlertCircle, X, Eye, RefreshCw
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import { fmt } from '../utils/format';

// Datos de los bancos
const BANK_DATA = {
  'banco_venezuela': {
    name: 'Banco de Venezuela',
    code: '0102',
    color: '#003876',
    pago_movil: {
      ci: 'V-24560778',
      telefono: '04249311288',
      banco: '0102 - Banco de Venezuela'
    },
    transferencia: {
      titular: 'JULIO FRANCISCO HERNANDEZ',
      cuenta: '01020504280000184324',
      ci: 'V-24560778',
      tipo: 'Corriente'
    }
  },
  'banesco': {
    name: 'Banesco',
    code: '0134',
    color: '#00529B',
    pago_movil: {
      ci: 'V-24560778',
      telefono: '04249311288',
      banco: '0134 - Banesco'
    },
    transferencia: {
      titular: 'JULIO FRANCISCO HERNANDEZ',
      cuenta: '01340869688691034659',
      ci: 'V-24560778',
      tipo: 'Corriente'
    }
  }
};

export default function RechargeVES() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  
  const [step, setStep] = useState(1);
  const idemRef = useRef(null);
  const [amountVES, setAmountVES] = useState('');
  const [selectedBank, setSelectedBank] = useState('');
  const [paymentType, setPaymentType] = useState('');
  const [proofImage, setProofImage] = useState(null);
  const [proofPreview, setProofPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [myRecharges, setMyRecharges] = useState([]);
  const [showRecharges, setShowRecharges] = useState(false);
  const [loadingRecharges, setLoadingRecharges] = useState(false);

  // Fetch user's VES recharges on mount
  useEffect(() => {
    fetchMyRecharges();
  }, []);

  const fetchMyRecharges = async () => {
    setLoadingRecharges(true);
    try {
      const response = await api.get('/recharge/ves/status');
      setMyRecharges(response.data || []);
    } catch (error) {
      console.error('Error fetching recharges:', error);
    } finally {
      setLoadingRecharges(false);
    }
  };

  const getStatusBadge = (status) => {
    const styles = {
      pending: { bg: '#fef3c7', color: '#92400e', text: 'En Revisión' },
      approved: { bg: '#dcfce7', color: '#166534', text: 'Aprobada' },
      rejected: { bg: '#fee2e2', color: '#991b1b', text: 'Rechazada' }
    };
    const style = styles[status] || styles.pending;
    return (
      <span style={{ 
        padding: '4px 12px', 
        borderRadius: '20px', 
        fontSize: '12px', 
        fontWeight: '600',
        backgroundColor: style.bg,
        color: style.color
      }}>
        {style.text}
      </span>
    );
  };
  const [submitted, setSubmitted] = useState(false);
  const [transactionId, setTransactionId] = useState(null);
  const [copiedField, setCopiedField] = useState(null);

  // Cálculo recarga VES: Si ves_to_ris_rate = 140, entonces 140 VES = 1 RIS
  const amountRIS = amountVES && rates?.ves_to_ris_rate ? fmt((parseFloat(amountVES) / rates.ves_to_ris_rate)) : '0.00';

  const copyToClipboard = async (text, fieldName) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(fieldName);
      toast.success('Copiado al portapapeles');
      setTimeout(() => setCopiedField(null), 2000);
    } catch (err) {
      toast.error('Error al copiar');
    }
  };

  // Copiar todos los datos de pago (solo datos relevantes)
  const copyAllPaymentData = async () => {
    if (!selectedBank || !paymentType) return;
    
    const bankData = BANK_DATA[selectedBank];
    let allData = '';
    
    if (paymentType === 'pago_movil') {
      allData = `${bankData.pago_movil.telefono}
${bankData.pago_movil.ci}
${bankData.code}`;
    } else {
      allData = `${bankData.transferencia.titular}
${bankData.transferencia.cuenta}
${bankData.transferencia.ci}`;
    }
    
    try {
      await navigator.clipboard.writeText(allData);
      setCopiedField('all');
      toast.success('¡Todos los datos copiados!');
      setTimeout(() => setCopiedField(null), 2000);
    } catch (err) {
      toast.error('Error al copiar');
    }
  };

  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        toast.error('La imagen no debe superar 5MB');
        return;
      }
      const reader = new FileReader();
      reader.onloadend = () => {
        setProofImage(reader.result);
        setProofPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmitRecharge = async () => {
    if (!amountVES || !selectedBank || !paymentType || !proofImage) {
      toast.error('Completa todos los campos');
      return;
    }

    if (!idemRef.current) idemRef.current = (window.crypto?.randomUUID?.() || (Date.now() + '-' + Math.random().toString(16).slice(2)));
    setLoading(true);
    try {
      const response = await api.post('/recharge/ves', {
        amount_ves: parseFloat(amountVES),
        amount_ris: parseFloat(amountRIS),
        payment_method: paymentType,
        voucher_image: proofImage,
        bank: selectedBank,
        idempotency_key: idemRef.current
      });
      idemRef.current = null;

      setTransactionId(response.data.transaction_id);
      setSubmitted(true);
      toast.success('Solicitud enviada correctamente');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al enviar solicitud');
    } finally {
      setLoading(false);
    }
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
    fontSize: '16px',
    outline: 'none',
    transition: 'border-color 0.2s'
  };

  const selectStyle = {
    ...inputStyle,
    appearance: 'none',
    cursor: 'pointer',
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'right 12px center',
    backgroundSize: '20px',
    paddingRight: '40px'
  };

  const btnPrimary = {
    width: '100%',
    padding: '16px',
    borderRadius: '14px',
    border: 'none',
    backgroundColor: '#6366f1',
    color: '#ffffff',
    fontSize: '16px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s'
  };

  const copyBtnStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 12px',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#f3f4f6',
    color: '#374151',
    fontSize: '13px',
    cursor: 'pointer',
    transition: 'all 0.2s'
  };

  // Si ya se envió la solicitud, mostrar pantalla de espera
  if (submitted) {
    return (
      <div style={pageStyle} data-testid="recharge-ves-submitted">
        <div style={{ padding: '24px', maxWidth: '500px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <button onClick={() => navigate('/dashboard')} style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.8)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
              </button>
              <h1 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Recarga con VES</h1>
            </div>
            <NotificationBell />
          </div>

          {/* Status Card */}
          <div style={{ ...cardStyle, padding: '32px', textAlign: 'center' }}>
            <div style={{ width: '80px', height: '80px', borderRadius: '50%', backgroundColor: '#fef3c7', margin: '0 auto 24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Clock style={{ width: '40px', height: '40px', color: '#d97706' }} />
            </div>
            <h2 style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: '0 0 12px 0' }}>
              Pago en Revisión
            </h2>
            <p style={{ fontSize: '15px', color: '#6b7280', margin: '0 0 24px 0', lineHeight: '1.5' }}>
              Tu comprobante ha sido enviado y está siendo revisado por nuestro equipo. Te notificaremos cuando tu recarga sea aprobada.
            </p>

            <div style={{ padding: '20px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                <span style={{ color: '#6b7280', fontSize: '14px' }}>Monto VES</span>
                <span style={{ fontWeight: '600', color: '#111827' }}>{fmt(parseFloat(amountVES))} VES</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                <span style={{ color: '#6b7280', fontSize: '14px' }}>Recibirás</span>
                <span style={{ fontWeight: '700', color: '#16a34a', fontSize: '18px' }}>{amountRIS} RIS</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280', fontSize: '14px' }}>ID Transacción</span>
                <span style={{ fontWeight: '500', color: '#6366f1', fontSize: '12px' }}>{transactionId?.slice(0, 12)}...</span>
              </div>
            </div>

            <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '12px' }}>
              <AlertCircle style={{ width: '20px', height: '20px', color: '#d97706', flexShrink: 0 }} />
              <p style={{ fontSize: '13px', color: '#92400e', margin: 0, textAlign: 'left' }}>
                El tiempo de aprobación puede variar entre 5 a 30 minutos en horario laboral.
              </p>
            </div>

            <button 
              onClick={() => navigate('/dashboard')} 
              style={{ ...btnPrimary, marginTop: '24px' }}
            >
              Volver al Inicio
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={pageStyle} data-testid="recharge-ves-page">
      <div style={{ padding: '24px', maxWidth: '500px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button onClick={() => navigate(-1)} style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.8)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="back-button">
              <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Recargar con VES</h1>
              <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
                Tasa: {fmt(rates?.ves_to_ris_rate) || '140'} VES = 1 RIS
              </p>
            </div>
          </div>
          <NotificationBell />
        </div>

        {/* My VES Recharges Section */}
        {myRecharges.length > 0 && step === 1 && (
          <div style={{ ...cardStyle, padding: '16px', marginBottom: '16px' }}>
            <div 
              onClick={() => setShowRecharges(!showRecharges)}
              style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between',
                cursor: 'pointer'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <Eye style={{ width: '20px', height: '20px', color: '#6366f1' }} />
                <span style={{ fontSize: '14px', fontWeight: '600', color: '#374151' }}>
                  Mis Recargas VES ({myRecharges.length})
                </span>
              </div>
              <ChevronDown 
                style={{ 
                  width: '20px', 
                  height: '20px', 
                  color: '#6b7280',
                  transform: showRecharges ? 'rotate(180deg)' : 'rotate(0)',
                  transition: 'transform 0.2s'
                }} 
              />
            </div>
            
            {showRecharges && (
              <div style={{ marginTop: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '12px' }}>
                  <button
                    onClick={fetchMyRecharges}
                    disabled={loadingRecharges}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '6px 12px',
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                      backgroundColor: '#ffffff',
                      fontSize: '12px',
                      color: '#6b7280',
                      cursor: 'pointer'
                    }}
                  >
                    <RefreshCw style={{ width: '14px', height: '14px', animation: loadingRecharges ? 'spin 1s linear infinite' : 'none' }} />
                    Actualizar
                  </button>
                </div>
                
                {myRecharges.map((recharge) => (
                  <div 
                    key={recharge.transaction_id}
                    style={{
                      padding: '14px',
                      backgroundColor: '#f9fafb',
                      borderRadius: '12px',
                      marginBottom: '10px',
                      border: '1px solid #e5e7eb'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                        {fmt(parseFloat(recharge.amount_ves || 0))} VES
                      </span>
                      {getStatusBadge(recharge.status)}
                    </div>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#6b7280' }}>
                      <span>Recibirás: {fmt(parseFloat(recharge.amount_ris || 0))} RIS</span>
                      <span>{new Date(recharge.created_at).toLocaleDateString()}</span>
                    </div>
                    
                    {recharge.status === 'approved' && (
                      <div style={{ 
                        marginTop: '10px', 
                        padding: '10px', 
                        backgroundColor: '#dcfce7', 
                        borderRadius: '8px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}>
                        <CheckCircle style={{ width: '16px', height: '16px', color: '#16a34a' }} />
                        <span style={{ fontSize: '13px', color: '#166534', fontWeight: '500' }}>
                          Recarga aprobada - Saldo acreditado
                        </span>
                      </div>
                    )}
                    
                    {recharge.status === 'rejected' && (
                      <div style={{ 
                        marginTop: '10px', 
                        padding: '10px', 
                        backgroundColor: '#fee2e2', 
                        borderRadius: '8px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <X style={{ width: '16px', height: '16px', color: '#dc2626' }} />
                          <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: '500' }}>
                            Recarga rechazada
                          </span>
                        </div>
                        {recharge.rejection_reason && (
                          <p style={{ fontSize: '12px', color: '#b91c1c', margin: '4px 0 0 24px' }}>
                            Motivo: {recharge.rejection_reason}
                          </p>
                        )}
                      </div>
                    )}
                    
                    {recharge.status === 'pending' && (
                      <div style={{ 
                        marginTop: '10px', 
                        padding: '10px', 
                        backgroundColor: '#fef3c7', 
                        borderRadius: '8px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}>
                        <Clock style={{ width: '16px', height: '16px', color: '#d97706' }} />
                        <span style={{ fontSize: '13px', color: '#92400e', fontWeight: '500' }}>
                          En revisión - Esperando aprobación
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 1: Amount and Bank Selection */}
        {step === 1 && (
          <div style={{ ...cardStyle, padding: '24px' }}>
            <h2 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 20px 0' }}>
              Paso 1: Datos de la recarga
            </h2>

            {/* Amount Input */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
                Monto a pagar (VES)
              </label>
              <input
                type="number"
                value={amountVES}
                onChange={(e) => setAmountVES(e.target.value)}
                placeholder="Ej: 50000"
                style={inputStyle}
                data-testid="amount-ves-input"
              />
              {amountVES && (
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '8px 0 0 0', fontWeight: '600' }}>
                  Recibirás: {amountRIS} RIS
                </p>
              )}
            </div>

            {/* Bank Selection */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
                Selecciona el banco
              </label>
              <select
                value={selectedBank}
                onChange={(e) => setSelectedBank(e.target.value)}
                style={selectStyle}
                data-testid="bank-select"
              >
                <option value="">Seleccionar banco...</option>
                <option value="banco_venezuela">🏦 Banco de Venezuela</option>
                <option value="banesco">🏦 Banesco</option>
              </select>
            </div>

            {/* Payment Type Selection */}
            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
                Tipo de pago
              </label>
              <select
                value={paymentType}
                onChange={(e) => setPaymentType(e.target.value)}
                style={selectStyle}
                data-testid="payment-type-select"
              >
                <option value="">Seleccionar tipo de pago...</option>
                <option value="pago_movil">📱 Pago Móvil</option>
                <option value="transferencia">💳 Transferencia Bancaria</option>
              </select>
            </div>

            <button
              onClick={() => setStep(2)}
              disabled={!amountVES || !selectedBank || !paymentType || parseFloat(amountVES) <= 0}
              style={{
                ...btnPrimary,
                opacity: (!amountVES || !selectedBank || !paymentType || parseFloat(amountVES) <= 0) ? 0.5 : 1,
                cursor: (!amountVES || !selectedBank || !paymentType || parseFloat(amountVES) <= 0) ? 'not-allowed' : 'pointer'
              }}
              data-testid="continue-btn"
            >
              Continuar
            </button>
          </div>
        )}

        {/* Step 2: Payment Details */}
        {step === 2 && selectedBank && paymentType && (
          <div>
            {/* Back button */}
            <button 
              onClick={() => setStep(1)} 
              style={{ 
                display: 'flex', alignItems: 'center', gap: '6px', 
                padding: '8px 12px', marginBottom: '16px',
                backgroundColor: 'transparent', border: 'none', 
                color: '#6366f1', fontSize: '14px', fontWeight: '500', cursor: 'pointer'
              }}
            >
              <ArrowLeft style={{ width: '16px', height: '16px' }} />
              Cambiar datos
            </button>

            {/* Amount Summary */}
            <div style={{ ...cardStyle, padding: '20px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 4px 0' }}>Monto a pagar</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>{fmt(parseFloat(amountVES))} VES</p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 4px 0' }}>Recibirás</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#16a34a', margin: 0 }}>{amountRIS} RIS</p>
                </div>
              </div>
            </div>

            {/* Payment Details Card */}
            <div style={{ ...cardStyle, padding: '24px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                <div style={{ 
                  width: '44px', height: '44px', borderRadius: '12px', 
                  backgroundColor: BANK_DATA[selectedBank].color,
                  display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}>
                  <Building2 style={{ width: '24px', height: '24px', color: '#ffffff' }} />
                </div>
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
                    {BANK_DATA[selectedBank].name}
                  </h3>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>
                    {paymentType === 'pago_movil' ? '📱 Pago Móvil' : '💳 Transferencia'}
                  </p>
                </div>
              </div>

              {/* Payment Details */}
              {paymentType === 'pago_movil' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Teléfono</p>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
                          {BANK_DATA[selectedBank].pago_movil.telefono}
                        </p>
                      </div>
                      <button 
                        onClick={() => copyToClipboard(BANK_DATA[selectedBank].pago_movil.telefono, 'telefono')}
                        style={{ ...copyBtnStyle, backgroundColor: copiedField === 'telefono' ? '#dcfce7' : '#f3f4f6' }}
                      >
                        {copiedField === 'telefono' ? <CheckCircle style={{ width: '14px', height: '14px', color: '#16a34a' }} /> : <Copy style={{ width: '14px', height: '14px' }} />}
                        {copiedField === 'telefono' ? 'Copiado' : 'Copiar'}
                      </button>
                    </div>
                  </div>

                  <div style={{ padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Cédula</p>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
                          {BANK_DATA[selectedBank].pago_movil.ci}
                        </p>
                      </div>
                      <button 
                        onClick={() => copyToClipboard(BANK_DATA[selectedBank].pago_movil.ci, 'ci')}
                        style={{ ...copyBtnStyle, backgroundColor: copiedField === 'ci' ? '#dcfce7' : '#f3f4f6' }}
                      >
                        {copiedField === 'ci' ? <CheckCircle style={{ width: '14px', height: '14px', color: '#16a34a' }} /> : <Copy style={{ width: '14px', height: '14px' }} />}
                        {copiedField === 'ci' ? 'Copiado' : 'Copiar'}
                      </button>
                    </div>
                  </div>

                  <div style={{ padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Banco</p>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
                          {BANK_DATA[selectedBank].pago_movil.banco}
                        </p>
                      </div>
                      <button 
                        onClick={() => copyToClipboard(BANK_DATA[selectedBank].code, 'banco')}
                        style={{ ...copyBtnStyle, backgroundColor: copiedField === 'banco' ? '#dcfce7' : '#f3f4f6' }}
                      >
                        {copiedField === 'banco' ? <CheckCircle style={{ width: '14px', height: '14px', color: '#16a34a' }} /> : <Copy style={{ width: '14px', height: '14px' }} />}
                        {copiedField === 'banco' ? 'Copiado' : 'Copiar'}
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Titular</p>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
                          {BANK_DATA[selectedBank].transferencia.titular}
                        </p>
                      </div>
                      <button 
                        onClick={() => copyToClipboard(BANK_DATA[selectedBank].transferencia.titular, 'titular')}
                        style={{ ...copyBtnStyle, backgroundColor: copiedField === 'titular' ? '#dcfce7' : '#f3f4f6' }}
                      >
                        {copiedField === 'titular' ? <CheckCircle style={{ width: '14px', height: '14px', color: '#16a34a' }} /> : <Copy style={{ width: '14px', height: '14px' }} />}
                        {copiedField === 'titular' ? 'Copiado' : 'Copiar'}
                      </button>
                    </div>
                  </div>

                  <div style={{ padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Número de Cuenta</p>
                        <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0, fontFamily: 'monospace' }}>
                          {BANK_DATA[selectedBank].transferencia.cuenta}
                        </p>
                      </div>
                      <button 
                        onClick={() => copyToClipboard(BANK_DATA[selectedBank].transferencia.cuenta, 'cuenta')}
                        style={{ ...copyBtnStyle, backgroundColor: copiedField === 'cuenta' ? '#dcfce7' : '#f3f4f6' }}
                      >
                        {copiedField === 'cuenta' ? <CheckCircle style={{ width: '14px', height: '14px', color: '#16a34a' }} /> : <Copy style={{ width: '14px', height: '14px' }} />}
                        {copiedField === 'cuenta' ? 'Copiado' : 'Copiar'}
                      </button>
                    </div>
                  </div>

                  <div style={{ padding: '14px', backgroundColor: '#f8f9fa', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Cédula</p>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
                          {BANK_DATA[selectedBank].transferencia.ci}
                        </p>
                      </div>
                      <button 
                        onClick={() => copyToClipboard(BANK_DATA[selectedBank].transferencia.ci, 'ci_trans')}
                        style={{ ...copyBtnStyle, backgroundColor: copiedField === 'ci_trans' ? '#dcfce7' : '#f3f4f6' }}
                      >
                        {copiedField === 'ci_trans' ? <CheckCircle style={{ width: '14px', height: '14px', color: '#16a34a' }} /> : <Copy style={{ width: '14px', height: '14px' }} />}
                        {copiedField === 'ci_trans' ? 'Copiado' : 'Copiar'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Copy All Button */}
              <button
                onClick={copyAllPaymentData}
                style={{
                  width: '100%',
                  marginTop: '16px',
                  padding: '14px',
                  borderRadius: '12px',
                  border: 'none',
                  backgroundColor: copiedField === 'all' ? '#dcfce7' : '#6366f1',
                  color: copiedField === 'all' ? '#166534' : '#ffffff',
                  fontSize: '15px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  transition: 'all 0.2s'
                }}
                data-testid="copy-all-btn"
              >
                {copiedField === 'all' ? (
                  <>
                    <CheckCircle style={{ width: '18px', height: '18px' }} />
                    ¡Todos los datos copiados!
                  </>
                ) : (
                  <>
                    <Copy style={{ width: '18px', height: '18px' }} />
                    Copiar todos los datos
                  </>
                )}
              </button>
            </div>

            {/* Upload Proof */}
            <div style={{ ...cardStyle, padding: '24px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
                Adjuntar comprobante de pago
              </h3>
              
              {!proofPreview ? (
                <label style={{ 
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  padding: '32px', border: '2px dashed #d1d5db', borderRadius: '14px',
                  cursor: 'pointer', transition: 'all 0.2s'
                }}>
                  <Upload style={{ width: '40px', height: '40px', color: '#9ca3af', marginBottom: '12px' }} />
                  <p style={{ fontSize: '15px', fontWeight: '500', color: '#374151', margin: '0 0 4px 0' }}>
                    Toca para subir imagen
                  </p>
                  <p style={{ fontSize: '13px', color: '#9ca3af', margin: 0 }}>
                    Capture del comprobante de pago
                  </p>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleImageUpload}
                    style={{ display: 'none' }}
                    data-testid="proof-upload"
                  />
                </label>
              ) : (
                <div style={{ position: 'relative' }}>
                  <img 
                    src={proofPreview} 
                    alt="Comprobante" 
                    style={{ width: '100%', borderRadius: '14px', border: '1px solid #e5e7eb' }}
                  />
                  <button
                    onClick={() => { setProofImage(null); setProofPreview(null); }}
                    style={{
                      position: 'absolute', top: '8px', right: '8px',
                      width: '32px', height: '32px', borderRadius: '50%',
                      backgroundColor: 'rgba(0,0,0,0.6)', border: 'none',
                      cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}
                  >
                    <X style={{ width: '18px', height: '18px', color: '#ffffff' }} />
                  </button>
                  <div style={{ 
                    marginTop: '12px', padding: '12px', backgroundColor: '#dcfce7', 
                    borderRadius: '10px', display: 'flex', alignItems: 'center', gap: '8px'
                  }}>
                    <CheckCircle style={{ width: '18px', height: '18px', color: '#16a34a' }} />
                    <span style={{ fontSize: '14px', color: '#166534', fontWeight: '500' }}>
                      Comprobante adjuntado
                    </span>
                  </div>
                </div>
              )}

              <button
                onClick={handleSubmitRecharge}
                disabled={!proofImage || loading}
                style={{
                  ...btnPrimary,
                  marginTop: '20px',
                  opacity: (!proofImage || loading) ? 0.5 : 1,
                  cursor: (!proofImage || loading) ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}
                data-testid="submit-recharge-btn"
              >
                {loading ? (
                  <>
                    <div style={{ width: '20px', height: '20px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                    Enviando...
                  </>
                ) : (
                  <>
                    <CheckCircle style={{ width: '20px', height: '20px' }} />
                    Enviar solicitud de recarga
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
