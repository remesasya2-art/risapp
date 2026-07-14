import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { FormattedNumberInput } from '../components/common/FormattedNumberInput';
import { 
  ArrowLeft, Calculator, AlertCircle, CheckCircle, Plus, X, ArrowRight,
  Smartphone, Building2, Search, User
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import PinConfirm from '../components/PinConfirm';
import { fmt } from '../utils/format';

// Lista actualizada de bancos venezolanos
const VENEZUELAN_BANKS = [
  { code: '0001', name: 'BANCO CENTRAL DE VENEZUELA' },
  { code: '0102', name: 'BANCO DE VENEZUELA' },
  { code: '0104', name: 'BANCO VENEZOLANO DE CREDITO' },
  { code: '0105', name: 'BANCO MERCANTIL' },
  { code: '0108', name: 'BANCO PROVINCIAL' },
  { code: '0114', name: 'BANCARIBE' },
  { code: '0115', name: 'BANCO EXTERIOR' },
  { code: '0128', name: 'BANCO CARONI' },
  { code: '0134', name: 'BANESCO' },
  { code: '0137', name: 'SOFITASA' },
  { code: '0138', name: 'BANCO PLAZA' },
  { code: '0145', name: 'BANCO DE COMERCIO EXTERIOR' },
  { code: '0146', name: 'BANCO DE LA GENTE EMPRENDEDORA C.A' },
  { code: '0151', name: 'FONDO COMUN BANCO UNIVERSAL' },
  { code: '0152', name: 'BANDES' },
  { code: '0156', name: '100% BANCO' },
  { code: '0157', name: 'DELSUR BANCO UNIVERSAL' },
  { code: '0163', name: 'BANCO DEL TESORO' },
  { code: '0166', name: 'BANCO AGRICOLA' },
  { code: '0168', name: 'BANCRECER' },
  { code: '0169', name: 'R4, BANCO MICROFINANCIERO, C.A.' },
  { code: '0171', name: 'BANCO ACTIVO' },
  { code: '0172', name: 'BANCAMIGA BANCO UNIVERSAL, C.A.' },
  { code: '0173', name: 'BANCO INTERNACIONAL DE DESARROLLO' },
  { code: '0174', name: 'BANPLUS BANCO COMERCIAL' },
  { code: '0175', name: 'BANCO DIGITAL DE LOS TRABAJADORES' },
  { code: '0177', name: 'BANCO DE LAS FUERZAS ARMADAS BANFANB' },
  { code: '0178', name: 'N58 BANCO DIGITAL' },
  { code: '0191', name: 'BANCO NACIONAL DE CREDITO' },
  { code: '0601', name: 'I.M.C.P' },
  { code: '0732', name: 'FONDEN' },
  { code: '2017', name: 'ONT' },
  { code: '6000', name: 'BANAVIH' },
];

export default function Send() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  const [step, setStep] = useState(1);
  const idemRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);
  
  // Step 1: Amount
  const [amount, setAmount] = useState('');
  const [vesInput, setVesInput] = useState('');
  const [lastEdited, setLastEdited] = useState('ris'); // 'ris' or 'ves'

  // Sync VES display when RIS changes (only if last edit was RIS)
  useEffect(() => {
    if (lastEdited === 'ris') {
      setVesInput(amount ? (parseFloat(amount) * (rates.ris_to_ves || 0)).toFixed(2) : '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [amount, rates.ris_to_ves]);
  
  // Step 2: Payment Type
  const [paymentType, setPaymentType] = useState(''); // 'pago_movil' or 'transferencia'
  
  // Step 3: Beneficiary
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [bankSearch, setBankSearch] = useState('');
  const [showBankDropdown, setShowBankDropdown] = useState(false);
  
  // New Beneficiary Form - Pago Móvil
  const [newBeneficiaryPM, setNewBeneficiaryPM] = useState({
    full_name: '',
    cedula: '',
    bank_code: '',
    bank: '',
    phone: '',
  });
  
  // New Beneficiary Form - Transferencia
  const [newBeneficiaryTR, setNewBeneficiaryTR] = useState({
    full_name: '',
    cedula: '',
    bank_code: '',
    bank: '',
    account_number: '',
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

  // Filter banks based on search (by code or name)
  const filteredBanks = VENEZUELAN_BANKS.filter(bank => 
    bank.code.includes(bankSearch) || 
    bank.name.toLowerCase().includes(bankSearch.toLowerCase())
  );

  // Filter beneficiaries by payment type
  const filteredBeneficiaries = beneficiaries.filter(b => b.payment_type === paymentType);

  // Validate only numbers
  const onlyNumbers = (value) => value.replace(/[^0-9]/g, '');

  const handleSelectBank = (bank, type) => {
    if (type === 'pago_movil') {
      // Para Pago Móvil solo guardamos el código del banco
      setNewBeneficiaryPM({ ...newBeneficiaryPM, bank_code: bank.code, bank: bank.code });
    } else {
      // Para Transferencia guardamos código y nombre
      setNewBeneficiaryTR({ ...newBeneficiaryTR, bank_code: bank.code, bank: bank.name });
    }
    setBankSearch('');
    setShowBankDropdown(false);
  };

  const handleSaveBeneficiary = async () => {
    let beneficiaryData;
    
    if (paymentType === 'pago_movil') {
      const { full_name, cedula, bank, bank_code, phone } = newBeneficiaryPM;
      if (!full_name || !cedula || !bank || !phone) {
        toast.error('Completa todos los campos');
        return;
      }
      if (!/^\d+$/.test(cedula)) {
        toast.error('La cédula debe contener solo números');
        return;
      }
      if (!/^\d{11}$/.test(phone)) {
        toast.error('El teléfono debe tener 11 dígitos (ej: 04141234567)');
        return;
      }
      beneficiaryData = {
        full_name,
        id_document: cedula,
        bank,
        bank_code,
        phone_number: phone,
        payment_type: 'pago_movil',
      };
    } else {
      const { full_name, cedula, bank, bank_code, account_number } = newBeneficiaryTR;
      if (!full_name || !cedula || !bank || !account_number) {
        toast.error('Completa todos los campos');
        return;
      }
      if (!/^\d+$/.test(cedula)) {
        toast.error('La cédula debe contener solo números');
        return;
      }
      if (!/^\d{20}$/.test(account_number)) {
        toast.error('El número de cuenta debe tener exactamente 20 dígitos');
        return;
      }
      beneficiaryData = {
        full_name,
        id_document: cedula,
        bank,
        bank_code,
        account_number,
        payment_type: 'transferencia',
      };
    }

    setLoading(true);
    try {
      const response = await api.post('/beneficiaries', beneficiaryData);
      toast.success('Beneficiario guardado');
      await loadBeneficiaries();
      setSelectedBeneficiary(response.data);
      setShowNewBeneficiary(false);
      setNewBeneficiaryPM({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '' });
      setNewBeneficiaryTR({ full_name: '', cedula: '', bank_code: '', bank: '', account_number: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al guardar beneficiario');
    } finally {
      setLoading(false);
    }
  };

  const [showPin, setShowPin] = useState(false);
  const pedirConfirmacion = () => {
    if (!isValidAmount || !selectedBeneficiary || !paymentType) {
      toast.error('Verifica los datos de envío');
      return;
    }
    setShowPin(true);
  };
  const handleSend = async () => {
    if (!isValidAmount || !selectedBeneficiary || !paymentType) {
      toast.error('Verifica los datos de envío');
      return;
    }
    if (!idemRef.current) idemRef.current = (window.crypto?.randomUUID?.() || (Date.now() + '-' + Math.random().toString(16).slice(2)));
    setLoading(true);
    try {
      await api.post('/withdraw', { 
        amount: parseFloat(amount), 
        beneficiary_id: selectedBeneficiary.beneficiary_id,
        idempotency_key: idemRef.current
      });
      idemRef.current = null;
      toast.success('¡Envío registrado! Será procesado pronto.');
      await refreshUser();
      try {
        const h = await api.post('/pin/hint-check');
        if (h.data?.hint) toast(h.data.message || 'Configura tu PIN para mayor seguridad en tu perfil.', { icon: '🔒' });
      } catch (_) { /* aviso opcional */ }
      navigate('/history');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar envío');
    } finally {
      setLoading(false);
    }
  };

  // Styles
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
    border: '1px solid #d1d5db', fontSize: '16px', outline: 'none',
    boxSizing: 'border-box'
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

  const paymentTypeCardStyle = (isSelected) => ({
    padding: '24px',
    borderRadius: '16px',
    border: isSelected ? '2px solid #6366f1' : '2px solid #e5e7eb',
    backgroundColor: isSelected ? '#eff6ff' : '#ffffff',
    cursor: 'pointer',
    transition: 'all 0.2s',
    textAlign: 'center'
  });

  // Render Bank Search Input inline
  const renderBankSearch = (type) => {
    // Para Pago Móvil solo mostrar código, para Transferencia mostrar código + nombre
    const getDisplayValue = () => {
      if (showBankDropdown) return bankSearch;
      if (type === 'pago_movil') {
        return newBeneficiaryPM.bank_code || '';  // Solo código (ej: 0134)
      } else {
        return newBeneficiaryTR.bank ? `${newBeneficiaryTR.bank_code} - ${newBeneficiaryTR.bank}` : '';
      }
    };
    
    return (
    <div style={{ position: 'relative' }}>
      <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
        {type === 'pago_movil' ? 'Código de Banco *' : 'Banco *'}
      </label>
      <div style={{ position: 'relative' }}>
        <Search style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
        <input
          type="text"
          value={getDisplayValue()}
          onChange={(e) => setBankSearch(e.target.value)}
          onFocus={() => setShowBankDropdown(true)}
          placeholder="Buscar por código o nombre..."
          style={{ ...inputStyle, paddingLeft: '44px' }}
          data-testid="bank-search-input"
        />
      </div>
      {showBankDropdown && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
          backgroundColor: '#ffffff', borderRadius: '12px', marginTop: '4px',
          boxShadow: '0 10px 40px rgba(0,0,0,0.15)', maxHeight: '250px', overflowY: 'auto',
          border: '1px solid #e5e7eb'
        }}>
          {filteredBanks.length === 0 ? (
            <div style={{ padding: '16px', textAlign: 'center', color: '#6b7280' }}>
              No se encontraron bancos
            </div>
          ) : (
            filteredBanks.map(bank => (
              <button
                key={bank.code}
                onClick={() => handleSelectBank(bank, type)}
                style={{
                  width: '100%', padding: '12px 16px', border: 'none', backgroundColor: 'transparent',
                  textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px',
                  borderBottom: '1px solid #f3f4f6'
                }}
                data-testid={`bank-option-${bank.code}`}
              >
                <span style={{ 
                  fontSize: '13px', fontWeight: '600', color: '#6366f1', 
                  backgroundColor: '#eff6ff', padding: '4px 8px', borderRadius: '6px',
                  fontFamily: 'monospace'
                }}>
                  {bank.code}
                </span>
                <span style={{ fontSize: '14px', color: '#374151' }}>{bank.name}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
  };

  return (
    <div style={pageStyle} data-testid="send-page" onClick={() => setShowBankDropdown(false)}>
      <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button 
              onClick={() => step > 1 ? setStep(step - 1) : navigate(-1)} 
              style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.8)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              data-testid="back-button"
            >
              <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Enviar a Venezuela</h1>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>1 RIS = {fmt(rates?.ris_to_ves) || '0.00'} VES</p>
            </div>
          </div>
          <NotificationBell />
        </div>

        {/* Progress Steps - 4 steps now */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '24px' }}>
          {[1, 2, 3, 4].map((s) => (
            <div key={s} style={{ display: 'flex', alignItems: 'center' }}>
              <div style={{
                width: '36px', height: '36px', borderRadius: '50%', fontSize: '14px', fontWeight: '600',
                backgroundColor: step >= s ? '#6366f1' : '#e5e7eb', color: step >= s ? '#ffffff' : '#6b7280',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>{s}</div>
              {s < 4 && <div style={{ width: '32px', height: '4px', marginLeft: '4px', marginRight: '4px', borderRadius: '2px', backgroundColor: step > s ? '#6366f1' : '#e5e7eb' }} />}
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
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Saldo: {fmt((user?.balance_ris || 0))} RIS</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Envías (RIS)</label>
                <FormattedNumberInput
                  decimals={4}
                  value={amount}
                  onChange={(v) => { setLastEdited('ris'); setAmount(v); }}
                  style={{ ...inputStyle, fontSize: '28px', fontWeight: '700' }} placeholder="0,00"
                  data-testid="send-amount"
                />
              </div>

              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '16px' }}>
                <p style={{ fontSize: '14px', color: '#111827', margin: '0 0 4px 0', fontWeight: '600' }}>Beneficiario recibe</p>
                <p style={{ fontSize: '32px', fontWeight: '700', color: '#15803d', margin: 0 }}>
                  {fmt(amountVes)} VES
                  {rates?.bcv_usd_ves && amountVes > 0 && (
                    <span> = $ {fmt(amountVes / rates.bcv_usd_ves, 2)} BCV</span>
                  )}
                </p>
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

        {/* Step 2: Payment Type */}
        {step === 2 && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: '0 0 8px 0' }}>Tipo de pago</h2>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 24px 0' }}>Selecciona cómo deseas pagar</p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
              {/* Pago Móvil Option */}
              <button
                onClick={() => setPaymentType('pago_movil')}
                style={paymentTypeCardStyle(paymentType === 'pago_movil')}
                data-testid="payment-type-pago-movil"
              >
                <div style={{ 
                  width: '64px', height: '64px', borderRadius: '16px', 
                  backgroundColor: paymentType === 'pago_movil' ? '#6366f1' : '#f3f4f6',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  margin: '0 auto 12px'
                }}>
                  <Smartphone style={{ width: '32px', height: '32px', color: paymentType === 'pago_movil' ? '#ffffff' : '#6b7280' }} />
                </div>
                <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>Pago Móvil</h3>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Cédula, Banco y Teléfono</p>
              </button>

              {/* Transferencia Option */}
              <button
                onClick={() => setPaymentType('transferencia')}
                style={paymentTypeCardStyle(paymentType === 'transferencia')}
                data-testid="payment-type-transferencia"
              >
                <div style={{ 
                  width: '64px', height: '64px', borderRadius: '16px', 
                  backgroundColor: paymentType === 'transferencia' ? '#6366f1' : '#f3f4f6',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  margin: '0 auto 12px'
                }}>
                  <Building2 style={{ width: '32px', height: '32px', color: paymentType === 'transferencia' ? '#ffffff' : '#6b7280' }} />
                </div>
                <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>Transferencia</h3>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Número de cuenta (20 dígitos)</p>
              </button>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => setStep(1)} style={buttonSecondaryStyle}>Atrás</button>
              <button onClick={() => { setSelectedBeneficiary(null); setStep(3); }} disabled={!paymentType} style={{ ...buttonPrimaryStyle, opacity: paymentType ? 1 : 0.5 }} data-testid="continue-step2">
                Continuar <ArrowRight style={{ width: '20px', height: '20px' }} />
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Beneficiary */}
        {step === 3 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Beneficiario</h2>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
                  {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}
                </p>
              </div>
              <button onClick={() => setShowNewBeneficiary(true)} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 12px', backgroundColor: '#eff6ff', color: '#2563eb', borderRadius: '10px', border: 'none', cursor: 'pointer', fontSize: '14px', fontWeight: '500' }}>
                <Plus style={{ width: '16px', height: '16px' }} /> Nuevo
              </button>
            </div>

            {filteredBeneficiaries.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '32px' }}>
                <div style={{ width: '80px', height: '80px', borderRadius: '50%', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <User style={{ width: '40px', height: '40px', color: '#d1d5db' }} />
                </div>
                <p style={{ color: '#6b7280', margin: '0 0 16px 0' }}>
                  No tienes beneficiarios de {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}
                </p>
                <button onClick={() => setShowNewBeneficiary(true)} style={{ color: '#6366f1', fontWeight: '500', background: 'none', border: 'none', cursor: 'pointer' }}>
                  Agregar beneficiario
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {filteredBeneficiaries.map((b) => (
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
                        {paymentType === 'pago_movil' ? 
                          <Smartphone style={{ width: '24px', height: '24px', color: '#6b7280' }} /> :
                          <Building2 style={{ width: '24px', height: '24px', color: '#6b7280' }} />
                        }
                      </div>
                      <div style={{ flex: 1 }}>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                        <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>
                          {b.bank} {paymentType === 'pago_movil' ? `• ${b.phone_number}` : `• ****${b.account_number?.slice(-4)}`}
                        </p>
                      </div>
                      {selectedBeneficiary?.beneficiary_id === b.beneficiary_id && <CheckCircle style={{ width: '24px', height: '24px', color: '#6366f1' }} />}
                    </div>
                  </button>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
              <button onClick={() => setStep(2)} style={buttonSecondaryStyle}>Atrás</button>
              <button onClick={() => setStep(4)} disabled={!selectedBeneficiary} style={{ ...buttonPrimaryStyle, opacity: selectedBeneficiary ? 1 : 0.5 }} data-testid="continue-step3">
                Continuar <ArrowRight style={{ width: '20px', height: '20px' }} />
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Confirm */}
        {step === 4 && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: '0 0 24px 0', textAlign: 'center' }}>Confirmar envío</h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
              <div style={{ padding: '20px', backgroundColor: '#f3f4f6', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 4px 0' }}>Envías</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#111827', margin: 0 }}>{fmt(parseFloat(amount))} RIS</p>
              </div>
              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Beneficiario recibe</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#15803d', margin: 0 }}>{fmt(amountVes)} VES</p>
              </div>
              
              {/* Payment Type Badge */}
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '8px 16px', borderRadius: '20px',
                  backgroundColor: paymentType === 'pago_movil' ? '#dbeafe' : '#fef3c7',
                  color: paymentType === 'pago_movil' ? '#2563eb' : '#d97706',
                  fontSize: '14px', fontWeight: '500'
                }}>
                  {paymentType === 'pago_movil' ? <Smartphone style={{ width: '16px', height: '16px' }} /> : <Building2 style={{ width: '16px', height: '16px' }} />}
                  {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}
                </span>
              </div>

              <div style={{ padding: '20px', backgroundColor: '#f8f9fa', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 12px 0' }}>Beneficiario</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {paymentType === 'pago_movil' ? 
                      <Smartphone style={{ width: '24px', height: '24px', color: '#2563eb' }} /> :
                      <Building2 style={{ width: '24px', height: '24px', color: '#2563eb' }} />
                    }
                  </div>
                  <div>
                    <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>{selectedBeneficiary?.full_name}</p>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>
                      {paymentType === 'pago_movil' ? `Banco: ${selectedBeneficiary?.bank}` : selectedBeneficiary?.bank}
                    </p>
                    {paymentType === 'pago_movil' ? (
                      <>
                        <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>CI: {selectedBeneficiary?.id_document}</p>
                        <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>Tel: {selectedBeneficiary?.phone_number}</p>
                      </>
                    ) : (
                      <>
                        <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>CI: {selectedBeneficiary?.id_document}</p>
                        <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>Cuenta: {selectedBeneficiary?.account_number}</p>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => setStep(3)} style={buttonSecondaryStyle}>Atrás</button>
              <button onClick={pedirConfirmacion} disabled={loading} style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a', opacity: loading ? 0.5 : 1 }} data-testid="confirm-send">
                {loading ? 'Procesando...' : 'Confirmar envío'}
              </button>
            </div>
            <PinConfirm open={showPin} onClose={() => setShowPin(false)} onVerified={handleSend} />
          </div>
        )}

        {/* New Beneficiary Modal */}
        {showNewBeneficiary && (
          <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }} onClick={(e) => { if (e.target === e.currentTarget) setShowNewBeneficiary(false); }}>
            <div style={{ backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', width: '100%', maxWidth: '450px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
                <div>
                  <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Nuevo beneficiario</h3>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
                    {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}
                  </p>
                </div>
                <button onClick={() => setShowNewBeneficiary(false)} style={{ width: '36px', height: '36px', borderRadius: '10px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
                </button>
              </div>

              {/* Pago Móvil Form */}
              {paymentType === 'pago_movil' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Nombre completo *</label>
                    <input 
                      type="text" 
                      value={newBeneficiaryPM.full_name} 
                      onChange={(e) => setNewBeneficiaryPM({...newBeneficiaryPM, full_name: e.target.value})} 
                      style={inputStyle} 
                      placeholder="Nombre del beneficiario" 
                      data-testid="pm-fullname"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Cédula * (solo números)</label>
                    <input 
                      type="text" 
                      value={newBeneficiaryPM.cedula} 
                      onChange={(e) => setNewBeneficiaryPM({...newBeneficiaryPM, cedula: onlyNumbers(e.target.value)})} 
                      style={inputStyle} 
                      placeholder="12345678" 
                      inputMode="numeric"
                      data-testid="pm-cedula"
                    />
                  </div>
                  {renderBankSearch('pago_movil')}
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Teléfono * (11 dígitos)</label>
                    <input 
                      type="text" 
                      value={newBeneficiaryPM.phone} 
                      onChange={(e) => setNewBeneficiaryPM({...newBeneficiaryPM, phone: onlyNumbers(e.target.value).slice(0, 11)})} 
                      style={inputStyle} 
                      placeholder="04141234567" 
                      inputMode="numeric"
                      maxLength={11}
                      data-testid="pm-phone"
                    />
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Ejemplo: 04141234567</p>
                  </div>
                  <button onClick={handleSaveBeneficiary} disabled={loading} style={{ ...buttonPrimaryStyle, marginTop: '8px', opacity: loading ? 0.5 : 1 }} data-testid="save-beneficiary-pm">
                    {loading ? 'Guardando...' : 'Guardar beneficiario'}
                  </button>
                </div>
              )}

              {/* Transferencia Form */}
              {paymentType === 'transferencia' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Nombre completo *</label>
                    <input 
                      type="text" 
                      value={newBeneficiaryTR.full_name} 
                      onChange={(e) => setNewBeneficiaryTR({...newBeneficiaryTR, full_name: e.target.value})} 
                      style={inputStyle} 
                      placeholder="Nombre del beneficiario" 
                      data-testid="tr-fullname"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Cédula * (solo números)</label>
                    <input 
                      type="text" 
                      value={newBeneficiaryTR.cedula} 
                      onChange={(e) => setNewBeneficiaryTR({...newBeneficiaryTR, cedula: onlyNumbers(e.target.value)})} 
                      style={inputStyle} 
                      placeholder="12345678" 
                      inputMode="numeric"
                      data-testid="tr-cedula"
                    />
                  </div>
                  {renderBankSearch('transferencia')}
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Número de cuenta * (20 dígitos)</label>
                    <input 
                      type="text" 
                      value={newBeneficiaryTR.account_number} 
                      onChange={(e) => setNewBeneficiaryTR({...newBeneficiaryTR, account_number: onlyNumbers(e.target.value).slice(0, 20)})} 
                      style={inputStyle} 
                      placeholder="01340123456789012345" 
                      inputMode="numeric"
                      maxLength={20}
                      data-testid="tr-account"
                    />
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>20 dígitos sin espacios ni guiones</p>
                  </div>
                  <button onClick={handleSaveBeneficiary} disabled={loading} style={{ ...buttonPrimaryStyle, marginTop: '8px', opacity: loading ? 0.5 : 1 }} data-testid="save-beneficiary-tr">
                    {loading ? 'Guardando...' : 'Guardar beneficiario'}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
