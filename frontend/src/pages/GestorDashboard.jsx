import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, QrCode, Users, DollarSign, TrendingUp, 
  Plus, Send, CheckCircle, Clock, AlertCircle, X,
  Building, Phone, CreditCard, User
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function GestorDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [showAddBeneficiary, setShowAddBeneficiary] = useState(false);
  const [showNewTransaction, setShowNewTransaction] = useState(false);
  const [rates, setRates] = useState(null);
  
  // New beneficiary form
  const [newBeneficiary, setNewBeneficiary] = useState({
    full_name: '', phone: '', bank_name: '', account_number: '', cedula: '', notes: ''
  });
  
  // New transaction form
  const [transaction, setTransaction] = useState({
    third_party_user_id: '', beneficiary_id: '', amount_ris: '', third_party_phone: ''
  });

  useEffect(() => {
    loadDashboard();
    loadRates();
  }, []);

  const loadDashboard = async () => {
    try {
      const response = await api.get('/gestor/dashboard');
      setData(response.data);
    } catch (error) {
      console.error('Error loading gestor dashboard:', error);
      if (error.response?.status === 403) {
        toast.error('No tienes acceso a esta sección');
        navigate('/dashboard');
      }
    } finally {
      setLoading(false);
    }
  };

  const loadRates = async () => {
    try {
      const response = await api.get('/rate');
      setRates(response.data);
    } catch (error) {
      console.error('Error loading rates:', error);
    }
  };

  const handleAddBeneficiary = async (e) => {
    e.preventDefault();
    if (!newBeneficiary.full_name || !newBeneficiary.phone || !newBeneficiary.bank_name || 
        !newBeneficiary.account_number || !newBeneficiary.cedula) {
      toast.error('Completa todos los campos requeridos');
      return;
    }
    
    try {
      await api.post('/gestor/beneficiaries', newBeneficiary);
      toast.success('Beneficiario agregado exitosamente');
      setShowAddBeneficiary(false);
      setNewBeneficiary({ full_name: '', phone: '', bank_name: '', account_number: '', cedula: '', notes: '' });
      loadDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al agregar beneficiario');
    }
  };

  const handleProcessTransaction = async (e) => {
    e.preventDefault();
    if (!transaction.third_party_user_id || !transaction.beneficiary_id || !transaction.amount_ris) {
      toast.error('Completa todos los campos requeridos');
      return;
    }
    
    const amountRis = parseFloat(transaction.amount_ris);
    if (amountRis <= 0) {
      toast.error('El monto debe ser mayor a 0');
      return;
    }
    
    if (amountRis > (data?.balance_ris || 0)) {
      toast.error('Saldo insuficiente');
      return;
    }
    
    // Calculate VES amount
    const vesRate = rates?.ris_to_ves || 110;
    const amountVes = amountRis * vesRate;
    
    try {
      const response = await api.post('/gestor/process-transaction', {
        third_party_user_id: transaction.third_party_user_id,
        beneficiary_id: transaction.beneficiary_id,
        amount_ris: amountRis,
        amount_ves: amountVes,
        third_party_phone: transaction.third_party_phone || null
      });
      
      toast.success(`Transacción registrada: ${response.data.amount_ves.toFixed(2)} VES`);
      setShowNewTransaction(false);
      setTransaction({ third_party_user_id: '', beneficiary_id: '', amount_ris: '', third_party_phone: '' });
      loadDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al procesar transacción');
    }
  };

  const pageStyle = {
    minHeight: '100vh',
    backgroundColor: '#f5f5f5',
    paddingBottom: '100px'
  };

  const headerStyle = {
    backgroundColor: '#ffffff',
    padding: '20px',
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    borderBottom: '1px solid #e5e7eb',
    position: 'sticky',
    top: 0,
    zIndex: 10
  };

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '16px',
    padding: '20px',
    marginBottom: '16px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
  };

  const modalStyle = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '20px',
    zIndex: 1000
  };

  const inputStyle = {
    width: '100%',
    padding: '14px 16px',
    borderRadius: '12px',
    border: '1px solid #d1d5db',
    fontSize: '15px',
    marginBottom: '12px'
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <div style={{ width: '40px', height: '40px', border: '3px solid #e5e7eb', borderTopColor: '#6366f1', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={pageStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }}>
          <ArrowLeft style={{ width: '24px', height: '24px', color: '#111827' }} />
        </button>
        <h1 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Panel Gestor</h1>
      </div>

      <div style={{ padding: '20px' }}>
        {/* Balance Card */}
        <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)', color: '#ffffff' }}>
          <p style={{ fontSize: '14px', opacity: 0.9, margin: '0 0 8px 0' }}>Tu saldo disponible</p>
          <p style={{ fontSize: '36px', fontWeight: '700', margin: '0 0 16px 0' }}>
            RI$ {(data?.balance_ris || 0).toFixed(2)}
          </p>
          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ backgroundColor: 'rgba(255,255,255,0.2)', padding: '8px 12px', borderRadius: '8px' }}>
              <span style={{ fontSize: '12px' }}>Comisión: {data?.commission_percentage || 5}%</span>
            </div>
            <div style={{ backgroundColor: 'rgba(255,255,255,0.2)', padding: '8px 12px', borderRadius: '8px' }}>
              <span style={{ fontSize: '12px' }}>Código: {data?.gestor_code}</span>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <Send style={{ width: '20px', height: '20px', color: '#6366f1' }} />
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Transacciones</span>
            </div>
            <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>
              {data?.stats?.total_transactions || 0}
            </p>
            <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
              Este mes: {data?.stats?.month_transactions || 0}
            </p>
          </div>

          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <TrendingUp style={{ width: '20px', height: '20px', color: '#16a34a' }} />
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Volumen</span>
            </div>
            <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>
              RI$ {(data?.stats?.total_volume || 0).toFixed(0)}
            </p>
            <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
              Este mes: RI$ {(data?.stats?.month_volume || 0).toFixed(0)}
            </p>
          </div>
        </div>

        {/* Quick Actions */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
          <button
            onClick={() => setShowNewTransaction(true)}
            style={{
              ...cardStyle,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#6366f1',
              color: '#ffffff'
            }}
          >
            <Send style={{ width: '24px', height: '24px' }} />
            <span style={{ fontSize: '14px', fontWeight: '600' }}>Nueva Transacción</span>
          </button>

          <button
            onClick={() => setShowAddBeneficiary(true)}
            style={{
              ...cardStyle,
              border: '2px solid #6366f1',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#ffffff',
              color: '#6366f1'
            }}
          >
            <Plus style={{ width: '24px', height: '24px' }} />
            <span style={{ fontSize: '14px', fontWeight: '600' }}>Agregar Beneficiario</span>
          </button>
        </div>

        {/* Beneficiaries */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
              Beneficiarios ({data?.beneficiaries?.length || 0})
            </h3>
          </div>
          
          {data?.beneficiaries?.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {data.beneficiaries.map((b, i) => (
                <div key={i} style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '10px' }}>
                  <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
                    {b.bank_name} - ***{b.account_number}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '14px', color: '#6b7280', textAlign: 'center' }}>
              No tienes beneficiarios registrados
            </p>
          )}
        </div>

        {/* Recent Transactions */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
            Transacciones Recientes
          </h3>
          
          {data?.recent_transactions?.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {data.recent_transactions.map((t, i) => (
                <div key={i} style={{ 
                  padding: '12px', 
                  backgroundColor: t.status === 'completed' ? '#f0fdf4' : '#fefce8', 
                  borderRadius: '10px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div>
                    <p style={{ fontSize: '14px', fontWeight: '500', color: '#111827', margin: 0 }}>
                      {t.beneficiary_name}
                    </p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                      Para: {t.third_party_name}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>
                      {t.amount_ves?.toFixed(2)} VES
                    </p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', justifyContent: 'flex-end' }}>
                      {t.status === 'completed' ? (
                        <CheckCircle style={{ width: '14px', height: '14px', color: '#16a34a' }} />
                      ) : (
                        <Clock style={{ width: '14px', height: '14px', color: '#f59e0b' }} />
                      )}
                      <span style={{ fontSize: '11px', color: t.status === 'completed' ? '#16a34a' : '#f59e0b' }}>
                        {t.status === 'completed' ? 'Completado' : 'Pendiente'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '14px', color: '#6b7280', textAlign: 'center' }}>
              No hay transacciones recientes
            </p>
          )}
        </div>
      </div>

      {/* Add Beneficiary Modal */}
      {showAddBeneficiary && (
        <div style={modalStyle} onClick={() => setShowAddBeneficiary(false)}>
          <div 
            style={{ 
              backgroundColor: '#ffffff', 
              borderRadius: '20px', 
              width: '100%', 
              maxWidth: '400px',
              maxHeight: '90vh',
              overflow: 'auto'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', margin: 0 }}>Agregar Beneficiario</h3>
              <button onClick={() => setShowAddBeneficiary(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                <X style={{ width: '24px', height: '24px', color: '#6b7280' }} />
              </button>
            </div>
            
            <form onSubmit={handleAddBeneficiary} style={{ padding: '20px' }}>
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Nombre completo *</label>
              </div>
              <input
                type="text"
                value={newBeneficiary.full_name}
                onChange={(e) => setNewBeneficiary({...newBeneficiary, full_name: e.target.value})}
                placeholder="Juan Pérez"
                style={inputStyle}
              />
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Teléfono *</label>
              </div>
              <input
                type="tel"
                value={newBeneficiary.phone}
                onChange={(e) => setNewBeneficiary({...newBeneficiary, phone: e.target.value})}
                placeholder="+58 412 1234567"
                style={inputStyle}
              />
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Banco *</label>
              </div>
              <input
                type="text"
                value={newBeneficiary.bank_name}
                onChange={(e) => setNewBeneficiary({...newBeneficiary, bank_name: e.target.value})}
                placeholder="Banco de Venezuela"
                style={inputStyle}
              />
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Número de cuenta *</label>
              </div>
              <input
                type="text"
                value={newBeneficiary.account_number}
                onChange={(e) => setNewBeneficiary({...newBeneficiary, account_number: e.target.value})}
                placeholder="0102 1234 5678 9012"
                style={inputStyle}
              />
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Cédula *</label>
              </div>
              <input
                type="text"
                value={newBeneficiary.cedula}
                onChange={(e) => setNewBeneficiary({...newBeneficiary, cedula: e.target.value})}
                placeholder="V-12345678"
                style={inputStyle}
              />
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Notas (opcional)</label>
              </div>
              <input
                type="text"
                value={newBeneficiary.notes}
                onChange={(e) => setNewBeneficiary({...newBeneficiary, notes: e.target.value})}
                placeholder="Notas adicionales..."
                style={inputStyle}
              />
              
              <button
                type="submit"
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: '#6366f1',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '15px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  marginTop: '8px'
                }}
              >
                Guardar Beneficiario
              </button>
            </form>
          </div>
        </div>
      )}

      {/* New Transaction Modal */}
      {showNewTransaction && (
        <div style={modalStyle} onClick={() => setShowNewTransaction(false)}>
          <div 
            style={{ 
              backgroundColor: '#ffffff', 
              borderRadius: '20px', 
              width: '100%', 
              maxWidth: '400px',
              maxHeight: '90vh',
              overflow: 'auto'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', margin: 0 }}>Nueva Transacción</h3>
              <button onClick={() => setShowNewTransaction(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                <X style={{ width: '24px', height: '24px', color: '#6b7280' }} />
              </button>
            </div>
            
            <form onSubmit={handleProcessTransaction} style={{ padding: '20px' }}>
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>ID Usuario (tercero) *</label>
              </div>
              <input
                type="text"
                value={transaction.third_party_user_id}
                onChange={(e) => setTransaction({...transaction, third_party_user_id: e.target.value})}
                placeholder="user_abc123..."
                style={inputStyle}
              />
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Teléfono tercero (WhatsApp)</label>
              </div>
              <input
                type="tel"
                value={transaction.third_party_phone}
                onChange={(e) => setTransaction({...transaction, third_party_phone: e.target.value})}
                placeholder="+55 95 99999999"
                style={inputStyle}
              />
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Beneficiario *</label>
              </div>
              <select
                value={transaction.beneficiary_id}
                onChange={(e) => setTransaction({...transaction, beneficiary_id: e.target.value})}
                style={{ ...inputStyle, backgroundColor: '#ffffff' }}
              >
                <option value="">Seleccionar beneficiario...</option>
                {data?.beneficiaries?.map((b) => (
                  <option key={b.beneficiary_id} value={b.beneficiary_id}>
                    {b.full_name} - {b.bank_name}
                  </option>
                ))}
              </select>
              
              <div style={{ marginBottom: '4px' }}>
                <label style={{ fontSize: '13px', fontWeight: '500', color: '#374151' }}>Monto en RI$ *</label>
              </div>
              <input
                type="number"
                value={transaction.amount_ris}
                onChange={(e) => setTransaction({...transaction, amount_ris: e.target.value})}
                placeholder="100.00"
                step="0.01"
                min="1"
                style={inputStyle}
              />
              
              {transaction.amount_ris && rates && (
                <div style={{ padding: '12px', backgroundColor: '#f0fdf4', borderRadius: '10px', marginBottom: '16px' }}>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 4px 0' }}>El beneficiario recibirá:</p>
                  <p style={{ fontSize: '20px', fontWeight: '700', color: '#16a34a', margin: 0 }}>
                    {(parseFloat(transaction.amount_ris || 0) * (rates?.ris_to_ves || 110)).toFixed(2)} VES
                  </p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
                    Comisión: {data?.commission_percentage || 5}%
                  </p>
                </div>
              )}
              
              <button
                type="submit"
                disabled={!transaction.third_party_user_id || !transaction.beneficiary_id || !transaction.amount_ris}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: '#6366f1',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '15px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  opacity: (!transaction.third_party_user_id || !transaction.beneficiary_id || !transaction.amount_ris) ? 0.5 : 1
                }}
              >
                Procesar Transacción
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
