import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, CreditCard, Check, Loader2, Gift, Wallet, 
  ChevronRight, AlertCircle, CheckCircle, RefreshCw, DollarSign
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function RechargePage() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [searchParams] = useSearchParams();
  
  const [packages, setPackages] = useState([]);
  const [currentRate, setCurrentRate] = useState(5.5);
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [forTerceros, setForTerceros] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingPackages, setLoadingPackages] = useState(true);
  
  // Payment status check
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [paymentResult, setPaymentResult] = useState(null);
  
  // Check for return from Stripe
  const sessionId = searchParams.get('session_id');

  // Load packages
  useEffect(() => {
    const loadPackages = async () => {
      try {
        const res = await api.get('/payments/stripe/packages');
        setPackages(res.data.packages || []);
        setCurrentRate(res.data.current_rate || 5.5);
      } catch (error) {
        console.error('Error loading packages:', error);
        toast.error('Error al cargar paquetes');
      } finally {
        setLoadingPackages(false);
      }
    };
    loadPackages();
  }, []);

  // Poll payment status if returning from Stripe
  useEffect(() => {
    if (sessionId && !paymentResult) {
      pollPaymentStatus(sessionId);
    }
  }, [sessionId]);

  const pollPaymentStatus = async (sid, attempts = 0) => {
    const maxAttempts = 10;
    const pollInterval = 2000;

    if (attempts >= maxAttempts) {
      setPaymentResult({ status: 'timeout', message: 'No pudimos confirmar tu pago. Revisa tu saldo.' });
      setCheckingStatus(false);
      return;
    }

    setCheckingStatus(true);

    try {
      const res = await api.get(`/payments/stripe/status/${sid}`);
      
      if (res.data.payment_status === 'paid') {
        setPaymentResult({
          status: 'success',
          amount_usd: res.data.amount_usd,
          amount_ris: res.data.amount_ris,
          message: res.data.message
        });
        setCheckingStatus(false);
        await refreshUser();
        toast.success('¡Pago exitoso!');
        return;
      } else if (res.data.status === 'expired') {
        setPaymentResult({ status: 'expired', message: 'La sesión de pago ha expirado.' });
        setCheckingStatus(false);
        return;
      }

      // Continue polling
      setTimeout(() => pollPaymentStatus(sid, attempts + 1), pollInterval);
    } catch (error) {
      console.error('Error checking status:', error);
      setTimeout(() => pollPaymentStatus(sid, attempts + 1), pollInterval);
    }
  };

  const handleCheckout = async () => {
    if (!selectedPackage) {
      toast.error('Selecciona un paquete');
      return;
    }

    setLoading(true);
    try {
      const originUrl = window.location.origin;
      const res = await api.post('/payments/stripe/checkout', {
        package_id: selectedPackage.id,
        origin_url: originUrl,
        for_terceros: forTerceros
      });

      if (res.data.checkout_url) {
        window.location.href = res.data.checkout_url;
      }
    } catch (error) {
      console.error('Checkout error:', error);
      toast.error(error.response?.data?.detail || 'Error al iniciar pago');
      setLoading(false);
    }
  };

  // Styles
  const pageStyle = { 
    minHeight: '100vh', 
    background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
    fontFamily: 'Inter, sans-serif'
  };
  const cardStyle = { 
    backgroundColor: '#ffffff', 
    borderRadius: '20px', 
    boxShadow: '0 10px 40px rgba(0,0,0,0.1)', 
    padding: '24px' 
  };
  const btnPrimary = { 
    width: '100%', 
    padding: '18px', 
    borderRadius: '16px', 
    border: 'none', 
    background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)', 
    color: 'white', 
    fontSize: '16px', 
    fontWeight: '700', 
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px'
  };

  // Payment Success View
  if (paymentResult?.status === 'success') {
    return (
      <div style={pageStyle}>
        <div style={{ padding: '24px', maxWidth: '500px', margin: '0 auto' }}>
          <div style={{ ...cardStyle, textAlign: 'center', marginTop: '60px' }}>
            <div style={{ 
              width: '100px', height: '100px', borderRadius: '50%', 
              background: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 24px'
            }}>
              <CheckCircle style={{ width: '50px', height: '50px', color: '#16a34a' }} />
            </div>
            
            <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#16a34a', margin: '0 0 8px 0' }}>
              ¡Pago Exitoso!
            </h2>
            <p style={{ color: '#6b7280', margin: '0 0 24px 0' }}>
              Tu recarga desde USA ha sido procesada correctamente
            </p>
            
            <div style={{ 
              backgroundColor: '#f0fdf4', borderRadius: '16px', padding: '20px', 
              marginBottom: '16px', border: '2px solid #bbf7d0' 
            }}>
              <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 4px 0' }}>
                Pagaste
              </p>
              <p style={{ fontSize: '24px', fontWeight: '700', color: '#374151', margin: '0 0 12px 0' }}>
                ${paymentResult.amount_usd?.toFixed(2)} USD
              </p>
              <p style={{ color: '#16a34a', fontSize: '14px', margin: '0 0 4px 0', fontWeight: '600' }}>
                Añadido a tu saldo
              </p>
              <p style={{ fontSize: '36px', fontWeight: '700', color: '#16a34a', margin: 0 }}>
                +{paymentResult.amount_ris?.toFixed(2)} RIS
              </p>
            </div>
            
            <button 
              onClick={() => navigate('/')} 
              style={btnPrimary}
            >
              Volver al Inicio
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Checking Status View
  if (checkingStatus) {
    return (
      <div style={pageStyle}>
        <div style={{ padding: '24px', maxWidth: '500px', margin: '0 auto' }}>
          <div style={{ ...cardStyle, textAlign: 'center', marginTop: '60px' }}>
            <Loader2 style={{ 
              width: '60px', height: '60px', color: '#7c3aed', 
              animation: 'spin 1s linear infinite', margin: '0 auto 24px' 
            }} />
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: '0 0 8px 0' }}>
              Verificando tu pago...
            </h2>
            <p style={{ color: '#6b7280', margin: 0 }}>
              Por favor espera mientras confirmamos tu transacción
            </p>
          </div>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // Payment Failed/Expired View
  if (paymentResult?.status === 'expired' || paymentResult?.status === 'timeout') {
    return (
      <div style={pageStyle}>
        <div style={{ padding: '24px', maxWidth: '500px', margin: '0 auto' }}>
          <div style={{ ...cardStyle, textAlign: 'center', marginTop: '60px' }}>
            <div style={{ 
              width: '100px', height: '100px', borderRadius: '50%', 
              background: 'linear-gradient(135deg, #fee2e2 0%, #fecaca 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 24px'
            }}>
              <AlertCircle style={{ width: '50px', height: '50px', color: '#dc2626' }} />
            </div>
            
            <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#dc2626', margin: '0 0 8px 0' }}>
              Pago No Completado
            </h2>
            <p style={{ color: '#6b7280', margin: '0 0 24px 0' }}>
              {paymentResult.message}
            </p>
            
            <button 
              onClick={() => { setPaymentResult(null); navigate('/recharge/stripe'); }} 
              style={btnPrimary}
            >
              Intentar de Nuevo
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Main Recharge View
  return (
    <div style={pageStyle} data-testid="recharge-page">
      <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
          <button 
            onClick={() => navigate('/')} 
            style={{ 
              width: '44px', height: '44px', borderRadius: '12px', border: 'none', 
              backgroundColor: 'rgba(255,255,255,0.2)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}
          >
            <ArrowLeft style={{ width: '22px', height: '22px', color: '#ffffff' }} />
          </button>
          <div>
            <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              💳 Recargar con USD
            </h1>
            <p style={{ fontSize: '14px', color: 'rgba(255,255,255,0.7)', margin: 0 }}>
              Pago seguro con tarjeta desde USA
            </p>
          </div>
        </div>

        {/* Exchange Rate Info */}
        <div style={{ 
          ...cardStyle, 
          marginBottom: '20px', 
          background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
          padding: '16px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <DollarSign style={{ width: '24px', height: '24px', color: '#d97706' }} />
              <span style={{ color: '#92400e', fontSize: '14px', fontWeight: '600' }}>Tasa actual</span>
            </div>
            <span style={{ fontSize: '18px', fontWeight: '700', color: '#92400e' }}>
              $1 USD = {currentRate.toFixed(2)} RIS
            </span>
          </div>
        </div>

        {/* Current Balance */}
        <div style={{ ...cardStyle, marginBottom: '20px', background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <Wallet style={{ width: '24px', height: '24px', color: 'rgba(255,255,255,0.8)' }} />
            <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: '14px' }}>Tu Saldo Actual</span>
          </div>
          <p style={{ fontSize: '32px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
            {(user?.balance_ris || 0).toFixed(2)} RIS
          </p>
        </div>

        {/* Destination Toggle (for gestores) */}
        {user?.role === 'socio_gestor' && (
          <div style={{ ...cardStyle, marginBottom: '20px' }}>
            <p style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '12px' }}>
              Destino de la recarga:
            </p>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button 
                onClick={() => setForTerceros(false)}
                style={{ 
                  flex: 1, padding: '14px', borderRadius: '12px', border: 'none',
                  backgroundColor: !forTerceros ? '#7c3aed' : '#f3f4f6',
                  color: !forTerceros ? 'white' : '#6b7280',
                  fontWeight: '600', cursor: 'pointer'
                }}
              >
                Mi Saldo
              </button>
              <button 
                onClick={() => setForTerceros(true)}
                style={{ 
                  flex: 1, padding: '14px', borderRadius: '12px', border: 'none',
                  backgroundColor: forTerceros ? '#059669' : '#f3f4f6',
                  color: forTerceros ? 'white' : '#6b7280',
                  fontWeight: '600', cursor: 'pointer'
                }}
              >
                Saldo Terceros
              </button>
            </div>
          </div>
        )}

        {/* Packages */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
            Selecciona un Paquete
          </h3>

          {loadingPackages ? (
            <div style={{ textAlign: 'center', padding: '40px' }}>
              <RefreshCw style={{ width: '32px', height: '32px', color: '#7c3aed', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {packages.map((pkg) => (
                <button
                  key={pkg.id}
                  onClick={() => setSelectedPackage(pkg)}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '16px', borderRadius: '14px', cursor: 'pointer',
                    border: selectedPackage?.id === pkg.id ? '3px solid #7c3aed' : '2px solid #e5e7eb',
                    backgroundColor: selectedPackage?.id === pkg.id ? '#faf5ff' : 'white',
                    transition: 'all 0.2s'
                  }}
                  data-testid={`package-${pkg.id}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <div style={{ 
                      width: '48px', height: '48px', borderRadius: '12px',
                      backgroundColor: selectedPackage?.id === pkg.id ? '#7c3aed' : '#fef3c7',
                      display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}>
                      <DollarSign style={{ 
                        width: '24px', height: '24px', 
                        color: selectedPackage?.id === pkg.id ? 'white' : '#d97706' 
                      }} />
                    </div>
                    <div style={{ textAlign: 'left' }}>
                      <p style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        ${pkg.amount_usd.toFixed(0)} USD
                      </p>
                      {pkg.bonus_percent > 0 && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                          <Gift style={{ width: '14px', height: '14px', color: '#16a34a' }} />
                          <span style={{ fontSize: '12px', color: '#16a34a', fontWeight: '600' }}>
                            +{pkg.bonus_percent}% bonus
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 2px 0' }}>Recibes</p>
                    <p style={{ fontSize: '20px', fontWeight: '700', color: '#16a34a', margin: 0 }}>
                      {pkg.total_ris.toFixed(0)} RIS
                    </p>
                    {pkg.bonus_ris > 0 && (
                      <p style={{ fontSize: '11px', color: '#059669', margin: '2px 0 0 0' }}>
                        ({pkg.base_ris.toFixed(0)} + {pkg.bonus_ris.toFixed(0)} bonus)
                      </p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Checkout Button */}
          <button
            onClick={handleCheckout}
            disabled={loading || !selectedPackage}
            style={{ 
              ...btnPrimary, 
              marginTop: '24px',
              opacity: (loading || !selectedPackage) ? 0.5 : 1
            }}
            data-testid="checkout-btn"
          >
            {loading ? (
              <Loader2 style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} />
            ) : (
              <>
                <CreditCard style={{ width: '20px', height: '20px' }} />
                Pagar con Tarjeta (USD)
                <ChevronRight style={{ width: '20px', height: '20px' }} />
              </>
            )}
          </button>

          {/* Security Note */}
          <div style={{ 
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
            marginTop: '16px', color: '#9ca3af', fontSize: '12px'
          }}>
            <Check style={{ width: '14px', height: '14px' }} />
            <span>Pago seguro procesado por Stripe</span>
          </div>
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
