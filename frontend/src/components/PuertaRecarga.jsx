/**
 * PuertaRecarga — envuelve las rutas de cargar saldo.
 *
 * POR QUE VA EN LA RUTA Y NO SOLO EN LOS BOTONES
 *
 *   Porque ataja a quien escriba `/recharge` a mano o la tenga en favoritos.
 *   Esconder las ocho puertas deja las dos pantallas alcanzables igual: la
 *   persona elige método, escribe el monto, y recién al apretar se come un
 *   503.
 *
 * MIENTRAS NO SE SABE, DEJA PASAR
 *
 *   Mismo criterio que el hook y que la guarda del backend: esconder de más le
 *   saca algo que hoy funciona; dejar pasar de más, en el peor caso, le da el
 *   mensaje del servidor, que nombra la vía que sí anda.
 */
import { Navigate } from 'react-router-dom';
import useRecarga from '../hooks/useRecarga';

export default function PuertaRecarga({ children }) {
  const { cargando, abierta } = useRecarga();
  if (cargando) return null;
  if (!abierta) return <Navigate to="/" replace />;
  return children;
}
