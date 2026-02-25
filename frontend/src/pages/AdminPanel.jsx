import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Settings, Users, CreditCard, ArrowUpRight, 
  ArrowDownLeft, TrendingUp, Search, Filter, ChevronDown,
  CheckCircle, XCircle, Clock, Eye, RefreshCw, Download,
  Shield, AlertCircle, MoreVertical, Edit, Trash2
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

const TABS = [
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
  const [activeTab, setActiveTab] = useState('withdrawals');
  const [loading, setLoading] = useState(true);
  
  // Data states
  const [withdrawals, setWithdrawals] = useState([]);
  const [recharges, setRecharges] = useState([]);
  const [users, setUsers] = useState([]);
  const [kycPending, setKycPending] = useState([]);
  
  // Filters
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Modal states
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
        case 'withdrawals':
          const wRes = await api.get('/admin/withdrawals/all');
          setWithdrawals(wRes.data || []);
          break;
        case 'recharges':
          const rRes = await api.get('/admin/recharges/pending');
          setRecharges(rRes.data || []);
          break;
        case 'users':
          const uRes = await api.get('/admin/users');
          setUsers(uRes.data.users || []);
          break;
        case 'kyc':
          const kRes = await api.get('/admin/kyc/pending');
          setKycPending(kRes.data || []);
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
      await api.post(`/admin/recharges/${txId}/approve`);
      toast.success('Recarga aprobada');
      loadData();
    } catch (error) {
      toast.error('Error al aprobar');
    }
  };

  const handleKycDecision = async (userId, approved, reason = '') => {
    try {
      await api.post('/admin/kyc/decision', {
        user_id: userId,
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
      await api.post('/admin/rate', { ris_to_ves: parseFloat(newRate) });
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
    switch (status) {
      case 'completed':
        return <span className="px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium">Completado</span>;
      case 'pending':
        return <span className="px-2 py-1 bg-amber-100 text-amber-700 rounded-full text-xs font-medium">Pendiente</span>;
      case 'rejected':
        return <span className="px-2 py-1 bg-red-100 text-red-700 rounded-full text-xs font-medium">Rechazado</span>;
      default:
        return <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded-full text-xs font-medium">{status}</span>;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-gradient-to-r from-slate-800 to-slate-900 text-white">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/')} className="p-2 hover:bg-white/10 rounded-lg">
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div>
                <h1 className="font-bold text-lg">Panel de Administración</h1>
                <p className="text-slate-300 text-sm">{user?.role === 'super_admin' ? 'Super Admin' : 'Admin'}</p>
              </div>
            </div>
            <button onClick={loadData} className="p-2 hover:bg-white/10 rounded-lg">
              <RefreshCw className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex overflow-x-auto scrollbar-hide">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors whitespace-nowrap ${
                  activeTab === tab.key
                    ? 'border-slate-800 text-slate-800'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Withdrawals Tab */}
        {activeTab === 'withdrawals' && (
          <div className="space-y-4">
            {/* Filters */}
            <div className="bg-white rounded-xl p-4 shadow-sm flex flex-wrap gap-4">
              <div className="flex-1 min-w-[200px]">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Buscar por beneficiario..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 rounded-lg border border-gray-200 focus:ring-2 focus:ring-slate-500"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                {['all', 'pending', 'completed', 'rejected'].map((status) => (
                  <button
                    key={status}
                    onClick={() => setStatusFilter(status)}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      statusFilter === status
                        ? 'bg-slate-800 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {status === 'all' ? 'Todos' : 
                     status === 'pending' ? 'Pendientes' : 
                     status === 'completed' ? 'Completados' : 'Rechazados'}
                  </button>
                ))}
              </div>
            </div>

            {/* Withdrawals List */}
            {loading ? (
              <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-4 border-slate-600 border-t-transparent"></div>
              </div>
            ) : filteredWithdrawals.length === 0 ? (
              <div className="bg-white rounded-xl p-12 text-center">
                <p className="text-gray-500">No hay retiros</p>
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-50 border-b">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Fecha</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Usuario</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Beneficiario</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Monto</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Estado</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Acciones</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {filteredWithdrawals.map((w) => (
                        <tr key={w.transaction_id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-sm text-gray-600">
                            {new Date(w.created_at).toLocaleDateString('es-ES', {
                              day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
                            })}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-900">{w.user_email || w.user_id}</td>
                          <td className="px-4 py-3">
                            <p className="text-sm font-medium text-gray-900">{w.beneficiary_data?.full_name}</p>
                            <p className="text-xs text-gray-500">{w.beneficiary_data?.bank}</p>
                          </td>
                          <td className="px-4 py-3">
                            <p className="text-sm font-bold text-gray-900">{w.amount_input?.toFixed(2)} RIS</p>
                            <p className="text-xs text-gray-500">{w.amount_output?.toFixed(2)} VES</p>
                          </td>
                          <td className="px-4 py-3">{getStatusBadge(w.status)}</td>
                          <td className="px-4 py-3">
                            {w.status === 'pending' && (
                              <div className="flex gap-2">
                                <button
                                  onClick={() => { setSelectedItem(w); setShowProcessModal(true); }}
                                  className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm"
                                >
                                  Procesar
                                </button>
                                <button
                                  onClick={() => handleRejectWithdrawal(w.transaction_id)}
                                  className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm"
                                >
                                  Rechazar
                                </button>
                              </div>
                            )}
                            {w.status === 'completed' && w.proof_image && (
                              <button className="text-blue-600 hover:text-blue-700 text-sm">
                                Ver comprobante
                              </button>
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
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {loading ? (
              <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-4 border-slate-600 border-t-transparent"></div>
              </div>
            ) : recharges.length === 0 ? (
              <div className="p-12 text-center text-gray-500">No hay recargas pendientes</div>
            ) : (
              <div className="divide-y">
                {recharges.map((r) => (
                  <div key={r.transaction_id} className="p-4 hover:bg-gray-50">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-gray-900">{r.user_email}</p>
                        <p className="text-sm text-gray-500">
                          {r.amount_input} VES → {r.amount_output?.toFixed(2)} RIS
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleApproveRecharge(r.transaction_id)}
                          className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm"
                        >
                          Aprobar
                        </button>
                        <button className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm">
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
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {loading ? (
              <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-4 border-slate-600 border-t-transparent"></div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Usuario</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Balance</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Estado</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rol</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {users.map((u) => (
                      <tr key={u.user_id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <p className="font-medium text-gray-900">{u.name}</p>
                          <p className="text-sm text-gray-500">{u.email}</p>
                        </td>
                        <td className="px-4 py-3 font-medium">{u.balance_ris?.toFixed(2)} RIS</td>
                        <td className="px-4 py-3">
                          {u.verification_status === 'verified' ? (
                            <span className="px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs">Verificado</span>
                          ) : (
                            <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded-full text-xs">Pendiente</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600">{u.role || 'user'}</td>
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
              <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-4 border-slate-600 border-t-transparent"></div>
              </div>
            ) : kycPending.length === 0 ? (
              <div className="bg-white rounded-xl p-12 text-center text-gray-500">
                No hay verificaciones pendientes
              </div>
            ) : (
              kycPending.map((k) => (
                <div key={k.user_id} className="bg-white rounded-xl p-6 shadow-sm">
                  <div className="flex items-start gap-4">
                    {k.selfie_image && (
                      <img src={k.selfie_image} alt="Selfie" className="w-24 h-24 rounded-xl object-cover" />
                    )}
                    <div className="flex-1">
                      <h3 className="font-bold text-gray-900">{k.full_name}</h3>
                      <p className="text-sm text-gray-500">{k.email}</p>
                      <p className="text-sm text-gray-600 mt-1">
                        CPF: {k.cpf_number} • Doc: {k.document_number}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleKycDecision(k.user_id, true)}
                        className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg"
                      >
                        Aprobar
                      </button>
                      <button
                        onClick={() => handleKycDecision(k.user_id, false, 'Documentos no válidos')}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg"
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
          <div className="bg-white rounded-xl p-6 shadow-sm max-w-md">
            <h3 className="font-bold text-gray-900 mb-4">Configurar Tasas de Cambio</h3>
            
            <div className="space-y-4">
              <div className="bg-gray-50 rounded-xl p-4">
                <p className="text-sm text-gray-500">Tasa actual</p>
                <p className="text-2xl font-bold text-gray-900">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Nueva tasa (VES por 1 RIS)</label>
                <input
                  type="number"
                  value={newRate}
                  onChange={(e) => setNewRate(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-slate-500"
                  placeholder={rates.ris_to_ves.toString()}
                />
              </div>

              <button
                onClick={handleUpdateRate}
                className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-900 text-white font-medium rounded-xl"
              >
                Actualizar tasa
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Process Withdrawal Modal */}
      {showProcessModal && selectedItem && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md animate-slideUp">
            <h3 className="font-bold text-gray-900 text-lg mb-4">Procesar Retiro</h3>
            
            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <p className="text-sm text-gray-500">Beneficiario</p>
              <p className="font-medium">{selectedItem.beneficiary_data?.full_name}</p>
              <p className="text-sm text-gray-600">{selectedItem.beneficiary_data?.bank}</p>
              <p className="text-sm text-gray-600">{selectedItem.beneficiary_data?.account_number}</p>
              <p className="font-bold text-lg mt-2">{selectedItem.amount_output?.toFixed(2)} VES</p>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">Comprobante de pago</label>
              <input
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="w-full"
              />
              {proofImage && (
                <img src={proofImage} alt="Comprobante" className="mt-2 rounded-lg max-h-40 object-contain" />
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => { setShowProcessModal(false); setSelectedItem(null); setProofImage(null); }}
                className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl"
              >
                Cancelar
              </button>
              <button
                onClick={handleProcessWithdrawal}
                disabled={!proofImage}
                className="flex-1 py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-xl disabled:opacity-50"
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
