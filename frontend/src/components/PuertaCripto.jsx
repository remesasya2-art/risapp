/**
 * PuertaCripto — envuelve las rutas de la vía cripto.
 *
 * POR QUE VA EN LA RUTA Y NO DENTRO DE CADA PANTALLA
 *
 *   Porque ataja también a quien escriba la dirección a mano. Esconder los
 *   botones deja las tres pantallas alcanzables por `/send-crypto`,
 *   `/credits/deposit` y `/btc-lightning`, y alguien con el enlace guardado en
 *   favoritos llega igual: ve la pantalla entera, la completa, y recién al
 *   final se come un 503 sin entender.
 *
 * POR QUE PIDE `tipo`, Y NO ALCANZA CON UN SOLO PORTON
 *
 *   La primera versión de este archivo miraba `visible` para las tres, y estaba
 *   MAL. Se vio corriendo la app: en el estado de apagado, `/credits/deposit` y
 *   `/btc-lightning` seguían abriéndose, y las dos son ENTRADA — el usuario
 *   completaba la pantalla y el servidor la rechazaba al final con un 503.
 *
 *   Las tres pantallas no son lo mismo:
 *
 *     tipo="envio"     `/send-crypto`. Saca saldo que ya existe. Tiene que
 *                      seguir abierta en el estado de apagado: es por donde la
 *                      plata de alguien sale.
 *     tipo="deposito"  `/credits/deposit` mete cripto, y `/btc-lightning`
 *                      genera una factura para que entre cripto nueva. Las dos
 *                      se cierran apenas la entrada se cierra.
 *
 *   El `tipo` es obligatorio a propósito: un valor por omisión sería el que
 *   alguien se olvida de poner en la pantalla siguiente, y el olvido no se ve
 *   —la pantalla abre— hasta que un usuario se come el 503.
 */
import { Navigate } from 'react-router-dom';
import useCripto from '../hooks/useCripto';

export default function PuertaCripto({ tipo, children }) {
  const cripto = useCripto();

  if (tipo !== 'envio' && tipo !== 'deposito') {
    throw new Error(
      `PuertaCripto necesita tipo="envio" o tipo="deposito", llegó «${tipo}». `
      + 'Sin eso no se sabe si esta pantalla mete o saca plata.');
  }

  // Mientras no se sabe, nada. Dibujar la pantalla y sacarla medio segundo
  // después es peor que esperar: alguien llega a escribir un monto.
  if (cripto.cargando) return null;

  const pasa = tipo === 'envio' ? cripto.envio : cripto.deposito;

  // A la portada, y no a un cartel propio: la vía apagada no es un error del
  // que haya que informar cada vez, es una función que no está. El cartel que
  // sí hace falta va en los lugares de donde se sacaron los botones.
  if (!pasa) return <Navigate to="/" replace />;

  return children;
}
