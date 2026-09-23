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


# ══════════════════════════════════════════════════════════════════════════
# 2. El perfil, y la seguridad de la cuenta
# ══════════════════════════════════════════════════════════════════════════

def _perfil_del_dueno():
    """El contrato de `/auth/me`, GENERADO de la lista de lo permitido de
    `services/perfil.py`, que es la misma que usa la proyección.

    No se escribe a mano a propósito. Dos listas de los mismos campos —la de
    la proyección y la del modelo— terminan distintas, y cuando pasa el campo
    se pierde en silencio: la ruta contesta 200 y la pantalla queda con un
    hueco. Generado, agregar un campo a la lista lo agrega a los dos.

    Todos los campos son `Any`: los saldos salen como número, el bono como un
    objeto, las fechas como fecha. El contrato decide QUE sale, no de qué tipo
    —eso lo hace `perfil.terminar_de_armar`, que ya estaba—."""
    from services.perfil import LO_PERMITIDO
    return create_model("PerfilDelDueno", **{c: (Optional[Any], None) for c in sorted(LO_PERMITIDO)})


PerfilDelDueno = _perfil_del_dueno()


class EstadoDeLaClave(BaseModel):
    password_set: Optional[bool] = None
    must_change_password: Optional[bool] = None


class EstadoDeDosPasos(BaseModel):
    enabled: bool
    role: Optional[str] = None
    is_required: bool
    backup_codes_remaining: int


class EstadoDelPin(BaseModel):
    has_pin: bool
    must_reset: bool
    locked: bool
    locked_seconds: int
    is_super_admin: bool
