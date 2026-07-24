import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Zap, AlertCircle, CheckCircle, Loader, ArrowLeft, ArrowRight, Plus, X, User, Smartphone, Building2, Search, Copy, Clock } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import PinConfirm from '../components/PinConfirm';


const VENEZUELAN_BANKS = [
  { code: '0102', name: 'BANCO DE VENEZUELA' },
  { code: '0104', name: 'BANCO VENEZOLANO DE CREDITO' },
  { code: '0105', name: 'BANCO MERCANTIL' },
  { code: '0108', name: 'BANCO PROVINCIAL' },
  { code: '0114', name: 'BANCARIBE' },
  { code: '0134', name: 'BANESCO' },
  { code: '0137', name: 'SOFITASA' },
  { code: '0138', name: 'BANCO PLAZA' },
  { code: '0156', name: '100% BANCO' },
  { code: '0163', name: 'BANCO DEL TESORO' },
  { code: '0168', name: 'BANCRECER' },
  { code: '0171', name: 'BANCO ACTIVO' },
  { code: '0172', name: 'BANCAMIGA BANCO UNIVERSAL, C.A.' },
  { code: '0174', name: 'BANPLUS BANCO COMERCIAL' },
  { code: '0175', name: 'BANCO DIGITAL DE LOS TRABAJADORES' },
  { code: '0177', name: 'BANCO DE LAS FUERZAS ARMADAS BANFANB' },
  { code: '0178', name: 'N58 BANCO DIGITAL' },
  { code: '0191', name: 'BANCO NACIONAL DE CREDITO' },
];


const S = {
  page: { minHeight: '100vh', background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)', fontFamily: 'Inter, sans-serif' },
  header: { background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(0,0,0,0.06)', padding: '0 20px', height: '60px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 10 },
  container: { maxWidth: '600px', margin: '0 auto', padding: '24px' },
  card: { background: '#fff', borderRadius: '16px', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 2px 16px rgba(0,0,0,0.06)', padding: '24px', marginBottom: '16px' },
  label: { fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px', display: 'block' },
  input: { width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '15px', color: '#111827', background: '#f9fafb', outline: 'none', boxSizing: 'border-box' },
  btnPrimary: { width: '100%', padding: '13px', borderRadius: '10px', background: 'linear-gradient(135deg, #f59e0b, #d97706)', border: 'none', color: '#fff', fontWeight: '700', fontSize: '15px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' },
  btnSecondary: { padding: '10px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: '#f9fafb', color: '#374151', fontWeight: '600', fontSize: '14px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' },
  stepDot: (active) => ({ width: '28px', height: '28px', borderRadius: '50%', background: active ? '#f59e0b' : '#e5e7eb', color: active ? '#fff' : '#9ca3af', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '13px', fontWeight: '700' }),
};

export default function BTCLightning() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [showPin, setShowPin] = useState(false);
  const [precioBTC, setPrecioBTC] = useState(null);
  const [tasaVES, setTasaVES] = useState(680);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);
  const [paymentType, setPaymentType] = useState('pago_movil');
  const [bankSearch, setBankSearch] = useState('');
  const [showBankDropdown, setShowBankDropdown] = useState(false);
  const bankRef = useRef(null);
    const [activeTab, setActiveTab] = useState('enviar');
    const [btcWallet, setBtcWallet] = useState(null);
  const [newBenef, setNewBenef] = useState({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '', account_number: '' });
  const [usd, setUsd] = useState('');
  const [invoiceData, setInvoiceData] = useState(null);
  const [countdown, setCountdown] = useState(1800);
  const countdownRef = useRef(null);
  const [paymentStatus, setPaymentStatus] = useState(null);
  const paymentPollingRef = useRef(null);
  const kycVerificado = user?.verification_status === 'verified';

  const fetchBtcWallet = async () => {
    try {
      setLoadingWallet(true);
      const res = await api.get('/btc/wallet');
      setBtcWallet(res.data);
    } catch (e) { setBtcWallet(null); } finally { setLoadingWallet(false); }
  };

  const fetchBtcHistorial = async () => {
    try {
      setLoadingHistorial(true);
      const res = await api.get('/btc/historial');
      setBtcHistorial(res.data.remesas || []);
    } catch (e) { setBtcHistorial([]); } finally { setLoadingHistorial(false); }
  };

  useEffect(() => {
    if (activeTab === 'billetera') fetchBtcWallet();
    if (activeTab === 'historial') fetchBtcHistorial();
  }, [activeTab]);

  useEffect(() => {
    fetchPrecioBTC();
    // Restaurar invoice de sessionStorage si existe
    const savedInvoice = sessionStorage.getItem('btc_invoice');
    if (savedInvoice) {
      try {
        const inv = JSON.parse(savedInvoice);
        setInvoiceData(inv);
        setStep(3);
      } catch (e) {
        sessionStorage.removeItem('btc_invoice');
      }
    }
    loadBeneficiaries();
    // Restaurar estado real desde el servidor (sobrevive aunque el navegador
    // cierre la pestaña mientras el usuario paga en su billetera). Si la remesa
    // ya fue pagada, mostramos la pantalla de éxito al volver.
    (async () => {
      try {
        const r = await api.get('/btc/mi-remesa-activa');
        const rem = r.data?.remesa;
        if (rem && ['pagado', 'enviado', 'completado'].includes(rem.estado)) {
          sessionStorage.removeItem('btc_invoice');
          setPaymentStatus('pagado');
          setStep(4);
        } else if (rem && rem.estado === 'pendiente' && rem.expira_en && new Date(rem.expira_en) > new Date()) {
          setInvoiceData({
            remesa_id: rem.remesa_id,
            payment_request: rem.payment_request,
            qr: 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(rem.payment_request || ''),
            sats: rem.sats,
            ves_recibe: rem.ves_recibe,
            usd_cliente: rem.usd_cliente,
            btc_pagar: rem.btc_pagar,
            expira_en: rem.expira_en,
          });
          if (rem.usd_cliente != null) setUsd(String(rem.usd_cliente));
          if (rem.beneficiario_data) setSelectedBeneficiary(rem.beneficiario_data);
          setStep(3);
        }
      } catch (e) { /* consulta opcional, no rompe el flujo */ }
    })();
    const interval = setInterval(fetchPrecioBTC, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handler = (e) => { if (bankRef.current && !bankRef.current.contains(e.target)) setShowBankDropdown(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    if (step === 3 && invoiceData) {
      let _secs = 1800;
      if (invoiceData.expira_en) {
        const _exp = new Date(invoiceData.expira_en);
        if (!isNaN(_exp.getTime()) && _exp.getTime() > Date.now()) {
          _secs = Math.max(0, Math.floor((_exp.getTime() - Date.now()) / 1000));
        }
      }
      setCountdown(_secs);
      countdownRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) { clearInterval(countdownRef.current); toast.error('El invoice expiro. Genera uno nuevo.'); return 0; }
          return prev - 1;
        });
      }, 1000);
      // Polling para detectar pago automaticamente
      paymentPollingRef.current = setInterval(async () => {
        try {
          const res = await api.get('/btc/status/' + invoiceData.remesa_id);
          if (res.data.estado === 'pagado') {
            clearInterval(paymentPollingRef.current);
            clearInterval(countdownRef.current);
            setPaymentStatus('pagado');
            setStep(4);
            sessionStorage.removeItem('btc_invoice');
          }
        } catch (e) {
          // ignorar errores de polling silenciosamente
        }
      }, 5000);
      return () => {
        clearInterval(countdownRef.current);
        clearInterval(paymentPollingRef.current);
      };
    }
  }, [step, invoiceData]);




  const fetchPrecioBTC = async () => {
    try { const res = await api.get('/btc/precio'); setPrecioBTC(res.data.precio_btc); setTasaVES(res.data.tasa_btc_ves); }
    catch { /* mantiene ultimo precio */ }
  };




  const loadBeneficiaries = async () => {
    try { const res = await api.get('/beneficiaries'); setBeneficiaries(res.data || []); }
    catch { console.error('Error cargando beneficiarios'); }
  };




  const usdNum = parseFloat(usd) || 0;
  const precioConMargen = precioBTC ? precioBTC * 0.99 : null;
  const btcAPagar = precioConMargen && usdNum > 0 ? ((usdNum * 1.02) / precioConMargen).toFixed(8) : '---';
  const vesRecibe = usdNum > 0 ? (usdNum * tasaVES).toLocaleString('es-VE') : '---';
  const fmtCountdown = (s) => Math.floor(s/60).toString().padStart(2,'0') + ':' + (s%60).toString().padStart(2,'0');
  const filteredBanks = VENEZUELAN_BANKS.filter(b => b.code.includes(bankSearch) || b.name.toLowerCase().includes(bankSearch.toLowerCase()));
  const filteredBenef = beneficiaries.filter(b => b.payment_type === paymentType);
  const copyText = (t) => navigator.clipboard.writeText(t).then(() => toast.success('Copiado'));




  const handleSaveNewBeneficiary = async () => {
    if (!newBenef.full_name || !newBenef.cedula || !newBenef.bank_code) return toast.error('Completa nombre, cedula y banco');
    if (paymentType === 'pago_movil' && !newBenef.phone) return toast.error('Telefono requerido');
    if (paymentType === 'transferencia' && !newBenef.account_number) return toast.error('Numero de cuenta requerido');
    setLoading(true);
    try {
      const payload = { full_name: newBenef.full_name, cedula: newBenef.cedula, bank_code: newBenef.bank_code, bank: newBenef.bank, payment_type: paymentType, ...(paymentType === 'pago_movil' ? { phone: newBenef.phone } : { account_number: newBenef.account_number }) };
      const res = await api.post('/beneficiaries', payload);
      setBeneficiaries(p => [...p, res.data]);
      setSelectedBeneficiary(res.data);
      setShowNewBeneficiary(false);
      setNewBenef({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '', account_number: '' });
      toast.success('Beneficiario agregado');
    } catch (err) { toast.error(err.response?.data?.detail || 'Error al guardar'); }
    finally { setLoading(false); }
  };




  const pedirConfirmacion = () => {
    if (!selectedBeneficiary) return toast.error('Selecciona un beneficiario');
    if (!usdNum || usdNum <= 0) return toast.error('Ingresa un monto valido');
    if (!precioBTC) return toast.error('Esperando precio BTC...');
    setShowPin(true);
  };
  const handleGenerarInvoice = async () => {
    if (!selectedBeneficiary) return toast.error('Selecciona un beneficiario');
    if (!usdNum || usdNum <= 0) return toast.error('Ingresa un monto valido');
    if (!precioBTC) return toast.error('Esperando precio BTC...');
    setLoading(true);
    try {
      const res = await api.post('/btc/generar-invoice', { usd_cliente: usdNum, beneficiario_id: selectedBeneficiary.beneficiary_id });
      setInvoiceData(res.data);
      sessionStorage.setItem('btc_invoice', JSON.stringify(res.data));
      setStep(3);
      try {
        const h = await api.post('/pin/hint-check');
        if (h.data?.hint) toast(h.data.message || 'Configura tu PIN para mayor seguridad en tu perfil.', { icon: '🔒' });
      } catch (_) { /* aviso opcional */ }
    } catch (err) { toast.error(err.response?.data?.detail || 'Error al generar invoice'); }
    finally { setLoading(false); }
  };

  const handleCancelRemesa = async () => {
    if (!invoiceData?.remesa_id) return;
    try {
      await api.post('/btc/cancelar/' + invoiceData.remesa_id);
    } catch (e) {
      // ignorar errores en cancelacion
    } finally {
      clearInterval(paymentPollingRef.current);
      clearInterval(countdownRef.current);
      setInvoiceData(null);
      setPaymentStatus(null);
      sessionStorage.removeItem('btc_invoice');
      setStep(2);
    }
  };


  if (!kycVerificado) {
    return (
      <div style={S.page}>
        <div style={S.header}>
          <button onClick={() => navigate('/')} style={{ ...S.btnSecondary, border: 'none', background: 'transparent' }}><ArrowLeft size={18} /> Volver</button>
          <span style={{ fontWeight: '700', color: '#111827' }}>Envio BTC Lightning</span>
          <NotificationBell />
        </div>
        {/* === NAVEGACION POR TABS === */}
        <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid #e5e7eb', background: '#fff', margin: '0 0 0 0' }}>
          {[{ id: 'enviar', label: 'Enviar BTC', icon: '⚡' }, { id: 'billetera', label: 'Billetera', icon: '👛' }, { id: 'historial', label: 'Historial', icon: '📋' }].map(tab => (
            <button key={tab.id} onClick={() => { setActiveTab(tab.id); if (tab.id !== 'enviar') { setStep(1); setInvoiceData(null); setSelectedBeneficiary(null); setUsd(''); } }}
              style={{ flex: 1, padding: '12px 8px', border: 'none', background: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: activeTab === tab.id ? '700' : '500', color: activeTab === tab.id ? '#f59e0b' : '#6b7280', borderBottom: activeTab === tab.id ? '2px solid #f59e0b' : '2px solid transparent', marginBottom: '-2px', transition: 'all 0.2s' }}>
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>
        <div style={S.container}>
          <div style={{ ...S.card, border: '1px solid #fde68a', background: '#fffbeb' }}>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <AlertCircle size={22} color='#d97706' style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <p style={{ fontWeight: '700', color: '#92400e', margin: '0 0 4px' }}>Verificacion KYC requerida</p>
                <p style={{ color: '#b45309', fontSize: '14px', margin: 0 }}>Completa tu verificacion de identidad para habilitar envios con BTC Lightning.</p>
              </div>
            </div>
            <button onClick={() => navigate('/verification')} style={{ ...S.btnPrimary, marginTop: '16px' }}>Ir a verificacion</button>
          </div>
        </div>
      </div>
    );
  }


  return (
    <div style={S.page}>
      <div style={S.header}>
        <button onClick={() => step > 1 && step < 3 ? setStep(s => s - 1) : navigate('/')} style={{ ...S.btnSecondary, border: 'none', background: 'transparent' }}>
          <ArrowLeft size={18} /> {step > 1 && step < 3 ? 'Atras' : 'Volver'}
        </button>
        <span style={{ fontWeight: '700', color: '#111827' }}>Lightning BTC</span>
        <NotificationBell />
      </div>
      <div style={S.container}>
        {activeTab === 'enviar' && step < 3 && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '8px' }}>
              {[1,2,3].map((n,i) => (
                <div key={n} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={S.stepDot(step >= n)}>{n}</div>
                  {i < 2 && <div style={{ width: '32px', height: '2px', background: step > n ? '#f59e0b' : '#e5e7eb' }} />}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '36px', marginBottom: '24px' }}>
              {['Beneficiario','Monto','Pagar'].map((label,i) => (
                <span key={label} style={{ fontSize: '11px', fontWeight: '600', color: step >= i+1 ? '#d97706' : '#9ca3af' }}>{label}</span>
              ))}
            </div>
          </>
        )}
        {activeTab === 'enviar' && step === 1 && (
          <>
            <div style={S.card}>
              <p style={{ fontWeight: '700', color: '#111827', marginBottom: '12px', fontSize: '15px' }}>Como recibira el dinero el beneficiario?</p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                {[{value:'pago_movil',label:'Pago Movil',icon:<Smartphone size={18}/>},{value:'transferencia',label:'Transferencia',icon:<Building2 size={18}/>}].map(opt => (
                  <button key={opt.value} onClick={() => { setPaymentType(opt.value); setSelectedBeneficiary(null); }}
                    style={{ padding: '14px', borderRadius: '10px', cursor: 'pointer', border: '2px solid '+(paymentType===opt.value?'#f59e0b':'#e5e7eb'), background: paymentType===opt.value?'#fffbeb':'#f9fafb', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', color: paymentType===opt.value?'#d97706':'#6b7280', fontWeight: '600', fontSize: '13px' }}>
                    {opt.icon}{opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div style={S.card}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <p style={{ fontWeight: '700', color: '#111827', margin: 0, fontSize: '15px' }}>Beneficiarios</p>
                <button onClick={() => setShowNewBeneficiary(!showNewBeneficiary)} style={{ ...S.btnSecondary, fontSize: '13px', padding: '6px 12px' }}>
                  {showNewBeneficiary ? <><X size={14}/> Cancelar</> : <><Plus size={14}/> Nuevo</>}
                </button>
              </div>
              {showNewBeneficiary && (
                <div style={{ background: '#f9fafb', borderRadius: '10px', padding: '14px', marginBottom: '14px', border: '1px solid #e5e7eb' }}>
                  <p style={{ fontWeight: '700', fontSize: '13px', color: '#374151', marginBottom: '12px' }}>
                    Nuevo — {paymentType === 'pago_movil' ? 'Pago Movil' : 'Transferencia'}
                  </p>
                  {[{key:'full_name',label:'Nombre completo',ph:'Juan Perez'},{key:'cedula',label:'Cedula',ph:'V-12345678'}].map(f => (
                    <div key={f.key} style={{ marginBottom: '10px' }}>
                      <label style={S.label}>{f.label}</label>
                      <input style={S.input} placeholder={f.ph} value={newBenef[f.key]} onChange={e => setNewBenef(p => ({...p,[f.key]:e.target.value}))} />
                    </div>
                  ))}
                  <div style={{ marginBottom: '10px', position: 'relative' }} ref={bankRef}>
                    <label style={S.label}>Banco</label>
                    <div style={{ position: 'relative' }}>
                      <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
                      <input style={{ ...S.input, paddingLeft: '32px' }} placeholder='Buscar banco...' value={newBenef.bank || bankSearch}
                        onChange={e => { setBankSearch(e.target.value); setNewBenef(p => ({...p,bank:e.target.value,bank_code:''})); setShowBankDropdown(true); }}
                        onFocus={() => setShowBankDropdown(true)} />
                    </div>
                    {showBankDropdown && filteredBanks.length > 0 && (
                      <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50, background: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', maxHeight: '180px', overflowY: 'auto' }}>
                        {filteredBanks.map(b => (
                          <div key={b.code} onClick={() => { setNewBenef(p => ({...p,bank:b.name,bank_code:b.code})); setBankSearch(''); setShowBankDropdown(false); }}
                            style={{ padding: '9px 12px', cursor: 'pointer', fontSize: '13px', color: '#374151' }}
                            onMouseEnter={e => e.currentTarget.style.background='#f9fafb'}
                            onMouseLeave={e => e.currentTarget.style.background='#fff'}>
                            <span style={{ color: '#9ca3af', marginRight: '8px' }}>{b.code}</span>{b.name}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {paymentType === 'pago_movil' ? (
                    <div style={{ marginBottom: '12px' }}>
                      <label style={S.label}>Telefono</label>
                      <input style={S.input} placeholder='0414-1234567' value={newBenef.phone} onChange={e => setNewBenef(p => ({...p,phone:e.target.value}))} />
                    </div>
                  ) : (
                    <div style={{ marginBottom: '12px' }}>
                      <label style={S.label}>Numero de cuenta</label>
                      <input style={S.input} placeholder='0102-0000-00-0000000000' value={newBenef.account_number} onChange={e => setNewBenef(p => ({...p,account_number:e.target.value}))} />
                    </div>
                  )}
                  <button onClick={handleSaveNewBeneficiary} disabled={loading} style={{ ...S.btnPrimary, padding: '10px' }}>
                    {loading ? <><Loader size={16}/> Guardando...</> : <><CheckCircle size={16}/> Guardar</>}
                  </button>
                </div>
              )}
              {filteredBenef.length === 0 && !showNewBeneficiary ? (
                <div style={{ textAlign: 'center', padding: '24px 0', color: '#9ca3af' }}>
                  <User size={32} style={{ marginBottom: '8px', opacity: 0.4 }} />
                  <p style={{ fontSize: '14px', margin: 0 }}>No tienes beneficiarios de {paymentType==='pago_movil'?'Pago Movil':'Transferencia'}</p>
                </div>
              ) : filteredBenef.map(b => (
                <div key={b.beneficiary_id} onClick={() => setSelectedBeneficiary(b)}
                  style={{ padding: '12px', borderRadius: '10px', cursor: 'pointer', marginBottom: '8px', border: '2px solid '+(selectedBeneficiary?.beneficiary_id===b.beneficiary_id?'#f59e0b':'#e5e7eb'), background: selectedBeneficiary?.beneficiary_id===b.beneficiary_id?'#fffbeb':'#f9fafb' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <p style={{ fontWeight: '700', color: '#111827', margin: '0 0 2px', fontSize: '14px' }}>{b.full_name}</p>
                      <p style={{ color: '#6b7280', fontSize: '12px', margin: 0 }}>{b.bank} - {b.payment_type==='pago_movil'?b.phone:b.account_number}</p>
                    </div>
                    {selectedBeneficiary?.beneficiary_id===b.beneficiary_id && <CheckCircle size={18} color='#f59e0b'/>}
                  </div>
                </div>
              ))}
            </div>
            <button onClick={() => setStep(2)} disabled={!selectedBeneficiary}
              style={{ ...S.btnPrimary, opacity: selectedBeneficiary?1:0.5, cursor: selectedBeneficiary?'pointer':'not-allowed' }}>
              Continuar <ArrowRight size={18}/>
            </button>
          </>
        )}
        {activeTab === 'enviar' && step === 2 && (
          <>
            <div style={{ ...S.card, background: '#fffbeb', border: '1px solid #fde68a' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: '#fde68a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <User size={18} color='#d97706'/>
                </div>
                <div>
                  <p style={{ fontWeight: '700', color: '#92400e', margin: '0 0 2px', fontSize: '14px' }}>{selectedBeneficiary?.full_name}</p>
                  <p style={{ color: '#b45309', fontSize: '12px', margin: 0 }}>{selectedBeneficiary?.bank} - {selectedBeneficiary?.payment_type==='pago_movil'?selectedBeneficiary?.phone:selectedBeneficiary?.account_number}</p>
                </div>
              </div>
            </div>
            <div style={S.card}>
              <p style={{ fontWeight: '700', color: '#111827', marginBottom: '16px', fontSize: '15px' }}>Cuanto quieres enviar?</p>
              <label style={S.label}>Monto (USDI)</label>
              <input type='number' style={{ ...S.input, fontSize: '28px', fontWeight: '700', textAlign: 'center', marginBottom: '16px', padding: '14px' }}
                placeholder='0' min='1' value={usd} onChange={e => setUsd(e.target.value)} />
              <div style={{ background: '#f9fafb', borderRadius: '10px', padding: '14px', border: '1px solid #e5e7eb' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ color: '#6b7280', fontSize: '13px' }}>Precio BTC (Binance)</span>
                  <span style={{ fontWeight: '600', color: '#111827', fontSize: '13px' }}>${precioBTC?precioBTC.toLocaleString():'...'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ color: '#6b7280', fontSize: '13px' }}>Pagas en BTC</span>
                  <span style={{ fontWeight: '700', color: '#111827', fontSize: '13px' }}>{btcAPagar} BTC</span>
                </div>
                <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#6b7280', fontSize: '13px' }}>Beneficiario recibe</span>
                  <span style={{ fontWeight: '700', color: '#16a34a', fontSize: '18px' }}>{vesRecibe} VES</span>
                </div>
              </div>
              <div style={{ background: '#1e293b', borderLeft: '3px solid #f59e0b', padding: '10px 14px', fontSize: '12px', color: '#cbd5e1', borderRadius: '6px', marginTop: '14px' }}>
                La tasa incluye 1% de margen por volatilidad. El beneficiario recibe <strong style={{ color: '#fbbf24' }}>{vesRecibe} VES</strong> garantizados.
              </div>
            </div>
            <button onClick={pedirConfirmacion} disabled={loading||!usdNum||usdNum<=0||!precioBTC}
              style={{ ...S.btnPrimary, opacity: (!usdNum||usdNum<=0||!precioBTC||loading)?0.5:1, cursor: (!usdNum||usdNum<=0||!precioBTC||loading)?'not-allowed':'pointer' }}>
              {loading?<><Loader size={18}/> Generando invoice...</>:<><Zap size={18}/> Generar Invoice Lightning</>}
            </button>
            <PinConfirm open={showPin} onClose={() => setShowPin(false)} onVerified={handleGenerarInvoice} />
          </>
        )}
        {activeTab === 'enviar' && step === 3 && invoiceData && (
          <>
            <div style={{ ...S.card, background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)', border: '1px solid #86efac', textAlign: 'center' }}>
              <div style={{ fontSize: '52px', marginBottom: '8px' }}>&#9889;</div>
              <h2 style={{ fontWeight: '800', color: '#15803d', margin: '0 0 8px', fontSize: '20px' }}>
                Tu envio esta siendo procesado
              </h2>
              <p style={{ color: '#16a34a', fontSize: '14px', margin: '0 0 16px', lineHeight: '1.5' }}>
                Una vez confirmado tu pago en Bitcoin, nuestro equipo procesara el envio de <strong>{vesRecibe} VES</strong> a <strong>{selectedBeneficiary?.full_name}</strong> via {selectedBeneficiary?.payment_type==='pago_movil'?'Pago Movil':'Transferencia Bancaria'}. Te notificaremos al completarse.
              </p>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: countdown<300?'#fee2e2':'#fef3c7', color: countdown<300?'#dc2626':'#d97706', borderRadius: '20px', padding: '6px 14px', fontSize: '13px', fontWeight: '700' }}>
                <Clock size={14}/> Invoice expira en {fmtCountdown(countdown)}
              </div>
            </div>
            <div style={S.card}>
              <p style={{ fontWeight: '700', color: '#111827', marginBottom: '14px', fontSize: '15px' }}>Paga con tu wallet Lightning</p>
              {invoiceData.qr && (
                <div style={{ textAlign: 'center', marginBottom: '16px' }}>
                  <img src={invoiceData.qr} alt='QR Lightning' style={{ width: '200px', height: '200px', borderRadius: '12px', border: '2px solid #e5e7eb', display: 'block', margin: '0 auto' }} />
                  <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '8px' }}>Escanea con tu wallet Lightning</p>
                </div>
              )}
              <div style={{ background: '#f9fafb', borderRadius: '8px', padding: '12px', border: '1px solid #e5e7eb', marginBottom: '12px' }}>
                <p style={{ fontSize: '11px', color: '#9ca3af', margin: '0 0 6px', fontWeight: '600', letterSpacing: '0.05em' }}>LIGHTNING INVOICE (BOLT11)</p>
                <p style={{ fontSize: '11px', color: '#374151', wordBreak: 'break-all', margin: '0 0 10px', fontFamily: 'monospace', lineHeight: '1.5' }}>
                  {invoiceData.payment_request?.slice(0,90)}...
                </p>
                <button onClick={() => copyText(invoiceData.payment_request)} style={{ ...S.btnSecondary, width: '100%', justifyContent: 'center', fontSize: '13px' }}>
                  <Copy size={14}/> Copiar invoice completo
                </button>
              </div>
            </div>
            <div style={S.card}>
              <p style={{ fontWeight: '700', color: '#111827', marginBottom: '14px', fontSize: '15px' }}>Resumen</p>
              {[
                { label: 'Beneficiario', value: selectedBeneficiary?.full_name },
                { label: 'Banco', value: selectedBeneficiary?.bank },
                { label: selectedBeneficiary?.payment_type==='pago_movil'?'Telefono':'Cuenta', value: selectedBeneficiary?.payment_type==='pago_movil'?selectedBeneficiary?.phone:selectedBeneficiary?.account_number },
                { label: 'Monto enviado', value: '$'+usdNum+' USDI' },
                { label: 'VES a recibir', value: vesRecibe+' VES', hl: true },
                { label: 'Metodo', value: selectedBeneficiary?.payment_type==='pago_movil'?'Pago Movil':'Transferencia Bancaria' },
              ].map(row => (
                <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #f3f4f6' }}>
                  <span style={{ color: '#6b7280', fontSize: '13px' }}>{row.label}</span>
                  <span style={{ fontWeight: '700', color: row.hl?'#16a34a':'#111827', fontSize: row.hl?'15px':'13px' }}>{row.value}</span>
                </div>
              ))}
              <div style={{ marginTop: '14px', background: '#f0fdf4', borderRadius: '8px', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle size={16} color='#16a34a'/>
                <span style={{ fontSize: '12px', color: '#15803d', fontWeight: '600' }}>Tu pago en Bitcoin se confirma al instante; el envio de los bolivares lo procesa nuestro equipo enseguida</span>
              </div>
            </div>
            <button onClick={() => navigate('/')} style={{ ...S.btnSecondary, width: '100%', justifyContent: 'center', marginBottom: '8px' }}>
              Volver al inicio
            </button>
            <button onClick={handleCancelRemesa} style={{ marginTop: '12px', padding: '12px 24px', background: '#fee2e2', color: '#dc2626', border: '1px solid #fca5a5', borderRadius: '10px', fontWeight: '700', fontSize: '14px', cursor: 'pointer', width: '100%' }}>
              Cancelar Pago
            </button>
            <button onClick={() => { setStep(1); setInvoiceData(null); setSelectedBeneficiary(null); setUsd(''); clearInterval(countdownRef.current); }}
              style={{ ...S.btnSecondary, width: '100%', justifyContent: 'center', color: '#6b7280' }}>
              Hacer otro envio
            </button>
          </>
        )}
        {activeTab === 'enviar' && step === 4 && (
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            <div style={{ fontSize: '64px', marginBottom: '16px' }}>⏳</div>
            <h2 style={{ color: '#f59e0b', fontWeight: '800', fontSize: '22px', marginBottom: '12px' }}>
              ¡Pago Recibido!
            </h2>
            <p style={{ color: '#374151', fontSize: '15px', marginBottom: '8px' }}>
              Tu envío está siendo procesado.
            </p>
            <p style={{ color: '#6b7280', fontSize: '14px', marginBottom: '24px' }}>
              Recibirás una notificación cuando tu envío esté completado (máx. 15 minutos).
            </p>
            <button onClick={() => { setStep(1); setInvoiceData(null); setPaymentStatus(null); setSelectedBeneficiary(null); setUsd(''); }} style={{ padding: '12px 28px', background: '#f59e0b', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: '700', fontSize: '15px', cursor: 'pointer' }}>
              Volver al inicio
            </button>
          </div>
        )}
      {/* === VISTA BILLETERA BTC-VES === */}
      {activeTab === 'billetera' && (
        <div style={{ padding: '16px 0' }}>
          <div style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)', borderRadius: '16px', padding: '24px', marginBottom: '16px', color: '#fff', textAlign: 'center' }}>
            <p style={{ fontSize: '13px', opacity: 0.9, marginBottom: '8px', fontWeight: '600', letterSpacing: '0.05em' }}>SALDO BTC-VES</p>
            {loadingWallet ? (
              <p style={{ fontSize: '24px', fontWeight: '800' }}>Cargando...</p>
            ) : (
              <p style={{ fontSize: '36px', fontWeight: '800', marginBottom: '4px' }}>{btcWallet ? Number(btcWallet.saldo || 0).toLocaleString('es-VE', { minimumFractionDigits: 2 }) : '0,00'}</p>
            )}
            <p style={{ fontSize: '12px', opacity: 0.8 }}>BTC-VES disponible</p>
          </div>
          <button onClick={fetchBtcWallet} style={{ width: '100%', padding: '10px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '10px', color: '#92400e', fontWeight: '600', cursor: 'pointer', marginBottom: '16px', fontSize: '14px' }}>
            🔄 Actualizar saldo
          </button>
          <div style={{ background: '#fff', borderRadius: '12px', padding: '16px', border: '1px solid #e5e7eb' }}>
            <p style={{ fontWeight: '700', color: '#111827', marginBottom: '12px', fontSize: '14px' }}>ℹ️ ¿Qué es BTC-VES?</p>
            <p style={{ color: '#6b7280', fontSize: '13px', lineHeight: '1.6' }}>
              Cuando pagas con Bitcoin Lightning, registramos tu pago al confirmarse en la red. 
              Ese monto representa el equivalente en bolívares que nuestro equipo enviará a tu 
              beneficiario al completar la transferencia.
            </p>
          </div>
        </div>
      )}
      {/* === VISTA HISTORIAL BTC === */}
      {activeTab === 'historial' && (
        <div style={{ padding: '16px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontWeight: '700', color: '#111827', fontSize: '16px', margin: 0 }}>Mis Órdenes BTC</h3>
            <button onClick={fetchBtcHistorial} style={{ padding: '6px 12px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', color: '#92400e', fontWeight: '600', cursor: 'pointer', fontSize: '12px' }}>🔄 Actualizar</button>
          </div>
          {loadingHistorial ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Cargando historial...</div>
          ) : btcHistorial.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', background: '#f9fafb', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
              <p style={{ fontSize: '40px', marginBottom: '12px' }}>📋</p>
              <p style={{ color: '#6b7280', fontWeight: '600' }}>No tienes órdenes BTC aún</p>
              <p style={{ color: '#9ca3af', fontSize: '13px', marginTop: '4px' }}>Tus envíos con BTC Lightning aparecerán aquí</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {btcHistorial.map((r, i) => {
                const estadoConfig = { pendiente: { color: '#f59e0b', bg: '#fffbeb', label: '⏳ Pendiente' }, pagado: { color: '#3b82f6', bg: '#eff6ff', label: '💰 Pagado' }, enviado: { color: '#10b981', bg: '#ecfdf5', label: '✅ Completado' }, cancelado: { color: '#ef4444', bg: '#fef2f2', label: '❌ Cancelado' } };
                const cfg = estadoConfig[r.estado] || { color: '#6b7280', bg: '#f9fafb', label: r.estado };
                return (
                  <div key={r.remesa_id || i} style={{ background: '#fff', borderRadius: '12px', padding: '16px', border: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                      <div>
                        <p style={{ fontWeight: '700', color: '#111827', fontSize: '15px', margin: '0 0 2px' }}>{Number(r.ves_recibe || 0).toLocaleString('es-VE', { minimumFractionDigits: 2 })} Bs</p>
                        <p style={{ color: '#6b7280', fontSize: '12px', margin: 0 }}>{r.usd_cliente ? Number(r.usd_cliente).toFixed(2) + ' USDI' : ''} · {r.sats ? Number(r.sats).toLocaleString() + ' sats' : ''}</p>
                      </div>
                      <span style={{ background: cfg.bg, color: cfg.color, padding: '4px 10px', borderRadius: '20px', fontSize: '12px', fontWeight: '700' }}>{cfg.label}</span>
                    </div>
                    {r.beneficiario_data && (
                      <p style={{ color: '#374151', fontSize: '12px', margin: '0 0 6px', padding: '8px', background: '#f9fafb', borderRadius: '8px' }}>
                        👤 {r.beneficiario_data.full_name} · {r.beneficiario_data.payment_type === 'pago_movil' ? '📱 Pago Móvil' : '🏦 Transferencia'}
                      </p>
                    )}
                    <p style={{ color: '#9ca3af', fontSize: '11px', margin: 0 }}>
                      {r.creado_en ? new Date(r.creado_en).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
}
