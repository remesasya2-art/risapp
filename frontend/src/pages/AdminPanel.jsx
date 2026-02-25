import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Users, CreditCard, ArrowUpRight, ArrowDownLeft, TrendingUp, 
  Search, CheckCircle, XCircle, Clock, Eye, RefreshCw, Shield, 
  ChevronDown, Filter, MoreHorizontal, DollarSign, Activity
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

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

  useEffect(() => {
    loadData();
  }, [activeTab]);

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
            pending_recharges: (rRes.data.recharges || []).length,
            users: (uRes.data.users || []).length,
            pending_kyc: (kRes.data || []).length
          });
          break;
        case 'withdrawals':
          const wAllRes = await api.get('/admin/withdrawals/all');
          setWithdrawals(wAllRes.data || []);
          break;
        case 'recharges':
          const rAllRes = await api.get('/admin/recharges/ves/pending');
          setRecharges(rAllRes.data.recharges || []);
          break;
        case 'users':
          const usersRes = await api.get('/admin/users');
          setUsers(usersRes.data.users || []);
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
    if (!selectedItem || !proofImage) {
      toast.error('Sube el comprobante de pago');
      return;
    }
    try {
      await api.post('/admin/withdrawals/process', {
        transaction_id: selectedItem.transaction_id,
        proof_image: proofImage,
      });
      toast.success('Retiro procesado');
      setShowProcessModal(false);
      setSelectedItem(null);
      setProofImage(null);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar');
    }
  };

  const handleRejectWithdrawal = async (txId) => {
    if (!confirm('¿Rechazar este retiro?')) return;
    try {
      await api.post(`/admin/withdrawals/${txId}/reject`);
      toast.success('Retiro rechazado');
      loadData();
    } catch (error) {
      toast.error('Error al rechazar');
    }
  };

  const handleApproveRecharge = async (txId) => {
    try {
      await api.post('/admin/recharge/approve', { transaction_id: txId, approved: true });
      toast.success('Recarga aprobada');
      loadData();
    } catch (error) {
      toast.error('Error al aprobar');
    }
  };

  const handleKycDecision = async (verificationId, approved, reason = '') => {
    try {
      await api.post('/admin/verifications/decide', {
        verification_id: verificationId,
        approved,
        rejection_reason: reason,
      });
      toast.success(approved ? 'KYC aprobado' : 'KYC rechazado');
      loadData();
    } catch (error) {
      toast.error('Error al procesar KYC');
    }
  };

  const handleUpdateRate = async () => {
    if (!newRate || parseFloat(newRate) <= 0) {
      toast.error('Ingresa una tasa válida');
      return;
    }
    try {
      await api.post('/rate', { ris_to_ves: parseFloat(newRate) });
      toast.success('Tasa actualizada');
      refreshRates();
      setNewRate('');
    } catch (error) {
      toast.error('Error al actualizar tasa');
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => setProofImage(reader.result);
      reader.readAsDataURL(file);
    }
  };

  const filteredWithdrawals = withdrawals.filter(w => {
    if (statusFilter !== 'all' && w.status !== statusFilter) return false;
    if (searchQuery && !w.beneficiary_data?.full_name?.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  const getStatusBadge = (status) => {
    const styles = {
      completed: 'bg-green-100 text-green-700',
      pending: 'bg-amber-100 text-amber-700',
      rejected: 'bg-red-100 text-red-700',
    };
    const labels = { completed: 'Completado', pending: 'Pendiente', rejected: 'Rechazado' };
    return (
      <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${styles[status] || 'bg-gray-100 text-gray-700'}`}>
        {labels[status] || status}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-slate-100">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <button onClick={() => navigate('/')} className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
                <ArrowLeft className="w-5 h-5 text-slate-600" />
              </button>
              <div>
                <h1 className="font-bold text-slate-900">Panel de Administración</h1>
                <p className="text-xs text-slate-500">{user?.role === 'super_admin' ? 'Super Admin' : 'Admin'}</p>
              </div>
            </div>
            <button onClick={loadData} className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
              <RefreshCw className={`w-5 h-5 text-slate-600 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex gap-1 overflow-x-auto py-2 scrollbar-hide">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                  activeTab === tab.key
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center">
                    <ArrowUpRight className="w-5 h-5 text-amber-600" />
                  </div>
                  <span className="text-2xl font-bold text-slate-900">{stats.pending_withdrawals}</span>
                </div>
                <p className="text-sm text-slate-600">Retiros pendientes</p>
              </div>
              <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-xl bg-green-100 flex items-center justify-center">
                    <ArrowDownLeft className="w-5 h-5 text-green-600" />
                  </div>
                  <span className="text-2xl font-bold text-slate-900">{stats.pending_recharges}</span>
                </div>
                <p className="text-sm text-slate-600">Recargas pendientes</p>
              </div>
              <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
                    <Users className="w-5 h-5 text-blue-600" />
                  </div>
                  <span className="text-2xl font-bold text-slate-900">{stats.users}</span>
                </div>
                <p className="text-sm text-slate-600">Usuarios totales</p>
              </div>
              <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center">
                    <Shield className="w-5 h-5 text-purple-600" />
                  </div>
                  <span className="text-2xl font-bold text-slate-900">{stats.pending_kyc}</span>
                </div>
                <p className="text-sm text-slate-600">KYC pendientes</p>
              </div>
            </div>

            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
              <h3 className="font-semibold text-slate-900 mb-4">Tasa actual</h3>
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <p className="text-3xl font-bold text-slate-900">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</p>
                  <p className="text-sm text-slate-500 mt-1">Última actualización: {new Date().toLocaleTimeString()}</p>
                </div>
                <button onClick={() => setActiveTab('rates')} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-medium transition-colors">
                  Modificar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Withdrawals Tab */}
        {activeTab === 'withdrawals' && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200">
              <div className="flex flex-col sm:flex-row gap-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Buscar por beneficiario..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 text-sm"
                  />
                </div>
                <div className="flex gap-2 overflow-x-auto">
                  {['all', 'pending', 'completed', 'rejected'].map((status) => (
                    <button
                      key={status}
                      onClick={() => setStatusFilter(status)}
                      className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-colors ${
                        statusFilter === status ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {status === 'all' ? 'Todos' : status === 'pending' ? 'Pendientes' : status === 'completed' ? 'Completados' : 'Rechazados'}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {loading ? (
              <div className="bg-white rounded-2xl p-12 flex justify-center">
                <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
              </div>
            ) : filteredWithdrawals.length === 0 ? (
              <div className="bg-white rounded-2xl p-12 text-center">
                <p className="text-slate-500">No hay retiros</p>
              </div>
            ) : (
              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Fecha</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Beneficiario</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Monto</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Estado</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Acciones</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredWithdrawals.map((w) => (
                        <tr key={w.transaction_id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-4 py-4 text-sm text-slate-600">
                            {new Date(w.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                          </td>
                          <td className="px-4 py-4">
                            <p className="text-sm font-medium text-slate-900">{w.beneficiary_data?.full_name}</p>
                            <p className="text-xs text-slate-500">{w.beneficiary_data?.bank}</p>
                          </td>
                          <td className="px-4 py-4">
                            <p className="text-sm font-semibold text-slate-900">{w.amount_input?.toFixed(2)} RIS</p>
                            <p className="text-xs text-slate-500">{w.amount_output?.toFixed(2)} VES</p>
                          </td>
                          <td className="px-4 py-4">{getStatusBadge(w.status)}</td>
                          <td className="px-4 py-4">
                            {w.status === 'pending' && (
                              <div className="flex gap-2">
                                <button
                                  onClick={() => { setSelectedItem(w); setShowProcessModal(true); }}
                                  className="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-xs font-medium transition-colors"
                                >
                                  Procesar
                                </button>
                                <button
                                  onClick={() => handleRejectWithdrawal(w.transaction_id)}
                                  className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-medium transition-colors"
                                >
                                  Rechazar
                                </button>
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
          <div className="space-y-4">
            {loading ? (
              <div className="bg-white rounded-2xl p-12 flex justify-center">
                <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
              </div>
            ) : recharges.length === 0 ? (
              <div className="bg-white rounded-2xl p-12 text-center">
                <p className="text-slate-500">No hay recargas pendientes</p>
              </div>
            ) : (
              <div className="grid gap-4">
                {recharges.map((r) => (
                  <div key={r.transaction_id} className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-slate-900">{r.user_email}</p>
                        <p className="text-sm text-slate-500">{r.amount_input} VES → {r.amount_output?.toFixed(2)} RIS</p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleApproveRecharge(r.transaction_id)}
                          className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-xl text-sm font-medium transition-colors"
                        >
                          Aprobar
                        </button>
                        <button className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-medium transition-colors">
                          Rechazar
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            {loading ? (
              <div className="p-12 flex justify-center">
                <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Usuario</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Balance</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Estado</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Rol</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {users.map((u) => (
                      <tr key={u.user_id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-4">
                          <p className="text-sm font-medium text-slate-900">{u.name}</p>
                          <p className="text-xs text-slate-500">{u.email}</p>
                        </td>
                        <td className="px-4 py-4 text-sm font-semibold text-slate-900">{u.balance_ris?.toFixed(2)} RIS</td>
                        <td className="px-4 py-4">
                          {u.verification_status === 'verified' ? (
                            <span className="px-2.5 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium">Verificado</span>
                          ) : (
                            <span className="px-2.5 py-1 bg-slate-100 text-slate-600 rounded-full text-xs font-medium">Pendiente</span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-sm text-slate-600 capitalize">{u.role || 'user'}</td>
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
          <div className="space-y-4">
            {loading ? (
              <div className="bg-white rounded-2xl p-12 flex justify-center">
                <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
              </div>
            ) : kycPending.length === 0 ? (
              <div className="bg-white rounded-2xl p-12 text-center">
                <p className="text-slate-500">No hay verificaciones pendientes</p>
              </div>
            ) : (
              kycPending.map((k) => (
                <div key={k.verification_id} className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
                  <div className="flex items-start gap-4">
                    {k.selfie_image && (
                      <img src={k.selfie_image} alt="Selfie" className="w-20 h-20 rounded-xl object-cover" />
                    )}
                    <div className="flex-1">
                      <h3 className="font-semibold text-slate-900">{k.full_name}</h3>
                      <p className="text-sm text-slate-500">{k.email}</p>
                      <p className="text-sm text-slate-600 mt-1">CPF: {k.cpf_number} • Doc: {k.document_number}</p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleKycDecision(k.verification_id, true)}
                        className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-xl text-sm font-medium transition-colors"
                      >
                        Aprobar
                      </button>
                      <button
                        onClick={() => handleKycDecision(k.verification_id, false, 'Documentos no válidos')}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-medium transition-colors"
                      >
                        Rechazar
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Rates Tab */}
        {activeTab === 'rates' && (
          <div className="max-w-lg">
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
              <h3 className="font-semibold text-slate-900 mb-6">Configurar Tasas de Cambio</h3>
              
              <div className="bg-slate-50 rounded-xl p-4 mb-6">
                <p className="text-sm text-slate-500 mb-1">Tasa actual</p>
                <p className="text-2xl font-bold text-slate-900">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">Nueva tasa (VES por 1 RIS)</label>
                  <input
                    type="number"
                    value={newRate}
                    onChange={(e) => setNewRate(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500"
                    placeholder={rates.ris_to_ves.toString()}
                  />
                </div>
                <button
                  onClick={handleUpdateRate}
                  className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl transition-colors"
                >
                  Actualizar tasa
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Process Withdrawal Modal */}
      {showProcessModal && selectedItem && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md animate-slideUp">
            <h3 className="font-bold text-slate-900 text-lg mb-4">Procesar Retiro</h3>
            
            <div className="bg-slate-50 rounded-xl p-4 mb-4">
              <p className="text-sm text-slate-500">Beneficiario</p>
              <p className="font-medium text-slate-900">{selectedItem.beneficiary_data?.full_name}</p>
              <p className="text-sm text-slate-600">{selectedItem.beneficiary_data?.bank}</p>
              <p className="text-sm text-slate-600">{selectedItem.beneficiary_data?.account_number}</p>
              <p className="font-bold text-lg text-slate-900 mt-2">{selectedItem.amount_output?.toFixed(2)} VES</p>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-slate-700 mb-2">Comprobante de pago</label>
              <input type="file" accept="image/*" onChange={handleFileChange} className="w-full" />
              {proofImage && <img src={proofImage} alt="Comprobante" className="mt-2 rounded-lg max-h-40 object-contain" />}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => { setShowProcessModal(false); setSelectedItem(null); setProofImage(null); }}
                className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-xl transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleProcessWithdrawal}
                disabled={!proofImage}
                className="flex-1 py-3 bg-green-600 hover:bg-green-700 text-white font-medium rounded-xl transition-colors disabled:opacity-50"
              >
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
