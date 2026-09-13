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
import ast
import asyncio
import logging
import os
import pathlib
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

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


def _sin_textos(codigo: str) -> str:
    """El archivo con sus CADENAS DE TEXTO tapadas, y nada más.

    POR QUE HACE FALTA

        Los comentarios y los docstrings SI pueden nombrar lo que está
        prohibido: son para quien lee el archivo, no instrucciones para la
        máquina. Y en este repositorio ya pasó dos veces. La segunda:
        `services/cadena_tls.py` explica en su encabezado que NO tiene ningún
        `verify=False` escondido, y esa misma frase puso roja a esta guarda.

        Borrar la frase sería arreglar el síntoma: la próxima persona que
        explique la regla vuelve a tropezar con lo mismo.

    POR QUE CON EL ARBOL DE SINTAXIS Y NO CON UNA EXPRESION REGULAR

        Las comillas anidadas y las cadenas de varias líneas no se recortan
        bien a mano.

    Y SE TAPA LA CADENA, NO LA LINEA. La diferencia importa: en
    `Client(base_url="https://x", verify=False)` hay un texto y código de
    verdad en la MISMA línea. Borrar la línea entera dejaría a la guarda ciega
    justo donde tiene que mirar. Lo comprueba el test de abajo.

    Un archivo que no parsea NO se salta en silencio: se devuelve tal cual,
    para que la guarda lo siga mirando.
    """
    try:
        arbol = ast.parse(codigo)
    except SyntaxError:
        return codigo

    # `col_offset` cuenta BYTES, no caracteres, y acá se escribe en español:
    # contando caracteres, cada acento corre el recorte y se come código.
    lineas = [linea.encode("utf-8") for linea in codigo.splitlines()]

    def tapar(i, desde, hasta):
        if not (0 <= i < len(lineas)):
            return
        linea = lineas[i]
        hasta = len(linea) if hasta is None else min(hasta, len(linea))
        desde = min(desde, len(linea))
        lineas[i] = linea[:desde] + b" " * max(0, hasta - desde) + linea[hasta:]

    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)):
            continue
        primera = nodo.lineno - 1
        ultima = (nodo.end_lineno or nodo.lineno) - 1
        if primera == ultima:
            tapar(primera, nodo.col_offset, nodo.end_col_offset)
        else:
            tapar(primera, nodo.col_offset, None)
            for i in range(primera + 1, ultima):
                tapar(i, 0, None)
            tapar(ultima, 0, nodo.end_col_offset)

    return "\n".join(linea.decode("utf-8", "ignore") for linea in lineas)


def test_el_limpiador_de_textos_sirve():
    """La comprobación de la guarda de abajo, exigiéndole las dos mitades.

    Si tapara de menos, la guarda se acusa a sí misma y alguien la borra por
    molesta. Si tapara de más, se pone verde por no tener nada que mirar.
    """
    muestra = (
        'def f():\n'
        '    """Acá NO hay ningún verify=False escondido — con acentós."""\n'
        '    return httpx.Client(base_url="https://x", verify=False)\n'
    )
    limpio = _sin_textos(muestra)
    assert "verify=False" in limpio, (
        "el limpiador se comió el `verify=False` que está en el CODIGO, en la "
        "misma línea que un texto. La guarda quedaría ciega justo donde "
        "importa.")
    assert limpio.count("verify=False") == 1, (
        "el limpiador dejó el `verify=False` que está adentro del docstring. La "
        "guarda va a acusar al comentario que explica la regla, como ya pasó "
        "con services/cadena_tls.py.")


def test_nadie_apaga_la_verificacion_del_certificado():
    hallazgos = []
    for archivo in _archivos():
        crudo = archivo.read_text(encoding="utf-8", errors="ignore")
        for n, linea in enumerate(_sin_textos(crudo).splitlines(), 1):
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


# ══════════════════════════════════════════════════════════════════════════
# El raspador del BCV, probado por su CONDUCTA y no por la forma del archivo
# ══════════════════════════════════════════════════════════════════════════
#
# Estos dos tests miraban el texto del archivo: si la palabra «raise» aparecía
# en los primeros 1500 caracteres después de `async def fetch_bcv_rates`, y si
# «logger.warning» aparecía en los primeros 900.
#
# Al mover ese código a dos funciones nuevas —el reintento que completa la
# cadena de certificados— los dos se pusieron rojos SIN QUE NADA SE HUBIERA
# ROTO. Medían dónde estaban escritas las líneas, no lo que hacía el programa.
# Un test así cuesta el doble: no agarra el defecto que dice vigilar, y cobra
# un rojo cada vez que alguien ordena el archivo.
#
# Ahora se simula el fallo y se mira qué hace el raspador.


class _Respuesta:
    """Lo mínimo que `fetch_bcv_rates` le pide a una respuesta."""
    text = "<html><body></body></html>"


def test_EL_RASPADOR_FALLA_CERRADO_SI_EL_CERTIFICADO_NO_VALIDA(monkeypatch):
    """Sin certificado válido no se trae ninguna tasa.

    Caer a una conexión sin verificar sería peor que no tener el dato: una tasa
    que pudo poner un tercero entra a la contabilidad como si fuera del Banco
    Central.
    """
    import httpx
    from services import bcv_scraper, cadena_tls

    usados = []

    async def no_valida(verificacion):
        usados.append(verificacion)
        raise httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
            "unable to get local issuer certificate")

    async def tampoco_se_completa(*_a, **_k):
        raise cadena_tls.NoSePudoCompletar("la cadena no cierra")

    monkeypatch.setattr(bcv_scraper, "_pedir", no_valida)
    monkeypatch.setattr(cadena_tls, "contexto_para", tampoco_se_completa)

    with pytest.raises(httpx.ConnectError):
        asyncio.run(bcv_scraper.fetch_bcv_rates())

    # LA MITAD QUE IMPORTA: no alcanza con que levante. Tiene que no haber
    # intentado la conexión sin verificar, que es lo que este módulo vino a
    # sacar y lo que un «arreglo» apurado vuelve a poner.
    assert False not in usados, (
        "después de fallar la verificación se intentó una conexión SIN "
        "verificar. Una tasa que pudo poner un tercero entra a la contabilidad "
        "como si fuera del Banco Central.")


def test_si_la_cadena_se_puede_completar_se_reintenta_verificando(monkeypatch):
    """La otra mitad: fallar cerrado no puede significar no intentar.

    Si esto no pasara, el arreglo de la cadena incompleta no serviría de nada y
    nadie se enteraría, porque el test de arriba seguiría verde.
    """
    import httpx
    from services import bcv_scraper, cadena_tls

    contexto_falso = object()
    usados = []

    async def segun_la_verificacion(verificacion):
        usados.append(verificacion)
        if verificacion is contexto_falso:
            return _Respuesta()
        raise httpx.ConnectError("certificate verify failed")

    async def se_completa(*_a, **_k):
        return contexto_falso

    monkeypatch.setattr(bcv_scraper, "_pedir", segun_la_verificacion)
    monkeypatch.setattr(cadena_tls, "contexto_para", se_completa)

    resultado = asyncio.run(bcv_scraper.fetch_bcv_rates())
    assert "fetched_at" in resultado
    assert usados == [True, contexto_falso], (
        "el primer intento tiene que ser el estricto, y el segundo el que lleva "
        "la pieza que falta — nunca uno sin verificar")


def test_un_fallo_de_red_no_dispara_el_reintento(monkeypatch):
    """Completar la cadena es para un fallo de certificado, no para cualquiera.

    Si se disparara con todo, cada caída de red se llevaría un saludo TLS extra
    y una descarga, y el registro diría «cadena incompleta» cuando el problema
    era otro."""
    import httpx
    from services import bcv_scraper, cadena_tls

    intentos = []
    completar = []

    async def sin_red(verificacion):
        intentos.append(verificacion)
        raise httpx.ConnectError("[Errno 111] Connection refused")

    async def anotar(*_a, **_k):
        # SE ANOTA, NO SE LEVANTA. La primera versión de este doble levantaba
        # un `AssertionError`, y el `except Exception` del reintento se lo
        # tragaba: la mutación que hacía sonar la alarma con cualquier fallo de
        # conexión pasaba este test en verde.
        completar.append(True)
        raise cadena_tls.NoSePudoCompletar("no debería haberse llamado")

    monkeypatch.setattr(bcv_scraper, "_pedir", sin_red)
    monkeypatch.setattr(cadena_tls, "contexto_para", anotar)

    with pytest.raises(httpx.ConnectError):
        asyncio.run(bcv_scraper.fetch_bcv_rates())
    assert intentos == [True]
    assert completar == [], (
        "se intentó completar la cadena de certificados por un fallo de red. "
        "Cada caída de red se lleva un saludo TLS extra y una descarga, y el "
        "registro dice «cadena incompleta» cuando el problema era otro.")


def test_LA_ESCOTILLA_EXISTE_PERO_AVISA_EN_CADA_CONSULTA(monkeypatch, caplog):
    """`BCV_TLS_INSEGURO` reactiva el comportamiento viejo para el día que la
    conexión al BCV se rompa por algo que completar la cadena no arregle.

    No es un equivalente: tiene que avisar en CADA consulta. Un agujero ruidoso
    y deliberado no es lo mismo que uno silencioso y permanente.
    """
    from services import bcv_scraper

    assert bcv_scraper.BCV_TLS_INSEGURO is False, (
        "la escotilla está activada por defecto, que es exactamente lo que se "
        "vino a arreglar")

    usados = []

    async def anota(verificacion):
        usados.append(verificacion)
        return _Respuesta()

    monkeypatch.setattr(bcv_scraper, "BCV_TLS_INSEGURO", True)
    monkeypatch.setattr(bcv_scraper, "_pedir", anota)

    with caplog.at_level(logging.WARNING, logger="services.bcv_scraper"):
        asyncio.run(bcv_scraper.fetch_bcv_rates())
        asyncio.run(bcv_scraper.fetch_bcv_rates())

    avisos = [r for r in caplog.records if "BCV_TLS_INSEGURO" in r.getMessage()]
    assert len(avisos) == 2, (
        f"la escotilla avisó {len(avisos)} vez/veces en dos consultas. Tiene "
        "que avisar en CADA una: un agujero silencioso no es lo mismo que uno "
        "ruidoso y deliberado.")
    assert usados == [False, False]
