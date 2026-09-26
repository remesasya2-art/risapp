/**
 * PuertaRemesas — envuelve las dos pantallas donde nace un envío: gastar en
 * Venezuela (`/send`) y gastar en Brasil (`/send-reais`).
 *
 * POR QUE VA EN LA RUTA Y NO SOLO EN LOS BOTONES
 *
 *   Son siete los lugares que llevan a esas pantallas: el menú, la tarjeta del
 *   saldo, la calculadora, los primeros pasos, el historial vacío y los dos
 *   de «hacer otro envío» al terminar un pago. Esconder los botones deja la
 *   pantalla alcanzable igual, desde un favorito o escribiendo la dirección:
 *   la persona llena el formulario entero y recién al confirmar se come un
 *   503. La puerta ataja todos los caminos de una vez.
 *
 * SOLO LAS DE EMPEZAR UNO NUEVO
 *
 *   El historial, el detalle de cada operación y retomar un pago NO llevan
 *   esta puerta: lo que ya empezó termina.
 *
 * MIENTRAS NO SE SABE, DEJA PASAR
 *
 *   Mismo criterio que el hook y que la guarda del servidor.
 */
import { Navigate } from 'react-router-dom';
import useRemesas from '../hooks/useRemesas';

export default function PuertaRemesas({ children }) {
  const { cargando, abiertas } = useRemesas();
  if (cargando) return null;
  if (!abiertas) return <Navigate to="/" replace />;
  return children;
}
