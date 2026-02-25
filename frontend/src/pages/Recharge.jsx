import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, ArrowDownLeft, CreditCard, QrCode, 
  Copy, CheckCircle, Upload, Clock, Banknote
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function Recharge() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  const [method, setMethod] = useState(null); // 'pix' or 'ves'
  const [amount, setAmount] = useState('');
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [pixData, setPixData] = useState(null);
  const [proofImage, setProofImage] = useState(null);

  // VES payment info (from backend)
  const vesPaymentInfo = {
    bank_name: 'Banco de Venezuela',
    account_holder: 'RIS REMESAS C.A.',
    account_number: '01020123456789012345',
    account_type: 'Corriente',
    phone_number: '04121234567',
    id_document: 'J-12345678-9',
  };

  const amountRis = method === 'ves' && amount ? parseFloat(amount) / rates.ves_to_ris : parseFloat(amount) || 0;

  const handleGeneratePix = async () => {
    if (!amount || parseFloat(amount) < 10) {
      toast.error('El monto mínimo es 10 BRL');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/recharge/pix', { amount: parseFloat(amount) });
      setPixData(response.data);
      setStep(2);
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
      reader.onload = () => {
        setProofImage(reader.result);
      };
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
              <p className="text-green-200 text-sm">Balance actual: {(user?.balance_ris || 0).toFixed(2)} RIS</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-6">
        {/* Method Selection */}
        {!method && (
          <div className="space-y-4 animate-fadeIn">
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

        {/* PIX Flow */}
        {method === 'pix' && step === 1 && (
          <div className="bg-white rounded-2xl p-6 shadow-sm animate-fadeIn">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center">
                <QrCode className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Recarga con PIX</h2>
                <p className="text-sm text-gray-500">Ingresa el monto en Reales</p>
              </div>
            </div>

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
                />
                <p className="text-sm text-gray-500 mt-1">Mínimo: 10 BRL</p>
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
                  disabled={loading || !amount || parseFloat(amount) < 10}
                  className="flex-1 py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-xl disabled:opacity-50"
                >
                  {loading ? 'Generando...' : 'Generar PIX'}
                </button>
              </div>
            </div>
          </div>
        )}

        {method === 'pix' && step === 2 && pixData && (
          <div className="bg-white rounded-2xl p-6 shadow-sm animate-fadeIn">
            <div className="text-center mb-6">
              <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
                <QrCode className="w-8 h-8 text-green-600" />
              </div>
              <h2 className="font-bold text-gray-900 text-xl">PIX generado</h2>
              <p className="text-gray-500">Escanea o copia el código</p>
            </div>

            {pixData.qr_code_base64 && (
              <div className="flex justify-center mb-6">
                <img 
                  src={`data:image/png;base64,${pixData.qr_code_base64}`} 
                  alt="QR Code PIX" 
                  className="w-48 h-48 rounded-xl border"
                />
              </div>
            )}

            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <p className="text-sm text-gray-500 mb-2">Código PIX (Copia y Pega)</p>
              <p className="text-xs font-mono break-all text-gray-700 mb-2">{pixData.pix_code?.substring(0, 50)}...</p>
              <button
                onClick={handleCopyPix}
                className="w-full flex items-center justify-center gap-2 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg"
              >
                <Copy className="w-4 h-4" />
                Copiar código
              </button>
            </div>

            <div className="flex items-center gap-2 text-amber-600 bg-amber-50 rounded-xl p-3">
              <Clock className="w-5 h-5" />
              <span className="text-sm">Este código expira en 30 minutos</span>
            </div>

            <button
              onClick={() => navigate('/history')}
              className="w-full mt-4 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
            >
              Ver historial de transacciones
            </button>
          </div>
        )}

        {/* VES Flow */}
        {method === 'ves' && (
          <div className="space-y-4 animate-fadeIn">
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
                  <div className="flex justify-between">
                    <span className="text-blue-700">Teléfono:</span>
                    <span className="font-medium text-blue-900">{vesPaymentInfo.phone_number}</span>
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
                  <div className="relative">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleFileChange}
                      className="hidden"
                      id="proof-upload"
                    />
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
          </div>
        )}
      </main>
    </div>
  );
}
