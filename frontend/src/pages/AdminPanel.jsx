import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Users, ArrowUpRight, ArrowDownLeft, TrendingUp, Search, 
  RefreshCw, Shield, Activity, Eye, X, ChevronRight, UserCog, Gift, Briefcase, KeyRound, Trash2
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

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
  { key: 'rates', label: 'Tasas', icon: TrendingUp },
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
  const [kycPending, setKycPending] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState(null);
  const [showProcessModal, setShowProcessModal] = useState(false);
  const [proofImages, setProofImages] = useState([]);  // Array for multiple images
  const [newRate, setNewRate] = useState('');
  const [newRateVesToRis, setNewRateVesToRis] = useState('');
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
  // Partner/Gestor management states
  const [partners, setPartners] = useState([]);
  const [gestors, setGestors] = useState([]);
  const [partnerSearchQuery, setPartnerSearchQuery] = useState('');
  const [partnerTab, setPartnerTab] = useState('socios'); // 'socios' or 'gestores'

  useEffect(() => { loadData(); }, [activeTab]);

  const loadData = async () => {
    setLoading(true);
    try {
      switch (activeTab) {
        case 'overview':
          const [wRes, rRes, uRes, kRes] = await Promise.all([
            api.get('/admin/withdrawals/pending').catch(() => ({ data: [] })),
            api.get('/admin/recharges/ves/pending').catch(() => ({ data: { recharges: [] } })),
            api.get('/admin/users').catch(() => ({ data: { users: [] } })),
            api.get('/admin/verifications/pending').catch(() => ({ data: [] }))
          ]);
          setStats({
            pending_withdrawals: (wRes.data || []).length,
            pending_recharges: (rRes.data?.recharges || []).length,
            users: (uRes.data?.users || []).length,
            pending_kyc: (kRes.data || []).length
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
          const rAllRes = await api.get('/admin/recharges/ves/pending');
          setRecharges(rAllRes.data?.recharges || []);
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
          const kycRes = await api.get('/admin/verifications/pending');
          setKycPending(kycRes.data || []);
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
    try {
      await api.post('/admin/withdrawals/process', { 
        transaction_id: selectedItem.transaction_id, 
        action: 'approve',
        proof_images: proofImages,  // Send array of images
        proof_image: proofImages[0] // Keep backwards compatibility
      });
      toast.success('Retiro procesado exitosamente');
      setShowProcessModal(false); setSelectedItem(null); setProofImages([]); loadData();
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

  // Aprobar recarga VES
  const handleApproveRechargeVES = async (txId) => {
    if (!confirm('¿Aprobar esta recarga? Se acreditará el saldo al usuario.')) return;
    try {
      await api.post('/admin/recharges/ves/approve', { transaction_id: txId, approved: true });
      toast.success('Recarga aprobada - Saldo acreditado');
      loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Error al aprobar'); }
  };

  // Rechazar recarga VES
  const handleRejectRechargeVES = async (txId) => {
    if (!confirm('¿Rechazar esta recarga? El usuario será notificado.')) return;
    try {
      await api.post('/admin/recharges/ves/approve', { 
        transaction_id: txId, 
        approved: false, 
        rejection_reason: 'Comprobante inválido o datos incorrectos' 
      });
      toast.success('Recarga rechazada');
      loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Error al rechazar'); }
  };

  const handleApproveRecharge = async (txId) => {
    try { await api.post('/admin/recharge/approve', { transaction_id: txId, approved: true }); toast.success('Recarga aprobada'); loadData(); } 
    catch { toast.error('Error al aprobar'); }
  };

  const handleKycDecision = async (verificationId, approved, reason = '') => {
    try { await api.post('/admin/verifications/decide', { verification_id: verificationId, approved, rejection_reason: reason }); toast.success(approved ? 'KYC aprobado' : 'KYC rechazado'); loadData(); } 
    catch { toast.error('Error al procesar KYC'); }
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
      await api.post('/rate', { 
        ris_to_ves: parseFloat(newRate),
        ves_to_ris: rates?.ves_to_ris || 0
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
      await api.post('/rate', { 
        ris_to_ves: rates?.ris_to_ves || 0,
        ves_to_ris: parseFloat(newRateVesToRis)
      }); 
      toast.success('Tasa VES → RIS actualizada'); 
      refreshRates(); 
      setNewRateVesToRis('');
    } 
    catch { toast.error('Error al actualizar tasa'); }
  };

  // Cargar historial completo de un usuario
  const loadUserHistory = async (userId) => {
    setLoadingUser(true);
    try {
      const response = await api.get(`/admin/users/${userId}/complete`);
      // Map the response to match expected structure
      const data = response.data;
      setUserHistory({
        user: {
          ...data.profile,
          cpf: data.kyc?.cpf_number || data.profile?.document_number,
          verification_status: data.kyc?.verification_status,
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

  const getStatusBadge = (status) => {
    const styles = { completed: { bg: '#dcfce7', color: '#16a34a' }, pending: { bg: '#fef3c7', color: '#d97706' }, rejected: { bg: '#fee2e2', color: '#dc2626' } };
    const labels = { completed: 'Completado', pending: 'Pendiente', rejected: 'Rechazado' };
    const s = styles[status] || { bg: '#f3f4f6', color: '#6b7280' };
    return <span style={{ padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600', backgroundColor: s.bg, color: s.color }}>{labels[status] || status}</span>;
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
                <h1 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Panel de Administración</h1>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{user?.role === 'super_admin' ? 'Super Admin' : 'Admin'}</p>
              </div>
            </div>
            <button onClick={loadData} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="refresh-button">
              <RefreshCw style={{ width: '20px', height: '20px', color: '#374151', animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            </button>
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
            <div style={{ ...cardStyle, padding: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>Tasa actual</h3>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
                <div>
                  <p style={{ fontSize: '32px', fontWeight: '700', color: '#111827', margin: 0 }}>1 RIS = {rates?.ris_to_ves?.toFixed(2) || '0.00'} VES</p>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Última actualización: {new Date().toLocaleTimeString('es-ES')}</p>
                </div>
                <button onClick={() => setActiveTab('rates')} style={btnPrimary}>Modificar</button>
              </div>
            </div>
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
                  {queueStats.total_ves_pending?.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} VES
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#78350f' }}>
                  ({queueStats.total_ris_pending?.toFixed(2)} RIS en {queueStats.total_pending} retiros pendientes)
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
                      style={{ padding: '10px 16px', borderRadius: '12px', border: 'none', cursor: 'pointer', fontSize: '14px', fontWeight: '500',
                        backgroundColor: statusFilter === status ? '#6366f1' : '#f3f4f6', color: statusFilter === status ? '#ffffff' : '#374151' }}>
                      {status === 'all' ? 'Todos' : status === 'pending' ? 'Pendientes' : status === 'completed' ? 'Completados' : 'Rechazados'}
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
                          <td style={{ padding: '16px', fontSize: '14px', color: '#6b7280' }}>{new Date(w.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                          <td style={{ padding: '16px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{w.beneficiary_data?.full_name}</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{w.beneficiary_data?.bank}</p>
                          </td>
                          <td style={{ padding: '16px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{w.amount_input?.toFixed(2)} RIS</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{w.amount_output?.toFixed(2)} VES</p>
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
                          <td style={{ padding: '16px' }}>{getStatusBadge(w.status)}</td>
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
                                const images = w.proof_images?.length > 0 ? w.proof_images : (w.proof_image ? [w.proof_image] : []);
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
              recharges.map((r) => (
                <div key={r.transaction_id} style={{ ...cardStyle, padding: '24px', overflow: 'hidden' }} data-testid={`recharge-${r.transaction_id}`}>
                  {/* Header */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '20px' }}>
                    <div>
                      <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>{r.user_name || r.user_email}</p>
                      <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>{r.user_email}</p>
                      <p style={{ fontSize: '12px', color: '#9ca3af', margin: '4px 0 0 0' }}>
                        {new Date(r.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                    <span style={{ padding: '6px 14px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600', backgroundColor: '#fef3c7', color: '#d97706' }}>
                      ⏳ Pendiente
                    </span>
                  </div>

                  {/* Amount Info */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
                    <div style={{ padding: '16px', backgroundColor: '#dbeafe', borderRadius: '12px' }}>
                      <p style={{ fontSize: '12px', color: '#2563eb', margin: '0 0 4px 0', fontWeight: '600' }}>PAGADO</p>
                      <p style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>{parseFloat(r.amount_ves || r.amount_input || 0).toLocaleString()} VES</p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#dcfce7', borderRadius: '12px' }}>
                      <p style={{ fontSize: '12px', color: '#16a34a', margin: '0 0 4px 0', fontWeight: '600' }}>A ACREDITAR</p>
                      <p style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>{parseFloat(r.amount_ris || r.amount_output || 0).toFixed(2)} RIS</p>
                    </div>
                  </div>

                  {/* Payment Method */}
                  <div style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '10px', marginBottom: '16px' }}>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Método de pago</p>
                    <p style={{ fontSize: '14px', fontWeight: '500', color: '#374151', margin: 0 }}>
                      {r.bank === 'banco_venezuela' ? '🏦 Banco de Venezuela' : r.bank === 'banesco' ? '🏦 Banesco' : r.bank || 'No especificado'} • {r.payment_method === 'pago_movil' ? '📱 Pago Móvil' : r.payment_method === 'transferencia' ? '💳 Transferencia' : r.payment_method || 'No especificado'}
                    </p>
                  </div>

                  {/* Voucher Image */}
                  {r.voucher_image && (
                    <div style={{ marginBottom: '16px' }}>
                      <p style={{ fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '8px' }}>Comprobante adjunto:</p>
                      <img 
                        src={r.voucher_image} 
                        alt="Comprobante" 
                        style={{ width: '100%', maxHeight: '300px', objectFit: 'contain', borderRadius: '12px', border: '1px solid #e5e7eb', backgroundColor: '#f9fafb' }}
                      />
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div style={{ display: 'flex', gap: '12px' }}>
                    <button 
                      onClick={() => handleApproveRechargeVES(r.transaction_id)} 
                      style={{ ...btnSuccess, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
                    >
                      <Eye style={{ width: '16px', height: '16px' }} />
                      Aprobar Recarga
                    </button>
                    <button 
                      onClick={() => handleRejectRechargeVES(r.transaction_id)} 
                      style={{ ...btnDanger, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
                    >
                      <X style={{ width: '16px', height: '16px' }} />
                      Rechazar
                    </button>
                  </div>
                </div>
              ))
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
                              {(p.total_earnings || 0).toFixed(2)} RIS
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#16a34a' }}>
                              +{(p.month_earnings || 0).toFixed(2)} RIS
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
                              {(g.total_volume || 0).toFixed(2)} RIS
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ fontSize: '14px', fontWeight: '700', color: '#059669' }}>
                                {(g.balance_ris_terceros || 0).toFixed(2)} RIS
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
                          <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>{u.balance_ris?.toFixed(2)} RIS</td>
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
                            {u.role !== 'admin' && u.role !== 'super_admin' && (
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
                            {u.role !== 'admin' && u.role !== 'super_admin' && (
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

        {/* KYC Tab */}
        {activeTab === 'kyc' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {loading ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
            ) : kycPending.length === 0 ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}><p style={{ color: '#6b7280' }}>No hay verificaciones pendientes</p></div>
            ) : kycPending.map((k) => (
              <div key={k.verification_id} style={{ ...cardStyle, padding: '24px' }} data-testid={`kyc-${k.verification_id}`}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
                  {k.selfie_image && <img src={k.selfie_image} alt="Selfie" style={{ width: '80px', height: '80px', borderRadius: '16px', objectFit: 'cover' }} />}
                  <div style={{ flex: 1, minWidth: '200px' }}>
                    <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>{k.full_name}</h3>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 8px 0' }}>{k.email}</p>
                    <p style={{ fontSize: '14px', color: '#374151', margin: 0 }}>CPF: {maskCPF(k.cpf_number)} • Doc: {k.document_number}</p>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={() => handleKycDecision(k.verification_id, true)} style={btnSuccess}>Aprobar</button>
                    <button onClick={() => handleKycDecision(k.verification_id, false, 'Documentos no válidos')} style={btnDanger}>Rechazar</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
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
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>1 RIS = {rates?.ris_to_ves?.toFixed(2) || '0.00'} VES</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para retiros a Venezuela</p>
                </div>
                <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                  <p style={{ fontSize: '12px', color: '#16a34a', margin: '0 0 4px 0', fontWeight: '600' }}>RECARGAS (VES → RIS)</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>{rates?.ves_to_ris?.toFixed(2) || '0.00'} VES = 1 RIS</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para recargas con Bolívares</p>
                </div>
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
              </div>
            </div>
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
                  {selectedItem.amount_output?.toFixed(2)} VES
                </p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0', textAlign: 'center' }}>
                  ({selectedItem.amount_input?.toFixed(2)} RIS)
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
              <button onClick={() => { setShowProcessModal(false); setSelectedItem(null); setProofImages([]); }} style={{ ...btnSecondary, flex: 1 }}>
                {selectedItem.status === 'completed' ? 'Cerrar' : 'Cancelar'}
              </button>
              {selectedItem.status === 'pending' && (
                <button onClick={handleProcessWithdrawal} disabled={proofImages.length === 0} style={{ ...btnSuccess, flex: 1, opacity: proofImages.length > 0 ? 1 : 0.5 }}>
                  Confirmar ({proofImages.length} img)
                </button>
              )}
            </div>
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
                        {(userHistory.user?.balance_ris ?? 0).toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#dbeafe', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#2563eb', margin: '0 0 4px 0', fontWeight: '600' }}>TOTAL RECARGADO</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {(userHistory.stats?.total_recharged ?? 0).toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#d97706', margin: '0 0 4px 0', fontWeight: '600' }}>TOTAL ENVIADO</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {(userHistory.stats?.total_withdrawn ?? 0).toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#f3e8ff', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#9333ea', margin: '0 0 4px 0', fontWeight: '600' }}>VES ENVIADOS</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {(userHistory.stats?.total_ves_sent ?? 0).toLocaleString('es-ES', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                      </p>
                    </div>
                  </div>

                  {/* User Info */}
                  <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '24px' }}>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', margin: '0 0 12px 0' }}>INFORMACIÓN DEL USUARIO</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>CPF</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{maskCPF(userHistory.user?.cpf)}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Estado KYC</p>
                        <p style={{ fontSize: '14px', margin: '2px 0 0 0', fontWeight: '600', color: userHistory.user?.verification_status === 'verified' ? '#16a34a' : '#d97706' }}>
                          {userHistory.user?.verification_status === 'verified' ? '✅ Verificado' : '⏳ Pendiente'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Fecha de registro</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>
                          {userHistory.user?.created_at ? new Date(userHistory.user.created_at).toLocaleDateString('es-ES') : 'No disponible'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Rol</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', textTransform: 'capitalize' }}>{userHistory.user?.role || 'user'}</p>
                      </div>
                    </div>
                  </div>

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
                                      {new Date(tx.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit' })}
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
                                      ? (tx.amount_input || tx.amount || 0).toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})
                                      : (tx.amount_output || tx.amount_ris || tx.amount || 0).toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})
                                    } RIS
                                  </p>
                                  {tx.type === 'withdrawal' && tx.amount_output > 0 && (
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      = {tx.amount_output?.toLocaleString('es-ES')} VES
                                    </p>
                                  )}
                                  {tx.type !== 'withdrawal' && tx.amount_ves > 0 && (
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      Pagó: {tx.amount_ves?.toLocaleString('es-ES')} VES
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
                                    src={tx.proof_image || tx.voucher_url} 
                                    alt="Comprobante" 
                                    style={{ 
                                      maxWidth: '200px', 
                                      maxHeight: '150px', 
                                      borderRadius: '8px', 
                                      border: '1px solid #e5e7eb',
                                      cursor: 'pointer'
                                    }}
                                    onClick={() => window.open(tx.proof_image || tx.voucher_url, '_blank')}
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
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>🏪 Socio Gestor</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Procesa remesas de terceros</p>
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
                          R{tx.display_id} • {tx.amount_ves?.toFixed(2)} VES
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

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
