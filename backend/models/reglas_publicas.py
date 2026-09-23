"""
models/reglas_publicas.py — Los contratos de salida de las rutas livianas: la
tasa, los límites, los primeros pasos, los avisos al celular, la configuración
del botón de Google y la raíz de la API.

Todas ya armaban la respuesta a mano: en pantalla no cambia nada. El contrato
es la segunda capa, y la que más lo necesita es `/rate`, que no pide sesión y
la consulta cada visitante: arma su respuesta con `apply_rate_adjustment`, que
copia el diccionario de configuración que le pasen. Un campo nuevo en la
configuración de la tasa automática saldría solo para cualquiera.

Los tests (`tests/test_contratos_livianos.py`) comparan, con datos reales, las
claves que arma cada ruta con las que salen por su contrato: el contrato que se
come un campo deja la pantalla con un hueco y no avisa.
"""
from typing import Any, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos):
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


RaizDeLaApi = _simple("RaizDeLaApi", ("message", "version"))

# Sin `base_ris_to_ves` ni `base_ves_to_ris_rate`, a propósito: son la tasa
# ANTES del ajuste fuera de horario, y en esta ruta pública le decían a
# cualquiera cuánto se le suma de noche. El panel las lee de
# `GET /admin/auto-rate` (ver `ConfigDeTasaAutomatica`).
LaTasa = _simple("LaTasa", (
    "ris_to_ves", "ves_to_ris_rate", "brl_to_ris", "usd_to_ves",
    "is_off_hours", "auto_rate_enabled", "updated_at",
    "usdtris_to_ves", "usdcris_to_ves",
    "bcv_usd_ves", "bcv_eur_ves", "bcv_value_date", "bcv_vencida", "bcv_edad_horas",
))


class LosLimites(BaseModel):
    # Cada grupo es un diccionario chico de topes públicos (`services/limits.py`):
    # van como están, porque son reglas y no datos de nadie.
    pix: Optional[Any] = None
    tarjeta: Optional[Any] = None
    ves: Optional[Any] = None
    sin_verificar: Optional[Any] = None
    cripto: Optional[Any] = None
    pago_al_final: Escalar = None
    recarga: Escalar = None
    encomiendas: Escalar = None


MiCupoSinVerificar = _simple("MiCupoSinVerificar", (
    "aplica", "verificado", "max_ris", "max_ops", "ris_usados", "ops_usadas",
    "ris_restantes", "ops_restantes", "agotado"))


class MisLimites(LosLimites):
    cupo_kyc: Optional[MiCupoSinVerificar] = None


MisPrimerosPasos = _simple("MisPrimerosPasos", (
    "verificacion", "recarga", "envio", "huella", "completo"))

EstadoDeMisAvisosAlCelular = _simple("EstadoDeMisAvisosAlCelular", ("subscribed", "endpoint"))

ClavePublicaDeAvisos = _simple("ClavePublicaDeAvisos", ("public_key",))

ConfigDelBotonDeGoogle = _simple("ConfigDelBotonDeGoogle", ("client_id",))
