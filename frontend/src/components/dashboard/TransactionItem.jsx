import { ArrowUpRight, ArrowDownLeft, Clock, CheckCircle2, XCircle, Eye, Building2, AlertCircle, Hourglass, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { fmt, formatAccountNumber } from '../../utils/format';

/**
 * Status pill (Pendiente / Aprobado / Rechazado / En revisión)
 */
const STATUS_CONFIG = {
  completed:                { label: 'Aprobado',  bg: 'var(--en-oscuro-exito-suave, #ECFDF5)', fg: 'var(--en-oscuro-exito, #10B981)', Icon: CheckCircle2 },
  approved:                 { label: 'Aprobado',  bg: 'var(--en-oscuro-exito-suave, #ECFDF5)', fg: 'var(--en-oscuro-exito, #10B981)', Icon: CheckCircle2 },
  verified:                 { label: 'Aprobado',  bg: 'var(--en-oscuro-exito-suave, #ECFDF5)', fg: 'var(--en-oscuro-exito, #10B981)', Icon: CheckCircle2 },
  pending:                  { label: 'Pendiente', bg: 'var(--en-oscuro-alerta-suave, #FFF8E1)', fg: 'var(--en-oscuro-alerta, #F59E0B)', Icon: Clock },
  pending_manual_approval:  { label: 'En revisión', bg: 'var(--en-oscuro-alerta-suave, #FFF8E1)', fg: 'var(--en-oscuro-alerta, #F59E0B)', Icon: Clock },
  rejected:                 { label: 'Rechazado', bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
  failed:                   { label: 'Fallida',   bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
  // Envios cripto pagados via NOWPayments: ciclo de vida del pago
  awaiting_payment:         { label: 'Esperando pago',    bg: 'var(--en-oscuro-acento-suave, #EFF6FF)', fg: 'var(--en-oscuro-info, #2563EB)', Icon: Hourglass },
  // ESTOS TRES FALTABAN, Y NO ERA UN DETALLE.
  //
  //   `StatusBadge` cae a «Pendiente» cuando no encuentra el estado. Así que
  //   un pedido vencido, uno esperando que alguien mire el comprobante y uno
  //   con un pago que entró fuera de tiempo se veían los tres igual: como si
  //   estuvieran en camino.
  //
  //   Al primero le decía que espere algo que ya no va a pasar. Al tercero,
  //   que estaba todo bien cuando hay plata suya esperando una decisión.
  payment_expired:          { label: 'Expirado',           bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
  awaiting_review:          { label: 'Revisando tu pago',  bg: 'var(--en-oscuro-alerta-suave, #FFF8E1)', fg: 'var(--en-oscuro-alerta, #F59E0B)', Icon: Clock },
  payment_late:             { label: 'Pago a revisar',     bg: 'var(--en-oscuro-alerta-suave, #FFF7ED)', fg: 'var(--en-oscuro-alerta, #C2410C)', Icon: AlertCircle },
  awaiting_topup:           { label: 'Falta completar',   bg: 'var(--en-oscuro-alerta-suave, #FFF7ED)', fg: 'var(--en-oscuro-alerta, #C2410C)', Icon: AlertCircle },
  underpaid_review:         { label: 'En revisión',       bg: 'var(--en-oscuro-alerta-suave, #FFF8E1)', fg: 'var(--en-oscuro-alerta, #F59E0B)', Icon: Clock },
  payment_failed:           { label: 'Pago no completado', bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
  payment_error:            { label: 'Error de pago',     bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
  // Estados en español (transacciones BTC y otras que guardan 'estado' en español)
  procesando:               { label: 'Procesando', bg: 'var(--en-oscuro-alerta-suave, #FFF8E1)', fg: 'var(--en-oscuro-alerta, #F59E0B)', Icon: Clock },
  pendiente:                { label: 'Pendiente',  bg: 'var(--en-oscuro-alerta-suave, #FFF8E1)', fg: 'var(--en-oscuro-alerta, #F59E0B)', Icon: Clock },
  completado:               { label: 'Enviado',    bg: 'var(--en-oscuro-exito-suave, #ECFDF5)', fg: 'var(--en-oscuro-exito, #10B981)', Icon: CheckCircle2 },
  enviado:                  { label: 'Enviado',    bg: 'var(--en-oscuro-exito-suave, #ECFDF5)', fg: 'var(--en-oscuro-exito, #10B981)', Icon: CheckCircle2 },
  cancelado:                { label: 'Cancelado',  bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
  expirado:                 { label: 'Expirado',   bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
  fallido:                  { label: 'Fallida',    bg: 'var(--en-oscuro-error-suave, #FEF2F2)', fg: 'var(--en-oscuro-error, #EF4444)', Icon: XCircle },
};

export function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const { Icon } = cfg;
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '5px',
        padding: '4px 10px', borderRadius: '20px',
        backgroundColor: cfg.bg, color: cfg.fg,
        fontSize: '12px', fontWeight: 600,
        lineHeight: 1,
      }}
    >
      <Icon size={12} strokeWidth={2.5} />
      {cfg.label}
    </span>
  );
}

// EN LA LISTA, EL ESTADO QUE SALIO BIEN NO SE PINTA.
//
//   El historial llevaba cuatro manchas de color por fila: la flecha, el
//   monto, la pastilla del estado y la del comprobante. Como casi todo está
//   «Aprobado», la lista era verde y roja de punta a punta —«un arbolito de
//   navidad», dijo el dueño— y lo único que importaba, el pedido vencido o el
//   que espera una revisión, no se distinguía del resto.
//
//   Ahora lo que terminó bien va en gris con un punto de color, y en color
//   entero sólo lo que pide que alguien mire. El panel de administración
//   sigue con `StatusBadge`: ahí se recorre la lista buscando por estado y la
//   pastilla sirve.
const TERMINADOS_BIEN = new Set(['completed', 'approved', 'verified', 'completado', 'enviado']);

function EstadoEnTexto({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const bien = TERMINADOS_BIEN.has(status);
  return (
    <span
      data-testid="estado-en-texto"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '6px',
        fontSize: '12.5px', fontWeight: 600, lineHeight: 1,
        color: bien ? 'var(--en-oscuro-texto-2, #8E8E9A)' : cfg.fg,
      }}
    >
      <span aria-hidden="true" style={{
        width: '7px', height: '7px', borderRadius: '50%', flexShrink: 0, backgroundColor: cfg.fg,
      }} />
      {cfg.label}
    </span>
  );
}

// «Ver comprobante» y «Ver por qué» son enlaces, no pastillas: una segunda
// pastilla de color al lado del estado competía con él.
const ENLACE_DE_FILA = {
  display: 'inline-flex', alignItems: 'center', gap: '2px',
  padding: '2px 0', background: 'none', border: 'none', cursor: 'pointer',
  fontSize: '12.5px', fontWeight: 600, textDecoration: 'none', lineHeight: 1,
  color: 'var(--en-oscuro-acento, #5B4FE9)', fontFamily: 'inherit',
};

function formatShort(dateString) {
  if (!dateString) return '';
  const d = new Date(dateString);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/**
 * Single transaction card.
 *
 * Props:
 *   tx: transaction object
 *   rates: { bcv_usd_ves } (optional, for $ conversion)
 *   onViewVoucher: (tx) => void
 */
export default function TransactionItem({ tx, rates, onViewVoucher, compact = false }) {
  // Normalizar nombres de campo: unas transacciones usan inglés
  // (type/status/amount_input) y otras español (tipo/estado/amount), p.ej. las de BTC.
  const txType = String(tx.type || tx.tipo || '').toLowerCase();
  const txStatus = tx.status || tx.estado || 'pending';
  const isBtc = txType.includes('btc') || tx.subtipo === 'btc_lightning';
  const isWithdrawal = ['withdrawal', 'send', 'envio', 'envío'].includes(txType) || isBtc;
  const isRecharge = txType.startsWith('recharge') || txType.startsWith('recarga');
  const sign = isWithdrawal ? '-' : '+';
  // MANDAR PLATA NO ES UN ERROR.
  //
  //   Cada envío salía en rojo —el monto y el círculo de la flecha—, y el
  //   rojo se lee como «algo salió mal». Lo que sale va en el color del
  //   texto, con su signo menos; en verde, sólo la plata que entra. La
  //   flecha ya dice hacia dónde va: no necesita además un color.
  const amountColor = isWithdrawal ? 'var(--en-oscuro-texto, #1A1A2E)' : 'var(--en-oscuro-exito, #38A169)';
  const iconBg = 'var(--en-oscuro-superficie-3, #F2F2F7)';
  const iconColor = 'var(--en-oscuro-texto-2, #8E8E9A)';
  const IconArrow = isWithdrawal ? ArrowUpRight : ArrowDownLeft;

  const beneficiary = tx.beneficiary_data || {};
  const account = beneficiary.account_number || beneficiary.phone || '';
  // El ojito aparece en CUALQUIER transacción con un comprobante cargado
  // (el admin lo sube en los envíos; el usuario en las recargas), sin importar el tipo ni el estado.
  //
  // La lista ya no trae las fotos —eran 10 MB por cada vez que se abría el
  // inicio—, sólo si las hay. Las fotos se piden al tocar el ojito: ver
  // `hooks/useComprobante.js`.
  const showVoucher = tx.tiene_comprobante;

  // RETOMAR UN PEDIDO QUE QUEDO A MEDIAS.
  //
  //   El cliente cotizó, vio el QR y cerró la pantalla. Hasta ahora eso era
  //   el final: lo que hacía falta para pagarlo venía en la respuesta de la
  //   cotización y no había cómo volver a pedirlo.
  //
  //   Se muestra también cuando ya venció, y a propósito: es la única forma
  //   de que el cliente sepa POR QUE su pedido no avanza. El servidor decide
  //   qué texto le corresponde según el corredor.
  const sePuedeRetomar = ['awaiting_payment', 'payment_expired']
    .includes(txStatus);

  // LA MONEDA DE LO QUE RECIBE EL BENEFICIARIO SE LEE, NO SE ESCRIBE A MANO
  //
  //   Acá decía «VES» fijo. Cuando se escribió, todos los envíos iban a
  //   Venezuela; después llegó el corredor a Brasil y nadie volvió a esta
  //   línea, así que una orden de 4.400 bolívares a Brasil mostraba «40,00
  //   VES» donde eran 40 reales. El respaldo en «VES» es para las órdenes
  //   viejas que no tengan guardada la moneda de salida.
  const monedaSalida = tx.currency_output || 'VES';

  // Monto principal y unidad según el flujo (busca el primer campo con valor)
  let mainAmount, mainUnit;
  if (isBtc) {
    mainAmount = Math.abs(Number(tx.amount_ves ?? tx.amount_output ?? 0));
    mainUnit = 'VES';
  } else {
    mainAmount = Math.abs(Number(tx.amount_input ?? tx.amount_ris ?? tx.amount ?? tx.amount_output ?? 0));
    mainUnit = (isWithdrawal && tx.currency_input) ? tx.currency_input : 'RIS';
  }

  // Etiqueta: "Recarga" SOLO para entradas (PIX / bolívares); el resto es envío
  const title = isBtc
    ? (beneficiary.full_name ? `Envío BTC · ${beneficiary.full_name}` : 'Envío BTC')
    : isWithdrawal
      ? (beneficiary.full_name || tx.beneficiario || 'Envío')
      : isRecharge
        ? 'Recarga'
        : (sign === '+' ? 'Recarga' : 'Envío');

  // EL NÚMERO DE LA ORDEN, A LA VISTA
  //
  //   El historial mostraba nombre, fecha y monto, y nada que NOMBRARA la
  //   operación. Cuando alguien escribía «pagué y no me aparece», ni el
  //   cliente ni quien lo atendía tenían un número que decirse: había que
  //   adivinar cuál de los envíos del día era, por el monto y la hora.
  //
  //   `display_id` es el número corto y correlativo que el backend ya venía
  //   guardando y mandando —está en `LO_QUE_VE_EL_CLIENTE`—; lo único que
  //   faltaba era pintarlo.
  //
  //   El respaldo corta el identificador largo por el FINAL y no por el
  //   principio: el principio es el prefijo del tipo (`tx_`, `rech_`) y sale
  //   igual en todas las órdenes, que es justo lo contrario de un
  //   identificador.
  //
  //   El respaldo NO mira el campo con que los envíos por Bitcoin guardan su
  //   identificador largo: ese nombre no está en `LO_QUE_VE_EL_CLIENTE`, así
  //   que al navegador no llega nunca. Leerlo acá sólo serviría para que
  //   `tests/test_el_historial_no_lleva_el_panel.py` falle —y falló—.
  const numero = tx.display_id
    || (String(tx.transaction_id || '').slice(-8).toUpperCase() || null);

  if (compact) {
    const statusCfg = STATUS_CONFIG[txStatus] || STATUS_CONFIG.pending;
    return (
      <div
        data-testid={`recent-tx-${tx.transaction_id}`}
        style={{
          backgroundColor: 'var(--en-oscuro-superficie, #ffffff)',
          borderRadius: '12px',
          padding: '10px 12px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          transition: 'background-color 0.15s',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--en-oscuro-superficie-2, #F8F8FF)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'var(--en-oscuro-superficie, #ffffff)'; }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '34px', height: '34px', borderRadius: '50%',
            backgroundColor: iconBg, color: iconColor,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <IconArrow size={16} strokeWidth={2.5} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
              <span style={{
                fontSize: '13.5px', fontWeight: 700, color: 'var(--en-oscuro-texto, #1A1A2E)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {title}
              </span>
              <span style={{
                fontSize: '14px', fontWeight: 700, color: amountColor,
                fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', flexShrink: 0,
              }}>
                {sign}{fmt(mainAmount)} {mainUnit}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginTop: '2px' }}>
              <span style={{ fontSize: '11px', color: 'var(--en-oscuro-texto-2, #8E8E9A)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {formatShort(tx.created_at)} · <span style={{ color: TERMINADOS_BIEN.has(txStatus) ? 'var(--en-oscuro-texto-2, #8E8E9A)' : statusCfg.fg, fontWeight: 600 }}>{statusCfg.label}</span>
                {numero && <> · <span data-testid={`numero-tx-${tx.transaction_id}`} style={{ userSelect: 'text' }}>#{numero}</span></>}
              </span>
              {showVoucher && (
                <button
                  onClick={() => onViewVoucher?.(tx)}
                  data-testid={`view-voucher-${tx.transaction_id}`}
                  style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: '22px', height: '22px', borderRadius: '50%',
                    backgroundColor: 'var(--en-oscuro-acento-suave, #EEF2FF)', color: 'var(--en-oscuro-acento, #5B4FE9)', border: 'none', cursor: 'pointer',
                    flexShrink: 0,
                  }}
                  title="Ver comprobante"
                >
                  <Eye size={12} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid={`recent-tx-${tx.transaction_id}`}
      style={{
        backgroundColor: 'var(--en-oscuro-superficie, #ffffff)',
        borderRadius: '12px',
        padding: '12px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        transition: 'background-color 0.2s, transform 0.05s',
        cursor: showVoucher ? 'default' : 'default',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--en-oscuro-superficie-2, #F8F8FF)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'var(--en-oscuro-superficie, #ffffff)'; }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
        {/* Category icon */}
        <div style={{
          width: '36px', height: '36px', borderRadius: '50%',
          backgroundColor: iconBg, color: iconColor,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <IconArrow size={17} strokeWidth={2.5} />
        </div>

        {/* Body */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Row 1: Name / Date — Amount / sub-amount */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{
                fontSize: '14px', fontWeight: 700, color: 'var(--en-oscuro-texto, #1A1A2E)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {title}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--en-oscuro-texto-2, #8E8E9A)', marginTop: '1px' }}>
                {formatShort(tx.created_at)}
                {numero && (
                  <> · <span
                    data-testid={`numero-tx-${tx.transaction_id}`}
                    style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', userSelect: 'text' }}
                  >#{numero}</span></>
                )}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{
                fontSize: '15px', fontWeight: 700, color: amountColor,
                fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
              }}>
                {sign}{fmt(mainAmount)} {mainUnit}
              </div>
              {isWithdrawal && !isBtc && tx.amount_output && (
                <div style={{ fontSize: '10.5px', color: 'var(--en-oscuro-texto-2, #8E8E9A)', marginTop: '1px', whiteSpace: 'nowrap' }}>
                  {fmt(tx.amount_output)} {monedaSalida}
                  {/* La equivalencia en dólares BCV sólo tiene sentido sobre
                      bolívares: dividir reales por la tasa del BCV da un
                      número que no es nada. */}
                  {monedaSalida === 'VES' && rates?.bcv_usd_ves > 0 && (
                    <> = ${fmt(tx.amount_output / rates.bcv_usd_ves, 2)} BCV</>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Beneficiary block for withdrawals */}
          {isWithdrawal && (beneficiary.bank || account) && (
            <div style={{
              marginTop: '8px', padding: '8px 10px',
              backgroundColor: 'var(--en-oscuro-superficie-2, #FAFAFC)', borderRadius: '9px',
              border: '1px solid var(--en-oscuro-linea, #EFEFF5)',
              display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap',
            }}>
              {beneficiary.bank && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '11.5px', color: 'var(--en-oscuro-texto-2, #8E8E9A)' }}>
                  <Building2 size={12} />
                  <span style={{ color: 'var(--en-oscuro-texto, #374151)', fontWeight: 500 }}>{beneficiary.bank}</span>
                </span>
              )}
              {account && (
                <span style={{
                  fontSize: '11.5px', color: 'var(--en-oscuro-texto, #374151)', fontVariantNumeric: 'tabular-nums',
                  letterSpacing: '0.04em', fontWeight: 500,
                }}>
                  {formatAccountNumber(account) || account}
                </span>
              )}
            </div>
          )}

          {/* Abajo: el estado a la izquierda y lo que se puede hacer, a la derecha. */}
          <div style={{ marginTop: '9px', display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
            <EstadoEnTexto status={txStatus} />
            {(sePuedeRetomar || showVoucher) && (
              <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: '14px' }}>
                {sePuedeRetomar && (
                  <Link
                    to={`/envios/${tx.transaction_id}/pagar`}
                    data-testid={`retomar-${tx.transaction_id}`}
                    style={ENLACE_DE_FILA}
                  >
                    {txStatus === 'payment_expired' ? 'Ver por qué' : 'Ver cómo pagar'}
                    <ChevronRight size={14} />
                  </Link>
                )}
                {showVoucher && (
                  <button
                    type="button"
                    onClick={() => onViewVoucher?.(tx)}
                    data-testid={`view-voucher-${tx.transaction_id}`}
                    style={ENLACE_DE_FILA}
                  >
                    Ver comprobante
                    <ChevronRight size={14} />
                  </button>
                )}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
