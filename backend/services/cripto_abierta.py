"""
¿Está abierta la vía cripto? Una sola definición, y la miran todas las rutas.

POR QUE ESTE ARCHIVO EXISTE

    Son treinta y cinco rutas de USDT, USDC y BTC Lightning. La condición
    escrita en cada una es la condición que un día se actualiza en treinta y
    cuatro. Ya pasó en este repositorio con el segundo factor: la regla vivía
    copiada en dos puertas de ingreso, y la copia de una dejaba afuera al
    cliente. Ver `services/personal.pide_dos_pasos`.

LOS TRES ESTADOS, Y POR QUE SON UN NUMERO Y NO DOS INTERRUPTORES

    El motivo está escrito junto al ajuste, en `services/configuracion.py`. En
    resumen: dos interruptores permiten la combinación «entra pero no sale»,
    que le atrapa la plata a quien deposite. Con un número, esa combinación no
    existe.

        2  abierta        como siempre
        1  sólo salida    no entran depósitos; quien tiene saldo lo saca
        0  cerrada        ni entra ni sale

QUE NO PREGUNTA POR ESTO, Y ES DELIBERADO

    LOS WEBHOOKS QUE ACREDITAN. `/api/credits/webhook`,
    `/api/crypto-send/webhook` y `/api/btc/webhook/blink` no llaman a este
    módulo en ningún estado.

    El motivo: alguien puede haber pagado en la blockchain minutos antes del
    apagado. Esa plata ya salió de su billetera y no vuelve. Un webhook cerrado
    dejaría el pago hecho y el saldo sin acreditar — o sea, plata de un usuario
    que se queda la empresa por un ajuste del panel.

    No abre ningún agujero, porque la ruta que CREA el pago (`/credits/deposit`)
    sí está cerrada: el webhook sólo puede terminar de acreditar una orden que
    ya existía antes del apagado.

    LAS LECTURAS. Los historiales y los reportes del panel tampoco preguntan.
    Lo ya operado tiene que seguir visible para conciliar y para el libro mayor.
    Esconder la contabilidad no es apagar una vía: es perderla de vista, y
    encima justo cuando hay que comprobar que los saldos llegaron a cero.

FALLA CERRADO PARA LA ENTRADA Y ABIERTO PARA LA SALIDA

    Si la base no contesta, `_estado` no puede saber en qué estado está. Las dos
    guardas eligen distinto a propósito, y cada una elige lo que no hace daño:

      · La entrada se niega. Dejar entrar plata sin poder comprobar que la vía
        está abierta es crear custodia que quizá no se puede devolver.
      · La salida se permite. Negarle a alguien sacar SU plata porque nuestra
        base tuvo un mal momento es el error más caro de los dos.

    Es el mismo criterio que la sección 9 del dossier: la falla de un
    componente nuestro no se le cobra al usuario, y la falla de un control de
    seguridad sí frena la operación. Acá el control es la entrada.
"""
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

CLAVE = "cripto_abierta"

CERRADA = 0
SOLO_SALIDA = 1
ABIERTA = 2

# Lo que ve el usuario. No dice «configuración» ni «ajuste»: dice qué pasa y
# qué puede hacer, que es lo único que le sirve.
# EL VOCABULARIO ES EL DE LA APLICACION: «gastar», no «enviar dinero».
#
#   La primera versión decía «podés seguir enviando dinero». El menú del
#   panel del cliente dice «Gastar en Venezuela» y «Gastar en Brasil», así que
#   «enviar dinero» era la palabra suelta que no usa ninguna otra pantalla.
#
#   La regla escrita en `Landing.jsx` —no describir el servicio como envío de
#   dinero— vale para las páginas públicas y no para acá adentro, donde el
#   usuario ya sabe qué contrató. Igual se alinea: dos vocabularios para la
#   misma acción es como se termina llamándola de tres formas.
SIN_DEPOSITOS = ("Los depósitos en cripto no están disponibles por ahora. "
                 "Podés recargar tu saldo con PIX y gastarlo como siempre.")
CERRADA_DEL_TODO = ("La vía cripto no está disponible por ahora. Podés "
                    "recargar tu saldo con PIX y gastarlo como siempre.")


async def _estado(db) -> int:
    """El estado guardado, o el de fábrica si no se puede leer.

    El `except` devuelve `SOLO_SALIDA` y no `ABIERTA`: si no se sabe, lo que no
    hace daño es no aceptar plata nueva. Ver el encabezado.
    """
    from services import configuracion
    try:
        return int(await configuracion.leer(db, CLAVE))
    except Exception as e:                                    # pragma: no cover
        logger.error("No se pudo leer %s, se asume sólo salida: %s", CLAVE, e)
        return SOLO_SALIDA


async def acepta_depositos(db) -> bool:
    """¿Puede nacer saldo cripto nuevo? Sólo con la vía abierta del todo."""
    return await _estado(db) == ABIERTA


async def acepta_envios(db) -> bool:
    """¿Se puede sacar saldo cripto? En 2 y en 1, que es el estado de apagado
    que existe justamente para que la plata pueda salir."""
    return await _estado(db) >= SOLO_SALIDA


async def se_le_muestra(db) -> bool:
    """¿Las pantallas de cripto se le dibujan al cliente?

    En 1 sí, y a propósito: si no se le muestran, quien tiene saldo no tiene
    por dónde sacarlo. Desaparecen recién en 0, cuando ya no hay nada que
    sacar."""
    return await _estado(db) >= SOLO_SALIDA


async def exigir_deposito(db) -> None:
    """Frena la ruta si no pueden entrar depósitos. 503 y no 403: no es que
    esta cuenta no tenga permiso, es que el servicio no está dando eso ahora.
    Un 403 le haría pensar que hizo algo mal."""
    if not await acepta_depositos(db):
        raise HTTPException(status_code=503, detail=SIN_DEPOSITOS)


async def exigir_envio(db) -> None:
    """Frena la ruta si no pueden salir envíos cripto."""
    if not await acepta_envios(db):
        raise HTTPException(status_code=503, detail=CERRADA_DEL_TODO)


def para_el_frontend(estado: int) -> dict:
    """Lo que `/api/limits` publica, para que la pantalla esconda exactamente lo
    mismo que el servidor rechaza.

    Se publican las tres respuestas ya resueltas y no el número crudo: el
    número obliga a cada pantalla a saber qué significa cada valor, y la
    pantalla que se equivoca dibuja un botón que el servidor va a rechazar.
    """
    return {
        "estado": estado,
        "deposito": estado == ABIERTA,
        "envio": estado >= SOLO_SALIDA,
        "visible": estado >= SOLO_SALIDA,
    }
