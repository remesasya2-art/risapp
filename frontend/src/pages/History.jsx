import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, ArrowUpRight, ArrowDownLeft, Clock, CheckCircle, 
  XCircle, Filter, ChevronDown, Search
} from 'lucide-react';
import api from '../utils/api';

export default function History() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all, withdrawals, recharges
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
      case 'rejected': return 'Rechazado';
      default: return status;
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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-purple-600 to-purple-700 text-white">
        <div className="max-w-2xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/10 rounded-lg">
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h1 className="font-bold text-lg">Historial</h1>
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-1 px-3 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm"
            >
              <Filter className="w-4 h-4" />
              Filtrar
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {/* Filters */}
          {showFilters && (
            <div className="flex gap-2 mt-4 animate-fadeIn">
              {[
                { key: 'all', label: 'Todos' },
                { key: 'withdrawals', label: 'Envíos' },
                { key: 'recharges', label: 'Recargas' },
              ].map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    filter === f.key
                      ? 'bg-white text-purple-700'
                      : 'bg-white/10 text-white hover:bg-white/20'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-4 border-purple-600 border-t-transparent"></div>
          </div>
        ) : filteredTransactions.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center">
              <Search className="w-8 h-8 text-gray-400" />
            </div>
            <p className="text-gray-500">No hay transacciones</p>
            <p className="text-sm text-gray-400 mt-1">
              {filter !== 'all' ? 'Prueba cambiando el filtro' : 'Realiza tu primera operación'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredTransactions.map((tx) => (
              <div
                key={tx.transaction_id}
                className="bg-white rounded-2xl p-4 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-start gap-3">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                    tx.type === 'withdrawal' ? 'bg-blue-100' : 'bg-green-100'
                  }`}>
                    {tx.type === 'withdrawal' ? (
                      <ArrowUpRight className="w-6 h-6 text-blue-600" />
                    ) : (
                      <ArrowDownLeft className="w-6 h-6 text-green-600" />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-medium text-gray-900">
                          {tx.type === 'withdrawal' ? 'Envío a Venezuela' : 'Recarga'}
                        </p>
                        <p className="text-sm text-gray-500">
                          {formatDate(tx.created_at)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className={`font-bold ${tx.type === 'withdrawal' ? 'text-red-600' : 'text-green-600'}`}>
                          {tx.type === 'withdrawal' ? '-' : '+'}{tx.amount_input?.toFixed(2)} RIS
                        </p>
                        {tx.type === 'withdrawal' && tx.amount_output && (
                          <p className="text-sm text-gray-500">{tx.amount_output.toFixed(2)} VES</p>
                        )}
                      </div>
                    </div>

                    {/* Beneficiary info for withdrawals */}
                    {tx.type === 'withdrawal' && tx.beneficiary_data && (
                      <div className="mt-2 p-2 bg-gray-50 rounded-lg">
                        <p className="text-sm text-gray-600">
                          {tx.beneficiary_data.full_name} • {tx.beneficiary_data.bank}
                        </p>
                      </div>
                    )}

                    {/* Status */}
                    <div className="flex items-center gap-2 mt-2">
                      {getStatusIcon(tx.status)}
                      <span className={`text-sm font-medium ${
                        tx.status === 'completed' ? 'text-green-600' :
                        tx.status === 'pending' ? 'text-amber-600' :
                        'text-red-600'
                      }`}>
                        {getStatusText(tx.status)}
                      </span>
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
