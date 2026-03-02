import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Users, ArrowUpRight, ArrowDownLeft, TrendingUp, Search, 
  RefreshCw, Shield, Activity
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
  { key: 'recharges', label: 'Recargas', icon: ArrowDownLeft },
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
  const [recharges, setRecharges] = useState([]);
  const [users, setUsers] = useState([]);
  const [kycPending, setKycPending] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState(null);
  const [showProcessModal, setShowProcessModal] = useState(false);
  const [proofImage, setProofImage] = useState(null);
  const [newRate, setNewRate] = useState('');
  const [newRateVesToRis, setNewRateVesToRis] = useState('');

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
          const wAllRes = await api.get('/admin/withdrawals/all');
          setWithdrawals(wAllRes.data || []);
          break;
        case 'recharges':
          const rAllRes = await api.get('/admin/recharges/ves/pending');
          setRecharges(rAllRes.data?.recharges || []);
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
    if (!selectedItem || !proofImage) { toast.error('Sube el comprobante de pago'); return; }
    try {
      await api.post('/admin/withdrawals/process', { 
        transaction_id: selectedItem.transaction_id, 
        action: 'approve',
        proof_image: proofImage 
      });
      toast.success('Retiro procesado exitosamente');
      setShowProcessModal(false); setSelectedItem(null); setProofImage(null); loadData();
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

  const handleApproveRecharge = async (txId) => {
    try { await api.post('/admin/recharge/approve', { transaction_id: txId, approved: true }); toast.success('Recarga aprobada'); loadData(); } 
    catch { toast.error('Error al aprobar'); }
  };

  const handleKycDecision = async (verificationId, approved, reason = '') => {
    try { await api.post('/admin/verifications/decide', { verification_id: verificationId, approved, rejection_reason: reason }); toast.success(approved ? 'KYC aprobado' : 'KYC rechazado'); loadData(); } 
    catch { toast.error('Error al procesar KYC'); }
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

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) { const reader = new FileReader(); reader.onload = () => setProofImage(reader.result); reader.readAsDataURL(file); }
  };

  const filteredWithdrawals = withdrawals.filter(w => {
    if (statusFilter !== 'all' && w.status !== statusFilter) return false;
    if (searchQuery && !w.beneficiary_data?.full_name?.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

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
                        {['Fecha', 'Beneficiario', 'Monto', 'Estado', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredWithdrawals.map((w) => (
                        <tr key={w.transaction_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`withdrawal-${w.transaction_id}`}>
                          <td style={{ padding: '16px', fontSize: '14px', color: '#6b7280' }}>{new Date(w.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                          <td style={{ padding: '16px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{w.beneficiary_data?.full_name}</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{w.beneficiary_data?.bank}</p>
                          </td>
                          <td style={{ padding: '16px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{w.amount_input?.toFixed(2)} RIS</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{w.amount_output?.toFixed(2)} VES</p>
                          </td>
                          <td style={{ padding: '16px' }}>{getStatusBadge(w.status)}</td>
                          <td style={{ padding: '16px' }}>
                            {w.status === 'pending' && (
                              <div style={{ display: 'flex', gap: '8px' }}>
                                <button onClick={() => { setSelectedItem(w); setShowProcessModal(true); }} style={btnSuccess}>Procesar</button>
                                <button onClick={() => handleRejectWithdrawal(w.transaction_id)} style={btnDanger}>Rechazar</button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Recharges Tab */}
        {activeTab === 'recharges' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {loading ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
            ) : recharges.length === 0 ? (
              <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}><p style={{ color: '#6b7280' }}>No hay recargas pendientes</p></div>
            ) : recharges.map((r) => (
              <div key={r.transaction_id} style={{ ...cardStyle, padding: '20px' }} data-testid={`recharge-${r.transaction_id}`}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
                  <div>
                    <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>{r.user_email}</p>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>{r.amount_input} VES → {r.amount_output?.toFixed(2)} RIS</p>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={() => handleApproveRecharge(r.transaction_id)} style={btnSuccess}>Aprobar</button>
                    <button style={btnDanger}>Rechazar</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && (
          <div style={{ ...cardStyle, overflow: 'hidden' }}>
            {loading ? (
              <div style={{ padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead style={{ backgroundColor: '#f8f9fa' }}>
                    <tr>
                      {['Usuario', 'Balance', 'Estado', 'Rol'].map(h => (
                        <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.user_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`user-${u.user_id}`}>
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
                        <td style={{ padding: '16px', fontSize: '14px', color: '#6b7280', textTransform: 'capitalize' }}>{u.role || 'user'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
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
                      style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px' }}
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
                      style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px' }}
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
          <div style={{ backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', width: '100%', maxWidth: '450px' }}>
            <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: '0 0 20px 0' }}>Procesar Retiro</h3>
            <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '20px' }}>
              <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Beneficiario</p>
              <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>{selectedItem.beneficiary_data?.full_name}</p>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 4px 0' }}>{selectedItem.beneficiary_data?.bank}</p>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 8px 0' }}>{selectedItem.beneficiary_data?.account_number}</p>
              <p style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>{selectedItem.amount_output?.toFixed(2)} VES</p>
            </div>
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Comprobante de pago</label>
              <input type="file" accept="image/*" onChange={handleFileChange} style={{ width: '100%' }} />
              {proofImage && <img src={proofImage} alt="Comprobante" style={{ marginTop: '12px', borderRadius: '12px', maxHeight: '160px', objectFit: 'contain' }} />}
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => { setShowProcessModal(false); setSelectedItem(null); setProofImage(null); }} style={{ ...btnSecondary, flex: 1 }}>Cancelar</button>
              <button onClick={handleProcessWithdrawal} disabled={!proofImage} style={{ ...btnSuccess, flex: 1, opacity: proofImage ? 1 : 0.5 }}>Confirmar</button>
            </div>
          </div>
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
