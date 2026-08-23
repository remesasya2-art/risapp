import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Copy, Share2, Users, DollarSign, TrendingUp, Gift, Check } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { fmt } from '../utils/format';

export default function PartnerDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const response = await api.get('/partner/dashboard');
      setData(response.data);
    } catch (error) {
      console.error('Error loading partner dashboard:', error);
      if (error.response?.status === 403) {
        toast.error('No tienes acceso a esta sección');
        navigate('/');
      } else {
        toast.error('Error al cargar el panel');
      }
    } finally {
      setLoading(false);
    }
  };

  const copyLink = () => {
    if (data?.referral_link) {
      navigator.clipboard.writeText(data.referral_link);
      setCopied(true);
      toast.success('¡Enlace copiado!');
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const shareLink = async () => {
    if (navigator.share && data?.referral_link) {
      try {
        await navigator.share({
          title: 'Únete a RIS App',
          text: '¡Regístrate en RIS App usando mi código de referido y empieza a operar fácilmente!',
          url: data.referral_link
        });
      } catch (error) {
        copyLink();
      }
    } else {
      copyLink();
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

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <div style={{ width: '40px', height: '40px', border: '3px solid #e5e7eb', borderTopColor: '#6366f1', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={pageStyle}>
        <div style={headerStyle}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }}>
            <ArrowLeft style={{ width: '24px', height: '24px', color: '#111827' }} />
          </button>
          <h1 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Panel de Socio</h1>
        </div>
        <div style={{ padding: '20px', textAlign: 'center' }}>
          <p style={{ color: '#6b7280' }}>No se pudo cargar la información</p>
        </div>
      </div>
    );
  }

  return (
    <div style={pageStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }} data-testid="back-btn">
          <ArrowLeft style={{ width: '24px', height: '24px', color: '#111827' }} />
        </button>
        <h1 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Panel de Socio</h1>
      </div>

      <div style={{ padding: '20px' }}>
        {/* Referral Link Card */}
        <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)', color: '#ffffff' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <Gift style={{ width: '24px', height: '24px' }} />
            <span style={{ fontSize: '16px', fontWeight: '600' }}>Tu enlace de referido</span>
          </div>
          
          <div style={{ 
            backgroundColor: 'rgba(255,255,255,0.15)', 
            borderRadius: '12px', 
            padding: '12px 16px',
            marginBottom: '16px',
            fontSize: '14px',
            wordBreak: 'break-all'
          }}>
            {data.referral_link}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <span style={{ fontSize: '14px', opacity: 0.9 }}>Código:</span>
            <span style={{ fontSize: '18px', fontWeight: '700', letterSpacing: '2px' }}>{data.referral_code}</span>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={copyLink}
              style={{
                flex: 1,
                padding: '14px',
                backgroundColor: 'rgba(255,255,255,0.2)',
                border: 'none',
                borderRadius: '12px',
                color: '#ffffff',
                fontSize: '15px',
                fontWeight: '600',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px'
              }}
              data-testid="copy-link-btn"
            >
              {copied ? <Check size={20} /> : <Copy size={20} />}
              {copied ? 'Copiado' : 'Copiar'}
            </button>
            <button
              onClick={shareLink}
              style={{
                flex: 1,
                padding: '14px',
                backgroundColor: '#ffffff',
                border: 'none',
                borderRadius: '12px',
                color: '#6366f1',
                fontSize: '15px',
                fontWeight: '600',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px'
              }}
              data-testid="share-link-btn"
            >
              <Share2 size={20} />
              Compartir
            </button>
          </div>
        </div>

        {/* Stats Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <Users style={{ width: '20px', height: '20px', color: '#6366f1' }} />
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Referidos</span>
            </div>
            <p style={{ fontSize: '28px', fontWeight: '700', color: '#111827', margin: 0 }}>
              {data.stats.total_referrals}
            </p>
            <p style={{ fontSize: '12px', color: '#16a34a', margin: '4px 0 0 0' }}>
              {data.stats.active_referrals} activos
            </p>
          </div>

          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <DollarSign style={{ width: '20px', height: '20px', color: '#16a34a' }} />
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Ganancias</span>
            </div>
            <p style={{ fontSize: '28px', fontWeight: '700', color: '#111827', margin: 0 }}>
              RI$ {fmt(data.stats.total_earnings)}
            </p>
            <p style={{ fontSize: '12px', color: '#6366f1', margin: '4px 0 0 0' }}>
              Este mes: RI$ {fmt(data.stats.month_earnings)}
            </p>
          </div>
        </div>

        {/* How it works */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
            ¿Cómo funciona?
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', backgroundColor: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontSize: '14px', fontWeight: '600', color: '#6366f1' }}>1</span>
              </div>
              <div>
                <p style={{ fontSize: '14px', fontWeight: '500', color: '#111827', margin: 0 }}>Comparte tu enlace</p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>Invita a amigos y familiares</p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', backgroundColor: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontSize: '14px', fontWeight: '600', color: '#6366f1' }}>2</span>
              </div>
              <div>
                <p style={{ fontSize: '14px', fontWeight: '500', color: '#111827', margin: 0 }}>Ellos se registran</p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>Usando tu código de referido</p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontSize: '14px', fontWeight: '600', color: '#16a34a' }}>$</span>
              </div>
              <div>
                <p style={{ fontSize: '14px', fontWeight: '500', color: '#111827', margin: 0 }}>Ganas comisiones</p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>5 RI$ al alcanzar 100 RI$ + 1% por recarga</p>
              </div>
            </div>
          </div>
        </div>

        {/* Referrals List */}
        {data.referrals.length > 0 && (
          <div style={cardStyle}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
              Mis Referidos ({data.referrals.length})
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {data.referrals.map((ref, index) => (
                <div 
                  key={index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px',
                    backgroundColor: '#f9fafb',
                    borderRadius: '12px'
                  }}
                >
                  <div>
                    <p style={{ fontSize: '14px', fontWeight: '500', color: '#111827', margin: 0 }}>{ref.name}</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                      Recargado: RI$ {fmt(ref.total_recharged)}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    {ref.milestone_reached ? (
                      <span style={{ fontSize: '12px', color: '#16a34a', fontWeight: '500' }}>✅ Activo</span>
                    ) : (
                      <span style={{ fontSize: '12px', color: '#f59e0b', fontWeight: '500' }}>⏳ {fmt((100 - ref.total_recharged))} RI$ para bono</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Earnings */}
        {data.recent_earnings.length > 0 && (
          <div style={cardStyle}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
              Ganancias Recientes
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {data.recent_earnings.map((earning, index) => (
                <div 
                  key={index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px',
                    backgroundColor: '#f0fdf4',
                    borderRadius: '10px'
                  }}
                >
                  <div>
                    <p style={{ fontSize: '14px', fontWeight: '500', color: '#111827', margin: 0 }}>
                      {earning.type === 'referral_milestone_bonus' ? '🎉 Bono de hito' : '💰 Comisión'}
                    </p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                      De: {earning.referred_user_name}
                    </p>
                  </div>
                  <span style={{ fontSize: '16px', fontWeight: '700', color: '#16a34a' }}>
                    +RI$ {fmt(earning.amount)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
