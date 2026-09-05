/**
 * usePulso — repetir una tarea cada tanto, sin gastar cuando nadie mira.
 *
 * POR QUE EXISTE
 *
 *   La mesa de ayuda se entera de las novedades preguntando: la bandeja del
 *   asesor cada pocos segundos, la conversación del cliente también. Escrito a
 *   mano con `setInterval` eso trae siempre los mismos tres problemas:
 *
 *     · La pestaña en segundo plano sigue preguntando. Un asesor con la mesa
 *       abierta en una solapa que no mira le pega al servidor todo el día, y
 *       son muchos asesores.
 *     · Al volver a la pestaña hay que esperar el próximo ciclo para ver lo
 *       que pasó mientras tanto. Se siente colgado.
 *     · La tarea queda congelada en el primer render: el `setInterval` guarda
 *       la función de entonces, con las variables de entonces.
 *
 *   Acá la tarea vive en una referencia que se actualiza en cada render —así
 *   el intervalo siempre llama a la última—, no corre con la pestaña oculta, y
 *   corre una vez ni bien vuelve a estar visible.
 */
import { useEffect, useRef } from 'react';

/**
 * @param tarea   Lo que hay que repetir. Se lee siempre la última versión.
 * @param cadaMs  Cada cuánto.
 * @param clave   Sobre QUÉ late. Cambiarla vuelve a arrancar el pulso y corre
 *                la tarea en el acto —al abrir otro caso, la conversación se
 *                trae ya, no en el próximo ciclo—. `null`, `undefined` o
 *                `false` apagan el pulso: es lo que hay que mirar cuando no
 *                hay nada seleccionado.
 */
export default function usePulso(tarea, cadaMs, clave = true) {
  const guardada = useRef(tarea);
  // En un efecto y no en el cuerpo: escribir una referencia mientras React
  // dibuja es justo lo que la regla `react-hooks/refs` prohíbe, y con razón
  // —en un render descartado quedaría guardada una tarea que nunca corrió—.
  useEffect(() => { guardada.current = tarea; });

  useEffect(() => {
    if (clave === null || clave === undefined || clave === false || !cadaMs) {
      return undefined;
    }

    let vivo = true;
    const correr = () => {
      if (!vivo) return;
      if (typeof document !== 'undefined' && document.hidden) return;
      guardada.current?.();
    };

    correr();
    const id = setInterval(correr, cadaMs);
    const alVolver = () => correr();
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', alVolver);
    }
    return () => {
      vivo = false;
      clearInterval(id);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', alVolver);
      }
    };
  }, [cadaMs, clave]);
}
