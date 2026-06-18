import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ArrowLeft, Plus, X, User, CheckCircle, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import { fmt } from '../utils/format';

export default function SendReais() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [amount, setAmount] = useState('');
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [newBenef, setNewBenef] = useState({ full_name: '', cpf: '', pix_key: '' });

  const balance = user?.balance_ris || 0;
  const amountNum = parseFloat(amount) || 0;
  const isValidAmount = amountNum > 0 && amountNum <= balance;

  const loadBeneficiaries = async () => {
    try {
      const res = await api.get('/beneficiaries/br');
      setBeneficiaries(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      // silencioso: lista vacía
    }
  };

  useEffect(() => { loadBeneficiaries(); }, []);

  const saveBeneficiary = async () => {
    if (!newBenef.full_name.trim() || !newBenef.cpf.trim() || !newBenef.pix_key.trim()) {
      toast.error('Completa nombre, CPF y llave PIX');
      return;
    }
    try {
      setLoading(true);
      const res = await api.post('/beneficiaries/br', {
        full_name: newBenef.full_name.trim(),
        cpf: newBenef.cpf.trim(),
        pix_key: newBenef.pix_key.trim(),
      });
      toast.success('Beneficiario guardado');
      setShowNew(false);
      setNewBenef({ full_name: '', cpf: '', pix_key: '' });
      await loadBeneficiaries();
      if (res.data?.beneficiary_id) setSelectedId(res.data.beneficiary_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al guardar beneficiario');
    } finally {
      setLoading(false);
    }
  };

  const enviar = async () => {
    if (!selectedId) { toast.error('Selecciona un beneficiario'); return; }
    if (!isValidAmount) { toast.error('Monto inválido o saldo insuficiente'); return; }
    try {
      setLoading(true);
      await api.post('/reais/send', { beneficiary_id: selectedId, amount: amountNum });
      toast.success('¡Envío a Brasil registrado! Será procesado pronto.');
      if (refreshUser) await refreshUser();
      navigate('/history');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al procesar el envío');
    } finally {
      setLoading(false);
    }
  };

  const card = {
    backgroundColor: '#fff', borderRadius: '16px', padding: '20px',
    border: '1px solid #eef0f4', marginBottom: '16px',
  };
  const inputStyle = {
    width: '100%', padding: '12px 14px', borderRadius: '10px',
    border: '1px solid #e5e7eb', fontSize: '15px', boxSizing: 'border-box',
  };
  const labelStyle = { fontSize: '13px', fontWeight: 600, color: '#374151', margin: '0 0 6px 0', display: 'block' };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F7F8FB' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px 20px', backgroundColor: '#fff', borderBottom: '1px solid #eef0f4',
      }}>
        <button onClick={() => navigate(-1)} style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px', border: 'none',
          background: 'none', cursor: 'pointer', color: '#374151', fontWeight: 600, fontSize: '15px',
        }}>
          <ArrowLeft size={18} /> Volver
        </button>
        <h1 style={{ fontSize: '17px', fontWeight: 700, color: '#111827', margin: 0 }}>Enviar a Brasil 🇧🇷</h1>
        <NotificationBell />
      </div>

      <div style={{ maxWidth: '520px', margin: '0 auto', padding: '20px' }}>
        {/* Saldo */}
        <div style={{ ...card, background: 'linear-gradient(135deg,#5B4FE9,#7A6FF0)', border: 'none' }}>
          <p style={{ color: 'rgba(255,255,255,0.8)', fontSize: '13px', margin: 0 }}>Saldo disponible</p>
          <p style={{ color: '#fff', fontSize: '28px', fontWeight: 800, margin: '4px 0 0 0' }}>RI$ {fmt(balance)}</p>
        </div>

        {/* Beneficiario */}
        <div style={card}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <h2 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', margin: 0 }}>Beneficiario en Brasil</h2>
            <button onClick={() => setShowNew((s) => !s)} style={{
              display: 'inline-flex', alignItems: 'center', gap: '5px', border: 'none', background: 'none',
              color: '#5B4FE9', fontWeight: 600, fontSize: '14px', cursor: 'pointer',
            }}>
              {showNew ? <><X size={15} /> Cancelar</> : <><Plus size={15} /> Nuevo</>}
            </button>
          </div>

          {showNew ? (
            <div>
              <label style={labelStyle}>Nombre completo</label>
              <input style={inputStyle} value={newBenef.full_name}
                onChange={(e) => setNewBenef({ ...newBenef, full_name: e.target.value })}
                placeholder="Nombre del beneficiario" />
              <div style={{ height: '12px' }} />
              <label style={labelStyle}>CPF</label>
              <input style={inputStyle} value={newBenef.cpf}
                onChange={(e) => setNewBenef({ ...newBenef, cpf: e.target.value })}
                placeholder="000.000.000-00" />
              <div style={{ height: '12px' }} />
              <label style={labelStyle}>Llave PIX</label>
              <input style={inputStyle} value={newBenef.pix_key}
                onChange={(e) => setNewBenef({ ...newBenef, pix_key: e.target.value })}
                placeholder="CPF, teléfono, email o llave aleatoria" />
              <button onClick={saveBeneficiary} disabled={loading} style={{
                width: '100%', marginTop: '16px', padding: '12px', borderRadius: '10px', border: 'none',
                backgroundColor: '#5B4FE9', color: '#fff', fontWeight: 700, cursor: 'pointer',
              }}>
                {loading ? 'Guardando…' : 'Guardar beneficiario'}
              </button>
            </div>
          ) : beneficiaries.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '24px', color: '#9ca3af' }}>
              <User size={28} style={{ marginBottom: '6px' }} />
              <p style={{ margin: 0, fontSize: '14px' }}>Aún no tienes beneficiarios en Brasil.</p>
              <p style={{ margin: '2px 0 0 0', fontSize: '13px' }}>Pulsa "Nuevo" para agregar uno.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {beneficiaries.map((b) => {
                const sel = selectedId === b.beneficiary_id;
                return (
                  <button key={b.beneficiary_id} onClick={() => setSelectedId(b.beneficiary_id)} style={{
                    textAlign: 'left', padding: '12px 14px', borderRadius: '12px', cursor: 'pointer',
                    border: sel ? '2px solid #5B4FE9' : '1px solid #e5e7eb',
                    backgroundColor: sel ? '#F5F4FF' : '#fff',
                  }}>
                    <div style={{ fontWeight: 700, color: '#111827', fontSize: '14px' }}>{b.full_name}</div>
                    <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                      CPF: {b.cpf} · PIX: {b.pix_key}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Monto */}
        {!showNew && (
          <div style={card}>
            <label style={labelStyle}>Monto a enviar (RIS)</label>
            <input
              type="number" inputMode="decimal" style={inputStyle} value={amount}
              onChange={(e) => setAmount(e.target.value)} placeholder="0,00" />
            <div style={{
              marginTop: '12px', padding: '12px 14px', backgroundColor: '#F7F8FB', borderRadius: '10px',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <span style={{ fontSize: '13px', color: '#6b7280' }}>El beneficiario recibe (1 RIS = 1 R$)</span>
              <span style={{ fontSize: '16px', fontWeight: 800, color: '#CA8A04' }}>R$ {fmt(amountNum)}</span>
            </div>
            {amount && !isValidAmount && (
              <p style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#dc2626', fontSize: '13px', margin: '10px 0 0 0' }}>
                <AlertCircle size={14} /> {amountNum > balance ? 'Saldo insuficiente' : 'Ingresa un monto válido'}
              </p>
            )}
          </div>
        )}

        {/* Enviar */}
        {!showNew && (
          <button onClick={enviar} disabled={loading || !selectedId || !isValidAmount} style={{
            width: '100%', padding: '14px', borderRadius: '12px', border: 'none',
            backgroundColor: '#5B4FE9', color: '#fff', fontWeight: 700, fontSize: '16px',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
            cursor: (selectedId && isValidAmount && !loading) ? 'pointer' : 'not-allowed',
            opacity: (selectedId && isValidAmount && !loading) ? 1 : 0.5,
          }}>
            <CheckCircle size={18} /> {loading ? 'Procesando…' : 'Enviar a Brasil'}
          </button>
        )}

        <p style={{ textAlign: 'center', fontSize: '12px', color: '#9ca3af', marginTop: '14px' }}>
          Sin comisión adicional · El pago lo procesa el equipo por PIX
        </p>
      </div>
    </div>
  );
}
