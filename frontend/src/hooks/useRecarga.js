/**
 * useRecarga — ¿se puede cargar saldo?
 *
 * POR QUE UN SOLO LUGAR
 *
 *   Son ocho puertas a `/recharge`: la tarjeta de saldo, el menú del panel,
 *   el historial vacío, el detalle de un envío, los primeros pasos, el
 *   dashboard, y la pantalla de envío cuando falta saldo. La condición escrita
 *   en cada una es la que un día se actualiza en siete.
 *
 * DE DONDE SALE, Y POR QUE DE AHI
 *
 *   De `/api/limits`, la MISMA ruta de la que el servidor saca lo que hace
 *   cumplir. Con la recarga cerrada esas cuatro rutas contestan 503, así que
 *   un botón que las llame es un botón que lleva a un error.
 *
 * MIENTRAS NO SE SABE, SE ASUME QUE SI
 *
 *   Al revés que `useCripto`, que arranca escondiendo. Acá esconder de más le
 *   saca al usuario algo que hoy funciona; mostrar de más, en el peor caso, le
 *   da un mensaje claro del servidor. Entre las dos equivocaciones, la segunda
 *   es la barata — y es el mismo criterio con el que falla la guarda del
 *   backend, escrito en `services/recarga_abierta.py`.
 */
import { useEffect, useState } from 'react';
import api from '../utils/api';

export default function useRecarga() {
  const [estado, setEstado] = useState({ cargando: true, abierta: true });

  useEffect(() => {
    let vigente = true;
    api.get('/limits')
      .then((r) => {
        if (!vigente) return;
        // `undefined` —un backend viejo que todavía no publica la clave— se
        // trata como abierta, no como cerrada: durante un despliegue a medias
        // no se le esconde al usuario algo que el servidor sigue aceptando.
        const v = r.data?.recarga;
        setEstado({ cargando: false, abierta: v === undefined ? true : Boolean(v) });
      })
      .catch(() => { if (vigente) setEstado({ cargando: false, abierta: true }); });
    return () => { vigente = false; };
  }, []);

  return estado;
}
