/**
 * BTCLightning.jsx — Enviar a Venezuela pagando con Bitcoin (Lightning).
 *
 * POR QUE SE REHIZO
 *
 *   La pantalla funcionaba y se veía como otra aplicación: fondo con degradado
 *   violeta y celeste, paletas ámbar propias, pasos dibujados a mano, emojis
 *   como iconos, y el texto sin una sola tilde. Al lado del flujo de enviar a
 *   Venezuela —la misma tarea, el mismo usuario, el mismo dinero— parecía
 *   hecha por otro equipo y en otro momento.
 *
 *   Ahora usa `components/flujo`, que es EL MISMO sistema visual que
 *   `Send.jsx`. No uno parecido: el mismo módulo. Copiar los estilos duraría
 *   hasta el primer retoque en una sola de las dos pantallas.
 *
 * LAS CUATRO COSAS QUE ESTABAN MAL, NO SOLO FEAS
 *
 *   1. LA TASA INVENTADA. `tasaVES` arrancaba en 680 escrito a mano. Si
 *      `/btc/precio` no contestaba, la pantalla decía «el beneficiario recibe
 *      X VES garantizados» con una tasa que nadie confirmó. Es el mismo error
 *      que `Send.jsx` ya había corregido, y acá encima la palabra
 *      «garantizados» lo convertía en una promesa. Ahora sin tasa del servidor
 *      no se convierte, no se promete y no se avanza.
 *
 *   2. EL BENEFICIARIO SIN BANCO. La lista mostraba `bank` crudo, y en las
 *      fichas viejas ese campo guarda el CODIGO. En pantalla se leía
 *      «0134 -»: un número y un guión. Ahora pasa por `nombreDelBanco`, el
 *      mismo del otro flujo, que resuelve el código contra el catálogo.
 *
 *   3. LOS GUIONES COMO CIFRA. Sin monto escrito, el resumen mostraba
 *      «--- BTC» y «--- VES», que parecen un error de carga. Ahora el resumen
 *      aparece cuando hay algo que resumir.
 *
 *   4. EL TELEFONO Y LA CUENTA SIN FORMATO. Se muestran como en el otro
 *      flujo: el teléfono agrupado para poder leerlo en voz alta, la cuenta
 *      con sus últimos cuatro dígitos.
 *
 * QUE NO SE TOCO
 *
 *   Los efectos, el conteo regresivo, la consulta de pago cada 5 s, la
 *   restauración de la remesa activa al volver, el PIN y las llamadas a la API
 *   son las mismas líneas de antes.
 *
 *   La única excepción: se sacó el estado `paymentStatus`. Se escribía en
 *   cinco lugares y no lo leía nadie —tampoco antes de este cambio—. Lo que
 *   decide qué se ve es `step`. Sacarlo no cambia ningún comportamiento
 *   porque no había nada del otro lado; dejarlo era invitar a alguien a
 *   creer que ahí hay una máquina de estados que no existe.
 */
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  Zap, AlertCircle, ArrowLeft, ArrowRight, Plus, X, User, Smartphone,
  Building2, Search, Copy, Clock, Check, RefreshCw, Wallet, ListOrdered,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import PinConfirm from '../components/PinConfirm';
import { Boton, Aviso, Progreso, Opcion } from '../components/flujo';
import {
  C, HOJA, tarjeta, etiqueta, microEtiqueta, campo, ayuda, iniciales,
} from '../components/flujo/estilos';
import { cuentaAbreviada, nombreDelBanco, telefonoLegible } from '../utils/envioAVenezuela';
import { fmt } from '../utils/format';

const VENEZUELAN_BANKS = [
  { code: '0102', name: 'BANCO DE VENEZUELA' },
  { code: '0104', name: 'BANCO VENEZOLANO DE CREDITO' },
  { code: '0105', name: 'BANCO MERCANTIL' },
  { code: '0108', name: 'BANCO PROVINCIAL' },
  { code: '0114', name: 'BANCARIBE' },
  { code: '0134', name: 'BANESCO' },
  { code: '0137', name: 'SOFITASA' },
  { code: '0138', name: 'BANCO PLAZA' },
  { code: '0156', name: '100% BANCO' },
  { code: '0163', name: 'BANCO DEL TESORO' },
  { code: '0168', name: 'BANCRECER' },
  { code: '0171', name: 'BANCO ACTIVO' },
  { code: '0172', name: 'BANCAMIGA BANCO UNIVERSAL, C.A.' },
  { code: '0174', name: 'BANPLUS BANCO COMERCIAL' },
  { code: '0175', name: 'BANCO DIGITAL DE LOS TRABAJADORES' },
  { code: '0177', name: 'BANCO DE LAS FUERZAS ARMADAS BANFANB' },
  { code: '0178', name: 'N58 BANCO DIGITAL' },
  { code: '0191', name: 'BANCO NACIONAL DE CREDITO' },
];


/* Los pasos del flujo. Tienen nombre y no sólo número: «2 de 3» no informa
   nada, «Monto» sí. Es la misma pieza `Progreso` del flujo de Venezuela. */
const PASOS = [
  { numero: 1, clave: 'beneficiario', titulo: 'Beneficiario' },
  { numero: 2, clave: 'monto', titulo: 'Monto' },
  { numero: 3, clave: 'pago', titulo: 'Pago' },
];

/* ─── Piezas de esta pantalla ─────────────────────────────────────────────

   Estaban definidas ADENTRO del componente. React las trata como un tipo
   nuevo en cada dibujo, así que las desmonta y las vuelve a montar: el campo
   que estabas escribiendo pierde el foco a la primera tecla. El linter lo
   marca como `static-components` y tiene razón.                            */

/* El nombre del banco y el destino, resueltos igual que en el otro flujo:
   las fichas viejas guardan el CODIGO en `bank`, y mostrarlo crudo daba
   «0134 -» en pantalla. */
const banco = (b) => nombreDelBanco(b, VENEZUELAN_BANKS);
const destino = (b) => (b?.payment_type === 'pago_movil'
  ? telefonoLegible(b?.phone) : cuentaAbreviada(b?.account_number));

/* La ficha del beneficiario. Una sola definición para los tres lugares donde
   aparece: la lista, el encabezado del monto y el resumen del pago. Antes
   cada uno la dibujaba a su manera y decían cosas distintas. */
function FichaBeneficiario({ b, compacta }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
      <span style={{
        width: compacta ? '36px' : '42px', height: compacta ? '36px' : '42px',
        borderRadius: '50%', flexShrink: 0, background: C.marcaSuave,
        color: C.marca, fontSize: compacta ? '13px' : '14.5px', fontWeight: 700,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {iniciales(b?.full_name)}
      </span>
      <span style={{ minWidth: 0 }}>
        <span style={{
          display: 'block', fontSize: '15px', fontWeight: 700, color: C.tinta,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {b?.full_name || '—'}
        </span>
        <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
          {banco(b)} · {destino(b)}
        </span>
      </span>
    </div>
  );
}

const SOLAPAS = [
  { id: 'enviar', label: 'Enviar', Icono: Zap },
  { id: 'billetera', label: 'Billetera', Icono: Wallet },
  { id: 'historial', label: 'Historial', Icono: ListOrdered },
];

function Marco({ navigate, solapa, irASolapa, children }) {
  return (
    <div className="env" style={{ minHeight: '100vh', background: C.fondo,
      fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif' }}>
      <style>{HOJA}</style>
      <header style={{
        background: C.lienzo, borderBottom: `1px solid ${C.linea}`,
        position: 'sticky', top: 0, zIndex: 20,
      }}>
        <div style={{
          maxWidth: '640px', margin: '0 auto', padding: '0 16px', height: '60px',
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <button type="button" onClick={() => navigate('/')} className="env-tap"
            aria-label="Volver al inicio"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px',
              height: '38px', padding: '0 12px', borderRadius: '10px',
              border: `1px solid ${C.linea}`, background: C.lienzo,
              color: C.texto, fontSize: '14px', fontWeight: 600, cursor: 'pointer',
            }}>
            <ArrowLeft size={17} /> Volver
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: '15.5px', fontWeight: 700, color: C.tinta }}>
              Enviar con Bitcoin
            </p>
            <p style={{ margin: 0, fontSize: '12px', color: C.tenue }}>Red Lightning</p>
          </div>
          <NotificationBell />
        </div>
        <div style={{ maxWidth: '640px', margin: '0 auto', padding: '0 16px', display: 'flex', gap: '4px' }}>
          {SOLAPAS.map((s) => {
            // Sin desestructurar el icono: el linter de este repositorio no
            // cuenta el uso en JSX de un parámetro desestructurado y lo
            // reportaría sin usar. Mismo rodeo que en `ComoFunciona.jsx`.
            const Icono = s.Icono;
            const { id, label } = s;
            const activa = solapa === id;
            return (
              <button key={id} type="button" aria-current={activa ? 'page' : undefined}
                onClick={() => irASolapa(id)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '7px',
                  padding: '11px 14px', border: 'none', background: 'none',
                  cursor: 'pointer', fontSize: '14px',
                  fontWeight: activa ? 700 : 500,
                  color: activa ? C.marca : C.suave,
                  borderBottom: `2px solid ${activa ? C.marca : 'transparent'}`,
                }}>
                <Icono size={16} /> {label}
              </button>
            );
          })}
        </div>
      </header>
      <main style={{ maxWidth: '640px', margin: '0 auto', padding: '20px 16px 44px' }}>
        {children}
      </main>
    </div>
  );
}

export default function BTCLightning() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [showPin, setShowPin] = useState(false);
  const [precioBTC, setPrecioBTC] = useState(null);
  // Sin valor por defecto, y es lo importante de esta línea. Antes decía 680.
  // Con un número escrito acá, si `/btc/precio` no contesta la pantalla no se
  // ve rota: se ve bien y miente. `Send.jsx` ya había pasado por esto.
  const [tasaVES, setTasaVES] = useState(null);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);
  const [paymentType, setPaymentType] = useState('pago_movil');
  const [bankSearch, setBankSearch] = useState('');
  const [showBankDropdown, setShowBankDropdown] = useState(false);
  const bankRef = useRef(null);
    const [activeTab, setActiveTab] = useState('enviar');
    const [btcWallet, setBtcWallet] = useState(null);
  const [newBenef, setNewBenef] = useState({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '', account_number: '' });
  const [usd, setUsd] = useState('');
  const [invoiceData, setInvoiceData] = useState(null);
  const [countdown, setCountdown] = useState(1800);
  const countdownRef = useRef(null);
  const [loadingWallet, setLoadingWallet] = useState(false);
  const [loadingHistorial, setLoadingHistorial] = useState(false);
  const [btcHistorial, setBtcHistorial] = useState([]);
  const paymentPollingRef = useRef(null);
  const kycVerificado = user?.verification_status === 'verified';

  const fetchBtcWallet = async () => {
    try {
      setLoadingWallet(true);
      const res = await api.get('/btc/wallet');
      setBtcWallet(res.data);
    } catch { setBtcWallet(null); } finally { setLoadingWallet(false); }
  };

  const fetchBtcHistorial = async () => {
    try {
      setLoadingHistorial(true);
      const res = await api.get('/btc/historial');
      setBtcHistorial(res.data.remesas || []);
    } catch { setBtcHistorial([]); } finally { setLoadingHistorial(false); }
  };

  useEffect(() => {
    if (activeTab === 'billetera') fetchBtcWallet();
    if (activeTab === 'historial') fetchBtcHistorial();
  }, [activeTab]);

  useEffect(() => {
    fetchPrecioBTC();
    // Restaurar invoice de sessionStorage si existe
    const savedInvoice = sessionStorage.getItem('btc_invoice');
    if (savedInvoice) {
      try {
        const inv = JSON.parse(savedInvoice);
        setInvoiceData(inv);
        setStep(3);
      } catch {
        // Lo guardado no se pudo leer. Se descarta y se sigue: un invoice
        // ilegible en sessionStorage no puede impedir abrir la pantalla.
        sessionStorage.removeItem('btc_invoice');
      }
    }
    loadBeneficiaries();
    // Restaurar estado real desde el servidor (sobrevive aunque el navegador
    // cierre la pestaña mientras el usuario paga en su billetera). Si la remesa
    // ya fue pagada, mostramos la pantalla de éxito al volver.
    (async () => {
      try {
        const r = await api.get('/btc/mi-remesa-activa');
        const rem = r.data?.remesa;
        if (rem && ['pagado', 'enviado', 'completado'].includes(rem.estado)) {
          sessionStorage.removeItem('btc_invoice');
          setStep(4);
        } else if (rem && rem.estado === 'pendiente' && rem.expira_en && new Date(rem.expira_en) > new Date()) {
          setInvoiceData({
            remesa_id: rem.remesa_id,
            payment_request: rem.payment_request,
            qr: 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(rem.payment_request || ''),
            sats: rem.sats,
            ves_recibe: rem.ves_recibe,
            usd_cliente: rem.usd_cliente,
            btc_pagar: rem.btc_pagar,
            expira_en: rem.expira_en,
          });
          if (rem.usd_cliente != null) setUsd(String(rem.usd_cliente));
          if (rem.beneficiario_data) setSelectedBeneficiary(rem.beneficiario_data);
          setStep(3);
        }
      } catch { /* consulta opcional, no rompe el flujo */ }
    })();
    // Cada diez segundos, por decisión del operador. No hay caché del lado
    // del servidor: cada consulta va en vivo a blockchain.info, así que el
    // precio en pantalla nunca tiene más de diez segundos.
    //
    // Es también lo que hace que `EDAD_MAXIMA_DEL_PRECIO` —los treinta
    // segundos que el servidor tolera si el proveedor no contesta— alcance
    // para unos tres intentos. Si algún día se espacia este intervalo, hay que
    // mirar aquel número.
    const interval = setInterval(fetchPrecioBTC, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handler = (e) => { if (bankRef.current && !bankRef.current.contains(e.target)) setShowBankDropdown(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    if (step === 3 && invoiceData) {
      let _secs = 1800;
      if (invoiceData.expira_en) {
        const _exp = new Date(invoiceData.expira_en);
        if (!isNaN(_exp.getTime()) && _exp.getTime() > Date.now()) {
          _secs = Math.max(0, Math.floor((_exp.getTime() - Date.now()) / 1000));
        }
      }
      setCountdown(_secs);
      countdownRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) { clearInterval(countdownRef.current); toast.error('El invoice expiro. Genera uno nuevo.'); return 0; }
          return prev - 1;
        });
      }, 1000);
      // Polling para detectar pago automaticamente
      paymentPollingRef.current = setInterval(async () => {
        try {
          const res = await api.get('/btc/status/' + invoiceData.remesa_id);
          if (res.data.estado === 'pagado') {
            clearInterval(paymentPollingRef.current);
            clearInterval(countdownRef.current);
            setStep(4);
            sessionStorage.removeItem('btc_invoice');
          }
        } catch {
          // A propósito, y por ser un poll: corre cada 5 s mientras el usuario
          // mira la pantalla. Un aviso por cada corte de red le llenaría el
          // visor por algo que se arregla solo en el intento siguiente.
        }
      }, 5000);
      return () => {
        clearInterval(countdownRef.current);
        clearInterval(paymentPollingRef.current);
      };
    }
  }, [step, invoiceData]);




  const fetchPrecioBTC = async () => {
    try { const res = await api.get('/btc/precio'); setPrecioBTC(res.data.precio_btc); setTasaVES(res.data.tasa_btc_ves); }
    catch { /* mantiene ultimo precio */ }
  };




  const loadBeneficiaries = async () => {
    try { const res = await api.get('/beneficiaries'); setBeneficiaries(res.data || []); }
    catch { console.error('Error cargando beneficiarios'); }
  };




  const usdNum = parseFloat(usd) || 0;
  const precioConMargen = precioBTC ? precioBTC * 0.99 : null;
  // `null` y no la cadena '---'. Un guión en el lugar de una cifra parece un
  // error de carga; `null` deja que la pantalla decida no mostrar la fila.
  const btcAPagar = precioConMargen && usdNum > 0 ? ((usdNum * 1.02) / precioConMargen).toFixed(8) : null;
  const hayCotizacion = precioBTC != null && tasaVES != null;
  const vesRecibe = hayCotizacion && usdNum > 0 ? usdNum * tasaVES : null;
  const vesRecibeTexto = vesRecibe === null ? null : fmt(vesRecibe);
  const alcanzable = !selectedBeneficiary ? 1 : (usdNum > 0 && hayCotizacion ? 3 : 2);
  const fmtCountdown = (s) => Math.floor(s/60).toString().padStart(2,'0') + ':' + (s%60).toString().padStart(2,'0');
  const filteredBanks = VENEZUELAN_BANKS.filter(b => b.code.includes(bankSearch) || b.name.toLowerCase().includes(bankSearch.toLowerCase()));
  const filteredBenef = beneficiaries.filter(b => b.payment_type === paymentType);
  const copyText = (t) => navigator.clipboard.writeText(t).then(() => toast.success('Copiado'));




  const handleSaveNewBeneficiary = async () => {
    if (!newBenef.full_name || !newBenef.cedula || !newBenef.bank_code) return toast.error('Completa nombre, cedula y banco');
    if (paymentType === 'pago_movil' && !newBenef.phone) return toast.error('Telefono requerido');
    if (paymentType === 'transferencia' && !newBenef.account_number) return toast.error('Numero de cuenta requerido');
    setLoading(true);
    try {
      const payload = { full_name: newBenef.full_name, cedula: newBenef.cedula, bank_code: newBenef.bank_code, bank: newBenef.bank, payment_type: paymentType, ...(paymentType === 'pago_movil' ? { phone: newBenef.phone } : { account_number: newBenef.account_number }) };
      const res = await api.post('/beneficiaries', payload);
      setBeneficiaries(p => [...p, res.data]);
      setSelectedBeneficiary(res.data);
      setShowNewBeneficiary(false);
      setNewBenef({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '', account_number: '' });
      toast.success('Beneficiario agregado');
    } catch (err) { toast.error(err.response?.data?.detail || 'Error al guardar'); }
    finally { setLoading(false); }
  };




  const pedirConfirmacion = () => {
    if (!selectedBeneficiary) return toast.error('Selecciona un beneficiario');
    if (!usdNum || usdNum <= 0) return toast.error('Ingresa un monto valido');
    if (!precioBTC) return toast.error('Esperando precio BTC...');
    setShowPin(true);
  };
  const handleGenerarInvoice = async () => {
    if (!selectedBeneficiary) return toast.error('Selecciona un beneficiario');
    if (!usdNum || usdNum <= 0) return toast.error('Ingresa un monto valido');
    if (!precioBTC) return toast.error('Esperando precio BTC...');
    setLoading(true);
    try {
      const res = await api.post('/btc/generar-invoice', { usd_cliente: usdNum, beneficiario_id: selectedBeneficiary.beneficiary_id });
      setInvoiceData(res.data);
      sessionStorage.setItem('btc_invoice', JSON.stringify(res.data));
      setStep(3);
      try {
        const h = await api.post('/pin/hint-check');
        if (h.data?.hint) toast(h.data.message || 'Configura tu PIN para mayor seguridad en tu perfil.', { icon: '🔒' });
      } catch { /* aviso opcional */ }
    } catch (err) { toast.error(err.response?.data?.detail || 'Error al generar invoice'); }
    finally { setLoading(false); }
  };

  const handleCancelRemesa = async () => {
    if (!invoiceData?.remesa_id) return;
    try {
      await api.post('/btc/cancelar/' + invoiceData.remesa_id);
    } catch {
      // A propósito: cancelar es un pedido de cortesía al servidor. Pase lo
      // que pase con él, abajo se limpia el estado local y el usuario vuelve
      // al paso anterior, que es lo que pidió al apretar el botón.
    } finally {
      clearInterval(paymentPollingRef.current);
      clearInterval(countdownRef.current);
      setInvoiceData(null);
      sessionStorage.removeItem('btc_invoice');
      setStep(2);
    }
  };


  /* ─── Puerta de KYC ─────────────────────────────────────────────────── */

  if (!kycVerificado) {
    return (
      <Marco navigate={navigate} solapa={activeTab} irASolapa={irASolapa}>
        <Aviso tono="alerta" titulo="Falta verificar tu identidad">
          Para enviar pagando con Bitcoin necesitamos tu verificación completa.
          Es el mismo requisito que para el resto de los envíos, y se hace una
          sola vez.
          <div style={{ marginTop: '13px' }}>
            <Boton tipo="primario" onClick={() => navigate('/verification')} Icono={ArrowRight} iconoDerecha>
              Verificar mi identidad
            </Boton>
          </div>
        </Aviso>
      </Marco>
    );
  }

  /* ─── La pantalla ───────────────────────────────────────────────────── */

  const irAPaso = (n) => { if (n <= alcanzable && n < 3) setStep(n); };
  const irASolapa = (id) => {
    setActiveTab(id);
    if (id !== 'enviar') {
      setStep(1); setInvoiceData(null); setSelectedBeneficiary(null); setUsd('');
    }
  };

  return (
    <Marco navigate={navigate} solapa={activeTab} irASolapa={irASolapa}>
      {activeTab === 'enviar' && step <= 3 ? (
        <Progreso pasos={PASOS} paso={step} alcanzable={alcanzable} irA={irAPaso} />
      ) : null}

      {/* ── Paso 1: a quién ─────────────────────────────────────────── */}
      {activeTab === 'enviar' && step === 1 && (
        <>
          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <h2 style={{ margin: '0 0 4px 0', fontSize: '17px', fontWeight: 700, color: C.tinta }}>
              ¿Cómo va a recibir el dinero?
            </h2>
            <p style={{ ...ayuda, marginBottom: '14px' }}>
              Elegí primero el método: los beneficiarios se guardan por separado.
            </p>
            <div role="radiogroup" style={{ display: 'grid', gap: '10px' }}>
              <Opcion
                elegida={paymentType === 'pago_movil'} Icono={Smartphone}
                titulo="Pago Móvil" detalle="Al teléfono del beneficiario"
                testid="btc-metodo-pago-movil"
                onClick={() => { setPaymentType('pago_movil'); setSelectedBeneficiary(null); }} />
              <Opcion
                elegida={paymentType === 'transferencia'} Icono={Building2}
                titulo="Transferencia" detalle="A su cuenta bancaria"
                testid="btc-metodo-transferencia"
                onClick={() => { setPaymentType('transferencia'); setSelectedBeneficiary(null); }} />
            </div>
          </section>

          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '14px' }}>
              <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: C.tinta }}>
                ¿A quién le enviás?
              </h2>
              <button type="button" className="env-chip"
                onClick={() => setShowNewBeneficiary(!showNewBeneficiary)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '8px 13px', borderRadius: '9px', background: C.lienzo,
                  border: `1px solid ${C.lineaFuerte}`, color: C.texto,
                  fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                }}>
                {showNewBeneficiary ? <><X size={14} /> Cancelar</> : <><Plus size={14} /> Nuevo</>}
              </button>
            </div>

            {showNewBeneficiary && (
              <div style={{
                background: C.fondo, border: `1px solid ${C.linea}`,
                borderRadius: '14px', padding: '16px', marginBottom: '16px',
              }}>
                <p style={{ ...microEtiqueta, marginBottom: '13px' }}>
                  Nuevo · {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}
                </p>
                {[
                  { key: 'full_name', label: 'Nombre completo', ph: 'Juan Pérez' },
                  { key: 'cedula', label: 'Cédula', ph: 'V-12345678' },
                ].map((f) => (
                  <div key={f.key} style={{ marginBottom: '12px' }}>
                    <label style={etiqueta} htmlFor={`btc-${f.key}`}>{f.label}</label>
                    <input id={`btc-${f.key}`} className="env-campo" style={campo} placeholder={f.ph}
                      value={newBenef[f.key]}
                      onChange={(e) => setNewBenef((p) => ({ ...p, [f.key]: e.target.value }))} />
                  </div>
                ))}

                <div style={{ marginBottom: '12px', position: 'relative' }} ref={bankRef}>
                  <label style={etiqueta} htmlFor="btc-banco">Banco</label>
                  <div style={{ position: 'relative' }}>
                    <Search size={15} style={{
                      position: 'absolute', left: '13px', top: '50%',
                      transform: 'translateY(-50%)', color: C.tenue, pointerEvents: 'none',
                    }} />
                    <input id="btc-banco" className="env-campo" style={{ ...campo, paddingLeft: '38px' }}
                      placeholder="Buscar por nombre o código"
                      value={newBenef.bank || bankSearch}
                      onChange={(e) => {
                        setBankSearch(e.target.value);
                        setNewBenef((p) => ({ ...p, bank: e.target.value, bank_code: '' }));
                        setShowBankDropdown(true);
                      }}
                      onFocus={() => setShowBankDropdown(true)} />
                  </div>
                  {showBankDropdown && filteredBanks.length > 0 && (
                    <ul style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                      margin: '6px 0 0 0', padding: '5px', listStyle: 'none',
                      background: C.lienzo, border: `1px solid ${C.lineaFuerte}`,
                      borderRadius: '12px', boxShadow: '0 10px 28px rgba(16,24,40,.12)',
                      maxHeight: '210px', overflowY: 'auto',
                    }}>
                      {filteredBanks.map((b) => (
                        <li key={b.code}>
                          <button type="button" className="env-chip"
                            onClick={() => {
                              setNewBenef((p) => ({ ...p, bank: b.name, bank_code: b.code }));
                              setBankSearch(''); setShowBankDropdown(false);
                            }}
                            style={{
                              display: 'flex', gap: '10px', width: '100%', textAlign: 'left',
                              padding: '10px 11px', borderRadius: '9px', border: 'none',
                              background: 'none', color: C.texto, fontSize: '13.5px', cursor: 'pointer',
                            }}>
                            <span style={{ color: C.tenue, fontVariantNumeric: 'tabular-nums' }}>{b.code}</span>
                            <span>{b.name}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label style={etiqueta} htmlFor="btc-destino">
                    {paymentType === 'pago_movil' ? 'Teléfono' : 'Número de cuenta'}
                  </label>
                  <input id="btc-destino" className="env-campo" style={campo}
                    inputMode="numeric"
                    placeholder={paymentType === 'pago_movil' ? '0414 123 4567' : '0102 0000 00 0000000000'}
                    value={paymentType === 'pago_movil' ? newBenef.phone : newBenef.account_number}
                    onChange={(e) => setNewBenef((p) => (paymentType === 'pago_movil'
                      ? { ...p, phone: e.target.value }
                      : { ...p, account_number: e.target.value }))} />
                </div>

                <Boton tipo="primario" ancho onClick={handleSaveNewBeneficiary}
                  disabled={loading} Icono={Check} testid="btc-guardar-beneficiario">
                  {loading ? 'Guardando…' : 'Guardar beneficiario'}
                </Boton>
              </div>
            )}

            {filteredBenef.length === 0 && !showNewBeneficiary ? (
              <div style={{ textAlign: 'center', padding: '26px 8px' }}>
                <User size={30} color={C.tenue} />
                <p style={{ margin: '10px 0 0 0', fontSize: '14px', color: C.suave }}>
                  Todavía no tenés beneficiarios de{' '}
                  {paymentType === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}.
                </p>
                <p style={{ ...ayuda, marginTop: '3px' }}>Agregá uno con el botón «Nuevo».</p>
              </div>
            ) : (
              <div role="radiogroup" style={{ display: 'grid', gap: '9px' }}>
                {filteredBenef.map((b) => {
                  const elegido = selectedBeneficiary?.beneficiary_id === b.beneficiary_id;
                  return (
                    <button key={b.beneficiary_id} type="button" role="radio" aria-checked={elegido}
                      onClick={() => setSelectedBeneficiary(b)} className="env-op env-tap"
                      style={{
                        display: 'flex', alignItems: 'center', gap: '12px', width: '100%',
                        padding: '14px', borderRadius: '14px', textAlign: 'left', cursor: 'pointer',
                        border: `1px solid ${elegido ? C.marca : C.linea}`,
                        background: elegido ? C.marcaSuave : C.lienzo,
                        boxShadow: elegido ? '0 0 0 3px rgba(79,70,229,.10)' : 'none',
                      }}>
                      <span style={{ flex: 1, minWidth: 0 }}><FichaBeneficiario b={b} compacta /></span>
                      <span style={{
                        width: '20px', height: '20px', borderRadius: '50%', flexShrink: 0,
                        border: `2px solid ${elegido ? C.marca : C.lineaFuerte}`,
                        background: elegido ? C.marca : 'transparent',
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        {elegido ? <Check size={12} color="#fff" strokeWidth={3} /> : null}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <Boton tipo="primario" ancho onClick={() => setStep(2)}
            disabled={!selectedBeneficiary} Icono={ArrowRight} iconoDerecha testid="btc-continuar">
            Continuar
          </Boton>
        </>
      )}

      {/* ── Paso 2: cuánto ──────────────────────────────────────────── */}
      {activeTab === 'enviar' && step === 2 && (
        <>
          <div style={{
            ...tarjeta, background: C.fondo, padding: '14px 16px', marginBottom: '16px',
            display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
          }}>
            <span style={{ flex: 1, minWidth: '200px' }}>
              <FichaBeneficiario b={selectedBeneficiary} compacta />
            </span>
            <button type="button" onClick={() => setStep(1)} className="env-chip"
              style={{
                padding: '8px 13px', borderRadius: '9px', background: C.lienzo,
                border: `1px solid ${C.lineaFuerte}`, color: C.texto,
                fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              }}>
              Cambiar
            </button>
          </div>

          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <h2 style={{ margin: '0 0 14px 0', fontSize: '17px', fontWeight: 700, color: C.tinta }}>
              ¿Cuánto querés enviar?
            </h2>
            <label style={etiqueta} htmlFor="btc-monto">Monto en USDI</label>
            <input id="btc-monto" type="number" inputMode="decimal" min="1"
              className="env-campo" placeholder="0" value={usd}
              onChange={(e) => setUsd(e.target.value)}
              data-testid="btc-monto"
              style={{ ...campo, fontSize: '30px', fontWeight: 700, textAlign: 'center', padding: '16px' }} />

            {!hayCotizacion ? (
              <div style={{ marginTop: '16px' }}>
                <Aviso tono="alerta" titulo="Todavía no tenemos la cotización">
                  No se pudo leer el precio de Bitcoin ni la tasa del día. No
                  mostramos una conversión estimada a propósito: en esta
                  pantalla el número es todo, y uno inventado sería una promesa
                  que no podemos cumplir. Reintentamos solos cada diez segundos.
                </Aviso>
              </div>
            ) : usdNum > 0 ? (
              <>
                <dl style={{
                  margin: '16px 0 0 0', padding: '15px 16px', borderRadius: '12px',
                  background: C.fondo, border: `1px solid ${C.linea}`,
                }}>
                  {[
                    ['Precio de Bitcoin', `$${fmt(precioBTC)}`],
                    ['Pagás en Bitcoin', `${btcAPagar} BTC`],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: '14px', marginBottom: '9px' }}>
                      <dt style={{ fontSize: '13.5px', color: C.suave }}>{k}</dt>
                      <dd style={{ margin: 0, fontSize: '13.5px', fontWeight: 600, color: C.texto }}>{v}</dd>
                    </div>
                  ))}
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                    gap: '14px', paddingTop: '11px', borderTop: `1px solid ${C.linea}`,
                  }}>
                    <dt style={{ fontSize: '13.5px', color: C.suave }}>El beneficiario recibe</dt>
                    <dd style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: C.exito }}>
                      {vesRecibeTexto} <span style={{ fontSize: '13px', color: C.tenue }}>VES</span>
                    </dd>
                  </div>
                </dl>
                <div style={{ marginTop: '13px' }}>
                  <Aviso tono="info">
                    La cotización incluye un 1 % de margen por la volatilidad de
                    Bitcoin. Los <strong>{vesRecibeTexto} VES</strong> quedan fijos
                    desde que generás el cobro: si el precio se mueve mientras
                    pagás, el beneficiario recibe igual esa cifra.
                  </Aviso>
                </div>
              </>
            ) : (
              <p style={{ ...ayuda, marginTop: '13px' }}>
                Escribí un monto y te mostramos cuánto pagás en Bitcoin y cuánto
                recibe el beneficiario, antes de generar nada.
              </p>
            )}
          </section>

          <div style={{ display: 'flex', gap: '10px' }}>
            <Boton onClick={() => setStep(1)} Icono={ArrowLeft}>Atrás</Boton>
            <Boton tipo="primario" ancho onClick={pedirConfirmacion} Icono={Zap}
              testid="btc-generar"
              disabled={loading || !usdNum || usdNum <= 0 || !hayCotizacion}>
              {loading ? 'Generando…' : 'Generar el cobro'}
            </Boton>
          </div>
          <PinConfirm open={showPin} onClose={() => setShowPin(false)} onVerified={handleGenerarInvoice} />
        </>
      )}

      {/* ── Paso 3: pagar ───────────────────────────────────────────── */}
      {activeTab === 'enviar' && step === 3 && invoiceData && (
        <>
          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px', textAlign: 'center' }}>
            <h2 style={{ margin: '0 0 6px 0', fontSize: '19px', fontWeight: 700, color: C.tinta }}>
              Pagá desde tu billetera
            </h2>
            <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: C.suave, lineHeight: 1.55 }}>
              Apenas se confirme el pago en la red, se procesa el envío de{' '}
              <strong style={{ color: C.tinta }}>{vesRecibeTexto} VES</strong> a{' '}
              <strong style={{ color: C.tinta }}>{selectedBeneficiary?.full_name}</strong>.
              Te avisamos cuando esté hecho.
            </p>
            {invoiceData.qr && (
              <img src={invoiceData.qr} alt="Código QR para pagar por Lightning"
                style={{
                  width: '210px', height: '210px', borderRadius: '14px',
                  border: `1px solid ${C.linea}`, display: 'block', margin: '0 auto 14px',
                }} />
            )}
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px',
              padding: '7px 14px', borderRadius: '999px', fontSize: '13px', fontWeight: 700,
              background: countdown < 300 ? C.errorSuave : C.fondo,
              color: countdown < 300 ? C.error : C.texto,
              border: `1px solid ${countdown < 300 ? C.errorBorde : C.linea}`,
            }}>
              <Clock size={14} /> Vence en {fmtCountdown(countdown)}
            </span>
          </section>

          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <p style={{ ...microEtiqueta, marginBottom: '9px' }}>O copiá el cobro</p>
            <p style={{
              margin: '0 0 12px 0', fontSize: '12px', color: C.suave,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              wordBreak: 'break-all', lineHeight: 1.55,
            }}>
              {invoiceData.payment_request?.slice(0, 84)}…
            </p>
            <Boton ancho onClick={() => copyText(invoiceData.payment_request)} Icono={Copy}>
              Copiar el cobro completo
            </Boton>
          </section>

          <section style={{ ...tarjeta, padding: '20px', marginBottom: '16px' }}>
            <p style={{ ...microEtiqueta, marginBottom: '13px' }}>Resumen</p>
            <div style={{ marginBottom: '13px' }}>
              <FichaBeneficiario b={selectedBeneficiary} />
            </div>
            <dl style={{ margin: 0 }}>
              {[
                ['Método', selectedBeneficiary?.payment_type === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'],
                ['Monto enviado', `${fmt(usdNum)} USDI`],
              ].map(([k, v]) => (
                <div key={k} style={{
                  display: 'flex', justifyContent: 'space-between', gap: '14px',
                  padding: '9px 0', borderBottom: `1px solid ${C.linea}`,
                }}>
                  <dt style={{ fontSize: '13.5px', color: C.suave }}>{k}</dt>
                  <dd style={{ margin: 0, fontSize: '13.5px', fontWeight: 600, color: C.texto }}>{v}</dd>
                </div>
              ))}
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                gap: '14px', paddingTop: '11px',
              }}>
                <dt style={{ fontSize: '13.5px', color: C.suave }}>El beneficiario recibe</dt>
                <dd style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: C.exito }}>
                  {vesRecibeTexto || '—'} <span style={{ fontSize: '12px', color: C.tenue }}>VES</span>
                </dd>
              </div>
            </dl>
          </section>

          <div style={{ display: 'grid', gap: '10px' }}>
            <Boton ancho onClick={() => navigate('/')}>Volver al inicio</Boton>
            <button type="button" onClick={handleCancelRemesa}
              style={{
                height: '52px', borderRadius: '12px', cursor: 'pointer',
                border: `1px solid ${C.errorBorde}`, background: C.errorSuave,
                color: C.error, fontSize: '15px', fontWeight: 600,
              }}>
              Cancelar este pago
            </button>
          </div>
        </>
      )}

      {/* ── Paso 4: pagado ──────────────────────────────────────────── */}
      {activeTab === 'enviar' && step === 4 && (
        <section style={{ ...tarjeta, padding: '32px 24px', textAlign: 'center' }}>
          <span style={{
            width: '58px', height: '58px', borderRadius: '50%', background: C.exitoSuave,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: '14px',
          }}>
            <Check size={28} color={C.exito} strokeWidth={2.5} />
          </span>
          <h2 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: 700, color: C.tinta }}>
            Recibimos tu pago
          </h2>
          <p style={{ margin: '0 0 22px 0', fontSize: '14.5px', color: C.suave, lineHeight: 1.6 }}>
            El envío ya está en proceso. Te llega una notificación cuando el
            beneficiario tenga el dinero, normalmente en menos de 15 minutos.
          </p>
          <Boton tipo="primario" onClick={() => {
            setStep(1); setInvoiceData(null);            setSelectedBeneficiary(null); setUsd('');
          }}>
            Hacer otro envío
          </Boton>
        </section>
      )}

      {/* ── Billetera ───────────────────────────────────────────────── */}
      {activeTab === 'billetera' && (
        <>
          <section style={{ ...tarjeta, padding: '26px 22px', marginBottom: '16px', textAlign: 'center' }}>
            <p style={{ ...microEtiqueta, marginBottom: '7px' }}>Saldo BTC-VES</p>
            <p style={{ margin: 0, fontSize: '36px', fontWeight: 700, color: C.tinta, letterSpacing: '-.02em' }}>
              {loadingWallet ? '—' : fmt(btcWallet?.saldo || 0)}
            </p>
            <p style={{ ...ayuda, marginTop: '4px' }}>bolívares disponibles</p>
            <div style={{ marginTop: '16px' }}>
              <Boton onClick={fetchBtcWallet} Icono={RefreshCw} disabled={loadingWallet}>
                {loadingWallet ? 'Actualizando…' : 'Actualizar'}
              </Boton>
            </div>
          </section>
          <section style={{ ...tarjeta, padding: '20px' }}>
            <p style={{ ...microEtiqueta, marginBottom: '9px' }}>Qué es este saldo</p>
            <p style={{ margin: 0, fontSize: '14px', color: C.texto, lineHeight: 1.65 }}>
              Cuando pagás con Bitcoin, registramos el pago al confirmarse en la
              red. Ese monto es el equivalente en bolívares que se le envía a tu
              beneficiario al completar la transferencia.
            </p>
          </section>
        </>
      )}

      {/* ── Historial ───────────────────────────────────────────────── */}
      {activeTab === 'historial' && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '14px' }}>
            <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: C.tinta }}>Tus envíos</h2>
            <Boton onClick={fetchBtcHistorial} Icono={RefreshCw} disabled={loadingHistorial}>
              {loadingHistorial ? 'Actualizando…' : 'Actualizar'}
            </Boton>
          </div>
          {loadingHistorial ? (
            <p style={{ ...ayuda, textAlign: 'center', padding: '30px 0' }}>Cargando…</p>
          ) : btcHistorial.length === 0 ? (
            <section style={{ ...tarjeta, padding: '34px 22px', textAlign: 'center' }}>
              <ListOrdered size={28} color={C.tenue} />
              <p style={{ margin: '11px 0 0 0', fontSize: '15px', fontWeight: 600, color: C.texto }}>
                Todavía no hiciste ningún envío con Bitcoin
              </p>
              <p style={{ ...ayuda, marginTop: '3px' }}>Los que hagas van a aparecer acá.</p>
            </section>
          ) : (
            <div style={{ display: 'grid', gap: '11px' }}>
              {btcHistorial.map((rem, i) => {
                const cfg = {
                  pendiente: [C.alerta, C.alertaSuave, C.alertaBorde, 'Pendiente'],
                  pagado: [C.marca, C.marcaSuave, C.marcaBorde, 'Pagado'],
                  enviado: [C.exito, C.exitoSuave, C.exitoBorde, 'Completado'],
                  cancelado: [C.error, C.errorSuave, C.errorBorde, 'Cancelado'],
                }[rem.estado] || [C.suave, C.fondo, C.linea, rem.estado];
                const [color, fondo, borde, texto] = cfg;
                return (
                  <article key={rem.remesa_id || i} style={{ ...tarjeta, padding: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                      <div style={{ minWidth: 0 }}>
                        <p style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: C.tinta }}>
                          {fmt(rem.ves_recibe || 0)} <span style={{ fontSize: '12.5px', color: C.tenue }}>VES</span>
                        </p>
                        <p style={{ margin: '2px 0 0 0', fontSize: '12.5px', color: C.suave }}>
                          {rem.usd_cliente ? `${fmt(rem.usd_cliente)} USDI` : ''}
                          {rem.sats ? ` · ${Number(rem.sats).toLocaleString('es-VE')} sats` : ''}
                        </p>
                      </div>
                      <span style={{
                        flexShrink: 0, padding: '5px 11px', borderRadius: '999px',
                        fontSize: '12px', fontWeight: 700,
                        background: fondo, color, border: `1px solid ${borde}`,
                      }}>
                        {texto}
                      </span>
                    </div>
                    {rem.beneficiario_data && (
                      <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: `1px solid ${C.linea}` }}>
                        <FichaBeneficiario b={rem.beneficiario_data} compacta />
                      </div>
                    )}
                    <p style={{ ...ayuda, marginTop: '10px' }}>
                      {rem.creado_en ? new Date(rem.creado_en).toLocaleDateString('es-VE', {
                        day: '2-digit', month: 'short', year: 'numeric',
                        hour: '2-digit', minute: '2-digit',
                      }) : ''}
                    </p>
                  </article>
                );
              })}
            </div>
          )}
        </>
      )}
    </Marco>
  );
}
