"""
El simulador del STA (Sistema de Transferência de Arquivos del Banco
Central) y de los receptores de la Receita.

    El STA de verdad recibe un archivo por HTTPS con certificado de la
    institución y devuelve un protocolo; después, un acuse de procesamiento.
    Este simulador devuelve un protocolo con esa forma y exige lo mismo que
    el de verdad exigiría a simple vista: un archivo bien formado. Nada sale
    de la máquina.

    El día que haya credencial, el adaptador real implementa `Transmisor`
    con la misma firma, y `nucleo.reportes.transmisor()` devuelve ése.
"""
import json
import secrets
from datetime import datetime, timezone


class SimuladorSta:
    nombre = "simulador-sta"

    async def transmitir(self, sesion, *, documento: str, periodo: str, archivo: str) -> str:
        datos = json.loads(archivo)                        # bien formado o no sale
        if datos.get("documento") != documento:
            raise ValueError(f"El archivo dice ser «{datos.get('documento')}» y se transmite como «{documento}».")
        return f"STA-SIM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
