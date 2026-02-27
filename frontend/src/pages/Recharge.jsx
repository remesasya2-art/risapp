import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, QrCode, Copy, CheckCircle, Upload, Clock, Banknote, AlertCircle
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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-green-600 to-green-700 text-white">
        <div className="max-w-2xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/10 rounded-lg">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="font-bold text-lg">Recargar saldo</h1>
              <p className="text-green-200 text-sm">Balance: {(user?.balance_ris || 0).toFixed(2)} RIS</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-6">
        {/* Method Selection */}
        {!method && (
          <div className="space-y-4">
            <h2 className="font-bold text-gray-900 text-lg">Selecciona el método de pago</h2>
            
            <button
              onClick={() => setMethod('pix')}
              className="w-full bg-white rounded-2xl p-6 shadow-sm hover:shadow-md transition-all text-left border-2 border-transparent hover:border-green-500"
            >
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-green-100 flex items-center justify-center">
                  <QrCode className="w-7 h-7 text-green-600" />
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900">PIX (Brasil)</h3>
                  <p className="text-sm text-gray-500">Pago instantáneo • 1 BRL = 1 RIS</p>
                </div>
                <div className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium">
                  Recomendado
                </div>
              </div>
            </button>

            <button
              onClick={() => setMethod('ves')}
              className="w-full bg-white rounded-2xl p-6 shadow-sm hover:shadow-md transition-all text-left border-2 border-transparent hover:border-blue-500"
            >
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-blue-100 flex items-center justify-center">
                  <Banknote className="w-7 h-7 text-blue-600" />
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900">Bolívares (Venezuela)</h3>
                  <p className="text-sm text-gray-500">Transferencia bancaria • {rates.ves_to_ris} VES = 1 RIS</p>
                </div>
              </div>
            </button>
          </div>
        )}

        {/* PIX Flow - Step 1 */}
        {method === 'pix' && step === 1 && (
          <div className="bg-white rounded-2xl p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center">
                <QrCode className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Recarga con PIX</h2>
                <p className="text-sm text-gray-500">Ingresa los datos de pago</p>
              </div>
            </div>

            {user?.verification_status !== 'verified' && (
              <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-800">Verificación requerida</p>
                  <p className="text-sm text-amber-700 mt-1">Debes verificar tu cuenta antes de usar PIX.</p>
                  <button 
                    onClick={() => navigate('/verification')}
                    className="mt-2 text-sm font-medium text-amber-800 underline"
                  >
                    Verificar ahora
                  </button>
                </div>
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Monto (BRL)</label>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full px-4 py-4 text-2xl font-bold rounded-xl border border-gray-200 focus:ring-2 focus:ring-green-500"
                  placeholder="0.00"
                  min="10"
                  max="2000"
                />
                <p className="text-sm text-gray-500 mt-1">Mínimo: R$ 10 • Máximo: R$ 2.000</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">CPF del pagador</label>
                <input
                  type="text"
                  value={cpf}
                  onChange={handleCpfChange}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-green-500"
                  placeholder="000.000.000-00"
                />
                <p className="text-sm text-gray-500 mt-1">Requerido para generar el PIX</p>
              </div>

              <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                <p className="text-sm text-green-700">Recibirás</p>
                <p className="text-2xl font-bold text-green-800">{amountRis.toFixed(2)} RIS</p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setMethod(null)}
                  className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
                >
                  Atrás
                </button>
                <button
                  onClick={handleGeneratePix}
                  disabled={loading || !amount || parseFloat(amount) < 10 || cpf.replace(/\D/g, '').length !== 11}
                  className="flex-1 py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Generando...' : 'Generar PIX'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* PIX Flow - Step 2 (QR Code) */}
        {method === 'pix' && step === 2 && pixData && (
          <div className="bg-white rounded-2xl p-6 shadow-sm">
            <div className="text-center mb-6">
              <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
                <QrCode className="w-8 h-8 text-green-600" />
              </div>
              <h2 className="font-bold text-gray-900 text-xl">PIX generado</h2>
              <p className="text-gray-500">Escanea el QR o copia el código</p>
            </div>

            {pixData.qr_code_base64 && (
              <div className="flex justify-center mb-6">
                <img 
                  src={`data:image/png;base64,${pixData.qr_code_base64}`} 
                  alt="QR Code PIX" 
                  className="w-48 h-48 rounded-xl border-2 border-gray-200"
                />
              </div>
            )}

            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <p className="text-sm text-gray-500 mb-2">Código PIX (Copia y Pega)</p>
              <p className="text-xs font-mono break-all text-gray-700 mb-3 bg-white p-2 rounded border">
                {pixData.pix_code?.substring(0, 80)}...
              </p>
              <button
                onClick={handleCopyPix}
                className="w-full flex items-center justify-center gap-2 py-3 bg-green-600 hover:bg-green-700 text-white rounded-xl font-medium"
              >
                <Copy className="w-4 h-4" />
                Copiar código completo
              </button>
            </div>

            <div className="flex items-center gap-2 text-amber-600 bg-amber-50 rounded-xl p-3 mb-4">
              <Clock className="w-5 h-5 flex-shrink-0" />
              <span className="text-sm">Este código expira en 30 minutos</span>
            </div>

            <div className="space-y-3">
              <button
                onClick={() => { refreshUser(); navigate('/history'); }}
                className="w-full py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
              >
                Ver historial de transacciones
              </button>
              <button
                onClick={() => { setStep(1); setPixData(null); setAmount(''); }}
                className="w-full py-3 px-4 text-green-600 hover:bg-green-50 font-medium rounded-xl"
              >
                Generar otro PIX
              </button>
            </div>
          </div>
        )}

        {/* VES Flow */}
        {method === 'ves' && (
          <div className="bg-white rounded-2xl p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center">
                <Banknote className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Recarga con Bolívares</h2>
                <p className="text-sm text-gray-500">Tasa: {rates.ves_to_ris} VES = 1 RIS</p>
              </div>
            </div>

            {/* Bank Info */}
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
              <h3 className="font-medium text-blue-900 mb-3">Datos para transferencia</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-blue-700">Banco:</span>
                  <span className="font-medium text-blue-900">{vesPaymentInfo.bank_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-700">Titular:</span>
                  <span className="font-medium text-blue-900">{vesPaymentInfo.account_holder}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-700">Cuenta:</span>
                  <span className="font-medium text-blue-900">{vesPaymentInfo.account_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-700">Tipo:</span>
                  <span className="font-medium text-blue-900">{vesPaymentInfo.account_type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-700">Cédula/RIF:</span>
                  <span className="font-medium text-blue-900">{vesPaymentInfo.id_document}</span>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Monto transferido (VES)</label>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full px-4 py-4 text-2xl font-bold rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500"
                  placeholder="0.00"
                />
              </div>

              <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                <p className="text-sm text-green-700">Recibirás</p>
                <p className="text-2xl font-bold text-green-800">{amountRis.toFixed(2)} RIS</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Comprobante de pago *</label>
                <input type="file" accept="image/*" onChange={handleFileChange} className="hidden" id="proof-upload" />
                <label
                  htmlFor="proof-upload"
                  className={`flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
                    proofImage ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-blue-500'
                  }`}
                >
                  {proofImage ? (
                    <div className="flex items-center gap-2 text-green-600">
                      <CheckCircle className="w-6 h-6" />
                      <span className="font-medium">Imagen cargada</span>
                    </div>
                  ) : (
                    <>
                      <Upload className="w-8 h-8 text-gray-400 mb-2" />
                      <span className="text-sm text-gray-500">Click para subir comprobante</span>
                    </>
                  )}
                </label>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setMethod(null)}
                  className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
                >
                  Atrás
                </button>
                <button
                  onClick={handleSubmitVesRecharge}
                  disabled={loading || !amount || !proofImage}
                  className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl disabled:opacity-50"
                >
                  {loading ? 'Enviando...' : 'Enviar recarga'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
