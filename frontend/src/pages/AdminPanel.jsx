import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';h
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Users, ArrowUpRight, ArrowDownLeft, TrendingUp, Search, 
  RefreshCw, Shield, Activity, Eye, X, ChevronRight, UserCog, Gift, Briefcase, KeyRound, Trash2, MessageSquare, CheckCircle, Clock, Phone, Mail, Send, Download, Image, Upload, AlertCircle, Zap
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { fmt, formatAccountNumber } from '../utils/format';
import { WipeButton } from '../components/common/WipeButton';
import { RestoreButton } from '../components/common/RestoreButton';
import { AutoRateCard } from '../components/common/AutoRateCard';
import { BcvRatesCard } from '../components/common/BcvRatesCard';
import KycPanel from '../components/admin/KycPanel';
import { StatusBadge } from '../components/dashboard/TransactionItem';

// Convertir URL de imagen a ruta accesible
const convertTwilioUrl = (url) => {
  if (!url) return url;
  // URLs locales ya funcionan via proxy Kubernetes
  if (url.startsWith('/api/static/') || url.startsWith('/api/media/')) return url;
  // Base64 inline
  if (url.startsWith('data:')) return url;
  // URLs directas de Twilio -> pasar por proxy backend
  if (url.includes('api.twilio.com')) {
    const match = url.match(/\/Accounts\/(AC[^/]+\/.*)/);
    if (match) return `/api/media/twilio/${match[1]}`;
  }
  return url;
};

// Función para enmascarar el CPF (solo muestra últimos 3 dígitos)
const maskCPF = (cpf) => {
  if (!cpf) return '';
  const cleanCPF = cpf.replace(/\D/g, '');
  if (cleanCPF.length < 3) return cpf;
  const lastThree = cleanCPF.slice(-3);
  return `***.***.**${lastThree.charAt(0)}-${lastThree.slice(1)}`;
};

const TABS = [
  { key: 'overview', label: 'Resumen', icon: Activity },
  { key: 'withdrawals', label: 'Retiros', icon: ArrowUpRight },
  { key: 'recharges', label: 'Recargas VES', icon: ArrowDownLeft },
  { key: 'partners', label: 'Socios', icon: Briefcase },
  { key: 'users', label: 'Usuarios', icon: Users },
  { key: 'kyc', label: 'KYC', icon: Shield },
  { key: 'chat', label: 'Chat', icon: MessageSquare },
  { key: 'support', label: 'Soporte', icon: MessageSquare },
  { key: 'rates', label: 'Tasas', icon: TrendingUp },
  { key: 'btc', label: 'BTC Lightning', icon: Zap },
];

export default function AdminPanel() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { rates, refreshRates } = useRate();
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ users: 0, pending_withdrawals: 0, pending_recharges: 0, pending_kyc: 0 });
  const [withdrawals, setWithdrawals] = useState([]);
  const [queueStats, setQueueStats] = useState({ total_pending: 0, active_in_whatsapp: 0, waiting_in_queue: 0, total_ves_pending: 0, total_ris_pending: 0 });
  const [recharges, setRecharges] = useState([]);
  const [users, setUsers] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState(null);
  const [showProcessModal, setShowProcessModal] = useState(false);
  const [processBankId, setProcessBankId] = useState('');
  const [rechargeBankSel, setRechargeBankSel] = useState({}); // txId -> bankId
  const [proofImages, setProofImages] = useState([]);  // Array for multiple images
  const [newRate, setNewRate] = useState('');
  const [newRateVesToRis, setNewRateVesToRis] = useState('');
  const [newRateBrlToRis, setNewRateBrlToRis] = useState('');
  const [selectedUser, setSelectedUser] = useState(null);
  const [userHistory, setUserHistory] = useState(null);
  const [loadingUser, setLoadingUser] = useState(false);
  const [userSearchQuery, setUserSearchQuery] = useState('');
  const [showRoleModal, setShowRoleModal] = useState(false);
  const [selectedUserForRole, setSelectedUserForRole] = useState(null);
  const [assigningRole, setAssigningRole] = useState(false);
  const [showCleanupModal, setShowCleanupModal] = useState(false);
  const [pendingToClean, setPendingToClean] = useState([]);
  const [cleaningUp, setCleaningUp] = useState(false);
  const [driveConnected, setDriveConnected] = useState(false);
  const [uploadingKyc, setUploadingKyc] = useState(false);
  // Partner/Gestor management states
  const [partners, setPartners] = useState([]);
  const [gestors, setGestors] = useState([]);
  const [partnerSearchQuery, setPartnerSearchQuery] = useState('');
  const [partnerTab, setPartnerTab] = useState('socios'); // 'socios' or 'gestores'
  // Support requests state
  const [supportRequests, setSupportRequests] = useState([]);
  const [supportFilter, setSupportFilter] = useState('pending'); // 'pending', 'resolved', 'all'
  // Chat state
  const [supportChats, setSupportChats] = useState([]);
  const [selectedChat, setSelectedChat] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatReply, setChatReply] = useState('');
  const [accountingBanks, setAccountingBanks] = useState([]);
  // Modal para rechazar recarga VES
  const [showRejectRechargeModal, setShowRejectRechargeModal] = useState(false);
  const [rejectRechargeId, setRejectRechargeId] = useState(null);
  const [rejectRechargeReason, setRejectRechargeReason] = useState('');

  // === BTC Orders State ===
  const [btcOrdenesP, setBtcOrdenesP] = useState([]);
  const [loadingBtcOrdenes, setLoadingBtcOrdenes] = useState(false);
  const [marcandoBtc, setMarcandoBtc] = useState(null);

  useEffect(() => { loadData(); }, [activeTab]);

  useEffect(() => {
    api.get('/admin/accounting/banks').then(res => setAccountingBanks(res.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    api.get('/oauth/drive/status').then(res => setDriveConnected(res.data.connected)).catch(() => {});
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      switch (activeTab) {
        case 'overview':
          const [wRes, rRes, uRes, kRes] = await Promise.all([
            api.get('/admin/withdrawals/pending').catch(() => ({ data: [] })),
            api.get('/admin/recharges/ves/pending').catch(() => ({ data: { recharges: [] } })),
            api.get('/admin/users').catch(() => ({ data: { users: [] } })),
            api.get('/admin/kyc/list', { params: { status: 'pending', limit: 1 } }).catch(() => ({ data: { counts: { pending: 0 } } }))
          ]);
          setStats({
            pending_withdrawals: (wRes.data || []).length,
            pending_recharges: (rRes.data?.recharges || []).length,
            users: (uRes.data?.users || []).length,
            pending_kyc: (kRes.data?.counts?.pending ?? 0)
          });
          break;
        case 'withdrawals':
          // Get all withdrawals and queue stats
          const [wAllRes, queueStatsRes] = await Promise.all([
            api.get('/admin/withdrawals/all'),
            api.get('/withdrawal/queue-stats').catch(() => ({ data: { total_pending: 0, active_in_whatsapp: 0, waiting_in_queue: 0 } }))
          ]);
          setWithdrawals(wAllRes.data || []);
          setQueueStats(queueStatsRes.data || { total_pending: 0, active_in_whatsapp: 0, waiting_in_queue: 0 });
          break;
        case 'recharges':
          const rAllRes = await api.get('/admin/recharges/ves');
          setRecharges(rAllRes.data || []);
          break;
        case 'partners':
          // Load both socios and gestores
          const [partnersRes, gestorsRes] = await Promise.all([
            api.get('/admin/partners').catch(() => ({ data: [] })),
            api.get('/admin/gestors').catch(() => ({ data: [] }))
          ]);
          setPartners(partnersRes.data || []);
          setGestors(gestorsRes.data || []);
          break;
        case 'users':
          const usersRes = await api.get('/admin/users');
          setUsers(usersRes.data?.users || []);
          break;
        case 'kyc':
          // Handled fully by <KycPanel/> (it fetches its own data via /admin/kyc/list)
          break;
        case 'support':
          const supportRes = await api.get('/admin/support-requests');
          setSupportRequests(supportRes.data?.requests || []);
          break;
        case 'chat':
          const chatsRes = await api.get('/admin/support/chats');
          setSupportChats(chatsRes.data || []);
          break;
      }
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleProcessWithdrawal = async () => {
    if (!selectedItem || proofImages.length === 0) { toast.error('Sube al menos un comprobante de pago'); return; }
    if (!processBankId) { toast.error('Selecciona el banco desde donde se pagó'); return; }
    try {
      await api.post('/admin/withdrawals/process', {
        transaction_id: selectedItem.transaction_id,
        action: 'approve',
        proof_images: proofImages,
        proof_image: proofImages[0],
        bank_id: processBankId
      });
      toast.success('Retiro procesado exitosamente');
      setShowProcessModal(false); setSelectedItem(null); setProofImages([]); setProcessBankId(''); loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Error al procesar'); }
  };

  const handleRejectWithdrawal = async (txId) => {
    if (!confirm('¿Rechazar este retiro? El monto será devuelto al usuario.')) return;
    try { 
      await api.post('/admin/withdrawals/process', { 
        transaction_id: txId, 
        action: 'reject',
        rejection_reason: 'Rechazado por administrador'
      }); 
      toast.success('Retiro rechazado y balance devuelto'); 
      loadData(); 
    } 
    catch (error) { toast.error(error.response?.data?.detail || 'Error al rechazar'); }
  };

  // Aprobar recarga VES (banco se toma automáticamente de la transacción)
  const handleApproveRechargeVES = async (txId) => {
    try {
      await api.post(`/admin/recharges/ves/process/${txId}`, { action: 'approve' });
      toast.success('Recarga aprobada - Saldo acreditado');
      loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Error al aprobar');  loadData();}
  };

  // Rechazar recarga VES
  const handleRejectRechargeVES = (txId) => {
    setRejectRechargeId(txId);
    setRejectRechargeReason('');
    setShowRejectRechargeModal(true);
  };

  const handleConfirmRejectRechargeVES = async () => {
    if (!rejectRechargeReason.trim()) {
      toast.error('Debes proporcionar un motivo de rechazo');
      return;
    }
    try {
      await api.post(`/admin/recharges/ves/process/${rejectRechargeId}`, { 
        action: 'reject', 
        rejection_reason: rejectRechargeReason.trim()
      });
      toast.success('Recarga rechazada');
      setShowRejectRechargeModal(false);
      setRejectRechargeId(null);
      setRejectRechargeReason('');
      loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Error al rechazar');  loadData();}
  };

  const handleApproveRecharge = async (txId) => {
    try { await api.post('/admin/recharge/approve', { transaction_id: txId, approved: true }); toast.success('Recarga aprobada'); loadData(); } 
    catch { toast.error('Error al aprobar'); }
  };

  // Refresh overview stats after KYC actions (the KycPanel manages its own state)
  const refreshKycStats = async () => {
    try {
      const res = await api.get('/admin/kyc/list', { params: { status: 'pending', limit: 1 } });
      setStats((prev) => ({ ...prev, pending_kyc: res.data?.counts?.pending ?? 0 }));
    } catch { /* silent */ }
  };

  const handleChangeRole = async (newRole) => {
    if (!selectedUserForRole) return;
    setAssigningRole(true);
    try {
      const response = await api.post('/admin/change-role', {
        user_id: selectedUserForRole.user_id,
        new_role: newRole
      });
      toast.success(response.data.message);
      setShowRoleModal(false);
      setSelectedUserForRole(null);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al cambiar rol');
    } finally {
      setAssigningRole(false);
    }
  };

  const handleResetPassword = async (userId, userName) => {
    if (!confirm(`¿Restablecer contraseña de ${userName}? Se enviará una contraseña temporal por email.`)) return;
    
    try {
      const response = await api.post('/admin/reset-password', { user_id: userId });
      toast.success(
        <div>
          <p><strong>{response.data.message}</strong></p>
          <p style={{fontSize: '12px', marginTop: '4px'}}>
            Contraseña temporal: <code style={{background: '#f3f4f6', padding: '2px 6px', borderRadius: '4px'}}>{response.data.temp_password}</code>
          </p>
          {response.data.email_sent && <p style={{fontSize: '11px', color: '#6b7280'}}>Email enviado al usuario</p>}
        </div>,
        { duration: 10000 }
      );
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al restablecer contraseña');
    }
  };

  const handleUpdateRate = async () => {
    if (!newRate || parseFloat(newRate) <= 0) { toast.error('Ingresa una tasa válida'); return; }
    try { 
      await api.post('/admin/rates', { 
        ris_to_ves: parseFloat(newRate)
      }); 
      toast.success('Tasa RIS → VES actualizada'); 
      refreshRates(); 
      setNewRate(''); 
    } 
    catch { toast.error('Error al actualizar tasa'); }
  };

  const handleUpdateRateVesToRis = async () => {
    if (!newRateVesToRis || parseFloat(newRateVesToRis) <= 0) { toast.error('Ingresa una tasa válida'); return; }
    try { 
      await api.post('/admin/rates', { 
        ves_to_ris_rate: parseFloat(newRateVesToRis)
      }); 
      toast.success('Tasa VES → RIS actualizada'); 
      refreshRates(); 
      setNewRateVesToRis('');
    } 
    catch { toast.error('Error al actualizar tasa'); }
  };

  const handleUpdateRateBrlToRis = async () => {
    if (!newRateBrlToRis || parseFloat(newRateBrlToRis) <= 0) { toast.error('Ingresa una tasa válida'); return; }
    try { 
      await api.post('/admin/rates', { 
        brl_to_ris: parseFloat(newRateBrlToRis)
      }); 
      toast.success('Tasa BRL → RIS actualizada'); 
      refreshRates(); 
      setNewRateBrlToRis('');
    } 
    catch { toast.error('Error al actualizar tasa'); }
  };

  // Cargar historial completo de un usuario
  const loadUserHistory = async (userId) => {
    setLoadingUser(true);
    try {
      const response = await api.get(`/admin/users/${userId}/complete`);
      const data = response.data;
      setUserHistory({
        user: {
          ...data.profile,
          cpf: data.profile?.cpf_number || data.kyc?.cpf_number,
          cpf_number: data.profile?.cpf_number || data.kyc?.cpf_number,
          full_name: data.profile?.full_name || data.profile?.name,
          phone_number: data.profile?.phone_number || data.kyc?.phone_number,
          document_number: data.profile?.document_number || data.kyc?.document_number,
          verification_status: data.profile?.verification_status || data.kyc?.status,
          email: data.profile?.email,
          role: data.profile?.role,
          created_at: data.profile?.created_at,
          last_login: data.profile?.last_login,
          email_verified: data.profile?.email_verified,
          gestor_code: data.profile?.gestor_code,
          referral_code: data.profile?.referral_code,
          balance_ris: data.profile?.balance_ris,
          balance_ris_terceros: data.profile?.balance_ris_terceros,
        },
        stats: {
          total_recharged: data.stats?.total_recharged_ris || 0,
          total_withdrawn: data.stats?.total_withdrawn_ris || 0,
          total_ves_sent: data.stats?.total_ves_sent || 0,
        },
        recharges: (data.recharges || []).map(tx => ({
          ...tx,
          type: 'recharge',
          amount_output: tx.amount_ris,
          amount_ves: tx.amount_brl,
        })),
        withdrawals: (data.withdrawals || []).map(tx => ({
          ...tx,
          type: 'withdrawal',
          amount_input: tx.amount_ris,
          amount_output: tx.amount_ves,
          beneficiary_name: tx.beneficiary?.full_name,
          beneficiary_bank: tx.beneficiary?.bank,
        })),
        beneficiaries: data.beneficiaries || [],
      });
      const selectedUserData = users.find(u => u.user_id === userId);
      setSelectedUser(selectedUserData);
    } catch (error) {
      toast.error('Error al cargar historial del usuario');
      console.error(error);
    } finally {
      setLoadingUser(false);
    }
  };

  const closeUserModal = () => {
    setSelectedUser(null);
    setUserHistory(null);
  };

  // Filtrar usuarios por búsqueda
  const filteredUsers = users.filter(u => 
    userSearchQuery === '' || 
    u.name?.toLowerCase().includes(userSearchQuery.toLowerCase()) ||
    u.email?.toLowerCase().includes(userSearchQuery.toLowerCase())
  );

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      const newImages = [];
      let processed = 0;
      files.forEach(file => {
        const reader = new FileReader();
        reader.onload = () => {
          newImages.push(reader.result);
          processed++;
          if (processed === files.length) {
            setProofImages(prev => [...prev, ...newImages]);
          }
        };
        reader.readAsDataURL(file);
      });
    }
  };

  const removeProofImage = (index) => {
    setProofImages(prev => prev.filter((_, i) => i !== index));
  };

  const filteredWithdrawals = withdrawals.filter(w => {
    if (statusFilter !== 'all' && w.status !== statusFilter) return false;
    if (searchQuery && !w.beneficiary_data?.full_name?.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  // Cleanup functions
  const checkPendingToClean = async () => {
    try {
      const response = await api.get('/admin/withdrawals/cleanup-check');
      setPendingToClean(response.data.pending_transactions || []);
      setShowCleanupModal(true);
    } catch (error) {
      toast.error('Error al verificar transacciones');
    }
  };

  const deleteSingleWithdrawal = async (txId) => {
    if (!confirm('¿Eliminar esta transacción? El saldo será reembolsado al usuario.')) return;
    setCleaningUp(true);
    try {
      await api.delete(`/admin/withdrawals/delete/${txId}`);
      toast.success('Transacción eliminada y saldo reembolsado');
      setPendingToClean(prev => prev.filter(tx => tx.transaction_id !== txId));
      loadData();
    } catch (error) {
      toast.error('Error al eliminar');
    } finally {
      setCleaningUp(false);
    }
  };

  const cleanupAllPending = async () => {
    if (!confirm('¿Cancelar TODAS las transacciones pendientes? Los saldos serán reembolsados.')) return;
    setCleaningUp(true);
    try {
      const response = await api.post('/admin/withdrawals/cleanup');
      toast.success(response.data.message);
      setShowCleanupModal(false);
      setPendingToClean([]);
      loadData();
    } catch (error) {
      toast.error('Error al limpiar');
    } finally {
      setCleaningUp(false);
    }
  };

  const pageStyle = { minHeight: '100vh', background: '#f8f9fc', fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' };
  const cardStyle = { backgroundColor: '#ffffff', borderRadius: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', border: '1px solid #e5e7eb' };
  const btnPrimary = { backgroundColor: '#6366f1', color: 'white', borderRadius: '12px', padding: '10px 20px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '14px' };
  const btnSuccess = { backgroundColor: '#16a34a', color: 'white', borderRadius: '10px', padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '13px' };
  const btnDanger = { backgroundColor: '#dc2626', color: 'white', borderRadius: '10px', padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '13px' };
  const btnSecondary = { backgroundColor: '#f3f4f6', color: '#374151', borderRadius: '12px', padding: '10px 20px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '14px' };


  // === BTC Orders Functions ===
  const fetchBtcOrdenesPendientes = async () => {
    try {
      setLoadingBtcOrdenes(true);
      const res = await api.get('/btc/operador/pendientes');
      setBtcOrdenesP(res.data.ordenes || []);
    } catch (e) {
      toast.error('Error cargando órdenes BTC');
      setBtcOrdenesP([]);
    } finally {
      setLoadingBtcOrdenes(false);
    }
  };

  const handleMarcarBtcEnviado = async (remesa_id) => {
    if (!window.confirm('¿Confirmar que ya realizaste la transferencia al beneficiario?')) return;
    try {
      setMarcandoBtc(remesa_id);
      await api.post('/btc/operador/marcar-enviado', { remesa_id });
      toast.success('Orden marcada como enviada exitosamente');
      fetchBtcOrdenesPendientes();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error al marcar como enviado');
    } finally {
      setMarcandoBtc(null);
    }

  // Load BTC orders when BTC tab is active
  useEffect(() => {
    if (activeTab === 'btc') {
      fetchBtcOrdenesPendientes();
    }
  }, [activeTab]);

  };

  return (
    <div style={pageStyle} data-testid="admin-panel">
      {/* Header */}
      <header style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #e5e7eb', position: 'sticky', top: 0, zIndex: 40 }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '64px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <button onClick={() => navigate('/')} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="back-button">
                <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
              </button>
              <div>
                <h1 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Panel de Control</h1>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{user?.role === 'super_admin' ? 'Super Admin' : 'Admin'}</p>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <RestoreButton userRole={user?.role} onSuccess={loadData} size="sm" />
              <button onClick={loadData} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="refresh-button">
                <RefreshCw style={{ width: '20px', height: '20px', color: '#374151', animation: loading ? 'spin 1s linear infinite' : 'none' }} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #e5e7eb' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '8px 24px' }}>
          <div style={{ display: 'flex', gap: '8px', overflowX: 'auto' }}>
            {TABS.map((tab) => (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 16px', borderRadius: '12px', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap', fontSize: '14px', fontWeight: '500',
                  backgroundColor: activeTab === tab.key ? '#6366f1' : 'transparent', color: activeTab === tab.key ? '#ffffff' : '#6b7280' }}
                data-testid={`tab-${tab.key}`}
              >
                <tab.icon style={{ width: '18px', height: '18px' }} /> {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <main style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px' }}>
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
              {[
                { icon: ArrowUpRight, value: stats.pending_withdrawals, label: 'Retiros pendientes', bg: '#fef3c7', iconColor: '#d97706' },
                { icon: ArrowDownLeft, value: stats.pending_recharges, label: 'Recargas pendientes', bg: '#dcfce7', iconColor: '#16a34a' },
                { icon: Users, value: stats.users, label: 'Usuarios totales', bg: '#dbeafe', iconColor: '#2563eb' },
                { icon: Shield, value: stats.pending_kyc, label: 'KYC pendientes', bg: '#f3e8ff', iconColor: '#9333ea' },
              ].map((item, i) => (
                <div key={i} style={{ ...cardStyle, padding: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <div style={{ width: '44px', height: '44px', borderRadius: '14px', backgroundColor: item.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <item.icon style={{ width: '22px', height: '22px', color: item.iconColor }} />
                    </div>
                    <span style={{ fontSize: '28px', fontWeight: '700', color: '#111827' }}>{item.value}</span>
                  </div>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>{item.label}</p>
                </div>
              ))}
            </div>
            
            {/* Maintenance Buttons */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
              <div style={{ ...cardStyle, padding: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#fef2f2', border: '1px solid #fecaca' }}>
                <div>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600', color: '#991b1b' }}>Mantenimiento WhatsApp</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#b91c1c' }}>Si no llegan notificaciones de retiros</p>
                </div>
                <button
                  onClick={async () => {
                    try {
                      const res = await api.post('/admin/fix-whatsapp-queue');
                      toast.success(`Cola corregida. Desbloqueados: ${res.data.unblocked}`);
                    } catch (e) {
                      toast.error('Error al corregir cola');
                    }
                  }}
                  style={{ padding: '12px 20px', borderRadius: '12px', border: 'none', backgroundColor: '#dc2626', color: 'white', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}
                  data-testid="fix-whatsapp-btn"
                >
                  Reparar Cola
                </button>
              </div>

              <div style={{ ...cardStyle, padding: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#fefce8', border: '1px solid #fef08a' }}>
                <div>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600', color: '#854d0e' }}>Reparar Imágenes</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#a16207' }}>Convierte URLs de Twilio a base64 para que se vean correctamente</p>
                </div>
                <button
                  onClick={async () => {
                    try {
                      toast('Procesando imágenes... puede tardar unos segundos');
                      const res = await api.post('/admin/fix-media-urls');
                      toast.success(`Imágenes convertidas: ${res.data.transactions_fixed}`);
                      if (res.data.errors?.length > 0) {
                        toast.error(`Errores: ${res.data.errors.length}`);
                      }
                      loadData();
                    } catch (e) {
                      toast.error('Error al corregir imágenes');
                    }
                  }}
                  style={{ padding: '12px 20px', borderRadius: '12px', border: 'none', backgroundColor: '#ca8a04', color: 'white', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}
                  data-testid="fix-media-btn"
                >
                  Reparar Imágenes
                </button>
              </div>
            </div>
            
            <div style={{ ...cardStyle, padding: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>Tasa actual</h3>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
                <div>
                  <p style={{ fontSize: '32px', fontWeight: '700', color: '#111827', margin: 0 }}>1 RIS = {fmt(rates?.ris_to_ves) || '0.00'} VES</p>
                  {rates?.auto_rate_enabled && rates?.is_off_hours && (
                    <p style={{ fontSize: '12px', color: '#ca8a04', margin: '4px 0 0 0', fontWeight: '600' }}>
                      Modo automático activo — Base: {fmt(rates?.base_ris_to_ves)}
                    </p>
                  )}
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>
                    Última actualización: {rates?.updated_at
                      ? new Date(rates.updated_at).toLocaleString('es-VE', { timeZone: 'America/Caracas', dateStyle: 'short', timeStyle: 'medium' })
                      : '—'}
                  </p>
                </div>
                <button onClick={() => setActiveTab('rates')} style={btnPrimary}>Modificar</button>
              </div>
            </div>

            <AutoRateCard
              baseRisToVes={rates?.base_ris_to_ves ?? rates?.ris_to_ves}
              baseVesToRis={rates?.base_ves_to_ris_rate ?? rates?.ves_to_ris_rate}
              onChange={loadData}
              userRole={user?.role}
            />

            <BcvRatesCard />
          </div>
        )}

        {/* Withdrawals Tab */}
        {activeTab === 'withdrawals' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* FIFO Queue Status Banner */}
            <div style={{ ...cardStyle, padding: '16px', background: 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)', border: '1px solid #7dd3fc' }}>
              {/* Total VES Required - Highlighted */}
              <div style={{ 
                background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)', 
                border: '2px solid #f59e0b', 
                borderRadius: '12px', 
                padding: '16px', 
                marginBottom: '16px',
                textAlign: 'center'
              }}>
                <p style={{ margin: 0, fontSize: '12px', color: '#92400e', fontWeight: '600', textTransform: 'uppercase' }}>💵 Total VES Necesarios</p>
                <p style={{ margin: '4px 0 0 0', fontSize: '28px', fontWeight: '800', color: '#b45309' }}>
                  {fmt(queueStats.total_ves_pending)} VES
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#78350f' }}>
                  ({fmt(queueStats.total_ris_pending)} RIS en {queueStats.total_pending} retiros pendientes)
                </p>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '20px' }}>📋</span>
                  <span style={{ fontWeight: '600', color: '#0369a1' }}>Cola WhatsApp (FIFO)</span>
                </div>
                <div style={{ display: 'flex', gap: '16px', marginLeft: 'auto' }}>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ margin: 0, fontSize: '20px', fontWeight: '700', color: '#0369a1' }}>{queueStats.total_pending}</p>
                    <p style={{ margin: 0, fontSize: '11px', color: '#6b7280' }}>Pendientes</p>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ margin: 0, fontSize: '20px', fontWeight: '700', color: '#059669' }}>{queueStats.active_in_whatsapp}</p>
                    <p style={{ margin: 0, fontSize: '11px', color: '#6b7280' }}>Activo WhatsApp</p>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ margin: 0, fontSize: '20px', fontWeight: '700', color: '#f59e0b' }}>{queueStats.waiting_in_queue}</p>
                    <p style={{ margin: 0, fontSize: '11px', color: '#6b7280' }}>En Cola</p>
                  </div>
                </div>
              </div>
              <p style={{ margin: '12px 0 0 0', fontSize: '12px', color: '#64748b' }}>
                ℹ️ El sistema FIFO envía un retiro a la vez por WhatsApp. Cuando completes el retiro activo, se enviará automáticamente el siguiente de la cola. También puedes procesar retiros directamente desde este panel.
              </p>
            </div>
            
            <div style={{ ...cardStyle, padding: '16px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
                <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                  <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                  <input type="text" placeholder="Buscar por beneficiario..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                    style={{ width: '100%', padding: '10px 10px 10px 40px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '14px', outline: 'none' }} />
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {['all', 'pending', 'completed', 'rejected'].map((status) => (
                    <button key={status} onClick={() => setStatusFilter(status)}
                      style={{ padding: '10px 16px', borderRadius: '12px', border: 'none', cursor: 'pointer', fontSize: '14px', fontWeight: 600,
                        backgroundColor: statusFilter === status ? '#5B4FE9' : '#f3f4f6',
                        color: statusFilter === status ? '#ffffff' : '#374151',
                        boxShadow: statusFilter === status ? '0 4px 10px rgba(91,79,233,0.30)' : 'none',
                        transition: 'all 0.2s' }}>
                      {status === 'all' ? 'Todos' : status === 'pending' ? 'Pendientes' : status === 'completed' ? 'Aprobados' : 'Rechazados'}
                    </button>
                  ))}
                  {/* Cleanup Button - Only for SuperAdmin */}
                  {user?.role === 'super_admin' && (
                    <button onClick={checkPendingToClean}
                      style={{ padding: '10px 16px', borderRadius: '12px', border: 'none', cursor: 'pointer', fontSize: '14px', fontWeight: '500',
                        backgroundColor: '#fef2f2', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '6px' }}
                      data-testid="cleanup-button">
                      <Trash2 style={{ width: '16px', height: '16px' }} /> Limpieza
                    </button>
                  )}
                </div>
              </div>
            </div>
            {loading ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
            ) : filteredWithdrawals.length === 0 ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}><p style={{ color: '#6b7280' }}>No hay retiros</p></div>
            ) : (
              <div style={{ ...cardStyle, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead style={{ backgroundColor: '#f8f9fa' }}>
                      <tr>
                        {['ID', 'Fecha', 'Beneficiario', 'Monto', 'Imágenes', 'Estado', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredWithdrawals.map((w) => {
                        const pendingImgCount = w.pending_images?.length || 0;
                        const proofImgCount = w.proof_images?.length || (w.proof_image ? 1 : 0);
                        const totalImages = w.status === 'pending' ? pendingImgCount : proofImgCount;
                        
                        return (
                        <tr key={w.transaction_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`withdrawal-${w.transaction_id}`}>
                          <td style={{ padding: '16px' }}>
                            <span style={{ fontSize: '13px', fontFamily: 'monospace', fontWeight: '600', color: '#6366f1', backgroundColor: '#eef2ff', padding: '4px 8px', borderRadius: '6px' }}>
                              {w.display_id || w.transaction_id?.slice(0, 8)}
                            </span>
                          </td>
                          <td style={{ padding: '16px', fontSize: '14px', color: '#6b7280' }}>{new Date(w.created_at).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'America/Caracas' })}</td>
                          <td style={{ padding: '16px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#1A1A2E', margin: 0 }}>{w.beneficiary_data?.full_name}</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                              {w.beneficiary_data?.bank}
                            </p>
                            {(w.beneficiary_data?.account_number || w.beneficiary_data?.phone) && (
                              <p style={{ fontSize: '11px', color: '#8E8E9A', margin: '2px 0 0 0', fontFamily: 'monospace', letterSpacing: '0.02em' }}>
                                {formatAccountNumber(w.beneficiary_data?.account_number || w.beneficiary_data?.phone) || (w.beneficiary_data?.account_number || w.beneficiary_data?.phone)}
                              </p>
                            )}
                          </td>
                          <td style={{ padding: '16px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{fmt(w.amount_input)} RIS</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{fmt(w.amount_output)} VES</p>
                          </td>
                          <td style={{ padding: '16px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ 
                                fontSize: '13px', 
                                fontWeight: '600', 
                                color: totalImages > 0 ? '#16a34a' : '#9ca3af',
                                backgroundColor: totalImages > 0 ? '#dcfce7' : '#f3f4f6',
                                padding: '4px 10px', 
                                borderRadius: '20px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px'
                              }}>
                                📷 {totalImages}
                              </span>
                              {w.status === 'pending' && pendingImgCount > 0 && (
                                <span style={{ fontSize: '11px', color: '#d97706', fontWeight: '500' }}>pendiente</span>
                              )}
                            </div>
                          </td>
                          <td style={{ padding: '16px' }}><StatusBadge status={w.status} /></td>
                          <td style={{ padding: '16px' }}>
                            {w.status === 'pending' && (
                              <div style={{ display: 'flex', gap: '8px' }}>
                                <button onClick={() => { setSelectedItem(w); setProofImages(w.pending_images || []); setShowProcessModal(true); }} style={btnSuccess}>Procesar</button>
                                <button onClick={() => handleRejectWithdrawal(w.transaction_id)} style={btnDanger}>Rechazar</button>
                              </div>
                            )}
                            {w.status === 'completed' && proofImgCount > 0 && (
                              <button onClick={() => { 
                                setSelectedItem(w); 
                                // Load images from proof_images array or fallback to single proof_image
                                const images = w.proof_images?.length > 0 ? w.proof_images.map(convertTwilioUrl) : (w.proof_image ? [convertTwilioUrl(w.proof_image)] : []);
                                setProofImages(images);
                                setShowProcessModal(true); 
                              }} style={{ ...btnSecondary, fontSize: '12px', padding: '6px 12px' }}>
                                Ver {proofImgCount} img
                              </button>
                            )}
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Recharges Tab */}
        {/* Recharges VES Tab */}
        {activeTab === 'recharges' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ ...cardStyle, padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>Recargas VES Pendientes</h3>
              <button onClick={loadData} style={{ padding: '8px 16px', borderRadius: '10px', border: 'none', backgroundColor: '#dbeafe', color: '#2563eb', fontSize: '14px', fontWeight: '500', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <RefreshCw style={{ width: '14px', height: '14px' }} />
                Actualizar
              </button>
            </div>

            {loading ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
            ) : recharges.length === 0 ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: '#f3f4f6', margin: '0 auto 16px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <ArrowDownLeft style={{ width: '28px', height: '28px', color: '#9ca3af' }} />
                </div>
                <p style={{ color: '#6b7280', margin: 0 }}>No hay recargas VES pendientes</p>
              </div>
            ) : (
              recharges.map((r) => {
                const legacyMap = {
                  banco_venezuela: 'Banco de Venezuela',
                  banesco: 'Banesco',
                  mercantil: 'Mercantil',
                  provincial: 'Provincial',
                };
                const destBankLabel = r.destination_bank_name || legacyMap[r.destination_bank] || r.destination_bank || '—';
                const hasBankResolved = !!r.destination_bank_id;
                const dt = new Date(r.created_at);
                const dateStr = dt.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'America/Caracas' });
                const timeStr = dt.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit', hour12: true, timeZone: 'America/Caracas' });
                return (
                  <div key={r.transaction_id} style={{ backgroundColor: '#fff', borderRadius: '16px', padding: '18px', border: '1px solid #e5e7eb', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }} data-testid={`recharge-${r.transaction_id}`}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '14px', gap: '12px' }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: '15px', fontWeight: '700', color: '#111827', margin: 0 }}>{r.user_name || r.user_email}</p>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{r.user_email}</p>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px', fontSize: '11px', color: '#9ca3af' }}>
                          <span>{dateStr}</span>
                          <span>•</span>
                          <span>{timeStr}</span>
                          <span>•</span>
                          <span style={{ color: '#6366f1', fontWeight: '600' }}>Caracas</span>
                        </div>
                      </div>
                      <StatusBadge status="pending" />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr', gap: '10px', marginBottom: '12px' }}>
                      {r.proof_image && (
                        <a href={r.proof_image} target="_blank" rel="noreferrer" style={{ display: 'block', width: '96px', height: '96px', borderRadius: '10px', overflow: 'hidden', border: '1px solid #e5e7eb', cursor: 'zoom-in' }}>
                          <img src={r.proof_image} alt="Comprobante" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        </a>
                      )}
                      <div style={{ padding: '12px', backgroundColor: '#dbeafe', borderRadius: '10px' }}>
                        <p style={{ fontSize: '10px', color: '#2563eb', margin: 0, fontWeight: '700', letterSpacing: '0.5px' }}>PAGÓ EN</p>
                        <p style={{ fontSize: '18px', fontWeight: '700', color: '#1e3a5f', margin: '2px 0 0 0' }}>{fmt(parseFloat(r.amount_ves || r.amount_input || 0))} VES</p>
                        <p style={{ fontSize: '11px', color: '#6b7280', margin: '4px 0 0 0' }}>Banco: <strong>{destBankLabel}</strong></p>
                      </div>
                      <div style={{ padding: '12px', backgroundColor: '#dcfce7', borderRadius: '10px' }}>
                        <p style={{ fontSize: '10px', color: '#16a34a', margin: 0, fontWeight: '700', letterSpacing: '0.5px' }}>A ACREDITAR</p>
                        <p style={{ fontSize: '18px', fontWeight: '700', color: '#166534', margin: '2px 0 0 0' }}>{fmt(parseFloat(r.amount_ris || r.amount_output || 0))} RI$</p>
                        <p style={{ fontSize: '11px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa: 1 RIS = {fmt(r.rate_used || 140)} VES</p>
                      </div>
                    </div>

                    {!hasBankResolved && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px', backgroundColor: '#fef3c7', borderRadius: '10px', marginBottom: '10px', fontSize: '12px', color: '#92400e' }}>
                        <AlertCircle style={{ width: '16px', height: '16px', flexShrink: 0 }} />
                        <span>El banco no está vinculado a Contabilidad. Verifica que existe en Contabilidad → Bancos antes de aprobar.</span>
                      </div>
                    )}

                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={() => handleApproveRechargeVES(r.transaction_id)}
                        style={{ flex: 1, padding: '12px', borderRadius: '10px', border: 'none', backgroundColor: '#16a34a', color: '#fff', fontSize: '13px', fontWeight: '700', cursor: 'pointer' }}
                        data-testid={`approve-recharge-${r.transaction_id}`}
                      >Aprobar</button>
                      <button
                        onClick={() => handleRejectRechargeVES(r.transaction_id)}
                        style={{ flex: 1, padding: '12px', borderRadius: '10px', border: 'none', backgroundColor: '#dc2626', color: '#fff', fontSize: '13px', fontWeight: '700', cursor: 'pointer' }}
                        data-testid={`reject-recharge-${r.transaction_id}`}
                      >Rechazar</button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Partners Tab - Socios y Gestores */}
        {activeTab === 'partners' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Sub-tabs for Socios / Gestores */}
            <div style={{ ...cardStyle, padding: '16px' }}>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                <button 
                  onClick={() => setPartnerTab('socios')}
                  style={{ 
                    flex: 1, padding: '14px', borderRadius: '12px', border: 'none', cursor: 'pointer',
                    backgroundColor: partnerTab === 'socios' ? '#7c3aed' : '#f3f4f6',
                    color: partnerTab === 'socios' ? '#ffffff' : '#374151',
                    fontWeight: '600', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                  }}
                  data-testid="partner-tab-socios"
                >
                  <Gift style={{ width: '18px', height: '18px' }} />
                  Socios Referidos ({partners.length})
                </button>
                <button 
                  onClick={() => setPartnerTab('gestores')}
                  style={{ 
                    flex: 1, padding: '14px', borderRadius: '12px', border: 'none', cursor: 'pointer',
                    backgroundColor: partnerTab === 'gestores' ? '#059669' : '#f3f4f6',
                    color: partnerTab === 'gestores' ? '#ffffff' : '#374151',
                    fontWeight: '600', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                  }}
                  data-testid="partner-tab-gestores"
                >
                  <Briefcase style={{ width: '18px', height: '18px' }} />
                  Socios Gestores ({gestors.length})
                </button>
              </div>
              
              {/* Search */}
              <div style={{ position: 'relative' }}>
                <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                <input 
                  type="text" 
                  placeholder={`Buscar ${partnerTab === 'socios' ? 'socio' : 'gestor'}...`}
                  value={partnerSearchQuery} 
                  onChange={(e) => setPartnerSearchQuery(e.target.value)}
                  style={{ width: '100%', padding: '12px 12px 12px 40px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '14px', outline: 'none', boxSizing: 'border-box' }} 
                />
              </div>
            </div>

            {/* Socios List */}
            {partnerTab === 'socios' && (
              <div style={{ ...cardStyle, overflow: 'hidden' }}>
                {loading ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
                ) : partners.filter(p => !partnerSearchQuery || p.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || p.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).length === 0 ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}>
                    <Gift style={{ width: '48px', height: '48px', color: '#d1d5db', margin: '0 auto 16px' }} />
                    <p style={{ color: '#6b7280', margin: 0 }}>No hay socios registrados</p>
                    <p style={{ color: '#9ca3af', fontSize: '13px', margin: '8px 0 0 0' }}>Asigna el rol Socio desde la pestaña de usuarios</p>
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead style={{ backgroundColor: '#faf5ff' }}>
                        <tr>
                          {['Socio', 'Código', 'Referidos', 'Total Ganancias', 'Este Mes', 'Estado'].map(h => (
                            <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#7c3aed', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {partners.filter(p => !partnerSearchQuery || p.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || p.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).map((p) => (
                          <tr key={p.user_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`partner-${p.user_id}`}>
                            <td style={{ padding: '16px' }}>
                              <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{p.name}</p>
                              <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{p.email}</p>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ fontSize: '13px', fontFamily: 'monospace', fontWeight: '600', color: '#7c3aed', backgroundColor: '#f5f3ff', padding: '4px 10px', borderRadius: '6px' }}>
                                {p.referral_code || 'N/A'}
                              </span>
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {p.referrals_count || 0}
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {fmt((p.total_earnings || 0))} RIS
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#16a34a' }}>
                              +{fmt((p.month_earnings || 0))} RIS
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600', backgroundColor: '#dcfce7', color: '#16a34a' }}>
                                Activo
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Gestores List */}
            {partnerTab === 'gestores' && (
              <div style={{ ...cardStyle, overflow: 'hidden' }}>
                {loading ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
                ) : gestors.filter(g => !partnerSearchQuery || g.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || g.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).length === 0 ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}>
                    <Briefcase style={{ width: '48px', height: '48px', color: '#d1d5db', margin: '0 auto 16px' }} />
                    <p style={{ color: '#6b7280', margin: 0 }}>No hay gestores registrados</p>
                    <p style={{ color: '#9ca3af', fontSize: '13px', margin: '8px 0 0 0' }}>Asigna el rol Socio Gestor desde la pestaña de usuarios</p>
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead style={{ backgroundColor: '#ecfdf5' }}>
                        <tr>
                          {['Gestor', 'Código', 'Transacciones', 'Volumen Total', 'Saldo Terceros', 'Estado'].map(h => (
                            <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#059669', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {gestors.filter(g => !partnerSearchQuery || g.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || g.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).map((g) => (
                          <tr key={g.user_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`gestor-${g.user_id}`}>
                            <td style={{ padding: '16px' }}>
                              <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{g.name}</p>
                              <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{g.email}</p>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ fontSize: '13px', fontFamily: 'monospace', fontWeight: '600', color: '#059669', backgroundColor: '#ecfdf5', padding: '4px 10px', borderRadius: '6px' }}>
                                {g.gestor_code || 'N/A'}
                              </span>
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {g.total_transactions || 0}
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {fmt((g.total_volume || 0))} RIS
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ fontSize: '14px', fontWeight: '700', color: '#059669' }}>
                                {fmt((g.balance_ris_terceros || 0))} RIS
                              </span>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600', backgroundColor: '#dcfce7', color: '#16a34a' }}>
                                Activo
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Search bar */}
            <div style={{ ...cardStyle, padding: '16px' }}>
              <div style={{ position: 'relative' }}>
                <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                <input 
                  type="text" 
                  placeholder="Buscar usuario por nombre o email..." 
                  value={userSearchQuery} 
                  onChange={(e) => setUserSearchQuery(e.target.value)}
                  style={{ width: '100%', padding: '12px 12px 12px 40px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '14px', outline: 'none' }} 
                />
              </div>
            </div>

            {/* Users List */}
            <div style={{ ...cardStyle, overflow: 'hidden' }}>
              {loading ? (
                <div style={{ padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
              ) : filteredUsers.length === 0 ? (
                <div style={{ padding: '48px', textAlign: 'center' }}><p style={{ color: '#6b7280' }}>No se encontraron usuarios</p></div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead style={{ backgroundColor: '#f8f9fa' }}>
                      <tr>
                        {['Usuario', 'Balance', 'Estado', 'Rol', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredUsers.map((u) => (
                        <tr key={u.user_id} style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer', transition: 'background 0.2s' }} 
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f9fafb'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                            data-testid={`user-${u.user_id}`}>
                          <td style={{ padding: '16px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{u.name}</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{u.email}</p>
                          </td>
                          <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>{fmt(u.balance_ris)} RIS</td>
                          <td style={{ padding: '16px' }}>
                            <span style={{ padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600',
                              backgroundColor: u.verification_status === 'verified' ? '#dcfce7' : '#f3f4f6',
                              color: u.verification_status === 'verified' ? '#16a34a' : '#6b7280' }}>
                              {u.verification_status === 'verified' ? 'Verificado' : 'Pendiente'}
                            </span>
                          </td>
                          <td style={{ padding: '16px', fontSize: '14px', color: '#6b7280' }}>
                            <span style={{ 
                              padding: '4px 10px', 
                              borderRadius: '8px', 
                              fontSize: '12px', 
                              fontWeight: '600',
                              backgroundColor: u.role === 'socio' ? '#ede9fe' : u.role === 'socio_gestor' ? '#d1fae5' : '#f3f4f6',
                              color: u.role === 'socio' ? '#7c3aed' : u.role === 'socio_gestor' ? '#059669' : '#6b7280'
                            }}>
                              {u.role === 'socio' ? '🎁 Socio' : u.role === 'socio_gestor' ? '🏪 Gestor' : '👤 Usuario'}
                            </span>
                          </td>
                          <td style={{ padding: '16px', display: 'flex', gap: '8px' }}>
                            <button 
                              onClick={() => loadUserHistory(u.user_id)}
                              style={{ 
                                display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                backgroundColor: '#dbeafe', color: '#2563eb', border: 'none',
                                borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                              }}
                              data-testid={`view-user-${u.user_id}`}
                            >
                              <Eye style={{ width: '14px', height: '14px' }} />
                              Ver
                            </button>
                            {u.user_id !== user.user_id && (
                              <button 
                                onClick={() => { setSelectedUserForRole(u); setShowRoleModal(true); }}
                                style={{ 
                                  display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                  backgroundColor: '#fef3c7', color: '#d97706', border: 'none',
                                  borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                                }}
                                data-testid={`change-role-${u.user_id}`}
                              >
                                <UserCog style={{ width: '14px', height: '14px' }} />
                                Rol
                              </button>
                            )}
                            {u.user_id !== user.user_id && (
                              <button 
                                onClick={() => handleResetPassword(u.user_id, u.name)}
                                style={{ 
                                  display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                  backgroundColor: '#fee2e2', color: '#dc2626', border: 'none',
                                  borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                                }}
                                data-testid={`reset-password-${u.user_id}`}
                              >
                                <KeyRound style={{ width: '14px', height: '14px' }} />
                                Clave
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* KYC Tab (new modular panel: tabs, search, lightbox, audit log, reject reasons) */}
        {activeTab === 'kyc' && (
          <KycPanel onChange={refreshKycStats} />
        )}

        {/* Rates Tab */}
        {activeTab === 'rates' && (
          <div style={{ maxWidth: '700px' }}>
            <div style={{ ...cardStyle, padding: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 24px 0' }}>Configurar Tasas de Cambio</h3>
              
              {/* Current Rates Display */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
                <div style={{ padding: '20px', backgroundColor: '#dbeafe', borderRadius: '14px' }}>
                  <p style={{ fontSize: '12px', color: '#2563eb', margin: '0 0 4px 0', fontWeight: '600' }}>ENVÍOS (RIS → VES)</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>1 RIS = {fmt(rates?.ris_to_ves) || '110.00'} VES</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para retiros a Venezuela</p>
                </div>
                <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                  <p style={{ fontSize: '12px', color: '#16a34a', margin: '0 0 4px 0', fontWeight: '600' }}>RECARGAS VES (VES → RIS)</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>{fmt(rates?.ves_to_ris_rate) || '140.00'} VES = 1 RIS</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para recargas con Bolívares</p>
                </div>
              </div>
              
              {/* BRL Rate Display */}
              <div style={{ padding: '20px', backgroundColor: '#fef9c3', borderRadius: '14px', marginBottom: '24px' }}>
                <p style={{ fontSize: '12px', color: '#ca8a04', margin: '0 0 4px 0', fontWeight: '600' }}>RECARGAS PIX (BRL → RIS)</p>
                <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>1 BRL = {fmt(rates?.brl_to_ris) || '1.00'} RIS</p>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para recargas con PIX Brasil</p>
              </div>

              {/* Update Rates Form - Independent */}
              <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: '24px' }}>
                <h4 style={{ fontSize: '16px', fontWeight: '600', color: '#374151', margin: '0 0 16px 0' }}>Actualizar Tasas</h4>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                  {/* RIS → VES Rate */}
                  <div style={{ padding: '20px', backgroundColor: '#f0f9ff', borderRadius: '14px', border: '1px solid #bfdbfe' }}>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#2563eb', marginBottom: '12px' }}>
                      RIS → VES (Envíos)
                    </label>
                    <input 
                      type="number" 
                      value={newRate} 
                      onChange={(e) => setNewRate(e.target.value)}
                      style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
                      placeholder={rates?.ris_to_ves?.toString() || '0'} 
                      data-testid="new-rate-input" 
                    />
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 12px 0' }}>VES por cada 1 RIS enviado</p>
                    <button 
                      onClick={handleUpdateRate} 
                      style={{ ...btnPrimary, width: '100%', height: '44px', backgroundColor: '#2563eb' }} 
                      data-testid="update-rate-button"
                    >
                      Actualizar RIS → VES
                    </button>
                  </div>

                  {/* VES → RIS Rate */}
                  <div style={{ padding: '20px', backgroundColor: '#f0fdf4', borderRadius: '14px', border: '1px solid #bbf7d0' }}>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#16a34a', marginBottom: '12px' }}>
                      VES → RIS (Recargas)
                    </label>
                    <input 
                      type="number" 
                      value={newRateVesToRis} 
                      onChange={(e) => setNewRateVesToRis(e.target.value)}
                      style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
                      placeholder={rates?.ves_to_ris?.toString() || '0'} 
                      data-testid="new-rate-ves-input" 
                    />
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 12px 0' }}>VES necesarios para obtener 1 RIS</p>
                    <button 
                      onClick={handleUpdateRateVesToRis} 
                      style={{ ...btnPrimary, width: '100%', height: '44px', backgroundColor: '#16a34a' }} 
                      data-testid="update-rate-ves-button"
                    >
                      Actualizar VES → RIS
                    </button>
                  </div>
                </div>
                
                {/* BRL → RIS Rate Form */}
                <div style={{ marginTop: '24px', padding: '20px', backgroundColor: '#fefce8', borderRadius: '14px', border: '1px solid #fde68a' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#ca8a04', marginBottom: '12px' }}>
                    BRL → RIS (Recargas PIX)
                  </label>
                  <input 
                    type="number" 
                    step="0.01"
                    value={newRateBrlToRis} 
                    onChange={(e) => setNewRateBrlToRis(e.target.value)}
                    style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
                    placeholder={rates?.brl_to_ris?.toString() || '1'} 
                    data-testid="new-rate-brl-input" 
                  />
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 12px 0' }}>RIS que recibirá por cada 1 BRL pagado</p>
                  <button 
                    onClick={handleUpdateRateBrlToRis} 
                    style={{ ...btnPrimary, width: '100%', height: '44px', backgroundColor: '#ca8a04' }} 
                    data-testid="update-rate-brl-button"
                  >
                    Actualizar BRL → RIS
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <div style={{ padding: '0', display: 'flex', gap: '24px', height: 'calc(100vh - 200px)', minHeight: '500px' }}>
            {/* Chat List */}
            <div style={{ width: '320px', backgroundColor: '#fff', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb' }}>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: '700', color: '#1f2937' }}>Conversaciones</h3>
              </div>
              <div style={{ flex: 1, overflowY: 'auto' }}>
                {supportChats.length === 0 ? (
                  <div style={{ padding: '40px 20px', textAlign: 'center', color: '#9ca3af' }}>
                    <MessageSquare style={{ width: '48px', height: '48px', margin: '0 auto 12px', opacity: 0.5 }} />
                    <p style={{ fontSize: '14px' }}>No hay conversaciones</p>
                  </div>
                ) : (
                  supportChats.map(chat => (
                    <div
                      key={chat.user_id}
                      onClick={async () => {
                        setSelectedChat(chat);
                        try {
                          const res = await api.get(`/admin/support/chat/${chat.user_id}`);
                          setChatMessages(res.data || []);
                        } catch (e) {
                          console.error(e);
                        }
                      }}
                      style={{
                        padding: '16px 20px',
                        borderBottom: '1px solid #f3f4f6',
                        cursor: 'pointer',
                        backgroundColor: selectedChat?.user_id === chat.user_id ? '#f0f9ff' : 'transparent',
                        borderLeft: selectedChat?.user_id === chat.user_id ? '3px solid #6366f1' : '3px solid transparent'
                      }}
                      data-testid={`chat-item-${chat.user_id}`}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                        <span style={{ fontWeight: '600', fontSize: '14px', color: '#1f2937' }}>{chat.user_name || 'Usuario'}</span>
                        {chat.unread_count > 0 && (
                          <span style={{ backgroundColor: '#ef4444', color: 'white', borderRadius: '10px', padding: '2px 8px', fontSize: '11px', fontWeight: '700' }}>
                            {chat.unread_count}
                          </span>
                        )}
                      </div>
                      <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>{chat.user_email}</p>
                      <p style={{ fontSize: '13px', color: '#9ca3af', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {chat.last_message?.substring(0, 40)}...
                      </p>
                      <p style={{ fontSize: '11px', color: '#9ca3af', margin: '4px 0 0 0' }}>
                        {chat.last_message_at ? new Date(chat.last_message_at).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Caracas' }) : ''}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Chat Messages */}
            <div style={{ flex: 1, backgroundColor: '#fff', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              {!selectedChat ? (
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af' }}>
                  <div style={{ textAlign: 'center' }}>
                    <MessageSquare style={{ width: '64px', height: '64px', margin: '0 auto 16px', opacity: 0.3 }} />
                    <p style={{ fontSize: '16px' }}>Selecciona una conversación</p>
                  </div>
                </div>
              ) : (
                <>
                  {/* Chat Header */}
                  <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: '#1f2937' }}>{selectedChat.user_name}</h3>
                      <p style={{ margin: '2px 0 0 0', fontSize: '13px', color: '#6b7280' }}>{selectedChat.user_email}</p>
                    </div>
                    <button
                      onClick={async () => {
                        try {
                          await api.post('/admin/support/close', { user_id: selectedChat.user_id });
                          toast.success('Chat cerrado');
                          loadData();
                          setSelectedChat(null);
                        } catch (e) {
                          toast.error('Error al cerrar chat');
                        }
                      }}
                      style={{ padding: '8px 16px', borderRadius: '10px', border: 'none', backgroundColor: '#fee2e2', color: '#dc2626', fontSize: '13px', fontWeight: '600', cursor: 'pointer' }}
                    >
                      Cerrar Chat
                    </button>
                  </div>

                  {/* Messages */}
                  <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '12px', backgroundColor: '#f9fafb' }}>
                    {chatMessages.map(msg => (
                      <div
                        key={msg.message_id}
                        style={{
                          alignSelf: msg.sender === 'admin' ? 'flex-end' : 'flex-start',
                          maxWidth: '70%'
                        }}
                      >
                        <div style={{
                          padding: '12px 16px',
                          borderRadius: msg.sender === 'admin' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                          backgroundColor: msg.sender === 'admin' ? '#6366f1' : 'white',
                          color: msg.sender === 'admin' ? 'white' : '#1f2937',
                          boxShadow: msg.sender === 'user' ? '0 2px 8px rgba(0,0,0,0.08)' : 'none'
                        }}>
                          <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.4', whiteSpace: 'pre-wrap' }}>{msg.message}</p>
                        </div>
                        <p style={{ fontSize: '10px', color: '#9ca3af', margin: '4px 8px 0', textAlign: msg.sender === 'admin' ? 'right' : 'left' }}>
                          {new Date(msg.created_at).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>
                    ))}
                  </div>

                  {/* Reply Input */}
                  <div style={{ padding: '16px 20px', borderTop: '1px solid #e5e7eb', display: 'flex', gap: '12px' }}>
                    <input
                      type="text"
                      value={chatReply}
                      onChange={(e) => setChatReply(e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter' && chatReply.trim()) {
                          api.post('/admin/support/respond', { user_id: selectedChat.user_id, message: chatReply.trim() })
                            .then(async () => {
                              setChatReply('');
                              const res = await api.get(`/admin/support/chat/${selectedChat.user_id}`);
                              setChatMessages(res.data || []);
                              toast.success('Respuesta enviada');
                            })
                            .catch(() => toast.error('Error al enviar'));
                        }
                      }}
                      placeholder="Escribe tu respuesta..."
                      style={{ flex: 1, padding: '14px 18px', borderRadius: '24px', border: '1px solid #e5e7eb', fontSize: '14px', outline: 'none' }}
                      data-testid="admin-chat-reply-input"
                    />
                    <button
                      onClick={async () => {
                        if (!chatReply.trim()) return;
                        try {
                          await api.post('/admin/support/respond', { user_id: selectedChat.user_id, message: chatReply.trim() });
                          setChatReply('');
                          const res = await api.get(`/admin/support/chat/${selectedChat.user_id}`);
                          setChatMessages(res.data || []);
                          toast.success('Respuesta enviada');
                        } catch (e) {
                          toast.error('Error al enviar');
                        }
                      }}
                      style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#6366f1', border: 'none', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      data-testid="admin-chat-send-btn"
                    >
                      <Send style={{ width: '20px', height: '20px' }} />
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Support Requests Tab */}
        {activeTab === 'support' && (
          <div style={{ padding: '0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#1f2937', margin: 0 }}>
                Solicitudes de Soporte
              </h2>
              <div style={{ display: 'flex', gap: '8px' }}>
                {['pending', 'resolved', 'all'].map(filter => (
                  <button 
                    key={filter}
                    onClick={() => setSupportFilter(filter)}
                    style={{ 
                      padding: '8px 16px', 
                      borderRadius: '10px', 
                      border: 'none', 
                      fontSize: '14px', 
                      fontWeight: '600',
                      cursor: 'pointer',
                      backgroundColor: supportFilter === filter ? '#6366f1' : '#f3f4f6',
                      color: supportFilter === filter ? '#fff' : '#6b7280'
                    }}
                    data-testid={`support-filter-${filter}`}
                  >
                    {filter === 'pending' ? 'Pendientes' : filter === 'resolved' ? 'Resueltas' : 'Todas'}
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <RefreshCw className="animate-spin" style={{ width: '32px', height: '32px', color: '#6366f1' }} />
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {supportRequests
                  .filter(req => supportFilter === 'all' || req.status === supportFilter)
                  .map((request) => (
                    <div 
                      key={request.support_id} 
                      style={{ 
                        padding: '20px', 
                        backgroundColor: '#fff', 
                        borderRadius: '16px', 
                        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                        border: request.status === 'pending' ? '2px solid #fbbf24' : '1px solid #e5e7eb'
                      }}
                      data-testid={`support-request-${request.support_id}`}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                            <span style={{ 
                              padding: '4px 10px', 
                              borderRadius: '20px', 
                              fontSize: '12px', 
                              fontWeight: '600',
                              backgroundColor: request.status === 'pending' ? '#fef3c7' : '#dcfce7',
                              color: request.status === 'pending' ? '#b45309' : '#16a34a'
                            }}>
                              {request.status === 'pending' ? 'Pendiente' : 'Resuelta'}
                            </span>
                            <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                              {request.support_id}
                            </span>
                          </div>
                          <h4 style={{ fontSize: '16px', fontWeight: '600', color: '#1f2937', margin: '8px 0 4px 0' }}>
                            {request.subject}
                          </h4>
                        </div>
                        {request.status === 'pending' && (
                          <button
                            onClick={async () => {
                              try {
                                await api.post(`/admin/support-requests/${request.support_id}/resolve`);
                                toast.success('Solicitud marcada como resuelta');
                                loadData();
                              } catch (error) {
                                toast.error('Error al marcar como resuelta');
                              }
                            }}
                            style={{ 
                              padding: '8px 16px', 
                              borderRadius: '10px', 
                              border: 'none', 
                              backgroundColor: '#16a34a', 
                              color: '#fff', 
                              fontSize: '14px', 
                              fontWeight: '600',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px'
                            }}
                            data-testid={`resolve-support-${request.support_id}`}
                          >
                            <CheckCircle style={{ width: '16px', height: '16px' }} />
                            Marcar Resuelta
                          </button>
                        )}
                      </div>
                      
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Mail style={{ width: '16px', height: '16px', color: '#6b7280' }} />
                          <span style={{ fontSize: '14px', color: '#374151' }}>{request.email}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Phone style={{ width: '16px', height: '16px', color: '#6b7280' }} />
                          <span style={{ fontSize: '14px', color: '#374151' }}>{request.phone_number || 'No proporcionado'}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Clock style={{ width: '16px', height: '16px', color: '#6b7280' }} />
                          <span style={{ fontSize: '14px', color: '#374151' }}>
                            {new Date(request.created_at).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Caracas' })}
                          </span>
                        </div>
                      </div>
                      
                      <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '10px' }}>
                        <p style={{ fontSize: '14px', color: '#4b5563', margin: 0, lineHeight: '1.5' }}>
                          {request.message}
                        </p>
                      </div>
                    </div>
                  ))}
                
                {supportRequests.filter(req => supportFilter === 'all' || req.status === supportFilter).length === 0 && (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>
                    <MessageSquare style={{ width: '48px', height: '48px', margin: '0 auto 12px', opacity: 0.5 }} />
                    <p style={{ fontSize: '16px', fontWeight: '500' }}>No hay solicitudes {supportFilter === 'pending' ? 'pendientes' : supportFilter === 'resolved' ? 'resueltas' : ''}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      
      {/* BTC Orders Tab */}
      {activeTab === 'btc' && (
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>⚡ Órdenes BTC Pendientes</h2>
              <p style={{ color: '#6b7280', fontSize: '14px', margin: '4px 0 0' }}>Órdenes que requieren transferencia manual al beneficiario</p>
            </div>
            <button onClick={fetchBtcOrdenesPendientes} disabled={loadingBtcOrdenes}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', background: '#f59e0b', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: '700', cursor: 'pointer', fontSize: '14px', opacity: loadingBtcOrdenes ? 0.7 : 1 }}>
              {loadingBtcOrdenes ? '⏳ Cargando...' : '🔄 Actualizar'}
            </button>
          </div>

          {btcOrdenesP.length === 0 && !loadingBtcOrdenes ? (
            <div style={{ background: '#f9fafb', border: '1px dashed #d1d5db', borderRadius: '16px', padding: '48px', textAlign: 'center' }}>
              <p style={{ fontSize: '48px', margin: '0 0 12px' }}>✅</p>
              <h3 style={{ color: '#374151', fontWeight: '700', margin: '0 0 8px' }}>No hay órdenes pendientes</h3>
              <p style={{ color: '#9ca3af', fontSize: '14px', margin: 0 }}>Todas las órdenes BTC han sido procesadas</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {btcOrdenesP.map((orden) => (
                <div key={orden.remesa_id} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '16px', padding: '20px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
                    <div>
                      <span style={{ background: '#fef3c7', color: '#d97706', padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: '700' }}>💰 PAGADO - PENDIENTE ENVÍO</span>
                      <p style={{ margin: '8px 0 0', fontSize: '13px', color: '#9ca3af', fontFamily: 'monospace' }}>ID: {orden.remesa_id}</p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <p style={{ fontWeight: '800', fontSize: '18px', color: '#111827', margin: 0 }}>{Number(orden.ves_recibe || 0).toLocaleString('es-VE', { minimumFractionDigits: 2 })} Bs</p>
                      <p style={{ color: '#6b7280', fontSize: '13px', margin: '2px 0 0' }}>{Number(orden.usd_cliente || 0).toFixed(2)} USD · {Number(orden.sats || 0).toLocaleString()} sats</p>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                    <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '12px', padding: '14px' }}>
                      <p style={{ fontSize: '11px', fontWeight: '700', color: '#166534', margin: '0 0 6px', letterSpacing: '0.05em' }}>BENEFICIARIO</p>
                      <p style={{ fontWeight: '700', color: '#111827', margin: '0 0 2px', fontSize: '15px' }}>{orden.beneficiario_data?.full_name || 'N/A'}</p>
                      <p style={{ color: '#374151', fontSize: '13px', margin: '0 0 2px' }}>CI: {orden.beneficiario_data?.cedula || 'N/A'}</p>
                      <p style={{ color: '#374151', fontSize: '13px', margin: 0 }}>
                        {orden.beneficiario_data?.payment_type === 'pago_movil' ? '📱 Pago Móvil' : '🏦 Transferencia'}
                      </p>
                    </div>
                    <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '12px', padding: '14px' }}>
                      <p style={{ fontSize: '11px', fontWeight: '700', color: '#1e40af', margin: '0 0 6px', letterSpacing: '0.05em' }}>DATOS PAGO</p>
                      {orden.beneficiario_data?.payment_type === 'pago_movil' ? (
                        <>
                          <p style={{ fontWeight: '600', color: '#111827', margin: '0 0 2px', fontSize: '14px' }}>📱 {orden.beneficiario_data?.phone || 'N/A'}</p>
                          <p style={{ color: '#374151', fontSize: '13px', margin: 0 }}>{orden.beneficiario_data?.bank || 'N/A'}</p>
                        </>
                      ) : (
                        <>
                          <p style={{ fontWeight: '600', color: '#111827', margin: '0 0 2px', fontSize: '14px' }}>🏦 {orden.beneficiario_data?.bank || 'N/A'}</p>
                          <p style={{ color: '#374151', fontSize: '13px', margin: 0, fontFamily: 'monospace' }}>{orden.beneficiario_data?.account_number || 'N/A'}</p>
                        </>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <p style={{ color: '#9ca3af', fontSize: '12px', margin: 0 }}>
                      📅 {orden.creado_en ? new Date(orden.creado_en).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                    </p>
                    <button onClick={() => handleMarcarBtcEnviado(orden.remesa_id)} disabled={marcandoBtc === orden.remesa_id}
                      style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', background: marcandoBtc === orden.remesa_id ? '#9ca3af' : '#10b981', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: '700', cursor: marcandoBtc === orden.remesa_id ? 'not-allowed' : 'pointer', fontSize: '14px' }}>
                      {marcandoBtc === orden.remesa_id ? '⏳ Procesando...' : '✅ Marcar como Enviado'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
</main>

      {/* Process Withdrawal Modal */}
      {showProcessModal && selectedItem && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', width: '100%', maxWidth: '550px', maxHeight: '90vh', overflow: 'auto' }}>
            <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: '0 0 20px 0' }}>
              {selectedItem.status === 'completed' ? 'Ver Comprobantes' : 'Procesar Retiro'}
            </h3>
            <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Beneficiario</p>
                  <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>{selectedItem.beneficiary_data?.full_name}</p>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 4px 0' }}>{selectedItem.beneficiary_data?.bank}</p>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: '0' }}>{selectedItem.beneficiary_data?.account_number}</p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>ID</p>
                  <p style={{ fontSize: '14px', fontWeight: '600', fontFamily: 'monospace', color: '#6366f1', margin: 0 }}>
                    {selectedItem.display_id || selectedItem.transaction_id?.slice(0, 8)}
                  </p>
                </div>
              </div>
              <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#dbeafe', borderRadius: '10px' }}>
                <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0, textAlign: 'center' }}>
                  {fmt(selectedItem.amount_output)} VES
                </p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0', textAlign: 'center' }}>
                  ({fmt(selectedItem.amount_input)} RIS)
                </p>
              </div>
            </div>
            
            {/* Images Section */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '12px' }}>
                <span>📷 Comprobantes de pago ({proofImages.length})</span>
                {selectedItem.status === 'pending' && (
                  <span style={{ fontSize: '12px', color: '#6b7280', fontWeight: '400' }}>Puedes subir múltiples imágenes</span>
                )}
              </label>
              
              {/* Image Grid */}
              {proofImages.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: '12px', marginBottom: '12px' }}>
                  {proofImages.map((img, idx) => (
                    <div key={idx} style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '1px solid #e5e7eb' }}>
                      <img src={img} alt={`Comprobante ${idx + 1}`} style={{ width: '100%', height: '100px', objectFit: 'cover' }} />
                      {selectedItem.status === 'pending' && (
                        <button 
                          onClick={() => removeProofImage(idx)} 
                          style={{ 
                            position: 'absolute', top: '4px', right: '4px', 
                            width: '22px', height: '22px', borderRadius: '50%', 
                            backgroundColor: '#dc2626', color: 'white', border: 'none', 
                            cursor: 'pointer', fontSize: '14px', fontWeight: 'bold',
                            display: 'flex', alignItems: 'center', justifyContent: 'center'
                          }}
                        >
                          ×
                        </button>
                      )}
                      <div style={{ position: 'absolute', bottom: '4px', left: '4px', backgroundColor: 'rgba(0,0,0,0.6)', color: 'white', fontSize: '11px', padding: '2px 6px', borderRadius: '4px' }}>
                        #{idx + 1}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
              {/* Upload Button (only for pending) */}
              {selectedItem.status === 'pending' && (
                <input 
                  type="file" 
                  accept="image/*" 
                  multiple 
                  onChange={handleFileChange} 
                  style={{ width: '100%' }} 
                  data-testid="upload-proof-images"
                />
              )}
              
              {/* Empty state */}
              {proofImages.length === 0 && selectedItem.status === 'completed' && (
                <p style={{ color: '#9ca3af', fontSize: '14px', textAlign: 'center', padding: '20px' }}>No hay imágenes de comprobantes</p>
              )}
            </div>
            
            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => { setShowProcessModal(false); setSelectedItem(null); setProofImages([]); setProcessBankId(''); }} style={{ ...btnSecondary, flex: 1 }}>
                {selectedItem.status === 'completed' ? 'Cerrar' : 'Cancelar'}
              </button>
              {selectedItem.status === 'pending' && (
                <button onClick={handleProcessWithdrawal} disabled={proofImages.length === 0 || !processBankId} style={{ ...btnSuccess, flex: 1, opacity: (proofImages.length > 0 && processBankId) ? 1 : 0.5 }}>
                  Confirmar ({proofImages.length} img)
                </button>
              )}
            </div>
            {selectedItem.status === 'pending' && (
              <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#fef3c7', borderRadius: '10px', border: '1px solid #fcd34d' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: '#92400e', marginBottom: '6px' }}>
                  Banco desde donde se pagó al beneficiario * (obligatorio)
                </label>
                <select value={processBankId} onChange={e => setProcessBankId(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '14px', backgroundColor: '#fff' }}
                  data-testid="process-bank-select"
                >
                  <option value="">-- Seleccionar banco --</option>
                  {accountingBanks.filter(b => b.currency === 'VES').map(b => (
                    <option key={b.bank_id} value={b.bank_id}>
                      {b.name} (Saldo: {fmt(b.balance)} VES)
                    </option>
                  ))}
                </select>
                {accountingBanks.filter(b => b.currency === 'VES').length === 0 && (
                  <p style={{ fontSize: '11px', color: '#991b1b', margin: '6px 0 0 0' }}>
                    No hay bancos VES registrados. Registra uno en Contabilidad antes de aprobar.
                  </p>
                )}
                <p style={{ fontSize: '11px', color: '#78350f', margin: '6px 0 0 0' }}>
                  Si el banco no tiene saldo suficiente, se registrará como déficit y se compensará cuando entre liquidez.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* User History Modal */}
      {selectedUser && (
        <div 
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}
          onClick={closeUserModal}
        >
          <div 
            style={{ backgroundColor: '#ffffff', borderRadius: '24px', width: '100%', maxWidth: '800px', maxHeight: '90vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{ padding: '24px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>{selectedUser.name}</h3>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>{selectedUser.email}</p>
              </div>
              <button onClick={closeUserModal} style={{ width: '36px', height: '36px', borderRadius: '10px', border: 'none', backgroundColor: '#f3f4f6', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {/* Modal Content */}
            <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
              {loadingUser ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px' }}>
                  <RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} />
                </div>
              ) : userHistory ? (
                <>
                  {/* User Stats */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ padding: '16px', backgroundColor: '#f0fdf4', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#16a34a', margin: '0 0 4px 0', fontWeight: '600' }}>BALANCE ACTUAL</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.user?.balance_ris ?? 0))} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#dbeafe', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#2563eb', margin: '0 0 4px 0', fontWeight: '600' }}>TOTAL RECARGADO</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.stats?.total_recharged ?? 0))} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#d97706', margin: '0 0 4px 0', fontWeight: '600' }}>TOTAL ENVIADO</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.stats?.total_withdrawn ?? 0))} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#f3e8ff', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#9333ea', margin: '0 0 4px 0', fontWeight: '600' }}>VES ENVIADOS</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.stats?.total_ves_sent ?? 0))}
                      </p>
                    </div>
                  </div>

                  {/* User Info - COMPLETE REGISTRATION DATA */}
                  <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '24px' }}>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', margin: '0 0 12px 0' }}>DATOS DE REGISTRO COMPLETOS</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Nombre Completo</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{userHistory.user?.full_name || userHistory.user?.name || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Email</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.email || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Teléfono</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.phone_number || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>CPF</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.cpf_number || userHistory.user?.cpf || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>RNM / Documento</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.document_number || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Estado KYC</p>
                        <p style={{ fontSize: '14px', margin: '2px 0 0 0', fontWeight: '600', color: userHistory.user?.verification_status === 'verified' ? '#16a34a' : '#d97706' }}>
                          {userHistory.user?.verification_status === 'verified' ? '✅ Verificado' : '⏳ Pendiente'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Fecha de Registro</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>
                          {userHistory.user?.created_at ? new Date(userHistory.user.created_at).toLocaleString('es-VE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Caracas' }) : 'No disponible'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Último Login</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>
                          {userHistory.user?.last_login ? new Date(userHistory.user.last_login).toLocaleString('es-VE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Caracas' }) : 'No disponible'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Rol</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', textTransform: 'capitalize', fontWeight: '600' }}>{userHistory.user?.role || 'user'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Email Verificado</p>
                        <p style={{ fontSize: '14px', margin: '2px 0 0 0', fontWeight: '600', color: userHistory.user?.email_verified ? '#16a34a' : '#dc2626' }}>
                          {userHistory.user?.email_verified ? '✅ Sí' : '❌ No'}
                        </p>
                      </div>
                      {userHistory.user?.gestor_code && (
                        <div>
                          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Código Gestor</p>
                          <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{userHistory.user.gestor_code}</p>
                        </div>
                      )}
                      {userHistory.user?.referral_code && (
                        <div>
                          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Código Referido</p>
                          <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{userHistory.user.referral_code}</p>
                        </div>
                      )}
                      {userHistory.user?.balance_ris_terceros > 0 && (
                        <div>
                          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Balance Terceros</p>
                          <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{fmt(userHistory.user.balance_ris_terceros)} RIS</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Admin Actions: Suspend / Delete */}
                  {selectedUser.role !== 'super_admin' && (
                    <div style={{ padding: '16px', backgroundColor: '#fef2f2', borderRadius: '14px', marginBottom: '24px' }}>
                      <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#991b1b', margin: '0 0 12px 0' }}>ACCIONES DE ADMINISTRADOR</h4>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <button
                          onClick={async () => {
                            const isSuspended = userHistory.user?.status === 'suspended';
                            if (!confirm(isSuspended ? '¿Reactivar este usuario?' : '¿Suspender este usuario? No podrá iniciar sesión.')) return;
                            try {
                              await api.post(`/admin/users/${selectedUser.user_id}/suspend`, { suspend: !isSuspended });
                              toast.success(isSuspended ? 'Usuario reactivado' : 'Usuario suspendido');
                              loadData();
                              closeUserModal();
                            } catch (e) {
                              toast.error(e.response?.data?.detail || 'Error');
                            }
                          }}
                          style={{ padding: '10px 20px', borderRadius: '10px', border: 'none', backgroundColor: userHistory.user?.status === 'suspended' ? '#16a34a' : '#f59e0b', color: 'white', fontSize: '13px', fontWeight: '600', cursor: 'pointer' }}
                          data-testid="suspend-user-btn"
                        >
                          {userHistory.user?.status === 'suspended' ? 'Reactivar Usuario' : 'Suspender Usuario'}
                        </button>
                        <button
                          onClick={async () => {
                            if (!confirm('¿ELIMINAR este usuario permanentemente? Esta acción NO se puede deshacer.')) return;
                            if (!confirm('¿Estás SEGURO? Se borrarán todos sus datos.')) return;
                            try {
                              await api.delete(`/admin/users/${selectedUser.user_id}`);
                              toast.success('Usuario eliminado');
                              loadData();
                              closeUserModal();
                            } catch (e) {
                              toast.error(e.response?.data?.detail || 'Error');
                            }
                          }}
                          style={{ padding: '10px 20px', borderRadius: '10px', border: 'none', backgroundColor: '#dc2626', color: 'white', fontSize: '13px', fontWeight: '600', cursor: 'pointer' }}
                          data-testid="delete-user-btn"
                        >
                          Eliminar Usuario
                        </button>
                      </div>
                    </div>
                  )}

                  {/* KYC Documents Section */}
                  {(userHistory.user?.id_document_image || userHistory.user?.cpf_image || userHistory.user?.selfie_image || userHistory.user?.profile_picture) && (
                    <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '14px', marginBottom: '24px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#92400e', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Image style={{ width: '16px', height: '16px' }} />
                          DOCUMENTOS KYC
                        </h4>
                        <button
                          onClick={() => {
                            const docs = [];
                            if (userHistory.user?.profile_picture) docs.push({ name: 'foto_perfil', url: userHistory.user.profile_picture });
                            if (userHistory.user?.id_document_image) docs.push({ name: 'documento_identidad', url: userHistory.user.id_document_image });
                            if (userHistory.user?.cpf_image) docs.push({ name: 'cpf', url: userHistory.user.cpf_image });
                            if (userHistory.user?.selfie_image) docs.push({ name: 'selfie', url: userHistory.user.selfie_image });
                            
                            docs.forEach(doc => {
                              const link = document.createElement('a');
                              link.href = doc.url;
                              link.download = `${userHistory.user?.name || 'usuario'}_${doc.name}.jpg`;
                              link.target = '_blank';
                              link.click();
                            });
                            toast.success(`${docs.length} documentos descargados`);
                          }}
                          style={{ padding: '8px 14px', borderRadius: '10px', border: 'none', backgroundColor: '#f59e0b', color: 'white', fontSize: '12px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                          data-testid="download-all-docs-btn"
                        >
                          <Download style={{ width: '14px', height: '14px' }} />
                          Descargar Todo
                        </button>
                        <button
                          onClick={async () => {
                            if (!driveConnected) {
                              try {
                                const res = await api.get('/oauth/drive/connect');
                                window.location.href = res.data.authorization_url;
                              } catch (e) {
                                toast.error('Error al conectar Drive');
                              }
                              return;
                            }
                            setUploadingKyc(true);
                            try {
                              const res = await api.post(`/oauth/drive/upload-kyc/${selectedUser.user_id}`);
                              toast.success(res.data.message);
                            } catch (e) {
                              toast.error(e.response?.data?.detail || 'Error al subir a Drive');
                            } finally {
                              setUploadingKyc(false);
                            }
                          }}
                          disabled={uploadingKyc}
                          style={{ padding: '8px 14px', borderRadius: '10px', border: 'none', backgroundColor: driveConnected ? '#16a34a' : '#4285f4', color: 'white', fontSize: '12px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', opacity: uploadingKyc ? 0.6 : 1 }}
                          data-testid="upload-drive-btn"
                        >
                          <Upload style={{ width: '14px', height: '14px' }} />
                          {uploadingKyc ? 'Subiendo...' : driveConnected ? 'Subir a Drive' : 'Conectar Drive'}
                        </button>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                        {userHistory.user?.profile_picture && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={userHistory.user.profile_picture} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={userHistory.user.profile_picture} 
                                alt="Foto de Perfil" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>Perfil</p>
                          </div>
                        )}
                        {userHistory.user?.id_document_image && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={userHistory.user.id_document_image} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={userHistory.user.id_document_image} 
                                alt="Documento" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>Documento</p>
                          </div>
                        )}
                        {userHistory.user?.cpf_image && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={userHistory.user.cpf_image} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={userHistory.user.cpf_image} 
                                alt="CPF" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>CPF</p>
                          </div>
                        )}
                        {userHistory.user?.selfie_image && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={userHistory.user.selfie_image} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={userHistory.user.selfie_image} 
                                alt="Selfie" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>Selfie</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Transactions List */}
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', margin: '0 0 12px 0' }}>
                      HISTORIAL DE TRANSACCIONES ({(userHistory.recharges?.length || 0) + (userHistory.withdrawals?.length || 0)} total)
                    </h4>
                    
                    {(!userHistory.recharges?.length && !userHistory.withdrawals?.length) ? (
                      <div style={{ padding: '32px', backgroundColor: '#f8f9fa', borderRadius: '14px', textAlign: 'center' }}>
                        <p style={{ color: '#6b7280', margin: 0 }}>No hay transacciones</p>
                      </div>
                    ) : (
                      <div style={{ border: '1px solid #e5e7eb', borderRadius: '14px', overflow: 'hidden' }}>
                        {[...(userHistory.withdrawals || []), ...(userHistory.recharges || [])]
                          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                          .map((tx, index) => (
                            <div 
                              key={tx.transaction_id || tx.recharge_id || index} 
                              style={{ 
                                padding: '14px 16px', 
                                borderBottom: index < (userHistory.withdrawals?.length || 0) + (userHistory.recharges?.length || 0) - 1 ? '1px solid #f3f4f6' : 'none',
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                  <div style={{ 
                                    width: '36px', height: '36px', borderRadius: '10px', 
                                    backgroundColor: tx.type === 'withdrawal' ? '#fef3c7' : '#dcfce7',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                                  }}>
                                    {tx.type === 'withdrawal' ? (
                                      <ArrowUpRight style={{ width: '18px', height: '18px', color: '#d97706' }} />
                                    ) : (
                                      <ArrowDownLeft style={{ width: '18px', height: '18px', color: '#16a34a' }} />
                                    )}
                                  </div>
                                  <div>
                                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>
                                      {tx.type === 'withdrawal' ? 'Envío/Retiro' : 'Recarga'}
                                      {tx.source && <span style={{ fontSize: '12px', color: '#6b7280', fontWeight: '400' }}> ({tx.source})</span>}
                                    </p>
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      {new Date(tx.created_at).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'America/Caracas' })}
                                    </p>
                                    <p style={{ fontSize: '11px', color: '#9ca3af', margin: '2px 0 0 0', fontFamily: 'monospace' }}>
                                      ID: {tx.transaction_id || tx.recharge_id || 'N/A'}
                                    </p>
                                  </div>
                                </div>
                                <div style={{ textAlign: 'right' }}>
                                  <p style={{ fontSize: '15px', fontWeight: '700', color: tx.type === 'withdrawal' ? '#d97706' : '#16a34a', margin: 0 }}>
                                    {tx.type === 'withdrawal' ? '-' : '+'}
                                    {tx.type === 'withdrawal' 
                                      ? fmt((tx.amount_input || tx.amount || 0))
                                      : fmt((tx.amount_output || tx.amount_ris || tx.amount || 0))
                                    } RIS
                                  </p>
                                  {tx.type === 'withdrawal' && tx.amount_output > 0 && (
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      = {fmt(tx.amount_output)} VES
                                    </p>
                                  )}
                                  {tx.type !== 'withdrawal' && tx.amount_ves > 0 && (
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      Pagó: {fmt(tx.amount_ves)} VES
                                    </p>
                                  )}
                                  <span style={{ 
                                    fontSize: '11px', fontWeight: '600', padding: '2px 8px', borderRadius: '9999px',
                                    backgroundColor: tx.status === 'completed' ? '#dcfce7' : tx.status === 'pending' ? '#fef3c7' : '#fee2e2',
                                    color: tx.status === 'completed' ? '#16a34a' : tx.status === 'pending' ? '#d97706' : '#dc2626'
                                  }}>
                                    {tx.status === 'completed' ? 'Completado' : tx.status === 'pending' ? 'Pendiente' : 'Rechazado'}
                                  </span>
                                </div>
                              </div>
                              
                              {/* Voucher/Comprobante */}
                              {(tx.proof_image || tx.voucher_url) && (
                                <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px dashed #e5e7eb' }}>
                                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 6px 0' }}>Comprobante:</p>
                                  <img 
                                    src={convertTwilioUrl(tx.proof_image || tx.voucher_url)} 
                                    alt="Comprobante" 
                                    style={{ 
                                      maxWidth: '200px', 
                                      maxHeight: '150px', 
                                      borderRadius: '8px', 
                                      border: '1px solid #e5e7eb',
                                      cursor: 'pointer'
                                    }}
                                    onClick={() => window.open(convertTwilioUrl(tx.proof_image || tx.voucher_url), '_blank')}
                                  />
                                </div>
                              )}
                              
                              {/* Beneficiario (para retiros) */}
                              {tx.type === 'withdrawal' && tx.beneficiary_name && (
                                <div style={{ marginTop: '8px', fontSize: '12px', color: '#6b7280' }}>
                                  <span>Beneficiario: </span>
                                  <span style={{ fontWeight: '500', color: '#374151' }}>{tx.beneficiary_name}</span>
                                  {tx.beneficiary_bank && <span> - {tx.beneficiary_bank}</span>}
                                </div>
                              )}
                            </div>
                          ))}
                      </div>
                    )}
                  </div>

                  {/* Beneficiaries */}
                  {userHistory.beneficiaries?.length > 0 && (
                    <div style={{ marginTop: '24px' }}>
                      <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', margin: '0 0 12px 0' }}>
                        BENEFICIARIOS ({userHistory.beneficiaries.length})
                      </h4>
                      <div style={{ display: 'grid', gap: '8px' }}>
                        {userHistory.beneficiaries.map((b, i) => (
                          <div key={i} style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '10px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{b.bank} • {b.account_number}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* Role Change Modal */}
      {showRoleModal && selectedUserForRole && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', padding: '20px', zIndex: 1000
        }} onClick={() => { setShowRoleModal(false); setSelectedUserForRole(null); }}>
          <div 
            style={{ 
              backgroundColor: '#ffffff', borderRadius: '20px', width: '100%', 
              maxWidth: '400px', overflow: 'hidden', boxShadow: '0 20px 50px rgba(0,0,0,0.2)' 
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '20px', borderBottom: '1px solid #e5e7eb' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3 style={{ fontSize: '18px', fontWeight: '600', margin: 0 }}>Cambiar Rol de Usuario</h3>
                <button 
                  onClick={() => { setShowRoleModal(false); setSelectedUserForRole(null); }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px' }}
                >
                  <X style={{ width: '24px', height: '24px', color: '#6b7280' }} />
                </button>
              </div>
            </div>

            <div style={{ padding: '20px' }}>
              <div style={{ marginBottom: '20px', padding: '16px', backgroundColor: '#f9fafb', borderRadius: '12px' }}>
                <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>
                  {selectedUserForRole.name}
                </p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>{selectedUserForRole.email}</p>
                <div style={{ marginTop: '8px' }}>
                  <span style={{ 
                    padding: '4px 10px', borderRadius: '8px', fontSize: '12px', fontWeight: '600',
                    backgroundColor: selectedUserForRole.role === 'socio' ? '#ede9fe' : selectedUserForRole.role === 'socio_gestor' ? '#d1fae5' : '#f3f4f6',
                    color: selectedUserForRole.role === 'socio' ? '#7c3aed' : selectedUserForRole.role === 'socio_gestor' ? '#059669' : '#6b7280'
                  }}>
                    Rol actual: {selectedUserForRole.role === 'socio' ? 'Socio' : selectedUserForRole.role === 'socio_gestor' ? 'Gestor' : 'Usuario'}
                  </span>
                </div>
              </div>

              <p style={{ fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '12px' }}>
                Selecciona el nuevo rol:
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {/* User Role */}
                <button
                  onClick={() => handleChangeRole('user')}
                  disabled={assigningRole || selectedUserForRole.role === 'user'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'user' ? '#f3f4f6' : '#ffffff',
                    border: '2px solid #e5e7eb', borderRadius: '12px', cursor: selectedUserForRole.role === 'user' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'user' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-user-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Users style={{ width: '22px', height: '22px', color: '#6b7280' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>👤 Usuario Normal</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Acceso básico a la app</p>
                  </div>
                </button>

                {/* Socio Role */}
                <button
                  onClick={() => handleChangeRole('socio')}
                  disabled={assigningRole || selectedUserForRole.role === 'socio'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'socio' ? '#ede9fe' : '#ffffff',
                    border: '2px solid #8b5cf6', borderRadius: '12px', cursor: selectedUserForRole.role === 'socio' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'socio' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-socio-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Gift style={{ width: '22px', height: '22px', color: '#7c3aed' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>🎁 Socio (Referidor)</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Puede referir usuarios y ganar comisiones</p>
                  </div>
                </button>

                {/* Socio Gestor Role */}
                <button
                  onClick={() => handleChangeRole('socio_gestor')}
                  disabled={assigningRole || selectedUserForRole.role === 'socio_gestor'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'socio_gestor' ? '#d1fae5' : '#ffffff',
                    border: '2px solid #10b981', borderRadius: '12px', cursor: selectedUserForRole.role === 'socio_gestor' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'socio_gestor' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-gestor-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#d1fae5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Briefcase style={{ width: '22px', height: '22px', color: '#059669' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>Socio Gestor</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Procesa envíos de terceros</p>
                  </div>
                </button>

                {/* Super Admin Role */}
                <button
                  onClick={() => {
                    if (confirm('¿Estás seguro? Este usuario tendrá los mismos poderes que tú.')) {
                      handleChangeRole('super_admin');
                    }
                  }}
                  disabled={assigningRole || selectedUserForRole.role === 'super_admin'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'super_admin' ? '#fef2f2' : '#ffffff',
                    border: '2px solid #dc2626', borderRadius: '12px', cursor: selectedUserForRole.role === 'super_admin' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'super_admin' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-super-admin-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Shield style={{ width: '22px', height: '22px', color: '#dc2626' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#dc2626', margin: 0 }}>Super Administrador</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Acceso total al panel de administración</p>
                  </div>
                </button>
              </div>

              {assigningRole && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: '16px' }}>
                  <RefreshCw style={{ width: '20px', height: '20px', color: '#6366f1', animation: 'spin 1s linear infinite' }} />
                  <span style={{ marginLeft: '8px', fontSize: '14px', color: '#6b7280' }}>Cambiando rol...</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Cleanup Modal */}
      {showCleanupModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', width: '100%', maxWidth: '550px', maxHeight: '90vh', overflow: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '12px', backgroundColor: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Trash2 style={{ width: '24px', height: '24px', color: '#dc2626' }} />
                </div>
                <div>
                  <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Limpieza de Retiros</h3>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Transacciones pendientes detectadas</p>
                </div>
              </div>
              <button onClick={() => setShowCleanupModal(false)} style={{ width: '36px', height: '36px', borderRadius: '10px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {pendingToClean.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <Activity style={{ width: '32px', height: '32px', color: '#16a34a' }} />
                </div>
                <h4 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 8px 0' }}>¡Todo limpio!</h4>
                <p style={{ color: '#6b7280', margin: 0 }}>No hay transacciones pendientes para limpiar</p>
              </div>
            ) : (
              <>
                <div style={{ backgroundColor: '#fef3c7', borderRadius: '12px', padding: '12px', marginBottom: '16px' }}>
                  <p style={{ color: '#92400e', fontSize: '13px', margin: 0 }}>
                    ⚠️ Se encontraron {pendingToClean.length} transacción(es) pendiente(s). Eliminar devolverá el saldo al usuario.
                  </p>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px', maxHeight: '300px', overflowY: 'auto' }}>
                  {pendingToClean.map((tx) => (
                    <div key={tx.transaction_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
                      <div>
                        <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{tx.beneficiary || 'Sin nombre'}</p>
                        <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>
                          R{tx.display_id} • {fmt(tx.amount_ves)} VES
                        </p>
                        <p style={{ fontSize: '11px', color: '#9ca3af', margin: '2px 0 0 0' }}>
                          {tx.whatsapp_active ? '🟢 Activo en WhatsApp' : '⏳ En cola'}
                        </p>
                      </div>
                      <button 
                        onClick={() => deleteSingleWithdrawal(tx.transaction_id)}
                        disabled={cleaningUp}
                        style={{ ...btnDanger, opacity: cleaningUp ? 0.5 : 1, padding: '8px 12px' }}
                      >
                        <Trash2 style={{ width: '14px', height: '14px' }} />
                      </button>
                    </div>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button onClick={() => setShowCleanupModal(false)} style={{ ...btnSecondary, flex: 1 }}>
                    Cerrar
                  </button>
                  <button 
                    onClick={cleanupAllPending}
                    disabled={cleaningUp}
                    style={{ ...btnDanger, flex: 1, opacity: cleaningUp ? 0.5 : 1 }}
                  >
                    {cleaningUp ? 'Limpiando...' : `Eliminar todas (${pendingToClean.length})`}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Modal para rechazar recarga VES */}
      {showRejectRechargeModal && (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            backgroundColor: '#fff', borderRadius: '16px', padding: '24px',
            width: '100%', maxWidth: '440px', margin: '0 16px',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
          }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: '700', color: '#111827' }}>
              Rechazar recarga
            </h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#6b7280' }}>
              Indica el motivo del rechazo. El usuario recibirá esta información.
            </p>
            <textarea
              value={rejectRechargeReason}
              onChange={(e) => setRejectRechargeReason(e.target.value)}
              placeholder="Ej: Comprobante ilegible, monto incorrecto..."
              rows={4}
              style={{
                width: '100%', padding: '12px', borderRadius: '10px',
                border: '1.5px solid #d1d5db', fontSize: '14px',
                fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box',
                outline: 'none'
              }}
              autoFocus
            />
            <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
              <button
                onClick={() => { setShowRejectRechargeModal(false); setRejectRechargeReason(''); setRejectRechargeId(null); }}
                style={{
                  flex: 1, padding: '12px', borderRadius: '10px', border: '1.5px solid #d1d5db',
                  backgroundColor: '#fff', color: '#374151', fontSize: '14px',
                  fontWeight: '600', cursor: 'pointer'
                }}
              >Cancelar</button>
              <button
                onClick={handleConfirmRejectRechargeVES}
                style={{
                  flex: 1, padding: '12px', borderRadius: '10px', border: 'none',
                  backgroundColor: '#dc2626', color: '#fff', fontSize: '14px',
                  fontWeight: '700', cursor: 'pointer'
                }}
              >Confirmar rechazo</button>
            </div>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
