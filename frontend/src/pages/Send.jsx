import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, User, Calculator, AlertCircle, CheckCircle, Plus, X, ArrowRight
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

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
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);
  
  const [amount, setAmount] = useState('');
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [newBeneficiary, setNewBeneficiary] = useState({
    full_name: '', id_document: '', phone_number: '', bank: '', bank_code: '', account_number: '',
  });

  useEffect(() => { loadBeneficiaries(); }, []);

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
    setNewBeneficiary({ ...newBeneficiary, bank_code: bankCode, bank: bank?.name || '' });
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
      setNewBeneficiary({ full_name: '', id_document: '', phone_number: '', bank: '', bank_code: '', account_number: '' });
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
      await api.post('/withdrawals', { amount_ris: parseFloat(amount), beneficiary_data: selectedBeneficiary });
      toast.success('¡Envío registrado! Será procesado pronto.');
      await refreshUser();
      navigate('/history');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar envío');
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
    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.08)',
    padding: '32px'
  };

  const inputStyle = {
    width: '100%', padding: '14px 16px', borderRadius: '14px',
    border: '1px solid #d1d5db', fontSize: '16px', outline: 'none'
  };

  const buttonPrimaryStyle = {
    backgroundColor: '#6366f1', color: 'white', borderRadius: '14px', height: '56px',
    padding: '0 32px', fontWeight: '600', fontSize: '16px', border: 'none', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', width: '100%'
  };

  const buttonSecondaryStyle = {
    backgroundColor: '#f3f4f6', color: '#374151', borderRadius: '14px', height: '56px',
    padding: '0 32px', fontWeight: '600', fontSize: '16px', border: 'none', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', width: '100%'
  };

  return (
    <div style={pageStyle} data-testid="send-page">
      <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
          <button 
            onClick={() => navigate(-1)} 
            style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.8)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            data-testid="back-button"
          >
            <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
          </button>
          <div>
            <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Enviar a Venezuela</h1>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>1 RIS = {rates?.ris_to_ves?.toFixed(2) || '0.00'} VES</p>
          </div>
        </div>

        {/* Progress Steps */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '24px' }}>
          {[1, 2, 3].map((s) => (
            <div key={s} style={{ display: 'flex', alignItems: 'center' }}>
              <div style={{
                width: '36px', height: '36px', borderRadius: '50%', fontSize: '14px', fontWeight: '600',
                backgroundColor: step >= s ? '#6366f1' : '#e5e7eb', color: step >= s ? '#ffffff' : '#6b7280',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>{s}</div>
              {s < 3 && <div style={{ width: '48px', height: '4px', marginLeft: '4px', marginRight: '4px', borderRadius: '2px', backgroundColor: step > s ? '#6366f1' : '#e5e7eb' }} />}
            </div>
          ))}
        </div>

        {/* Step 1: Amount */}
        {step === 1 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '16px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Calculator style={{ width: '28px', height: '28px', color: '#2563eb' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Monto a enviar</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Saldo: {(user?.balance_ris || 0).toFixed(2)} RIS</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Envías (RIS)</label>
                <input
                  type="number" value={amount} onChange={(e) => setAmount(e.target.value)}
                  style={{ ...inputStyle, fontSize: '28px', fontWeight: '700' }} placeholder="0.00"
                  data-testid="send-amount"
                />
              </div>

              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '16px' }}>
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Beneficiario recibe</p>
                <p style={{ fontSize: '32px', fontWeight: '700', color: '#15803d', margin: 0 }}>{amountVes.toFixed(2)} VES</p>
              </div>

              {amount && parseFloat(amount) > (user?.balance_ris || 0) && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px', backgroundColor: '#fee2e2', borderRadius: '12px' }}>
                  <AlertCircle style={{ width: '20px', height: '20px', color: '#dc2626' }} />
                  <span style={{ color: '#dc2626', fontSize: '14px' }}>Saldo insuficiente</span>
                </div>
              )}

              <button onClick={() => setStep(2)} disabled={!isValidAmount} style={{ ...buttonPrimaryStyle, opacity: isValidAmount ? 1 : 0.5 }} data-testid="continue-step1">
                Continuar <ArrowRight style={{ width: '20px', height: '20px' }} />
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Beneficiary */}
        {step === 2 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Seleccionar beneficiario</h2>
              <button onClick={() => setShowNewBeneficiary(true)} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 12px', backgroundColor: '#eff6ff', color: '#2563eb', borderRadius: '10px', border: 'none', cursor: 'pointer', fontSize: '14px', fontWeight: '500' }}>
                <Plus style={{ width: '16px', height: '16px' }} /> Nuevo
              </button>
            </div>

            {beneficiaries.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '32px' }}>
                <div style={{ width: '80px', height: '80px', borderRadius: '50%', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <User style={{ width: '40px', height: '40px', color: '#d1d5db' }} />
                </div>
                <p style={{ color: '#6b7280', margin: '0 0 16px 0' }}>No tienes beneficiarios guardados</p>
                <button onClick={() => setShowNewBeneficiary(true)} style={{ color: '#6366f1', fontWeight: '500', background: 'none', border: 'none', cursor: 'pointer' }}>Agregar beneficiario</button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {beneficiaries.map((b) => (
                  <button
                    key={b.beneficiary_id} onClick={() => setSelectedBeneficiary(b)}
                    style={{
                      width: '100%', padding: '16px', borderRadius: '16px', cursor: 'pointer', textAlign: 'left',
                      border: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '2px solid #6366f1' : '2px solid #e5e7eb',
                      backgroundColor: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '#eff6ff' : '#ffffff'
                    }}
                    data-testid={`beneficiary-${b.beneficiary_id}`}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <User style={{ width: '24px', height: '24px', color: '#6b7280' }} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                        <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>{b.bank} • ****{b.account_number?.slice(-4)}</p>
                      </div>
                      {selectedBeneficiary?.beneficiary_id === b.beneficiary_id && <CheckCircle style={{ width: '24px', height: '24px', color: '#6366f1' }} />}
                    </div>
                  </button>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
              <button onClick={() => setStep(1)} style={buttonSecondaryStyle}>Atrás</button>
              <button onClick={() => setStep(3)} disabled={!selectedBeneficiary} style={{ ...buttonPrimaryStyle, opacity: selectedBeneficiary ? 1 : 0.5 }} data-testid="continue-step2">
                Continuar <ArrowRight style={{ width: '20px', height: '20px' }} />
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Confirm */}
        {step === 3 && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: '0 0 24px 0', textAlign: 'center' }}>Confirmar envío</h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
              <div style={{ padding: '20px', backgroundColor: '#f3f4f6', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 4px 0' }}>Envías</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#111827', margin: 0 }}>{parseFloat(amount).toFixed(2)} RIS</p>
              </div>
              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Beneficiario recibe</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#15803d', margin: 0 }}>{amountVes.toFixed(2)} VES</p>
              </div>
              <div style={{ padding: '20px', backgroundColor: '#f8f9fa', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 12px 0' }}>Beneficiario</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <User style={{ width: '24px', height: '24px', color: '#2563eb' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>{selectedBeneficiary?.full_name}</p>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>{selectedBeneficiary?.bank}</p>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>{selectedBeneficiary?.account_number}</p>
                  </div>
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => setStep(2)} style={buttonSecondaryStyle}>Atrás</button>
              <button onClick={handleSend} disabled={loading} style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a', opacity: loading ? 0.5 : 1 }} data-testid="confirm-send">
                {loading ? 'Procesando...' : 'Confirmar envío'}
              </button>
            </div>
          </div>
        )}

        {/* New Beneficiary Modal */}
        {showNewBeneficiary && (
          <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}>
            <div style={{ backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', width: '100%', maxWidth: '450px', maxHeight: '90vh', overflowY: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Nuevo beneficiario</h3>
                <button onClick={() => setShowNewBeneficiary(false)} style={{ width: '36px', height: '36px', borderRadius: '10px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Nombre completo *</label>
                  <input type="text" value={newBeneficiary.full_name} onChange={(e) => setNewBeneficiary({...newBeneficiary, full_name: e.target.value})} style={inputStyle} placeholder="Nombre del beneficiario" />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Cédula de identidad *</label>
                  <input type="text" value={newBeneficiary.id_document} onChange={(e) => setNewBeneficiary({...newBeneficiary, id_document: e.target.value})} style={inputStyle} placeholder="V-12345678" />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Teléfono</label>
                  <input type="tel" value={newBeneficiary.phone_number} onChange={(e) => setNewBeneficiary({...newBeneficiary, phone_number: e.target.value})} style={inputStyle} placeholder="0412-1234567" />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Banco *</label>
                  <select value={newBeneficiary.bank_code} onChange={(e) => handleBankChange(e.target.value)} style={inputStyle}>
                    <option value="">Seleccionar banco</option>
                    {VENEZUELAN_BANKS.map((bank) => <option key={bank.code} value={bank.code}>{bank.name}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Número de cuenta *</label>
                  <input type="text" value={newBeneficiary.account_number} onChange={(e) => setNewBeneficiary({...newBeneficiary, account_number: e.target.value})} style={inputStyle} placeholder="01020123456789012345" />
                </div>
                <button onClick={handleSaveBeneficiary} disabled={loading} style={{ ...buttonPrimaryStyle, marginTop: '8px', opacity: loading ? 0.5 : 1 }} data-testid="save-beneficiary">
                  {loading ? 'Guardando...' : 'Guardar beneficiario'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
