"""
services/geo_restrictions.py — Restriccion de jurisdicciones (cumplimiento NOWPayments / AML).

OBJETIVO
    NOWPayments (FD Transfers LLC) NO presta servicio a residentes o ciudadanos de
    EE.UU., la Union Europea y Reino Unido (Terms of Service, seccion 15.1).
    Este modulo ayuda a bloquear el PAGO/RECARGA en cripto desde esas jurisdicciones.

ESTADO
    Modulo aislado. Se conecta al endpoint de recarga cripto cuando se integre NOWPayments.
    No cambia el comportamiento actual de la app.

IMPORTANTE (residencia vs nacionalidad)
    La deteccion por IP solo indica DESDE DONDE se conecta el usuario (residencia aproximada),
    NO su nacionalidad. Un ciudadano de EE.UU. conectado desde otro pais pasaria este filtro.
    Por eso el bloqueo por IP es SOLO la primera capa; debe complementarse con:
      - una DECLARACION explicita del usuario (no soy residente ni ciudadano de EE.UU./UE/UK), y
      - el pais/nacionalidad verificado en el KYC (capa mas fuerte).
"""

from fastapi import Request, HTTPException

# Codigos ISO-3166 alpha-2 de paises restringidos por el ToS de NOWPayments.
# EE.UU. + Reino Unido + los 27 de la Union Europea.
US_UK = {"US", "GB"}
EU_27 = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
}
RESTRICTED_COUNTRIES = US_UK | EU_27


def get_ip_country(request: Request) -> str | None:
    """Devuelve el codigo de pais (ISO alpha-2) de la IP del visitante, via Cloudflare.
    Devuelve None si no se puede determinar (no asumir que es seguro si es None)."""
    if request is None:
        return None
    country = request.headers.get("cf-ipcountry")
    if not country:
        return None
    country = country.strip().upper()
    # Cloudflare usa "XX" o "T1" para casos desconocidos/Tor
    if country in ("XX", "T1", ""):
        return None
    return country


def is_restricted_ip(request: Request) -> bool:
    """True si la IP del visitante pertenece a una jurisdiccion restringida."""
    country = get_ip_country(request)
    if country is None:
        return False  # no bloqueamos por IP desconocida; la declaracion + KYC son el respaldo
    return country in RESTRICTED_COUNTRIES


def assert_payment_allowed(request: Request, declared_not_restricted: bool = False) -> None:
    """Guardia para el endpoint de recarga en cripto.
    Lanza HTTP 403 si:
      - la IP proviene de una jurisdiccion restringida, o
      - el usuario NO declaro que reside/es ciudadano fuera de EE.UU./UE/UK.
    declared_not_restricted debe venir del checkbox de declaracion del usuario.
    """
    if is_restricted_ip(request):
        country = get_ip_country(request)
        raise HTTPException(
            status_code=403,
            detail=(
                "Las recargas en cripto no estan disponibles en tu jurisdiccion "
                f"({country}) por politicas de nuestro proveedor de pagos."
            ),
        )
    if not declared_not_restricted:
        raise HTTPException(
            status_code=400,
            detail=(
                "Debes confirmar que no eres residente ni ciudadano de "
                "Estados Unidos, la Union Europea o el Reino Unido para recargar en cripto."
            ),
        )
