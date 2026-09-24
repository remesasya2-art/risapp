"""
models/acciones_de_seguridad.py — Lo que contestan las acciones con las que el
cliente cuida su cuenta: la contraseña, el segundo factor, el PIN, la huella,
la recuperación de la cuenta y el aviso del celular.

Cuarta tanda de los contratos de salida de las acciones (la primera, con el
porqué completo, en `models/acciones_de_dinero.py`; la de las puertas de
entrada, en `models/acciones_de_acceso.py`).

POR QUE ESTAS

    Tocan justo lo que no puede salir: la contraseña, la semilla del segundo
    factor, el hash del PIN, la clave de la huella. Hoy todas contestan campo
    por campo, así que en pantalla no cambia nada. El contrato es la segunda
    capa, para el día que una de ellas conteste con el documento que acaba de
    leer.

    Y la recuperación de la cuenta se usa SIN sesión: la contesta el servidor
    a cualquiera que escriba un correo y un CPF. Ahí más que en ningún lado,
    lo que sale tiene que estar escrito.

Un test (`tests/test_contratos_de_seguridad.py`) compara las claves que
devuelve cada ruta, leídas del código, con su contrato.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos):
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


# ── Contraseña ────────────────────────────────────────────────────────────

# El correo sale ENMASCARADO: la pantalla dice «te mandamos el código a
# a•••@ejemplo.com». Con sesión o sin ella, el correo entero no hace falta.
MiCodigoDeCambioPedido = _simple("MiCodigoDeCambioPedido", ("success", "email_enmascarado", "minutos"))
MiClaveCambiada = _simple("MiClaveCambiada", ("message", "sesiones_cerradas"))


# ── Segundo factor, con la sesión abierta ─────────────────────────────────

class MisCodigosDeRespaldo(BaseModel):
    """Los códigos de respaldo EN CLARO. Salen una sola vez, al activarlo o al
    pedir unos nuevos: después sólo se guarda su hash."""
    message: Escalar = None
    backup_codes: Optional[List[Escalar]] = None
    important: Escalar = None


# ── PIN, huella y avisos ──────────────────────────────────────────────────

MiResultado = _simple("MiResultado", ("success", "message"))
# `hint` es sí o no: si mostrar la sugerencia de configurar un PIN. No es una
# pista del PIN.
MiSugerenciaDePin = _simple("MiSugerenciaDePin", ("hint", "message"))


# ── Recuperar la cuenta (sin sesión) ──────────────────────────────────────

MiIdentidadComprobada = _simple("MiIdentidadComprobada", ("success", "message", "email_masked"))
# `recovery_token` sirve sólo para el paso siguiente —poner la contraseña
# nueva— y vence solo. Es la única credencial que sale de estas rutas.
MiCodigoDeRecuperacionComprobado = _simple("MiCodigoDeRecuperacionComprobado", (
    "success", "message", "recovery_token"))
MiPedidoDeAyuda = _simple("MiPedidoDeAyuda", ("success", "message", "ticket_id"))
