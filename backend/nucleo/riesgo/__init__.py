"""
Riesgo: qué se mira de la conducta, qué se abre cuando algo no cierra, y
cómo se le cuenta al COAF.

TRES PIEZAS

    monitoreo   reglas sobre las operaciones ya liquidadas: umbral por
                operación, acumulado de 30 días y de 12 meses, fraccionamiento,
                velocidad, contraparte repetida, horario. Cada regla que salta
                deja una alerta, y la alerta abre (o engorda) un caso. Los
                umbrales se configuran desde el panel, nunca en código.
    casos       el expediente: quién lo analiza, qué se anotó, qué se
                concluyó, y los plazos de la Circular 3.978: 45 días para
                analizar, 24 horas para comunicar desde la conclusión.
                Comunicar exige cuatro ojos: uno concluye, otro aprueba.
    coaf        el archivo de la comunicación con los campos del SISCOAF, y
                el puerto por el que se manda. Hoy, un simulador que
                devuelve un acuse; el día que haya credencial, el adaptador
                real habla con el SISCOAF con esa misma forma.

LO QUE SE CONSERVA

    Todo, diez años (Circular 3.978, art. 56 y siguientes): alertas, casos,
    notas, comunicaciones y acuses. No hay función que borre nada.
"""
from typing import Protocol


class Comunicador(Protocol):
    nombre: str

    async def enviar(self, sesion, *, archivo: str, tipo: str) -> str:
        """Manda la comunicación y devuelve el acuse (el número de protocolo)."""


def comunicador() -> Comunicador:
    from nucleo.riesgo.coaf import SimuladorSiscoaf
    return SimuladorSiscoaf()
