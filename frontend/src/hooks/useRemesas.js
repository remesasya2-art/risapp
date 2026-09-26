/**
 * useRemesas — ¿se puede gastar en Venezuela y en Brasil?
 *
 * La llave del servicio de remesas entero. El por qué y lo que corta está en
 * `backend/services/remesas_abiertas.py`.
 *
 * DE DONDE SALE, Y POR QUE DE AHI
 *
 *   De `/api/limits`, la MISMA ruta de la que el servidor saca lo que hace
 *   cumplir. Con remesas en pausa, las cinco rutas que crean un envío
 *   contestan 503: un botón que las llame es un botón que lleva a un error.
 *
 *   La recarga y la cripto no se miran acá: `/limits` ya las publica
 *   recortadas por esta llave, así que `useRecarga` y `useCripto` dicen la
 *   verdad solos.
 *
 * MIENTRAS NO SE SABE, SE ASUME QUE SI
 *
 *   Igual que `useEncomiendas` y `useRecarga`, y con el mismo criterio con
 *   el que falla la guarda del servidor: esconder de más le saca al usuario
 *   algo que hoy funciona; mostrar de más, en el peor caso, le da un mensaje
 *   claro del servidor.
 */
import { useEffect, useState } from 'react';
import api from '../utils/api';

export default function useRemesas() {
  const [estado, setEstado] = useState({ cargando: true, abiertas: true });

  useEffect(() => {
    let vigente = true;
    api.get('/limits')
      .then((r) => {
        if (!vigente) return;
        // `undefined` —un backend viejo que todavía no publica la clave— se
        // trata como abiertas: durante un despliegue a medias no se le
        // esconde al usuario algo que el servidor sigue aceptando.
        const v = r.data?.remesas;
        setEstado({ cargando: false, abiertas: v === undefined ? true : Boolean(v) });
      })
      .catch(() => { if (vigente) setEstado({ cargando: false, abiertas: true }); });
    return () => { vigente = false; };
  }, []);

  return estado;
}
