/**
 * useEncomiendas — ¿se pueden mandar encomiendas nuevas?
 *
 * POR QUE UN SOLO LUGAR
 *
 *   Son cuatro puertas a `/envios/nuevo`: el menú del panel, el botón de «Mis
 *   envíos», y los dos «Cotizar de nuevo» del detalle. La condición escrita en
 *   cada una es la que un día se actualiza en tres.
 *
 * DE DONDE SALE, Y POR QUE DE AHI
 *
 *   De `/api/limits`, la MISMA ruta de la que el servidor saca lo que hace
 *   cumplir. Con el servicio suspendido, cotizar y confirmar contestan 503,
 *   así que un botón que las llame es un botón que lleva a un error.
 *
 * MIENTRAS NO SE SABE, SE ASUME QUE SI
 *
 *   Igual que `useRecarga`, y por el mismo motivo: esconder de más le saca al
 *   usuario algo que hoy funciona; mostrar de más, en el peor caso, le da un
 *   mensaje claro del servidor. Es el mismo criterio con el que falla la
 *   guarda del backend, escrito en `services/encomiendas_abiertas.py`.
 */
import { useEffect, useState } from 'react';
import api from '../utils/api';

export default function useEncomiendas() {
  const [estado, setEstado] = useState({ cargando: true, abiertas: true });

  useEffect(() => {
    let vigente = true;
    api.get('/limits')
      .then((r) => {
        if (!vigente) return;
        // `undefined` —un backend viejo que todavía no publica la clave— se
        // trata como abiertas, no como cerradas: durante un despliegue a
        // medias no se le esconde al usuario algo que el servidor sigue
        // aceptando.
        const v = r.data?.encomiendas;
        setEstado({ cargando: false, abiertas: v === undefined ? true : Boolean(v) });
      })
      .catch(() => { if (vigente) setEstado({ cargando: false, abiertas: true }); });
    return () => { vigente = false; };
  }, []);

  return estado;
}
