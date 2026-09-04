"""
tests/test_lenguaje_de_las_paginas_publicas.py — Lo que las páginas públicas
no pueden decir.

LA REGLA

    `Landing.jsx` la deja escrita desde antes: las páginas públicas NO
    mencionan remesas ni transferencias internacionales. Por pedido expreso se
    suman «envíos transfronterizos» y «cambio de dinero». Todo se describe
    como soluciones digitales, que es la línea principal de servicio.

POR QUE ES UN TEST Y NO UN COMENTARIO

    Un comentario en la cabecera de un archivo lo lee quien abre ESE archivo.
    Las páginas públicas son cinco y crecen; el texto lo edita cualquiera, a
    veces para "mejorar la redacción", y una palabra que vuelve no rompe nada
    —la página compila igual, se ve igual— así que nadie se entera hasta que
    la ve alguien de afuera.

    Se revisa el FUENTE y no el bundle: el bundle es la salida compilada, y
    revisarlo haría fallar el test por una compilación vieja que nadie
    regeneró.

QUE SE REVISA Y QUE NO

    Sólo las páginas que se sirven sin sesión iniciada, más los componentes
    que ellas montan. Dentro de la aplicación —después del login— el
    vocabulario del negocio es otro asunto: ahí el usuario ya sabe qué
    contrató, y esta regla no aplica.
"""
import os
import pathlib
import re
import unicodedata

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

# Las pantallas que ve alguien sin cuenta, y lo que montan.
PUBLICAS = [
    "frontend/src/pages/Landing.jsx",
    "frontend/src/pages/LegalPage.jsx",
    "frontend/src/pages/ComoFunciona.jsx",
    "frontend/src/pages/Seguimiento.jsx",
    "frontend/src/components/Footer.jsx",
]

# Se comparan sin tildes y en minúscula, para que «remesa» no se escape
# escrita como «Remesa» ni «transfronterizo» como «transfronterizos».
PROHIBIDAS = [
    "remesa",
    "transferencia internacional",
    "transferencias internacionales",
    "transfronteriz",
    "cambio de dinero",
    "casa de cambio",
    "envio de dinero",
    "giro internacional",
]


def _plano(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn")
    return sin_tildes.lower()


def _archivos_publicos():
    faltan = [r for r in PUBLICAS if not (_RAIZ / r).exists()]
    if faltan:
        pytest.fail(
            "Estas páginas públicas ya no están donde dice la lista. Si se "
            "movieron o se renombraron, actualizá PUBLICAS; si se borraron, "
            "sacalas. Dejar la lista desactualizada apaga el test en "
            f"silencio:\n  " + "\n  ".join(faltan))
    return [(r, (_RAIZ / r).read_text(encoding="utf-8")) for r in PUBLICAS]


def test_ninguna_pagina_publica_usa_el_vocabulario_prohibido():
    hallazgos = []
    for ruta, texto in _archivos_publicos():
        for n, linea in enumerate(texto.splitlines(), 1):
            plano = _plano(linea)
            # La cabecera de cada archivo NOMBRA las palabras para explicar la
            # regla. Nombrarlas ahí es documentar; usarlas en un texto que se
            # muestra es lo que no va.
            if plano.lstrip().startswith(("*", "//", "/*", "{/*")):
                continue
            for mala in PROHIBIDAS:
                if mala in plano:
                    hallazgos.append(f"{ruta}:{n}  «{mala}»  →  {linea.strip()[:90]}")

    assert not hallazgos, (
        "Vocabulario prohibido en una página pública:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nEstas pantallas describen el servicio como soluciones digitales. "
          "Es una regla de negocio, no una preferencia de estilo.")


def test_la_pagina_principal_nombra_las_soluciones_digitales():
    """La contracara: que la línea principal de servicio esté dicha.

    Sin esto, alguien podría cumplir el test de arriba borrando texto hasta
    que no quede nada que decir.

    Se ignoran los comentarios, y no es un detalle: la cabecera del archivo
    explica la regla y nombra la frase, así que buscarla en el archivo entero
    da verde aunque la portada ya no la diga. Se comprobó: la primera versión
    de este test sobrevivió a esa mutación exacta.
    """
    fuente = (_RAIZ / "frontend/src/pages/Landing.jsx").read_text(encoding="utf-8")
    visible = "\n".join(
        l for l in fuente.splitlines()
        if not _plano(l).lstrip().startswith(("*", "//", "/*", "{/*")))

    assert "soluciones digitales" in _plano(visible), (
        "La página principal ya no menciona las soluciones digitales, que son "
        "la línea principal de servicio.")


# La identificación del operador —razón social, CNPJ— va en UN solo lugar: la
# ficha de empresa del documento legal. Repetirla en cada página pública tiene
# dos costos: expone los datos del titular en pantallas que no los necesitan, y
# obliga a acordarse de cambiarlos en todas cuando algo se actualiza.
LEGAL = "frontend/src/pages/LegalPage.jsx"
IDENTIFICACION = [
    (re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"), "el CNPJ"),
    (re.compile(r"carmen\s+hernandez\s+barreto"), "la razón social del titular"),
]


def test_la_identificacion_del_titular_vive_solo_en_el_documento_legal():
    """En ninguna otra pantalla pública, y en el documento legal sí.

    Las dos mitades importan. Sacarla de todas partes dejaría a la plataforma
    sin identificar a su operador, que es lo que exige el Decreto 7.962/2013
    para el comercio electrónico en Brasil y lo primero que revisa una debida
    diligencia. Dejarla repetida en cada página la expone sin necesidad.
    """
    de_mas = []
    for ruta, texto in _archivos_publicos():
        if ruta == LEGAL:
            continue
        for n, linea in enumerate(texto.splitlines(), 1):
            plano = _plano(linea)
            if plano.lstrip().startswith(("*", "//", "/*", "{/*")):
                continue
            for patron, que in IDENTIFICACION:
                if patron.search(plano):
                    de_mas.append(f"{ruta}:{n}  {que}")

    assert not de_mas, (
        "La identificación del titular aparece fuera del documento legal:\n  "
        + "\n  ".join(de_mas)
        + "\n\nVa en un solo lugar: la ficha de empresa de LegalPage.jsx. "
          "Desde otras páginas, enlazá a /legal#empresa.")

    legal = _plano((_RAIZ / LEGAL).read_text(encoding="utf-8"))
    faltan = [q for patron, q in IDENTIFICACION if not patron.search(legal)]
    assert not faltan, (
        "Falta en el documento legal: " + ", ".join(faltan)
        + ". Ahí sí tiene que estar: es la identificación del operador, y sin "
          "ella la plataforma no dice quién la opera.")


def test_las_paginas_publicas_no_publican_ninguna_direccion_de_correo():
    """El único canal de atención es el centro de ayuda de la aplicación."""
    correo = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    ejemplos = ("@example.com", "@ejemplo.com", "@dominio.com",
                "@empresa.com", "@correo.com")

    hallazgos = []
    for ruta, texto in _archivos_publicos():
        for n, linea in enumerate(texto.splitlines(), 1):
            for hallado in correo.findall(linea):
                if any(hallado.lower().endswith(d) for d in ejemplos):
                    continue
                hallazgos.append(f"{ruta}:{n}  {hallado}")

    assert not hallazgos, (
        "Hay direcciones de correo en páginas públicas:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nEl único canal de atención es el centro de ayuda: enlazá a "
          "/support.")
