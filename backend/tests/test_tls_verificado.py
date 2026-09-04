"""
tests/test_tls_verificado.py — Nadie apaga la verificación del certificado.

QUE PASABA

    `services/bcv_scraper.py` consultaba el sitio del BCV con `verify=False`,
    o sea sin verificar el certificado TLS. Cualquiera capaz de interponerse
    en esa conexión —una red comprometida, un DNS envenenado— servía su propia
    página y la aplicación se creía la tasa que le mandaran.

    El valor raspado no es el que se le cobra al cliente —eso vive en
    `db.rates` y esto escribe en `db.bcv_rates`— pero `accounting_engine` lo
    lee como referencia BCV, así que una tasa falsa distorsiona la
    contabilidad.

POR QUE UN TEST DEL PROYECTO ENTERO Y NO SOLO DEL SCRAPER

    `verify=False` es lo que uno escribe cuando un sitio tiene la cadena de
    certificados rota y hay que salir del paso. Es una línea, funciona al
    instante, y no vuelve a mirarse. Va a pasar otra vez, en otro archivo.

    Y es de lo primero que revisa la debida diligencia de un proveedor de
    pagos: el requisito de TLS 1.2+ no se cumple si la verificación está
    apagada.
"""
import os
import pathlib
import re

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

SALTEAR = {"__pycache__", ".git", "node_modules", "venv", ".venv"}

# Las formas de apagar la verificación que se escriben sin pensar.
APAGADO = re.compile(
    r"verify\s*=\s*False"
    r"|ssl\._create_unverified_context"
    r"|CERT_NONE"
    r"|check_hostname\s*=\s*False"
    r"|curl.*(-k|--insecure)\b")


def _archivos():
    for p in _RAIZ.rglob("*.py"):
        if any(x in p.parts for x in SALTEAR):
            continue
        # Este archivo NOMBRA los patrones para poder buscarlos.
        if p.name == "test_tls_verificado.py":
            continue
        yield p


def test_nadie_apaga_la_verificacion_del_certificado():
    hallazgos = []
    for archivo in _archivos():
        for n, linea in enumerate(archivo.read_text(encoding="utf-8",
                                                    errors="ignore").splitlines(), 1):
            sin_comentario = linea.split("#", 1)[0]
            if APAGADO.search(sin_comentario):
                hallazgos.append(f"{archivo.relative_to(_RAIZ)}:{n}  {linea.strip()[:90]}")

    assert not hallazgos, (
        "Hay conexiones que no verifican el certificado TLS:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nSi el sitio de destino tiene la cadena incompleta, la solución "
          "es aportar el certificado intermedio, no dejar de mirar. Apagar la "
          "verificación deja que cualquiera en el medio sirva su propia "
          "respuesta.")


def test_el_scraper_del_bcv_falla_cerrado():
    """Sin certificado válido no se guarda ninguna tasa.

    Caer a una conexión sin verificar sería peor que no tener el dato: una
    tasa que pudo poner un tercero entra a la contabilidad como si fuera del
    Banco Central.
    """
    from services import bcv_scraper

    fuente = pathlib.Path(bcv_scraper.__file__).read_text(encoding="utf-8")
    assert "raise" in fuente.split("async def fetch_bcv_rates")[1][:1500], (
        "el scraper no levanta cuando falla la conexión: se traga el error y "
        "sigue como si nada")


def test_la_escotilla_existe_pero_avisa():
    """`BCV_TLS_INSEGURO` reactiva el comportamiento viejo para el día que la
    cadena del BCV se rompa otra vez.

    No es un equivalente: tiene que avisar en CADA consulta. Un agujero
    ruidoso y deliberado no es lo mismo que uno silencioso y permanente.
    """
    from services import bcv_scraper

    assert hasattr(bcv_scraper, "BCV_TLS_INSEGURO")
    assert bcv_scraper.BCV_TLS_INSEGURO is False, (
        "la escotilla está activada por defecto, que es exactamente lo que se "
        "vino a arreglar")

    cuerpo = pathlib.Path(bcv_scraper.__file__).read_text(
        encoding="utf-8").split("async def fetch_bcv_rates")[1][:900]
    assert "logger.warning" in cuerpo, "la escotilla no avisa cuando se usa"
