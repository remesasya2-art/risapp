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


def test_todo_enlace_a_una_seccion_legal_apunta_a_una_que_existe():
    """Un ancla rota no rompe nada: la página abre igual, arriba de todo.

    Por eso hace falta un test. Pasó de verdad: al reescribir la página legal
    se renombró la sección `datos-fiscales` a `empresa`, y el enlace del pie
    de página quedó apuntando al nombre viejo. Nada falló, nada avisó, y el
    visitante que buscaba los datos del operador aterrizaba en el encabezado.

    Se revisa todo el frontend, no sólo las páginas públicas: los enlaces al
    marco legal también salen de pantallas con sesión iniciada.
    """
    legal = (_RAIZ / LEGAL).read_text(encoding="utf-8")
    existentes = set(re.findall(r"id:\s*'([a-z0-9-]+)'", legal))
    assert existentes, "no se encontraron las secciones declaradas en LegalPage"

    rotos = []
    frontend = _RAIZ / "frontend" / "src"
    for archivo in frontend.rglob("*"):
        if not archivo.is_file() or archivo.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        if any(parte in ("node_modules", "dist", "build") for parte in archivo.parts):
            continue
        for n, linea in enumerate(archivo.read_text(encoding="utf-8",
                                                    errors="ignore").splitlines(), 1):
            for ancla in re.findall(r"/legal#([a-z0-9-]+)", linea):
                if ancla not in existentes:
                    rotos.append(
                        f"{archivo.relative_to(_RAIZ)}:{n}  #{ancla}")

    assert not rotos, (
        "Enlaces a secciones del marco legal que no existen:\n  "
        + "\n  ".join(rotos)
        + f"\n\nLas secciones declaradas son: {', '.join(sorted(existentes))}.")


# ══════════════════════════════════════════════════════════════════════════
# Los controles internos no se publican
# ══════════════════════════════════════════════════════════════════════════
#
# La distinción es entre PROMESA y MECANISMO.
#
#   Promesa  : «toda entrada y salida de saldo deja un asiento».
#   Mecanismo: «hay una comprobación periódica de los saldos», «un
#              administrador puede ajustar un saldo o cambiar una tasa», «el
#              personal con acceso administrativo tiene el segundo factor
#              obligatorio».
#
# La promesa es lo que necesita quien decide si confía. El mecanismo es lo que
# necesita quien está buscando por dónde entrar: le dice qué cuenta vale la
# pena tomar, qué defensa va a encontrar del otro lado, y qué tiene que imitar
# una página de phishing para que el engaño funcione. «Periódica» es, además,
# la palabra que anuncia que existe una ventana.
#
# Nada de esto se borró del proyecto: está en
# `docs/dossier-tecnico-de-seguridad.md`, que es interno y se entrega bajo
# acuerdo a quien tenga que auditarlo. Lo que cambia es quién puede leerlo sin
# pedirlo.
#
# El riesgo que justifica un test y no un comentario es el mismo de siempre: el
# texto de estas páginas se reescribe para «mostrar que somos serios», y
# enumerar controles es exactamente lo que parece serio.

CONTROLES = [
    ("acceso administrativo", "que hay una superficie de administración, y cuál"),
    ("panel de administracion", "que hay una superficie de administración, y cuál"),
    ("ajustar un saldo", "que un saldo se puede crear a mano"),
    ("ajuste de saldo", "que un saldo se puede crear a mano"),
    ("modificar permisos", "el inventario de lo que puede hacer una cuenta interna"),
    ("cambiar una tasa", "el inventario de lo que puede hacer una cuenta interna"),
    ("comprobacion periodica", "que el control no es continuo: anuncia la ventana"),
    ("revision periodica", "que el control no es continuo: anuncia la ventana"),
    ("conciliacion periodica", "que el control no es continuo: anuncia la ventana"),
    ("se revisa a mano", "que no hay verificación automática que sortear"),
    ("altas y bajas de personal", "el tamaño y la rotación del equipo interno"),
]

# El segundo factor es el caso que no se puede resolver con una lista de
# palabras, y el primer intento de este test se equivocó justamente ahí.
#
# «Tu cuenta puede protegerse con verificación en dos pasos» es una función
# que se le OFRECE al usuario: decirlo lo ayuda a protegerse y no le sirve de
# nada a un atacante, que ya lo va a descubrir al primer intento de entrar.
#
# «El personal con acceso administrativo la tiene obligatoria» es otra cosa:
# habla de una puerta que el visitante no usa, y le dice a quien prepara un
# engaño contra un empleado que la pantalla falsa tiene que pedir el código —
# si no, el empleado sospecha.
#
# La diferencia no está en la palabra sino en de quién se habla. Por eso se
# busca la coincidencia de las dos cosas en la MISMA oración.
FACTOR = ("dos pasos", "segundo factor", "doble factor", "dos factores",
          "dos etapas", "2fa", "mfa")
PERSONAL = ("personal", "administrador", "administradores", "administrativo",
            "administrativa", "colaborador", "colaboradores",
            "equipo interno", "nuestro equipo")


def _visible(texto: str) -> str:
    """El fuente sin los comentarios, en una sola tira y sin tildes.

    Las cabeceras de estos archivos NOMBRAN las frases prohibidas para
    explicar por qué lo están. Contarlas sería castigar la documentación de la
    regla, y además haría imposible dejarla escrita donde se lee.
    """
    return _plano(" ".join(
        l.strip() for l in texto.splitlines()
        if not _plano(l).lstrip().startswith(("*", "//", "/*", "{/*"))))


def test_ninguna_pagina_publica_describe_los_controles_internos():
    """Se busca sobre el texto ARMADO, no línea por línea.

    Esto lo encontró una mutación: «comprobación periódica» escrito con el
    salto de línea en el medio —que es como queda cuando el editor acomoda el
    párrafo— no lo veía ninguna búsqueda por línea, y el test daba verde con la
    frase publicada. La versión por líneas de los tests de más arriba tiene el
    mismo agujero; se arregló acá primero porque acá la frase que importa son
    tres palabras y se parte sola.
    """
    hallazgos = []
    for ruta, texto in _archivos_publicos():
        armado = _visible(texto)
        for frase, porque in CONTROLES:
            donde = armado.find(frase)
            if donde >= 0:
                hallazgos.append(
                    f"{ruta}  «{frase}»  →  le dice a un desconocido {porque}"
                    f"\n      …{armado[max(0, donde - 40):donde + 70].strip()}…")

    assert not hallazgos, (
        "Una página pública está describiendo un control interno:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nUna página pública promete un RESULTADO; no describe el "
          "MECANISMO que lo garantiza. El detalle va en "
          "docs/dossier-tecnico-de-seguridad.md, que es interno.")


def test_ninguna_pagina_publica_cuenta_como_se_protege_el_personal():
    hallazgos = []
    for ruta, texto in _archivos_publicos():
        for oracion in _visible(texto).split("."):
            if any(f in oracion for f in FACTOR) and any(p in oracion for p in PERSONAL):
                hallazgos.append(f"{ruta}  →  {oracion.strip()[:120]}")

    assert not hallazgos, (
        "Una página pública cuenta cómo se protegen las cuentas internas:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nOfrecerle el segundo factor AL USUARIO está bien y ayuda. "
          "Contar qué exige la plataforma A SU PERSONAL le dice a quien "
          "prepara un engaño contra un empleado qué tiene que imitar la "
          "pantalla falsa. Eso va en el dossier interno.")


def test_las_paginas_publicas_siguen_prometiendo_la_trazabilidad():
    """La contracara, otra vez: que no se resuelva borrando la sección entera.

    Sin este test, la forma más fácil de pasar los dos de arriba es dejar la
    página sin decir nada sobre qué queda registrado — y eso es peor que el
    problema que se estaba arreglando: quien evalúa la plataforma se va sin
    saber si sus movimientos dejan rastro.
    """
    visible = _visible((_RAIZ / "frontend/src/pages/ComoFunciona.jsx")
                       .read_text(encoding="utf-8"))

    faltan = [f for f in ("asiento", "queda registrado") if f not in visible]
    assert not faltan, (
        "La página dejó de prometer la trazabilidad: falta "
        + ", ".join(f"«{f}»" for f in faltan)
        + ". Los controles no se publican, pero la promesa de que todo "
          "movimiento deja rastro sí: es lo que necesita quien decide si "
          "confía.")


def test_la_portada_le_sigue_ofreciendo_el_segundo_factor_al_usuario():
    """Y la otra contracara: que el test de arriba no borre la oferta.

    La forma más fácil de dejar de hablar del segundo factor del personal es
    dejar de hablar del segundo factor. Sería un retroceso: la función existe,
    es opcional, y el usuario que no sabe que está no la va a prender.
    """
    visible = _visible((_RAIZ / "frontend/src/pages/Landing.jsx")
                       .read_text(encoding="utf-8"))

    assert any(f in visible for f in FACTOR), (
        "La portada dejó de ofrecerle la verificación en dos pasos al usuario. "
        "Lo que no se publica es cómo se protege el PERSONAL; la función que "
        "el usuario puede prender en su cuenta sí se cuenta.")
