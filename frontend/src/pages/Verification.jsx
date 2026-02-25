import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, Shield, Camera, Upload, User, CreditCard, 
  FileText, CheckCircle, AlertCircle, Loader
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function Verification() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const videoRef = useRef(null);
  const [stream, setStream] = useState(null);
  
  const [formData, setFormData] = useState({
    full_name: user?.full_name || user?.name || '',
    document_number: '',
    cpf_number: '',
    id_document_image: null,
    cpf_image: null,
    selfie_image: null,
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

  const startCamera = async () => {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: 'user', width: 640, height: 480 } 
      });
      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch (error) {
      toast.error('No se pudo acceder a la cámara');
    }
  };

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      setStream(null);
    }
  };

  const capturePhoto = () => {
    if (videoRef.current) {
      const canvas = document.createElement('canvas');
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      canvas.getContext('2d').drawImage(videoRef.current, 0, 0);
      const selfieData = canvas.toDataURL('image/jpeg', 0.8);
      setFormData({ ...formData, selfie_image: selfieData });
      stopCamera();
    }
  };

  const handleSubmit = async () => {
    if (!formData.full_name || !formData.document_number || !formData.cpf_number) {
      toast.error('Completa todos los campos');
      return;
    }
    if (!formData.id_document_image || !formData.cpf_image || !formData.selfie_image) {
      toast.error('Sube todos los documentos requeridos');
      return;
    }

    setLoading(true);
    try {
      await api.post('/verification/submit', formData);
      toast.success('Documentos enviados para verificación');
      await refreshUser();
      navigate('/');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al enviar documentos');
    } finally {
      setLoading(false);
    }
  };

  // Already verified
  if (user?.verification_status === 'verified') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl p-8 text-center max-w-md shadow-sm">
          <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-green-100 flex items-center justify-center">
            <CheckCircle className="w-10 h-10 text-green-600" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">¡Cuenta verificada!</h2>
          <p className="text-gray-500 mb-6">Tu identidad ha sido verificada exitosamente.</p>
          <button
            onClick={() => navigate('/')}
            className="w-full py-3 px-4 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-xl"
          >
            Ir al inicio
          </button>
        </div>
      </div>
    );
  }

  // Pending verification
  if (user?.verification_status === 'pending') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl p-8 text-center max-w-md shadow-sm">
          <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-amber-100 flex items-center justify-center">
            <Loader className="w-10 h-10 text-amber-600 animate-spin" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Verificación en proceso</h2>
          <p className="text-gray-500 mb-6">
            Tu documentación está siendo revisada. Te notificaremos cuando esté lista.
          </p>
          <button
            onClick={() => navigate('/')}
            className="w-full py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
          >
            Volver al inicio
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-indigo-600 to-indigo-700 text-white">
        <div className="max-w-2xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/10 rounded-lg">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="font-bold text-lg">Verificación KYC</h1>
              <p className="text-indigo-200 text-sm">Paso {step} de 4</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-6">
        {/* Progress */}
        <div className="flex gap-2 mb-6">
          {[1, 2, 3, 4].map((s) => (
            <div
              key={s}
              className={`flex-1 h-2 rounded-full transition-colors ${
                step >= s ? 'bg-indigo-600' : 'bg-gray-200'
              }`}
            />
          ))}
        </div>

        {/* Step 1: Personal Info */}
        {step === 1 && (
          <div className="bg-white rounded-2xl p-6 shadow-sm animate-fadeIn">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center">
                <User className="w-6 h-6 text-indigo-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Datos personales</h2>
                <p className="text-sm text-gray-500">Ingresa tu información</p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nombre completo</label>
                <input
                  type="text"
                  value={formData.full_name}
                  onChange={(e) => setFormData({...formData, full_name: e.target.value})}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-indigo-500"
                  placeholder="Como aparece en tu documento"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Número de documento</label>
                <input
                  type="text"
                  value={formData.document_number}
                  onChange={(e) => setFormData({...formData, document_number: e.target.value})}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-indigo-500"
                  placeholder="RG o Pasaporte"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
                <input
                  type="text"
                  value={formData.cpf_number}
                  onChange={(e) => setFormData({...formData, cpf_number: e.target.value})}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-indigo-500"
                  placeholder="000.000.000-00"
                />
              </div>

              <button
                onClick={() => setStep(2)}
                disabled={!formData.full_name || !formData.document_number || !formData.cpf_number}
                className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl disabled:opacity-50"
              >
                Continuar
              </button>
            </div>
          </div>
        )}

        {/* Step 2: ID Document */}
        {step === 2 && (
          <div className="bg-white rounded-2xl p-6 shadow-sm animate-fadeIn">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center">
                <CreditCard className="w-6 h-6 text-indigo-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Documento de identidad</h2>
                <p className="text-sm text-gray-500">RG o Pasaporte (frente)</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="relative">
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleFileChange('id_document_image')}
                  className="hidden"
                  id="id-upload"
                />
                <label
                  htmlFor="id-upload"
                  className={`flex flex-col items-center justify-center w-full h-48 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
                    formData.id_document_image ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-indigo-500'
                  }`}
                >
                  {formData.id_document_image ? (
                    <div className="relative w-full h-full">
                      <img src={formData.id_document_image} alt="ID" className="w-full h-full object-contain rounded-lg" />
                      <div className="absolute top-2 right-2 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                        <CheckCircle className="w-5 h-5 text-white" />
                      </div>
                    </div>
                  ) : (
                    <>
                      <Upload className="w-10 h-10 text-gray-400 mb-2" />
                      <span className="text-gray-500">Toca para subir foto del documento</span>
                    </>
                  )}
                </label>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
                >
                  Atrás
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!formData.id_document_image}
                  className="flex-1 py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl disabled:opacity-50"
                >
                  Continuar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: CPF Document */}
        {step === 3 && (
          <div className="bg-white rounded-2xl p-6 shadow-sm animate-fadeIn">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center">
                <FileText className="w-6 h-6 text-indigo-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Documento CPF</h2>
                <p className="text-sm text-gray-500">Foto del CPF</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="relative">
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleFileChange('cpf_image')}
                  className="hidden"
                  id="cpf-upload"
                />
                <label
                  htmlFor="cpf-upload"
                  className={`flex flex-col items-center justify-center w-full h-48 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
                    formData.cpf_image ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-indigo-500'
                  }`}
                >
                  {formData.cpf_image ? (
                    <div className="relative w-full h-full">
                      <img src={formData.cpf_image} alt="CPF" className="w-full h-full object-contain rounded-lg" />
                      <div className="absolute top-2 right-2 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                        <CheckCircle className="w-5 h-5 text-white" />
                      </div>
                    </div>
                  ) : (
                    <>
                      <Upload className="w-10 h-10 text-gray-400 mb-2" />
                      <span className="text-gray-500">Toca para subir foto del CPF</span>
                    </>
                  )}
                </label>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setStep(2)}
                  className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
                >
                  Atrás
                </button>
                <button
                  onClick={() => { setStep(4); startCamera(); }}
                  disabled={!formData.cpf_image}
                  className="flex-1 py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl disabled:opacity-50"
                >
                  Continuar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Selfie */}
        {step === 4 && (
          <div className="bg-white rounded-2xl p-6 shadow-sm animate-fadeIn">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center">
                <Camera className="w-6 h-6 text-indigo-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Selfie de verificación</h2>
                <p className="text-sm text-gray-500">Será tu foto de perfil permanente</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="relative bg-gray-900 rounded-xl overflow-hidden aspect-[4/3]">
                {stream ? (
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover"
                  />
                ) : formData.selfie_image ? (
                  <img src={formData.selfie_image} alt="Selfie" className="w-full h-full object-cover" />
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-white">
                    <Camera className="w-16 h-16 mb-2 opacity-50" />
                    <p>Cámara no activa</p>
                  </div>
                )}
              </div>

              {stream ? (
                <button
                  onClick={capturePhoto}
                  className="w-full py-4 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl flex items-center justify-center gap-2"
                >
                  <Camera className="w-5 h-5" />
                  Tomar foto
                </button>
              ) : formData.selfie_image ? (
                <div className="flex gap-3">
                  <button
                    onClick={() => { setFormData({...formData, selfie_image: null}); startCamera(); }}
                    className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
                  >
                    Repetir
                  </button>
                  <button
                    onClick={handleSubmit}
                    disabled={loading}
                    className="flex-1 py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-xl disabled:opacity-50"
                  >
                    {loading ? 'Enviando...' : 'Enviar verificación'}
                  </button>
                </div>
              ) : (
                <button
                  onClick={startCamera}
                  className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl"
                >
                  Activar cámara
                </button>
              )}

              <button
                onClick={() => { stopCamera(); setStep(3); }}
                className="w-full py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
              >
                Atrás
              </button>
            </div>
          </div>
        )}

        {/* Info Box */}
        <div className="mt-6 bg-blue-50 border border-blue-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-800">
              <p className="font-medium mb-1">Información importante</p>
              <ul className="list-disc list-inside space-y-1 text-blue-700">
                <li>Tus documentos serán revisados manualmente</li>
                <li>La verificación puede tomar de 5 a 30 minutos</li>
                <li>Tu selfie será tu foto de perfil permanente</li>
              </ul>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
