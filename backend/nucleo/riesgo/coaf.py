"""
La comunicación al COAF: el archivo y el puerto por el que se manda.

EL ARCHIVO

    El SISCOAF recibe comunicaciones con un conjunto de campos fijo: quién
    comunica, quiénes están involucrados (nombre, CPF, ocupación), qué
    operaciones (fecha, valor, tipo), con qué indicio (el enquadramento del
    catálogo de la Carta Circular 4.001/2020) y una descripción. Acá se
    arma ese conjunto, en JSON canónico. El formato final de transmisión
    (XML del SISCOAF) lo pone el adaptador real cuando exista la
    credencial; los datos son los mismos.

    Una comunicación de NO OCURRENCIA es el aviso anual de que no hubo
    nada que comunicar. Es la que todos se olvidan, y el sistema la pide.

EL PUERTO

    `Comunicador.enviar` devuelve el acuse. El simulador devuelve uno con
    forma de protocolo y lo deja anotado; nada sale de la máquina.
"""
import json
import secrets
from datetime import datetime, timezone

COMUNICACION, NO_OCURRENCIA = "comunicacion", "no_ocurrencia"

# Los indicios del catálogo de la Carta Circular 4.001, los que estas reglas
# pueden citar. El código es el del catálogo; el texto, la explicación.
INDICIOS = {
    "umbral_operacion": ("I-2.a", "Operación de valor incompatible con la ocupación o la renta declarada"),
    "acumulado_30_dias": ("I-2.b", "Movimiento acumulado incompatible con el perfil en el mes"),
    "acumulado_12_meses": ("I-2.c", "Movimiento acumulado incompatible con el perfil en el año"),
    "fraccionamiento": ("I-2.d", "Fraccionamiento para evitar los umbrales"),
    "velocidad": ("I-2.e", "Ráfaga de operaciones en corto tiempo"),
    "contraparte_repetida": ("I-2.f", "Contraparte repetida sin relación aparente"),
    "horario": ("I-2.g", "Operaciones en horario inusual"),
    "lista": ("I-1.a", "Persona que consta en lista de sanciones"),
    "manual": ("I-9.z", "Indicio apreciado por el analista"),
}

COMUNICANTE = {"tipo": "instituicao_de_pagamento", "ispb": "99999999", "cnpj": "00000000000000",
               "nombre": "RIS Instituição de Pagamento (laboratorio)"}


def _canonico(datos: dict) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=1, default=str)


def armar_comunicacion(*, caso: dict, titular: dict, alertas: list, operaciones: list, conclusion: str) -> str:
    """El archivo de una comunicación, con los campos del SISCOAF."""
    indicios = []
    for a in alertas:
        codigo, texto = INDICIOS.get(a["regla"], INDICIOS["manual"])
        if codigo not in [i["codigo"] for i in indicios]:
            indicios.append({"codigo": codigo, "descripcion": texto})
    if not indicios:
        codigo, texto = INDICIOS["lista" if caso.get("origen") == "lista" else "manual"]
        indicios.append({"codigo": codigo, "descripcion": texto})
    return _canonico({
        "tipo": COMUNICACION,
        "comunicante": COMUNICANTE,
        "caso": caso["id"],
        "fecha": datetime.now(timezone.utc).date().isoformat(),
        "envolvidos": [{"nombre": titular["nombre"], "documento": titular["documento"],
                        "ocupacion": titular.get("ocupacion"), "pep": titular.get("pep", False),
                        "nivel_de_riesgo": titular.get("nivel_de_riesgo")}],
        "operacoes": [{"id": o["id"], "fecha": (o.get("creada") or "")[:10], "valor": o["monto"],
                       "tipo": f"pix_{o['direccion']}", "end_to_end": o.get("end_to_end")} for o in operaciones],
        "indicios": indicios,
        "descripcion": conclusion,
    })


def armar_no_ocurrencia(*, anio: int) -> str:
    return _canonico({"tipo": NO_OCURRENCIA, "comunicante": COMUNICANTE, "periodo": anio,
                      "declaracion": "No hubo operaciones o situaciones pasibles de comunicación en el período."})


class SimuladorSiscoaf:
    nombre = "simulador-siscoaf"

    async def enviar(self, sesion, *, archivo: str, tipo: str) -> str:
        json.loads(archivo)                              # tiene que ser un archivo bien formado
        return f"SISCOAF-SIM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
