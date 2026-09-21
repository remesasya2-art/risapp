/**
 * useEsperarElPago — «¿ya entró el PIX?», preguntado al servidor hasta que
 * conteste que sí, que venció, o que se canceló.
 *
 * POR QUE EXISTE
 *
 *   El aviso de Mercado Pago llega bien y el servidor acredita bien —la hoja
 *   de Pagos de Mercado Pago lo muestra—. Pero la pantalla del envío, la del
 *   QR, NO PREGUNTABA NUNCA si el pago había entrado: mostraba el código y
 *   se quedaba ahí. El cliente pagaba, miraba, y no pasaba nada. Con la
 *   recarga sí pasaba, porque `Recharge.jsx` pregunta cada pocos segundos.
 *   Cuando el envío pasó a pagarse al final, la pantalla del QR se escribió
 *   sin la pregunta.
 *
 *   Esto es esa pregunta, en un solo lugar, para que la usen las dos
 *   pantallas que muestran un QR de envío: `Send.jsx` y `RetomarPago.jsx`.
 *
 * DE DONDE SALE LA RESPUESTA
 *
 *   De `/gestor/pix/status/{id}`, la misma ruta que usa la recarga. Cuando el
 *   receptor acredita un cobro de envío, marca el cobro como `paid`
 *   (`services/pago_al_final.confirmar`), y esa ruta lo devuelve.
 *
 * EL RITMO
 *
 *   Copiado de `Recharge.jsx`, y por su mismo motivo: la gente paga en el
 *   primer minuto —abre el banco, escanea, confirma—, y ahí los cinco
 *   segundos valen porque el «listo» tiene que llegar rápido. El que a los
 *   diez minutos no pagó no está a punto de pagar: dejó la pantalla abierta.
 *   Preguntarle cada cinco segundos durante media hora es gastar servidor en
 *   alguien que se fue.
 *
 * LA GUARDA CONTRA PREGUNTAS SOLAPADAS VIVE EN UNA REF, NO EN EL ESTADO
 *
 *   También aprendido en `Recharge.jsx`: una función programada con
 *   `setTimeout` captura el estado del render en que se armó, así que una
 *   guarda por estado nunca frena nada. Una ref no vive en el render: la
 *   función vieja y la nueva miran el mismo valor.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../utils/api';

export const RITMO = [
  { hasta: 60, cada: 5000 },      // el primer minuto: cuando de verdad se paga
  { hasta: 300, cada: 15000 },    // hasta los cinco minutos
  { cada: 30000 },                // de ahí en adelante
];

/** Cuántos milisegundos esperar, según hace cuánto que la persona está mirando. */
export function cadaCuanto(segundosEsperando) {
  const tramo = RITMO.find((t) => t.hasta === undefined || segundosEsperando < t.hasta);
  return (tramo || RITMO[RITMO.length - 1]).cada;
}

// Los tres desenlaces que da el servidor, y el cuarto mientras no da ninguno.
export const ESPERANDO = 'esperando';
export const PAGADO = 'pagado';
export const VENCIDO = 'vencido';
export const CANCELADO = 'cancelado';

function desenlace(status) {
  if (status === 'paid' || status === 'approved' || status === 'completed') return PAGADO;
  if (status === 'expired') return VENCIDO;
  if (status === 'cancelled') return CANCELADO;
  return ESPERANDO;
}

/**
 * @param {string|null} paymentId  El `payment_order_id` del cobro. `null`
 *   apaga la pregunta: es lo que se pasa cuando la pantalla no está en el
 *   paso del QR, o cuando el cobro es con tarjeta (que contesta al instante).
 */
export default function useEsperarElPago(paymentId) {
  const [estado, setEstado] = useState(ESPERANDO);
  const [detalle, setDetalle] = useState(null);
  const enVuelo = useRef(false);
  const programada = useRef(null);
  const desdeCuando = useRef(0);
  const vigente = useRef(paymentId);

  const preguntar = useCallback(async () => {
    if (!paymentId || enVuelo.current) return ESPERANDO;
    enVuelo.current = true;
    try {
      const r = await api.get(`/gestor/pix/status/${paymentId}`);
      // Si mientras se preguntaba la pantalla cambió de cobro, esta respuesta
      // es de otro pedido y no se mira.
      if (vigente.current !== paymentId) return ESPERANDO;
      const como = desenlace(r.data?.status);
      if (como !== ESPERANDO) {
        setEstado(como);
        setDetalle(r.data);
      }
      return como;
    } catch {
      // Una consulta que falla no es un pago que falló: se vuelve a
      // preguntar en la próxima vuelta. Y si esto se rompe del todo, el aviso
      // de Mercado Pago acredita igual y el historial lo muestra.
      return ESPERANDO;
    } finally {
      enVuelo.current = false;
    }
  }, [paymentId]);

  useEffect(() => {
    vigente.current = paymentId;
    // Volver a «esperando» cuando cambia el cobro. En un microtask y no en el
    // cuerpo del efecto: es la regla de la casa para no disparar un render en
    // cascada durante el montaje (`react-hooks/set-state-in-effect`).
    const reinicio = setTimeout(() => { setEstado(ESPERANDO); setDetalle(null); }, 0);
    if (!paymentId) return () => clearTimeout(reinicio);

    desdeCuando.current = Date.now();
    let parado = false;

    const preguntarYVolver = async () => {
      const como = await preguntar();
      if (parado || como !== ESPERANDO) return;
      const esperando = (Date.now() - desdeCuando.current) / 1000;
      programada.current = setTimeout(preguntarYVolver, cadaCuanto(esperando));
    };

    // La primera vez enseguida, en un microtask: el cliente puede haber
    // pagado antes de que la pantalla terminara de dibujarse.
    programada.current = setTimeout(preguntarYVolver, 0);

    return () => {
      parado = true;
      clearTimeout(reinicio);
      clearTimeout(programada.current);
      programada.current = null;
    };
  }, [paymentId, preguntar]);

  // Para el botón «Ya pagué»: pregunta ahora, sin esperar la próxima vuelta.
  const revisarAhora = useCallback(() => preguntar(), [preguntar]);

  return { estado, detalle, revisarAhora };
}
