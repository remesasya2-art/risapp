import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, ArrowUpRight, ArrowDownLeft, Clock, CheckCircle, 
  XCircle, Filter, ChevronDown, Search, History as HistoryIcon, Plus
} from 'lucide-react';
import api from '../utils/api';

export default function History() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    loadTransactions();
  }, []);

  const loadTransactions = async () => {
    try {
      const response = await api.get('/transactions');
      setTransactions(response.data || []);
    } catch (error) {
      console.error('Error loading transactions:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredTransactions = transactions.filter(tx => {
    if (filter === 'all') return true;
    if (filter === 'withdrawals') return tx.type === 'withdrawal';
    if (filter === 'recharges') return tx.type === 'recharge';
    return true;
  });

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-600" />;
      case 'pending':
      case 'pending_manual_approval':
        return <Clock className="w-5 h-5 text-amber-600" />;
      case 'rejected':
        return <XCircle className="w-5 h-5 text-red-600" />;
      default:
        return <Clock className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'completed': return 'Completado';
      case 'pending': return 'Pendiente';
      case 'pending_manual_approval': return 'En revisión';
      case 'rejected': return 'Rechazado';
      default: return status;
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-700';
      case 'pending':
      case 'pending_manual_approval':
        return 'bg-amber-100 text-amber-700';
      case 'rejected':
        return 'bg-red-100 text-red-700';
      default:
        return 'bg-gray-100 text-gray-600';
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-ES', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="min-h-screen bg-gray-50" data-testid="history-page">
      {/* Header */}
      <header className="bg-gradient-to-r from-blue-600 to-blue-700 text-white sticky top-0 z-10">
        <div className="max-w-xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button 
                onClick={() => navigate(-1)} 
                className="p-2 hover:bg-white/10 rounded-xl transition-colors"
                data-testid="back-button"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div>
                <h1 className="font-bold text-xl">Historial</h1>
                <p className="text-blue-200 text-sm">{filteredTransactions.length} transacciones</p>
              </div>
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 px-4 py-2.5 bg-white/10 hover:bg-white/20 rounded-xl text-sm font-medium transition-colors"
              data-testid="filter-button"
            >
              <Filter className="w-4 h-4" />
              Filtrar
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {/* Filters */}
          {showFilters && (
            <div className="flex gap-2 mt-4 pt-4 border-t border-white/10">
              {[
                { key: 'all', label: 'Todos', icon: '📋' },
                { key: 'withdrawals', label: 'Envíos', icon: '📤' },
                { key: 'recharges', label: 'Recargas', icon: '📥' },
              ].map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    filter === f.key
                      ? 'bg-white text-blue-700 shadow-sm'
                      : 'bg-white/10 text-white hover:bg-white/20'
                  }`}
                  data-testid={`filter-${f.key}`}
                >
                  <span>{f.icon}</span>
                  {f.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <main className="max-w-xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="animate-spin rounded-full h-10 w-10 border-4 border-blue-600 border-t-transparent"></div>
            <p className="text-gray-500 mt-4">Cargando transacciones...</p>
          </div>
        ) : filteredTransactions.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gray-100 flex items-center justify-center">
              <HistoryIcon className="w-10 h-10 text-gray-300" />
            </div>
            <h3 className="font-semibold text-gray-700 text-lg mb-1">Sin transacciones</h3>
            <p className="text-gray-500 mb-6">
              {filter !== 'all' ? 'Prueba cambiando el filtro' : 'Realiza tu primera operación para verla aquí'}
            </p>
            <div className="flex justify-center gap-3">
              <Link 
                to="/recharge"
                className="inline-flex items-center gap-2 px-5 py-3 bg-green-600 hover:bg-green-700 text-white rounded-xl font-medium transition-colors"
              >
                <Plus className="w-5 h-5" />
                Recargar saldo
              </Link>
              <Link 
                to="/send"
                className="inline-flex items-center gap-2 px-5 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-medium transition-colors"
              >
                <ArrowUpRight className="w-5 h-5" />
                Enviar remesa
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredTransactions.map((tx) => (
              <div
                key={tx.transaction_id}
                className="bg-white rounded-2xl p-5 shadow-sm hover:shadow-md transition-all border border-gray-100"
                data-testid={`transaction-${tx.transaction_id}`}
              >
                <div className="flex items-start gap-4">
                  <div className={`w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0 ${
                    tx.type === 'withdrawal' ? 'bg-blue-100' : 'bg-green-100'
                  }`}>
                    {tx.type === 'withdrawal' ? (
                      <ArrowUpRight className="w-7 h-7 text-blue-600" />
                    ) : (
                      <ArrowDownLeft className="w-7 h-7 text-green-600" />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-gray-900 text-lg">
                          {tx.type === 'withdrawal' ? 'Envío a Venezuela' : 'Recarga'}
                        </p>
                        <p className="text-sm text-gray-500 mt-0.5">
                          {formatDate(tx.created_at)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className={`text-xl font-bold ${tx.type === 'withdrawal' ? 'text-red-600' : 'text-green-600'}`}>
                          {tx.type === 'withdrawal' ? '-' : '+'}{tx.amount_input?.toFixed(2)} RIS
                        </p>
                        {tx.type === 'withdrawal' && tx.amount_output && (
                          <p className="text-sm text-gray-500 mt-0.5">{tx.amount_output.toFixed(2)} VES</p>
                        )}
                      </div>
                    </div>

                    {/* Beneficiary info for withdrawals */}
                    {tx.type === 'withdrawal' && tx.beneficiary_data && (
                      <div className="mt-3 p-3 bg-gray-50 rounded-xl">
                        <p className="text-sm text-gray-600 font-medium">
                          {tx.beneficiary_data.full_name}
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {tx.beneficiary_data.bank}
                        </p>
                      </div>
                    )}

                    {/* Status Badge */}
                    <div className="flex items-center gap-2 mt-3">
                      <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${getStatusBadge(tx.status)}`}>
                        {getStatusIcon(tx.status)}
                        {getStatusText(tx.status)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
