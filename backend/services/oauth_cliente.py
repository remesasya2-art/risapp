"""
Cliente OAuth 2.0 (client credentials) para hablar con APIs de terceros.

QUE RESUELVE, Y POR QUE NO ES «PEDIR UN TOKEN»

    Pedir el token es la parte fácil. Lo que se rompe en producción es todo lo
    de alrededor, y cada cosa de acá abajo está por un modo de falla concreto:

    1. **El token vence a mitad de vuelo.** Uno válido «por dos segundos más»
       no es válido: entre que se decide usarlo y llega al otro lado, venció.
       Se renueva con un margen (`MARGEN_SEGUNDOS`) antes del vencimiento.

    2. **El arranque pide veinte tokens a la vez.** Sin candado, veinte
       peticiones simultáneas ven el token vacío y piden veinte. Algunos
       proveedores lo cobran, otros lo bloquean por abuso. Un `asyncio.Lock`,
       y quien lo consigue segundo se encuentra el token ya puesto.

    3. **Reintentar con credenciales malas no arregla nada.** Un 401 del
       endpoint de token es un secreto equivocado: reintentar es golpear la
       puerta más fuerte. Se levanta enseguida. Un 5xx o un corte de red sí se
       reintenta, con espera creciente.

    4. **El token se revoca antes de vencer.** Una llamada puede volver 401
       aunque el token «no venció». Se renueva y se reintenta UNA vez. Una
       sola: reintentar en bucle contra un 401 permanente es un bucle
       infinito con credenciales.

DONDE VIVE EL TOKEN

    En memoria, en la instancia del cliente. No en Mongo: es efímero, y
    guardarlo en la base convierte cualquier lectura de la base —un backup,
    un dump, un empleado con acceso— en una credencial viva del proveedor.

QUE NUNCA SE ESCRIBE EN EL LOG

    Ni el `client_secret` ni el token. `Credenciales.__repr__` los tapa, para
    que un `logger.error("... %s", credenciales)` escrito con prisa no los
    filtre.

LO QUE ESTE MODULO NO SABE

    Nada de ningún proveedor en particular. Los nombres de los campos del
    token (`access_token`, `expires_in`) son los del RFC 6749; el nombre de la
    cabecera de idempotencia se configura, porque cada proveedor usa el suyo y
    inventarlo sería adivinar.
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Cuánto antes del vencimiento se considera vencido. Un token que vale dos
# segundos más no vale: entre que se decide usarlo y llega al otro lado, venció.
MARGEN_SEGUNDOS = 60

# Si el proveedor no dice cuánto dura, se asume poco. Asumir mucho significa
# usar un token muerto durante horas y no entender por qué todo devuelve 401.
DURACION_POR_DEFECTO = 300

# Los métodos que pueden repetirse sin repetir el efecto. A los otros se les
# manda llave de idempotencia.
SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

REINTENTOS = 3
ESPERA_BASE = 0.5


class ErrorDeCredenciales(Exception):
    """El proveedor rechazó las credenciales. No se reintenta: un secreto
    equivocado no se arregla insistiendo."""


class NoSePudoAutenticar(Exception):
    """No se pudo obtener el token por una falla temporal, después de
    reintentar."""


@dataclass
class Credenciales:
    token_url: str
    client_id: str
    client_secret: str = field(repr=False)
    scope: Optional[str] = None
    # Cada proveedor nombra su cabecera de idempotencia distinto. Se configura
    # en vez de adivinarse: mandar la llave con el nombre equivocado es lo
    # mismo que no mandarla, y no falla — deja pasar el duplicado.
    cabecera_idempotencia: str = "Idempotency-Key"
    # El `repr=False` de arriba es lo único que tapa el secreto, y por eso es
    # lo único que hay: antes había además un `__repr__` propio que hacía lo
    # mismo. Con los dos puestos, ninguna prueba podía distinguir cuál
    # protegía de verdad — sacar uno no rompía nada. Dos mecanismos para una
    # garantía es el que se termina borrando por «redundante».


class ClienteOAuth:
    """Un cliente autenticado contra un proveedor. Una instancia por proveedor.

    No es seguro compartir una instancia entre proveedores distintos: el token
    cacheado es de uno solo.
    """

    def __init__(self, credenciales: Credenciales, *, timeout: float = 30.0,
                 cliente_http: Optional[httpx.AsyncClient] = None):
        self.credenciales = credenciales
        self._timeout = timeout
        # Inyectable para los tests. En producción se crea uno por llamada:
        # sostener un cliente abierto entre peticiones esporádicas deja
        # conexiones colgadas cuando el proceso se reinicia.
        self._cliente_http = cliente_http
        self._token: Optional[str] = None
        self._vence_en: float = 0.0
        self._candado = asyncio.Lock()

    # ─── El token ─────────────────────────────────────────────────────────

    def _vigente(self) -> bool:
        return bool(self._token) and time.monotonic() < self._vence_en - MARGEN_SEGUNDOS

    async def token(self, *, forzar: bool = False) -> str:
        """El token de acceso, pidiéndolo o renovándolo si hace falta."""
        if not forzar and self._vigente():
            return self._token

        async with self._candado:
            # Se vuelve a mirar adentro del candado: mientras se esperaba, otro
            # pudo haberlo renovado. Sin esto el candado sólo serializa las
            # peticiones en vez de evitarlas.
            if not forzar and self._vigente():
                return self._token
            await self._pedir_token()
            return self._token

    async def _pedir_token(self) -> None:
        cuerpo = {
            "grant_type": "client_credentials",
            "client_id": self.credenciales.client_id,
            "client_secret": self.credenciales.client_secret,
        }
        if self.credenciales.scope:
            cuerpo["scope"] = self.credenciales.scope

        ultimo = None
        for intento in range(REINTENTOS):
            try:
                async with self._http() as http:
                    r = await http.post(self.credenciales.token_url, data=cuerpo)
            except httpx.HTTPError as e:
                ultimo = e
                logger.warning("OAuth: no se pudo pedir el token (intento %d): %s",
                               intento + 1, e)
                await asyncio.sleep(ESPERA_BASE * (2 ** intento))
                continue

            if r.status_code in (400, 401, 403):
                # Credenciales o scope mal: reintentar es golpear más fuerte.
                # El cuerpo se recorta y se registra porque suele decir cuál de
                # los dos está mal, y no trae el secreto.
                logger.error("OAuth: el proveedor rechazó las credenciales (%s): %s",
                             r.status_code, r.text[:300])
                raise ErrorDeCredenciales(
                    f"El proveedor rechazó las credenciales ({r.status_code}).")

            if r.status_code >= 500:
                ultimo = httpx.HTTPStatusError(f"{r.status_code}", request=r.request,
                                               response=r)
                logger.warning("OAuth: el proveedor devolvió %s pidiendo el token",
                               r.status_code)
                await asyncio.sleep(ESPERA_BASE * (2 ** intento))
                continue

            datos = r.json()
            token = datos.get("access_token")
            if not token:
                raise NoSePudoAutenticar(
                    "El proveedor respondió sin access_token.")

            try:
                dura = int(datos.get("expires_in") or DURACION_POR_DEFECTO)
            except (TypeError, ValueError):
                dura = DURACION_POR_DEFECTO

            self._token = token
            # `monotonic` y no `time()`: un ajuste del reloj del sistema no
            # puede hacer que un token vivo parezca vencido, ni al revés.
            self._vence_en = time.monotonic() + dura
            logger.info("OAuth: token renovado, vale %d s", dura)
            return

        raise NoSePudoAutenticar(
            f"No se pudo obtener el token después de {REINTENTOS} intentos: {ultimo}")

    # ─── Las llamadas ─────────────────────────────────────────────────────

    def _http(self) -> httpx.AsyncClient:
        if self._cliente_http is not None:
            return _SinCerrar(self._cliente_http)
        return httpx.AsyncClient(timeout=self._timeout)

    async def pedir(self, metodo: str, url: str, *,
                    idempotency_key: Optional[str] = None,
                    **kwargs) -> httpx.Response:
        """Una llamada autenticada.

        A los métodos que no son seguros les pone llave de idempotencia: si la
        respuesta se pierde y se reintenta, el proveedor tiene que reconocer
        que es el mismo pedido y no cobrarlo dos veces. Se genera una si no se
        pasó, pero conviene pasarla: la generada acá cambia en cada llamada, y
        entonces un reintento del llamador es un pedido nuevo.
        """
        metodo = metodo.upper()
        cabeceras = dict(kwargs.pop("headers", None) or {})
        cabeceras["Authorization"] = f"Bearer {await self.token()}"

        if metodo not in SEGUROS:
            clave = idempotency_key or uuid.uuid4().hex
            cabeceras.setdefault(self.credenciales.cabecera_idempotencia, clave)

        async with self._http() as http:
            r = await http.request(metodo, url, headers=cabeceras, **kwargs)

            # Un 401 con un token que creíamos vigente = lo revocaron. Se
            # renueva y se reintenta UNA vez. Una sola: contra un 401
            # permanente, reintentar en bucle es un bucle infinito con
            # credenciales adentro.
            if r.status_code == 401:
                logger.info("OAuth: 401 con token vigente; se renueva y se reintenta")
                cabeceras["Authorization"] = f"Bearer {await self.token(forzar=True)}"
                r = await http.request(metodo, url, headers=cabeceras, **kwargs)

        return r


class _SinCerrar:
    """Envuelve un cliente inyectado para que el `async with` no lo cierre.

    Sin esto, la primera llamada cierra el cliente del test y la segunda
    revienta con «client has been closed» — que se lee como un error del
    código y es un error del andamiaje.
    """

    def __init__(self, cliente):
        self._cliente = cliente

    async def __aenter__(self):
        return self._cliente

    async def __aexit__(self, *a):
        return False
