/**
 * PuertaEncomiendas — envuelve la ruta de mandar un paquete nuevo.
 *
 * POR QUE VA EN LA RUTA Y NO SOLO EN LOS BOTONES
 *
 *   Porque ataja a quien escriba `/envios/nuevo` a mano o la tenga en
 *   favoritos. Esconder las cuatro puertas deja la pantalla alcanzable igual:
 *   la persona llena el formulario entero y recién al cotizar se come un 503.
 *
 * SOLO LA DE MANDAR UNO NUEVO
 *
 *   «Mis envíos» y el detalle de cada uno NO llevan esta puerta: lo que ya
 *   está en camino sigue su curso, y quien lo mandó tiene que poder verlo.
 *
 * MIENTRAS NO SE SABE, DEJA PASAR
 *
 *   Mismo criterio que el hook y que la guarda del backend.
 */
import { Navigate } from 'react-router-dom';
import useEncomiendas from '../hooks/useEncomiendas';

export default function PuertaEncomiendas({ children }) {
  const { cargando, abiertas } = useEncomiendas();
  if (cargando) return null;
  if (!abiertas) return <Navigate to="/envios" replace />;
  return children;
}
