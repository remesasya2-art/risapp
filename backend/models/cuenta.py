"""
models/cuenta.py — Los contratos de salida de lo que una persona ve de su
propia cuenta.

QUE ES UN CONTRATO DE SALIDA, Y POR QUE ACA

    El `response_model` de FastAPI recorta la respuesta a los campos que
    declara: un campo que no está en el modelo no sale, aunque la función lo
    devuelva. Es una lista de lo permitido que vive al lado del nombre de la
    ruta y no se puede olvidar (ver tests/test_contrato_de_salida.py).

    Estas rutas son las primeras porque devuelven datos de la persona. La que
    abrió la tanda, `/verification/status`, devolvía el documento entero de la
    verificación con una lista de lo prohibido que sólo sacaba el `_id`: la
    nota interna que el agente escribió sobre el cliente, su nivel de riesgo
    de prevención de lavado y el nombre de quien lo revisó le llegaban al
    propio cliente. Avisarle a alguien que está bajo sospecha es justamente
    lo que esas normas prohíben.

LOS TIPOS SON LOS DE LA RESPUESTA DE HOY, NO LOS IDEALES

    Cada modelo copia lo que la ruta ya devolvía, con el mismo nombre y la
    misma forma. Poner un contrato no es el momento de cambiar un número por
    un texto: eso rompe una pantalla, y el contrato tiene que poder ponerse
    sin que nadie lo note. Donde la forma varía (fechas que en unos
    documentos son fecha y en otros texto), el campo es `Any`.
"""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, create_model


# ══════════════════════════════════════════════════════════════════════════
# 1. La verificación de identidad, vista por su dueño
# ══════════════════════════════════════════════════════════════════════════

# Lo único que el cliente necesita saber de su propia verificación: en qué
# estado está y desde cuándo. NUNCA lo que escribió el equipo (nota interna,
# nivel de riesgo, quién la procesó) ni sus fotos, que ya mandó él y no hace
# falta devolverle.
LO_QUE_VE_DE_SU_VERIFICACION = {
    "_id": 0, "status": 1, "submitted_at": 1, "verified_at": 1, "document_type": 1,
}


class EstadoDeMiVerificacion(BaseModel):
    status: str
    submitted_at: Optional[Any] = None
    verified_at: Optional[Any] = None
    document_type: Optional[str] = None
