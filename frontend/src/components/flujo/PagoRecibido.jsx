/**
 * PagoRecibido — la pantalla verde de «tu pago entró».
 *
 * LA MISMA EN LAS DOS PANTALLAS QUE MUESTRAN UN QR DE ENVIO
 *
 *   `Send.jsx` (paso del QR) y `RetomarPago.jsx` (un pedido retomado desde
 *   el historial). Es el mismo momento visto desde dos lugares, así que es la
 *   misma pantalla: un cliente que pague desde una y otra vez desde la otra
 *   tiene que ver lo mismo.
 *
 * QUE DICE, Y POR QUE EN ESE ORDEN
 *
 *   1. Que el pago entró — es lo único que vino a saber.
 *   2. Qué pedido es, con su número: es lo que va a decir si escribe a
 *      soporte.
 *   3. Cuánto pagó y cuánto recibe quién: para que confirme con los ojos que
 *      es el pedido que quiso hacer.
 *   4. Qué pasa ahora. «Ya está en camino» sin decir qué sigue deja a la
 *      persona mirando la pantalla esperando otra cosa.
 *
 * NO TIENE BOTON DE «CERRAR»: lo que hay que hacer después está en los dos
 * botones, y volver atrás no tiene sentido — el pedido ya se pagó.
 */
import { CheckCircle2 } from 'lucide-react';
import { Boton } from './index.jsx';
import { C, tarjeta } from './estilos';
import { fmt } from '../../utils/format';

export default function PagoRecibido({
  numero, pagaste, recibe, monedaRecibe = 'VES', beneficiario,
  onHistorial, onOtroEnvio, testid = 'pago-recibido',
}) {
  const filas = [
    ['Pagaste', `R$ ${fmt(pagaste)}`],
    ['Recibe', `${fmt(recibe)} ${monedaRecibe}`],
    ...(beneficiario ? [['Para', beneficiario]] : []),
  ];

  return (
    <section style={{ ...tarjeta, padding: '26px 22px', textAlign: 'center' }}
      data-testid={testid} role="status" aria-live="polite">
      <div style={{
        width: '76px', height: '76px', borderRadius: '50%', margin: '0 auto 16px',
        background: C.exitoSuave, border: `1px solid ${C.exitoBorde}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <CheckCircle2 size={40} color={C.exito} strokeWidth={2.2} />
      </div>

      <h2 style={{ fontSize: '22px', fontWeight: 800, color: C.exito, margin: '0 0 6px 0',
        letterSpacing: '-0.01em' }}>
        ¡Pago recibido!
      </h2>
      <p style={{ fontSize: '14.5px', color: C.texto, margin: '0 0 20px 0', lineHeight: 1.55 }}>
        Tu pedido{numero ? <> <strong style={{ color: C.tinta }}>Nº {numero}</strong></> : null} ya
        está en camino.
      </p>

      <dl style={{
        margin: '0 0 18px 0', padding: '14px 16px', display: 'grid', gap: '9px',
        background: C.fondo, borderRadius: '12px', textAlign: 'left',
      }} data-testid={`${testid}-detalle`}>
        {filas.map(([k, v]) => (
          <div key={k} style={{ display: 'flex', gap: '12px',
            justifyContent: 'space-between', alignItems: 'baseline' }}>
            <dt style={{ fontSize: '13px', color: C.suave }}>{k}</dt>
            <dd style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: C.tinta,
              fontVariantNumeric: 'tabular-nums' }}>{v}</dd>
          </div>
        ))}
      </dl>

      <p style={{ fontSize: '13px', color: C.suave, margin: '0 0 20px 0', lineHeight: 1.55 }}>
        Lo procesamos nosotros y te avisamos en la campana cuando esté
        acreditado{beneficiario ? <> en la cuenta de <strong style={{ color: C.texto }}>{beneficiario}</strong></> : null}.
        Podés cerrar esta pantalla.
      </p>

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <Boton tipo="primario" ancho onClick={onHistorial} testid={`${testid}-historial`}>
          Ver en mi historial
        </Boton>
        {onOtroEnvio ? (
          <Boton ancho onClick={onOtroEnvio} testid={`${testid}-otro`}>
            Hacer otro envío
          </Boton>
        ) : null}
      </div>
    </section>
  );
}
