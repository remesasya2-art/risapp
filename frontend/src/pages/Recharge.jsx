import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, QrCode, Copy, CheckCircle, Upload, Clock, Banknote, AlertCircle,
  CreditCard, Wallet, ArrowRight, Shield, Zap
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
      const errorMsg = error.response?.data?.detail || 'Error al generar PIX';
      toast.error(errorMsg);
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

  return (
    <div className="min-h-screen bg-gray-50" data-testid="recharge-page">
      {/* Header */}
      <header className="bg-gradient-to-r from-green-600 to-green-700 text-white sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => navigate(-1)} 
              className="p-2 hover:bg-white/10 rounded-xl transition-colors"
              data-testid="back-button"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex-1">
              <h1 className="font-bold text-xl">Recargar saldo</h1>
              <p className="text-green-200 text-sm">Balance actual: {(user?.balance_ris || 0).toFixed(2)} RIS</p>
            </div>
            <div className="w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center">
              <Wallet className="w-6 h-6" />
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6">
        {/* Method Selection */}
        {!method && (
          <div className="space-y-6">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Selecciona el método de pago</h2>
              <p className="text-gray-500">Elige cómo deseas recargar tu saldo RIS</p>
            </div>
            
            <div className="grid gap-4">
              {/* PIX Option */}
              <button
                onClick={() => setMethod('pix')}
                className="w-full bg-white rounded-2xl p-6 shadow-sm hover:shadow-lg transition-all text-left border-2 border-transparent hover:border-green-500 group"
                data-testid="select-pix"
              >
                <div className="flex items-center gap-4">
                  <div className="w-16 h-16 rounded-2xl bg-green-100 flex items-center justify-center group-hover:bg-green-200 transition-colors">
                    <QrCode className="w-8 h-8 text-green-600" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-bold text-gray-900">PIX (Brasil)</h3>
                      <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded-full text-xs font-semibold">Recomendado</span>
                    </div>
                    <p className="text-gray-500 text-sm">Pago instantáneo • Sin comisiones</p>
                    <p className="text-green-600 font-semibold text-sm mt-1">1 BRL = 1 RIS</p>
                  </div>
                  <ArrowRight className="w-6 h-6 text-gray-300 group-hover:text-green-500 transition-colors" />
                </div>
                
                <div className="flex items-center gap-4 mt-4 pt-4 border-t border-gray-100">
                  <div className="flex items-center gap-2 text-gray-500 text-xs">
                    <Zap className="w-4 h-4 text-green-500" />
                    <span>Instantáneo</span>
                  </div>
                  <div className="flex items-center gap-2 text-gray-500 text-xs">
                    <Shield className="w-4 h-4 text-green-500" />
                    <span>Seguro</span>
                  </div>
                </div>
              </button>

              {/* VES Option */}
              <button
                onClick={() => setMethod('ves')}
                className="w-full bg-white rounded-2xl p-6 shadow-sm hover:shadow-lg transition-all text-left border-2 border-transparent hover:border-blue-500 group"
                data-testid="select-ves"
              >
                <div className="flex items-center gap-4">
                  <div className="w-16 h-16 rounded-2xl bg-blue-100 flex items-center justify-center group-hover:bg-blue-200 transition-colors">
                    <Banknote className="w-8 h-8 text-blue-600" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-bold text-gray-900">Bolívares (Venezuela)</h3>
                    <p className="text-gray-500 text-sm">Transferencia bancaria</p>
                    <p className="text-blue-600 font-semibold text-sm mt-1">{rates.ves_to_ris.toFixed(0)} VES = 1 RIS</p>
                  </div>
                  <ArrowRight className="w-6 h-6 text-gray-300 group-hover:text-blue-500 transition-colors" />
                </div>
              </button>
            </div>

            {/* Help Section */}
            <div className="bg-orange-50 rounded-2xl p-4 border border-orange-100">
              <p className="text-sm text-orange-800">
                <strong>¿Necesitas ayuda?</strong> Visita nuestra{' '}
                <Link to="/support" className="text-orange-600 underline font-medium">página de soporte</Link>
                {' '}para asistencia.
              </p>
            </div>
          </div>
        )}

        {/* PIX Flow - Step 1 */}
        {method === 'pix' && step === 1 && (
          <div className="space-y-6">
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <div className="flex items-center gap-4 mb-6">
                <div className="w-14 h-14 rounded-2xl bg-green-100 flex items-center justify-center">
                  <QrCode className="w-7 h-7 text-green-600" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900">Recarga con PIX</h2>
                  <p className="text-gray-500">Ingresa los datos de pago</p>
                </div>
              </div>

              {user?.verification_status !== 'verified' && (
                <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-amber-800">Verificación requerida</p>
                    <p className="text-sm text-amber-700 mt-1">Debes verificar tu cuenta antes de usar PIX.</p>
                    <button 
                      onClick={() => navigate('/verification')}
                      className="mt-2 text-sm font-semibold text-amber-800 underline"
                    >
                      Verificar ahora
                    </button>
                  </div>
                </div>
              )}

              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    Monto a recargar (BRL)
                  </label>
                  <input
                    type="number"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="w-full px-4 py-4 text-3xl font-bold rounded-xl border-2 border-gray-200 focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-all"
                    placeholder="0.00"
                    min="10"
                    max="2000"
                    data-testid="pix-amount"
                  />
                  <p className="text-sm text-gray-500 mt-2">Mínimo: R$ 10 • Máximo: R$ 2.000</p>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    CPF del pagador
                  </label>
                  <input
                    type="text"
                    value={cpf}
                    onChange={handleCpfChange}
                    className="w-full px-4 py-4 text-lg rounded-xl border-2 border-gray-200 focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-all"
                    placeholder="000.000.000-00"
                    data-testid="pix-cpf"
                  />
                  <p className="text-sm text-gray-500 mt-2">Requerido para generar el código PIX</p>
                </div>

                <div className="bg-green-50 rounded-xl p-5 border border-green-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-green-700 font-medium">Recibirás en tu cuenta</p>
                      <p className="text-3xl font-bold text-green-700 mt-1">{amountRis.toFixed(2)} RIS</p>
                    </div>
                    <div className="w-12 h-12 bg-green-200 rounded-xl flex items-center justify-center">
                      <CheckCircle className="w-6 h-6 text-green-600" />
                    </div>
                  </div>
                </div>

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => setMethod(null)}
                    className="flex-1 py-4 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold rounded-xl transition-colors"
                    data-testid="back-to-methods"
                  >
                    Atrás
                  </button>
                  <button
                    onClick={handleGeneratePix}
                    disabled={loading || !amount || parseFloat(amount) < 10 || cpf.replace(/\D/g, '').length !== 11}
                    className="flex-1 py-4 px-4 bg-green-600 hover:bg-green-700 text-white font-semibold rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    data-testid="generate-pix"
                  >
                    {loading ? 'Generando...' : 'Generar PIX'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* PIX Flow - Step 2 (QR Code) */}
        {method === 'pix' && step === 2 && pixData && (
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="text-center mb-6">
              <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
                <QrCode className="w-10 h-10 text-green-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900">PIX generado</h2>
              <p className="text-gray-500">Escanea el QR o copia el código</p>
            </div>

            {pixData.qr_code_base64 && (
              <div className="flex justify-center mb-6">
                <div className="p-4 bg-white rounded-2xl border-2 border-gray-200">
                  <img 
                    src={`data:image/png;base64,${pixData.qr_code_base64}`} 
                    alt="QR Code PIX" 
                    className="w-52 h-52"
                  />
                </div>
              </div>
            )}

            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <p className="text-sm text-gray-500 mb-2 font-medium">Código PIX (Copia y Pega)</p>
              <p className="text-xs font-mono break-all text-gray-700 mb-3 bg-white p-3 rounded-lg border">
                {pixData.pix_code?.substring(0, 80)}...
              </p>
              <button
                onClick={handleCopyPix}
                className="w-full flex items-center justify-center gap-2 py-3 bg-green-600 hover:bg-green-700 text-white rounded-xl font-semibold transition-colors"
                data-testid="copy-pix"
              >
                <Copy className="w-5 h-5" />
                Copiar código completo
              </button>
            </div>

            <div className="flex items-center gap-3 text-amber-600 bg-amber-50 rounded-xl p-4 mb-4 border border-amber-200">
              <Clock className="w-6 h-6 flex-shrink-0" />
              <span className="font-medium">Este código expira en 30 minutos</span>
            </div>

            <div className="space-y-3">
              <button
                onClick={() => { refreshUser(); navigate('/history'); }}
                className="w-full py-4 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold rounded-xl transition-colors"
              >
                Ver historial de transacciones
              </button>
              <button
                onClick={() => { setStep(1); setPixData(null); setAmount(''); }}
                className="w-full py-4 px-4 text-green-600 hover:bg-green-50 font-semibold rounded-xl transition-colors"
              >
                Generar otro PIX
              </button>
            </div>
          </div>
        )}

        {/* VES Flow */}
        {method === 'ves' && (
          <div className="space-y-6">
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <div className="flex items-center gap-4 mb-6">
                <div className="w-14 h-14 rounded-2xl bg-blue-100 flex items-center justify-center">
                  <Banknote className="w-7 h-7 text-blue-600" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900">Recarga con Bolívares</h2>
                  <p className="text-gray-500">Tasa: {rates.ves_to_ris.toFixed(0)} VES = 1 RIS</p>
                </div>
              </div>

              {/* Bank Info */}
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-6">
                <h3 className="font-semibold text-blue-900 mb-4 flex items-center gap-2">
                  <CreditCard className="w-5 h-5" />
                  Datos para transferencia
                </h3>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between py-2 border-b border-blue-200">
                    <span className="text-blue-700">Banco:</span>
                    <span className="font-semibold text-blue-900">{vesPaymentInfo.bank_name}</span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-blue-200">
                    <span className="text-blue-700">Titular:</span>
                    <span className="font-semibold text-blue-900">{vesPaymentInfo.account_holder}</span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-blue-200">
                    <span className="text-blue-700">Cuenta:</span>
                    <span className="font-semibold text-blue-900">{vesPaymentInfo.account_number}</span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-blue-200">
                    <span className="text-blue-700">Tipo:</span>
                    <span className="font-semibold text-blue-900">{vesPaymentInfo.account_type}</span>
                  </div>
                  <div className="flex justify-between py-2">
                    <span className="text-blue-700">Cédula/RIF:</span>
                    <span className="font-semibold text-blue-900">{vesPaymentInfo.id_document}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">Monto transferido (VES)</label>
                  <input
                    type="number"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="w-full px-4 py-4 text-3xl font-bold rounded-xl border-2 border-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
                    placeholder="0.00"
                    data-testid="ves-amount"
                  />
                </div>

                <div className="bg-green-50 border border-green-200 rounded-xl p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-green-700 font-medium">Recibirás en tu cuenta</p>
                      <p className="text-3xl font-bold text-green-700 mt-1">{amountRis.toFixed(2)} RIS</p>
                    </div>
                    <div className="w-12 h-12 bg-green-200 rounded-xl flex items-center justify-center">
                      <CheckCircle className="w-6 h-6 text-green-600" />
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">Comprobante de pago *</label>
                  <input type="file" accept="image/*" onChange={handleFileChange} className="hidden" id="proof-upload" />
                  <label
                    htmlFor="proof-upload"
                    className={`flex flex-col items-center justify-center w-full h-36 border-2 border-dashed rounded-xl cursor-pointer transition-all ${
                      proofImage ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-blue-500 hover:bg-blue-50'
                    }`}
                  >
                    {proofImage ? (
                      <div className="flex items-center gap-3 text-green-600">
                        <CheckCircle className="w-8 h-8" />
                        <span className="font-semibold text-lg">Imagen cargada</span>
                      </div>
                    ) : (
                      <>
                        <Upload className="w-10 h-10 text-gray-400 mb-2" />
                        <span className="font-medium text-gray-600">Click para subir comprobante</span>
                        <span className="text-sm text-gray-400">PNG, JPG hasta 5MB</span>
                      </>
                    )}
                  </label>
                </div>

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => setMethod(null)}
                    className="flex-1 py-4 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold rounded-xl transition-colors"
                  >
                    Atrás
                  </button>
                  <button
                    onClick={handleSubmitVesRecharge}
                    disabled={loading || !amount || !proofImage}
                    className="flex-1 py-4 px-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl disabled:opacity-50 transition-colors"
                    data-testid="submit-ves"
                  >
                    {loading ? 'Enviando...' : 'Enviar recarga'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
