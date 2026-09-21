"""
El simulador del riel PIX: un liquidante de mentira con las formas del real.

PARA QUE SIRVE

    Para construir y probar todo lo que está de este lado del contrato —las
    operaciones, los asientos, la cola, la pestaña— sin tener todavía un
    liquidante. Habla el mismo idioma que va a hablar el real: recibe una
    orden (pacs.008), contesta «aceptada» y después AVISA el resultado
    (pacs.002), como hace el SPI, que no liquida en la misma llamada.

    Los avisos entran por el mismo lugar por el que van a entrar los del
    liquidante real: `operaciones.recibir_aviso`, que es nuestro webhook.

LAS CLAVES DE PRUEBA

    Un DICT chico con claves que se portan distinto, para ver cada camino
    con los propios ojos:

      ana@ejemplo.test          paga normal, liquida enseguida
      +5511999990000            ídem, por teléfono
      12345678909               ídem, por CPF
      123e4567-…-426614174000   ídem, clave aleatoria
      rechaza@ejemplo.test      el SPI la rechaza (AC06, cuenta bloqueada)
      tarda@ejemplo.test        queda «en liquidación» hasta que alguien
                                simule el resultado desde la pestaña
      noexiste@ejemplo.test     no está en el DICT

    Dominios de ejemplo, nunca un proveedor real: regla de la casa.
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from nucleo.esquema import sim_claves
from nucleo.rieles import pix

NOMBRE = "simulador"
ISPB = "99999999"                                  # el nuestro, de mentira
INSTITUCION = "RIS Instituicao de Pagamento"       # como sale en el BR Code: sin acentos
CIUDAD = "SAO PAULO"
CLAVE_RECEPTORA = "cobros@ejemplo.test"            # la clave con la que la institución cobra

NORMAL, RECHAZA, TARDA = "normal", "rechaza", "tarda"

CLAVES_DE_PRUEBA = (
    # clave,                                   tipo,          nombre,             documento,        ispb,       banco,                       comportamiento
    ("ana@ejemplo.test",                       pix.EMAIL,     "Ana Prueba",       "12345678909",    "11111111", "Banco Azul de Prueba",      NORMAL),
    ("+5511999990000",                         pix.TELEFONE,  "Beto Prueba",      "98765432100",    "22222222", "Banco Verde de Prueba",     NORMAL),
    ("12345678909",                            pix.CPF,       "Ana Prueba",       "12345678909",    "11111111", "Banco Azul de Prueba",      NORMAL),
    ("123e4567-e89b-12d3-a456-426614174000",   pix.EVP,       "Cooperativa Prueba", "12345678000195", "33333333", "Cooperativa de Prueba",   NORMAL),
    ("rechaza@ejemplo.test",                   pix.EMAIL,     "Cuenta Bloqueada", "98765432100",    "44444444", "Banco Cerrado de Prueba",   RECHAZA),
    ("tarda@ejemplo.test",                     pix.EMAIL,     "Liquidacion Lenta", "12345678909",   "55555555", "Banco Lento de Prueba",     TARDA),
)


async def sembrar(sesion) -> int:
    """Deja las claves de prueba en la base si no están. Idempotente."""
    existentes = {c for (c,) in (await sesion.execute(select(sim_claves.c.clave))).all()}
    filas = [dict(clave=c, tipo=t, nombre=n, documento=d, ispb=i, banco=b, comportamiento=comp)
             for c, t, n, d, i, b, comp in CLAVES_DE_PRUEBA if c not in existentes]
    if filas:
        await sesion.execute(sim_claves.insert(), filas)
    return len(filas)


def _nuevo_id_de_aviso() -> str:
    return "sim_" + secrets.token_hex(8)


async def _avisar(sesion, tipo: str, carga: dict) -> dict:
    """Lo que el liquidante real hace por webhook, el simulador lo hace
    llamando a nuestro receptor directamente. Mismo receptor, mismo camino."""
    from nucleo.rieles import operaciones
    return await operaciones.recibir_aviso(sesion, riel=NOMBRE, id_externo=_nuevo_id_de_aviso(),
                                           tipo=tipo, carga=carga)


class Simulador:
    nombre = NOMBRE
    ispb = ISPB

    async def consultar_clave(self, sesion, clave: str):
        await sembrar(sesion)
        fila = (await sesion.execute(select(sim_claves).where(sim_claves.c.clave == clave))).first()
        if fila is None:
            return None
        return pix.TitularDeClave(clave=fila.clave, tipo=fila.tipo, nombre=fila.nombre,
                                  documento_enmascarado=pix.enmascarar_documento(fila.documento),
                                  ispb=fila.ispb, banco=fila.banco)

    async def _comportamiento(self, sesion, clave: str) -> str:
        fila = (await sesion.execute(
            select(sim_claves.c.comportamiento).where(sim_claves.c.clave == clave))).first()
        return fila.comportamiento if fila else NORMAL

    async def cobrar(self, sesion, *, txid: str, monto: int, cuenta_id: str, descripcion: str) -> pix.Cobro:
        codigo = pix.br_code(clave=CLAVE_RECEPTORA, monto_centavos=monto, nombre=INSTITUCION,
                             ciudad=CIUDAD, txid=txid, descripcion=descripcion or None)
        return pix.Cobro(txid=txid, monto=monto, codigo_br=codigo, clave_receptora=CLAVE_RECEPTORA)

    async def pagar(self, sesion, *, orden: pix.OrdenDePago) -> pix.RespuestaDeEstado:
        """Contesta «aceptada, en liquidación» y, según la clave, avisa el
        resultado final enseguida (normal, rechaza) o no avisa nada (tarda)."""
        comportamiento = await self._comportamiento(sesion, orden.clave_destino)
        if comportamiento == RECHAZA:
            await _avisar(sesion, "estado_de_pago",
                          {"end_to_end": orden.end_to_end, "estado": pix.RJCT, "motivo": "AC06"})
        elif comportamiento == NORMAL:
            await _avisar(sesion, "estado_de_pago",
                          {"end_to_end": orden.end_to_end, "estado": pix.ACSC, "motivo": None})
        return pix.RespuestaDeEstado(end_to_end=orden.end_to_end, estado=pix.ACSP)

    async def devolver(self, sesion, *, devolucion: pix.Devolucion) -> pix.RespuestaDeEstado:
        await _avisar(sesion, "estado_de_pago",
                      {"end_to_end": devolucion.end_to_end, "estado": pix.ACSC, "motivo": None})
        return pix.RespuestaDeEstado(end_to_end=devolucion.end_to_end, estado=pix.ACSP)

    # ── lo que sólo un simulador puede hacer ──────────────────────────────

    async def simular_pago_del_cobro(self, sesion, *, txid: str, monto: int, pagador_clave: str) -> dict:
        """Alguien pagó el QR. Llega el crédito (pacs.008 hacia nosotros)."""
        pagador = await self.consultar_clave(sesion, pagador_clave)
        if pagador is None:
            raise ValueError(f"La clave del pagador no está en el DICT de prueba: {pagador_clave}.")
        end_to_end = pix.nuevo_end_to_end(pagador.ispb, datetime.now(timezone.utc))
        return await _avisar(sesion, "credito_recibido", {
            "txid": txid, "end_to_end": end_to_end, "monto": monto,
            "pagador": {"clave": pagador.clave, "nombre": pagador.nombre,
                        "documento": pagador.documento_enmascarado, "ispb": pagador.ispb, "banco": pagador.banco},
        })

    async def simular_resultado(self, sesion, *, end_to_end: str, estado: str, motivo: str = None) -> dict:
        """Para las claves que tardan: el SPI por fin contestó."""
        if estado not in (pix.ACSC, pix.RJCT):
            raise ValueError("El resultado es ACSC (liquidado) o RJCT (rechazado).")
        if estado == pix.RJCT and motivo not in pix.MOTIVOS_DE_RECHAZO:
            raise ValueError("Un rechazo lleva un motivo del catálogo del SPI.")
        return await _avisar(sesion, "estado_de_pago",
                             {"end_to_end": end_to_end, "estado": estado, "motivo": motivo if estado == pix.RJCT else None})
