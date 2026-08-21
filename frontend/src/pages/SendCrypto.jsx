import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { ArrowLeft, ArrowRight, AlertCircle, User, ChevronDown, Copy, Clock, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { fmt } from '../utils/format';
import { QRCodeSVG } from 'qrcode.react';
import { NOWPAYMENTS_FEE_RATE, UNKNOWN_NETWORK_FEE_TEXT, estimatedNetworkFee } from '../utils/networkFees';

// Cuenta regresiva legible para el plazo del pago de la diferencia (topup).
function formatCountdown(ms) {
  if (ms == null || ms <= 0) return null;
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

const CURRENCIES = [
  { key: 'usdt', label: 'USDT', color: '#26A17B' },
  { key: 'usdc', label: 'USDC', color: '#2775CA' },
];

export default function SendCrypto() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();

  const initialCurrency = CURRENCIES.some((c) => c.key === searchParams.get('currency'))
    ? searchParams.get('currency')
    : 'usdt';

  const [currency, setCurrency] = useState(initialCurrency);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [amount, setAmount] = useState('');
  const [minAmount, setMinAmount] = useState(null);

  const [networks, setNetworks] = useState([]);
  const [network, setNetwork] = useState(null);
  const [networksLoading, setNetworksLoading] = useState(false);
  const [networkMenuOpen, setNetworkMenuOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [order, setOrder] = useState(null);
  const [paid, setPaid] = useState(false);
  // Ultima respuesta de /withdraw-crypto/{id}/status: de ahi salen los estados
  // de pago incompleto (awaiting_topup / underpaid_review) y los datos del topup.
  const [statusData, setStatusData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const pollRef = useRef(null);
  const idemRef = useRef(null);
  const topupToastRef = useRef(false);

  const cfg = CURRENCIES.find((c) => c.key === currency);
  const amountNum = parseFloat(amount);
  const rateField = currency === 'usdt' ? 'usdtris_to_ves' : 'usdcris_to_ves';
  const rate = rates?.[rateField] || 0;
  const rateAvailable = rate > 0;
  const amountVes = amountNum > 0 ? amountNum * rate : 0;

  // ---- Calculadora de costos (camino B: pago con cripto nueva) ----
  // Aritmetica local pura: no llama a ningun endpoint. Se recalcula sola en
  // cada render, o sea cada vez que cambia el monto o la red elegida.
  const nowpaymentsFee = amountNum > 0 ? amountNum * NOWPAYMENTS_FEE_RATE : 0;
  const networkFee = estimatedNetworkFee(network);
  const totalEstimado = amountNum > 0 ? amountNum + nowpaymentsFee + (networkFee ?? 0) : 0;

  const balanceField = currency === 'usdt' ? 'balance_usdt' : 'balance_usdc';
  const availableBalance = user?.[balanceField] || 0;
  const hasBalance = availableBalance > 0;
  const [useBalance, setUseBalance] = useState(availableBalance > 0);
  const userToggledRef = useRef(false);
  useEffect(() => {
    userToggledRef.current = false;
  }, [currency]);
  useEffect(() => {
    if (!userToggledRef.current) setUseBalance(availableBalance > 0);
  }, [availableBalance, currency]);

  const belowMin = !useBalance && minAmount != null && amountNum > 0 && amountNum < minAmount;
  const exceedsBalance = useBalance && amountNum > availableBalance;
  const canContinue = useBalance
    ? (amountNum > 0 && !exceedsBalance && !!selectedBeneficiary && rateAvailable && !loading)
    : (amountNum > 0 && !belowMin && !!selectedBeneficiary && !!network && rateAvailable && !loading);

  useEffect(() => { loadBeneficiaries(); }, []);

  const loadBeneficiaries = async () => {
    try {
      const response = await api.get('/beneficiaries');
      setBeneficiaries(response.data || []);
    } catch (error) {
      console.error('Error loading beneficiaries:', error);
    }
  };

  useEffect(() => {
    let cancelled = false;
    if (useBalance) { setNetworks([]); setNetwork(null); setNetworksLoading(false); return; }
    setNetworks([]);
    setNetwork(null);
    setNetworksLoading(true);
    api.get('/credits/networks', { params: { currency } })
      .then(({ data }) => {
        if (cancelled) return;
        const list = data?.networks || [];
        setNetworks(list);
        const def = list.find((n) => n.is_default) || list[0];
        setNetwork(def?.ticker || null);
      })
      .catch(() => {
        if (!cancelled) {
          const fallbackTicker = currency === 'usdc' ? 'usdc' : 'usdttrc20';
          const fallbackLabel = currency === 'usdc' ? 'Ethereum (ERC20)' : 'Tron (TRC20)';
          setNetworks([{ ticker: fallbackTicker, label: fallbackLabel, is_default: true }]);
          setNetwork(fallbackTicker);
        }
      })
      .finally(() => { if (!cancelled) setNetworksLoading(false); });
    return () => { cancelled = true; };
  }, [currency, useBalance]);

  useEffect(() => {
    let cancelled = false;
    setMinAmount(null);
    if (useBalance || !network) return;
    api.get('/credits/min-amount', { params: { currency, network } })
      .then(({ data }) => { if (!cancelled) setMinAmount(data?.min_amount || 10); })
      .catch(() => { if (!cancelled) setMinAmount(10); });
    return () => { cancelled = true; };
  }, [currency, network, useBalance]);

  const selectedNetwork = networks.find((n) => n.ticker === network);

  const handleCrear = async () => {
    if (!canContinue) return;
    if (!idemRef.current) idemRef.current = (window.crypto?.randomUUID?.() || (Date.now() + '-' + Math.random().toString(16).slice(2)));
    setLoading(true);
    try {
      const { data } = await api.post('/withdraw-crypto', {
        currency,
        amount: amountNum,
        beneficiary_id: selectedBeneficiary.beneficiary_id,
        network: useBalance ? null : network,
        use_balance: useBalance,
        idempotency_key: idemRef.current,
      });
      if (data?.funded_from === 'balance') {
        setOrder(data);
        setPaid(true);
        refreshUser();
      } else if (data?.pay_address && data?.pay_amount) {
        setOrder(data);
        setPaid(false);
      } else {
        idemRef.current = null;
        toast.error('No se pudo iniciar el pago. Intenta de nuevo.');
      }
    } catch (error) {
      idemRef.current = null;
      toast.error(error.response?.data?.detail || 'No se pudo iniciar el pago. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!order?.transaction_id || paid || failed) return;
    const checkStatus = async () => {
      try {
        const { data } = await api.get(`/withdraw-crypto/${order.transaction_id}/status`);
        if (!data?.status) return;
        setStatusData(data);

        // Sigue esperando: ni el pago original ni la diferencia cerraron todavia.
        if (data.status === 'awaiting_payment') return;
        if (data.status === 'awaiting_topup') {
          if (!topupToastRef.current) {
            topupToastRef.current = true;
            toast('Tu pago llegó incompleto. Falta completar la diferencia.', { icon: '⚠️' });
          }
          return;
        }
        // En revision manual: no hay nada que el usuario pueda hacer, pero
        // seguimos consultando por si el admin la aprueba.
        if (data.status === 'underpaid_review') return;

        if (['payment_failed', 'payment_error', 'rejected'].includes(data.status)) {
          setFailed(true);
          toast.error('El pago no se completó. La orden quedó cancelada.');
          refreshUser();
          return;
        }

        setPaid(true);
        toast.success('¡Pago recibido! Tu envío está en cola de procesamiento.');
        refreshUser();
      } catch (e) {
      }
    };
    checkStatus();
    pollRef.current = setInterval(checkStatus, 5000);
    return () => clearInterval(pollRef.current);
  }, [order?.transaction_id, paid, failed]);

  const orderStatus = statusData?.status || (order ? 'awaiting_payment' : null);

  // Reloj de 1s solo mientras hay cuenta regresiva en pantalla.
  useEffect(() => {
    if (orderStatus !== 'awaiting_topup') return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [orderStatus]);

  const topupExpiresAt = statusData?.topup_expires_at ? new Date(statusData.topup_expires_at).getTime() : null;
  const topupCountdown = topupExpiresAt ? formatCountdown(topupExpiresAt - now) : null;

  const handleCopy = (text, label) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado`);
  };

  const resetFlow = () => {
    clearInterval(pollRef.current);
    setOrder(null);
    setPaid(false);
    setFailed(false);
    setStatusData(null);
    setAmount('');
    idemRef.current = null;
    topupToastRef.current = false;
  };

  // "Cambiar monto": cancela la orden abierta en el backend antes de volver al
  // formulario, asi no queda una orden fantasma en awaiting_payment.
  const handleCambiarMonto = async () => {
    if (!order?.transaction_id || cancelling) return;
    setCancelling(true);
    try {
      await api.post(`/withdraw-crypto/${order.transaction_id}/cancelar`);
      resetFlow();
    } catch (e) {
      if (e?.response?.status === 409) {
        // Justo entro un pago en el medio: no forzamos nada. El polling que ya
        // esta corriendo trae el estado real en el proximo tick.
        toast('Justo llegó un pago para esta orden. Actualizando el estado...');
      } else {
        toast.error(e?.response?.data?.detail || 'No pudimos cancelar la orden. Intentá de nuevo.');
      }
    } finally {
      setCancelling(false);
    }
  };

  const feeRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 6 };
  const feeLabelStyle = { fontSize: '13px', color: '#6b7280', lineHeight: 1.4 };
  const feeValueStyle = { fontSize: '13px', fontWeight: 600, color: '#374151', whiteSpace: 'nowrap' };
  const cardStyle = { backgroundColor: '#fff', borderRadius: 16, border: '1px solid #eef0f4', padding: 20 };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', paddingBottom: '40px' }}>
      <header style={{ backgroundColor: '#fff', borderBottom: '1px solid #e5e7eb', padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button onClick={() => (order ? resetFlow() : navigate('/dashboard'))} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
        </button>
        <h1 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Enviar con {order ? order.currency : cfg.label}</h1>
      </header>

      <div style={{ maxWidth: '600px', margin: '24px auto', padding: '0 20px' }}>
        {!order ? (
          <>
            <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
              {CURRENCIES.map((c) => (
                <button
                  key={c.key}
                  onClick={() => setCurrency(c.key)}
                  style={{
                    flex: 1, padding: '14px', borderRadius: '14px', cursor: 'pointer',
                    border: currency === c.key ? `2px solid ${c.color}` : '1px solid #e5e7eb',
                    backgroundColor: currency === c.key ? `${c.color}14` : '#fff',
                    fontWeight: 700, fontSize: '14px', color: currency === c.key ? c.color : '#6b7280',
                  }}
                >
                  {c.label}
                </button>
              ))}
            </div>

            {hasBalance && (
              <div style={{ ...cardStyle, marginBottom: '16px' }}>
                <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', display: 'block', marginBottom: '12px' }}>
                  ¿Cómo querés enviar?
                </label>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    type="button"
                    onClick={() => { userToggledRef.current = true; setUseBalance(true); }}
                    style={{
                      flex: 1, padding: '12px', borderRadius: '12px', cursor: 'pointer', textAlign: 'left',
                      border: useBalance ? `2px solid ${cfg.color}` : '1px solid #e5e7eb',
                      backgroundColor: useBalance ? `${cfg.color}14` : '#fff',
                    }}
                  >
                    <div style={{ fontSize: '13px', fontWeight: 700, color: useBalance ? cfg.color : '#111827' }}>Usar mi saldo</div>
                    <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '2px' }}>{fmt(availableBalance)} {cfg.label} disponibles</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => { userToggledRef.current = true; setUseBalance(false); }}
                    style={{
                      flex: 1, padding: '12px', borderRadius: '12px', cursor: 'pointer', textAlign: 'left',
                      border: !useBalance ? `2px solid ${cfg.color}` : '1px solid #e5e7eb',
                      backgroundColor: !useBalance ? `${cfg.color}14` : '#fff',
                    }}
                  >
                    <div style={{ fontSize: '13px', fontWeight: 700, color: !useBalance ? cfg.color : '#111827' }}>Pagar con cripto nueva</div>
                    <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '2px' }}>Generás un pago nuevo</div>
                  </button>
                </div>
              </div>
            )}

            <div style={{ ...cardStyle, marginBottom: '16px' }}>
              <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', display: 'block', marginBottom: '12px' }}>
                Beneficiario en Venezuela
              </label>
              {beneficiaries.length === 0 ? (
                <p style={{ fontSize: '13px', color: '#6b7280' }}>
                  No tienes beneficiarios guardados todavía. Puedes crear uno desde la pantalla de{' '}
                  <a href="/send" style={{ color: '#4338ca', fontWeight: 600 }}>Enviar RIS</a> y luego volver aquí.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {beneficiaries.map((b) => (
                    <button
                      key={b.beneficiary_id}
                      onClick={() => setSelectedBeneficiary(b)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 14px', borderRadius: '10px',
                        border: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '2px solid #4338ca' : '1px solid #e5e7eb',
                        backgroundColor: selectedBeneficiary?.beneficiary_id === b.beneficiary_id ? '#eef2ff' : '#fff',
                        cursor: 'pointer', textAlign: 'left',
                      }}
                    >
                      <User size={18} color="#6b7280" />
                      <div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>{b.full_name}</div>
                        <div style={{ fontSize: '12px', color: '#6b7280' }}>{b.bank || b.payment_type} · {b.account_number || b.phone_number}</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div style={{ ...cardStyle, marginBottom: '16px' }}>
              <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', display: 'block', marginBottom: '8px' }}>
                Monto en {cfg.label}
              </label>
              <input
                type="number" step="0.01" min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '20px', outline: 'none', boxSizing: 'border-box', fontWeight: 700 }}
              />
              {minAmount != null && (
                <p style={{ fontSize: '12px', color: belowMin ? '#dc2626' : '#9ca3af', margin: '8px 0 0 0' }}>
                  Monto mínimo: {minAmount} {cfg.label}
                </p>
              )}
              {useBalance && exceedsBalance && (
                <p style={{ fontSize: '12px', color: '#dc2626', margin: '8px 0 0 0' }}>
                  Supera tu saldo disponible ({fmt(availableBalance)} {cfg.label}).
                </p>
              )}
              {!rateAvailable ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px', padding: '10px 12px', backgroundColor: '#fef2f2', borderRadius: '10px', color: '#dc2626', fontSize: '13px' }}>
                  <AlertCircle size={16} /> La tasa de {cfg.label} → VES no está configurada todavía.
                </div>
              ) : amountNum > 0 ? (
                <div style={{ marginTop: '12px', padding: '10px 12px', backgroundColor: '#f0fdf4', borderRadius: '10px', color: '#16a34a', fontSize: '14px', fontWeight: 600 }}>
                  ≈ {fmt(amountVes)} VES
                </div>
              ) : null}
            </div>

            {!useBalance && (
              <div style={{ ...cardStyle, marginBottom: '20px', position: 'relative' }}>
                <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', display: 'block', marginBottom: '8px' }}>
                  Red
                </label>
                <button
                  type="button"
                  onClick={() => setNetworkMenuOpen((v) => !v)}
                  disabled={networksLoading || networks.length === 0}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db',
                    backgroundColor: '#fff', cursor: networksLoading ? 'default' : 'pointer', fontSize: '14px', fontWeight: 600, color: '#111827',
                  }}
                >
                  <span>
                    {networksLoading ? 'Consultando redes disponibles...' : (selectedNetwork?.label || 'Selecciona una red')}
                  </span>
                  <ChevronDown style={{ width: '18px', height: '18px', transform: networkMenuOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: '#6b7280' }} />
                </button>
                {networkMenuOpen && networks.length > 0 && (
                  <div style={{
                    position: 'absolute', left: 20, right: 20, marginTop: 6, backgroundColor: '#fff',
                    border: '1px solid #e5e7eb', borderRadius: '12px', boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                    zIndex: 10, overflow: 'hidden', maxHeight: '260px', overflowY: 'auto',
                  }}>
                    {networks.map((n) => (
                      <button
                        key={n.ticker}
                        type="button"
                        onClick={() => { setNetwork(n.ticker); setNetworkMenuOpen(false); }}
                        style={{
                          width: '100%', textAlign: 'left', padding: '12px 16px', border: 'none', cursor: 'pointer',
                          backgroundColor: network === n.ticker ? '#eef2ff' : '#fff',
                          color: network === n.ticker ? '#4338ca' : '#374151',
                          fontSize: '14px', fontWeight: network === n.ticker ? 700 : 500,
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        }}
                      >
                        {n.label}
                        {n.is_default && <span style={{ fontSize: '11px', color: '#9ca3af', fontWeight: 500 }}>Por defecto</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {!useBalance && amountNum > 0 && (
              <div style={{ ...cardStyle, marginBottom: '20px' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '10px' }}>
                  Lo que vas a pagar
                </div>

                <div style={feeRowStyle}>
                  <span style={feeLabelStyle}>Monto a enviar</span>
                  <span style={feeValueStyle}>{fmt(amountNum, 2)} {cfg.label}</span>
                </div>

                <div style={feeRowStyle}>
                  <span style={feeLabelStyle}>+ Comisión de NOWPayments (~1%)</span>
                  <span style={feeValueStyle}>{fmt(nowpaymentsFee, 2)} {cfg.label}</span>
                </div>

                <div style={feeRowStyle}>
                  <span style={feeLabelStyle}>
                    + Comisión de red estimada{selectedNetwork?.label ? ` (${selectedNetwork.label})` : ''}
                  </span>
                  <span style={feeValueStyle}>
                    {networkFee !== null ? `${fmt(networkFee, 2)} ${cfg.label}` : UNKNOWN_NETWORK_FEE_TEXT}
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, borderTop: '1px solid #eef0f4', marginTop: 10, paddingTop: 10 }}>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#111827' }}>Total estimado a pagar</span>
                  <span style={{ fontSize: '16px', fontWeight: 700, color: '#111827', whiteSpace: 'nowrap' }}>
                    {networkFee === null ? 'desde ' : ''}{fmt(totalEstimado, 2)} {cfg.label}
                  </span>
                </div>

                <p style={{ fontSize: '11px', color: '#9ca3af', margin: '10px 0 0 0', lineHeight: 1.5 }}>
                  Estimado, puede variar levemente según la congestión de la red.
                </p>
              </div>
            )}
            <button
              onClick={handleCrear}
              disabled={!canContinue}
              style={{
                width: '100%', padding: '16px', borderRadius: '14px', border: 'none',
                backgroundColor: cfg.color, color: '#fff', fontWeight: 700, fontSize: '16px',
                cursor: canContinue ? 'pointer' : 'not-allowed', opacity: canContinue ? 1 : 0.5,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
              }}
            >
              {loading ? 'Generando pago...' : <>Continuar <ArrowRight size={18} /></>}
            </button>
          </>
        ) : paid ? (
          <div style={{ ...cardStyle, textAlign: 'center' }}>
            <h2 style={{ fontSize: 22, fontWeight: 700, color: '#16a34a', margin: '0 0 8px 0' }}>
              {order.funded_from === 'balance' ? '¡Envío en camino!' : '¡Pago recibido!'}
            </h2>
            <p style={{ fontSize: 14, color: '#6b7280', margin: '0 0 20px 0' }}>
              {order.funded_from === 'balance'
                ? `Se descontaron ${order.amount_crypto} ${order.currency} de tu saldo disponible. `
                : ''}
              Tu envío de {order.amount_ves ? fmt(order.amount_ves) : ''} VES a {selectedBeneficiary?.full_name} quedó en cola de procesamiento.
            </p>
            <button
              onClick={() => navigate('/history')}
              style={{ width: '100%', padding: 14, fontSize: 15, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 12, backgroundColor: '#2563eb', cursor: 'pointer' }}
            >
              Ver historial
            </button>
          </div>
        ) : failed ? (
          <div style={{ ...cardStyle, textAlign: 'center' }}>
            <XCircle size={40} color="#dc2626" style={{ marginBottom: 12 }} />
            <h2 style={{ fontSize: 22, fontWeight: 700, color: '#dc2626', margin: '0 0 8px 0' }}>El pago no se completó</h2>
            <p style={{ fontSize: 14, color: '#6b7280', margin: '0 0 20px 0' }}>
              La orden quedó cancelada. Podés generar un envío nuevo cuando quieras.
            </p>
            <button
              onClick={resetFlow}
              style={{ width: '100%', padding: 14, fontSize: 15, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 12, backgroundColor: '#2563eb', cursor: 'pointer' }}
            >
              Empezar de nuevo
            </button>
          </div>
        ) : orderStatus === 'awaiting_topup' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ ...cardStyle, textAlign: 'center' }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 14px',
                borderRadius: 999, backgroundColor: '#ffedd5', color: '#c2410c', fontSize: 13, fontWeight: 600, marginBottom: 14,
              }}>
                <AlertCircle size={14} /> Falta completar tu pago
              </div>
              <p style={{ fontSize: 13.5, color: '#6b7280', margin: '0 0 16px 0', lineHeight: 1.5 }}>
                Tu pago llegó incompleto, probablemente por la comisión de tu wallet.
                Enviá la diferencia a esta dirección y el envío se procesa automáticamente.
              </p>

              {topupCountdown && (
                <div style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px',
                  borderRadius: 999, backgroundColor: '#fef3c7', color: '#92400e',
                  fontSize: 12.5, fontWeight: 600, marginBottom: 16,
                }}>
                  <Clock size={13} /> Te quedan {topupCountdown}
                </div>
              )}

              {statusData?.topup_pay_address && (
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
                  <div style={{ padding: 16, backgroundColor: '#fff', borderRadius: 16, border: '2px solid #e5e7eb' }}>
                    <QRCodeSVG value={statusData.topup_pay_address} size={200} />
                  </div>
                </div>
              )}

              <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 4px 0' }}>Envía exactamente</p>
              <p style={{ fontSize: 26, fontWeight: 700, color: '#111827', margin: '0 0 8px 0' }}>
                {statusData?.topup_pay_amount} {(statusData?.topup_pay_currency || '').toUpperCase()}
              </p>
              <button
                onClick={() => handleCopy(String(statusData?.topup_pay_amount ?? ''), 'Monto')}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', fontSize: 12, fontWeight: 600, color: '#2563eb', border: '1px solid #bfdbfe', borderRadius: 999, backgroundColor: '#eff6ff', cursor: 'pointer', marginBottom: 10 }}
              >
                <Copy size={12} /> Copiar monto exacto
              </button>
              {statusData?.topup_network && (
                <p style={{ fontSize: 12, color: '#9ca3af', margin: '0 0 16px 0' }}>Red: {statusData.topup_network}</p>
              )}

              <div style={{ padding: 14, backgroundColor: '#f3f4f6', borderRadius: 12, textAlign: 'left' }}>
                <p style={{ fontSize: 11, color: '#6b7280', margin: '0 0 6px 0', fontWeight: 500 }}>Dirección de pago</p>
                <p style={{ fontSize: 12, fontFamily: 'monospace', wordBreak: 'break-all', color: '#374151', margin: '0 0 10px 0' }}>
                  {statusData?.topup_pay_address}
                </p>
                <button
                  onClick={() => handleCopy(statusData?.topup_pay_address, 'Dirección')}
                  style={{ width: '100%', padding: 10, fontSize: 13, fontWeight: 600, color: '#374151', border: '1px solid #d1d5db', borderRadius: 10, backgroundColor: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
                >
                  <Copy size={14} /> Copiar dirección
                </button>
              </div>

              {statusData?.topup_payin_extra_id && (
                <div style={{ padding: 14, backgroundColor: '#fee2e2', borderRadius: 12, textAlign: 'left', marginTop: 12 }}>
                  <p style={{ fontSize: 11, color: '#991b1b', margin: '0 0 6px 0', fontWeight: 600 }}>Memo/Tag obligatorio</p>
                  <p style={{ fontSize: 12, fontFamily: 'monospace', color: '#374151', margin: '0 0 10px 0' }}>
                    {statusData.topup_payin_extra_id}
                  </p>
                  <button
                    onClick={() => handleCopy(statusData.topup_payin_extra_id, 'Memo/Tag')}
                    style={{ width: '100%', padding: 10, fontSize: 13, fontWeight: 600, color: '#991b1b', border: '1px solid #fecaca', borderRadius: 10, backgroundColor: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
                  >
                    <Copy size={14} /> Copiar memo/tag
                  </button>
                </div>
              )}
            </div>
            <p style={{ fontSize: 12, color: '#9ca3af', textAlign: 'center', margin: 0 }}>
              Si no completás la diferencia a tiempo, la orden pasa a revisión manual y te contactamos.
            </p>
            <button
              onClick={() => navigate('/history')}
              style={{ padding: 12, fontSize: 14, fontWeight: 600, color: '#6b7280', border: 'none', backgroundColor: 'transparent', cursor: 'pointer' }}
            >
              Volver al historial
            </button>
          </div>
        ) : orderStatus === 'underpaid_review' ? (
          <div style={{ ...cardStyle, textAlign: 'center' }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 14px',
              borderRadius: 999, backgroundColor: '#fef3c7', color: '#92400e', fontSize: 13, fontWeight: 600, marginBottom: 16,
            }}>
              <Clock size={14} /> En revisión
            </div>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: '#111827', margin: '0 0 8px 0' }}>
              Estamos revisando tu pago
            </h2>
            <p style={{ fontSize: 14, color: '#6b7280', margin: '0 0 20px 0', lineHeight: 1.55 }}>
              Tu pago llegó incompleto y lo pasamos a revisión manual. No hace falta que hagas nada:
              te contactamos apenas lo resolvamos. Si aprobamos el envío, lo vas a ver en tu historial.
            </p>
            <button
              onClick={() => navigate('/history')}
              style={{ width: '100%', padding: 14, fontSize: 15, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 12, backgroundColor: '#2563eb', cursor: 'pointer' }}
            >
              Ver historial
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ ...cardStyle, textAlign: 'center' }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 14px',
                borderRadius: 999, backgroundColor: '#fef3c7', color: '#92400e', fontSize: 13, fontWeight: 600, marginBottom: 16,
              }}>
                <Clock size={14} /> Esperando confirmación del pago...
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
                <div style={{ padding: 16, backgroundColor: '#fff', borderRadius: 16, border: '2px solid #e5e7eb' }}>
                  <QRCodeSVG value={order.pay_address} size={200} />
                </div>
              </div>
              <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 4px 0' }}>Envía exactamente</p>
              <p style={{ fontSize: 26, fontWeight: 700, color: '#111827', margin: '0 0 8px 0' }}>
                {order.pay_amount} {order.pay_currency?.toUpperCase()}
              </p>
              <button
                onClick={() => handleCopy(String(order.pay_amount), 'Monto')}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', fontSize: 12, fontWeight: 600, color: '#2563eb', border: '1px solid #bfdbfe', borderRadius: 999, backgroundColor: '#eff6ff', cursor: 'pointer', marginBottom: 10 }}
              >
                <Copy size={12} /> Copiar monto exacto
              </button>
              <p style={{ fontSize: 12, color: '#dc2626', fontWeight: 600, margin: '0 0 8px 0' }}>
                ⚠️ Envía el monto EXACTO. Si envías menos, el pago puede quedar pendiente sin confirmarse.
              </p>
              {order.network_label && (
                <p style={{ fontSize: 12, color: '#9ca3af', margin: '0 0 16px 0' }}>Red: {order.network_label}</p>
              )}
              <div style={{ padding: 14, backgroundColor: '#f3f4f6', borderRadius: 12, marginBottom: order.payin_extra_id ? 12 : 0, textAlign: 'left' }}>
                <p style={{ fontSize: 11, color: '#6b7280', margin: '0 0 6px 0', fontWeight: 500 }}>Dirección de pago</p>
                <p style={{ fontSize: 12, fontFamily: 'monospace', wordBreak: 'break-all', color: '#374151', margin: '0 0 10px 0' }}>
                  {order.pay_address}
                </p>
                <button
                  onClick={() => handleCopy(order.pay_address, 'Dirección')}
                  style={{ width: '100%', padding: 10, fontSize: 13, fontWeight: 600, color: '#374151', border: '1px solid #d1d5db', borderRadius: 10, backgroundColor: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
                >
                  <Copy size={14} /> Copiar dirección
                </button>
              </div>
              {order.payin_extra_id && (
                <div style={{ padding: 14, backgroundColor: '#fee2e2', borderRadius: 12, textAlign: 'left', marginTop: 12 }}>
                  <p style={{ fontSize: 11, color: '#991b1b', margin: '0 0 6px 0', fontWeight: 600 }}>
                    Memo/Tag obligatorio
                  </p>
                  <p style={{ fontSize: 12, fontFamily: 'monospace', color: '#374151', margin: '0 0 10px 0' }}>
                    {order.payin_extra_id}
                  </p>
                  <button
                    onClick={() => handleCopy(order.payin_extra_id, 'Memo/Tag')}
                    style={{ width: '100%', padding: 10, fontSize: 13, fontWeight: 600, color: '#991b1b', border: '1px solid #fecaca', borderRadius: 10, backgroundColor: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
                  >
                    <Copy size={14} /> Copiar memo/tag
                  </button>
                </div>
              )}
            </div>
            <p style={{ fontSize: 12, color: '#9ca3af', textAlign: 'center', margin: 0 }}>
              La app detecta el pago automáticamente. Puedes cerrar esta pantalla y volver más tarde.
            </p>
            <button
              onClick={handleCambiarMonto}
              disabled={cancelling}
              style={{ width: '100%', padding: 14, fontSize: 15, fontWeight: 600, color: '#374151', border: '1px solid #d1d5db', borderRadius: 12, backgroundColor: '#fff', cursor: cancelling ? 'default' : 'pointer', opacity: cancelling ? 0.6 : 1 }}
            >
              {cancelling ? 'Cancelando...' : 'Cambiar monto'}
            </button>
            <button
              onClick={resetFlow}
              style={{ padding: 12, fontSize: 14, fontWeight: 600, color: '#6b7280', border: 'none', backgroundColor: 'transparent', cursor: 'pointer' }}
            >
              Cancelar y volver
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
