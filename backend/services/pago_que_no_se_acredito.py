"""
Un pago que entró y no se pudo acreditar. Que alguien se entere.

POR QUE ESTO EXISTE

    El 20 de septiembre de 2026 un cliente pagó su envío con PIX y la orden se
    quedó en «esperando pago». El historial completo está en
    `docs/incidentes/2026-09-20-un-pix-pagado-que-no-avanzo-el-envio.md`.

    La causa fue una diferencia de tipos —el identificador de Mercado Pago se
    guardaba como número y se buscaba como texto— y está arreglada. Pero al
    buscarla apareció algo peor que la causa:

    EL RECEPTOR DE PAGOS TENIA SEIS SALIDAS QUE NO ACREDITABAN NADA Y NO
    AVISABAN A NADIE.

        No encuentra el cobro. El cobro no está en «pendiente». Mercado Pago
        no contesta. El monto no coincide. La confirmación devuelve que no.

        Las seis dejaban una línea en el registro y devolvían 200. Desde
        afuera —y desde Mercado Pago— todo se veía bien. El cliente había
        pagado y nadie iba a enterarse hasta que reclamara.

    El arreglo de la causa evita ESTE fallo. Esto evita el silencio, que es lo
    que lo hizo durar.

POR QUE 200 Y NO UN ERROR

    Que el receptor conteste 200 en estos casos es correcto: si devolviera un
    error, Mercado Pago reintentaría durante horas y después se rendiría igual,
    sin que nadie hubiera mirado nada.

    Lo que faltaba no era fallar más fuerte. Era avisar.

UNA VEZ POR PAGO Y POR MOTIVO

    Mercado Pago reintenta. Sin un reclamo, el mismo problema avisaría diez
    veces y el equipo aprendería a ignorar el aviso — que es la forma más
    rápida de volver al silencio, con más ruido.

    Se usa `pagos_una_sola_vez`, el mismo candado que impide acreditar dos
    veces, con una clave propia para no pisarle la suya.
"""
import logging

logger = logging.getLogger(__name__)


def identificadores_posibles(mp_payment_id) -> list:
    """Las dos formas en que el identificador de un pago puede estar guardado.

    LA CAUSA DEL INCIDENTE, EN UNA FUNCION.

        Al crear el cobro se guarda lo que devuelve el SDK de Mercado Pago
        —`response.get("id")`, un ENTERO—. Al recibir el aviso llega lo que
        manda el cuerpo —`data.get("id")`, una CADENA—.

        MongoDB no iguala 123456789 con "123456789". El receptor buscaba con
        el valor crudo, no encontraba nada, contestaba 200 y no tocaba la
        orden. Desde afuera todo se veía bien.

    SE BUSCAN LOS DOS Y NO SE NORMALIZA AL GUARDAR

        Los cobros que ya están en la base tienen el número. Una migración que
        no llegara a correr —o que corriera a medias— dejaría el mismo agujero
        abierto para esos, y son justamente los del incidente.
    """
    posibles = [str(mp_payment_id)]
    try:
        posibles.append(int(mp_payment_id))
    except (TypeError, ValueError):
        # No es un número: queda sólo la forma de texto, que es correcta.
        pass
    return posibles

# El prefijo separa estos reclamos de los que evitan acreditar dos veces. Sin
# él, avisar de un problema con el pago 123 impediría acreditarlo después.
PREFIJO = "aviso_sin_acreditar_"

# Lo que se le dice al equipo, por motivo. En español llano: quien lo recibe
# puede ser el que atiende el chat, no quien escribió esto.
MOTIVOS = {
    "no_encontrado": (
        "Entró un pago de Mercado Pago que no coincide con ningún cobro "
        "nuestro. Si es de un cliente, su plata salió y no se le acreditó."),
    "no_esta_pendiente": (
        "Entró un pago sobre un cobro que ya no estaba esperando. Puede ser "
        "un aviso repetido, pero si el cobro quedó marcado raro hay que "
        "mirarlo."),
    "mercadopago_no_contesta": (
        "Entró un pago y no pudimos preguntarle a Mercado Pago si es real, "
        "así que no se acreditó. Si el cliente pagó, está esperando."),
    "monto_distinto": (
        "Entró un pago por un monto distinto al del cobro. No se acreditó "
        "nada y el cobro quedó marcado para revisar."),
    "no_se_pudo_confirmar": (
        "El pago está aprobado en Mercado Pago pero la orden no avanzó. El "
        "cliente pagó y su envío sigue frenado."),
}

QUE_HACER = ("Buscalo en Mercado Pago por su referencia y resolvelo a mano: "
             "acreditar, o devolver.")


async def avisar(db, *, motivo: str, mp_payment_id, referencia=None,
                 detalle: str = "") -> bool:
    """Le avisa al equipo que un pago entró y no se acreditó.

    Devuelve si el aviso salió. NO LEVANTA NUNCA: quien la llama está
    contestándole a Mercado Pago, y una excepción acá convertiría un problema
    de un pago en un reintento eterno de todos.
    """
    from services import pagos_una_sola_vez
    from services.notifications import avisar_al_personal

    que_paso = MOTIVOS.get(motivo, "Entró un pago que no se pudo acreditar.")

    # El registro va SIEMPRE, aunque el aviso no salga o ya se haya avisado.
    # Es lo que queda para conciliar después.
    logger.error(
        "PAGO SIN ACREDITAR (%s): pago de Mercado Pago %s%s. %s%s",
        motivo, mp_payment_id,
        f", referencia {referencia}" if referencia else "",
        que_paso, f" {detalle}" if detalle else "")

    try:
        # Una vez por pago y por motivo. Ver el encabezado.
        primero = await pagos_una_sola_vez.reclamar(
            db, f"{PREFIJO}{motivo}_{mp_payment_id}",
            proveedor="mercadopago_sin_acreditar")
        if not primero:
            return False

        await avisar_al_personal(
            title="Un pago entró y no se acreditó",
            message=f"{que_paso} {QUE_HACER}",
            notification_type="pago_sin_acreditar",
            solo_super_admin=True,
            data={"motivo": motivo,
                  "mp_payment_id": str(mp_payment_id),
                  "referencia": referencia})
        return True
    except Exception as e:                                    # pragma: no cover
        logger.error("No se pudo avisar del pago sin acreditar %s: %s",
                     mp_payment_id, e)
        return False
