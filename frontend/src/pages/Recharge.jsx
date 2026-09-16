import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, QrCode, Copy, CheckCircle, Upload, Clock, Banknote, AlertCircle,
  Wallet, ArrowRight, Shield, Zap, X, XCircle, Timer, CreditCard, Bitcoin
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { formatearCpf, normalizarCpf, queLeFaltaAlCpf } from '../utils/cpf';
import { confirmar } from '../components/flujo/confirmar.js';
import { QRCodeSVG } from 'qrcode.react';
import NotificationBell from '../components/NotificationBell';
import CardPaymentBrick from '../components/CardPaymentBrick';
import { fmt } from '../utils/format';

// ─── Cada cuánto se pregunta si el pago PIX entró ─────────────────────────
//
// ANTES ERAN CINCO SEGUNDOS FIJOS, LOS QUINCE MINUTOS QUE DURA EL CODIGO
//
//     Son 180 preguntas por persona, y cada una cruza a Mercado Pago desde el
//     servidor. Con esta escalera son 48: **un 73% menos**, sin que nadie
//     espere más de lo que ya esperaba.
//
// POR QUE UNA ESCALERA Y NO UN NUMERO MAS GRANDE
//
//     La gente paga en el primer minuto: abre la app del banco, escanea y
//     confirma. Ahí los cinco segundos valen, porque es cuando el aviso de
//     «listo» tiene que llegar rápido. El que a los diez minutos no pagó no es
//     alguien a punto de pagar: es alguien que se fue a hacer otra cosa y
//     dejó la pantalla abierta.
//
//     Y del otro lado está el aviso de Mercado Pago, que acredita solo. Esto
//     es la red de seguridad, no el camino principal.
const RITMO = [
  { hasta: 60, cada: 5000 },      // el primer minuto: cuando de verdad se paga
  { hasta: 300, cada: 15000 },    // hasta los cinco minutos
  { cada: 30000 },                // de ahí en adelante
];

/** Cuántos milisegundos esperar, según hace cuánto que la persona está mirando. */
function cadaCuanto(segundosEsperando) {
  const tramo = RITMO.find((t) => t.hasta === undefined || segundosEsperando < t.hasta);
  return (tramo || RITMO[RITMO.length - 1]).cada;
}

export default function Recharge() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates } = useRate();
  const [method, setMethod] = useState(null);
  const idemRef = useRef(null);
  const [amount, setAmount] = useState('');
  const [cpf, setCpf] = useState('');
  // (el efecto de más abajo lo rellena con el de la cuenta cuando ya lo hay)
  const [cpfError, setCpfError] = useState('');
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [pixData, setPixData] = useState(null);
  const [proofImage, setProofImage] = useState(null);
  const [paymentStatus, setPaymentStatus] = useState('pending'); // pending, completed, expired, cancelled
  const [timeRemaining, setTimeRemaining] = useState(600); // 10 minutos en segundos
  // «Hay un pedido en vuelo» se guarda en una ref y no en el estado.
  //
  // Estaba en `useState`, y ahí la guarda no frenaba nada: el `setInterval`
  // que consulta el pago cada 5 s captura la función del render en que se
  // armó, y esa función ve para siempre el `checkingPayment` de ESE render
  // —falso—. Se comprobó simulando el ciclo: con la guarda por estado, 8 de
  // 9 consultas se solapaban; con la ref, ninguna.
  //
  // Lo que costaba: si la respuesta tardaba más que los 5 s del poll, dos
  // consultas volvían juntas con «pagado», y el usuario veía el aviso de
  // pago confirmado dos veces. Una ref no vive en el render, así que la
  // función vieja y la nueva miran el mismo valor.
  const consultaEnVuelo = useRef(false);
  const timerRef = useRef(null);
  const pollRef = useRef(null);
  const desdeCuandoEspera = useRef(0);

  // Corta la cadena de preguntas. Deja la ref en NULL a propósito: es lo que
  // mira `preguntarYVolver` para no reprogramarse después de que el pago ya se
  // resolvió mientras ella estaba esperando la respuesta.
  const pararDePreguntar = () => {
    clearTimeout(pollRef.current);
    pollRef.current = null;
  };

  // Limites de monto: vienen del servidor (GET /limits) para que el cartel que ve
  // el usuario y el 400 que devuelve el backend salgan del mismo numero.
  const [limits, setLimits] = useState(null);
  useEffect(() => {
    api.get('/limits')
      .then((r) => setLimits(r.data))
      .catch(() => setLimits(null)); // sin limites la pantalla igual funciona: valida el servidor
  }, []);
  const pixMin = limits?.pix?.min_brl ?? null;
  const pixMax = limits?.pix?.max_brl ?? null;
  const vesMin = limits?.ves?.min_ves ?? null;

  // El CPF atado a esta cuenta. Vacío en las cuentas creadas antes de que el
  // registro lo pidiera: a ésas se les pide una vez acá y queda atado.
  const cpfDeLaCuenta = user?.cpf_number?.replace(/\D/g, '') || '';
  const yaTieneCpf = cpfDeLaCuenta.length === 11;

  // El campo arranca con el CPF de la cuenta cuando lo hay: si ya lo sabemos,
  // que no lo tipee. Va en un efecto y no en el valor inicial del estado
  // porque `user` llega después del primer dibujo.
  useEffect(() => {
    if (yaTieneCpf) setCpf(formatearCpf(cpfDeLaCuenta));
  }, [cpfDeLaCuenta, yaTieneCpf]);

  // Check for pending PIX payment on mount
  useEffect(() => {
    const checkPendingPayment = async () => {
      try {
        const response = await api.get('/gestor/pix/pending');
        if (response.data.has_pending) {
          // Restore pending payment
          setPixData({
            payment_id: response.data.payment_id,
            qr_code: response.data.qr_code,
            qr_code_base64: response.data.qr_code_base64,
            copy_paste_code: response.data.copy_paste_code,
            amount_ris: response.data.amount_ris,
            amount_brl: response.data.amount_brl,
            expires_at: response.data.expires_at
          });
          setAmount(response.data.amount_ris?.toString() || '');
          setTimeRemaining(response.data.expires_in_seconds || 0);
          setMethod('pix');
          setStep(2);
          setPaymentStatus('pending');
          toast('Tienes un pago PIX pendiente', { icon: '⏳' });
        }
      } catch (error) {
        console.error('Error checking pending payment:', error);
      }
    };
    
    checkPendingPayment();
  }, []);

  // Timer countdown
  useEffect(() => {
    if (step === 2 && pixData && paymentStatus === 'pending') {
      timerRef.current = setInterval(() => {
        setTimeRemaining(prev => {
          if (prev <= 1) {
            clearInterval(timerRef.current);
            setPaymentStatus('expired');
            toast.error('El código PIX ha expirado');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      // Se pregunta si el pago entró, cada vez más espaciado. Ver RITMO.
      desdeCuandoEspera.current = Date.now();

      const preguntarYVolver = async () => {
        await checkPaymentStatus();
        // Si mientras se preguntaba el pago se confirmó, venció o se canceló,
        // `pararDePreguntar` dejó esto en null y no hay que reprogramar nada.
        if (pollRef.current === null) return;
        const esperando = (Date.now() - desdeCuandoEspera.current) / 1000;
        pollRef.current = setTimeout(preguntarYVolver, cadaCuanto(esperando));
      };

      pollRef.current = setTimeout(preguntarYVolver, cadaCuanto(0));

      // Y una primera vez enseguida, sin esperar.
      checkPaymentStatus();

      return () => {
        clearInterval(timerRef.current);
        pararDePreguntar();
      };
    }
  }, [step, pixData, paymentStatus]);

  const checkPaymentStatus = async () => {
    if (!pixData?.payment_id || consultaEnVuelo.current) return;

    consultaEnVuelo.current = true;
    try {
      const response = await api.get(`/gestor/pix/status/${pixData.payment_id}`);
      const status = response.data.status;
      
      // Check for any success status
      if (status === 'completed' || status === 'approved' || status === 'paid') {
        setPaymentStatus('completed');
        clearInterval(timerRef.current);
        pararDePreguntar();
        toast.success('¡Pago PIX confirmado! Tu saldo ha sido actualizado.');
        await refreshUser();
      } else if (status === 'expired') {
        setPaymentStatus('expired');
        clearInterval(timerRef.current);
        pararDePreguntar();
        toast.error('El código PIX ha expirado');
      } else if (status === 'cancelled') {
        setPaymentStatus('cancelled');
        clearInterval(timerRef.current);
        pararDePreguntar();
      }
    } catch (error) {
      console.error('Error checking payment status:', error);
    } finally {
      consultaEnVuelo.current = false;
    }
  };

  const vesPaymentInfo = {
    bank_name: 'Banco de Venezuela',
    account_holder: 'RIS REMESAS C.A.',
    account_number: '01020123456789012345',
    account_type: 'Corriente',
    phone_number: '04121234567',
    id_document: 'J-12345678-9',
  };

  // Cálculo recarga VES: Si ves_to_ris_rate = 140, entonces 140 VES = 1 RIS
  const amountRis = method === 'ves' && amount ? parseFloat(amount) / (rates.ves_to_ris_rate || 140) : parseFloat(amount) || 0;

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleCpfChange = (e) => {
    setCpf(formatearCpf(e.target.value));
    // Clear error when user starts typing
    if (cpfError) setCpfError('');
  };

  // El CPF que se manda. Si la cuenta ya tiene uno, es ése y el campo ni se
  // edita; si no lo tiene, es el que la persona escribe y queda atado.
  //
  // ACA NO SE DECIDE NADA. Antes esta función comparaba contra
  // `user.cpf_number`, un campo que ninguna parte del servidor escribía, así
  // que la comparación no podía dar bien NUNCA y la recarga estaba trabada
  // para todos. Quien decide ahora es el servidor, en `/gestor/pix/create`.
  // Esto es sólo para no hacerle perder el viaje a quien escribió mal.
  const validateCpf = (inputCpf) => {
    const cleanInput = normalizarCpf(inputCpf);
    const falta = queLeFaltaAlCpf(cleanInput);
    if (falta) {
      return { valid: false, error: falta };
    }
    if (yaTieneCpf && cleanInput !== cpfDeLaCuenta) {
      return { valid: false, error: 'El CPF tiene que ser el de tu cuenta' };
    }
    return { valid: true, error: '' };
  };

  const handleGeneratePix = async () => {
    const montoPix = parseFloat(amount);
    if (!amount || !(montoPix > 0)) {
      toast.error('El monto debe ser mayor a 0');
      return;
    }
    if (pixMin != null && montoPix < pixMin) {
      toast.error(`El monto mínimo es R$ ${fmt(pixMin)}`);
      return;
    }
    if (pixMax != null && montoPix > pixMax) {
      toast.error(`El monto máximo es R$ ${fmt(pixMax)}`);
      return;
    }
    
    // Validate CPF matches registered one
    const cpfValidation = validateCpf(cpf);
    if (!cpfValidation.valid) {
      setCpfError(cpfValidation.error);
      toast.error(cpfValidation.error);
      return;
    }
    
    // EL PORTON DE KYC SALIO DE ACA, Y NO ES UN DESCUIDO.
    //
    // El servidor le da a toda cuenta sin verificar un cupo inicial —200 R$ y
    // 2 operaciones, configurables— y la página «Cómo funciona» se lo promete
    // al visitante. `services/kyc_quota.py` lo hace cumplir en
    // `/gestor/pix/create`, con un mensaje que explica qué le falta.
    //
    // Esta pantalla lo mandaba a verificarse antes de dejarlo intentar, así
    // que ese cupo no lo podía usar NADIE: el cliente nuevo no llegaba a hacer
    // su primera recarga. Quien decide si puede es el cupo del servidor, que
    // además es el único lugar donde la decisión no se salta con la consola
    // abierta.

    setLoading(true);
    try {
      const response = await api.post('/gestor/pix/create', { 
        amount_ris: parseFloat(amount),
        client_cpf: cpf.replace(/\D/g, '')
      });
      setPixData(response.data);
      setStep(2);
      setTimeRemaining(600); // Reset to 10 minutes
      setPaymentStatus('pending');
      toast.success('PIX generado correctamente');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al generar PIX');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyPix = () => {
    // El backend devuelve qr_code, no pix_code
    const pixCode = pixData?.qr_code || pixData?.pix_code;
    if (pixCode) {
      navigator.clipboard.writeText(pixCode);
      toast.success('Código PIX copiado');
    } else {
      toast.error('No hay código PIX disponible');
    }
  };

  const handleCancelPix = async () => {
    if (!pixData?.payment_id) return;
    
    const confirmado = await confirmar({
      titulo: '¿Cancelás este pago PIX?',
      detalle: 'Se anula el código. Si después querés recargar, vas a tener que generar uno nuevo.',
      accion: 'Sí, cancelar',
      cancelar: 'Seguir esperando',
      tono: 'peligro',
    });
    if (!confirmado) return;

    setLoading(true);
    try {
      await api.post(`/gestor/pix/cancel/${pixData.payment_id}`);
      setPaymentStatus('cancelled');
      clearInterval(timerRef.current);
      pararDePreguntar();
      toast.success('Pago PIX cancelado');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al cancelar');
    } finally {
      setLoading(false);
    }
  };

  // Acá vivía `handleUploadProof`, que subía un comprobante del pago PIX a
  // `/gestor/pix/upload-proof`. Se sacó porque ese endpoint NO EXISTE en el
  // backend —el router `/gestor/pix` expone create, pending, cancel, status,
  // simulate-payment, active e history, y ninguno más— así que la función
  // habría dado 404 el día que alguien la enganchara a un botón.
  //
  // Tampoco la llamaba nadie: estaba escrita y suelta. El pago PIX se
  // confirma solo, por la consulta de estado cada 5 s. El comprobante a mano
  // es del flujo de bolívares, que sí tiene su endpoint y su botón.
  //
  // Si algún día hace falta un comprobante para PIX —cuando la confirmación
  // automática no llega— hay que escribir el endpoint primero.

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        toast.error('La imagen no debe superar 5MB');
        return;
      }
      const reader = new FileReader();
      reader.onload = () => setProofImage(reader.result);
      reader.readAsDataURL(file);
    }
  };

  const handleSubmitVesRecharge = async () => {
    const montoVes = parseFloat(amount);
    if (!amount || !(montoVes > 0)) {
      toast.error('El monto debe ser mayor a 0');
      return;
    }
    if (vesMin != null && montoVes < vesMin) {
      toast.error(`El monto mínimo es ${fmt(vesMin)} VES`);
      return;
    }
    if (!proofImage) {
      toast.error('Sube el comprobante de pago');
      return;
    }
    if (!idemRef.current) idemRef.current = (window.crypto?.randomUUID?.() || (Date.now() + '-' + Math.random().toString(16).slice(2)));
    setLoading(true);
    try {
      await api.post('/recharge/ves', {
        amount_ves: parseFloat(amount),
        proof_image: proofImage,
        idempotency_key: idemRef.current,
      });
      idemRef.current = null;
      toast.success('Recarga enviada para verificación');
      navigate('/history');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al enviar recarga');
    } finally {
      setLoading(false);
    }
  };

  const resetPix = () => {
    setStep(1);
    setPixData(null);
    setAmount('');
    setProofImage(null);
    setPaymentStatus('pending');
    setTimeRemaining(600);
  };

  const pageStyle = {
    minHeight: '100vh',
    background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)',
    fontFamily: 'Inter, Helvetica, -apple-system, sans-serif'
  };

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '24px',
    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.08), 0 12px 24px -8px rgba(0, 0, 0, 0.04)',
    padding: '32px'
  };

  const inputStyle = {
    width: '100%',
    padding: '16px',
    borderRadius: '14px',
    border: '1px solid #d1d5db',
    fontSize: '16px',
    outline: 'none',
    transition: 'all 0.2s'
  };

  const buttonPrimaryStyle = {
    backgroundColor: '#6366f1',
    color: 'white',
    borderRadius: '14px',
    height: '56px',
    padding: '0 32px',
    fontWeight: '600',
    fontSize: '16px',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    transition: 'all 0.2s'
  };

  const buttonSecondaryStyle = {
    backgroundColor: '#f3f4f6',
    color: '#374151',
    borderRadius: '14px',
    height: '56px',
    padding: '0 32px',
    fontWeight: '600',
    fontSize: '16px',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    transition: 'all 0.2s'
  };

  return (
    <div style={pageStyle} data-testid="recharge-page">
      {/* Header */}
      <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button 
              onClick={() => navigate(-1)} 
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                border: 'none',
                backgroundColor: 'rgba(255,255,255,0.8)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              data-testid="back-button"
            >
              <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Recargar Saldo</h1>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>
                Saldo actual: {fmt((user?.balance_ris || 0))} RIS
              </p>
            </div>
          </div>
          <NotificationBell />
        </div>

        {/* Method Selection */}
        {!method && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: '0 0 8px 0', textAlign: 'center' }}>
              Selecciona el método de pago
            </h2>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 24px 0', textAlign: 'center' }}>
              Elige cómo deseas recargar tu saldo RIS
            </p>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* PIX Option */}
              <button
                onClick={() => setMethod('pix')}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  border: '2px solid #e5e7eb',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s'
                }}
                data-testid="select-pix"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <QrCode style={{ width: '28px', height: '28px', color: '#16a34a' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>PIX (Brasil)</span>
                      <span style={{ padding: '2px 8px', backgroundColor: '#dcfce7', color: '#16a34a', borderRadius: '9999px', fontSize: '12px', fontWeight: '600' }}>Recomendado</span>
                    </div>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>Pago instantáneo • Sin comisiones</p>
                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#16a34a', margin: '4px 0 0 0' }}>1 BRL = {fmt(rates?.brl_to_ris) || '1.00'} RIS</p>
                  </div>
                  <ArrowRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                </div>
              </button>

              {/* VES Option */}
              <button
                onClick={() => navigate('/recharge-ves')}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  border: '2px solid #e5e7eb',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s'
                }}
                data-testid="select-ves"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Banknote style={{ width: '28px', height: '28px', color: '#2563eb' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>Bolívares (Venezuela)</span>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Pago Móvil o Transferencia</p>
                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#2563eb', margin: '4px 0 0 0' }}>{fmt(rates?.ves_to_ris_rate) || '140'} VES = 1 RIS</p>
                  </div>
                  <ArrowRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                </div>
              </button>

              {/* Card Option (Brazil) */}
              <button
                onClick={() => { setMethod('card'); setStep(1); }}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  border: '2px solid #e5e7eb',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s'
                }}
                data-testid="select-card"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#f5e9ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <CreditCard style={{ width: '28px', height: '28px', color: '#7c3aed' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>Tarjeta de Crédito/Débito (Brasil)</span>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Pago en 1 cuota • Comisión MP incluida</p>
                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#7c3aed', margin: '4px 0 0 0' }}>1 BRL = {fmt(rates?.brl_to_ris) || '1.00'} RIS</p>
                  </div>
                  <ArrowRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                </div>
              </button>

              {/* Cripto Option (USDT/USDC) */}
              <button
                onClick={() => navigate('/credits/deposit')}
                style={{
                  padding: '24px',
                  borderRadius: '16px',
                  border: '2px solid #e5e7eb',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s'
                }}
                data-testid="select-crypto"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Bitcoin style={{ width: '28px', height: '28px', color: '#d97706' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: '16px', fontWeight: '600', color: '#111827' }}>Cripto (USDT/USDC)</span>
                    <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Sin salir de la app • Acreditación automática</p>
                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#d97706', margin: '4px 0 0 0' }}>Créditos separados de tu saldo RIS</p>
                  </div>
                  <ArrowRight style={{ width: '20px', height: '20px', color: '#9ca3af' }} />
                </div>
              </button>
            </div>
          </div>
        )}

        {/* PIX Flow - Step 1: Enter Amount */}
        {method === 'pix' && step === 1 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <QrCode style={{ width: '28px', height: '28px', color: '#16a34a' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Recarga con PIX</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Ingresa los datos de pago</p>
              </div>
            </div>

            {/* AVISA, NO TAPA. Antes este cartel venía con un portón que
                mandaba a verificarse antes de dejar intentar, y así el cupo
                inicial que el servidor concede no lo podía usar nadie. Ahora
                cuenta lo que hay y deja pasar: el que se pase del cupo se
                entera al apretar, con el mensaje del servidor diciendo
                exactamente cuánto le queda. */}
            {user?.verification_status !== 'verified' && (
              <div style={{ padding: '16px', backgroundColor: '#eff6ff', borderRadius: '12px', marginBottom: '24px', display: 'flex', gap: '12px' }}>
                <AlertCircle style={{ width: '20px', height: '20px', color: '#2563eb', flexShrink: 0 }} />
                <div>
                  <p style={{ fontWeight: '600', color: '#1e40af', margin: 0 }}>Estás usando tu cupo inicial</p>
                  <p style={{ fontSize: '14px', color: '#1d4ed8', margin: '4px 0 0 0' }}>
                    Podés recargar sin verificar tu cuenta hasta agotarlo. Después,
                    para seguir operando, hay que verificar la identidad.
                  </p>
                  <button onClick={() => navigate('/verification')} style={{ marginTop: '8px', fontSize: '14px', fontWeight: '600', color: '#1e40af', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                    Verificar ahora
                  </button>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Monto a recargar (BRL)</label>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  style={{ ...inputStyle, fontSize: '24px', fontWeight: '700' }}
                  min={pixMin ?? undefined}
                  max={pixMax ?? undefined}
                  data-testid="pix-amount"
                />
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '8px 0 0 0' }}>
                  {pixMin != null && pixMax != null
                    ? `Mínimo: R$ ${fmt(pixMin)} • Máximo: R$ ${fmt(pixMax)}`
                    : 'Consultando límites...'}
                </p>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>CPF del pagador</label>
                {/* Si la cuenta ya tiene CPF, llega puesto y NO se edita: ya
                    lo declaró al registrarse y es el único con el que puede
                    pagar. Sólo lo tipea quien se registró antes de que el
                    registro lo pidiera, y ahí queda atado para siempre. */}
                <input
                  type="text"
                  value={cpf}
                  onChange={handleCpfChange}
                  readOnly={yaTieneCpf}
                  placeholder="000.000.000-00"
                  style={{
                    ...inputStyle,
                    borderColor: cpfError ? '#ef4444' : '#e5e7eb',
                    backgroundColor: cpfError ? '#fef2f2' : (yaTieneCpf ? '#f3f4f6' : 'white'),
                    color: yaTieneCpf ? '#6b7280' : undefined,
                    cursor: yaTieneCpf ? 'not-allowed' : undefined,
                  }}
                  data-testid="pix-cpf"
                />
                {cpfError && (
                  <p style={{ fontSize: '12px', color: '#ef4444', margin: '4px 0 0 0', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertCircle style={{ width: '14px', height: '14px' }} />
                    {cpfError}
                  </p>
                )}
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
                  {yaTieneCpf
                    ? 'Es el CPF de tu cuenta. La recarga la tenés que hacer vos, no un tercero.'
                    : 'Queda registrado como el CPF de tu cuenta: de acá en adelante es el único con el que vas a poder recargar.'}
                </p>
              </div>

              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Recibirás en tu cuenta</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#16a34a', margin: 0 }}>{fmt(amountRis)} RIS</p>
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setMethod(null)} style={buttonSecondaryStyle} data-testid="back-to-methods">Atrás</button>
                <button
                  onClick={handleGeneratePix}
                  disabled={loading || !amount || parseFloat(amount) < 10 || cpf.replace(/\D/g, '').length !== 11}
                  style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a', opacity: loading || !amount || parseFloat(amount) < 10 || cpf.replace(/\D/g, '').length !== 11 ? 0.5 : 1 }}
                  data-testid="generate-pix"
                >
                  {loading ? 'Generando...' : 'Generar PIX'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* PIX Flow - Step 2: QR Code & Payment */}
        {method === 'pix' && step === 2 && pixData && (
          <div style={cardStyle}>
            {/* Payment Completed */}
            {paymentStatus === 'completed' && (
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '100px', height: '100px', borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px' }}>
                  <CheckCircle style={{ width: '56px', height: '56px', color: '#16a34a' }} />
                </div>
                <h2 style={{ fontSize: '28px', fontWeight: '700', color: '#16a34a', margin: '0 0 8px 0' }}>¡Pago Exitoso!</h2>
                <p style={{ fontSize: '16px', color: '#6b7280', margin: '0 0 16px 0' }}>Tu recarga PIX ha sido procesada automáticamente</p>
                <div style={{ padding: '20px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '16px' }}>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 4px 0' }}>Monto acreditado</p>
                  <p style={{ fontSize: '36px', fontWeight: '700', color: '#16a34a', margin: 0 }}>+{fmt(pixData?.amount_ris) || fmt(amountRis)} RIS</p>
                </div>
                <div style={{ padding: '16px', backgroundColor: '#e0f2fe', borderRadius: '14px', marginBottom: '24px' }}>
                  <p style={{ fontSize: '14px', color: '#0369a1', margin: '0 0 4px 0' }}>Tu nuevo saldo</p>
                  <p style={{ fontSize: '28px', fontWeight: '700', color: '#0284c7', margin: 0 }}>{fmt(user?.balance_ris)} RIS</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button onClick={() => navigate('/')} style={buttonPrimaryStyle}>Ir al Dashboard</button>
                </div>
              </div>
            )}

            {/* Payment Expired */}
            {paymentStatus === 'expired' && (
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '100px', height: '100px', borderRadius: '50%', backgroundColor: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px' }}>
                  <XCircle style={{ width: '56px', height: '56px', color: '#dc2626' }} />
                </div>
                <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#dc2626', margin: '0 0 8px 0' }}>Código Expirado</h2>
                <p style={{ fontSize: '16px', color: '#6b7280', margin: '0 0 24px 0' }}>El código PIX ha expirado después de 10 minutos</p>
                <button onClick={resetPix} style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a' }}>
                  Generar nuevo PIX
                </button>
              </div>
            )}

            {/* Payment Cancelled */}
            {paymentStatus === 'cancelled' && (
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '100px', height: '100px', borderRadius: '50%', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px' }}>
                  <X style={{ width: '56px', height: '56px', color: '#6b7280' }} />
                </div>
                <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#374151', margin: '0 0 8px 0' }}>Pago Cancelado</h2>
                <p style={{ fontSize: '16px', color: '#6b7280', margin: '0 0 24px 0' }}>Has cancelado esta operación de pago</p>
                <button onClick={resetPix} style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a' }}>
                  Generar nuevo PIX
                </button>
              </div>
            )}

            {/* Payment Pending - Show QR Code */}
            {paymentStatus === 'pending' && (
              <>
                <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                  <div style={{ width: '80px', height: '80px', borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                    <QrCode style={{ width: '40px', height: '40px', color: '#16a34a' }} />
                  </div>
                  <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: '0 0 8px 0' }}>PIX generado</h2>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>Escanea el QR o copia el código</p>
                </div>

                {/* Timer */}
                <div style={{ 
                  padding: '16px', 
                  backgroundColor: timeRemaining <= 60 ? '#fee2e2' : '#fef3c7', 
                  borderRadius: '12px', 
                  marginBottom: '16px', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  gap: '12px'
                }}>
                  <Timer style={{ width: '24px', height: '24px', color: timeRemaining <= 60 ? '#dc2626' : '#d97706' }} />
                  <span style={{ fontWeight: '700', fontSize: '20px', color: timeRemaining <= 60 ? '#dc2626' : '#92400e' }}>
                    {formatTime(timeRemaining)}
                  </span>
                  <span style={{ fontWeight: '500', color: timeRemaining <= 60 ? '#dc2626' : '#92400e' }}>
                    restantes
                  </span>
                </div>

                {(() => {
                  const pixCode = pixData?.qr_code || pixData?.pix_code || '';
                  if (pixData?.qr_code_base64) {
                    return (
                      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '24px' }}>
                        <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '16px', border: '2px solid #e5e7eb' }}>
                          <img src={`data:image/png;base64,${pixData.qr_code_base64}`} alt="QR Code PIX" style={{ width: '200px', height: '200px' }} />
                        </div>
                      </div>
                    );
                  } else if (pixCode) {
                    return (
                      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '24px' }}>
                        <div style={{ padding: '16px', backgroundColor: '#ffffff', borderRadius: '16px', border: '2px solid #e5e7eb' }}>
                          <QRCodeSVG value={pixCode} size={200} />
                        </div>
                      </div>
                    );
                  }
                  return null;
                })()}

                <div style={{ padding: '16px', backgroundColor: '#f3f4f6', borderRadius: '12px', marginBottom: '16px' }}>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 8px 0', fontWeight: '500' }}>Código PIX (Copia y Pega)</p>
                  <p style={{ fontSize: '11px', fontFamily: 'monospace', wordBreak: 'break-all', color: '#374151', backgroundColor: '#ffffff', padding: '12px', borderRadius: '8px', margin: '0 0 12px 0' }}>
                    {(pixData?.qr_code || pixData?.pix_code || 'Código no disponible').substring(0, 60)}...
                  </p>
                  <button onClick={handleCopyPix} style={{ ...buttonPrimaryStyle, backgroundColor: '#16a34a', height: '48px' }} data-testid="copy-pix">
                    <Copy style={{ width: '20px', height: '20px' }} />
                    Copiar código completo
                  </button>
                </div>

                {/* Monto */}
                <div style={{ padding: '16px', backgroundColor: '#dcfce7', borderRadius: '12px', marginBottom: '16px' }}>
                  <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Monto a pagar</p>
                  <p style={{ fontSize: '28px', fontWeight: '700', color: '#15803d', margin: 0 }}>R$ {fmt(parseFloat(amount))}</p>
                  <p style={{ fontSize: '14px', color: '#16a34a', margin: '8px 0 0 0' }}>Recibirás: {fmt(amountRis)} RIS</p>
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <button 
                    onClick={handleCancelPix} 
                    disabled={loading}
                    style={{ ...buttonSecondaryStyle, color: '#dc2626', borderColor: '#fecaca', backgroundColor: '#fef2f2' }}
                  >
                    <X style={{ width: '20px', height: '20px' }} />
                    Cancelar pago
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Card Flow - Step 1: Enter Amount */}
        {method === 'card' && step === 1 && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#f5e9ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CreditCard style={{ width: '28px', height: '28px', color: '#7c3aed' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Recarga con Tarjeta</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Crédito o Débito • Brasil • R$ 5 - R$ 5.000</p>
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                Monto a recargar (RIS)
              </label>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="100"
                min="5"
                max="5000"
                data-testid="card-amount-input"
                style={{ width: '100%', padding: '14px', fontSize: 18, borderRadius: 12, border: '1px solid #d1d5db', boxSizing: 'border-box' }}
              />
              <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 6 }}>
                Recibirás {fmt(parseFloat(amount) || 0)} RIS (1 BRL = 1 RIS). La comisión MP se suma al total a cobrar.
              </p>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button onClick={() => { setMethod(null); setAmount(''); }} style={buttonSecondaryStyle} data-testid="card-back-to-methods">Atrás</button>
              <button
                onClick={() => {
                  const v = parseFloat(amount);
                  if (!v || v < 5 || v > 5000) {
                    toast.error('Monto debe estar entre R$ 5 y R$ 5.000');
                    return;
                  }
                  // LA TARJETA SI PIDE VERIFICACION, Y PIX NO. NO ES UN OLVIDO.
                  //
                  // Un PIX no se puede revertir: el que paga, pagó. Una
                  // tarjeta sí — el titular puede desconocer el cobro meses
                  // después. Una cuenta sin verificar que recarga con tarjeta,
                  // manda la plata a Venezuela y después desconoce el cobro
                  // nos deja sin la plata y sin a quién reclamarle.
                  //
                  // Por eso el cupo inicial se usa con PIX y no con tarjeta.
                  // Esta comprobación acompaña a la del servidor
                  // (`routes/payments_card.py`), que es la que manda: sin
                  // ella, la persona carga los datos de su tarjeta para
                  // enterarse recién al final de que no puede.
                  if (user?.verification_status !== 'verified') {
                    toast.error('Para pagar con tarjeta hay que verificar la cuenta. Con PIX podés recargar usando tu cupo inicial.');
                    navigate('/verification');
                    return;
                  }
                  setStep(2);
                }}
                style={{ ...buttonPrimaryStyle, flex: 1 }}
                data-testid="card-continue-btn"
              >
                Continuar
              </button>
            </div>
          </div>
        )}

        {/* Card Flow - Step 2: Brick */}
        {method === 'card' && step === 2 && (
          <div style={cardStyle}>
            <CardPaymentBrick
              amountRis={parseFloat(amount)}
              userEmail={user?.email}
              userCpf={(user?.cpf_number || '').replace(/\D/g, '')}
              onSuccess={() => {
                refreshUser();
                setTimeout(() => navigate('/'), 2500);
              }}
              onBack={() => setStep(1)}
            />
          </div>
        )}


        {/* VES Flow */}
        {method === 'ves' && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Banknote style={{ width: '28px', height: '28px', color: '#2563eb' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#111827', margin: 0 }}>Recarga con Bolívares</h2>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa: {fmt(rates.ves_to_ris_rate) || '140'} VES = 1 RIS</p>
              </div>
            </div>

            {/* Bank Info */}
            <div style={{ padding: '20px', backgroundColor: '#eff6ff', borderRadius: '14px', marginBottom: '24px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#1e40af', margin: '0 0 16px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Wallet style={{ width: '20px', height: '20px' }} />
                Datos para transferencia
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {[
                  { label: 'Banco', value: vesPaymentInfo.bank_name },
                  { label: 'Titular', value: vesPaymentInfo.account_holder },
                  { label: 'Cuenta', value: vesPaymentInfo.account_number },
                  { label: 'Tipo', value: vesPaymentInfo.account_type },
                  { label: 'Cédula/RIF', value: vesPaymentInfo.id_document },
                ].map((item, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: i < 4 ? '1px solid #bfdbfe' : 'none' }}>
                    <span style={{ fontSize: '14px', color: '#3b82f6' }}>{item.label}:</span>
                    <span style={{ fontSize: '14px', fontWeight: '600', color: '#1e40af' }}>{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Monto transferido (VES)</label>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  style={{ ...inputStyle, fontSize: '24px', fontWeight: '700' }}
                  data-testid="ves-amount"
                />
              </div>

              <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                <p style={{ fontSize: '14px', color: '#16a34a', margin: '0 0 4px 0' }}>Recibirás en tu cuenta</p>
                <p style={{ fontSize: '28px', fontWeight: '700', color: '#16a34a', margin: 0 }}>{fmt(amountRis)} RIS</p>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>Comprobante de pago *</label>
                <input type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} id="proof-upload" />
                <label
                  htmlFor="proof-upload"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '100%',
                    height: '140px',
                    border: `2px dashed ${proofImage ? '#16a34a' : '#d1d5db'}`,
                    borderRadius: '14px',
                    cursor: 'pointer',
                    backgroundColor: proofImage ? '#f0fdf4' : '#ffffff',
                    transition: 'all 0.2s'
                  }}
                >
                  {proofImage ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: '#16a34a' }}>
                      <CheckCircle style={{ width: '32px', height: '32px' }} />
                      <span style={{ fontSize: '16px', fontWeight: '600' }}>Imagen cargada</span>
                    </div>
                  ) : (
                    <>
                      <Upload style={{ width: '40px', height: '40px', color: '#9ca3af', marginBottom: '8px' }} />
                      <span style={{ fontSize: '14px', fontWeight: '500', color: '#374151' }}>Click para subir comprobante</span>
                      <span style={{ fontSize: '12px', color: '#9ca3af' }}>PNG, JPG hasta 5MB</span>
                    </>
                  )}
                </label>
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setMethod(null)} style={buttonSecondaryStyle}>Atrás</button>
                <button
                  onClick={handleSubmitVesRecharge}
                  disabled={loading || !amount || !proofImage}
                  style={{ ...buttonPrimaryStyle, opacity: loading || !amount || !proofImage ? 0.5 : 1 }}
                  data-testid="submit-ves"
                >
                  {loading ? 'Enviando...' : 'Enviar recarga'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
