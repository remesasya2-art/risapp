/**
 * Send.jsx — Enviar a Venezuela.
 *
 * QUE SE CAMBIO Y POR QUE
 *
 *   El flujo funcionaba. Lo que se rehizo es cómo se ve y qué se le dice al
 *   usuario mientras decide, más cuatro cosas que estaban mal:
 *
 *   1. LA TASA INVENTADA. `RateContext` arranca con `ris_to_ves: 110` como
 *      valor por defecto para que ninguna pantalla se rompa mientras carga. Si
 *      `/rate` fallaba, esta pantalla mostraba «1 RIS = 110,00 VES» y convertía
 *      con eso. El servidor aplicaba la real. O sea que le decíamos a alguien
 *      un número que no era, en la pantalla donde ese número es todo. Ahora,
 *      sin tasa confirmada por el servidor, no se convierte y no se avanza.
 *
 *   2. EL CAMPO EN BOLIVARES QUE NO EXISTIA. El archivo ya tenía `vesInput` y
 *      `lastEdited` —la maquinaria completa para escribir en bolívares— y el
 *      campo nunca se dibujaba. Quien manda dinero a Venezuela piensa en
 *      bolívares: «quiero que le lleguen 10.000», no «quiero mandar 60,61
 *      RIS». Ahora se puede escribir en cualquiera de los dos.
 *
 *   3. LO QUE SE MUESTRA ES LO QUE VA A PASAR. Si se escribe en bolívares, el
 *      RIS se redondea a dos decimales —es lo que el saldo admite— y los
 *      bolívares que se muestran se recalculan A PARTIR DE ESE RIS. Escribir
 *      10.000 y que diga «recibe 10.000,65» parece un detalle; decir «10.000»
 *      cuando van a llegar 10.000,65 es contar mal a propósito.
 *
 *   4. LA TASA QUE SE MUEVE MIENTRAS SE DECIDE. Se refresca sola cada cinco
 *      minutos. Entre mirar el monto y confirmar podían pasar más, y nadie
 *      avisaba. Ahora al llegar a confirmar se vuelve a pedir, y si cambió se
 *      dice con las dos cifras antes de que apriete el botón.
 *
 * EL CRITERIO VISUAL: PROFESIONAL PERO AMIGABLE
 *
 *   No es lo mismo que el panel de administración. Esto lo usa alguien desde
 *   el teléfono, probablemente apurado, mandándole plata a su familia. Serio
 *   quiere decir que se entienda de una y que no haya sorpresas; no quiere
 *   decir austero.
 *
 *     · Los pasos tienen NOMBRE, no sólo número. «2 de 4» no informa nada;
 *       «Método» sí. Y se puede volver tocando un paso ya hecho.
 *     · El monto viaja arriba en los pasos siguientes. Antes, del paso 2 en
 *       adelante, no se veía cuánto se estaba enviando.
 *     · La tasa es una tira propia, con su antigüedad y su botón de refrescar.
 *       Era un subtítulo diminuto y es el segundo dato más importante.
 *     · Los blancos y grises hacen el trabajo; el color aparece sólo donde
 *       significa algo: lo que recibe, un aviso, un error.
 */
import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { FormattedNumberInput } from '../components/common/FormattedNumberInput';
import {
  ArrowLeft, ArrowRight, AlertCircle, AlertTriangle, Building2, Check,
  CheckCircle2, Info, Plus, RefreshCw, Search, ShieldCheck, Smartphone, User, X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import PinConfirm from '../components/PinConfirm';
import { fmt } from '../utils/format';
import { Boton, Aviso, Progreso, Opcion } from '../components/flujo';
import {
  C, HOJA, tarjeta, etiqueta, microEtiqueta, campo, ayuda, iniciales,
} from '../components/flujo/estilos';
import {
  MENSAJE_DEL_MOTIVO, MOTIVO, PASOS, cuentaAbreviada, nombreDelBanco,
  risAEnviar, tasaSeMovio, telefonoLegible, ultimoPasoAlcanzable, validarMonto,
  vesARecibir,
} from '../utils/envioAVenezuela';

const VENEZUELAN_BANKS = [
  { code: '0001', name: 'Banco Central de Venezuela' },
  { code: '0102', name: 'Banco de Venezuela' },
  { code: '0104', name: 'Banco Venezolano de Crédito' },
  { code: '0105', name: 'Banco Mercantil' },
  { code: '0108', name: 'Banco Provincial' },
  { code: '0114', name: 'Bancaribe' },
  { code: '0115', name: 'Banco Exterior' },
  { code: '0128', name: 'Banco Caroní' },
  { code: '0134', name: 'Banesco' },
  { code: '0137', name: 'Sofitasa' },
  { code: '0138', name: 'Banco Plaza' },
  { code: '0145', name: 'Banco de Comercio Exterior' },
  { code: '0146', name: 'Banco de la Gente Emprendedora' },
  { code: '0151', name: 'Fondo Común' },
  { code: '0152', name: 'Bandes' },
  { code: '0156', name: '100% Banco' },
  { code: '0157', name: 'DelSur Banco Universal' },
  { code: '0163', name: 'Banco del Tesoro' },
  { code: '0166', name: 'Banco Agrícola' },
  { code: '0168', name: 'Bancrecer' },
  { code: '0169', name: 'R4 Banco Microfinanciero' },
  { code: '0171', name: 'Banco Activo' },
  { code: '0172', name: 'Bancamiga' },
  { code: '0173', name: 'Banco Internacional de Desarrollo' },
  { code: '0174', name: 'Banplus' },
  { code: '0175', name: 'Banco Digital de los Trabajadores' },
  { code: '0177', name: 'Banco de las Fuerzas Armadas (BANFANB)' },
  { code: '0178', name: 'N58 Banco Digital' },
  { code: '0191', name: 'Banco Nacional de Crédito' },
  { code: '0601', name: 'I.M.C.P' },
  { code: '0732', name: 'Fonden' },
  { code: '2017', name: 'ONT' },
  { code: '6000', name: 'Banavih' },
];

/* ─── Sistema visual ───────────────────────────────────────────────────────
   Vive en `components/flujo`, compartido con el flujo de BTC Lightning. Estaba
   escrito acá y se movió tal cual: dos pantallas que hacen lo mismo tienen que
   verse iguales, y con estilos copiados eso dura hasta el primer retoque en
   una sola de las dos.

   Lo que sigue abajo —la tira de tasa y el resumen del monto— se queda: es de
   esta pantalla y de ningún otro lugar.                                     */

/* ─── Piezas propias ───────────────────────────────────────────────────── */

function TiraDeTasa({ tasa, disponible, lastUpdated, ahora, onRefrescar, refrescando }) {
  // `ahora` llega desde afuera y avanza con un temporizador. Calcularlo acá con
  // `Date.now()` sería leer el reloj durante el render —impuro— y encima
  // dejaría el texto congelado: diría «hace 2 min» hasta que otra cosa
  // provocara un redibujo.
  const minutos = (lastUpdated && ahora)
    ? Math.floor((ahora - new Date(lastUpdated).getTime()) / 60000) : null;
  const antiguedad = minutos === null ? ''
    : (minutos < 1 ? 'recién actualizada' : `hace ${minutos} min`);

  return (
    <div style={{
      ...tarjeta, padding: '12px 15px', display: 'flex', alignItems: 'center',
      gap: '12px', flexWrap: 'wrap', marginBottom: '18px',
      borderColor: disponible ? C.linea : C.alertaBorde,
      background: disponible ? C.lienzo : C.alertaSuave,
    }}>
      <div style={{ flex: 1, minWidth: '190px' }}>
        <p style={microEtiqueta}>Tasa de hoy</p>
        {disponible ? (
          <>
            <p style={{ margin: '3px 0 0 0', fontSize: '16px', fontWeight: 700,
              color: C.tinta, whiteSpace: 'nowrap' }}>
              1 RIS = {fmt(tasa)} VES
            </p>
            {antiguedad ? (
              <p style={{ margin: '1px 0 0 0', fontSize: '12px', color: C.tenue }}>
                {antiguedad}
              </p>
            ) : null}
          </>
        ) : (
          <p style={{ margin: '3px 0 0 0', fontSize: '14px', fontWeight: 600, color: C.alerta }}>
            No disponible por ahora
          </p>
        )}
      </div>
      <button
        type="button" onClick={onRefrescar} disabled={refrescando}
        className="env-tap" aria-label="Actualizar la tasa" data-testid="refrescar-tasa"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: '7px',
          padding: '9px 13px', borderRadius: '10px', background: C.lienzo,
          border: `1px solid ${C.lineaFuerte}`, color: C.texto,
          fontSize: '13px', fontWeight: 600,
          cursor: refrescando ? 'default' : 'pointer', opacity: refrescando ? 0.6 : 1,
        }}>
        <RefreshCw size={14} /> {refrescando ? 'Actualizando…' : 'Actualizar'}
      </button>
    </div>
  );
}

function ResumenDelMonto({ ris, ves, onCambiar }) {
  return (
    <div style={{
      ...tarjeta, padding: '14px 16px', marginBottom: '16px', background: C.fondo,
      display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap',
    }}>
      <div style={{ flex: 1, minWidth: '210px', display: 'flex',
        alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
        <div>
          <p style={microEtiqueta}>Envías</p>
          <p style={{ margin: '2px 0 0 0', fontSize: '16px', fontWeight: 700, color: C.tinta }}>
            {fmt(ris)} <span style={{ fontSize: '12px', color: C.tenue }}>RIS</span>
          </p>
        </div>
        <ArrowRight size={16} color={C.tenue} />
        <div>
          <p style={microEtiqueta}>Recibe</p>
          <p style={{ margin: '2px 0 0 0', fontSize: '16px', fontWeight: 700, color: C.exito }}>
            {fmt(ves)} <span style={{ fontSize: '12px', color: C.tenue }}>VES</span>
          </p>
        </div>
      </div>
      <button type="button" onClick={onCambiar} className="env-chip"
        style={{
          padding: '8px 13px', borderRadius: '9px', background: C.lienzo,
          border: `1px solid ${C.lineaFuerte}`, color: C.texto,
          fontSize: '13px', fontWeight: 600, cursor: 'pointer',
        }}>
        Cambiar
      </button>
    </div>
  );
}

/* ─── La pantalla ──────────────────────────────────────────────────────── */

export default function Send() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const { rates, tasaDisponible, lastUpdated, refreshRates } = useRate();

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [refrescando, setRefrescando] = useState(false);
  const idemRef = useRef(null);

  const [beneficiaries, setBeneficiaries] = useState([]);
  const [showNewBeneficiary, setShowNewBeneficiary] = useState(false);

  // Se puede escribir en cualquiera de las dos monedas. `ultimoCampo` dice cuál
  // manda: el otro se muestra calculado y no pisa lo que la persona escribió.
  const [risEscrito, setRisEscrito] = useState('');
  const [vesEscrito, setVesEscrito] = useState('');
  const [ultimoCampo, setUltimoCampo] = useState('ris');

  const [paymentType, setPaymentType] = useState('');
  const [selectedBeneficiary, setSelectedBeneficiary] = useState(null);
  const [bankSearch, setBankSearch] = useState('');
  const [showBankDropdown, setShowBankDropdown] = useState(false);
  const [showPin, setShowPin] = useState(false);

  // La tasa con la que se cotizó, para avisar si se movió antes de confirmar.
  const [tasaAlCotizar, setTasaAlCotizar] = useState(null);

  // El reloj que hace avanzar el «hace N min» de la tasa. Medio minuto es
  // suficiente para un texto que se mide en minutos.
  const [ahora, setAhora] = useState(0);

  const [newBeneficiaryPM, setNewBeneficiaryPM] = useState({
    full_name: '', cedula: '', bank_code: '', bank: '', phone: '' });
  const [newBeneficiaryTR, setNewBeneficiaryTR] = useState({
    full_name: '', cedula: '', bank_code: '', bank: '', account_number: '' });

  const tasa = rates?.ris_to_ves;
  const saldo = user?.balance_ris || 0;
  const esPagoMovil = paymentType === 'pago_movil';

  const ris = useMemo(() => risAEnviar({
    risEscrito: ultimoCampo === 'ris' ? risEscrito : '',
    vesEscrito: ultimoCampo === 'ves' ? vesEscrito : '',
    tasa, tasaDisponible,
  }), [risEscrito, vesEscrito, ultimoCampo, tasa, tasaDisponible]);

  const ves = useMemo(() => vesARecibir({ ris, tasa, tasaDisponible }),
    [ris, tasa, tasaDisponible]);

  const escribioAlgo = Boolean(ultimoCampo === 'ris' ? risEscrito : vesEscrito);
  const validacion = validarMonto({ ris, saldo, tasaDisponible, escribioAlgo });

  const alcanzable = ultimoPasoAlcanzable({
    montoOk: validacion.ok, metodo: paymentType, beneficiario: selectedBeneficiary });

  const movimiento = step === 4
    ? tasaSeMovio({ tasaAlCotizar, tasaAhora: tasa }) : null;

  const cargarBeneficiarios = async () => {
    try {
      const r = await api.get('/beneficiaries');
      setBeneficiaries(r.data || []);
    } catch (e) {
      console.error('Error loading beneficiaries:', e);
    }
  };

  useEffect(() => {
    (async () => { await cargarBeneficiarios(); })();
  }, []);

  useEffect(() => {
    // El primer valor se pone en un microtask y no en el cuerpo del efecto:
    // así el setState no ocurre de forma sincrónica durante el montaje.
    const t = setInterval(() => setAhora(Date.now()), 30000);
    const inicial = setTimeout(() => setAhora(Date.now()), 0);
    return () => { clearInterval(t); clearTimeout(inicial); };
  }, []);

  // Al llegar a confirmar se vuelve a pedir la tasa: es el instante anterior a
  // que el dinero salga, el único momento en el que de verdad importa.
  useEffect(() => {
    if (step !== 4) return undefined;
    let vivo = true;
    (async () => {
      setRefrescando(true);
      try { await refreshRates(); } finally { if (vivo) setRefrescando(false); }
    })();
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const refrescarTasa = async () => {
    setRefrescando(true);
    try { await refreshRates(); } finally { setRefrescando(false); }
  };

  const filteredBanks = VENEZUELAN_BANKS.filter((b) =>
    b.code.includes(bankSearch) || b.name.toLowerCase().includes(bankSearch.toLowerCase()));

  const filteredBeneficiaries = beneficiaries.filter((b) => b.payment_type === paymentType);

  const onlyNumbers = (v) => v.replace(/[^0-9]/g, '');

  const handleSelectBank = (bank) => {
    if (esPagoMovil) {
      // Pago Móvil opera con el CODIGO: es lo que pide el banco al pagar. Se
      // guarda el código, y la pantalla muestra el nombre al lado para que
      // quien lo eligió reconozca el suyo.
      setNewBeneficiaryPM({ ...newBeneficiaryPM, bank_code: bank.code, bank: bank.code });
    } else {
      setNewBeneficiaryTR({ ...newBeneficiaryTR, bank_code: bank.code, bank: bank.name });
    }
    setBankSearch('');
    setShowBankDropdown(false);
  };

  const handleSaveBeneficiary = async () => {
    let datos;
    if (esPagoMovil) {
      const { full_name, cedula, bank, bank_code, phone } = newBeneficiaryPM;
      if (!full_name || !cedula || !bank || !phone) return toast.error('Completá todos los campos');
      if (!/^\d+$/.test(cedula)) return toast.error('La cédula lleva sólo números');
      if (!/^\d{11}$/.test(phone)) return toast.error('El teléfono tiene 11 dígitos (ej: 04141234567)');
      datos = { full_name, id_document: cedula, bank, bank_code,
        phone_number: phone, payment_type: 'pago_movil' };
    } else {
      const { full_name, cedula, bank, bank_code, account_number } = newBeneficiaryTR;
      if (!full_name || !cedula || !bank || !account_number) return toast.error('Completá todos los campos');
      if (!/^\d+$/.test(cedula)) return toast.error('La cédula lleva sólo números');
      if (!/^\d{20}$/.test(account_number)) return toast.error('El número de cuenta tiene 20 dígitos');
      datos = { full_name, id_document: cedula, bank, bank_code,
        account_number, payment_type: 'transferencia' };
    }

    setLoading(true);
    try {
      const r = await api.post('/beneficiaries', datos);
      toast.success('Beneficiario guardado');
      await cargarBeneficiarios();
      setSelectedBeneficiary(r.data);
      setShowNewBeneficiary(false);
      setNewBeneficiaryPM({ full_name: '', cedula: '', bank_code: '', bank: '', phone: '' });
      setNewBeneficiaryTR({ full_name: '', cedula: '', bank_code: '', bank: '', account_number: '' });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'No se pudo guardar el beneficiario');
    } finally {
      setLoading(false);
    }
    return undefined;
  };

  const pedirConfirmacion = () => {
    if (!validacion.ok || !selectedBeneficiary || !paymentType) {
      return toast.error('Revisá los datos del envío');
    }
    return setShowPin(true);
  };

  const handleSend = async () => {
    if (!validacion.ok || !selectedBeneficiary || !paymentType) {
      return toast.error('Revisá los datos del envío');
    }
    if (!idemRef.current) {
      idemRef.current = window.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }
    setLoading(true);
    try {
      await api.post('/withdraw', {
        amount: ris,
        beneficiary_id: selectedBeneficiary.beneficiary_id,
        idempotency_key: idemRef.current,
      });
      idemRef.current = null;
      toast.success('¡Envío registrado! Lo vas a ver en tu historial.');
      await refreshUser();
      try {
        const h = await api.post('/pin/hint-check');
        if (h.data?.hint) toast(h.data.message || 'Configurá tu PIN para más seguridad.', { icon: '🔒' });
      } catch { /* aviso opcional */ }
      navigate('/history');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'No se pudo procesar el envío');
    } finally {
      setLoading(false);
    }
    return undefined;
  };

  const irAPaso = (n) => { if (n <= alcanzable) setStep(n); };
  const seguirDesdeMonto = () => { setTasaAlCotizar(tasa); setStep(2); };

  const bancoElegido = esPagoMovil
    ? VENEZUELAN_BANKS.find((b) => b.code === newBeneficiaryPM.bank_code)
    : VENEZUELAN_BANKS.find((b) => b.code === newBeneficiaryTR.bank_code);

  const detalleDe = (b) => (esPagoMovil
    ? telefonoLegible(b?.phone_number) : cuentaAbreviada(b?.account_number));

  return (
    <div className="env" data-testid="send-page"
      style={{ minHeight: '100vh', background: C.fondo,
        fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' }}
      onClick={() => setShowBankDropdown(false)}>
      <style>{HOJA}</style>

      <div style={{ padding: '20px 16px 48px', maxWidth: '620px', margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
          <button
            type="button" onClick={() => (step > 1 ? setStep(step - 1) : navigate(-1))}
            aria-label="Volver" data-testid="back-button" className="env-tap"
            style={{
              width: '42px', height: '42px', borderRadius: '11px', flexShrink: 0,
              border: `1px solid ${C.linea}`, background: C.lienzo, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
            <ArrowLeft size={19} color={C.texto} />
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 style={{ fontSize: '21px', fontWeight: 700, color: C.tinta, margin: 0,
              letterSpacing: '-.01em' }}>Enviar a Venezuela</h1>
            <p style={{ fontSize: '13px', color: C.suave, margin: '2px 0 0 0' }}>
              Saldo disponible: <strong style={{ color: C.texto }}>{fmt(saldo)} RIS</strong>
            </p>
          </div>
          <NotificationBell />
        </div>

        <TiraDeTasa tasa={tasa} disponible={tasaDisponible} lastUpdated={lastUpdated}
          ahora={ahora} onRefrescar={refrescarTasa} refrescando={refrescando} />

        <Progreso pasos={PASOS} paso={step} alcanzable={alcanzable} irA={irAPaso} />

        {step > 1 && ris !== null ? (
          <ResumenDelMonto ris={ris} ves={ves} onCambiar={() => setStep(1)} />
        ) : null}

        {step === 1 ? (
          <div style={{ ...tarjeta, padding: '22px' }}>
            <h2 style={{ fontSize: '17px', fontWeight: 700, color: C.tinta, margin: '0 0 4px 0' }}>
              ¿Cuánto querés enviar?
            </h2>
            <p style={{ fontSize: '13.5px', color: C.suave, margin: '0 0 20px 0', lineHeight: 1.55 }}>
              Escribí el monto en la moneda que te resulte más cómoda. La otra se
              calcula sola.
            </p>

            {!tasaDisponible ? (
              <Aviso tono="alerta" titulo="No pudimos obtener la tasa" testid="sin-tasa">
                Sin la tasa del día no podemos decirte cuánto va a recibir tu
                beneficiario, y preferimos no mostrarte una cifra que después
                cambie. Tocá <strong>Actualizar</strong> acá arriba.
              </Aviso>
            ) : (
              <div>
                <div className="env-dos" style={{ display: 'grid', gap: '14px',
                  gridTemplateColumns: '1fr 1fr' }}>
                  <div>
                    <label style={etiqueta} htmlFor="monto-ris">Envías (RIS)</label>
                    <FormattedNumberInput
                      className="env-campo" id="monto-ris" decimals={2}
                      value={ultimoCampo === 'ris' ? risEscrito : (ris === null ? '' : String(ris))}
                      onChange={(v) => { setUltimoCampo('ris'); setRisEscrito(v); }}
                      style={{ ...campo, fontSize: '22px', fontWeight: 700 }}
                      placeholder="0,00" data-testid="send-amount"
                    />
                  </div>
                  <div>
                    <label style={etiqueta} htmlFor="monto-ves">Recibe (VES)</label>
                    <FormattedNumberInput
                      className="env-campo" id="monto-ves" decimals={2}
                      value={ultimoCampo === 'ves' ? vesEscrito : (ves === null ? '' : String(ves))}
                      onChange={(v) => { setUltimoCampo('ves'); setVesEscrito(v); }}
                      style={{ ...campo, fontSize: '22px', fontWeight: 700 }}
                      placeholder="0,00" data-testid="send-amount-ves"
                    />
                  </div>
                </div>

                {saldo > 0 ? (
                  <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
                    {[['25 %', 0.25], ['50 %', 0.5], ['Todo mi saldo', 1]].map(([txt, f]) => (
                      <button
                        key={txt} type="button" className="env-chip"
                        onClick={() => {
                          setUltimoCampo('ris');
                          setRisEscrito(String(Math.floor(saldo * f * 100) / 100));
                        }}
                        style={{
                          padding: '7px 13px', borderRadius: '999px', cursor: 'pointer',
                          border: `1px solid ${C.linea}`, background: C.lienzo,
                          color: C.texto, fontSize: '13px', fontWeight: 600,
                        }}>{txt}</button>
                    ))}
                  </div>
                ) : null}

                <div style={{
                  marginTop: '18px', padding: '18px', borderRadius: '14px',
                  background: C.exitoSuave, border: `1px solid ${C.exitoBorde}`,
                }}>
                  <p style={{ ...microEtiqueta, color: C.exito }}>Tu beneficiario recibe</p>
                  <p style={{ margin: '5px 0 0 0', fontSize: '30px', fontWeight: 700,
                    color: C.exito, lineHeight: 1.1 }}>
                    {ves === null ? '—' : fmt(ves)}
                    <span style={{ fontSize: '15px', fontWeight: 600, marginLeft: '7px' }}>VES</span>
                  </p>
                  {rates?.bcv_usd_ves && ves ? (
                    <p style={{ margin: '6px 0 0 0', fontSize: '12.5px', color: C.suave }}>
                      Referencia BCV: US$ {fmt(ves / rates.bcv_usd_ves, 2)}
                    </p>
                  ) : null}
                </div>

                {ultimoCampo === 'ves' && ris !== null && ves !== null ? (
                  <p style={{ margin: '10px 0 0 0', fontSize: '12.5px', color: C.suave,
                    lineHeight: 1.55 }}>
                    Para que lleguen esos bolívares se descuentan{' '}
                    <strong>{fmt(ris)} RIS</strong> de tu saldo. Los bolívares se
                    calculan sobre ese monto, así que lo que ves acá es
                    exactamente lo que va a recibir.
                  </p>
                ) : null}

                {!validacion.ok && validacion.motivo !== MOTIVO.VACIO ? (
                  <div style={{ marginTop: '14px' }}>
                    <Aviso testid="monto-invalido"
                      tono={validacion.motivo === MOTIVO.SIN_SALDO ? 'info' : 'error'}>
                      {MENSAJE_DEL_MOTIVO[validacion.motivo]}
                      {validacion.motivo === MOTIVO.SIN_SALDO
                        || validacion.motivo === MOTIVO.EXCEDE_SALDO ? (
                          <button type="button" onClick={() => navigate('/recharge')}
                            style={{ background: 'none', border: 'none', padding: '0 0 0 4px',
                              color: C.marca, fontWeight: 700, cursor: 'pointer',
                              fontSize: '13.5px', textDecoration: 'underline' }}>
                            Recargar saldo
                          </button>
                        ) : null}
                    </Aviso>
                  </div>
                ) : null}
              </div>
            )}

            <div style={{ marginTop: '20px' }}>
              <Boton tipo="primario" ancho disabled={!validacion.ok} onClick={seguirDesdeMonto}
                testid="continue-step1" Icono={ArrowRight} iconoDerecha>
                Continuar
              </Boton>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div style={{ ...tarjeta, padding: '22px' }}>
            <h2 style={{ fontSize: '17px', fontWeight: 700, color: C.tinta, margin: '0 0 4px 0' }}>
              ¿Cómo lo recibe?
            </h2>
            <p style={{ fontSize: '13.5px', color: C.suave, margin: '0 0 18px 0' }}>
              Elegí el método con el que tu beneficiario va a cobrar.
            </p>

            <div role="radiogroup" aria-label="Método de pago"
              style={{ display: 'grid', gap: '12px' }}>
              <Opcion
                elegida={esPagoMovil} onClick={() => setPaymentType('pago_movil')}
                Icono={Smartphone} titulo="Pago Móvil"
                detalle="Con cédula, código de banco y teléfono"
                testid="payment-type-pago-movil"
              />
              <Opcion
                elegida={paymentType === 'transferencia'}
                onClick={() => setPaymentType('transferencia')}
                Icono={Building2} titulo="Transferencia bancaria"
                detalle="A una cuenta de 20 dígitos"
                testid="payment-type-transferencia"
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
              <Boton onClick={() => setStep(1)} ancho>Atrás</Boton>
              <Boton tipo="primario" ancho disabled={!paymentType} testid="continue-step2"
                onClick={() => { setSelectedBeneficiary(null); setStep(3); }}
                Icono={ArrowRight} iconoDerecha>
                Continuar
              </Boton>
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div style={{ ...tarjeta, padding: '22px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px',
              flexWrap: 'wrap', marginBottom: '18px' }}>
              <div style={{ flex: 1, minWidth: '180px' }}>
                <h2 style={{ fontSize: '17px', fontWeight: 700, color: C.tinta, margin: 0 }}>
                  ¿A quién le enviás?
                </h2>
                <p style={{ fontSize: '13px', color: C.suave, margin: '3px 0 0 0' }}>
                  {esPagoMovil ? 'Pago Móvil' : 'Transferencia bancaria'}
                </p>
              </div>
              <button type="button" onClick={() => setShowNewBeneficiary(true)} className="env-chip"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '9px 13px', borderRadius: '10px', cursor: 'pointer',
                  border: `1px solid ${C.lineaFuerte}`, background: C.lienzo,
                  color: C.texto, fontSize: '13.5px', fontWeight: 600,
                }}>
                <Plus size={15} /> Nuevo
              </button>
            </div>

            {filteredBeneficiaries.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px 16px' }}>
                <div style={{
                  width: '58px', height: '58px', borderRadius: '50%', margin: '0 auto 14px',
                  background: C.fondo, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', border: `1px solid ${C.linea}`,
                }}>
                  <User size={26} color={C.tenue} />
                </div>
                <p style={{ color: C.tinta, margin: '0 0 4px 0', fontSize: '15px', fontWeight: 600 }}>
                  Todavía no tenés beneficiarios de {esPagoMovil ? 'Pago Móvil' : 'transferencia'}
                </p>
                <p style={{ color: C.suave, margin: '0 0 16px 0', fontSize: '13.5px' }}>
                  Cargá los datos una vez y quedan guardados para la próxima.
                </p>
                <Boton tipo="primario" Icono={Plus} onClick={() => setShowNewBeneficiary(true)}>
                  Agregar beneficiario
                </Boton>
              </div>
            ) : (
              <div role="radiogroup" aria-label="Beneficiario"
                style={{ display: 'grid', gap: '10px' }}>
                {filteredBeneficiaries.map((b) => {
                  const elegido = selectedBeneficiary?.beneficiary_id === b.beneficiary_id;
                  return (
                    <button
                      key={b.beneficiary_id} type="button" role="radio" aria-checked={elegido}
                      onClick={() => setSelectedBeneficiary(b)}
                      data-testid={`beneficiary-${b.beneficiary_id}`}
                      className="env-op env-tap"
                      style={{
                        display: 'flex', alignItems: 'center', gap: '13px', width: '100%',
                        padding: '14px', borderRadius: '14px', textAlign: 'left',
                        cursor: 'pointer',
                        border: `1px solid ${elegido ? C.marca : C.linea}`,
                        background: elegido ? C.marcaSuave : C.lienzo,
                      }}>
                      <span style={{
                        width: '42px', height: '42px', borderRadius: '50%', flexShrink: 0,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        background: elegido ? C.marca : C.fondo,
                        color: elegido ? '#fff' : C.suave, fontWeight: 700, fontSize: '14px',
                      }}>{iniciales(b.full_name)}</span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ display: 'block', fontSize: '15px', fontWeight: 700,
                          color: C.tinta, overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap' }}>{b.full_name}</span>
                        <span style={{ display: 'block', fontSize: '12.5px', color: C.suave,
                          marginTop: '2px' }}>{nombreDelBanco(b, VENEZUELAN_BANKS)}</span>
                        <span style={{ display: 'block', fontSize: '12.5px', color: C.suave }}>
                          {detalleDe(b)}
                        </span>
                      </span>
                      {elegido ? <CheckCircle2 size={21} color={C.marca} /> : null}
                    </button>
                  );
                })}
              </div>
            )}

            <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
              <Boton onClick={() => setStep(2)} ancho>Atrás</Boton>
              <Boton tipo="primario" ancho disabled={!selectedBeneficiary}
                onClick={() => setStep(4)} testid="continue-step3"
                Icono={ArrowRight} iconoDerecha>
                Continuar
              </Boton>
            </div>
          </div>
        ) : null}

        {step === 4 ? (
          <div style={{ ...tarjeta, padding: '22px' }}>
            <h2 style={{ fontSize: '17px', fontWeight: 700, color: C.tinta, margin: '0 0 4px 0' }}>
              Revisá antes de enviar
            </h2>
            <p style={{ fontSize: '13.5px', color: C.suave, margin: '0 0 18px 0', lineHeight: 1.55 }}>
              Comprobá el nombre y los datos del beneficiario. Una vez enviado no
              se puede cambiar el destino.
            </p>

            {movimiento ? (
              <div style={{ marginBottom: '16px' }}>
                <Aviso tono="alerta" titulo="La tasa cambió mientras completabas"
                  testid="tasa-cambio">
                  Cotizaste con <strong>{fmt(movimiento.antes)}</strong> y ahora
                  está en <strong>{fmt(movimiento.ahora)}</strong>.
                  {movimiento.mejora
                    ? ' Tu beneficiario recibe un poco más de lo que viste.'
                    : ' Tu beneficiario recibe un poco menos de lo que viste.'}
                  {' '}El monto de abajo ya está actualizado.
                </Aviso>
              </div>
            ) : null}

            <div style={{
              padding: '20px', borderRadius: '14px', background: C.fondo,
              border: `1px solid ${C.linea}`, marginBottom: '14px',
            }}>
              <div className="env-dos" style={{ display: 'grid', gap: '16px',
                gridTemplateColumns: '1fr 1fr' }}>
                <div>
                  <p style={microEtiqueta}>Se descuenta de tu saldo</p>
                  <p style={{ margin: '5px 0 0 0', fontSize: '24px', fontWeight: 700,
                    color: C.tinta }}>
                    {fmt(ris)} <span style={{ fontSize: '13px', color: C.tenue }}>RIS</span>
                  </p>
                </div>
                <div>
                  <p style={{ ...microEtiqueta, color: C.exito }}>Recibe</p>
                  <p style={{ margin: '5px 0 0 0', fontSize: '24px', fontWeight: 700,
                    color: C.exito }}>
                    {fmt(ves)} <span style={{ fontSize: '13px', color: C.tenue }}>VES</span>
                  </p>
                </div>
              </div>
              <p style={{ margin: '14px 0 0 0', paddingTop: '13px',
                borderTop: `1px solid ${C.linea}`, fontSize: '12.5px', color: C.suave }}>
                Tasa aplicada: 1 RIS = {fmt(tasa)} VES
              </p>
            </div>

            <div style={{
              padding: '18px', borderRadius: '14px', border: `1px solid ${C.linea}`,
              marginBottom: '18px',
            }}>
              <p style={{ ...microEtiqueta, marginBottom: '12px' }}>Beneficiario</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '13px',
                marginBottom: '14px' }}>
                <span style={{
                  width: '44px', height: '44px', borderRadius: '50%', flexShrink: 0,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  background: C.marcaSuave, color: C.marca, fontWeight: 700, fontSize: '15px',
                }}>{iniciales(selectedBeneficiary?.full_name)}</span>
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: C.tinta }}>
                    {selectedBeneficiary?.full_name}
                  </p>
                  <p style={{ margin: '2px 0 0 0', fontSize: '13px', color: C.suave }}>
                    {esPagoMovil ? 'Pago Móvil' : 'Transferencia bancaria'}
                  </p>
                </div>
              </div>

              <dl style={{ margin: 0, display: 'grid', gap: '9px' }}>
                {[
                  ['Banco', nombreDelBanco(selectedBeneficiary, VENEZUELAN_BANKS)],
                  ['Cédula', selectedBeneficiary?.id_document || '—'],
                  esPagoMovil
                    ? ['Teléfono', telefonoLegible(selectedBeneficiary?.phone_number)]
                    // La cuenta va COMPLETA acá y abreviada en la lista: éste es
                    // el momento de comprobarla dígito por dígito.
                    : ['Cuenta', selectedBeneficiary?.account_number || '—'],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', gap: '12px',
                    justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <dt style={{ fontSize: '13px', color: C.suave, flexShrink: 0 }}>{k}</dt>
                    <dd style={{ margin: 0, fontSize: '13.5px', fontWeight: 600,
                      color: C.tinta, textAlign: 'right', wordBreak: 'break-all' }}>{v}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div style={{ marginBottom: '18px' }}>
              <Aviso>
                El envío queda registrado al confirmar y se procesa en breve. Vas
                a poder seguirlo desde tu historial.
              </Aviso>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <Boton onClick={() => setStep(3)}>Atrás</Boton>
              <Boton tipo="exito" ancho onClick={pedirConfirmacion}
                disabled={loading || !validacion.ok} testid="confirm-send" Icono={ShieldCheck}>
                {loading ? 'Procesando…' : 'Confirmar envío'}
              </Boton>
            </div>

            <PinConfirm open={showPin} onClose={() => setShowPin(false)} onVerified={handleSend} />
          </div>
        ) : null}

        {showNewBeneficiary ? (
          <div
            style={{
              position: 'fixed', inset: 0, background: 'rgba(16,24,40,.55)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '16px', zIndex: 50,
            }}
            onClick={(e) => { if (e.target === e.currentTarget) setShowNewBeneficiary(false); }}>
            <div
              role="dialog" aria-modal="true" aria-label="Nuevo beneficiario"
              style={{
                background: C.lienzo, borderRadius: '18px', padding: '22px',
                width: '100%', maxWidth: '460px', maxHeight: '90vh', overflowY: 'auto',
              }}
              onClick={(e) => { e.stopPropagation(); setShowBankDropdown(false); }}>

              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px',
                marginBottom: '20px' }}>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 700, color: C.tinta, margin: 0 }}>
                    Nuevo beneficiario
                  </h3>
                  <p style={{ fontSize: '13px', color: C.suave, margin: '3px 0 0 0' }}>
                    {esPagoMovil ? 'Pago Móvil' : 'Transferencia bancaria'}
                  </p>
                </div>
                <button type="button" onClick={() => setShowNewBeneficiary(false)}
                  aria-label="Cerrar" className="env-tap"
                  style={{
                    width: '36px', height: '36px', borderRadius: '10px', flexShrink: 0,
                    background: C.lienzo, border: `1px solid ${C.linea}`, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                  <X size={18} color={C.suave} />
                </button>
              </div>

              <div style={{ display: 'grid', gap: '15px' }}>
                <div>
                  <label style={etiqueta} htmlFor="ben-nombre">Nombre completo</label>
                  <input
                    className="env-campo" id="ben-nombre" type="text" style={campo}
                    placeholder="Como figura en su cédula"
                    value={esPagoMovil ? newBeneficiaryPM.full_name : newBeneficiaryTR.full_name}
                    onChange={(e) => (esPagoMovil
                      ? setNewBeneficiaryPM({ ...newBeneficiaryPM, full_name: e.target.value })
                      : setNewBeneficiaryTR({ ...newBeneficiaryTR, full_name: e.target.value }))}
                    data-testid={esPagoMovil ? 'pm-fullname' : 'tr-fullname'}
                  />
                </div>

                <div>
                  <label style={etiqueta} htmlFor="ben-cedula">Cédula</label>
                  <input
                    className="env-campo" id="ben-cedula" type="text" inputMode="numeric"
                    style={campo} placeholder="12345678"
                    value={esPagoMovil ? newBeneficiaryPM.cedula : newBeneficiaryTR.cedula}
                    onChange={(e) => {
                      const v = onlyNumbers(e.target.value);
                      return esPagoMovil
                        ? setNewBeneficiaryPM({ ...newBeneficiaryPM, cedula: v })
                        : setNewBeneficiaryTR({ ...newBeneficiaryTR, cedula: v });
                    }}
                    data-testid={esPagoMovil ? 'pm-cedula' : 'tr-cedula'}
                  />
                  <p style={ayuda}>Sólo los números, sin la V ni puntos.</p>
                </div>

                <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
                  <label style={etiqueta} htmlFor="banco-buscar">Banco</label>

                  {/* Lo elegido se muestra COMO DATO, no dentro del buscador.
                      Antes el input mostraba el banco elegido y al enfocarlo se
                      vaciaba: parecía que se había perdido la elección. */}
                  {bancoElegido ? (
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: '9px', marginBottom: '8px',
                      padding: '10px 12px', borderRadius: '10px',
                      background: C.marcaSuave, border: `1px solid ${C.marcaBorde}`,
                    }}>
                      <Building2 size={16} color={C.marca} />
                      <span style={{ flex: 1, fontSize: '14px', fontWeight: 600, color: C.tinta }}>
                        {bancoElegido.name}
                      </span>
                      <span style={{ fontFamily: 'ui-monospace, monospace', fontSize: '12.5px',
                        fontWeight: 700, color: C.marca }}>{bancoElegido.code}</span>
                    </div>
                  ) : null}

                  <div style={{ position: 'relative' }}>
                    <Search size={17} color={C.tenue} style={{
                      position: 'absolute', left: '14px', top: '50%',
                      transform: 'translateY(-50%)', pointerEvents: 'none', zIndex: 1 }} />
                    <input
                      className="env-campo" id="banco-buscar" type="text" value={bankSearch}
                      onChange={(e) => { setBankSearch(e.target.value); setShowBankDropdown(true); }}
                      onFocus={() => setShowBankDropdown(true)}
                      placeholder={bancoElegido ? 'Buscar otro banco…' : 'Buscá por nombre o código…'}
                      style={{ ...campo, paddingLeft: '42px' }}
                      data-testid="bank-search-input"
                    />
                  </div>

                  {showBankDropdown ? (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 60,
                      background: C.lienzo, borderRadius: '12px', marginTop: '6px',
                      boxShadow: '0 12px 32px rgba(16,24,40,.14)', maxHeight: '240px',
                      overflowY: 'auto', border: `1px solid ${C.linea}`,
                    }}>
                      {filteredBanks.length === 0 ? (
                        <p style={{ padding: '16px', textAlign: 'center', color: C.suave,
                          fontSize: '13.5px', margin: 0 }}>No encontramos ese banco.</p>
                      ) : filteredBanks.map((bank) => (
                        <button
                          key={bank.code} type="button" onClick={() => handleSelectBank(bank)}
                          data-testid={`bank-option-${bank.code}`}
                          style={{
                            width: '100%', padding: '11px 14px', border: 'none',
                            background: 'transparent', textAlign: 'left', cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: '11px',
                            borderBottom: `1px solid ${C.fondo}`,
                          }}>
                          <span style={{
                            fontSize: '12px', fontWeight: 700, color: C.marca,
                            background: C.marcaSuave, padding: '4px 7px', borderRadius: '6px',
                            fontFamily: 'ui-monospace, monospace', flexShrink: 0,
                          }}>{bank.code}</span>
                          <span style={{ fontSize: '14px', color: C.texto }}>{bank.name}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>

                {esPagoMovil ? (
                  <div>
                    <label style={etiqueta} htmlFor="ben-telefono">Teléfono</label>
                    <input
                      className="env-campo" id="ben-telefono" type="text" inputMode="numeric"
                      maxLength={11} style={campo} placeholder="04141234567"
                      value={newBeneficiaryPM.phone}
                      onChange={(e) => setNewBeneficiaryPM({
                        ...newBeneficiaryPM, phone: onlyNumbers(e.target.value).slice(0, 11) })}
                      data-testid="pm-phone"
                    />
                    <p style={ayuda}>11 dígitos, empezando por 04. Ejemplo: 04141234567.</p>
                  </div>
                ) : (
                  <div>
                    <label style={etiqueta} htmlFor="ben-cuenta">Número de cuenta</label>
                    <input
                      className="env-campo" id="ben-cuenta" type="text" inputMode="numeric"
                      maxLength={20} placeholder="01340123456789012345"
                      style={{ ...campo, fontFamily: 'ui-monospace, monospace' }}
                      value={newBeneficiaryTR.account_number}
                      onChange={(e) => setNewBeneficiaryTR({
                        ...newBeneficiaryTR,
                        account_number: onlyNumbers(e.target.value).slice(0, 20) })}
                      data-testid="tr-account"
                    />
                    <p style={ayuda}>
                      20 dígitos, sin espacios ni guiones.
                      {newBeneficiaryTR.account_number.length > 0
                        ? ` Llevás ${newBeneficiaryTR.account_number.length} de 20.` : ''}
                    </p>
                  </div>
                )}

                <Boton tipo="primario" ancho onClick={handleSaveBeneficiary} disabled={loading}
                  testid={esPagoMovil ? 'save-beneficiary-pm' : 'save-beneficiary-tr'}>
                  {loading ? 'Guardando…' : 'Guardar beneficiario'}
                </Boton>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
