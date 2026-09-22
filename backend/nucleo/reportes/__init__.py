"""
Reportes regulatorios: lo que una instituição de pagamento le manda al
Banco Central y a la Receita, armado desde el libro y el legajo.

TRES REPORTES, UN REGISTRO, UN PUERTO

    balancete     el balancete patrimonial mensual con los códigos del COSIF
                  (documento CADOC 4010). Sale del balance de comprobación
                  del libro, SOLO sobre días cerrados: un balancete de un mes
                  que todavía se puede asentar es un balancete que miente.
    ccs           el Cadastro de Clientes do Sistema Financeiro Nacional:
                  cada día, qué relaciones titular–cuenta empezaron y cuáles
                  terminaron. Lo genera la cola cuando se cierra el día.
    efinanceira   la e-Financeira de la Receita Federal: por semestre, los
                  totales mensuales de créditos y débitos y el saldo final
                  de cada cuenta, por titular, cuando superan el límite.
    registro      la tabla `reportes`: cada archivo generado, tal cual se
                  mandó, con su versión (una corrección es una versión nueva,
                  nunca una edición) y el protocolo de la transmisión.
    sta           el puerto `Transmisor` y su simulador. El STA es el sistema
                  de transferencia de archivos del Banco Central; hoy no hay
                  credencial, y el simulador devuelve un protocolo con la
                  forma del de verdad sin que nada salga de la máquina.

EL CALENDARIO

    Qué vence cuándo, y si ya está generado o transmitido, lo calcula
    `nucleo/calendario.py` a partir de esta tabla. Acá no se guarda ningún
    «pendiente»: el pendiente es lo que falta, y lo que falta se deduce.

LO QUE SE CONSERVA

    Todo, y sin función que borre ni edite. Lo que se le mandó a un
    regulador es lo que se le mandó; si estaba mal, se manda otra versión.
"""
from typing import Protocol


class ReporteInvalido(ValueError):
    """Un reporte que no se puede generar o transmitir: período sin cerrar,
    período sin cambios, transmitido dos veces."""


class Transmisor(Protocol):
    nombre: str

    async def transmitir(self, sesion, *, documento: str, periodo: str, archivo: str) -> str:
        """Manda el archivo y devuelve el protocolo que el sistema receptor
        asignó. Lanza si el receptor lo rechaza."""


def transmisor() -> Transmisor:
    from nucleo.reportes.sta import SimuladorSta
    return SimuladorSta()
