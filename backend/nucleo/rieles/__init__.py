"""
Los rieles de pago del núcleo: por dónde entra y sale la plata de verdad.

QUE ES UN RIEL

    Un riel es un sistema de pagos al que la institución se conecta: el PIX
    (por el SPI, el sistema del Banco Central), y mañana el TED o el boleto.
    Como instituição de pagamento no autorizada a ser participante directa,
    la institución llega al SPI a través de un LIQUIDANTE: un banco
    participante que recibe nuestras órdenes y nos avisa lo que pasa.

EL PUERTO

    `Riel` es la forma que tiene que tener cualquier riel para que el resto
    del núcleo lo use: cobrar, pagar, devolver, consultar una clave. Hoy la
    única implementación es el simulador (`simulador.py`). El día que haya
    contrato con un liquidante, se escribe `liquidante.py` con esta misma
    forma, y nada más cambia: ni las operaciones, ni la cola, ni el libro.

    Por eso el puerto está escrito ANTES de que exista un riel real: es la
    parte de la arquitectura que decide cuánto cuesta el día del contrato.

LO QUE EL PUERTO NO HACE

    No toca el libro ni la cola. Un riel dice «esto salió» o «esto entró»; lo
    que eso significa contablemente lo decide `operaciones.py`, que es el
    único que llama a los comandos del libro. Un riel que asentara por su
    cuenta sería un segundo camino a la plata.

LO QUE ACA NO HAY, A PROPOSITO

    Nada de remesas ni de paquetes. Esto es una institución de pagos en
    Brasil: cuentas de pago y PIX. El resto de la aplicación no se importa
    (el test de la frontera lo sostiene).
"""
from typing import Protocol

from nucleo.rieles import pix


class Riel(Protocol):
    """Lo que un riel sabe hacer. Los montos en centavos, siempre."""

    nombre: str

    async def cobrar(self, sesion, *, txid: str, monto: int, cuenta_id: str, descripcion: str) -> pix.Cobro:
        """Genera un cobro (un QR / BR Code) que otro puede pagar."""

    async def pagar(self, sesion, *, orden: pix.OrdenDePago) -> pix.RespuestaDeEstado:
        """Envía una orden de pago al SPI. La respuesta inmediata suele ser
        «aceptada, en liquidación»; el resultado final llega por aviso."""

    async def devolver(self, sesion, *, devolucion: pix.Devolucion) -> pix.RespuestaDeEstado:
        """Devuelve (total o parcialmente) un pago recibido."""

    async def consultar_clave(self, sesion, clave: str) -> pix.TitularDeClave | None:
        """Consulta el DICT: de quién es la clave, o None si no existe."""


def vigente():
    """El riel que corresponde al modo. Hoy hay uno solo: el simulador. El
    día que exista el adaptador real, acá se elige por configuración —nunca
    editando código— y ACTIVO lo va a exigir."""
    from nucleo.rieles.simulador import Simulador
    return Simulador()
