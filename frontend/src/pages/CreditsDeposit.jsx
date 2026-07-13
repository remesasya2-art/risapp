import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, Loader2, Bitcoin, Copy, CheckCircle, Clock, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { QRCodeSVG } from 'qrcode.react';

// Monedas de credito disponibles (de cara al usuario: "Creditos")
const CREDIT_OPTIONS = [
  { key: 'usdt', label: 'Creditos USDTRIS', desc: 'Deposita con USDT', color: '#26A17B' },
  { key: 'usdc', label: 'Creditos USDCRIS', desc: 'Deposita con USDC', color: '#2775CA' },
];

export default function CreditsDeposit() {
  const navigate = useNavigate();
  const [currency, setCurrency] = useState('usdt');
  const [amount, setAmount] = useState('');
  const [declared, setDeclared] = useState(false);
  const [loading, setLoading] = useState(false);
  const [minAmount, setMinAmount] = useState(null);
  // Seleccion de red (TRC20, ERC20, BSC, Solana, Polygon, etc.)
  const [networks, setNetworks] = useState([]);
  const [network, setNetwork] = useState(null); // ticker exacto, ej. 'usdttrc20'
  const [networksLoading, setNetworksLoading] = useState(false);
  // Datos del pago en curso (dentro de la app, sin redireccion)
  const [order, setOrder] = useState(null);
  const [depositStatus, setDepositStatus] = useState('pending');
  const [credited, setCredited] = useState(false);
  const pollRef = useRef(null);

  const selected = CREDIT_OPTIONS.find((o) => o.key === currency);
  const amountNum = parseFloat(amount);
  const belowMin = minAmount != null && amountNum > 0 && amountNum < minAmount;
  const canContinue = amountNum > 0 && declared && !loading && !belowMin && !!network;

  // Consulta las redes disponibles cada vez que cambia la moneda elegida.
  // Si la consulta falla, cae a la red por defecto de esa moneda (nunca deja al
  // usuario bloqueado sin poder depositar).
  useEffect(() => {
    let cancelled = false;
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
      .finally(() => {
        if (!cancelled) setNetworksLoading(false);
      });
    return () => { cancelled = true; };
  }, [currency]);

  // Consulta el monto minimo real (via NOWPayments) para la moneda + red elegidas.
  // Si la consulta falla, se usa un valor de respaldo (10) para que el aviso SIEMPRE
  // se muestre al usuario, en vez de quedar en "Consultando..." indefinidamente.
  useEffect(() => {
    let cancelled = false;
    setMinAmount(null);
    if (!network) return;
    api.get('/credits/min-amount', { params: { currency, network } })
      .then(({ data }) => {
        if (!cancelled) setMinAmount(data?.min_amount || 10);
      })
      .catch(() => {
        if (!cancelled) setMinAmount(10);
      });
    return () => { cancelled = true; };
  }, [currency, network]);

  const handleDeposit = async () => {
    if (!canContinue) return;
    setLoading(true);
    try {
      const { data } = await api.post('/credits/deposit', {
        currency,
        amount: amountNum,
        declared_not_restricted: declared,
        network,
      });
      if (data?.pay_address && data?.pay_amount) {
        setOrder(data);
        setDepositStatus('pending');
        setCredited(false);
      } else {
        toast.error('No se pudo iniciar el pago. Intenta de nuevo.');
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || 'No se pudo iniciar el pago. Intenta de nuevo.';
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  // Polling del estado cada 5s mientras haya un pedido activo y no este acreditado
  useEffect(() => {
    if (!order?.order_id || credited) return;
    const checkStatus = async () => {
      try {
        const { data } = await api.get(`/credits/deposit/${order.order_id}/status`);
        if (data?.credited) {
          setCredited(true);
          setDepositStatus('finished');
          toast.success('¡Depósito acreditado!');
        } else if (data?.status) {
          setDepositStatus(data.status);
        }
      } catch (err) {
        // Silencioso: si falla una consulta, se reintenta en el proximo ciclo
      }
    };
    checkStatus();
    pollRef.current = setInterval(checkStatus, 5000);
    return () => clearInterval(pollRef.current);
  }, [order?.order_id, credited]);

  const handleCopy = (text, label) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado`);
  };

  const resetFlow = () => {
    clearInterval(pollRef.current);
    setOrder(null);
    setAmount('');
    setDeclared(false);
    setDepositStatus('pending');
    setCredited(false);
  };

  const cardStyle = {
    backgroundColor: '#fff', borderRadius: 16, border: '1px solid #e5e7eb',
    padding: 20,
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ backgroundColor: '#fff', borderBottom: '1px solid #e5e7eb', padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => (order ? resetFlow() : navigate(-1))} style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex' }}>
          <ArrowLeft size={22} color="#374151" />
        </button>
        <h1 style={{ fontSize: 18, fontWeight: 600, color: '#111827', margin: 0 }}>Recargar con cripto</h1>
      </div>

      <div style={{ maxWidth: 480, margin: '0 auto', padding: '20px' }}>
        {!order ? (
          <>
            <p style={{ fontSize: 14, color: '#6b7280', marginBottom: 20 }}>
              Deposita USDT o USDC y recibe creditos en tu cuenta. Se acreditan al confirmarse el pago,
              sin salir de la aplicación.
            </p>

            {/* Seleccion de moneda */}
            <label style={{ fontSize: 13, fontWeight: 500, color: '#374151', display: 'block', marginBottom: 8 }}>Tipo de credito</label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
              {CREDIT_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  onClick={() => setCurrency(opt.key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: 14, textAlign: 'left',
                    borderRadius: 12, cursor: 'pointer', backgroundColor: '#fff',
                    border: currency === opt.key ? `2px solid ${opt.color}` : '1px solid #e5e7eb',
                  }}
                >
                  <div style={{ width: 40, height: 40, borderRadius: '50%', backgroundColor: `${opt.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Bitcoin size={20} color={opt.color} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 15, fontWeight: 500, color: '#111827' }}>{opt.label}</div>
                    <div style={{ fontSize: 12, color: '#6b7280' }}>{opt.desc}</div>
                  </div>
                  <div style={{ width: 18, height: 18, borderRadius: '50%', border: currency === opt.key ? `5px solid ${opt.color}` : '2px solid #d1d5db' }} />
                </button>
              ))}
            </div>

            {/* Seleccion de red */}
            <label style={{ fontSize: 13, fontWeight: 500, color: '#374151', display: 'block', marginBottom: 8 }}>Red</label>
            {networksLoading ? (
              <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 20 }}>Consultando redes disponibles...</p>
            ) : (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
                {networks.map((n) => (
                  <button
                    key={n.ticker}
                    onClick={() => setNetwork(n.ticker)}
                    style={{
                      padding: '8px 14px', borderRadius: 999, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                      border: network === n.ticker ? '2px solid #2563eb' : '1px solid #e5e7eb',
                      backgroundColor: network === n.ticker ? '#eff6ff' : '#fff',
                      color: network === n.ticker ? '#1d4ed8' : '#374151',
                    }}
                  >
                    {n.label}
                  </button>
                ))}
              </div>
            )}

            {/* Monto */}
            <label style={{ fontSize: 13, fontWeight: 500, color: '#374151', display: 'block', marginBottom: 8 }}>
              Monto a depositar ({selected?.key.toUpperCase()})
            </label>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              style={{
                width: '100%', boxSizing: 'border-box', padding: '12px 14px', fontSize: 18, fontWeight: 500, color: '#111827',
                border: belowMin ? '1px solid #dc2626' : '1px solid #d1d5db', borderRadius: 12, marginBottom: 6,
              }}
            />
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 10,
              marginBottom: 20, backgroundColor: belowMin ? '#fee2e2' : '#eff6ff',
              border: belowMin ? '1px solid #fecaca' : '1px solid #bfdbfe',
            }}>
              <AlertTriangle size={16} color={belowMin ? '#dc2626' : '#2563eb'} />
              <span style={{ fontSize: 13, fontWeight: 600, color: belowMin ? '#dc2626' : '#1d4ed8' }}>
                {minAmount != null
                  ? `Monto mínimo para depositar: ${minAmount} ${selected?.key.toUpperCase()}`
                  : 'Consultando monto mínimo...'}
              </span>
            </div>

            {/* Declaracion de jurisdiccion */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', backgroundColor: '#fef3c7', borderRadius: 12, padding: '12px 14px', marginBottom: 20 }}>
              <input
                type="checkbox"
                checked={declared}
                onChange={(e) => setDeclared(e.target.checked)}
                style={{ marginTop: 3, width: 16, height: 16, flexShrink: 0 }}
              />
              <span style={{ fontSize: 12, color: '#854d0e', lineHeight: 1.5 }}>
                Declaro que no soy residente ni ciudadano de Estados Unidos, la Union Europea o el Reino Unido.
              </span>
            </div>

            {/* Boton */}
            <button
              onClick={handleDeposit}
              disabled={!canContinue}
              style={{
                width: '100%', padding: 14, fontSize: 15, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 12,
                backgroundColor: canContinue ? '#2563eb' : '#93c5fd', cursor: canContinue ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {loading ? (<><Loader2 size={18} className="animate-spin" /> Generando dirección...</>) : 'Generar dirección de pago'}
            </button>
            <p style={{ fontSize: 11, color: '#9ca3af', textAlign: 'center', marginTop: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
              <ShieldCheck size={13} /> Pago procesado de forma segura por NOWPayments
            </p>
          </>
        ) : credited ? (
          /* Pantalla de exito */
          <div style={{ ...cardStyle, textAlign: 'center' }}>
            <div style={{ width: 88, height: 88, borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
              <CheckCircle size={48} color="#16a34a" />
            </div>
            <h2 style={{ fontSize: 22, fontWeight: 700, color: '#16a34a', margin: '0 0 8px 0' }}>¡Depósito acreditado!</h2>
            <p style={{ fontSize: 14, color: '#6b7280', margin: '0 0 20px 0' }}>
              Se acreditaron {order.credit_amount ?? order.pay_amount} {currency.toUpperCase()} a tu cuenta.
            </p>
            <button
              onClick={() => navigate('/')}
              style={{ width: '100%', padding: 14, fontSize: 15, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 12, backgroundColor: '#2563eb', cursor: 'pointer' }}
            >
              Ir al Dashboard
            </button>
          </div>
        ) : (
          /* Pantalla de pago: QR + direccion + monto, esperando confirmacion */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ ...cardStyle, textAlign: 'center' }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 14px',
                borderRadius: 999, backgroundColor: '#fef3c7', color: '#92400e', fontSize: 13, fontWeight: 600, marginBottom: 16,
              }}>
                <Clock size={14} className="animate-spin" /> Esperando confirmación del pago...
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
                ⚠️ Envía el monto EXACTO. Si envías menos, el pago puede quedar pendiente sin acreditarse.
              </p>
              <p style={{ fontSize: 11, color: '#9ca3af', margin: '0 0 12px 0' }}>
                Tu billetera o exchange de origen puede cobrarte una comisión adicional al retirar/enviar —
                esa comisión es externa a esta app y no está incluida en el cálculo de arriba. Se acreditará
                exactamente lo que llegue a esta dirección.
              </p>
              {order.network_label && (
                <p style={{ fontSize: 12, color: '#9ca3af', margin: '0 0 16px 0' }}>Red: {order.network_label}</p>
              )}
              {order.fee_amount != null && (
                <div style={{ backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 10, padding: 12, marginBottom: 16, textAlign: 'left' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                    <span>Se acreditará en tu cuenta</span>
                    <span style={{ fontWeight: 600, color: '#111827' }}>{order.credit_amount} {currency.toUpperCase()}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                    <span>Comisión de red (la pagas tú)</span>
                    <span style={{ fontWeight: 600, color: '#111827' }}>
                      {order.fee_amount} {currency.toUpperCase()} ({order.fee_percentage}%)
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#374151', paddingTop: 6, borderTop: '1px dashed #e5e7eb' }}>
                    <span style={{ fontWeight: 600 }}>Total a enviar</span>
                    <span style={{ fontWeight: 700 }}>{order.pay_amount} {order.pay_currency?.toUpperCase()}</span>
                  </div>
                </div>
              )}
              <div style={{ padding: 14, backgroundColor: '#f3f4f6', borderRadius: 12, marginBottom: order.payin_extra_id ? 12 : 0, textAlign: 'left' }}>
                <p style={{ fontSize: 11, color: '#6b7280', margin: '0 0 6px 0', fontWeight: 500 }}>Dirección de depósito</p>
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
                <div style={{ padding: 14, backgroundColor: '#fee2e2', borderRadius: 12, textAlign: 'left' }}>
                  <p style={{ fontSize: 11, color: '#991b1b', margin: '0 0 6px 0', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertTriangle size={13} /> Memo/Tag obligatorio
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
              La app detecta el pago automáticamente. Puedes cerrar esta pantalla y volver más tarde;
              el saldo se acreditará igual apenas se confirme.
            </p>
            <button
              onClick={resetFlow}
              style={{ width: '100%', padding: 12, fontSize: 14, fontWeight: 600, color: '#6b7280', border: '1px solid #e5e7eb', borderRadius: 12, backgroundColor: '#fff', cursor: 'pointer' }}
            >
              Cancelar y volver
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
