import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, QrCode, Copy, CheckCircle, Upload, Clock, Banknote, AlertCircle,
  Wallet, ArrowRight, Shield, Zap
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function Recharge() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  const [method, setMethod] = useState(null);
  const [amount, setAmount] = useState('');
  const [cpf, setCpf] = useState(user?.cpf_number || '');
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [pixData, setPixData] = useState(null);
  const [proofImage, setProofImage] = useState(null);

  const vesPaymentInfo = {
    bank_name: 'Banco de Venezuela',
    account_holder: 'RIS REMESAS C.A.',
    account_number: '01020123456789012345',
    account_type: 'Corriente',
    phone_number: '04121234567',
    id_document: 'J-12345678-9',
  };

  const amountRis = method === 'ves' && amount ? parseFloat(amount) / rates.ves_to_ris : parseFloat(amount) || 0;

  const formatCpf = (value) => {
    const numbers = value.replace(/\D/g, '');
    if (numbers.length <= 3) return numbers;
    if (numbers.length <= 6) return `${numbers.slice(0, 3)}.${numbers.slice(3)}`;
    if (numbers.length <= 9) return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6)}`;
    return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6, 9)}-${numbers.slice(9, 11)}`;
  };

  const handleCpfChange = (e) => {
    const formatted = formatCpf(e.target.value);
    if (formatted.length <= 14) setCpf(formatted);
  };

  const handleGeneratePix = async () => {
    if (!amount || parseFloat(amount) < 10) {
      toast.error('El monto mínimo es 10 BRL');
      return;
    }
    const cpfClean = cpf.replace(/\D/g, '');
    if (cpfClean.length !== 11) {
      toast.error('Ingresa un CPF válido (11 dígitos)');
      return;
    }
    if (user?.verification_status !== 'verified') {
      toast.error('Debes verificar tu cuenta antes de recargar con PIX');
      navigate('/verification');
      return;
    }
    setLoading(true);
    try {
      const response = await api.post('/pix/create', { 
        amount_brl: parseFloat(amount),
        payer_cpf: cpfClean
      });
      setPixData(response.data);
      setStep(2);
      toast.success('PIX generado correctamente');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al generar PIX');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyPix = () => {
    if (pixData?.pix_code) {
      navigator.clipboard.writeText(pixData.pix_code);
      toast.success('Código PIX copiado');
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        toast.error('La imagen no debe superar 5MB');
        return;
      }
      const reader = new FileReader();
      reader.onload = () => setProofImage(reader.result);
      reader.readAsDataURL(file);
    }
  };

  const handleSubmitVesRecharge = async () => {
    if (!amount || parseFloat(amount) < 100) {
      toast.error('El monto mínimo es 100 VES');
      return;
    }
    if (!proofImage) {
      toast.error('Sube el comprobante de pago');
      return;
    }
    setLoading(true);
    try {
      await api.post('/recharge/ves', {
        amount_ves: parseFloat(amount),
        proof_image: proofImage,
      });
      toast.success('Recarga enviada para verificación');
      navigate('/history');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al enviar recarga');
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
    borderRadius: '24px',
    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.08), 0 12px 24px -8px rgba(0, 0, 0, 0.04)',
    padding: '32px'
  };

  const inputStyle = {
    width: '100%',
    padding: '16px',
    borderRadius: '14px',
    border: '1px solid #d1d5db',
    fontSize: '16px',
    outline: 'none',
    transition: 'all 0.2s'
  };

  const buttonPrimaryStyle = {
    backgroundColor: '#6366f1',
    color: 'white',
    borderRadius: '14px',
    height: '56px',
    padding: '0 32px',
    fontWeight: '600',
    fontSize: '16px',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    transition: 'all 0.2s'
  };

  const buttonSecondaryStyle = {
    backgroundColor: '#f3f4f6',
    color: '#374151',
    borderRadius: '14px',
    height: '56px',
    padding: '0 32px',
    fontWeight: '600',
    fontSize: '16px',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    transition: 'all 0.2s'
  };

  return (
    <div style={pageStyle} data-testid="recharge-page">
      {/* Header */}
      <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
          <button 
            onClick={() => navigate(-1)} 
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '12px',
              border: 'none',
              backgroundColor: 'rgba(255,255,255,0.8)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
            data-testid="back-button"
          >
            <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
          </button>
          <div>
            <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Recargar Saldo</h1>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>
              Saldo actual: {(user?.balance_ris || 0).toFixed(2)} RIS
            </p>
          </div>
        </div>

        {/* Method Selection */}
        {!method && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: '0 0 8px 0', textAlign: 'center' }}>
              Selecciona el método de pago
            </h2>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 24px 0', textAlign: 'center' }}>
              Elige cómo deseas recargar tu saldo RIS
            </p>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* PIX Option */}
              <button
                onClick={() => setMethod('pix')}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  border: '2px solid #e5e7eb',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s'
                }}
                data-testid="select-pix"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <QrCode style={{ width: '28px', height: '28px', color: '#16a34a' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>PIX (Brasil)</span>
                      <span style={{ padding: '2px 8px', backgroundColor: '#dcfce7', color: '#16a34a', borderRadius: '9999px', fontSize: '12px', fontWeight: '600' }}>Recomendado</span>
                    </div>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>Pago instantáneo • Sin comisiones</p>
                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#16a34a', margin: '4px 0 0 0' }}>1 BRL = 1 RIS</p>
                  </div>
                  <ArrowRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                </div>
              </button>

              {/* VES Option */}
              <button
                onClick={() => setMethod('ves')}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  border: '2px solid #e5e7eb',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s'
                }}
                data-testid="select-ves"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Banknote style={{ width: '28px', height: '28px', color: '#2563eb' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>Bolívares (Venezuela)</span>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Transferencia bancaria</p>
                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#2563eb', margin: '4px 0 0 0' }}>{rates.ves_to_ris.toFixed(0)} VES = 1 RIS</p>
                  </div>
                  <ArrowRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                </div>
              </button>
            </div>
          </div>
        )}

        {/* PIX Flow - Step 1 */}
        {method === 'pix' && step === 1 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <QrCode style={{ width: '28px', height: '28px', color: '#16a34a' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Recarga con PIX</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Ingresa los datos de pago</p>
              </div>
            </div>

            {user?.verification_status !== 'verified' && (
              <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '12px', marginBottom: '24px', display: 'flex', gap: '12px' }}>
                <AlertCircle style={{ width: '20px', height: '20px', color: '#d97706', flexShrink: 0 }} />
                <div>
                  <p style={{ fontWeight: '600', color: '#92400e', margin: 0 }}>Verificación requerida</p>
                  <p style={{ fontSize: '14px', color: '#a16207', margin: '4px 0 0 0' }}>Debes verificar tu cuenta antes de usar PIX.</p>
                  <button onClick={() => navigate('/verification')} style={{ marginTop: '8px', fontSize: '14px', fontWeight: '600', color: '#92400e', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                    Verificar ahora
                  </button>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Monto a recargar (BRL)</label>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  style={{ ...inputStyle, fontSize: '24px', fontWeight: '700' }}
                  placeholder="0.00"
                  min="10"
                  max="2000"
                  data-testid="pix-amount"
                />
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '8px 0 0 0' }}>Mínimo: R$ 10 • Máximo: R$ 2.000</p>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>CPF del pagador</label>
                <input
                  type="text"
                  value={cpf}
                  onChange={handleCpfChange}
                  style={inputStyle}
                  placeholder="000.000.000-00"
                  data-testid="pix-cpf"
                />
              </div>

              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Recibirás en tu cuenta</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#16a34a', margin: 0 }}>{amountRis.toFixed(2)} RIS</p>
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setMethod(null)} style={buttonSecondaryStyle} data-testid="back-to-methods">Atrás</button>
                <button
                  onClick={handleGeneratePix}
                  disabled={loading || !amount || parseFloat(amount) < 10 || cpf.replace(/\D/g, '').length !== 11}
                  style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a', opacity: loading || !amount || parseFloat(amount) < 10 || cpf.replace(/\D/g, '').length !== 11 ? 0.5 : 1 }}
                  data-testid="generate-pix"
                >
                  {loading ? 'Generando...' : 'Generar PIX'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* PIX Flow - Step 2 (QR Code) */}
        {method === 'pix' && step === 2 && pixData && (
          <div style={cardStyle}>
            <div style={{ textAlign: 'center', marginBottom: '24px' }}>
              <div style={{ width: '80px', height: '80px', borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                <QrCode style={{ width: '40px', height: '40px', color: '#16a34a' }} />
              </div>
              <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: '0 0 8px 0' }}>PIX generado</h2>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>Escanea el QR o copia el código</p>
            </div>

            {pixData.qr_code_base64 && (
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '24px' }}>
                <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '16px', border: '2px solid #e5e7eb' }}>
                  <img src={`data:image/png;base64,${pixData.qr_code_base64}`} alt="QR Code PIX" style={{ width: '200px', height: '200px' }} />
                </div>
              </div>
            )}

            <div style={{ padding: '16px', backgroundColor: '#f3f4f6', borderRadius: '12px', marginBottom: '16px' }}>
              <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 8px 0', fontWeight: '500' }}>Código PIX (Copia y Pega)</p>
              <p style={{ fontSize: '12px', fontFamily: 'monospace', wordBreak: 'break-all', color: '#374151', backgroundColor: '#ffffff', padding: '12px', borderRadius: '8px', margin: '0 0 12px 0' }}>
                {pixData.pix_code?.substring(0, 80)}...
              </p>
              <button onClick={handleCopyPix} style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a', height: '48px' }} data-testid="copy-pix">
                <Copy style={{ width: '20px', height: '20px' }} />
                Copiar código completo
              </button>
            </div>

            <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '12px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Clock style={{ width: '24px', height: '24px', color: '#d97706' }} />
              <span style={{ fontWeight: '500', color: '#92400e' }}>Este código expira en 30 minutos</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <button onClick={() => { refreshUser(); navigate('/history'); }} style={buttonSecondaryStyle}>Ver historial de transacciones</button>
              <button onClick={() => { setStep(1); setPixData(null); setAmount(''); }} style={{ ...buttonPrimaryStyle, backgroundColor: 'transparent', color: '#16a34a', border: '2px solid #16a34a' }}>Generar otro PIX</button>
            </div>
          </div>
        )}

        {/* VES Flow */}
        {method === 'ves' && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Banknote style={{ width: '28px', height: '28px', color: '#2563eb' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Recarga con Bolívares</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa: {rates.ves_to_ris.toFixed(0)} VES = 1 RIS</p>
              </div>
            </div>

            {/* Bank Info */}
            <div style={{ padding: '20px', backgroundColor: '#eff6ff', borderRadius: '14px', marginBottom: '24px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#1e40af', margin: '0 0 16px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Wallet style={{ width: '20px', height: '20px' }} />
                Datos para transferencia
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {[
                  { label: 'Banco', value: vesPaymentInfo.bank_name },
                  { label: 'Titular', value: vesPaymentInfo.account_holder },
                  { label: 'Cuenta', value: vesPaymentInfo.account_number },
                  { label: 'Tipo', value: vesPaymentInfo.account_type },
                  { label: 'Cédula/RIF', value: vesPaymentInfo.id_document },
                ].map((item, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: i < 4 ? '1px solid #bfdbfe' : 'none' }}>
                    <span style={{ fontSize: '14px', color: '#3b82f6' }}>{item.label}:</span>
                    <span style={{ fontSize: '14px', fontWeight: '600', color: '#1e40af' }}>{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Monto transferido (VES)</label>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  style={{ ...inputStyle, fontSize: '24px', fontWeight: '700' }}
                  placeholder="0.00"
                  data-testid="ves-amount"
                />
              </div>

              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Recibirás en tu cuenta</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#16a34a', margin: 0 }}>{amountRis.toFixed(2)} RIS</p>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Comprobante de pago *</label>
                <input type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} id="proof-upload" />
                <label
                  htmlFor="proof-upload"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '100%',
                    height: '140px',
                    border: `2px dashed ${proofImage ? '#16a34a' : '#d1d5db'}`,
                    borderRadius: '14px',
                    cursor: 'pointer',
                    backgroundColor: proofImage ? '#f0fdf4' : '#ffffff',
                    transition: 'all 0.2s'
                  }}
                >
                  {proofImage ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: '#16a34a' }}>
                      <CheckCircle style={{ width: '32px', height: '32px' }} />
                      <span style={{ fontSize: '16px', fontWeight: '600' }}>Imagen cargada</span>
                    </div>
                  ) : (
                    <>
                      <Upload style={{ width: '40px', height: '40px', color: '#9ca3af', marginBottom: '8px' }} />
                      <span style={{ fontSize: '14px', fontWeight: '500', color: '#374151' }}>Click para subir comprobante</span>
                      <span style={{ fontSize: '12px', color: '#9ca3af' }}>PNG, JPG hasta 5MB</span>
                    </>
                  )}
                </label>
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setMethod(null)} style={buttonSecondaryStyle}>Atrás</button>
                <button
                  onClick={handleSubmitVesRecharge}
                  disabled={loading || !amount || !proofImage}
                  style={{ ...buttonPrimaryStyle, opacity: loading || !amount || !proofImage ? 0.5 : 1 }}
                  data-testid="submit-ves"
                >
                  {loading ? 'Enviando...' : 'Enviar recarga'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
