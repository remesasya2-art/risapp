"""
services/cadena_tls.py — Completar una cadena de certificados incompleta,
igual que hace el navegador.

EL PROBLEMA, CON EL ERROR TEXTUAL

    El sitio del Banco Central de Venezuela dejó de poder consultarse:

        [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
        unable to get local issuer certificate

    Y NO es que el certificado del BCV sea falso ni esté vencido. Se lo emitió
    Sectigo, una autoridad comercial común, cuya raíz ya viene en el paquete de
    certificados que usa Python. Lo que pasa es que una cadena tiene tres
    eslabones —la raíz, una pieza intermedia, y el certificado del sitio— y el
    servidor del BCV manda sólo el último. Falta la pieza del medio.

    Chrome entra sin quejarse porque hace algo que Python no hace nunca: lee
    adentro del certificado la dirección de dónde bajar la pieza que falta, la
    baja, y sigue. Eso es lo que hace este módulo.

POR QUE NO SE PEGO LA PIEZA ADENTRO DEL REPOSITORIO

    Era el plan inicial y se descartó por un motivo concreto: las piezas
    intermedias CADUCAN, y las autoridades las rotan. La de Sectigo que hoy
    hace falta vence en noviembre de 2026. El día que la cambien, la tasa se
    rompe otra vez exactamente igual que hoy, y arreglarlo vuelve a requerir
    que una persona exporte un certificado a mano.

    Buscarla sola no caduca.

LAS TRES COSAS QUE HACEN QUE ESTO NO SEA UN AGUJERO

    Bajar un certificado de una dirección que viene escrita adentro de un
    certificado que TODAVIA NO SE PUDO VERIFICAR es, dicho así, exactamente la
    forma de comerse uno falso. Por eso:

    1. LA VERIFICACION NO SE APAGA EN NINGUN MOMENTO. Ni un instante, ni «sólo
       para mirar». Para leer lo que ofrece el servidor se usa `pyOpenSSL` con
       la verificación ENCENDIDA y un mirón que RECHAZA SIEMPRE: el saludo TLS
       falla igual, no se establece ninguna sesión de confianza, y lo único que
       queda en la mano es el papel que el servidor mostró. Por eso
       `tests/test_tls_verificado.py` sigue pasando sin excepciones: acá no hay
       un `verify=False` escondido en ninguna parte.

    2. LA PIEZA BAJADA SE VERIFICA ANTES DE USARLA. Se comprueba, sin salir a
       la red, que con ella la cadena del sitio CIERRA contra una raíz del
       depósito público. Si no cierra, se descarta y la consulta sigue
       fallando. Un atacante tendría que conseguir la firma de Sectigo, y eso
       no se falsifica.

       Y ACA VA LA PARTE QUE IMPORTA ENTENDER, porque es contraintuitiva:

         Se comprobó a mano que OpenSSL, con sus banderas por omisión, NO
         trata como raíz de confianza a un certificado del depósito que no sea
         autofirmado — así que incluso sin esta verificación una pieza falsa
         quedaría rechazada. O sea que este paso es, hoy, redundante.

         Se deja igual, y no por ceremonia: sin él, la seguridad de todo esto
         dependería de una bandera por omisión de OpenSSL
         (`VERIFY_X509_PARTIAL_CHAIN` apagada) que nadie de este proyecto
         controla. Y además hay una diferencia observable, que es lo que la
         prueba por mutación agarra: sin la verificación, una pieza falsa se
         GUARDA en la memoria del proceso y se reusa en cada consulta, y la
         verdadera no se busca nunca más hasta que se reinicie el servidor.
         Eso no es un agujero, pero sí es la tasa congelada volviendo por otra
         puerta.

    3. LA DIRECCION DE DONDE SE BAJA ESTA ACOTADA. Sólo `http` y `https`
       —`file://` leería un archivo del servidor—, nada que resuelva a una
       dirección interna, sin seguir redirecciones, con un tope de tamaño y un
       tope de saltos.

       El umbral de paranoia es el que corresponde: para que alguien llegue a
       poner una dirección acá tendría que estar YA interponiéndose en la
       conexión al BCV. Quien puede hacer eso tiene opciones peores. Pero una
       petición a ciegas contra un servicio interno es gratis de evitar.

LO QUE ESTE MODULO NO HACE

    No guarda nada en disco. La pieza vive en la memoria del proceso y se
    vuelve a buscar cuando el servidor arranca. Es un dato público que se baja
    en medio segundo; un archivo en disco sería una copia más que puede quedar
    vieja.
"""
import asyncio
import ipaddress
import logging
import pathlib
import select
import socket
import ssl
import time
import warnings
from urllib.parse import urlsplit

import certifi
import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import AuthorityInformationAccessOID, NameOID
from OpenSSL import SSL, crypto

logger = logging.getLogger(__name__)

# Una pieza intermedia pesa uno o dos kilobytes. El tope es para que una
# dirección que devuelve un archivo enorme no se lleve la memoria del proceso.
MAXIMO_DE_LA_PIEZA = 64 * 1024

# Cuántos eslabones se persiguen hacia arriba. Con dos ya se cubre el caso
# normal (falta una pieza) y el raro (faltan dos). El tope es lo que evita que
# una cadena armada para dar vueltas nos haga bajar certificados para siempre.
MAXIMO_DE_SALTOS = 4

ESQUEMAS_PERMITIDOS = ("http", "https")

SEGUNDOS = 15


class NoSePudoCompletar(Exception):
    """No se consiguió la pieza que falta, o la que se consiguió no cierra la
    cadena. El llamador tiene que seguir fallando: es el punto de todo esto."""


# ══════════════════════════════════════════════════════════════════════════
# El depósito de raíces públicas
# ══════════════════════════════════════════════════════════════════════════

def archivo_de_raices() -> str:
    """El archivo con las raíces públicas de confianza.

    Está en una función, y no escrito en los tres lugares que lo necesitan, por
    dos motivos: que el depósito se decida en UN solo punto, y que las pruebas
    puedan poner el suyo. Sin ese segundo motivo no habría forma de probar nada
    de este módulo sin salir a internet y sin depender de que el BCV tenga hoy
    la cadena rota.
    """
    return certifi.where()


_DEPOSITOS = {}


def _raices():
    """Las raíces de `certifi`, que son las mismas que usa `httpx`.

    Se arman una vez por archivo: son unas ciento cuarenta, y parsearlas en
    cada consulta sería tirar trabajo a la basura.
    """
    ruta = archivo_de_raices()
    if ruta in _DEPOSITOS:
        return _DEPOSITOS[ruta]

    crudo = pathlib.Path(ruta).read_bytes()
    raices = []
    for trozo in crudo.split(b"-----END CERTIFICATE-----"):
        if b"BEGIN CERTIFICATE" not in trozo:
            continue
        with warnings.catch_warnings():
            # Alguna raíz de `certifi` tiene un número de serie que la norma no
            # permite, y `cryptography` avisa. Es un problema de esa raíz, no
            # nuestro, y no puede impedir armar el depósito entero.
            warnings.simplefilter("ignore")
            try:
                raices.append(x509.load_pem_x509_certificate(
                    trozo + b"-----END CERTIFICATE-----\n"))
            except Exception:
                continue
    _DEPOSITOS[ruta] = raices
    return _DEPOSITOS[ruta]


# ══════════════════════════════════════════════════════════════════════════
# 1. Mirar lo que ofrece el servidor, sin confiar en nada
# ══════════════════════════════════════════════════════════════════════════

def _rechazar_siempre(conexion, certificado, codigo, profundidad, aprobado):
    """El mirón. Devuelve `False` SIEMPRE, para cualquier certificado.

    Es lo que hace que esto no sea una conexión sin verificar: la verificación
    está encendida (`VERIFY_PEER`) y encima este mirón rechaza todo, así que el
    saludo TLS termina en error pase lo que pase. No se manda ni se recibe un
    solo byte de datos por esta conexión; lo único que queda es la copia del
    certificado que el servidor mostró, que es un papel público.

    NO CAMBIAR ESTO POR `return aprobado`. Sería una conexión de verdad, y
    entonces sí habría un camino donde se confía en algo que no se verificó.
    """
    return False


def _lo_que_ofrece(host: str, puerto: int, segundos: int) -> list:
    """Los certificados que el servidor manda, en DER, sin confiar en ninguno.

    Bloquea: hay que llamarla en un hilo.
    """
    contexto = SSL.Context(SSL.TLS_CLIENT_METHOD)
    contexto.load_verify_locations(archivo_de_raices())
    contexto.set_verify(SSL.VERIFY_PEER, _rechazar_siempre)

    cruda = socket.create_connection((host, puerto), timeout=segundos)
    try:
        conexion = SSL.Connection(contexto, cruda)
        # Sin esto el servidor no sabe qué sitio se le pide y manda el
        # certificado equivocado: el BCV comparte dirección con otros nombres.
        conexion.set_tlsext_host_name(host.encode("idna"))
        conexion.set_connect_state()

        # POR QUE ESTO ES UN BUCLE Y NO UN `do_handshake()` A SECAS
        #
        #   Un zócalo con plazo (`timeout=`) queda en modo no bloqueante por
        #   dentro, y entonces OpenSSL no espera: corta con «quiero leer más» en
        #   cuanto se le acaban los bytes. La primera versión de esto llamaba
        #   una sola vez, se comía ese aviso como si fuera el rechazo esperado,
        #   y se iba con la cadena VACIA — o sea que el arreglo entero no hacía
        #   nada, y en silencio.
        #
        #   La alternativa era un zócalo sin plazo, pero un servidor que abre y
        #   no contesta colgaría el hilo para siempre.
        fin = time.monotonic() + segundos
        while True:
            try:
                conexion.do_handshake()
                break
            except (SSL.WantReadError, SSL.WantWriteError) as espera:
                restante = fin - time.monotonic()
                if restante <= 0:
                    break
                leer = [cruda] if isinstance(espera, SSL.WantReadError) else []
                escribir = [] if leer else [cruda]
                select.select(leer, escribir, [], restante)
            except (SSL.Error, OSError):
                # Acá sí: el mirón rechazó, que es lo que se esperaba.
                break

        ofrecidos = conexion.get_peer_cert_chain() or []
        return [crypto.dump_certificate(crypto.FILETYPE_ASN1, c)
                for c in ofrecidos]
    finally:
        try:
            cruda.close()
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════════════
# 2. Leer la dirección que el certificado lleva adentro
# ══════════════════════════════════════════════════════════════════════════

def direcciones_del_emisor(certificado: x509.Certificate) -> list:
    """Las direcciones de donde bajar el certificado de quien lo firmó.

    Es la extensión «acceso a la información de la autoridad», campo
    `caIssuers`. La misma que lee el navegador. Si el certificado no la trae,
    no hay nada que hacer y la lista vuelve vacía.
    """
    try:
        extension = certificado.extensions.get_extension_for_class(
            x509.AuthorityInformationAccess)
    except x509.ExtensionNotFound:
        return []

    salida = []
    for acceso in extension.value:
        if acceso.access_method != AuthorityInformationAccessOID.CA_ISSUERS:
            # El otro valor habitual es `OCSP`, que sirve para preguntar si el
            # certificado fue revocado. No es lo que buscamos.
            continue
        lugar = acceso.access_location
        if isinstance(lugar, x509.UniformResourceIdentifier):
            salida.append(lugar.value)
    return salida


def la_direccion_sirve(url: str, *, permitir_loopback: bool = False):
    """¿Se puede pedir esta dirección? Devuelve `(sirve, motivo)`.

    `permitir_loopback` existe PARA LAS PRUEBAS, que montan el servidor de la
    pieza en `127.0.0.1`. En producción nadie lo pasa, y por eso el valor por
    omisión es el cerrado.
    """
    try:
        partes = urlsplit(url)
    except ValueError:
        return False, "no se entiende como dirección"

    if partes.scheme not in ESQUEMAS_PERMITIDOS:
        # `file://` haría que el servidor se leyera un archivo propio y lo
        # tratara como certificado. `gopher://`, `ftp://` y el resto no tienen
        # por qué aparecer acá.
        return False, f"el esquema «{partes.scheme}» no está permitido"

    if not partes.hostname:
        return False, "no dice a qué servidor pedirla"

    try:
        resueltas = socket.getaddrinfo(partes.hostname, partes.port or None,
                                       proto=socket.IPPROTO_TCP)
    except OSError as e:
        return False, f"el nombre no resuelve ({e})"

    for *_resto, direccion in resueltas:
        try:
            ip = ipaddress.ip_address(direccion[0])
        except ValueError:
            return False, "resuelve a algo que no es una dirección IP"
        interna = (ip.is_private or ip.is_loopback or ip.is_link_local
                   or ip.is_reserved or ip.is_multicast)
        if interna and not permitir_loopback:
            # Una petición a ciegas contra un servicio interno del servidor.
            return False, f"resuelve a una dirección interna ({ip})"

    return True, ""


async def _bajar(url: str, *, segundos: int,
                 permitir_loopback: bool = False) -> bytes:
    """Baja la pieza. Levanta `NoSePudoCompletar` si algo no cuadra."""
    sirve, motivo = await asyncio.to_thread(
        la_direccion_sirve, url, permitir_loopback=permitir_loopback)
    if not sirve:
        raise NoSePudoCompletar(
            f"la dirección del certificado emisor no sirve: {motivo} ({url})")

    # NO SE SIGUEN REDIRECCIONES: una redirección apunta a donde quiera, y
    # dejaría atrás la comprobación de la dirección que se acaba de hacer.
    async with httpx.AsyncClient(timeout=segundos,
                                 follow_redirects=False) as cliente:
        respuesta = await cliente.get(url)

    if respuesta.status_code != 200:
        raise NoSePudoCompletar(
            f"pedir el certificado emisor devolvió {respuesta.status_code} "
            f"({url})")

    if len(respuesta.content) > MAXIMO_DE_LA_PIEZA:
        raise NoSePudoCompletar(
            f"el certificado emisor pesa {len(respuesta.content)} bytes, más "
            f"que el tope de {MAXIMO_DE_LA_PIEZA} ({url})")

    return respuesta.content


def certificados_de(crudo: bytes) -> list:
    """Los certificados que haya en esos bytes, en cualquiera de las formas.

    Las autoridades sirven esto de cuatro maneras distintas y ninguna avisa
    cuál: DER pelado (lo más común), PEM, o un sobre PKCS#7 con varios adentro.
    Se prueban todas antes de darse por vencido.
    """
    for intento in (
        lambda: [x509.load_der_x509_certificate(crudo)],
        lambda: [x509.load_pem_x509_certificate(crudo)],
        lambda: list(x509.load_der_pkcs7_certificates(crudo)),
        lambda: list(x509.load_pem_pkcs7_certificates(crudo)),
    ):
        try:
            encontrados = intento()
        except Exception:
            continue
        if encontrados:
            return encontrados
    return []


# ══════════════════════════════════════════════════════════════════════════
# 3. La guarda: la pieza sólo vale si CIERRA la cadena contra una raíz pública
# ══════════════════════════════════════════════════════════════════════════

_DEPOSITOS_OPENSSL = {}


def _deposito_de_openssl():
    """El depósito de raíces, en la forma que entiende OpenSSL."""
    ruta = archivo_de_raices()
    if ruta in _DEPOSITOS_OPENSSL:
        return _DEPOSITOS_OPENSSL[ruta]

    deposito = crypto.X509Store()
    for raiz in _raices():
        try:
            deposito.add_cert(crypto.X509.from_cryptography(raiz))
        except Exception:
            # Una raíz repetida o ilegible no puede impedir armar el depósito
            # entero. Son ciento cuarenta; que falte una no cambia nada.
            continue
    _DEPOSITOS_OPENSSL[ruta] = deposito
    return deposito


def por_que_no_cierra(hoja: x509.Certificate, piezas: list) -> str:
    """El motivo por el que la cadena no cierra, o cadena vacía si cierra.

    SE VERIFICA CON OPENSSL, QUE ES EL MISMO MOTOR QUE VA A HACER LA CONEXION

        La primera versión usaba el verificador de `cryptography`, que aplica el
        perfil formal del foro CA/B. Es MAS ESTRICTO que OpenSSL, y eso lo hacía
        inservible como portero: rechazaba cadenas que la conexión de verdad
        aceptaba sin chistar.

        Comprobado con un certificado al que le falta la extensión 2.5.29.35
        —el identificador de la clave de la autoridad, que muchos certificados
        viejos no traen—:

            perfil estricto : RECHAZA
            conexión OpenSSL: ACEPTA

        O sea que la guarda tiraba abajo el arreglo entero y encima con un
        mensaje equivocado: decía «no cierra contra una raíz pública» cuando sí
        cerraba. Un portero más exigente que el que después deja pasar no es
        seguridad, es un fallo con otro nombre.

    LA PROTECCION NO SE AFLOJA

        Se comprobó a mano que OpenSSL, con sus banderas por omisión, EXIGE
        llegar a un certificado autofirmado del depósito: una pieza suelta
        metida ahí no se vuelve raíz de confianza. Una pieza inventada sigue sin
        servir para nada.

    NO SE MIRA EL NOMBRE DEL SITIO, A PROPOSITO

        Lo mira la conexión real, que es donde corresponde. Acá sólo importa si
        la cadena llega a una raíz pública. Y comprobarlo dos veces, con dos
        implementaciones distintas de las reglas de comodines y nombres
        alternativos, era otra fuente de rechazos equivocados.
    """
    try:
        contexto = crypto.X509StoreContext(
            _deposito_de_openssl(),
            crypto.X509.from_cryptography(hoja),
            [crypto.X509.from_cryptography(p) for p in piezas])
        contexto.verify_certificate()
        return ""
    except crypto.X509StoreContextError as e:
        return str(e)
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def la_cadena_cierra(hoja: x509.Certificate, piezas: list,
                     host: str = None) -> bool:
    """¿Con estas piezas, el certificado del sitio llega hasta una raíz pública?

    `host` ya no se usa para verificar (ver `por_que_no_cierra`); se conserva
    porque los llamadores lo pasan y porque aparece en el registro.
    """
    motivo = por_que_no_cierra(hoja, piezas)
    if motivo:
        logger.debug("cadena_tls: la cadena de %s no cierra todavía (%s)",
                     host, motivo)
    return not motivo


# ── Para que el registro diga QUE cadena mandó el servidor ─────────────────
#
# Cuando esto falla, «no cierra contra una raíz pública» no alcanza para saber
# qué pasó: hace falta ver quién es cada certificado y quién lo firmó. Sin eso,
# diagnosticar un fallo en producción es adivinar.

def _nombre_corto(nombre) -> str:
    partes = []
    for oid, etiqueta in ((NameOID.COMMON_NAME, ""),
                          (NameOID.ORGANIZATION_NAME, "de ")):
        valores = nombre.get_attributes_for_oid(oid)
        if valores:
            partes.append(f"{etiqueta}{valores[0].value}")
    return " — ".join(partes) or nombre.rfc4514_string()


def describir(certificados) -> str:
    """Una línea por certificado: quién es y quién lo firmó."""
    if not certificados:
        return "      (ninguno)"
    filas = []
    for i, c in enumerate(certificados):
        filas.append(f"      [{i}] {_nombre_corto(c.subject)}")
        filas.append(f"          lo firmó: {_nombre_corto(c.issuer)}")
    return "\n".join(filas)


# ══════════════════════════════════════════════════════════════════════════
# 4. Lo que usa el resto del proyecto
# ══════════════════════════════════════════════════════════════════════════

async def piezas_para(host: str, puerto: int = 443, *, segundos: int = SEGUNDOS,
                      permitir_loopback: bool = False) -> list:
    """Los certificados intermedios que faltan para cerrar la cadena, en PEM.

    SE CAMINA DESDE EL CERTIFICADO DEL SITIO HACIA ARRIBA, Y ESO NO ES UN DETALLE

        La primera versión buscaba la dirección en la ULTIMA pieza que mandaba
        el servidor. Eso da por sentado que lo que manda el servidor es el
        principio correcto de la cadena, y el sitio del BCV demostró que no:

            [0] *.bcv.org.ve
                lo firmó: Sectigo Public Server Authentication CA DV R36
            [1] Sectigo RSA Domain Validation Secure Server CA   ← OTRA COSA
                lo firmó: USERTrust RSA Certification Authority

        La pieza [1] NO es quien firmó el certificado del sitio: es una vieja,
        de otra cadena, que no tiene nada que ver. Lo que de verdad falta —la
        R36— no viene por ningún lado.

        Al seguir la dirección de [1] se bajaba un certificado de USERTrust que
        no servía para nada, y el arreglo fallaba diciendo «la cadena no
        cierra», que era cierto pero por el motivo equivocado.

        Ahora se camina como camina el navegador: se arranca en el certificado
        del sitio, y en cada paso se busca A QUIEN LE FALTA EL EMISOR. Si ese
        emisor está entre lo que mandó el servidor, se usa; si no está, se baja
        por la dirección que trae adentro EL CERTIFICADO AL QUE LE FALTA — no
        la de cualquier otro.

        Lo que el servidor manda de más no molesta: queda como candidato y, si
        no sirve, se ignora.

    Levanta `NoSePudoCompletar` si no se consigue cerrar la cadena.
    """
    ofrecidos = await asyncio.to_thread(_lo_que_ofrece, host, puerto, segundos)
    if not ofrecidos:
        raise NoSePudoCompletar(
            f"{host} no mostró ningún certificado: el problema no es una "
            "cadena incompleta")

    try:
        hoja = x509.load_der_x509_certificate(ofrecidos[0])
    except Exception as e:
        raise NoSePudoCompletar(
            f"no se pudo leer el certificado que mostró {host}: {e}")

    piezas = []
    for crudo in ofrecidos[1:]:
        try:
            piezas.append(x509.load_der_x509_certificate(crudo))
        except Exception:
            continue
    del_servidor = list(piezas)
    bajadas = []

    # Quién es quién, por su nombre. Es como se busca el emisor de un
    # certificado: su campo «emisor» es el «sujeto» de quien lo firmó.
    conocidos = {c.subject: c for c in piezas}

    def _cierra():
        return la_cadena_cierra(hoja, piezas, host)

    # Si con lo que el servidor SI manda la cadena ya cierra, no se baja nada.
    if piezas and _cierra():
        logger.info("cadena_tls: %s manda la cadena completa; el fallo de la "
                    "conexión no era una pieza que falta.", host)
        return [p.public_bytes(serialization.Encoding.PEM) for p in piezas]

    # NO HAY UN CORTE AL LLEGAR A UN CERTIFICADO AUTOFIRMADO, Y SE SACO A
    # PROPOSITO. Lo había: «si el sujeto es igual al emisor, se llegó arriba de
    # todo, cortar». Al romperlo no se puso roja ninguna prueba, y mirando por
    # qué se ve que no hacía nada: la caminata ya está acotada por
    # `MAXIMO_DE_SALTOS`, así que sin él sólo se dan unas vueltas de más
    # comprobando lo mismo. Una guarda que no se puede poner en rojo es una
    # guarda de la que nadie sabe si anda, y este repositorio ya pagó eso.
    actual = hoja
    for _salto in range(MAXIMO_DE_SALTOS):
        emisor = conocidos.get(actual.issuer)
        if emisor is None:
            emisor = await _bajar_al_emisor(
                actual, host, segundos=segundos,
                permitir_loopback=permitir_loopback, ya_se_bajo=bool(bajadas))
            if emisor is None:
                break
            piezas.append(emisor)
            bajadas.append(emisor)
            conocidos[emisor.subject] = emisor

        if _cierra():
            logger.info(
                "cadena_tls: %s manda una cadena incompleta; se bajaron %d "
                "pieza(s) y ahora cierra contra una raíz pública.",
                host, len(bajadas))
            return [p.public_bytes(serialization.Encoding.PEM) for p in piezas]

        actual = emisor

    # EL REGISTRO TIENE QUE DECIR QUE CADENA ERA. Sin esto, un fallo en
    # producción sólo dice «no cierra» y diagnosticarlo es adivinar — ya pasó,
    # y fue este registro el que lo resolvió.
    logger.error(
        "cadena_tls: la cadena de %s no cierra contra ninguna raíz pública.\n"
        "  Lo que ofreció el servidor:\n%s\n"
        "  Lo que se bajó siguiendo la dirección de adentro:\n%s\n"
        "  Motivo de la última comprobación: %s",
        host, describir([hoja] + del_servidor), describir(bajadas),
        por_que_no_cierra(hoja, piezas) or "(ninguno: cerró y no debería)")

    raise NoSePudoCompletar(
        f"la cadena de {host} sigue sin cerrar contra una raíz pública después "
        f"de bajar {len(bajadas)} pieza(s). NO se usa ninguna: una pieza que no "
        "cierra la cadena puede haberla puesto cualquiera. El registro de "
        "arriba dice qué certificados eran.")


async def _bajar_al_emisor(certificado, host, *, segundos, permitir_loopback,
                           ya_se_bajo):
    """Baja el certificado de quien firmó a `certificado`, o `None`.

    La dirección sale de ADENTRO de `certificado`, que es el que tiene el
    eslabón roto. Seguir la de cualquier otro es lo que hacía la versión
    anterior, y es lo que la dejó persiguiendo una pieza que no servía.
    """
    direcciones = direcciones_del_emisor(certificado)
    if not direcciones:
        if ya_se_bajo:
            # Ya se bajó algo y la cadena no cerró: el motivo no es que falte
            # una dirección. Decirlo acá mandaría a mirar el lugar equivocado.
            return None
        raise NoSePudoCompletar(
            f"el certificado de {host} no dice dónde bajar el de quien lo "
            "firmó, así que no hay forma de completar la cadena sola")

    ultimo_error = None
    for url in direcciones:
        try:
            encontrados = certificados_de(await _bajar(
                url, segundos=segundos, permitir_loopback=permitir_loopback))
        except NoSePudoCompletar as e:
            ultimo_error = e
            continue
        for candidato in encontrados:
            # Tiene que ser EL EMISOR, no cualquier certificado que devuelvan.
            # Una dirección que contesta otra cosa no completa nada.
            if candidato.subject == certificado.issuer:
                return candidato
        if encontrados:
            logger.warning(
                "cadena_tls: %s devolvió %d certificado(s), pero ninguno es "
                "quien firmó a «%s».", url, len(encontrados),
                _nombre_corto(certificado.subject))

    if ultimo_error and not ya_se_bajo:
        raise ultimo_error
    return None


# Las piezas ya conseguidas, por servidor. En memoria del proceso: son datos
# públicos que se bajan en medio segundo, y un archivo en disco sería una copia
# más que puede quedar vieja.
_GUARDADAS = {}


async def contexto_para(host: str, puerto: int = 443, *,
                        segundos: int = SEGUNDOS,
                        permitir_loopback: bool = False) -> ssl.SSLContext:
    """Un contexto TLS que VERIFICA, con la pieza que falta ya adentro.

    Es lo que se le pasa a `httpx` para reintentar. La verificación queda
    encendida y completa: si la pieza no alcanzara, la conexión falla igual.
    """
    piezas = _GUARDADAS.get((host, puerto))
    if piezas is None:
        piezas = await piezas_para(host, puerto, segundos=segundos,
                                   permitir_loopback=permitir_loopback)
        _GUARDADAS[(host, puerto)] = piezas

    contexto = ssl.create_default_context(cafile=archivo_de_raices())
    contexto.load_verify_locations(
        cadata="".join(p.decode("ascii") for p in piezas))
    return contexto


def olvidar(host: str = None, puerto: int = 443) -> None:
    """Tira lo guardado, para que la próxima consulta vuelva a buscarlo.

    Hace falta el día que la autoridad rote la pieza: la vieja deja de cerrar
    la cadena y hay que ir a buscar la nueva. Sin esto habría que reiniciar el
    servidor, que es justo el tipo de cosa que este módulo vino a evitar.
    """
    if host is None:
        _GUARDADAS.clear()
    else:
        _GUARDADAS.pop((host, puerto), None)
