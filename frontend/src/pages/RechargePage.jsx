import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, CreditCard, Check, Loader2, Wallet, 
  ChevronRight, AlertCircle, CheckCircle, DollarSign
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function RechargePage() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [searchParams] = useSearchParams();
  
  const [amountUsd, setAmountUsd] = useState('');
  const [minAmount, setMinAmount] = useState(5);
  const [maxAmount, setMaxAmount] = useState(1000);
  const [forTerceros, setForTerceros] = useState(false);
  const [loading, setLoading] = useState(false);
  
  // Payment status check
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [paymentResult, setPaymentResult] = useState(null);
  
  // Check for return from Stripe
  const sessionId = searchParams.get('session_id');

  // Load rate info
  useEffect(() => {
    const loadInfo = async () => {
      try {
        const res = await api.get('/payments/stripe/rate');
        setMinAmount(res.data.min_amount || 5);
        setMaxAmount(res.data.max_amount || 1000);
      } catch (error) {
        console.error('Error loading info:', error);
      }
    };
    loadInfo();
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
          total_received: res.data.total_received,
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
    const amount = parseFloat(amountUsd);
    if (!amount || amount < minAmount) {
      toast.error(`El monto mínimo es $${minAmount} USD`);
      return;
    }
    if (amount > maxAmount) {
      toast.error(`El monto máximo es $${maxAmount} USD`);
      return;
    }

    setLoading(true);
    try {
      const originUrl = window.location.origin;
      const res = await api.post('/payments/stripe/checkout', {
        amount_usd: amount,
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

  // Quick amount buttons
  const quickAmounts = [10, 25, 50, 100];

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
              ¡Recarga Exitosa!
            </h2>
            <p style={{ color: '#6b7280', margin: '0 0 24px 0' }}>
              Tu recarga ha sido procesada correctamente
            </p>
            
            <div style={{ 
              backgroundColor: '#f0fdf4', borderRadius: '16px', padding: '20px', 
              marginBottom: '16px', border: '2px solid #bbf7d0' 
            }}>
              <p style={{ color: '#16a34a', fontSize: '14px', margin: '0 0 8px 0', fontWeight: '600' }}>
                Añadido a tu cartera
              </p>
              <p style={{ fontSize: '42px', fontWeight: '700', color: '#16a34a', margin: 0 }}>
                +${paymentResult.total_received?.toFixed(2)} USD
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
              💳 Recargar con Tarjeta
            </h1>
            <p style={{ fontSize: '14px', color: 'rgba(255,255,255,0.7)', margin: 0 }}>
              Pago seguro con tarjeta de crédito/débito
            </p>
          </div>
        </div>

        {/* Current Balance */}
        <div style={{ ...cardStyle, marginBottom: '20px', background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <Wallet style={{ width: '24px', height: '24px', color: 'rgba(255,255,255,0.8)' }} />
            <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: '14px' }}>Tu Saldo Actual</span>
          </div>
          <p style={{ fontSize: '32px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
            ${(user?.balance_ris || 0).toFixed(2)} USD
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

        {/* Amount Input */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>
            ¿Cuánto deseas recargar?
          </h3>

          {/* Main Input */}
          <div style={{ 
            display: 'flex', alignItems: 'center', gap: '12px',
            backgroundColor: '#f9fafb', borderRadius: '16px', padding: '16px',
            border: '2px solid #e5e7eb', marginBottom: '16px'
          }}>
            <DollarSign style={{ width: '28px', height: '28px', color: '#6b7280' }} />
            <input
              type="number"
              value={amountUsd}
              onChange={(e) => setAmountUsd(e.target.value)}
              placeholder="0.00"
              style={{
                flex: 1,
                fontSize: '32px',
                fontWeight: '700',
                color: '#111827',
                border: 'none',
                backgroundColor: 'transparent',
                outline: 'none'
              }}
              data-testid="amount-input"
            />
            <span style={{ fontSize: '20px', fontWeight: '600', color: '#6b7280' }}>USD</span>
          </div>

          {/* Quick Amount Buttons */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '16px' }}>
            {quickAmounts.map((amount) => (
              <button
                key={amount}
                onClick={() => setAmountUsd(amount.toString())}
                style={{
                  padding: '14px 8px',
                  borderRadius: '12px',
                  border: amountUsd === amount.toString() ? '2px solid #7c3aed' : '2px solid #e5e7eb',
                  backgroundColor: amountUsd === amount.toString() ? '#faf5ff' : 'white',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '16px',
                  color: amountUsd === amount.toString() ? '#7c3aed' : '#374151'
                }}
                data-testid={`quick-amount-${amount}`}
              >
                ${amount}
              </button>
            ))}
          </div>

          {/* Info Box */}
          <div style={{ 
            backgroundColor: '#f0fdf4', borderRadius: '12px', padding: '14px',
            display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px'
          }}>
            <CheckCircle style={{ width: '20px', height: '20px', color: '#16a34a', flexShrink: 0 }} />
            <p style={{ fontSize: '14px', color: '#166534', margin: 0 }}>
              Pagas <strong>${amountUsd || '0'} USD</strong>, recibes <strong>${amountUsd || '0'} USD</strong> en tu cartera
            </p>
          </div>

          {/* Limits Info */}
          <p style={{ fontSize: '12px', color: '#9ca3af', textAlign: 'center', marginBottom: '20px' }}>
            Mínimo: ${minAmount} USD • Máximo: ${maxAmount} USD
          </p>

          {/* Checkout Button */}
          <button
            onClick={handleCheckout}
            disabled={loading || !amountUsd || parseFloat(amountUsd) < minAmount}
            style={{ 
              ...btnPrimary, 
              opacity: (loading || !amountUsd || parseFloat(amountUsd) < minAmount) ? 0.5 : 1
            }}
            data-testid="checkout-btn"
          >
            {loading ? (
              <Loader2 style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} />
            ) : (
              <>
                <CreditCard style={{ width: '20px', height: '20px' }} />
                Pagar ${amountUsd || '0'} USD
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
