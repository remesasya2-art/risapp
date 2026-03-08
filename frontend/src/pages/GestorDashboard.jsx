import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Calculator, QrCode, Copy, Clock, CheckCircle, XCircle, 
  Phone, Building2, ChevronRight, Loader2, Plus, RefreshCw,
  Wallet, CreditCard, Search, TrendingUp, X, AlertCircle, User
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';

// Venezuelan Banks
const VENEZUELAN_BANKS = [
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
  { code: '0146', name: 'BANGENTE' },
  { code: '0151', name: 'FONDO COMUN' },
  { code: '0156', name: '100% BANCO' },
  { code: '0157', name: 'DELSUR' },
  { code: '0163', name: 'BANCO DEL TESORO' },
  { code: '0166', name: 'BANCO AGRICOLA' },
  { code: '0168', name: 'BANCRECER' },
  { code: '0171', name: 'BANCO ACTIVO' },
  { code: '0172', name: 'BANCAMIGA' },
  { code: '0174', name: 'BANPLUS' },
  { code: '0175', name: 'BICENTENARIO' },
  { code: '0177', name: 'BANFANB' },
  { code: '0178', name: 'N58 BANCO DIGITAL' },
  { code: '0191', name: 'BNC' },
];

// Flow Steps
const FLOW_STEPS = {
  CALCULATOR: 'calculator',
  PIX_QR: 'pix_qr',
  PAYMENT_SUCCESS: 'payment_success',
  PAYMENT_TYPE: 'payment_type',
  BENEFICIARY: 'beneficiary',
  CONFIRM: 'confirm',
  DASHBOARD: 'dashboard'
};

export default function GestorDashboard() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  
  // Flow state
  const [currentStep, setCurrentStep] = useState(FLOW_STEPS.DASHBOARD);
  const [loading, setLoading] = useState(true);
  
  // Dashboard data
  const [dashboardData, setDashboardData] = useState(null);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [transactions, setTransactions] = useState([]);
  
  // Calculator state
  const [inputMode, setInputMode] = useState('ris'); // 'ris' or 'ves'
  const [inputAmount, setInputAmount] = useState('');
  
  // PIX state
  const [pixPayment, setPixPayment] = useState(null);
  const [pixTimer, setPixTimer] = useState(420); // 7 minutes in seconds
  const [pixStatus, setPixStatus] = useState('pending');
  
  // Transaction form state
  const [paymentType, setPaymentType] = useState('');
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);
  
  // New beneficiary form
  const [newBeneficiaryType, setNewBeneficiaryType] = useState('pago_movil');
  const [bankSearch, setBankSearch] = useState('');
  const [showBankDropdown, setShowBankDropdown] = useState(false);
  const [newBeneficiaryData, setNewBeneficiaryData] = useState({
    full_name: '', cedula: '', bank_code: '', bank: '', phone: '', account_number: ''
  });

  // Load dashboard data
  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [dashboardRes, beneficiariesRes, transactionsRes] = await Promise.all([
        api.get('/gestor/dashboard'),
        api.get('/gestor/beneficiaries'),
        api.get('/gestor/transactions')
      ]);
      setDashboardData(dashboardRes.data);
      setBeneficiaries(beneficiariesRes.data || []);
      setTransactions(transactionsRes.data || []);
    } catch (error) {
      console.error('Error loading gestor data:', error);
      toast.error('Error al cargar datos');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.role === 'socio_gestor') {
      loadDashboard();
    }
  }, [user, loadDashboard]);

  // PIX Timer effect
  useEffect(() => {
    let interval;
    if (currentStep === FLOW_STEPS.PIX_QR && pixStatus === 'pending' && pixTimer > 0) {
      interval = setInterval(() => {
        setPixTimer(prev => {
          if (prev <= 1) {
            setPixStatus('expired');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [currentStep, pixStatus, pixTimer]);

  // PIX Status polling
  useEffect(() => {
    let pollInterval;
    if (currentStep === FLOW_STEPS.PIX_QR && pixStatus === 'pending' && pixPayment) {
      pollInterval = setInterval(async () => {
        try {
          const res = await api.get(`/gestor/pix/status/${pixPayment.payment_id}`);
          if (res.data.status === 'paid') {
            setPixStatus('paid');
            toast.success('¡Pago PIX recibido!');
            await refreshUser();
            await loadDashboard();
            setTimeout(() => setCurrentStep(FLOW_STEPS.PAYMENT_SUCCESS), 500);
          } else if (res.data.status === 'expired') {
            setPixStatus('expired');
          }
        } catch (error) {
          console.error('Error polling PIX status:', error);
        }
      }, 3000);
    }
    return () => clearInterval(pollInterval);
  }, [currentStep, pixStatus, pixPayment, refreshUser, loadDashboard]);

  // Calculate amounts
  const risToVes = rates?.ris_to_ves || 92;
  const calculatedAmount = inputAmount ? parseFloat(inputAmount) : 0;
  const amountRis = inputMode === 'ris' ? calculatedAmount : calculatedAmount / risToVes;
  const amountVes = inputMode === 'ves' ? calculatedAmount : calculatedAmount * risToVes;
  const balanceTerceros = dashboardData?.balance_ris_terceros ?? user?.balance_ris_terceros ?? 0;

  // Format timer
  const formatTimer = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Handle keyboard input
  const handleKeyPress = (key) => {
    if (key === '⌫') {
      setInputAmount(prev => prev.slice(0, -1));
    } else if (key === '.' && inputAmount.includes('.')) {
      return;
    } else {
      setInputAmount(prev => prev + key);
    }
  };

  // Start new transaction flow
  const startNewTransaction = () => {
    setInputAmount('');
    setInputMode('ris');
    setPaymentType('');
    setSelectedBeneficiary(null);
    setPixPayment(null);
    setPixTimer(420);
    setPixStatus('pending');
    setCurrentStep(FLOW_STEPS.CALCULATOR);
  };

  // Create PIX payment
  const createPixPayment = async () => {
    if (amountRis <= 0) {
      toast.error('Ingresa un monto válido');
      return;
    }
    
    setLoading(true);
    try {
      const res = await api.post('/gestor/pix/create', {
        amount_ris: amountRis
      });
      setPixPayment(res.data);
      setPixTimer(res.data.expires_in_seconds || 420);
      setPixStatus('pending');
      setCurrentStep(FLOW_STEPS.PIX_QR);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al crear pago PIX');
    } finally {
      setLoading(false);
    }
  };

  // Simulate PIX payment (for testing)
  const simulatePixPayment = async () => {
    if (!pixPayment) return;
    
    setLoading(true);
    try {
      const res = await api.post(`/gestor/pix/simulate-payment/${pixPayment.payment_id}`);
      setPixStatus('paid');
      toast.success('¡Pago PIX confirmado!');
      await refreshUser();
      await loadDashboard();
      setCurrentStep(FLOW_STEPS.PAYMENT_SUCCESS);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al simular pago');
    } finally {
      setLoading(false);
    }
  };

  // Copy PIX code
  const copyPixCode = () => {
    if (pixPayment?.copy_paste_code) {
      navigator.clipboard.writeText(pixPayment.copy_paste_code);
      toast.success('Código PIX copiado');
    }
  };

  // Filter banks
  const filteredBanks = VENEZUELAN_BANKS.filter(bank => 
    bank.code.includes(bankSearch) || 
    bank.name.toLowerCase().includes(bankSearch.toLowerCase())
  );

  // Filter beneficiaries by payment type
  const filteredBeneficiaries = beneficiaries.filter(b => b.payment_type === paymentType);

  // Handle bank selection
  const handleSelectBank = (bank) => {
    setNewBeneficiaryData({ 
      ...newBeneficiaryData, 
      bank_code: bank.code, 
      bank: newBeneficiaryType === 'pago_movil' ? bank.code : bank.name 
    });
    setBankSearch('');
    setShowBankDropdown(false);
  };

  // Save new beneficiary
  const saveBeneficiary = async () => {
    const { full_name, cedula, bank, bank_code, phone, account_number } = newBeneficiaryData;
    
    if (!full_name || !cedula || !bank) {
      toast.error('Completa todos los campos requeridos');
      return;
    }
    
    if (newBeneficiaryType === 'pago_movil' && (!phone || phone.length !== 11)) {
      toast.error('El teléfono debe tener 11 dígitos');
      return;
    }
    
    if (newBeneficiaryType === 'transferencia' && (!account_number || account_number.length !== 20)) {
      toast.error('El número de cuenta debe tener 20 dígitos');
      return;
    }
    
    setLoading(true);
    try {
      const payload = {
        full_name,
        id_document: cedula,
        bank,
        bank_code,
        payment_type: newBeneficiaryType,
        ...(newBeneficiaryType === 'pago_movil' ? { phone_number: phone } : { account_number })
      };
      
      await api.post('/gestor/beneficiaries', payload);
      toast.success('Beneficiario guardado');
      await loadDashboard();
      setShowNewBeneficiary(false);
      setNewBeneficiaryData({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '', account_number: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al guardar');
    } finally {
      setLoading(false);
    }
  };

  // Process final transaction
  const processTransaction = async () => {
    if (!selectedBeneficiary || amountRis <= 0) {
      toast.error('Datos incompletos');
      return;
    }
    
    setLoading(true);
    try {
      await api.post('/gestor/process-transaction', {
        amount_ris: amountRis,
        beneficiary_id: selectedBeneficiary.beneficiary_id,
        client_name: 'Cliente Tercero',
        payment_type: paymentType
      });
      toast.success('¡Transacción enviada a procesamiento!');
      await refreshUser();
      await loadDashboard();
      setCurrentStep(FLOW_STEPS.DASHBOARD);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar');
    } finally {
      setLoading(false);
    }
  };

  // Styles
  const pageStyle = { minHeight: '100vh', background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)', fontFamily: 'Inter, sans-serif' };
  const cardStyle = { backgroundColor: '#ffffff', borderRadius: '20px', boxShadow: '0 10px 40px rgba(0,0,0,0.1)', padding: '24px' };
  const headerStyle = { background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)', padding: '20px', color: 'white' };
  const btnPrimary = { width: '100%', padding: '18px', borderRadius: '16px', border: 'none', background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)', color: 'white', fontSize: '16px', fontWeight: '700', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' };
  const btnSuccess = { ...btnPrimary, background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' };
  const inputStyle = { width: '100%', padding: '14px 16px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', boxSizing: 'border-box' };

  // Access check
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

  // DASHBOARD VIEW
  if (currentStep === FLOW_STEPS.DASHBOARD) {
    return (
      <div style={pageStyle} data-testid="gestor-dashboard">
        <div style={{ padding: '24px', maxWidth: '800px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <button onClick={() => navigate('/')} style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.2)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <ArrowLeft style={{ width: '20px', height: '20px', color: '#ffffff' }} />
              </button>
              <div>
                <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#ffffff', margin: 0 }}>Panel Gestor</h1>
                <p style={{ fontSize: '14px', color: 'rgba(255,255,255,0.7)', margin: 0 }}>Código: {dashboardData?.gestor_code || user?.gestor_code}</p>
              </div>
            </div>
            <NotificationBell />
          </div>

          {loading && !dashboardData ? (
            <div style={{ ...cardStyle, textAlign: 'center', padding: '60px' }}>
              <RefreshCw style={{ width: '40px', height: '40px', color: '#2563eb', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : (
            <>
              {/* Balance Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px', marginBottom: '24px' }}>
                <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                    <Wallet style={{ width: '24px', height: '24px', color: 'rgba(255,255,255,0.8)' }} />
                    <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: '14px' }}>Mi Saldo</span>
                  </div>
                  <p style={{ fontSize: '28px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                    R$ {(dashboardData?.balance_ris || 0).toFixed(2)}
                  </p>
                </div>
                
                <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }} data-testid="saldo-terceros">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                    <CreditCard style={{ width: '24px', height: '24px', color: 'rgba(255,255,255,0.8)' }} />
                    <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: '14px' }}>Saldo Terceros</span>
                  </div>
                  <p style={{ fontSize: '28px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                    R$ {balanceTerceros.toFixed(2)}
                  </p>
                </div>
              </div>

              {/* Stats */}
              <div style={{ ...cardStyle, marginBottom: '24px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>{dashboardData?.stats?.total_transactions || 0}</p>
                    <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Transacciones</p>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: '24px', fontWeight: '700', color: '#16a34a', margin: 0 }}>R$ {(dashboardData?.stats?.total_volume || 0).toFixed(0)}</p>
                    <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Volumen</p>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: '24px', fontWeight: '700', color: '#2563eb', margin: 0 }}>{dashboardData?.commission_rate || 5}%</p>
                    <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Comisión</p>
                  </div>
                </div>
              </div>

              {/* Main Action Button */}
              <button onClick={startNewTransaction} style={{ ...btnPrimary, marginBottom: '24px' }} data-testid="new-transaction-btn">
                <Plus style={{ width: '20px', height: '20px' }} /> Nuevo Envío de Tercero
              </button>

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
                          <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{tx.client_name || 'Cliente'}</p>
                          <p style={{ fontSize: '12px', color: '#6b7280', margin: 0 }}>{tx.beneficiary_name}</p>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{tx.amount_ves?.toFixed(2)} VES</p>
                          <span style={{ 
                            display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 10px', borderRadius: '20px', fontSize: '12px', fontWeight: '500',
                            backgroundColor: tx.status === 'completed' ? '#dcfce7' : tx.status === 'pending' ? '#fef3c7' : '#fee2e2',
                            color: tx.status === 'completed' ? '#16a34a' : tx.status === 'pending' ? '#d97706' : '#dc2626'
                          }}>
                            {tx.status === 'completed' ? <CheckCircle style={{ width: '14px', height: '14px' }} /> : 
                             tx.status === 'pending' ? <Clock style={{ width: '14px', height: '14px' }} /> :
                             <XCircle style={{ width: '14px', height: '14px' }} />}
                            {tx.status === 'pending' ? 'Pendiente' : tx.status === 'completed' ? 'Completado' : 'Rechazado'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // CALCULATOR VIEW
  if (currentStep === FLOW_STEPS.CALCULATOR) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: 'white' }} data-testid="calculator-step">
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <button onClick={() => setCurrentStep(FLOW_STEPS.DASHBOARD)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <ArrowLeft style={{ width: '24px', height: '24px', color: 'white' }} />
            </button>
            <span style={{ fontSize: '18px', fontWeight: '600' }}>Nuevo Envío</span>
          </div>
          <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>Ingresa el monto que el tercero pagará</p>
        </div>

        <div style={{ padding: '24px' }}>
          {/* Toggle RIS/VES */}
          <div style={{ display: 'flex', backgroundColor: '#f3f4f6', borderRadius: '12px', padding: '4px', marginBottom: '24px' }}>
            <button 
              onClick={() => setInputMode('ris')}
              style={{ flex: 1, padding: '12px', borderRadius: '10px', border: 'none', backgroundColor: inputMode === 'ris' ? '#7c3aed' : 'transparent', color: inputMode === 'ris' ? 'white' : '#6b7280', fontWeight: '600', cursor: 'pointer' }}
            >
              RIS (Reales)
            </button>
            <button 
              onClick={() => setInputMode('ves')}
              style={{ flex: 1, padding: '12px', borderRadius: '10px', border: 'none', backgroundColor: inputMode === 'ves' ? '#7c3aed' : 'transparent', color: inputMode === 'ves' ? 'white' : '#6b7280', fontWeight: '600', cursor: 'pointer' }}
            >
              VES (Bolívares)
            </button>
          </div>

          {/* Amount Display */}
          <div style={{ textAlign: 'center', marginBottom: '24px' }}>
            <div style={{ fontSize: '48px', fontWeight: '700', color: '#111827', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
              <span style={{ color: '#7c3aed' }}>{inputMode === 'ris' ? 'R$' : 'Bs'}</span>
              <span>{inputAmount || '0.00'}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginTop: '8px' }}>
              <Calculator style={{ width: '16px', height: '16px', color: '#9ca3af' }} />
              <span style={{ color: '#6b7280', fontSize: '14px' }}>
                = {inputMode === 'ris' ? `${amountVes.toFixed(2)} VES` : `R$ ${amountRis.toFixed(2)}`}
              </span>
            </div>
            <p style={{ color: '#9ca3af', fontSize: '12px', marginTop: '8px' }}>
              Tasa: 1 RIS = {risToVes.toFixed(2)} VES
            </p>
          </div>

          {/* Numeric Keypad */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '24px' }}>
            {['1','2','3','4','5','6','7','8','9','.','0','⌫'].map((key) => (
              <button 
                key={key} 
                onClick={() => handleKeyPress(key)}
                style={{ padding: '20px', fontSize: '24px', fontWeight: '600', borderRadius: '16px', border: 'none', backgroundColor: '#f3f4f6', color: '#374151', cursor: 'pointer' }}
              >
                {key}
              </button>
            ))}
          </div>

          {/* Continue Button */}
          <button 
            onClick={createPixPayment} 
            disabled={loading || amountRis <= 0}
            style={{ ...btnPrimary, opacity: (loading || amountRis <= 0) ? 0.5 : 1 }}
            data-testid="continue-to-pix-btn"
          >
            {loading ? <Loader2 style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} /> : <>Generar QR PIX <ChevronRight style={{ width: '20px', height: '20px' }} /></>}
          </button>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // PIX QR VIEW
  if (currentStep === FLOW_STEPS.PIX_QR) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: 'white' }} data-testid="pix-qr-step">
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <button onClick={() => setCurrentStep(FLOW_STEPS.CALCULATOR)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <ArrowLeft style={{ width: '24px', height: '24px', color: 'white' }} />
            </button>
            <span style={{ fontSize: '18px', fontWeight: '600' }}>Pago PIX</span>
          </div>
          <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>El tercero debe escanear el QR o copiar el código</p>
        </div>

        <div style={{ padding: '24px', textAlign: 'center' }}>
          {/* Timer */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '8px',
            backgroundColor: pixStatus === 'expired' ? '#fee2e2' : '#fef3c7',
            color: pixStatus === 'expired' ? '#dc2626' : '#d97706',
            padding: '12px 20px', borderRadius: '12px', marginBottom: '24px'
          }}>
            <Clock style={{ width: '20px', height: '20px' }} />
            <span style={{ fontWeight: '600' }}>
              {pixStatus === 'expired' ? 'Expirado' : `Expira en: ${formatTimer(pixTimer)}`}
            </span>
          </div>

          {/* Amount */}
          <div style={{ marginBottom: '24px' }}>
            <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 4px 0' }}>Monto a pagar</p>
            <p style={{ fontSize: '32px', fontWeight: '700', color: '#111827', margin: 0 }}>
              R$ {pixPayment?.amount_ris?.toFixed(2) || amountRis.toFixed(2)}
            </p>
          </div>

          {/* QR Code */}
          <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '20px', border: '2px solid #e5e7eb', display: 'inline-block', marginBottom: '24px' }}>
            <div style={{ width: '200px', height: '200px', backgroundColor: '#f3f4f6', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {pixPayment?.qr_code_base64 ? (
                <img src={`data:image/png;base64,${pixPayment.qr_code_base64}`} alt="QR PIX" style={{ width: '180px', height: '180px' }} />
              ) : (
                <QrCode style={{ width: '150px', height: '150px', color: '#374151' }} />
              )}
            </div>
          </div>

          {/* PIX Code */}
          <div style={{ backgroundColor: '#f3f4f6', borderRadius: '12px', padding: '16px', marginBottom: '24px' }}>
            <p style={{ color: '#6b7280', fontSize: '12px', margin: '0 0 8px 0' }}>Código PIX Copia y Pega</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: 'white', padding: '12px', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
              <code style={{ flex: 1, fontSize: '11px', color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {pixPayment?.copy_paste_code?.substring(0, 40) || '...'}...
              </code>
              <button 
                onClick={copyPixCode}
                style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', backgroundColor: '#7c3aed', color: 'white', fontWeight: '600', fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
              >
                <Copy style={{ width: '14px', height: '14px' }} /> Copiar
              </button>
            </div>
          </div>

          {/* Status */}
          {pixStatus === 'pending' && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: '#6b7280', marginBottom: '24px' }}>
              <Loader2 style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} />
              <span>Esperando pago...</span>
            </div>
          )}

          {/* Simulate Payment Button (for testing) */}
          <button 
            onClick={simulatePixPayment}
            disabled={loading || pixStatus !== 'pending'}
            style={{ ...btnSuccess, opacity: (loading || pixStatus !== 'pending') ? 0.5 : 1, marginBottom: '12px' }}
            data-testid="simulate-payment-btn"
          >
            {loading ? <Loader2 style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} /> : <>Simular Pago (Testing)</>}
          </button>

          {pixStatus === 'expired' && (
            <button onClick={startNewTransaction} style={btnPrimary}>
              Generar Nuevo QR
            </button>
          )}
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // PAYMENT SUCCESS VIEW
  if (currentStep === FLOW_STEPS.PAYMENT_SUCCESS) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: 'white' }} data-testid="payment-success-step">
        <div style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)', padding: '20px', color: 'white' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <CheckCircle style={{ width: '24px', height: '24px' }} />
            <span style={{ fontSize: '18px', fontWeight: '600' }}>Pago Recibido</span>
          </div>
        </div>

        <div style={{ padding: '24px', textAlign: 'center' }}>
          {/* Success Icon */}
          <div style={{ width: '120px', height: '120px', borderRadius: '50%', background: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px' }}>
            <CheckCircle style={{ width: '60px', height: '60px', color: '#16a34a' }} />
          </div>

          <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#16a34a', margin: '0 0 8px 0' }}>
            ¡Pago Realizado con Éxito!
          </h2>
          <p style={{ color: '#6b7280', margin: '0 0 32px 0' }}>
            El pago PIX ha sido confirmado
          </p>

          {/* Amount Added */}
          <div style={{ backgroundColor: '#f0fdf4', borderRadius: '16px', padding: '20px', marginBottom: '24px', border: '2px solid #bbf7d0' }}>
            <p style={{ color: '#16a34a', fontSize: '14px', margin: '0 0 8px 0', fontWeight: '600' }}>
              Añadido a Saldo Terceros
            </p>
            <p style={{ fontSize: '36px', fontWeight: '700', color: '#16a34a', margin: 0 }}>
              +R$ {amountRis.toFixed(2)}
            </p>
          </div>

          {/* New Balance */}
          <div style={{ backgroundColor: '#f3f4f6', borderRadius: '12px', padding: '16px', marginBottom: '32px' }}>
            <p style={{ color: '#6b7280', fontSize: '12px', margin: '0 0 4px 0' }}>
              Saldo Terceros Disponible
            </p>
            <p style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>
              R$ {(dashboardData?.balance_ris_terceros || balanceTerceros).toFixed(2)}
            </p>
          </div>

          <button 
            onClick={() => setCurrentStep(FLOW_STEPS.PAYMENT_TYPE)}
            style={btnSuccess}
            data-testid="continue-to-payment-type-btn"
          >
            Continuar con el Envío <ChevronRight style={{ width: '20px', height: '20px' }} />
          </button>
        </div>
      </div>
    );
  }

  // PAYMENT TYPE VIEW
  if (currentStep === FLOW_STEPS.PAYMENT_TYPE) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: 'white' }} data-testid="payment-type-step">
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <button onClick={() => setCurrentStep(FLOW_STEPS.PAYMENT_SUCCESS)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <ArrowLeft style={{ width: '24px', height: '24px', color: 'white' }} />
            </button>
            <span style={{ fontSize: '18px', fontWeight: '600' }}>Tipo de Pago</span>
          </div>
          <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>¿Cómo desea recibir el beneficiario?</p>
        </div>

        <div style={{ padding: '24px' }}>
          {/* Amount Summary */}
          <div style={{ backgroundColor: '#f3f4f6', borderRadius: '12px', padding: '16px', marginBottom: '24px', textAlign: 'center' }}>
            <p style={{ color: '#6b7280', fontSize: '12px', margin: '0 0 4px 0' }}>Monto a enviar</p>
            <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>
              {amountVes.toFixed(2)} VES
            </p>
          </div>

          {/* Payment Options */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <button 
              onClick={() => { setPaymentType('pago_movil'); setCurrentStep(FLOW_STEPS.BENEFICIARY); }}
              style={{ padding: '20px', borderRadius: '16px', border: paymentType === 'pago_movil' ? '3px solid #7c3aed' : '2px solid #e5e7eb', backgroundColor: paymentType === 'pago_movil' ? '#faf5ff' : 'white', cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: '16px' }}
              data-testid="pago-movil-option"
            >
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#7c3aed', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Phone style={{ width: '28px', height: '28px', color: 'white' }} />
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: '0 0 4px 0' }}>Pago Móvil</p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Transferencia instantánea vía teléfono</p>
              </div>
              <ChevronRight style={{ width: '24px', height: '24px', color: '#9ca3af' }} />
            </button>

            <button 
              onClick={() => { setPaymentType('transferencia'); setCurrentStep(FLOW_STEPS.BENEFICIARY); }}
              style={{ padding: '20px', borderRadius: '16px', border: paymentType === 'transferencia' ? '3px solid #7c3aed' : '2px solid #e5e7eb', backgroundColor: paymentType === 'transferencia' ? '#faf5ff' : 'white', cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: '16px' }}
              data-testid="transferencia-option"
            >
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#d97706', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Building2 style={{ width: '28px', height: '28px', color: 'white' }} />
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: '0 0 4px 0' }}>Transferencia Bancaria</p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Depósito directo a cuenta bancaria</p>
              </div>
              <ChevronRight style={{ width: '24px', height: '24px', color: '#9ca3af' }} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // BENEFICIARY VIEW
  if (currentStep === FLOW_STEPS.BENEFICIARY) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: 'white' }} data-testid="beneficiary-step" onClick={() => setShowBankDropdown(false)}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <button onClick={() => setCurrentStep(FLOW_STEPS.PAYMENT_TYPE)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <ArrowLeft style={{ width: '24px', height: '24px', color: 'white' }} />
            </button>
            <span style={{ fontSize: '18px', fontWeight: '600' }}>Seleccionar Beneficiario</span>
          </div>
          <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>
            {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia Bancaria'}
          </p>
        </div>

        <div style={{ padding: '24px' }}>
          {/* Existing Beneficiaries */}
          {filteredBeneficiaries.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '12px' }}>Beneficiarios Guardados</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '300px', overflowY: 'auto' }}>
                {filteredBeneficiaries.map((b) => (
                  <button 
                    key={b.beneficiary_id}
                    onClick={() => { setSelectedBeneficiary(b); setCurrentStep(FLOW_STEPS.CONFIRM); }}
                    style={{ width: '100%', padding: '16px', borderRadius: '12px', border: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '2px solid #7c3aed' : '1px solid #e5e7eb', backgroundColor: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '#faf5ff' : 'white', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px' }}
                  >
                    <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: paymentType === 'pago_movil' ? '#dbeafe' : '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {paymentType === 'pago_movil' ? <Phone style={{ width: '22px', height: '22px', color: '#2563eb' }} /> : <Building2 style={{ width: '22px', height: '22px', color: '#d97706' }} />}
                    </div>
                    <div style={{ flex: 1 }}>
                      <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                      <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
                        {paymentType === 'pago_movil' ? `${b.bank_code || b.bank} • ${b.phone_number}` : `${b.bank} • ****${b.account_number?.slice(-4)}`}
                      </p>
                    </div>
                    <ChevronRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Add New Beneficiary */}
          <button 
            onClick={() => { setNewBeneficiaryType(paymentType); setShowNewBeneficiary(true); }}
            style={{ width: '100%', padding: '16px', borderRadius: '12px', border: '2px dashed #d1d5db', backgroundColor: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: '#6b7280' }}
          >
            <Plus style={{ width: '20px', height: '20px' }} /> Agregar Nuevo Beneficiario
          </button>
        </div>

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

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Nombre completo *</label>
                  <input type="text" value={newBeneficiaryData.full_name} onChange={(e) => setNewBeneficiaryData({...newBeneficiaryData, full_name: e.target.value})} style={inputStyle} placeholder="Nombre del beneficiario" />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Cédula * (solo números)</label>
                  <input type="text" value={newBeneficiaryData.cedula} onChange={(e) => setNewBeneficiaryData({...newBeneficiaryData, cedula: e.target.value.replace(/[^0-9]/g, '')})} style={inputStyle} placeholder="12345678" />
                </div>
                <div style={{ position: 'relative' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Banco *</label>
                  <div style={{ position: 'relative' }}>
                    <Search style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                    <input 
                      type="text" 
                      value={showBankDropdown ? bankSearch : (newBeneficiaryData.bank_code ? `${newBeneficiaryData.bank_code} - ${newBeneficiaryData.bank}` : '')} 
                      onChange={(e) => setBankSearch(e.target.value)} 
                      onFocus={() => setShowBankDropdown(true)} 
                      style={{ ...inputStyle, paddingLeft: '44px' }} 
                      placeholder="Buscar banco..." 
                    />
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
                
                {paymentType === 'pago_movil' ? (
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Teléfono * (11 dígitos)</label>
                    <input type="text" value={newBeneficiaryData.phone} onChange={(e) => setNewBeneficiaryData({...newBeneficiaryData, phone: e.target.value.replace(/[^0-9]/g, '').slice(0, 11)})} style={inputStyle} placeholder="04141234567" maxLength={11} />
                  </div>
                ) : (
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Número de cuenta * (20 dígitos)</label>
                    <input type="text" value={newBeneficiaryData.account_number} onChange={(e) => setNewBeneficiaryData({...newBeneficiaryData, account_number: e.target.value.replace(/[^0-9]/g, '').slice(0, 20)})} style={inputStyle} placeholder="01340123456789012345" maxLength={20} />
                  </div>
                )}

                <button onClick={saveBeneficiary} disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.5 : 1 }}>
                  {loading ? 'Guardando...' : 'Guardar y Seleccionar'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // CONFIRM VIEW
  if (currentStep === FLOW_STEPS.CONFIRM) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: 'white' }} data-testid="confirm-step">
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <button onClick={() => setCurrentStep(FLOW_STEPS.BENEFICIARY)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <ArrowLeft style={{ width: '24px', height: '24px', color: 'white' }} />
            </button>
            <span style={{ fontSize: '18px', fontWeight: '600' }}>Confirmar Envío</span>
          </div>
        </div>

        <div style={{ padding: '24px' }}>
          {/* Transaction Summary */}
          <div style={{ backgroundColor: '#f9fafb', borderRadius: '16px', padding: '20px', marginBottom: '24px' }}>
            <h4 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>Resumen de Transacción</h4>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
              <span style={{ color: '#6b7280' }}>Tipo de Pago:</span>
              <span style={{ fontWeight: '600', color: '#111827' }}>
                {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}
              </span>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
              <span style={{ color: '#6b7280' }}>Beneficiario:</span>
              <span style={{ fontWeight: '600', color: '#111827' }}>{selectedBeneficiary?.full_name}</span>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
              <span style={{ color: '#6b7280' }}>
                {paymentType === 'pago_movil' ? 'Teléfono:' : 'Cuenta:'}
              </span>
              <span style={{ fontWeight: '500', color: '#374151' }}>
                {paymentType === 'pago_movil' ? selectedBeneficiary?.phone_number : `****${selectedBeneficiary?.account_number?.slice(-4)}`}
              </span>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
              <span style={{ color: '#6b7280' }}>Banco:</span>
              <span style={{ fontWeight: '500', color: '#374151' }}>
                {selectedBeneficiary?.bank_code || selectedBeneficiary?.bank}
              </span>
            </div>

            <div style={{ borderTop: '2px solid #e5e7eb', marginTop: '16px', paddingTop: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ color: '#6b7280' }}>Monto RIS:</span>
                <span style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>R$ {amountRis.toFixed(2)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280' }}>Recibe:</span>
                <span style={{ fontSize: '20px', fontWeight: '700', color: '#16a34a' }}>{amountVes.toFixed(2)} VES</span>
              </div>
            </div>
          </div>

          {/* Alert */}
          <div style={{ backgroundColor: '#fef3c7', borderRadius: '12px', padding: '16px', marginBottom: '24px', display: 'flex', gap: '12px' }}>
            <AlertCircle style={{ width: '24px', height: '24px', color: '#d97706', flexShrink: 0 }} />
            <p style={{ color: '#92400e', fontSize: '14px', margin: 0 }}>
              Esta transacción será enviada a la cola de procesamiento. Un administrador la completará pronto.
            </p>
          </div>

          {/* Confirm Button */}
          <button 
            onClick={processTransaction}
            disabled={loading}
            style={{ ...btnSuccess, opacity: loading ? 0.5 : 1 }}
            data-testid="confirm-transaction-btn"
          >
            {loading ? (
              <Loader2 style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} />
            ) : (
              <>
                <CheckCircle style={{ width: '20px', height: '20px' }} /> Confirmar y Enviar
              </>
            )}
          </button>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return null;
}
