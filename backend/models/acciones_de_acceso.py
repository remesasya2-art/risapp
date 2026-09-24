"""
models/acciones_de_acceso.py — Lo que contestan las puertas de entrada a la
cuenta: registrarse, confirmar el correo, entrar con contraseña, con Google,
con el segundo factor o con la huella, y activar una cuenta del personal.

Tercera tanda de los contratos de salida de las acciones (la primera, lo que
mueve plata, en `models/acciones_de_dinero.py`, con el porqué completo).

POR QUE ESTAS

    Son las rutas que leen el documento ENTERO del usuario: para dejar pasar
    necesitan la contraseña, la semilla del segundo factor o la clave de la
    huella. Y en su historia ya dejaron salir de más: cinco listas de lo
    PROHIBIDO, una por puerta y todas distintas, que dejaban pasar el hash del
    PIN y las credenciales de la huella (ver `services/perfil.py`).

    Hoy todas recortan con `para_su_dueno`, que es una lista de lo permitido.
    El contrato es la segunda capa, y el campo `user` usa el MISMO contrato
    que `/auth/me` —generado de la misma lista—: una puerta que un día
    devuelva el documento crudo sigue sacando sólo lo que el dueño ve en su
    perfil.

UNA RESPUESTA DE ENTRADA PARA TODAS LAS PUERTAS

    Las puertas contestan lo mismo de tres formas: con la sesión, pidiendo el
    código del segundo factor, o pidiendo que lo configure. La pantalla de
    entrada decide qué hacer mirando qué claves vinieron, y es una sola para
    todas. Un contrato por puerta sería cinco copias de la misma lista, que es
    justo cómo empezaron las cinco listas de lo prohibido.

Un test (`tests/test_contratos_de_acceso.py`) compara las claves que devuelve
cada ruta, leídas del código, con su contrato.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.cuenta import PerfilDelDueno
from models.escalar import Escalar


def _simple(nombre, campos):
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


class MiEntrada(BaseModel):
    message: Escalar = None
    # Con la sesión abierta. `session_token` va también en la cookie; en el
    # cuerpo lo usa la aplicación móvil, que no guarda cookies.
    session_token: Escalar = None
    user: Optional[PerfilDelDueno] = None
    must_change_password: Escalar = None
    # Todavía no: falta el segundo factor, o configurarlo. `pending_token`
    # sirve sólo para ese paso, no para operar.
    two_factor_required: Escalar = None
    two_factor_enrollment_required: Escalar = None
    pending_token: Escalar = None
    email: Escalar = None
    user_id: Escalar = None
    # Google, con un correo que todavía no tiene cuenta: falta el CPF.
    registro_incompleto: Escalar = None
    nombre: Escalar = None


class MiEntradaConDosPasos(MiEntrada):
    """La entrada que pasa por el segundo factor: además de la sesión, lo de
    los códigos de respaldo. `backup_codes` son los códigos EN CLARO, y salen
    una sola vez, al configurarlo: después sólo se guarda su hash."""
    backup_codes: Optional[List[Escalar]] = None
    important: Escalar = None
    used_backup_code: Escalar = None
    backup_codes_remaining: Escalar = None


# La semilla del segundo factor sale UNA vez, a su dueño, mientras lo
# configura: es lo que lee la aplicación de códigos. Después no vuelve a salir
# por ningún lado.
MiAltaDeDosPasos = _simple("MiAltaDeDosPasos", (
    "secret", "otpauth_url", "qr_code_data_url", "issuer", "account"))

MiRegistroEmpezado = _simple("MiRegistroEmpezado", (
    "message", "email", "email_sent", "code_expires_in_minutes"))
MiCodigoReenviado = _simple("MiCodigoReenviado", ("message", "email_sent"))
MiInvitacion = _simple("MiInvitacion", ("valido", "email", "nombre", "cargo"))
MiMensaje = _simple("MiMensaje", ("message",))
MiLatido = _simple("MiLatido", ("status",))
