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

from conftest import usar_base                                      # noqa: E402
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
    ("routes/admin.py", "abrir_varios"),    # la ficha del usuario
    ("routes/google_drive.py", "abrir"),    # el PDF que se sube a Drive
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
        for archivo in sorted(os.listdir(raiz)):
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
