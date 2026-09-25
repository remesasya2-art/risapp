"""
tests/test_cofre.py — Los documentos de identidad, cifrados en la base.

QUE PROTEGE

    Los documentos del KYC son el conjunto de datos más sensible de la
    plataforma: no son montos, son las caras y los documentos de gente que manda
    plata a Venezuela. Vivían en la base como texto, así que quien llegara a la
    base los veía todos.

LA GARANTIA QUE MAS SE PRUEBA ACA, Y POR QUE

    **Lo que entra tiene que volver idéntico.**

    Cifrar crea un peligro nuevo y peor que el que resuelve: un error en el
    cifrado no se ve el día que pasa. Se ve meses después, cuando alguien
    necesita abrir un documento y no puede — y para entonces ya no queda el
    original en ningún lado.

    Por eso la mitad de este archivo son casos de ida y vuelta: fotos grandes,
    con acentos, con bytes que no son texto, vacías, al límite. Un cifrado que
    funciona con `"hola"` y rompe con un JPEG de 3 MB es exactamente el que se
    descubre tarde.

LO SEGUNDO QUE MAS SE PRUEBA

    Que nada se prenda solo, y que un problema de llave no tumbe la aplicación.
    Con el cofre apagado —lo que va a estar mientras no se decida lo contrario—
    todo tiene que comportarse EXACTAMENTE como antes.
"""
import base64
import hashlib
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")
pytest.importorskip("cryptography", reason="`cryptography` no está instalado")

from conftest import los_py_de, usar_base                                      # noqa: E402
from services import cofre                                          # noqa: E402


def una_llave():
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


@pytest.fixture
def cerrado(monkeypatch):
    """El cofre prendido, con una llave nueva por test."""
    monkeypatch.setenv(cofre.VARIABLE_MODO, "cifrando")
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    monkeypatch.delenv(cofre.VARIABLE_LLAVE_ANTERIOR, raising=False)


@pytest.fixture
def apagado(monkeypatch):
    monkeypatch.delenv(cofre.VARIABLE_MODO, raising=False)
    monkeypatch.delenv(cofre.VARIABLE_LLAVE, raising=False)
    monkeypatch.delenv(cofre.VARIABLE_LLAVE_ANTERIOR, raising=False)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def corre(coro):
    import asyncio
    return asyncio.run(coro)


def foto(bytes_=60000, tipo="image/jpeg"):
    return f"data:{tipo};base64," + base64.b64encode(os.urandom(bytes_)).decode()


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que entra vuelve idéntico. Es la garantía que importa.
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("original", [
    foto(1),                                      # una foto de un byte
    foto(60_000),                                 # una foto normal
    foto(2_000_000),                              # una foto grande de teléfono
    foto(1000, "image/png"),
    foto(1000, "image/webp"),
    "data:image/jpeg;base64,",                    # `data:` sin datos
    "/api/media/twilio/ACxxx/Media/MExxx",        # una ruta, no una foto
    "https://almacen.test/kyc/abc.jpg",
    "un texto con acentos: ñáéíóú ¿? ¡!",
    "x" * 100_000,                                # texto largo sin estructura
])
def test_LO_QUE_ENTRA_VUELVE_IDENTICO(cerrado, original):
    """Si esto falla, se pierden documentos de personas — y no el día que pasa,
    sino meses después, cuando ya no queda el original."""
    assert cofre.abrir(cofre.guardar(original)) == original


def test_una_foto_con_bytes_que_no_son_texto_vuelve_igual(cerrado):
    """Los bytes de un JPEG no son texto válido en ninguna codificación. Un
    cifrado que pase por `str` en algún lado los rompe."""
    crudos = bytes(range(256)) * 400
    original = "data:image/jpeg;base64," + base64.b64encode(crudos).decode()
    devuelto = cofre.abrir(cofre.guardar(original))
    assert devuelto == original
    assert base64.b64decode(devuelto.split(",", 1)[1]) == crudos


def test_EL_TAMANO_NO_CRECE(cerrado):
    """Un documento de Mongo no puede pasar de 16 MB y una verificación con
    cuatro fotos ya se acerca. Cifrar el base64 y volver a codificarlo lo haría
    crecer un tercio, lo que acercaría el problema en vez de dejarlo igual."""
    original = foto(3_000_000)
    crecimiento = len(cofre.guardar(original)) / len(original) - 1
    assert crecimiento < 0.01, f"creció {crecimiento:.1%}"


def test_dos_guardadas_del_mismo_valor_dan_resultados_distintos(cerrado):
    """Si dos fotos iguales se cifraran igual, quien mire la base sabría que dos
    personas subieron el mismo documento sin poder abrirlo. Cada guardada usa un
    número al azar distinto."""
    uno, otro = cofre.guardar("la misma foto"), cofre.guardar("la misma foto")
    assert uno != otro
    assert cofre.abrir(uno) == cofre.abrir(otro) == "la misma foto"


def test_lo_guardado_no_contiene_el_original(cerrado):
    """La comprobación tonta que conviene tener: que efectivamente esté cifrado
    y no envuelto."""
    original = "el numero de documento es 12345678"
    guardado = cofre.guardar(original)
    assert "12345678" not in guardado
    assert "documento" not in guardado


# ══════════════════════════════════════════════════════════════════════════
# 2. Que un byte cambiado se note
# ══════════════════════════════════════════════════════════════════════════

def test_UN_BYTE_CAMBIADO_DEVUELVE_NADA_Y_NO_BASURA(cerrado):
    """AES-GCM autentica además de cifrar. Sin eso, un documento corrupto en la
    base saldría en la pantalla como una foto rota que nadie sabe explicar — y
    peor, alguien podría alterarlo a propósito sin que se note."""
    guardado = cofre.guardar(foto(1000))
    roto = guardado[:-8] + "AAAAAAAA"
    assert cofre.abrir(roto) is None


@pytest.mark.parametrize("basura", [
    cofre.MARCA, cofre.MARCA + "x", cofre.MARCA + "image/jpeg:no-es-base64!!",
    cofre.MARCA + ":", cofre.MARCA + "::::",
])
def test_un_valor_cifrado_mal_formado_no_revienta(cerrado, basura):
    assert cofre.abrir(basura) is None


def test_con_la_llave_equivocada_no_se_abre(cerrado, monkeypatch):
    guardado = cofre.guardar("un documento")
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    assert cofre.abrir(guardado) is None


# ══════════════════════════════════════════════════════════════════════════
# 3. Nada se prende solo, y nada se rompe por sorpresa
# ══════════════════════════════════════════════════════════════════════════

def test_POR_OMISION_EL_COFRE_ESTA_APAGADO(apagado):
    """Mientras no se decida lo contrario, todo se comporta EXACTAMENTE como
    antes. Un cambio que empieza a cifrar solo en un despliegue es la forma de
    que alguien se entere el día que ya no puede abrir un documento."""
    assert cofre.modo() == "apagado"
    assert cofre.guardar("una foto") == "una foto"
    assert cofre.abrir("una foto") == "una foto"


@pytest.mark.parametrize("valor", ["", "  ", "si", "true", "1", "CIFRAR", "on"])
def test_un_valor_raro_en_el_modo_no_prende_el_cifrado(valor, monkeypatch):
    """La dirección del error importa: un dedazo en la variable tiene que dejar
    todo como está, nunca prender algo irreversible."""
    monkeypatch.setenv(cofre.VARIABLE_MODO, valor)
    assert cofre.modo() == "apagado"


def test_SE_CORTA_ANTES_DE_GUARDAR_EN_CLARO_CREYENDO_QUE_CIFRA(monkeypatch):
    """La peor de las tres situaciones posibles: creer que se está cifrando y
    no. No se nota nunca. Así que si el modo dice cifrar y la llave no sirve, se
    levanta en vez de guardar."""
    monkeypatch.setenv(cofre.VARIABLE_MODO, "cifrando")
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, "no-es-una-llave")
    with pytest.raises(cofre.CofreCerrado):
        cofre.guardar("un documento")


@pytest.mark.parametrize("mala", ["", "   ", "no-es-base64!!", "MTIz",
                                  base64.urlsafe_b64encode(b"x" * 16).decode()])
def test_una_llave_mal_puesta_se_reconoce(mala, monkeypatch):
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, mala)
    assert cofre.llave_actual() is None


def test_LEER_SIGUE_FUNCIONANDO_CON_LOS_DOS_FORMATOS(cerrado):
    """Es lo que hace que la migración sea gradual y que volver atrás sea
    posible. Sin esto, prender el cofre exigiría migrar todo de una."""
    en_claro = "data:image/jpeg;base64,AAAA"
    cifrado = cofre.guardar(en_claro)
    assert cofre.abrir(en_claro) == en_claro
    assert cofre.abrir(cifrado) == en_claro


def test_guardar_algo_ya_cifrado_no_lo_cifra_dos_veces(cerrado):
    """La migración se puede cortar y volver a correr. Si cifrara de nuevo lo ya
    cifrado, cada corrida agregaría una capa y la última quedaría inabrible."""
    una_vez = cofre.guardar("una foto")
    assert cofre.guardar(una_vez) == una_vez


def test_abrir_algo_en_claro_no_lo_toca(apagado):
    """`abrir` se llama en varios lugares, algunos sobre valores que ya vienen
    en claro. Tiene que ser inocuo."""
    for valor in ["/api/x.png", "data:image/png;base64,AAA", "", None, 42]:
        assert cofre.abrir(valor) == valor


# ══════════════════════════════════════════════════════════════════════════
# 4. La huella: lo que hace esto operable por una persona
# ══════════════════════════════════════════════════════════════════════════

def test_la_huella_no_revela_la_llave(monkeypatch):
    """Se muestra en el panel y se anota en papel al lado de la llave. Si de la
    huella se pudiera sacar la llave, todo el procedimiento sería al revés."""
    llave = una_llave()
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, llave)
    huella = cofre.huella()
    assert len(huella) == 8
    assert huella not in llave
    assert llave[:8] not in huella


def test_la_misma_llave_da_siempre_la_misma_huella(monkeypatch):
    """Es para lo que sirve: cotejar la que está corriendo contra la anotada."""
    llave = una_llave()
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, llave)
    primera = cofre.huella()
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, llave)
    assert cofre.huella() == primera


def test_dos_llaves_distintas_dan_huellas_distintas(monkeypatch):
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    una = cofre.huella()
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    assert cofre.huella() != una


def test_sin_llave_la_huella_lo_dice(apagado):
    assert cofre.huella() == "(sin llave)"


# ══════════════════════════════════════════════════════════════════════════
# 5. Cambiar la llave sin destruir lo viejo
# ══════════════════════════════════════════════════════════════════════════

def test_LA_LLAVE_ANTERIOR_SE_SIGUE_PROBANDO_AL_LEER(cerrado, monkeypatch):
    """Sin esto, rotar la llave sería destruir todo lo cifrado con la vieja: la
    rotación pasaría de ser una operación de higiene a una catástrofe."""
    vieja = os.environ[cofre.VARIABLE_LLAVE]
    guardado_con_la_vieja = cofre.guardar("un documento de antes")

    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    monkeypatch.setenv(cofre.VARIABLE_LLAVE_ANTERIOR, vieja)

    assert cofre.abrir(guardado_con_la_vieja) == "un documento de antes"
    # Y lo nuevo se guarda con la nueva.
    assert cofre.abrir(cofre.guardar("uno de ahora")) == "uno de ahora"


def test_sacar_la_llave_anterior_deja_de_abrir_lo_viejo(cerrado, monkeypatch):
    """Es el paso final de una rotación, y conviene que esté probado: es
    exactamente lo que NO hay que hacer antes de terminar de migrar."""
    vieja = os.environ[cofre.VARIABLE_LLAVE]
    guardado = cofre.guardar("de antes")
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    monkeypatch.delenv(cofre.VARIABLE_LLAVE_ANTERIOR, raising=False)
    assert cofre.abrir(guardado) is None
    monkeypatch.setenv(cofre.VARIABLE_LLAVE_ANTERIOR, vieja)
    assert cofre.abrir(guardado) == "de antes"


# ══════════════════════════════════════════════════════════════════════════
# 6. El testigo: saber si la llave es la buena sin restaurar nada
# ══════════════════════════════════════════════════════════════════════════

def test_el_testigo_confirma_que_la_llave_es_la_correcta(base, cerrado):
    async def caso():
        await cofre.sellar_testigo(base)
        estado = await cofre.revisar(base)
        assert estado["ok"] is True
        assert estado["modo"] == "cifrando"
    corre(caso())


def test_CON_LA_LLAVE_EQUIVOCADA_EL_TESTIGO_LO_GRITA(base, cerrado, monkeypatch):
    """El caso que motiva todo el testigo: alguien cambia la variable por otra
    llave y, sin esto, nadie se entera hasta que necesita abrir un documento —
    que puede ser dentro de tres meses."""
    corre(cofre.sellar_testigo(base))
    huella_buena = cofre.huella()

    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    estado = corre(cofre.revisar(base))

    assert estado["ok"] is False
    assert huella_buena in estado["detalle"]
    assert "docs/la-llave-del-cofre.md" in estado["detalle"]


def test_el_testigo_se_sella_una_sola_vez(base, cerrado):
    """Volver a sellarlo con otra llave borraría la única prueba de cuál era la
    correcta, justo cuando más falta hace."""
    async def caso():
        primero = await cofre.sellar_testigo(base)
        segundo = await cofre.sellar_testigo(base)
        assert primero["testigo"] == segundo["testigo"]
        assert await base.config.count_documents({"_id": "cofre_testigo"}) == 1
    corre(caso())


def test_con_el_cofre_apagado_no_se_sella_nada(base, apagado):
    async def caso():
        assert await cofre.sellar_testigo(base) is None
        estado = await cofre.revisar(base)
        assert estado["ok"] is True and estado["modo"] == "apagado"
    corre(caso())


def test_LA_BASE_CAIDA_NO_SE_CONFUNDE_CON_UNA_LLAVE_MALA(cerrado):
    """Los dos son «no ok», y confundirlos es peligroso de verdad.

    Quien lee «la llave no es la correcta» cuando en realidad la base está
    caída se pone a cambiar la llave — que es exactamente lo único que NO hay
    que tocar. El motivo los separa, y el mensaje lo dice con todas las letras.
    """
    class _BaseCaida:
        def __getattr__(self, _):
            raise RuntimeError("no hay conexión")

        def __getitem__(self, _):
            raise RuntimeError("no hay conexión")

    estado = corre(cofre.revisar(_BaseCaida()))
    assert estado["ok"] is False
    assert estado["motivo"] == "sin_base"
    assert "no la cambies" in estado["detalle"].lower()


def test_la_llave_equivocada_si_se_llama_por_su_nombre(base, cerrado, monkeypatch):
    """El otro lado de la moneda: cuando SI es la llave, hay que decirlo."""
    corre(cofre.sellar_testigo(base))
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, una_llave())
    estado = corre(cofre.revisar(base))
    assert estado["motivo"] == "llave_equivocada"


def test_modo_cifrando_sin_llave_avisa_pero_no_revienta(base, monkeypatch):
    """La aplicación tiene que poder arrancar igual: lo único que falla es el
    KYC. Un cajón que no abre no puede cerrar el negocio entero."""
    monkeypatch.setenv(cofre.VARIABLE_MODO, "cifrando")
    monkeypatch.delenv(cofre.VARIABLE_LLAVE, raising=False)
    estado = corre(cofre.revisar(base))
    assert estado["ok"] is False
    assert "no hay una llave válida" in estado["detalle"].lower()


# ══════════════════════════════════════════════════════════════════════════
# 7. Que los cuatro campos pasen por el cofre en TODOS lados
# ══════════════════════════════════════════════════════════════════════════

def test_abrir_varios_deja_el_resto_del_documento_intacto(cerrado):
    doc = {"verification_id": "v1", "full_name": "Ana",
           "cpf_image": cofre.guardar("data:image/png;base64,AAA"),
           "selfie_image": "data:image/png;base64,BBB"}   # en claro, del pasado
    abierto = cofre.abrir_varios(doc, cofre.CAMPOS_KYC)
    assert abierto["verification_id"] == "v1"
    assert abierto["full_name"] == "Ana"
    assert abierto["cpf_image"] == "data:image/png;base64,AAA"
    assert abierto["selfie_image"] == "data:image/png;base64,BBB"
    assert doc["cpf_image"] != abierto["cpf_image"], "modificó el original"


# Dónde se leen y se escriben estos campos hoy. La lista se mantiene a mano y el
# barrido de abajo la contrasta contra el código, así que una ruta nueva que lea
# un documento sin abrirlo se ve.
PUNTOS = [
    ("routes/misc.py", "guardar"),          # el envío del KYC
    ("routes/kyc_admin.py", "abrir"),       # el panel de revisión
    ("routes/admin/usuarios.py", "abrir_varios"),    # la ficha del usuario
    # La ficha del cliente. Estaba en `routes/google_drive.py`, que subía el
    # PDF a Google Drive; ese camino se quitó y ahora la ficha se descarga
    # desde el servidor. El cofre sigue en el medio: si las imágenes
    # estuvieran cifradas, hay que abrirlas para dibujarlas en el PDF.
    ("services/ficha_del_cliente.py", "abrir"),
]


@pytest.mark.parametrize("archivo, funcion", PUNTOS)
def test_cada_punto_pasa_por_el_cofre(archivo, funcion):
    fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    assert f"cofre.{funcion}" in fuente, (
        f"{archivo} toca un documento del KYC sin pasar por cofre.{funcion}()")


def test_LAS_CUATRO_FOTOS_PASAN_POR_EL_COFRE_AL_GUARDAR():
    """La comprobación de arriba tiene un hueco que este test tapa: mira que
    `cofre.guardar` aparezca EN EL ARCHIVO, no que las cuatro fotos pasen por él.

    Se descubrió rompiendo a mano una sola de las cuatro líneas —la del frente
    del documento— y viendo que ningún test se ponía en rojo. O sea que un campo
    podía dejar de cifrarse en silencio, que es exactamente la falla que no se
    nota hasta que ya no importa.

    Acá se mira el ARBOL: qué variable termina en cada campo del documento que
    se guarda, y si esa variable pasó por `cofre.guardar`.
    """
    import ast

    ruta = os.path.join(_BACKEND, "routes", "misc.py")
    arbol = ast.parse(open(ruta, encoding="utf-8").read())

    # `x = cofre.guardar(x)` → las variables que quedaron cifradas.
    guardadas = set()
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Call)):
            continue
        llamada = nodo.value.func
        if not (isinstance(llamada, ast.Attribute) and llamada.attr == "guardar"
                and isinstance(llamada.value, ast.Name) and llamada.value.id == "cofre"):
            continue
        for destino in nodo.targets:
            if isinstance(destino, ast.Name):
                guardadas.add(destino.id)

    # Qué variable termina en cada campo del documento que se inserta.
    sin_cifrar = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Dict):
            continue
        for clave, valor in zip(nodo.keys, nodo.values):
            if not (isinstance(clave, ast.Constant) and clave.value in cofre.CAMPOS_KYC):
                continue
            # El valor puede ser la variable, o un condicional sobre ella.
            nombres = {n.id for n in ast.walk(valor) if isinstance(n, ast.Name)}
            if not (nombres & guardadas):
                sin_cifrar.append(f"{clave.value} (línea {clave.lineno})")

    assert not sin_cifrar, (
        "estos campos se guardan sin pasar por cofre.guardar():\n  "
        + "\n  ".join(sin_cifrar))


def test_NINGUNA_RUTA_LEE_UN_DOCUMENTO_SIN_ABRIR_EL_COFRE():
    """El barrido. Si mañana una pantalla nueva lee `selfie_image` de la base y
    la manda al navegador sin abrirla, la persona ve un texto cifrado en vez de
    una foto — y nadie entiende por qué."""
    declarados = {a for a, _ in PUNTOS}
    huerfanos = []
    for carpeta in ("routes", "services"):
        raiz = os.path.join(_BACKEND, carpeta)
        for archivo in los_py_de(raiz):
            if not archivo.endswith(".py"):
                continue
            rel = f"{carpeta}/{archivo}"
            if rel in declarados or archivo == "cofre.py":
                continue
            texto = open(os.path.join(raiz, archivo), encoding="utf-8").read()
            # ¿Lee alguno de los campos DESDE un documento?
            lee = any(f'.get("{campo}")' in texto or f'["{campo}"]' in texto
                      for campo in cofre.CAMPOS_KYC)
            if lee and "cofre" not in texto:
                huerfanos.append(rel)
    assert not huerfanos, (
        "estos archivos leen un documento del KYC sin abrir el cofre:\n  "
        + "\n  ".join(huerfanos)
        + "\n\nPasalo por services/cofre.py: abrir() es inocuo sobre un valor "
          "que ya está en claro.")


def test_el_barrido_conoce_los_campos():
    """Si `CAMPOS_KYC` quedara vacía, el barrido pasaría sin mirar nada."""
    assert len(cofre.CAMPOS_KYC) == 4


# ══════════════════════════════════════════════════════════════════════════
# 8. Lo que sale al panel: la huella, nunca la llave
# ══════════════════════════════════════════════════════════════════════════

def test_LO_QUE_SE_PUBLICA_AL_PANEL_NO_CONTIENE_LA_LLAVE(base, cerrado):
    """`/admin/ledger/cofre` alimenta la tarjeta C-06, que existe para que la
    huella se pueda cotejar de un vistazo contra la anotada en papel.

    Esa comodidad no puede convertirse en «y de paso copiá la llave del panel»:
    la huella se comparte a propósito, la llave no sale nunca. Se comprueba
    sobre lo que la función DEVUELVE y no sobre el texto del archivo, porque un
    grep de la palabra «llave» encuentra los comentarios.
    """
    corre(cofre.sellar_testigo(base))
    llave = os.environ[cofre.VARIABLE_LLAVE]
    estado = corre(cofre.revisar(base))

    entero = repr(estado)
    assert llave not in entero
    assert llave.rstrip("=") not in entero
    # Ni siquiera un pedazo suficiente para adivinar el resto.
    assert llave[:12] not in entero

    # Y lo que sí tiene que estar, está.
    assert estado["huella"] == cofre.huella()


def test_el_panel_recibe_los_campos_que_dibuja(base, cerrado):
    """La tarjeta lee `modo`, `ok`, `huella` y `detalle`. Si el servidor deja de
    mandar alguno, la tarjeta cae en «no se pudo comprobar» — que es seguro,
    pero se lee como un error del servidor y nadie sabría que faltó un campo."""
    corre(cofre.sellar_testigo(base))
    estado = corre(cofre.revisar(base))
    for campo in ("modo", "ok", "huella", "detalle", "motivo"):
        assert campo in estado, f"falta «{campo}», que la pantalla usa"


def test_el_modo_que_sale_al_panel_es_uno_de_los_dos_que_conoce(base, apagado):
    """La pantalla trata cualquier otro valor como «no se pudo leer». Si el
    servidor inventara un tercer modo, la tarjeta se quedaría en gris sin que
    nadie entienda por qué."""
    estado = corre(cofre.revisar(base))
    assert estado["modo"] in ("apagado", "cifrando")


def test_LA_RUTA_DEL_PANEL_ES_SOLO_PARA_EL_SUPER_ADMINISTRADOR():
    """La huella no revela la llave, pero decir «los documentos están sin
    cifrar» ya es información útil para quien esté mirando por dónde entrar."""
    import ast
    fuente = open(os.path.join(_BACKEND, "routes", "ledger_admin.py"),
                  encoding="utf-8").read()
    arbol = ast.parse(fuente)
    for fn in ast.walk(arbol):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name != "estado_del_cofre":
            continue
        # Se recorren los ARGUMENTOS del árbol y no su texto:
        # `get_source_segment` sobre un nodo de argumentos devuelve vacío, y un
        # test que compara contra vacío pasa o falla por el motivo equivocado.
        guardias = {n.id for n in ast.walk(fn.args) if isinstance(n, ast.Name)}
        assert "get_super_admin" in guardias, \
            f"la ruta del cofre no exige super administrador (tiene: {guardias})"
        return
    raise AssertionError("no se encontró la ruta del cofre")


# ══════════════════════════════════════════════════════════════════════════
# El guión, que lo corre una persona en su computadora
# ══════════════════════════════════════════════════════════════════════════

def _sin_pywebpush(carpeta):
    """Arma una carpeta que, puesta en PYTHONPATH, hace desaparecer `pywebpush`.

    No alcanza con no tenerlo instalado: acá SI está (los tests lo reemplazan
    por un doble). Un test que dependiera de que falte pasaría en la máquina de
    desarrollo y no probaría nada en ninguna otra.

    `sitecustomize.py` lo importa Python solo, antes de correr el guión.
    """
    (carpeta / "sitecustomize.py").write_text(
        "import sys\n"
        "\n"
        "class _NoEstaInstalado:\n"
        "    def find_spec(self, nombre, ruta=None, destino=None):\n"
        "        if nombre == 'pywebpush' or nombre.startswith('pywebpush.'):\n"
        "            raise ModuleNotFoundError(\"No module named 'pywebpush'\")\n"
        "        return None\n"
        "\n"
        "sys.meta_path.insert(0, _NoEstaInstalado())\n",
        encoding="utf-8")
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = os.pathsep.join(
        [str(carpeta)] + ([entorno["PYTHONPATH"]] if entorno.get("PYTHONPATH") else []))
    return entorno


def test_EL_GUION_CREA_UNA_LLAVE_SIN_TENER_PYWEBPUSH(tmp_path):
    """La orden `crear` no toca la base, no lee nada y no manda ningún aviso.
    Tiene que correr en la computadora de quien va a guardar la llave, que no
    tiene instaladas las dependencias del servidor.

    Antes no corría: el guión hacía `from services import cofre`, eso ejecutaba
    `services/__init__.py`, y ahí está `pywebpush`. La persona veía
    «No module named 'pywebpush'» justo en el paso donde menos sentido tiene.
    """
    import subprocess
    guion = os.path.join(_BACKEND, "scripts", "cofre.py")
    r = subprocess.run([sys.executable, guion, "crear"],
                       capture_output=True, text=True, timeout=180,
                       env=_sin_pywebpush(tmp_path))
    assert r.returncode == 0, f"salió {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "pywebpush" not in r.stderr, r.stderr
    assert "COFRE_LLAVE=" in r.stdout, r.stdout
    assert "Huella:" in r.stdout, r.stdout


def test_EL_GUION_VERIFICA_LA_LLAVE_SIN_TENER_PYWEBPUSH(tmp_path):
    """`verificar` es el paso que hay que dar ANTES de prender el cofre, y se da
    con la llave a mano en la máquina de quien la anotó. Si esta orden no corre
    ahí, «comprobá que copiaste bien la llave» es un consejo imposible de seguir.

    Sin base no puede decir si es LA llave de los documentos, y eso está bien:
    lo que se prueba acá es que llega a leerla y a mostrar su huella.
    """
    import subprocess
    guion = os.path.join(_BACKEND, "scripts", "cofre.py")
    entorno = _sin_pywebpush(tmp_path)
    entorno[cofre.VARIABLE_LLAVE] = una_llave()
    # Una dirección de base que no existe: el guión tiene que contestar sobre la
    # llave igual, y no morirse esperando a Mongo.
    entorno["MONGO_URL"] = "mongodb://127.0.0.1:1/"
    r = subprocess.run([sys.executable, guion, "verificar"],
                       capture_output=True, text=True, timeout=180,
                       env=entorno)
    assert "pywebpush" not in r.stderr, r.stderr
    assert "La llave se lee bien" in r.stdout, f"{r.stdout}\n{r.stderr}"


# ══════════════════════════════════════════════════════════════════════════
# Una llave escrita como texto: la que se puede poner sin abrir una terminal
# ══════════════════════════════════════════════════════════════════════════
#
# POR QUE ESTA PARTE EXISTE
#
#   El cofre estuvo apagado desde que se escribió, y no por falta de código:
#   porque la llave tenía que ser 44 caracteres en base64, y producirlos exigía
#   correr Python en una terminal. El dueño del proyecto no escribe código, así
#   que el paso que protege los documentos quedaba fuera de su alcance.
#
#   Ahora `COFRE_LLAVE` acepta además cualquier texto largo, del que se derivan
#   los 32 bytes. Lo que se prueba acá es que eso no rompió la primera forma.

UN_TEXTO_DE_LLAVE = "Kt7-vraLLaveGeneradaPorUnGestor-9fQz2xWb"


def test_una_llave_escrita_como_texto_sirve():
    """Lo que genera el botón «generar contraseña» de cualquier gestor."""
    crudo, motivo = cofre.bytes_y_motivo(UN_TEXTO_DE_LLAVE)
    assert motivo == ""
    assert crudo is not None and len(crudo) == 32


def test_la_misma_llave_escrita_da_siempre_los_mismos_32_bytes():
    """Si esto no se cumpliera, un reinicio del servidor dejaría de abrir los
    documentos cifrados un minuto antes. Es la propiedad de la que depende todo
    lo demás."""
    primero, _ = cofre.bytes_y_motivo(UN_TEXTO_DE_LLAVE)
    segundo, _ = cofre.bytes_y_motivo(UN_TEXTO_DE_LLAVE)
    assert primero == segundo
    # Y con los espacios de los bordes que deja cualquier copiar y pegar.
    conEspacios, _ = cofre.bytes_y_motivo(f"  {UN_TEXTO_DE_LLAVE}\n")
    assert conEspacios == primero


def test_UNA_LLAVE_EN_BASE64_SIGUE_DANDO_EXACTAMENTE_SUS_PROPIOS_BYTES():
    """LA GUARDA QUE PROTEGE LOS DOCUMENTOS YA CIFRADOS.

    Una llave en base64 tiene que seguir dando los 32 bytes que representa, y
    NO el sha256 de su texto. Si el orden de las dos formas se invirtiera, cada
    llave en base64 ya en uso pasaría a dar otros 32 bytes, y todos los
    documentos cifrados con ella quedarían ilegibles para siempre.

    No es una hipótesis: es exactamente el error que se comete al «unificar» las
    dos ramas en una.
    """
    crudos = os.urandom(32)
    texto = base64.urlsafe_b64encode(crudos).decode("ascii")
    obtenidos, motivo = cofre.bytes_y_motivo(texto)
    assert motivo == ""
    assert obtenidos == crudos, "una llave en base64 dejó de dar sus propios bytes"
    # Y no el derivado del texto, que es el error que se quiere impedir.
    assert obtenidos != hashlib.sha256(
        cofre._SAL_DE_LA_DERIVACION + texto.encode()).digest()


def test_una_llave_en_base64_sin_el_relleno_tambien_entra():
    """43 caracteres, que es la misma llave sin el `=` del final. Un gestor de
    contraseñas o un copiar y pegar pueden comerse ese carácter."""
    crudos = os.urandom(32)
    texto = base64.urlsafe_b64encode(crudos).decode("ascii").rstrip("=")
    assert len(texto) == 43
    obtenidos, _ = cofre.bytes_y_motivo(texto)
    assert obtenidos == crudos


def test_dos_contrasenas_que_se_diferencian_en_un_signo_dan_llaves_distintas():
    """Dos textos distintos, dos llaves distintas. Suena obvio y casi no lo fue.

    `b64decode` sin `validate` DESCARTA en silencio los caracteres que no son
    del alfabeto, así que la sospecha era que dos contraseñas diferenciadas sólo
    por un «!» perdieran ese carácter y dieran la MISMA llave — y entonces el
    cotejo diría «sí, es tu llave» sobre una llave que no es.

    No puede pasar, y por un motivo que conviene dejar escrito: quitar un
    carácter cambia el largo, y un largo que no es múltiplo de cuatro hace
    fallar el decodificador antes de devolver nada. El texto cae entonces en la
    derivación, que sí mira todos los caracteres.

    Este test pasa por eso y no por una comprobación de alfabeto. Hubo una, y se
    sacó justamente porque no se la podía poner en rojo rompiéndola.
    """
    base = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")[:43]
    una, _ = cofre.bytes_y_motivo(base + "!")
    otra, _ = cofre.bytes_y_motivo(base + "?")
    assert una is not None and otra is not None
    assert una != otra, "dos llaves distintas dieron los mismos bytes"


@pytest.mark.parametrize("mala,parte_del_motivo", [
    ("corta", "al menos"),
    ("a" * (cofre.MINIMO_DE_LA_LLAVE - 1), "al menos"),
    ("a" * 40, "caracteres distintos"),
    ("abababababababababababababababab", "caracteres distintos"),
    ("", "ninguna llave"),
    (None, "ninguna llave"),
])
def test_una_llave_pobre_no_entra_y_dice_por_que(mala, parte_del_motivo):
    """El motivo se prueba junto con el rechazo. Un «no sirve» sin motivo manda
    a alguien a probar cosas al azar sobre la única cosa del sistema que no
    tiene vuelta atrás."""
    crudo, motivo = cofre.bytes_y_motivo(mala)
    assert crudo is None
    assert parte_del_motivo in motivo


def test_el_cifrado_de_punta_a_punta_con_una_llave_escrita(base, monkeypatch):
    """La prueba que importa: una llave puesta como texto cifra y abre de
    verdad, y el testigo la reconoce. Las dos formas tienen que ser
    intercambiables para el resto del módulo."""
    monkeypatch.setenv(cofre.VARIABLE_MODO, "cifrando")
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, UN_TEXTO_DE_LLAVE)
    monkeypatch.delenv(cofre.VARIABLE_LLAVE_ANTERIOR, raising=False)

    original = foto(5000)
    sellado = cofre.guardar(original)
    assert cofre.esta_cifrado(sellado)
    assert cofre.abrir(sellado) == original

    corre(cofre.sellar_testigo(base))
    estado = corre(cofre.revisar(base))
    assert estado["ok"] is True
    assert estado["modo"] == "cifrando"


# ══════════════════════════════════════════════════════════════════════════
# La llave que sortea el panel
# ══════════════════════════════════════════════════════════════════════════

def test_la_llave_nueva_trae_su_huella_y_las_dos_se_corresponden():
    nueva = cofre.llave_nueva()
    assert set(nueva) == {"llave", "huella"}
    crudo, motivo = cofre.bytes_y_motivo(nueva["llave"])
    assert motivo == "" and len(crudo) == 32
    assert cofre.huella(crudo) == nueva["huella"]


def test_dos_llaves_nuevas_no_son_la_misma():
    """Una llave sorteada que se repite no es una llave. El día que esto falle,
    todas las instalaciones estarían usando la misma."""
    llaves = {cofre.llave_nueva()["llave"] for _ in range(25)}
    assert len(llaves) == 25


def test_LA_LLAVE_GENERADA_NO_VIAJA_A_LA_AUDITORIA():
    """De la llave sorteada sólo se registra la HUELLA.

    Escribirla en el libro de auditoría la convertiría en un secreto guardado en
    texto dentro de la base — que es exactamente lo que el cofre existe para
    evitar, y encima en la colección que más gente puede leer.

    Se mira el árbol del código y no la respuesta, porque una llamada a
    `registrar` con el campo equivocado no falla: escribe.
    """
    import ast
    fuente = open(os.path.join(_BACKEND, "routes", "ledger_admin.py"),
                  encoding="utf-8").read()
    for fn in ast.walk(ast.parse(fuente)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name != "llave_nueva_del_cofre":
            continue
        registros = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "registrar"]
        assert registros, "la ruta dejó de registrar en auditoría"
        for llamada in registros:
            textos = {n.value for n in ast.walk(llamada)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            assert "llave" not in textos, \
                f"la auditoría de la llave nueva menciona «llave»: {textos}"
            assert "huella" in textos, "la auditoría dejó de guardar la huella"
        return
    raise AssertionError("no se encontró la ruta que genera la llave")


# ══════════════════════════════════════════════════════════════════════════
# El cotejo: «¿la llave que anoté sirve?»
# ══════════════════════════════════════════════════════════════════════════

CAMPOS_DEL_COTEJO = {"sirve", "huella", "es_la_que_corre",
                     "abre_los_documentos", "detalle"}


def test_EL_COTEJO_DEVUELVE_ESTOS_CAMPOS_Y_NINGUNO_MAS(base, cerrado):
    """Un conjunto exacto, no un «contiene».

    Un `assert "llave" not in respuesta` pasa con el producto roto de dos formas
    distintas: alcanza con llamar al campo `clave`, o con anidarlo dentro de
    otro. Exigir el conjunto completo obliga a que cualquier campo nuevo pase
    por acá, que es donde se decide si puede salir.
    """
    r = corre(cofre.cotejar(base, os.environ[cofre.VARIABLE_LLAVE]))
    assert set(r) == CAMPOS_DEL_COTEJO


def test_el_cotejo_no_devuelve_la_llave_en_ningun_valor(base, cerrado):
    """La segunda guarda, independiente de la de arriba: que no salga escondida
    dentro del texto de un campo que sí está permitido."""
    puesta = os.environ[cofre.VARIABLE_LLAVE]
    r = corre(cofre.cotejar(base, puesta))
    for campo, valor in r.items():
        assert puesta not in str(valor), f"la llave apareció en «{campo}»"


def test_el_cotejo_reconoce_la_llave_que_cifro_los_documentos(base, cerrado):
    corre(cofre.sellar_testigo(base))
    r = corre(cofre.cotejar(base, os.environ[cofre.VARIABLE_LLAVE]))
    assert r["sirve"] is True
    assert r["es_la_que_corre"] is True
    assert r["abre_los_documentos"] is True
    assert r["huella"] == cofre.huella()


def test_el_cotejo_dice_que_no_con_otra_llave(base, cerrado):
    """Una llave válida pero que no es la de los documentos. Las tres respuestas
    son distintas y tienen que poder contradecirse entre ellas."""
    corre(cofre.sellar_testigo(base))
    r = corre(cofre.cotejar(base, una_llave()))
    assert r["sirve"] is True
    assert r["es_la_que_corre"] is False
    assert r["abre_los_documentos"] is False
    assert "NO abre" in r["detalle"]


def test_SIN_TESTIGO_EL_COTEJO_NO_DICE_QUE_NO_DICE_QUE_NO_SABE(base, apagado):
    """`None`, nunca `False`.

    Con el cofre recién configurado no hay nada cifrado con qué comparar. Decir
    «esta llave no abre los documentos» ahí manda a alguien a buscar un problema
    que no existe — y peor: a cambiar la llave, que es lo único que no hay que
    tocar.
    """
    r = corre(cofre.cotejar(base, UN_TEXTO_DE_LLAVE))
    assert r["sirve"] is True
    assert r["abre_los_documentos"] is None


def test_SIN_LLAVE_PUESTA_TAMPOCO_SE_DICE_QUE_NO_ES_LA_QUE_CORRE(base, apagado):
    """Lo mismo que arriba, para la otra pregunta, y lo encontró una captura.

    Con el cofre apagado no hay ninguna llave puesta en el servidor. Decir «no
    es la misma que está corriendo» es cierto y se pinta en rojo, y entonces el
    estado NORMAL de la aplicación —el cofre sin prender— se ve como si algo
    estuviera roto. Cada respuesta era correcta por separado; el conjunto
    asustaba. Eso no lo ve un test: se vio mirando la pantalla.
    """
    r = corre(cofre.cotejar(base, UN_TEXTO_DE_LLAVE))
    assert r["es_la_que_corre"] is None


def test_el_cotejo_de_una_llave_pobre_explica_el_motivo(base, cerrado):
    """Y no contesta las otras dos preguntas.

    Con el cofre prendido y una llave puesta, el servidor PODRIA contestar «no
    es la que corre». No lo hace: si el texto no tiene forma de llave, ninguna
    de las dos preguntas siguientes se evaluó, y contestarlas pinta de rojo tres
    renglones cuando el que importa es el primero. Se vio en una captura.
    """
    r = corre(cofre.cotejar(base, "corta"))
    assert r["sirve"] is False
    assert r["es_la_que_corre"] is None
    assert r["abre_los_documentos"] is None
    assert "al menos" in r["detalle"]


def test_PROBAR_UNA_LLAVE_EQUIVOCADA_NO_DISPARA_LA_ALARMA(base, cerrado, caplog):
    """El aviso «NO SE PUDO ABRIR un documento» es la única alarma grave de este
    módulo: significa que hay documentos que no se van a poder recuperar.

    Cotejar una llave equivocada es una respuesta esperada, no una alarma. Si
    cada intento la disparara, el aviso que no se puede ignorar aparecería
    decenas de veces por una persona probando copias de papel — y a partir de
    ahí nadie lo mira.
    """
    import logging
    corre(cofre.sellar_testigo(base))
    with caplog.at_level(logging.ERROR, logger="services.cofre"):
        r = corre(cofre.cotejar(base, una_llave()))
    assert r["abre_los_documentos"] is False
    assert "NO SE PUDO ABRIR" not in caplog.text, caplog.text


def test_pero_el_cofre_de_verdad_si_grita_cuando_no_abre(base, cerrado, caplog):
    """El otro lado de la guarda de arriba. Sin este test, silenciar la alarma
    entera pasaría las dos pruebas."""
    import logging
    sellado = cofre.guardar("una foto")
    with caplog.at_level(logging.ERROR, logger="services.cofre"):
        os.environ[cofre.VARIABLE_LLAVE] = una_llave()
        assert cofre.abrir(sellado) is None
    assert "NO SE PUDO ABRIR" in caplog.text


# ══════════════════════════════════════════════════════════════════════════
# Las dos rutas nuevas del panel
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta", ["llave_nueva_del_cofre",
                                  "cotejar_la_llave_del_cofre"])
def test_LAS_RUTAS_DE_LA_LLAVE_SON_SOLO_PARA_EL_SUPER_ADMINISTRADOR(ruta):
    """Sortear una llave no revela nada, y cotejar tampoco devuelve la llave.
    Pero el cotejo sí contesta «esta llave abre los documentos», y eso en manos
    de cualquiera con una sesión es un oráculo para probar llaves."""
    import ast
    fuente = open(os.path.join(_BACKEND, "routes", "ledger_admin.py"),
                  encoding="utf-8").read()
    for fn in ast.walk(ast.parse(fuente)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name != ruta:
            continue
        guardias = {n.id for n in ast.walk(fn.args) if isinstance(n, ast.Name)}
        assert "get_super_admin" in guardias, \
            f"«{ruta}» no exige super administrador (tiene: {guardias})"
        return
    raise AssertionError(f"no se encontró la ruta «{ruta}»")


def test_LA_PANTALLA_NO_GUARDA_LA_LLAVE_EN_EL_NAVEGADOR():
    """La llave sorteada vive en memoria y se va con la pestaña.

    `localStorage` sobrevive al cierre del navegador y no se borra nunca solo.
    Una llave ahí es un secreto que queda en la computadora de quien abrió el
    panel —prestada, robada, vendida— sin que nadie se acuerde de que quedó.

    SE MIRA EL CODIGO SIN SUS COMENTARIOS, y no el archivo entero, porque el
    comentario que explica esta decisión NOMBRA lo que no hay que usar. La
    primera versión de esta guarda se puso roja acusando a ese comentario —el
    mismo tropiezo que ya pasó con la guarda de la pantalla de registro—, y una
    guarda que acusa a su propia explicación es una guarda que alguien borra por
    molesta. El limpiador es el de `test_el_codigo_de_referido_llega`, con su
    prueba propia, en vez de un segundo limpiador que se desincronice.
    """
    from test_el_codigo_de_referido_llega import _sin_comentarios

    ruta = os.path.join(_BACKEND, "..", "frontend", "src", "components",
                        "admin", "SeguridadFinanciera.jsx")
    vivo = _sin_comentarios(open(ruta, encoding="utf-8").read())
    assert "function Cofre" in vivo, \
        "cambió la pantalla del cofre: este test ya no mira lo que cree"
    for guardadero in ("localStorage", "sessionStorage", "document.cookie"):
        assert guardadero not in vivo, \
            f"la pantalla del cofre usa {guardadero}"
