"""
tests/test_cadena_tls.py — Que una cadena de certificados incompleta se
complete sola, y que una pieza falsa no entre.

QUE PASO

    El sitio del BCV dejó de poder consultarse con «unable to get local issuer
    certificate»: manda su certificado pero no la pieza intermedia que lo une a
    una raíz conocida. El navegador entra igual porque lee adentro del
    certificado la dirección de esa pieza y la baja. Python no lo hace nunca.

    Mientras eso estuvo roto, la contabilidad quedó usando una tasa del BCV
    congelada, y encima le ganaba a la que el operador cargaba a mano.

POR QUE ACA SE FABRICAN CERTIFICADOS EN VEZ DE LLAMAR AL BCV

    Tres motivos, y los tres importan:

      · Un test que sale a internet falla cuando falla la red, y entonces deja
        de creerse.
      · El día que el BCV arregle su servidor, un test contra el BCV pasaría
        por el motivo equivocado: no habría nada que completar.
      · Y el caso que más importa probar —una pieza FALSA— no se puede pedir a
        una autoridad de verdad.

    Así que acá se arma una autoridad de laboratorio entera: una raíz, una
    pieza intermedia y un certificado de servidor. Se levanta un servidor TLS
    que manda la cadena incompleta, igual que el BCV, y un servidor de
    certificados en la dirección que el certificado lleva escrita adentro.

    El depósito de raíces se sustituye por el del laboratorio a través de
    `cadena_tls.archivo_de_raices()`, que existe exactamente para esto.
"""
import asyncio
import datetime
import logging
import http.server
import os
import socket
import ssl
import sys
import threading

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from cryptography import x509                                    # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa        # noqa: E402
from cryptography.x509.oid import (ExtendedKeyUsageOID,          # noqa: E402
                                   NameOID)

from services import cadena_tls                                  # noqa: E402


def corre(coro):
    return asyncio.run(coro)


# El nombre tiene que resolver a 127.0.0.1 de verdad, porque el módulo abre una
# conexión TCP real. `localhost` es el único que cumple sin tocar /etc/hosts.
HOST = "localhost"

_DESDE = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
_HASTA = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
# La fábrica de certificados de laboratorio
# ══════════════════════════════════════════════════════════════════════════

def _clave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _nombre(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _raiz(cn):
    clave = _clave()
    cert = (x509.CertificateBuilder()
            .subject_name(_nombre(cn)).issuer_name(_nombre(cn))
            .public_key(clave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_DESDE).not_valid_after(_HASTA)
            .add_extension(x509.BasicConstraints(True, None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=False, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(
                clave.public_key()), critical=False)
            .sign(clave, hashes.SHA256()))
    return clave, cert


def _intermedia(clave_raiz, cert_raiz, cn, largo=0, direccion=None):
    """`largo` es cuántas autoridades más puede haber por debajo: 0 sólo firma
    certificados de sitio, 1 puede firmar otra intermedia."""
    clave = _clave()
    plano = (x509.CertificateBuilder()
             .subject_name(_nombre(cn)).issuer_name(cert_raiz.subject)
             .public_key(clave.public_key())
             .serial_number(x509.random_serial_number())
             .not_valid_before(_DESDE).not_valid_after(_HASTA)
             .add_extension(x509.BasicConstraints(True, largo), critical=True)
             .add_extension(x509.KeyUsage(
                digital_signature=False, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False), critical=True)
             .add_extension(x509.SubjectKeyIdentifier.from_public_key(
                clave.public_key()), critical=False)
             .add_extension(x509.AuthorityKeyIdentifier
                            .from_issuer_public_key(clave_raiz.public_key()),
                            critical=False))
    if direccion:
        plano = plano.add_extension(x509.AuthorityInformationAccess([
            x509.AccessDescription(
                x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                x509.UniformResourceIdentifier(direccion)),
        ]), critical=False)
    return clave, plano.sign(clave_raiz, hashes.SHA256())


def _hoja(clave_int, cert_int, host, direccion_del_emisor=None,
          con_identificador_de_autoridad=True):
    clave = _clave()
    plano = (x509.CertificateBuilder()
             .subject_name(_nombre(host)).issuer_name(cert_int.subject)
             .public_key(clave.public_key())
             .serial_number(x509.random_serial_number())
             .not_valid_before(_DESDE).not_valid_after(_HASTA)
             .add_extension(x509.BasicConstraints(False, None), critical=True)
             .add_extension(x509.SubjectAlternativeName(
                 [x509.DNSName(host)]), critical=False)
             .add_extension(x509.ExtendedKeyUsage(
                 [ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
             .add_extension(x509.KeyUsage(
                 digital_signature=True, content_commitment=False,
                 key_encipherment=True, data_encipherment=False,
                 key_agreement=False, key_cert_sign=False, crl_sign=False,
                 encipher_only=False, decipher_only=False), critical=True)
             .add_extension(x509.SubjectKeyIdentifier.from_public_key(
                 clave.public_key()), critical=False)
             )
    if con_identificador_de_autoridad:
        # 2.5.29.35, el «identificador de la clave de la autoridad».
        #
        # ESTA EXTENSION TIENE HISTORIA EN ESTE ARCHIVO. La primera versión del
        # laboratorio no la ponía, la guarda rechazaba su propia cadena buena, y
        # lo leí como que al laboratorio le faltaba algo. Era al revés: la
        # guarda usaba el verificador estricto de `cryptography` y rechazaba
        # cadenas que la conexión real acepta. Muchos certificados de verdad no
        # traen esta extensión, y por eso el arreglo no funcionó en producción.
        #
        # Por eso ahora se puede omitir: hay un test que EXIGE que sin ella la
        # cadena se acepte igual.
        plano = plano.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                clave_int.public_key()), critical=False)
    if direccion_del_emisor:
        # La extensión que lee el navegador y que este arreglo vino a leer.
        plano = plano.add_extension(x509.AuthorityInformationAccess([
            x509.AccessDescription(
                x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                x509.UniformResourceIdentifier(direccion_del_emisor)),
        ]), critical=False)
    return clave, plano.sign(clave_int, hashes.SHA256())


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def _pem_clave(clave):
    return clave.private_bytes(serialization.Encoding.PEM,
                               serialization.PrivateFormat.TraditionalOpenSSL,
                               serialization.NoEncryption())


# ══════════════════════════════════════════════════════════════════════════
# Los dos servidores del laboratorio
# ══════════════════════════════════════════════════════════════════════════

class ServidorTLS:
    """Un servidor TLS que manda exactamente los certificados que se le digan.

    Mandar sólo la hoja es reproducir el defecto del BCV.
    """

    def __init__(self, tmp, cadena, clave):
        ruta = os.path.join(tmp, f"srv-{id(self)}.pem")
        with open(ruta, "wb") as f:
            f.write(b"".join(_pem(c) for c in cadena) + _pem_clave(clave))
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.load_cert_chain(ruta)
        self._oyente = socket.socket()
        self._oyente.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._oyente.bind(("127.0.0.1", 0))
        self._oyente.listen(16)
        self.puerto = self._oyente.getsockname()[1]
        self._hilo = threading.Thread(target=self._servir, daemon=True)
        self._hilo.start()

    def _servir(self):
        while True:
            try:
                cruda, _ = self._oyente.accept()
            except OSError:
                return
            try:
                envuelta = self._ctx.wrap_socket(cruda, server_side=True)
                # Una respuesta mínima, para que el reintento verificado tenga
                # algo que leer y no muera en «conexión cerrada».
                envuelta.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                                 b"Connection: close\r\n\r\nok")
                envuelta.close()
            except Exception:
                try:
                    cruda.close()
                except OSError:
                    pass

    def cerrar(self):
        self._oyente.close()


class ServidorDeCertificados:
    """El que atiende la dirección escrita adentro del certificado."""

    def __init__(self, cuerpo, tipo="application/pkix-cert", estado=200,
                 redirigir_a=None):
        cuerpo_ = cuerpo
        tipo_ = tipo
        estado_ = estado
        redirigir_ = redirigir_a
        self.pedidos = []
        pedidos = self.pedidos

        class Manejador(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                pedidos.append(self.path)
                if redirigir_:
                    self.send_response(302)
                    self.send_header("Location", redirigir_)
                    self.end_headers()
                    return
                self.send_response(estado_)
                self.send_header("Content-Type", tipo_)
                self.send_header("Content-Length", str(len(cuerpo_)))
                self.end_headers()
                self.wfile.write(cuerpo_)

            def log_message(self, *_a):
                pass

        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.puerto = self._srv.server_address[1]
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    @property
    def direccion(self):
        return f"http://{HOST}:{self.puerto}/intermedia.crt"

    def cerrar(self):
        self._srv.shutdown()


# ══════════════════════════════════════════════════════════════════════════
# El laboratorio armado
# ══════════════════════════════════════════════════════════════════════════

class Laboratorio:
    def __init__(self, tmp, con_direccion=True,
                 con_identificador_de_autoridad=True):
        self.tmp = tmp
        self.k_raiz, self.raiz = _raiz("Raiz De Laboratorio")
        self.k_int, self.intermedia = _intermedia(
            self.k_raiz, self.raiz, "Intermedia De Laboratorio")

        # La del atacante: su propia raíz, que NO está en ningún depósito.
        self.k_raiz_mala, self.raiz_mala = _raiz("Raiz Del Atacante")
        self.k_int_mala, self.intermedia_mala = _intermedia(
            self.k_raiz_mala, self.raiz_mala, "Intermedia Del Atacante")

        self.servidor_certs = None
        direccion = None
        if con_direccion:
            crudo = self.intermedia.public_bytes(serialization.Encoding.DER)
            self.servidor_certs = ServidorDeCertificados(crudo)
            direccion = self.servidor_certs.direccion

        self.k_hoja, self.hoja = _hoja(
            self.k_int, self.intermedia, HOST, direccion,
            con_identificador_de_autoridad=con_identificador_de_autoridad)
        self.archivo_raiz = os.path.join(tmp, "raices.pem")
        with open(self.archivo_raiz, "wb") as f:
            f.write(_pem(self.raiz))
        self.servidor_tls = None

    def servir_incompleta(self):
        """Sólo la hoja: el defecto del BCV."""
        self.servidor_tls = ServidorTLS(self.tmp, [self.hoja], self.k_hoja)
        return self.servidor_tls

    def servir_completa(self):
        self.servidor_tls = ServidorTLS(self.tmp, [self.hoja, self.intermedia],
                                        self.k_hoja)
        return self.servidor_tls

    def cerrar(self):
        for s in (self.servidor_tls, self.servidor_certs):
            if s:
                s.cerrar()


@pytest.fixture
def lab(tmp_path, monkeypatch):
    laboratorio = Laboratorio(str(tmp_path))
    monkeypatch.setattr(cadena_tls, "archivo_de_raices",
                        lambda: laboratorio.archivo_raiz)
    cadena_tls.olvidar()
    yield laboratorio
    laboratorio.cerrar()
    cadena_tls.olvidar()


def _conectar_verificando(puerto, contexto=None):
    """Una conexión TLS de verdad, con la verificación puesta.

    Es la prueba final: si esto pasa, el arreglo sirve; si falla, no.
    """
    ctx = contexto or ssl.create_default_context(
        cafile=cadena_tls.archivo_de_raices())
    cruda = socket.create_connection(("127.0.0.1", puerto), timeout=10)
    envuelta = ctx.wrap_socket(cruda, server_hostname=HOST)
    envuelta.close()


# ══════════════════════════════════════════════════════════════════════════
# 1. El defecto, reproducido — y la comprobación de que estas pruebas prueban
# ══════════════════════════════════════════════════════════════════════════

def test_SIN_COMPLETAR_LA_CADENA_LA_CONEXION_FALLA(lab):
    """La comprobación de que el laboratorio reproduce el defecto de verdad.

    Si esto dejara de fallar, todas las pruebas de abajo pasarían por el motivo
    equivocado: no habría nada que completar y nadie se enteraría.
    """
    srv = lab.servir_incompleta()
    with pytest.raises(ssl.SSLCertVerificationError) as fallo:
        _conectar_verificando(srv.puerto)
    assert "unable to get local issuer certificate" in str(fallo.value), (
        f"el laboratorio falló por otro motivo: {fallo.value}")


def test_UNA_CADENA_INCOMPLETA_SE_COMPLETA_SOLA(lab):
    """El arreglo entero, de punta a punta.

    El servidor manda la cadena rota; se lee la dirección de adentro del
    certificado; se baja la pieza; y la conexión VERIFICADA pasa.
    """
    srv = lab.servir_incompleta()

    contexto = corre(cadena_tls.contexto_para(
        HOST, srv.puerto, permitir_loopback=True))

    # La prueba de verdad: una conexión con la verificación encendida.
    _conectar_verificando(srv.puerto, contexto)

    assert lab.servidor_certs.pedidos == ["/intermedia.crt"], (
        "no se pidió la pieza en la dirección que decía el certificado")


def test_la_pieza_bajada_es_la_que_faltaba(lab):
    srv = lab.servir_incompleta()
    piezas = corre(cadena_tls.piezas_para(HOST, srv.puerto,
                                          permitir_loopback=True))
    assert len(piezas) == 1
    recuperada = x509.load_pem_x509_certificate(piezas[0])
    assert recuperada == lab.intermedia


# ══════════════════════════════════════════════════════════════════════════
# 2. LA GUARDA: una pieza que no cierra la cadena no se usa ni se guarda
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_PIEZA_QUE_NO_CIERRA_LA_CADENA_SE_RECHAZA(lab, monkeypatch):
    """LA GUARDA PRINCIPAL DE TODO ESTE MODULO.

    Se baja un certificado de una dirección que viene escrita adentro de un
    certificado que todavía no se pudo verificar. O sea: de una dirección que,
    si hay alguien interponiéndose en la conexión, la elige él.

    Si eso se usara sin más, el atacante manda su propia pieza y listo. Acá se
    comprueba que NO: la pieza se acepta sólo si con ella la cadena cierra
    contra una raíz del depósito público.

    Y se comprueba además que no quede GUARDADA. Sin esa mitad, una pieza falsa
    se reusaría en cada consulta y la verdadera no se buscaría nunca más hasta
    reiniciar el servidor: la tasa congelada volviendo por otra puerta.
    """
    # El servidor de certificados devuelve la pieza DEL ATACANTE.
    lab.servidor_certs.cerrar()
    falsa = ServidorDeCertificados(
        lab.intermedia_mala.public_bytes(serialization.Encoding.DER))
    lab.servidor_certs = falsa
    # El certificado del sitio apunta a esa dirección.
    lab.k_hoja, lab.hoja = _hoja(lab.k_int, lab.intermedia, HOST,
                                 falsa.direccion)
    srv = lab.servir_incompleta()

    with pytest.raises(cadena_tls.NoSePudoCompletar) as fallo:
        corre(cadena_tls.piezas_para(HOST, srv.puerto, permitir_loopback=True))
    assert "sigue sin cerrar" in str(fallo.value)

    assert cadena_tls._GUARDADAS == {}, (
        "la pieza falsa quedó guardada: se va a reusar en cada consulta y la "
        "verdadera no se va a buscar nunca más")


def test_la_cadena_cierra_no_toma_la_pieza_como_raiz(lab):
    """El detalle que hace que la guarda de arriba sirva.

    Las piezas van como ESLABONES INTERMEDIOS, nunca al depósito de raíces. Si
    fueran al depósito, cualquier pieza autofirmada se validaría sola.
    """
    assert cadena_tls.la_cadena_cierra(lab.hoja, [lab.intermedia], HOST) is True
    assert cadena_tls.la_cadena_cierra(
        lab.hoja, [lab.intermedia_mala], HOST) is False
    assert cadena_tls.la_cadena_cierra(lab.hoja, [], HOST) is False


def test_EL_MIRON_RECHAZA_SIEMPRE():
    """La línea que mantiene la verificación encendida.

    `_rechazar_siempre` es lo que hace que la conexión con la que se mira el
    certificado no sea nunca una conexión de confianza. Si devolviera
    `aprobado`, habría un camino en el que se confía en algo sin verificar, y
    todo el argumento de seguridad de este módulo se cae.
    """
    for aprobado in (True, False, 1, 0):
        assert cadena_tls._rechazar_siempre(None, None, 0, 0, aprobado) is False


# ══════════════════════════════════════════════════════════════════════════
# 3. De dónde se acepta bajar
# ══════════════════════════════════════════════════════════════════════════

# CADA CASO AFIRMA EL MOTIVO, Y NO SOLO EL RECHAZO.
#
# La primera versión de esto pedía `file:///etc/passwd` y comprobaba nada más
# que se rechazara. Se rechazaba, sí — pero por la OTRA comprobación, la de la
# dirección interna, porque esa URL no nombra ningún servidor. Al permitir
# `file` a propósito el test seguía verde: dos guardas tapándose entre sí, que
# es el defecto que este repositorio ya pagó una vez.
#
# Por eso ahora las que prueban el esquema nombran un servidor y traen
# `permitir_loopback`: así la única comprobación que puede rechazarlas es la que
# se quiere probar.
@pytest.mark.parametrize("url, loopback, esperado, porque", [
    ("file://localhost/etc/passwd", True, "esquema",
     "leería un archivo del propio servidor"),
    ("gopher://localhost/x", True, "esquema",
     "ninguna autoridad sirve certificados por ahí"),
    ("ftp://localhost/x.crt", True, "esquema", "tampoco"),
    ("http://", False, "no dice a qué servidor", "no dice a qué servidor"),
    ("http://127.0.0.1/x.crt", False, "interna", "es un servicio interno"),
])
def test_de_ahi_no_se_baja(url, loopback, esperado, porque):
    sirve, motivo = cadena_tls.la_direccion_sirve(
        url, permitir_loopback=loopback)
    assert sirve is False, f"{url}: {porque}"
    assert esperado in motivo, (
        f"{url} se rechazó por «{motivo}», que no es el motivo que este caso "
        f"vino a probar («{esperado}»). Si se rechaza por otra comprobación, "
        "esta guarda podría estar apagada sin que nadie se entere.")


def test_NO_SE_PIDE_A_UNA_DIRECCION_INTERNA(lab):
    """Una petición a ciegas contra un servicio interno del servidor.

    Quien puede poner una dirección acá ya está interponiéndose en la conexión
    al BCV, así que tiene opciones peores. Pero evitarlo es gratis.
    """
    sirve, motivo = cadena_tls.la_direccion_sirve(lab.servidor_certs.direccion)
    assert sirve is False
    assert "interna" in motivo

    srv = lab.servir_incompleta()
    with pytest.raises(cadena_tls.NoSePudoCompletar) as fallo:
        # Sin `permitir_loopback`: como en producción.
        corre(cadena_tls.piezas_para(HOST, srv.puerto))
    assert "interna" in str(fallo.value)


def test_NO_SE_SIGUEN_REDIRECCIONES(lab):
    """Una redirección apunta a donde quiera, y dejaría atrás la comprobación
    de la dirección que se acaba de hacer."""
    lab.servidor_certs.cerrar()
    real = ServidorDeCertificados(
        lab.intermedia.public_bytes(serialization.Encoding.DER))
    desviado = ServidorDeCertificados(b"", redirigir_a=real.direccion)
    lab.servidor_certs = desviado
    lab.k_hoja, lab.hoja = _hoja(lab.k_int, lab.intermedia, HOST,
                                 desviado.direccion)
    srv = lab.servir_incompleta()
    try:
        with pytest.raises(cadena_tls.NoSePudoCompletar) as fallo:
            corre(cadena_tls.piezas_para(HOST, srv.puerto,
                                         permitir_loopback=True))
        assert "302" in str(fallo.value)
        assert real.pedidos == [], "se siguió la redirección"
    finally:
        real.cerrar()


# El tamaño es FIJO y no se calcula a partir de la constante.
#
# La primera versión servía `MAXIMO_DE_LA_PIEZA + 1` bytes, así que subir el
# tope subía también el cuerpo y el test seguía pasando: no probaba el tope,
# probaba una tautología.
DEMASIADO = 200_000


def test_una_pieza_demasiado_grande_se_rechaza(lab):
    assert cadena_tls.MAXIMO_DE_LA_PIEZA < DEMASIADO, (
        "subieron el tope por encima de lo que este test manda: dejó de probar "
        "el tope. Hay que subir DEMASIADO.")
    lab.servidor_certs.cerrar()
    gorda = ServidorDeCertificados(b"x" * DEMASIADO)
    lab.servidor_certs = gorda
    lab.k_hoja, lab.hoja = _hoja(lab.k_int, lab.intermedia, HOST,
                                 gorda.direccion)
    srv = lab.servir_incompleta()
    with pytest.raises(cadena_tls.NoSePudoCompletar) as fallo:
        corre(cadena_tls.piezas_para(HOST, srv.puerto, permitir_loopback=True))
    assert "tope" in str(fallo.value)


# ══════════════════════════════════════════════════════════════════════════
# 4. Los casos en los que no hay nada que hacer, y hay que fallar
# ══════════════════════════════════════════════════════════════════════════

def test_sin_direccion_adentro_del_certificado_no_hay_nada_que_hacer(tmp_path,
                                                                     monkeypatch):
    """Si el certificado no dice dónde bajar la pieza, no se puede inventar."""
    laboratorio = Laboratorio(str(tmp_path), con_direccion=False)
    monkeypatch.setattr(cadena_tls, "archivo_de_raices",
                        lambda: laboratorio.archivo_raiz)
    cadena_tls.olvidar()
    try:
        srv = laboratorio.servir_incompleta()
        with pytest.raises(cadena_tls.NoSePudoCompletar) as fallo:
            corre(cadena_tls.piezas_para(HOST, srv.puerto,
                                         permitir_loopback=True))
        assert "no dice dónde" in str(fallo.value)
    finally:
        laboratorio.cerrar()
        cadena_tls.olvidar()


def test_si_el_servidor_manda_la_cadena_entera_no_se_baja_nada(lab):
    """No se sale a la red por gusto: si con lo que manda el servidor la cadena
    ya cierra, el problema de la conexión era otro."""
    srv = lab.servir_completa()
    piezas = corre(cadena_tls.piezas_para(HOST, srv.puerto,
                                          permitir_loopback=True))
    assert len(piezas) == 1
    assert lab.servidor_certs.pedidos == []


def test_si_no_hay_servidor_del_otro_lado_levanta(lab):
    oyente = socket.socket()
    oyente.bind(("127.0.0.1", 0))
    puerto = oyente.getsockname()[1]
    oyente.close()
    with pytest.raises(OSError):
        corre(cadena_tls.piezas_para(HOST, puerto, segundos=3,
                                     permitir_loopback=True))


# ══════════════════════════════════════════════════════════════════════════
# 5. Los formatos en los que las autoridades sirven un certificado
# ══════════════════════════════════════════════════════════════════════════

def test_se_entienden_los_cuatro_formatos(lab):
    """Ninguna autoridad avisa en qué formato sirve la pieza."""
    der = lab.intermedia.public_bytes(serialization.Encoding.DER)
    assert cadena_tls.certificados_de(der) == [lab.intermedia]
    assert cadena_tls.certificados_de(_pem(lab.intermedia)) == [lab.intermedia]
    assert cadena_tls.certificados_de(b"esto no es un certificado") == []


def test_una_pieza_en_pem_tambien_sirve(lab):
    """El caso de verdad, no sólo el parseo: servida en PEM, se completa igual."""
    lab.servidor_certs.cerrar()
    en_pem = ServidorDeCertificados(_pem(lab.intermedia),
                                    tipo="application/x-pem-file")
    lab.servidor_certs = en_pem
    lab.k_hoja, lab.hoja = _hoja(lab.k_int, lab.intermedia, HOST,
                                 en_pem.direccion)
    srv = lab.servir_incompleta()
    contexto = corre(cadena_tls.contexto_para(HOST, srv.puerto,
                                              permitir_loopback=True))
    _conectar_verificando(srv.puerto, contexto)


# ══════════════════════════════════════════════════════════════════════════
# 6. Que no se baje la misma pieza en cada consulta
# ══════════════════════════════════════════════════════════════════════════

def test_la_pieza_se_guarda_y_no_se_vuelve_a_bajar(lab):
    srv = lab.servir_incompleta()
    corre(cadena_tls.contexto_para(HOST, srv.puerto, permitir_loopback=True))
    corre(cadena_tls.contexto_para(HOST, srv.puerto, permitir_loopback=True))
    corre(cadena_tls.contexto_para(HOST, srv.puerto, permitir_loopback=True))
    assert lab.servidor_certs.pedidos == ["/intermedia.crt"], (
        "se bajó la pieza más de una vez")


def test_olvidar_hace_que_se_vuelva_a_buscar(lab):
    """Hace falta el día que la autoridad rote la pieza: la vieja deja de
    cerrar la cadena y hay que ir a buscar la nueva SIN reiniciar el servidor."""
    srv = lab.servir_incompleta()
    corre(cadena_tls.contexto_para(HOST, srv.puerto, permitir_loopback=True))
    cadena_tls.olvidar(HOST, srv.puerto)
    corre(cadena_tls.contexto_para(HOST, srv.puerto, permitir_loopback=True))
    assert len(lab.servidor_certs.pedidos) == 2


# ══════════════════════════════════════════════════════════════════════════
# 7. La guarda no puede ser más estricta que la conexión que vigila
# ══════════════════════════════════════════════════════════════════════════
#
# EL DEFECTO QUE ESTOS TESTS VIENEN A IMPEDIR
#
#   La primera versión de `la_cadena_cierra` usaba el verificador de
#   `cryptography`, que aplica el perfil formal del foro CA/B. Es MAS ESTRICTO
#   que OpenSSL, que es quien hace la conexión de verdad.
#
#   Resultado en producción: el servidor bajó la pieza que faltaba, la guarda la
#   rechazó, y el registro dijo «no cierra contra una raíz pública» — cuando sí
#   cerraba. El arreglo entero no servía, y encima el mensaje mandaba a mirar
#   el lugar equivocado.
#
#   Un portero más exigente que el que después deja pasar no es seguridad.

def test_LA_GUARDA_NO_ES_MAS_ESTRICTA_QUE_LA_CONEXION(tmp_path, monkeypatch):
    """Un certificado sin la extensión 2.5.29.35 tiene que pasar.

    Muchos certificados de verdad no la traen. El perfil estricto los rechaza;
    OpenSSL los acepta. Manda OpenSSL, porque es el que hace la conexión.
    """
    laboratorio = Laboratorio(str(tmp_path),
                              con_identificador_de_autoridad=False)
    monkeypatch.setattr(cadena_tls, "archivo_de_raices",
                        lambda: laboratorio.archivo_raiz)
    cadena_tls.olvidar()
    try:
        # Sin la extensión, la cadena buena sigue siendo buena.
        assert cadena_tls.la_cadena_cierra(
            laboratorio.hoja, [laboratorio.intermedia], HOST) is True, (
            "la guarda rechazó una cadena que la conexión real acepta. Es el "
            "defecto que dejó el arreglo sin funcionar en producción.")

        # Y de punta a punta: se completa y la conexión VERIFICADA pasa.
        srv = laboratorio.servir_incompleta()
        contexto = corre(cadena_tls.contexto_para(HOST, srv.puerto,
                                                  permitir_loopback=True))
        _conectar_verificando(srv.puerto, contexto)
    finally:
        laboratorio.cerrar()
        cadena_tls.olvidar()


def test_la_pieza_del_atacante_sigue_sin_servir_sin_esa_extension(tmp_path,
                                                                  monkeypatch):
    """La contracara, y es la que importa: aflojar el verificador no puede
    haber aflojado la protección."""
    laboratorio = Laboratorio(str(tmp_path),
                              con_identificador_de_autoridad=False)
    monkeypatch.setattr(cadena_tls, "archivo_de_raices",
                        lambda: laboratorio.archivo_raiz)
    cadena_tls.olvidar()
    try:
        assert cadena_tls.la_cadena_cierra(
            laboratorio.hoja, [laboratorio.intermedia_mala], HOST) is False
        assert cadena_tls.la_cadena_cierra(laboratorio.hoja, [], HOST) is False
    finally:
        laboratorio.cerrar()
        cadena_tls.olvidar()


def test_por_que_no_cierra_dice_el_motivo(lab):
    """El motivo va al registro. «No cierra» a secas no alcanza para
    diagnosticar nada, y ya costó una ronda entera de suposiciones."""
    assert cadena_tls.por_que_no_cierra(lab.hoja, [lab.intermedia]) == ""
    motivo = cadena_tls.por_que_no_cierra(lab.hoja, [])
    assert motivo, "no dio ningún motivo"
    assert "issuer" in motivo.lower() or "certificate" in motivo.lower()


# ══════════════════════════════════════════════════════════════════════════
# 8. Que el registro diga QUE cadena era
# ══════════════════════════════════════════════════════════════════════════

def test_EL_REGISTRO_DICE_QUIEN_FIRMO_A_QUIEN(lab):
    """Sin esto, un fallo en producción sólo dice «no cierra».

    Es exactamente lo que pasó: hubo que adivinar qué certificados eran, y se
    adivinó mal dos veces.
    """
    texto = cadena_tls.describir([lab.hoja, lab.intermedia])
    assert HOST in texto
    assert "Intermedia De Laboratorio" in texto
    assert "Raiz De Laboratorio" in texto, (
        "no dice quién firmó la pieza intermedia, que es justo el eslabón que "
        "hay que mirar cuando la cadena no cierra")
    assert "lo firmó" in texto


def test_describir_aguanta_una_lista_vacia():
    assert "ninguno" in cadena_tls.describir([])


def test_AL_FALLAR_EL_REGISTRO_MUESTRA_LA_CADENA_ENTERA(lab, caplog):
    """La guarda del diagnóstico.

    Cuando esto falla en producción no hay forma de mirar el certificado a mano:
    el registro es todo lo que hay. Si deja de decir qué cadena era, el próximo
    fallo se vuelve a diagnosticar adivinando — y fue justamente este registro
    el que resolvió el caso del BCV.

    El escenario es el del atacante completo: sirve SU certificado, y la
    dirección de adentro apunta a SU intermedia. Así se baja algo de verdad —si
    la dirección devolviera un certificado que no es el emisor, no se bajaría
    nada y el registro no tendría qué mostrar.
    """
    lab.servidor_certs.cerrar()
    suya = ServidorDeCertificados(
        lab.intermedia_mala.public_bytes(serialization.Encoding.DER))
    lab.servidor_certs = suya
    clave_mala, hoja_mala = _hoja(lab.k_int_mala, lab.intermedia_mala, HOST,
                                  suya.direccion)
    srv = ServidorTLS(lab.tmp, [hoja_mala], clave_mala)
    lab.servidor_tls = srv

    with caplog.at_level(logging.ERROR, logger="services.cadena_tls"):
        with pytest.raises(cadena_tls.NoSePudoCompletar):
            corre(cadena_tls.piezas_para(HOST, srv.puerto,
                                         permitir_loopback=True))

    # `getMessage()` ya aplica los argumentos: volver a formatear revienta.
    registro = "\n".join(r.getMessage() for r in caplog.records)
    assert "Lo que ofreció el servidor" in registro
    assert "localhost" in registro, (
        "el registro no dice qué mandó el servidor")
    assert "Intermedia Del Atacante" in registro, (
        "el registro no dice qué se bajó, que es la pieza que hay que mirar")
    assert "Motivo de la última comprobación" in registro


def test_UNA_PIEZA_AUTOFIRMADA_NO_SE_VUELVE_RAIZ_DE_CONFIANZA(lab):
    """EL ATAQUE DE VERDAD, y el caso que ningún otro test cubría.

    Una pieza INTERMEDIA inventada no sirve aunque se metiera al depósito de
    raíces: OpenSSL exige llegar a un certificado AUTOFIRMADO, y una intermedia
    no lo es. Eso hace que el error de meterla al depósito pase desapercibido.

    Pero una RAIZ inventada sí es autofirmada. Si las piezas bajadas fueran al
    depósito de raíces en vez de ir como eslabones intermedios, al atacante le
    alcanzaría con firmarse la suya: pone la dirección en el certificado que
    sirve, el servidor la baja, y queda confiada.

    Por eso van como eslabones. Este test es el único que lo comprueba.
    """
    _clave, hoja_del_atacante = _hoja(lab.k_raiz_mala, lab.raiz_mala, HOST)

    assert cadena_tls.la_cadena_cierra(
        hoja_del_atacante, [lab.raiz_mala], HOST) is False, (
        "una raíz autofirmada inventada quedó aceptada. Cualquiera que pueda "
        "interponerse en la conexión se firma la suya, la publica en la "
        "dirección que él mismo elige, y la aplicación se la cree.")

    # Y la contracara, para que no pase por no aceptar nunca nada.
    assert cadena_tls.la_cadena_cierra(lab.hoja, [lab.intermedia], HOST) is True


# ══════════════════════════════════════════════════════════════════════════
# 9. El caso del BCV: el servidor manda la pieza EQUIVOCADA
# ══════════════════════════════════════════════════════════════════════════

def test_EL_SERVIDOR_MANDA_LA_PIEZA_EQUIVOCADA(lab):
    """LO QUE DE VERDAD PASA CON EL BCV, sacado de su registro de producción.

        [0] *.bcv.org.ve
            lo firmó: Sectigo Public Server Authentication CA DV R36
        [1] Sectigo RSA Domain Validation Secure Server CA   ← OTRA COSA
            lo firmó: USERTrust RSA Certification Authority

    La pieza [1] no es quien firmó el certificado del sitio: es de otra cadena y
    no sirve para nada. La que de verdad falta no viene.

    La primera versión buscaba la dirección en la ULTIMA pieza que mandaba el
    servidor —o sea, en la equivocada— y terminaba bajando un certificado que no
    completaba nada. Hay que arrancar en el certificado del sitio y seguir SU
    dirección.
    """
    lab.servidor_tls = ServidorTLS(
        lab.tmp, [lab.hoja, lab.intermedia_mala], lab.k_hoja)

    contexto = corre(cadena_tls.contexto_para(
        HOST, lab.servidor_tls.puerto, permitir_loopback=True))
    _conectar_verificando(lab.servidor_tls.puerto, contexto)

    assert lab.servidor_certs.pedidos == ["/intermedia.crt"], (
        "no se siguió la dirección del certificado del SITIO. Con la pieza "
        "equivocada del servidor de por medio, seguir la dirección de ésta "
        "lleva a un certificado que no completa nada — es exactamente lo que "
        "pasó con el BCV.")


def test_NO_SE_ACEPTA_UN_CERTIFICADO_QUE_NO_ES_EL_EMISOR(lab, caplog):
    """La dirección de adentro puede contestar cualquier cosa.

    Se baja de una dirección que viene escrita en un certificado que todavía no
    se pudo verificar. Aceptar lo que sea que devuelva sería llenar la lista de
    certificados que no pintan nada — y en el caso del BCV fue justamente un
    certificado de USERTrust que no completaba ningún eslabón.

    Sólo se acepta si su «sujeto» es el «emisor» del certificado al que le falta
    la firma.
    """
    lab.servidor_certs.cerrar()
    otro = ServidorDeCertificados(
        lab.intermedia_mala.public_bytes(serialization.Encoding.DER))
    lab.servidor_certs = otro
    lab.k_hoja, lab.hoja = _hoja(lab.k_int, lab.intermedia, HOST,
                                 otro.direccion)
    srv = lab.servir_incompleta()

    with caplog.at_level(logging.WARNING, logger="services.cadena_tls"):
        with pytest.raises(cadena_tls.NoSePudoCompletar):
            corre(cadena_tls.piezas_para(HOST, srv.puerto,
                                         permitir_loopback=True))

    registro = "\n".join(r.getMessage() for r in caplog.records)
    assert "ninguno es quien firmó" in registro, (
        "se aceptó un certificado que no es el emisor, o no se dijo que no lo "
        "era")
    assert cadena_tls._GUARDADAS == {}


def test_si_el_servidor_manda_la_cadena_entera_no_se_pide_nada(lab):
    """Lo obvio: si no falta nada, no se sale a la red."""
    lab.servidor_tls = ServidorTLS(
        lab.tmp, [lab.hoja, lab.intermedia_mala, lab.intermedia], lab.k_hoja)
    contexto = corre(cadena_tls.contexto_para(
        HOST, lab.servidor_tls.puerto, permitir_loopback=True))
    _conectar_verificando(lab.servidor_tls.puerto, contexto)
    assert lab.servidor_certs.pedidos == [], "se bajó algo que ya estaba"


def test_NO_SE_BAJA_LO_QUE_EL_SERVIDOR_YA_MANDO(tmp_path, monkeypatch):
    """Cuatro eslabones, y el servidor manda uno de los dos del medio.

        raíz  ←  intermedia ALTA  ←  intermedia BAJA  ←  sitio

    El servidor manda el certificado del sitio y la BAJA, pero no la ALTA. Como
    la baja ya vino, no hay que volver a pedirla: se baja UNA sola pieza, la que
    falta de verdad.

    LA VERSION ANTERIOR DE ESTE TEST NO PROBABA NADA. Servía la cadena completa,
    así que salía por el atajo de «ya cierra» sin llegar nunca a la línea que
    decía estar probando. Al romperla a propósito seguía en verde.
    """
    raiz_k, raiz_c = _raiz("Raiz Honda")
    # `largo=1`: esta autoridad puede firmar otra autoridad debajo.
    alta_k, alta_c = _intermedia(raiz_k, raiz_c, "Intermedia Alta", largo=1)

    archivo_raiz = str(tmp_path / "raices.pem")
    with open(archivo_raiz, "wb") as f:
        f.write(_pem(raiz_c))
    monkeypatch.setattr(cadena_tls, "archivo_de_raices", lambda: archivo_raiz)
    cadena_tls.olvidar()

    srv_alta = ServidorDeCertificados(
        alta_c.public_bytes(serialization.Encoding.DER))
    baja_k, baja_c = _intermedia(alta_k, alta_c, "Intermedia Baja",
                                 direccion=srv_alta.direccion)
    srv_baja = ServidorDeCertificados(
        baja_c.public_bytes(serialization.Encoding.DER))
    hoja_k, hoja_c = _hoja(baja_k, baja_c, HOST, srv_baja.direccion)

    servidor = ServidorTLS(str(tmp_path), [hoja_c, baja_c], hoja_k)
    try:
        contexto = corre(cadena_tls.contexto_para(
            HOST, servidor.puerto, permitir_loopback=True))
        _conectar_verificando(servidor.puerto, contexto)

        assert srv_baja.pedidos == [], (
            "se volvió a pedir la pieza que el servidor YA había mandado")
        assert len(srv_alta.pedidos) == 1, (
            f"se esperaba una sola descarga, hubo {len(srv_alta.pedidos)}")
    finally:
        servidor.cerrar()
        srv_alta.cerrar()
        srv_baja.cerrar()
        cadena_tls.olvidar()
