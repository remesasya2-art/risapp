import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Users, TrendingUp, Plus, Search, RefreshCw, 
  Smartphone, Building2, CheckCircle, Clock, XCircle, X, ArrowRight, Wallet, CreditCard
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';

// Lista de bancos venezolanos (misma que en Send.jsx)
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

export default function GestorDashboard() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [transactions, setTransactions] = useState([]);
  
  // Modals
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);
  const [showNewTransaction, setShowNewTransaction] = useState(false);
  const [showRechargeModal, setShowRechargeModal] = useState(false);
  
  // Transaction flow states
  const [txStep, setTxStep] = useState(1);
  const [txAmount, setTxAmount] = useState('');
  const [txPaymentType, setTxPaymentType] = useState('');
  const [txSelectedBeneficiary, setTxSelectedBeneficiary] = useState(null);
  const [txClientName, setTxClientName] = useState('');
  const [txClientPhone, setTxClientPhone] = useState('');
  
  // Beneficiary form states
  const [paymentType, setPaymentType] = useState('pago_movil');
  const [bankSearch, setBankSearch] = useState('');
  const [showBankDropdown, setShowBankDropdown] = useState(false);
  const [newBeneficiaryPM, setNewBeneficiaryPM] = useState({
    full_name: '', cedula: '', bank_code: '', bank: '', phone: ''
  });
  const [newBeneficiaryTR, setNewBeneficiaryTR] = useState({
    full_name: '', cedula: '', bank_code: '', bank: '', account_number: ''
  });

  useEffect(() => {
    if (user?.role === 'socio_gestor') {
      loadData();
    }
  }, [user]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [dashboardRes, beneficiariesRes, transactionsRes] = await Promise.all([
        api.get('/gestor/dashboard'),
        api.get('/gestor/beneficiaries'),
        api.get('/gestor/transactions')
      ]);
      setData(dashboardRes.data);
      setBeneficiaries(beneficiariesRes.data || []);
      setTransactions(transactionsRes.data || []);
    } catch (error) {
      console.error('Error loading gestor data:', error);
      toast.error('Error al cargar datos');
    } finally {
      setLoading(false);
    }
  };

  // Filter banks
  const filteredBanks = VENEZUELAN_BANKS.filter(bank => 
    bank.code.includes(bankSearch) || 
    bank.name.toLowerCase().includes(bankSearch.toLowerCase())
  );

  // Filter beneficiaries by payment type for transaction
  const filteredBeneficiaries = beneficiaries.filter(b => b.payment_type === txPaymentType);

  const onlyNumbers = (value) => value.replace(/[^0-9]/g, '');

  const handleSelectBank = (bank) => {
    if (paymentType === 'pago_movil') {
      setNewBeneficiaryPM({ ...newBeneficiaryPM, bank_code: bank.code, bank: bank.code });
    } else {
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
      if (!/^\d{11}$/.test(phone)) {
        toast.error('El teléfono debe tener 11 dígitos');
        return;
      }
      beneficiaryData = {
        full_name, id_document: cedula, bank, bank_code, phone_number: phone, payment_type: 'pago_movil'
      };
    } else {
      const { full_name, cedula, bank, bank_code, account_number } = newBeneficiaryTR;
      if (!full_name || !cedula || !bank || !account_number) {
        toast.error('Completa todos los campos');
        return;
      }
      if (!/^\d{20}$/.test(account_number)) {
        toast.error('El número de cuenta debe tener 20 dígitos');
        return;
      }
      beneficiaryData = {
        full_name, id_document: cedula, bank, bank_code, account_number, payment_type: 'transferencia'
      };
    }

    setLoading(true);
    try {
      await api.post('/gestor/beneficiaries', beneficiaryData);
      toast.success('Beneficiario guardado');
      await loadData();
      setShowNewBeneficiary(false);
      setNewBeneficiaryPM({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '' });
      setNewBeneficiaryTR({ full_name: '', cedula: '', bank_code: '', bank: '', account_number: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al guardar');
    } finally {
      setLoading(false);
    }
  };

  const handleProcessTransaction = async () => {
    if (!txAmount || !txSelectedBeneficiary || !txClientName) {
      toast.error('Completa todos los datos');
      return;
    }
    
    setLoading(true);
    try {
      await api.post('/gestor/process-transaction', {
        amount_ris: parseFloat(txAmount),
        beneficiary_id: txSelectedBeneficiary.beneficiary_id,
        client_name: txClientName,
        client_phone: txClientPhone,
        payment_type: txPaymentType
      });
      toast.success('¡Transacción registrada!');
      await loadData();
      await refreshUser();
      resetTransactionFlow();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar');
    } finally {
      setLoading(false);
    }
  };

  const resetTransactionFlow = () => {
    setShowNewTransaction(false);
    setTxStep(1);
    setTxAmount('');
    setTxPaymentType('');
    setTxSelectedBeneficiary(null);
    setTxClientName('');
    setTxClientPhone('');
  };

  const amountVes = txAmount ? parseFloat(txAmount) * rates.ris_to_ves : 0;
  const balanceTerceros = data?.balance_ris_terceros ?? user?.balance_ris_terceros ?? 0;
  const isValidAmount = txAmount && parseFloat(txAmount) > 0 && parseFloat(txAmount) <= balanceTerceros;

  const getStatusBadge = (status) => {
    const styles = {
      pending: { bg: '#fef3c7', color: '#d97706', icon: Clock },
      completed: { bg: '#dcfce7', color: '#16a34a', icon: CheckCircle },
      rejected: { bg: '#fee2e2', color: '#dc2626', icon: XCircle },
    };
    const s = styles[status] || styles.pending;
    const Icon = s.icon;
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 10px', borderRadius: '20px', backgroundColor: s.bg, color: s.color, fontSize: '12px', fontWeight: '500' }}>
        <Icon style={{ width: '14px', height: '14px' }} />
        {status === 'pending' ? 'Pendiente' : status === 'completed' ? 'Completado' : 'Rechazado'}
      </span>
    );
  };

  // Styles
  const pageStyle = { minHeight: '100vh', background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)', fontFamily: 'Inter, sans-serif' };
  const cardStyle = { backgroundColor: '#ffffff', borderRadius: '20px', boxShadow: '0 10px 40px rgba(0,0,0,0.1)', padding: '24px' };
  const inputStyle = { width: '100%', padding: '14px 16px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', boxSizing: 'border-box' };
  const btnPrimary = { backgroundColor: '#2563eb', color: 'white', borderRadius: '12px', padding: '14px 24px', fontWeight: '600', fontSize: '15px', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', width: '100%' };
  const btnSecondary = { backgroundColor: '#f3f4f6', color: '#374151', borderRadius: '12px', padding: '14px 24px', fontWeight: '600', fontSize: '15px', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', width: '100%' };
  const btnOutline = { backgroundColor: 'transparent', color: '#2563eb', borderRadius: '12px', padding: '14px 24px', fontWeight: '600', fontSize: '15px', border: '2px solid #2563eb', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', width: '100%' };

  if (!user || user.role !== 'socio_gestor') {
    return (
      <div style={pageStyle}>
        <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto', textAlign: 'center', paddingTop: '100px' }}>
          <div style={cardStyle}>
            <h2 style={{ color: '#111827', marginBottom: '16px' }}>Acceso Restringido</h2>
            <p style={{ color: '#6b7280', marginBottom: '24px' }}>Solo usuarios con rol de Socio Gestor pueden acceder a esta sección.</p>
            <button onClick={() => navigate('/')} style={btnPrimary}>Volver al inicio</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={pageStyle} onClick={() => setShowBankDropdown(false)}>
      <div style={{ padding: '24px', maxWidth: '800px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button onClick={() => navigate('/')} style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.2)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <ArrowLeft style={{ width: '20px', height: '20px', color: '#ffffff' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#ffffff', margin: 0 }}>Panel Gestor</h1>
              <p style={{ fontSize: '14px', color: 'rgba(255,255,255,0.7)', margin: 0 }}>Código: {user?.gestor_code}</p>
            </div>
          </div>
          <NotificationBell />
        </div>

        {loading ? (
          <div style={{ ...cardStyle, textAlign: 'center', padding: '60px' }}>
            <RefreshCw style={{ width: '40px', height: '40px', color: '#2563eb', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : (
          <>
            {/* Balance Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px', marginBottom: '24px' }}>
              {/* Saldo Personal */}
              <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                  <Wallet style={{ width: '24px', height: '24px', color: 'rgba(255,255,255,0.8)' }} />
                  <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: '14px' }}>Mi Saldo Personal</span>
                </div>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                  RI$ {(user?.balance_ris || 0).toFixed(2)}
                </p>
              </div>
              
              {/* Saldo Terceros */}
              <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                  <CreditCard style={{ width: '24px', height: '24px', color: 'rgba(255,255,255,0.8)' }} />
                  <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: '14px' }}>Saldo Terceros</span>
                </div>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                  RI$ {balanceTerceros.toFixed(2)}
                </p>
                <button 
                  onClick={() => setShowRechargeModal(true)} 
                  style={{ marginTop: '12px', padding: '8px 16px', backgroundColor: 'rgba(255,255,255,0.2)', color: '#ffffff', border: 'none', borderRadius: '8px', fontSize: '13px', cursor: 'pointer' }}
                >
                  + Recargar
                </button>
              </div>
            </div>

            {/* Stats */}
            <div style={{ ...cardStyle, marginBottom: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                <div style={{ textAlign: 'center' }}>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>{data?.stats?.total_transactions || 0}</p>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Transacciones</p>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#16a34a', margin: 0 }}>RI$ {(data?.stats?.total_volume || 0).toFixed(0)}</p>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Volumen</p>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#2563eb', margin: 0 }}>{data?.commission_rate || 5}%</p>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Comisión</p>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '24px' }}>
              <button onClick={() => setShowNewTransaction(true)} style={btnPrimary} disabled={balanceTerceros <= 0}>
                <TrendingUp style={{ width: '20px', height: '20px' }} /> Nueva Transacción
              </button>
              <button onClick={() => setShowNewBeneficiary(true)} style={btnOutline}>
                <Plus style={{ width: '20px', height: '20px' }} /> Agregar Beneficiario
              </button>
            </div>

            {/* Beneficiaries */}
            <div style={{ ...cardStyle, marginBottom: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
                Beneficiarios ({beneficiaries.length})
              </h3>
              {beneficiaries.length === 0 ? (
                <p style={{ color: '#6b7280', textAlign: 'center', padding: '24px' }}>No hay beneficiarios registrados</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {beneficiaries.slice(0, 5).map((b) => (
                    <div key={b.beneficiary_id} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '12px' }}>
                      <div style={{ width: '40px', height: '40px', borderRadius: '10px', backgroundColor: b.payment_type === 'pago_movil' ? '#dbeafe' : '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {b.payment_type === 'pago_movil' ? <Smartphone style={{ width: '20px', height: '20px', color: '#2563eb' }} /> : <Building2 style={{ width: '20px', height: '20px', color: '#d97706' }} />}
                      </div>
                      <div style={{ flex: 1 }}>
                        <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: 0 }}>
                          {b.payment_type === 'pago_movil' ? `${b.bank} • ${b.phone_number}` : `${b.bank} • ****${b.account_number?.slice(-4)}`}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recent Transactions */}
            <div style={cardStyle}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
                Transacciones Recientes
              </h3>
              {transactions.length === 0 ? (
                <p style={{ color: '#6b7280', textAlign: 'center', padding: '24px' }}>No hay transacciones</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {transactions.slice(0, 5).map((tx) => (
                    <div key={tx.transaction_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '12px' }}>
                      <div>
                        <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{tx.client_name}</p>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: 0 }}>{tx.beneficiary_name}</p>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{tx.amount_output?.toFixed(2)} VES</p>
                        {getStatusBadge(tx.status)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* New Transaction Modal - 4 Steps */}
      {showNewTransaction && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}>
          <div style={{ ...cardStyle, width: '100%', maxWidth: '500px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Nueva Transacción</h3>
              <button onClick={resetTransactionFlow} style={{ width: '36px', height: '36px', borderRadius: '10px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {/* Progress */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '24px' }}>
              {[1, 2, 3, 4].map((s) => (
                <div key={s} style={{ display: 'flex', alignItems: 'center' }}>
                  <div style={{ width: '32px', height: '32px', borderRadius: '50%', fontSize: '13px', fontWeight: '600', backgroundColor: txStep >= s ? '#2563eb' : '#e5e7eb', color: txStep >= s ? '#fff' : '#6b7280', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{s}</div>
                  {s < 4 && <div style={{ width: '24px', height: '3px', marginLeft: '4px', marginRight: '4px', borderRadius: '2px', backgroundColor: txStep > s ? '#2563eb' : '#e5e7eb' }} />}
                </div>
              ))}
            </div>

            {/* Step 1: Amount */}
            {txStep === 1 && (
              <div>
                <p style={{ fontSize: '14px', color: '#6b7280', marginBottom: '16px' }}>Saldo disponible: RI$ {balanceTerceros.toFixed(2)}</p>
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Monto a enviar (RIS)</label>
                  <input type="number" value={txAmount} onChange={(e) => setTxAmount(e.target.value)} style={{ ...inputStyle, fontSize: '24px', fontWeight: '700' }} placeholder="0.00" />
                </div>
                {txAmount && (
                  <div style={{ padding: '16px', backgroundColor: '#dcfce7', borderRadius: '12px', marginBottom: '16px' }}>
                    <p style={{ fontSize: '13px', color: '#16a34a', margin: 0 }}>Beneficiario recibe</p>
                    <p style={{ fontSize: '24px', fontWeight: '700', color: '#15803d', margin: 0 }}>{amountVes.toFixed(2)} VES</p>
                  </div>
                )}
                <button onClick={() => setTxStep(2)} disabled={!isValidAmount} style={{ ...btnPrimary, opacity: isValidAmount ? 1 : 0.5 }}>
                  Continuar <ArrowRight style={{ width: '18px', height: '18px' }} />
                </button>
              </div>
            )}

            {/* Step 2: Payment Type */}
            {txStep === 2 && (
              <div>
                <p style={{ fontSize: '14px', color: '#6b7280', marginBottom: '16px' }}>Selecciona el tipo de pago</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px' }}>
                  <button onClick={() => setTxPaymentType('pago_movil')} style={{ padding: '20px', borderRadius: '14px', border: txPaymentType === 'pago_movil' ? '2px solid #2563eb' : '2px solid #e5e7eb', backgroundColor: txPaymentType === 'pago_movil' ? '#eff6ff' : '#fff', textAlign: 'center', cursor: 'pointer' }}>
                    <Smartphone style={{ width: '32px', height: '32px', color: txPaymentType === 'pago_movil' ? '#2563eb' : '#6b7280', margin: '0 auto 8px' }} />
                    <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>Pago Móvil</p>
                  </button>
                  <button onClick={() => setTxPaymentType('transferencia')} style={{ padding: '20px', borderRadius: '14px', border: txPaymentType === 'transferencia' ? '2px solid #2563eb' : '2px solid #e5e7eb', backgroundColor: txPaymentType === 'transferencia' ? '#eff6ff' : '#fff', textAlign: 'center', cursor: 'pointer' }}>
                    <Building2 style={{ width: '32px', height: '32px', color: txPaymentType === 'transferencia' ? '#2563eb' : '#6b7280', margin: '0 auto 8px' }} />
                    <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>Transferencia</p>
                  </button>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button onClick={() => setTxStep(1)} style={btnSecondary}>Atrás</button>
                  <button onClick={() => setTxStep(3)} disabled={!txPaymentType} style={{ ...btnPrimary, opacity: txPaymentType ? 1 : 0.5 }}>
                    Continuar <ArrowRight style={{ width: '18px', height: '18px' }} />
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Beneficiary + Client Info */}
            {txStep === 3 && (
              <div>
                <p style={{ fontSize: '14px', color: '#6b7280', marginBottom: '16px' }}>Datos del cliente y beneficiario</p>
                
                {/* Client Info */}
                <div style={{ marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Nombre del cliente *</label>
                  <input type="text" value={txClientName} onChange={(e) => setTxClientName(e.target.value)} style={inputStyle} placeholder="Nombre de quien paga" />
                </div>
                <div style={{ marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Teléfono del cliente</label>
                  <input type="text" value={txClientPhone} onChange={(e) => setTxClientPhone(onlyNumbers(e.target.value))} style={inputStyle} placeholder="04141234567" />
                </div>

                {/* Beneficiary Selection */}
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Beneficiario ({txPaymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'})</label>
                {filteredBeneficiaries.length === 0 ? (
                  <div style={{ padding: '20px', backgroundColor: '#f9fafb', borderRadius: '12px', textAlign: 'center', marginBottom: '20px' }}>
                    <p style={{ color: '#6b7280', margin: '0 0 12px 0' }}>No hay beneficiarios de este tipo</p>
                    <button onClick={() => { setPaymentType(txPaymentType); setShowNewBeneficiary(true); }} style={{ color: '#2563eb', fontWeight: '500', background: 'none', border: 'none', cursor: 'pointer' }}>
                      + Agregar beneficiario
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '20px', maxHeight: '200px', overflowY: 'auto' }}>
                    {filteredBeneficiaries.map((b) => (
                      <button key={b.beneficiary_id} onClick={() => setTxSelectedBeneficiary(b)} style={{ width: '100%', padding: '12px', borderRadius: '12px', border: txSelectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '2px solid #2563eb' : '1px solid #e5e7eb', backgroundColor: txSelectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '#eff6ff' : '#fff', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ flex: 1 }}>
                          <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                          <p style={{ fontSize: '12px', color: '#6b7280', margin: 0 }}>{b.bank}</p>
                        </div>
                        {txSelectedBeneficiary?.beneficiary_id === b.beneficiary_id && <CheckCircle style={{ width: '20px', height: '20px', color: '#2563eb' }} />}
                      </button>
                    ))}
                  </div>
                )}

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button onClick={() => setTxStep(2)} style={btnSecondary}>Atrás</button>
                  <button onClick={() => setTxStep(4)} disabled={!txClientName || !txSelectedBeneficiary} style={{ ...btnPrimary, opacity: txClientName && txSelectedBeneficiary ? 1 : 0.5 }}>
                    Continuar <ArrowRight style={{ width: '18px', height: '18px' }} />
                  </button>
                </div>
              </div>
            )}

            {/* Step 4: Confirm */}
            {txStep === 4 && (
              <div>
                <div style={{ padding: '16px', backgroundColor: '#f9fafb', borderRadius: '12px', marginBottom: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <span style={{ color: '#6b7280' }}>Cliente:</span>
                    <span style={{ fontWeight: '600', color: '#111827' }}>{txClientName}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <span style={{ color: '#6b7280' }}>Beneficiario:</span>
                    <span style={{ fontWeight: '600', color: '#111827' }}>{txSelectedBeneficiary?.full_name}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <span style={{ color: '#6b7280' }}>Tipo:</span>
                    <span style={{ fontWeight: '500', color: '#2563eb' }}>{txPaymentType === 'pago_movil' ? '📱 Pago Móvil' : '🏦 Transferencia'}</span>
                  </div>
                  <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: '12px', marginTop: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ color: '#6b7280' }}>Envía:</span>
                      <span style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>{parseFloat(txAmount).toFixed(2)} RIS</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#6b7280' }}>Recibe:</span>
                      <span style={{ fontSize: '18px', fontWeight: '700', color: '#16a34a' }}>{amountVes.toFixed(2)} VES</span>
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button onClick={() => setTxStep(3)} style={btnSecondary}>Atrás</button>
                  <button onClick={handleProcessTransaction} disabled={loading} style={{ ...btnPrimary, backgroundColor: '#16a34a', opacity: loading ? 0.5 : 1 }}>
                    {loading ? 'Procesando...' : 'Confirmar'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* New Beneficiary Modal */}
      {showNewBeneficiary && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }} onClick={(e) => e.target === e.currentTarget && setShowNewBeneficiary(false)}>
          <div style={{ ...cardStyle, width: '100%', maxWidth: '450px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Nuevo Beneficiario</h3>
              <button onClick={() => setShowNewBeneficiary(false)} style={{ width: '36px', height: '36px', borderRadius: '10px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {/* Payment Type Selector */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
              <button onClick={() => setPaymentType('pago_movil')} style={{ flex: 1, padding: '12px', borderRadius: '10px', border: paymentType === 'pago_movil' ? '2px solid #2563eb' : '1px solid #e5e7eb', backgroundColor: paymentType === 'pago_movil' ? '#eff6ff' : '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                <Smartphone style={{ width: '18px', height: '18px', color: paymentType === 'pago_movil' ? '#2563eb' : '#6b7280' }} />
                <span style={{ fontWeight: '500', color: paymentType === 'pago_movil' ? '#2563eb' : '#6b7280' }}>Pago Móvil</span>
              </button>
              <button onClick={() => setPaymentType('transferencia')} style={{ flex: 1, padding: '12px', borderRadius: '10px', border: paymentType === 'transferencia' ? '2px solid #2563eb' : '1px solid #e5e7eb', backgroundColor: paymentType === 'transferencia' ? '#eff6ff' : '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                <Building2 style={{ width: '18px', height: '18px', color: paymentType === 'transferencia' ? '#2563eb' : '#6b7280' }} />
                <span style={{ fontWeight: '500', color: paymentType === 'transferencia' ? '#2563eb' : '#6b7280' }}>Transferencia</span>
              </button>
            </div>

            {/* Pago Móvil Form */}
            {paymentType === 'pago_movil' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Nombre completo *</label>
                  <input type="text" value={newBeneficiaryPM.full_name} onChange={(e) => setNewBeneficiaryPM({...newBeneficiaryPM, full_name: e.target.value})} style={inputStyle} placeholder="Nombre del beneficiario" />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Cédula * (solo números)</label>
                  <input type="text" value={newBeneficiaryPM.cedula} onChange={(e) => setNewBeneficiaryPM({...newBeneficiaryPM, cedula: onlyNumbers(e.target.value)})} style={inputStyle} placeholder="12345678" />
                </div>
                <div style={{ position: 'relative' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Código de Banco *</label>
                  <div style={{ position: 'relative' }}>
                    <Search style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                    <input type="text" value={showBankDropdown ? bankSearch : newBeneficiaryPM.bank_code || ''} onChange={(e) => setBankSearch(e.target.value)} onFocus={() => setShowBankDropdown(true)} style={{ ...inputStyle, paddingLeft: '44px' }} placeholder="Buscar banco..." />
                  </div>
                  {showBankDropdown && (
                    <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50, backgroundColor: '#fff', borderRadius: '12px', marginTop: '4px', boxShadow: '0 10px 40px rgba(0,0,0,0.15)', maxHeight: '200px', overflowY: 'auto', border: '1px solid #e5e7eb' }}>
                      {filteredBanks.map(bank => (
                        <button key={bank.code} onClick={() => handleSelectBank(bank)} style={{ width: '100%', padding: '10px 14px', border: 'none', backgroundColor: 'transparent', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '10px', borderBottom: '1px solid #f3f4f6' }}>
                          <span style={{ fontSize: '13px', fontWeight: '600', color: '#2563eb', backgroundColor: '#eff6ff', padding: '2px 6px', borderRadius: '4px' }}>{bank.code}</span>
                          <span style={{ fontSize: '13px', color: '#374151' }}>{bank.name}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Teléfono * (11 dígitos)</label>
                  <input type="text" value={newBeneficiaryPM.phone} onChange={(e) => setNewBeneficiaryPM({...newBeneficiaryPM, phone: onlyNumbers(e.target.value).slice(0, 11)})} style={inputStyle} placeholder="04141234567" maxLength={11} />
                </div>
                <button onClick={handleSaveBeneficiary} disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.5 : 1 }}>
                  {loading ? 'Guardando...' : 'Guardar Beneficiario'}
                </button>
              </div>
            )}

            {/* Transferencia Form */}
            {paymentType === 'transferencia' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Nombre completo *</label>
                  <input type="text" value={newBeneficiaryTR.full_name} onChange={(e) => setNewBeneficiaryTR({...newBeneficiaryTR, full_name: e.target.value})} style={inputStyle} placeholder="Nombre del beneficiario" />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Cédula * (solo números)</label>
                  <input type="text" value={newBeneficiaryTR.cedula} onChange={(e) => setNewBeneficiaryTR({...newBeneficiaryTR, cedula: onlyNumbers(e.target.value)})} style={inputStyle} placeholder="12345678" />
                </div>
                <div style={{ position: 'relative' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Banco *</label>
                  <div style={{ position: 'relative' }}>
                    <Search style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                    <input type="text" value={showBankDropdown ? bankSearch : (newBeneficiaryTR.bank ? `${newBeneficiaryTR.bank_code} - ${newBeneficiaryTR.bank}` : '')} onChange={(e) => setBankSearch(e.target.value)} onFocus={() => setShowBankDropdown(true)} style={{ ...inputStyle, paddingLeft: '44px' }} placeholder="Buscar banco..." />
                  </div>
                  {showBankDropdown && (
                    <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50, backgroundColor: '#fff', borderRadius: '12px', marginTop: '4px', boxShadow: '0 10px 40px rgba(0,0,0,0.15)', maxHeight: '200px', overflowY: 'auto', border: '1px solid #e5e7eb' }}>
                      {filteredBanks.map(bank => (
                        <button key={bank.code} onClick={() => handleSelectBank(bank)} style={{ width: '100%', padding: '10px 14px', border: 'none', backgroundColor: 'transparent', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '10px', borderBottom: '1px solid #f3f4f6' }}>
                          <span style={{ fontSize: '13px', fontWeight: '600', color: '#2563eb', backgroundColor: '#eff6ff', padding: '2px 6px', borderRadius: '4px' }}>{bank.code}</span>
                          <span style={{ fontSize: '13px', color: '#374151' }}>{bank.name}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Número de cuenta * (20 dígitos)</label>
                  <input type="text" value={newBeneficiaryTR.account_number} onChange={(e) => setNewBeneficiaryTR({...newBeneficiaryTR, account_number: onlyNumbers(e.target.value).slice(0, 20)})} style={inputStyle} placeholder="01340123456789012345" maxLength={20} />
                </div>
                <button onClick={handleSaveBeneficiary} disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.5 : 1 }}>
                  {loading ? 'Guardando...' : 'Guardar Beneficiario'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Recharge Modal - Transfer from personal to terceros */}
      {showRechargeModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}>
          <div style={{ ...cardStyle, width: '100%', maxWidth: '400px' }}>
            <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: '0 0 16px 0' }}>Recargar Saldo Terceros</h3>
            <p style={{ color: '#6b7280', marginBottom: '16px' }}>Transfiere de tu saldo personal al saldo para terceros.</p>
            <p style={{ fontSize: '14px', color: '#6b7280', marginBottom: '20px' }}>
              Saldo personal disponible: <strong>RI$ {(user?.balance_ris || 0).toFixed(2)}</strong>
            </p>
            <RechargeForm 
              maxAmount={user?.balance_ris || 0}
              onSuccess={() => { setShowRechargeModal(false); loadData(); refreshUser(); }}
              onCancel={() => setShowRechargeModal(false)}
            />
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// Recharge Form Component
function RechargeForm({ maxAmount, onSuccess, onCancel }) {
  const [amount, setAmount] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRecharge = async () => {
    if (!amount || parseFloat(amount) <= 0 || parseFloat(amount) > maxAmount) {
      toast.error('Monto inválido');
      return;
    }
    setLoading(true);
    try {
      await api.post('/gestor/recharge-terceros', { amount: parseFloat(amount) });
      toast.success('Saldo transferido exitosamente');
      onSuccess();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al transferir');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="number"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="Monto a transferir"
        style={{ width: '100%', padding: '14px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '18px', marginBottom: '16px', boxSizing: 'border-box' }}
      />
      <div style={{ display: 'flex', gap: '12px' }}>
        <button onClick={onCancel} style={{ flex: 1, padding: '14px', borderRadius: '12px', border: 'none', backgroundColor: '#f3f4f6', color: '#374151', fontWeight: '600', cursor: 'pointer' }}>
          Cancelar
        </button>
        <button onClick={handleRecharge} disabled={loading || !amount || parseFloat(amount) > maxAmount} style={{ flex: 1, padding: '14px', borderRadius: '12px', border: 'none', backgroundColor: '#2563eb', color: '#fff', fontWeight: '600', cursor: 'pointer', opacity: loading || !amount || parseFloat(amount) > maxAmount ? 0.5 : 1 }}>
          {loading ? 'Procesando...' : 'Transferir'}
        </button>
      </div>
    </div>
  );
}
