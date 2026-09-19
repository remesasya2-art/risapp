/**
 * useCripto — ¿se le muestra la vía cripto a este visitante?
 *
 * POR QUE UN SOLO LUGAR
 *
 *   Son cuatro puntos de entrada —la tarjeta de saldo, el menú del panel del
 *   cliente, el botón de la pantalla de recargar y las tres pantallas mismas—.
 *   La condición escrita en cada uno es la que un día se actualiza en tres.
 *
 * DE DONDE SALE EL DATO, Y POR QUE DE AHI
 *
 *   De `/api/limits`, que es la MISMA ruta de la que el servidor saca lo que
 *   hace cumplir. Su propio comentario en `services/limits.py` dice para qué
 *   existe: «para que el cartel que ve el usuario y el 400 que devuelve el
 *   servidor no puedan discrepar».
 *
 *   Una ruta nueva y propia habría dado justo el problema contrario: un
 *   despliegue a medias en el que la pantalla dibuja un botón que el servidor
 *   ya rechaza.
 *
 * MIENTRAS NO SE SABE, NO SE DIBUJA NADA
 *
 *   `cargando` arranca en `true` y `visible` en `false`. Dibujar la vía y
 *   esconderla medio segundo después es peor que no dibujarla: alguien llega a
 *   apretar.
 *
 * SI LA CONSULTA FALLA, SE ESCONDE
 *
 *   Es lo contrario de lo que hace la guarda del backend con la salida, y es a
 *   propósito: acá esconder no le quita nada a nadie —el servidor sigue
 *   aceptando el envío si corresponde—, y mostrar una vía que está apagada
 *   manda al usuario a un 503 sin explicación.
 */
import { useEffect, useState } from 'react';
import api from '../utils/api';

export default function useCripto() {
  const [estado, setEstado] = useState({
    cargando: true,
    visible: false,
    deposito: false,
    envio: false,
  });

  useEffect(() => {
    let vigente = true;
    api.get('/limits')
      .then((r) => {
        if (!vigente) return;
        const c = r.data?.cripto;
        setEstado({
          cargando: false,
          visible: Boolean(c?.visible),
          deposito: Boolean(c?.deposito),
          envio: Boolean(c?.envio),
        });
      })
      .catch(() => {
        if (vigente) setEstado({ cargando: false, visible: false, deposito: false, envio: false });
      });
    return () => { vigente = false; };
  }, []);

  return estado;
}
