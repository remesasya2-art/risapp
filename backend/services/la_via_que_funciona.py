"""
Qué SI puede hacer el usuario, cuando algo no se puede.

POR QUE ESTO EXISTE

    Tres mensajes distintos le decían al usuario «esto no está disponible,
    pero podés recargar tu saldo»:

      · `pago_al_final.exigir_activo`, cuando el flujo que cobra al final
        está apagado.
      · `cripto_abierta.SIN_DEPOSITOS`, cuando no se aceptan depósitos.
      · `cripto_abierta.CERRADA_DEL_TODO`, cuando la vía cripto está cerrada.

    Los tres quedaron mintiendo el día que se pudo cerrar la carga de saldo
    (`services/recarga_abierta.py`): mandaban a recargar a alguien que no
    puede recargar. Y los tres mintieron A LA VEZ, porque los tres tenían la
    misma frase escrita por separado.

    Eso es lo que este archivo arregla: la salida se calcula UNA vez, mirando
    la configuración de verdad, y los tres la usan. La próxima vía que se
    apague o se prenda no deja tres mensajes que alguien tiene que acordarse
    de actualizar.

POR QUE NO ALCANZABA CON CORREGIR LAS TRES FRASES

    Porque la respuesta correcta depende del estado, y el estado cambia desde
    el panel sin desplegar. Una frase fija vuelve a mentir en cuanto alguien
    aprieta un botón — que es exactamente lo que acababa de pasar.

LAS TRES RESPUESTAS POSIBLES

    1. Se puede cargar saldo   → que cargue y gaste, como siempre.
    2. No, pero se puede pagar
       el envío al final       → que envíe directamente; no necesita saldo.
    3. Ninguna de las dos      → NO DEBERIA PASAR NUNCA. El seguro de
                                 `configuracion.revisar_las_parejas` no deja
                                 guardar esa combinación, justamente porque
                                 deja la aplicación sin forma de mover plata.

                                 Si igual pasa —alguien escribió en la base a
                                 mano, una migración— el mensaje no inventa una
                                 salida que no existe: manda a soporte, que es
                                 lo único verdadero en ese momento. Y queda un
                                 ERROR en el registro, porque significa que el
                                 seguro no está haciendo su trabajo.

EL VOCABULARIO ES EL DE LA APLICACION

    «Gastar», no «enviar dinero». El menú del panel del cliente dice «Gastar
    en Venezuela» y «Gastar en Brasil». Es la misma razón por la que
    `cripto_abierta` dejó de decir «podés seguir enviando dinero»: dos
    vocabularios para la misma acción es como se termina llamándola de tres
    formas.
"""
import logging

logger = logging.getLogger(__name__)

# Lo que se le dice según lo que de verdad se puede hacer.
CARGANDO_SALDO = "Podés recargar tu saldo y gastarlo como siempre."
PAGANDO_AL_FINAL = ("Podés hacer tu envío directamente y pagarlo al final, "
                    "con PIX o con tarjeta: no hace falta cargar saldo.")
NI_UNA_NI_OTRA = ("Escribinos por el chat de soporte y te ayudamos a "
                  "completarlo.")


async def para_poner_plata(db) -> str:
    """La frase que nombra la vía que SI funciona ahora mismo.

    Se le pega al final de un «esto no está disponible». Un rechazo que no
    dice qué hacer manda a soporte a preguntar lo que la pantalla podía haber
    contestado sola.

    FALLA HACIA LA VIA MAS SEGURA DE NOMBRAR.

        Si no se puede leer la configuración, se devuelve la del pago al
        final. Motivo: es la que no depende de que la recarga esté abierta, y
        equivocarse ofreciéndola sólo cuesta que el usuario vea un segundo
        mensaje del servidor. Ofrecer recargar cuando la recarga está cerrada
        lo manda a una pantalla que rebota, que es el error que este archivo
        existe para no repetir.
    """
    from services import pago_al_final, recarga_abierta

    try:
        se_puede_cargar = await recarga_abierta.esta_abierta(db)
        hay_pago_al_final = await pago_al_final.esta_activo(db)
    except Exception as e:                                    # pragma: no cover
        logger.error("No se pudo leer con qué se puede pagar: %s", e)
        return PAGANDO_AL_FINAL

    if se_puede_cargar:
        return CARGANDO_SALDO
    if hay_pago_al_final:
        return PAGANDO_AL_FINAL

    # El caso 3. Ver el encabezado: el seguro del panel no lo deja guardar.
    logger.error(
        "No hay ninguna forma de poner plata: la carga de saldo está cerrada "
        "y el pago al final apagado. El seguro de "
        "`configuracion.revisar_las_parejas` no deja guardar esa combinación, "
        "así que alguien la escribió por fuera del panel.")
    return NI_UNA_NI_OTRA


async def con(db, no_se_puede: str) -> str:
    """El mensaje entero: lo que no se puede, y qué hacer en su lugar.

    Existe para que los tres llamadores no repitan el `f"{a} {b}"` — que es la
    forma en que una de las tres se queda un día sin la segunda mitad.
    """
    return f"{no_se_puede} {await para_poner_plata(db)}"
