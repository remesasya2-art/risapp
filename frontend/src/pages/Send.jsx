import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, ArrowUpRight, User, CreditCard, Phone, Building, 
  Calculator, AlertCircle, CheckCircle, Plus, X
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

// Venezuelan banks list
const VENEZUELAN_BANKS = [
  { code: '0102', name: 'Banco de Venezuela' },
  { code: '0104', name: 'Venezolano de Crédito' },
  { code: '0105', name: 'Mercantil' },
  { code: '0108', name: 'Provincial' },
  { code: '0114', name: 'Bancaribe' },
  { code: '0115', name: 'Exterior' },
  { code: '0116', name: 'Occidental de Descuento' },
  { code: '0128', name: 'Caroní' },
  { code: '0134', name: 'Banesco' },
  { code: '0137', name: 'Sofitasa' },
  { code: '0138', name: 'Plaza' },
  { code: '0151', name: 'Fondo Común' },
  { code: '0156', name: '100% Banco' },
  { code: '0157', name: 'Del Sur' },
  { code: '0163', name: 'Del Tesoro' },
  { code: '0166', name: 'Agrícola de Venezuela' },
  { code: '0168', name: 'Bancrecer' },
  { code: '0169', name: 'Mi Banco' },
  { code: '0171', name: 'Activo' },
  { code: '0172', name: 'Bancamiga' },
  { code: '0174', name: 'Banplus' },
  { code: '0175', name: 'Bicentenario' },
  { code: '0177', name: 'Banfanb' },
  { code: '0191', name: 'BNC' },
];

export default function Send() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  const [step, setStep] = useState(1); // 1: amount, 2: beneficiary, 3: confirm
  const [loading, setLoading] = useState(false);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);
  
  const [amount, setAmount] = useState('');
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [newBeneficiary, setNewBeneficiary] = useState({
    full_name: '',
    id_document: '',
    phone_number: '',
    bank: '',
    bank_code: '',
    account_number: '',
  });

  useEffect(() => {
    loadBeneficiaries();
  }, []);

  const loadBeneficiaries = async () => {
    try {
      const response = await api.get('/beneficiaries');
      setBeneficiaries(response.data || []);
    } catch (error) {
      console.error('Error loading beneficiaries:', error);
    }
  };

  const amountVes = amount ? parseFloat(amount) * rates.ris_to_ves : 0;
  const isValidAmount = amount && parseFloat(amount) > 0 && parseFloat(amount) <= (user?.balance_ris || 0);

  const handleBankChange = (bankCode) => {
    const bank = VENEZUELAN_BANKS.find(b => b.code === bankCode);
    setNewBeneficiary({
      ...newBeneficiary,
      bank_code: bankCode,
      bank: bank?.name || '',
    });
  };

  const handleSaveBeneficiary = async () => {
    if (!newBeneficiary.full_name || !newBeneficiary.id_document || !newBeneficiary.bank || !newBeneficiary.account_number) {
      toast.error('Completa todos los campos del beneficiario');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/beneficiaries', newBeneficiary);
      toast.success('Beneficiario guardado');
      await loadBeneficiaries();
      setSelectedBeneficiary(response.data);
      setShowNewBeneficiary(false);
      setNewBeneficiary({
        full_name: '',
        id_document: '',
        phone_number: '',
        bank: '',
        bank_code: '',
        account_number: '',
      });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al guardar beneficiario');
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!isValidAmount || !selectedBeneficiary) {
      toast.error('Verifica los datos de envío');
      return;
    }

    setLoading(true);
    try {
      await api.post('/withdrawals', {
        amount_ris: parseFloat(amount),
        beneficiary_data: selectedBeneficiary,
      });
      toast.success('¡Envío registrado! Será procesado pronto.');
      await refreshUser();
      navigate('/history');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar envío');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-blue-600 to-blue-700 text-white">
        <div className="max-w-xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/10 rounded-lg">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="font-bold text-lg">Enviar a Venezuela</h1>
              <p className="text-blue-200 text-sm">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-xl mx-auto px-4 py-6">
        {/* Progress Steps */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {[1, 2, 3].map((s) => (
            <div key={s} className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                step >= s ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'
              }`}>
                {s}
              </div>
              {s < 3 && <div className={`w-12 h-1 mx-1 ${step > s ? 'bg-blue-600' : 'bg-gray-200'}`} />}
            </div>
          ))}
        </div>

        {/* Step 1: Amount */}
        {step === 1 && (
          <div className="bg-white rounded-2xl p-6 shadow-sm animate-fadeIn">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center">
                <Calculator className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <h2 className="font-bold text-gray-900">Monto a enviar</h2>
                <p className="text-sm text-gray-500">Balance: {(user?.balance_ris || 0).toFixed(2)} RIS</p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Envías (RIS)</label>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full px-4 py-4 text-2xl font-bold rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="0.00"
                />
              </div>

              <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                <p className="text-sm text-green-700">Beneficiario recibe</p>
                <p className="text-3xl font-bold text-green-800">{amountVes.toFixed(2)} VES</p>
              </div>

              {amount && parseFloat(amount) > (user?.balance_ris || 0) && (
                <div className="flex items-center gap-2 text-red-600 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  <span>Saldo insuficiente</span>
                </div>
              )}

              <button
                onClick={() => setStep(2)}
                disabled={!isValidAmount}
                className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Continuar
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Beneficiary */}
        {step === 2 && (
          <div className="space-y-4 animate-fadeIn">
            <div className="bg-white rounded-2xl p-6 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-bold text-gray-900">Seleccionar beneficiario</h2>
                <button
                  onClick={() => setShowNewBeneficiary(true)}
                  className="flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium"
                >
                  <Plus className="w-4 h-4" />
                  Nuevo
                </button>
              </div>

              {beneficiaries.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <User className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  <p>No tienes beneficiarios guardados</p>
                  <button
                    onClick={() => setShowNewBeneficiary(true)}
                    className="mt-3 text-blue-600 hover:text-blue-700 font-medium"
                  >
                    Agregar beneficiario
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  {beneficiaries.map((b) => (
                    <button
                      key={b.beneficiary_id}
                      onClick={() => setSelectedBeneficiary(b)}
                      className={`w-full p-4 rounded-xl border-2 text-left transition-colors ${
                        selectedBeneficiary?.beneficiary_id === b.beneficiary_id
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center">
                          <User className="w-5 h-5 text-gray-600" />
                        </div>
                        <div className="flex-1">
                          <p className="font-medium text-gray-900">{b.full_name}</p>
                          <p className="text-sm text-gray-500">{b.bank} • {b.account_number.slice(-4)}</p>
                        </div>
                        {selectedBeneficiary?.beneficiary_id === b.beneficiary_id && (
                          <CheckCircle className="w-5 h-5 text-blue-600" />
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setStep(1)}
                className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl transition-colors"
              >
                Atrás
              </button>
              <button
                onClick={() => setStep(3)}
                disabled={!selectedBeneficiary}
                className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl transition-colors disabled:opacity-50"
              >
                Continuar
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Confirm */}
        {step === 3 && (
          <div className="space-y-4 animate-fadeIn">
            <div className="bg-white rounded-2xl p-6 shadow-sm">
              <h2 className="font-bold text-gray-900 mb-4">Confirmar envío</h2>

              <div className="space-y-4">
                <div className="bg-gray-50 rounded-xl p-4">
                  <p className="text-sm text-gray-500 mb-1">Envías</p>
                  <p className="text-2xl font-bold text-gray-900">{parseFloat(amount).toFixed(2)} RIS</p>
                </div>

                <div className="bg-green-50 rounded-xl p-4">
                  <p className="text-sm text-green-700 mb-1">Beneficiario recibe</p>
                  <p className="text-2xl font-bold text-green-800">{amountVes.toFixed(2)} VES</p>
                </div>

                <div className="border-t pt-4">
                  <p className="text-sm text-gray-500 mb-2">Beneficiario</p>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                      <User className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">{selectedBeneficiary?.full_name}</p>
                      <p className="text-sm text-gray-500">{selectedBeneficiary?.bank}</p>
                      <p className="text-sm text-gray-500">{selectedBeneficiary?.account_number}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setStep(2)}
                className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl transition-colors"
              >
                Atrás
              </button>
              <button
                onClick={handleSend}
                disabled={loading}
                className="flex-1 py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-xl transition-colors disabled:opacity-50"
              >
                {loading ? 'Procesando...' : 'Confirmar envío'}
              </button>
            </div>
          </div>
        )}

        {/* New Beneficiary Modal */}
        {showNewBeneficiary && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md max-h-[90vh] overflow-y-auto animate-slideUp">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-bold text-gray-900">Nuevo beneficiario</h3>
                <button onClick={() => setShowNewBeneficiary(false)} className="text-gray-400 hover:text-gray-600">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Nombre completo *</label>
                  <input
                    type="text"
                    value={newBeneficiary.full_name}
                    onChange={(e) => setNewBeneficiary({...newBeneficiary, full_name: e.target.value})}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500"
                    placeholder="Nombre del beneficiario"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Cédula de identidad *</label>
                  <input
                    type="text"
                    value={newBeneficiary.id_document}
                    onChange={(e) => setNewBeneficiary({...newBeneficiary, id_document: e.target.value})}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500"
                    placeholder="V-12345678"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Teléfono</label>
                  <input
                    type="tel"
                    value={newBeneficiary.phone_number}
                    onChange={(e) => setNewBeneficiary({...newBeneficiary, phone_number: e.target.value})}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500"
                    placeholder="0412-1234567"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Banco *</label>
                  <select
                    value={newBeneficiary.bank_code}
                    onChange={(e) => handleBankChange(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Seleccionar banco</option>
                    {VENEZUELAN_BANKS.map((bank) => (
                      <option key={bank.code} value={bank.code}>{bank.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Número de cuenta *</label>
                  <input
                    type="text"
                    value={newBeneficiary.account_number}
                    onChange={(e) => setNewBeneficiary({...newBeneficiary, account_number: e.target.value})}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500"
                    placeholder="0102-1234-12-1234567890"
                  />
                </div>

                <button
                  onClick={handleSaveBeneficiary}
                  disabled={loading}
                  className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl transition-colors disabled:opacity-50"
                >
                  {loading ? 'Guardando...' : 'Guardar beneficiario'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
