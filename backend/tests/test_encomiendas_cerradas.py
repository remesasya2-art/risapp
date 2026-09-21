"""
tests/test_encomiendas_cerradas.py — El envío de paquetes se suspende por ahora.

POR QUE EXISTE ESTE ARCHIVO

    El servicio de encomiendas se suspende. El módulo no tenía llave: sólo se
    podía apagar rompiéndolo (borrando la tarifa). Ahora tiene una, calcada de
    la de la recarga, y se apaga desde Configuración. El por qué está en
    `services/encomiendas_abiertas.py`.

LAS CUATRO COSAS QUE ESTE ARCHIVO NO DEJA QUE SE ROMPAN

    1. QUE CERRAR LA LLAVE CIERRE LAS DOS PUERTAS POR LAS QUE NACE UN ENVIO.

       Cotizar y confirmar. Una que se olvide es el servicio abierto por un
       costado. Y la guarda va ANTES de cotizar nada.

    2. QUE LO QUE YA ESTA EN CAMINO SIGA SU CURSO.

       Ver los envíos, el detalle, el seguimiento público, subir el
       comprobante y pagar los cobros de un envío en curso NO llevan la guarda.
       Ponérsela dejaría una caja en el limbo, que es peor que la suspensión.

    3. QUE NINGUNA PANTALLA OFREZCA LO QUE EL SERVIDOR VA A NEGAR.

       Cuatro puertas llevan a `/envios/nuevo`. Cada una tiene que preguntar
       primero. Y la ruta misma lleva puerta, para quien la tenga en favoritos.

    4. QUE LA PANTALLA Y EL SERVIDOR LEAN LO MISMO.

       El frontend lo saca de `/api/limits`, la misma ruta de la que el
       servidor saca lo que hace cumplir.
"""
import ast
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parent
_SRC = _REPO / "frontend" / "src"

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import HTTPException                             # noqa: E402

from conftest import usar_base                                # noqa: E402
from services import configuracion as cfg                     # noqa: E402
from services import encomiendas_abiertas as ea               # noqa: E402
from services import limits                                   # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def poner(base, clave, valor):
    normalizado, error = cfg.normalizar(clave, valor)
    assert error is None, f"el panel rechazaría {valor}: {error}"
    corre(cfg.escribir(base, clave, normalizado))


# ══════════════════════════════════════════════════════════════════════════
# 1. La llave
# ══════════════════════════════════════════════════════════════════════════

def test_DE_FABRICA_LAS_ENCOMIENDAS_SIGUEN_ABIERTAS(base):
    """El despliegue no cambia el comportamiento de la aplicación: eso lo
    decide una persona, en el panel. Fue la elección del dueño del proyecto."""
    assert corre(ea.esta_abierta(base)) is True


def test_el_ajuste_esta_en_el_catalogo_y_es_de_dos_estados():
    """Si no está en `AJUSTES`, el panel no lo dibuja y nadie lo puede apagar
    sin tocar código — que es exactamente lo que la regla de la casa prohíbe."""
    ajuste = cfg.AJUSTES[ea.CLAVE]
    assert ajuste.tipo == cfg.ENTERO
    assert (ajuste.minimo, ajuste.maximo) == (ea.CERRADA, ea.ABIERTA)
    assert ajuste.defecto == ea.ABIERTA


def test_cerrada_frena_con_503(base):
    poner(base, ea.CLAVE, ea.CERRADA)
    with pytest.raises(HTTPException) as e:
        corre(ea.exigir_abierta(base))
    assert e.value.status_code == 503
    assert e.value.detail == ea.SUSPENDIDO


def test_abierta_deja_pasar(base):
    poner(base, ea.CLAVE, ea.ABIERTA)
    corre(ea.exigir_abierta(base))          # no levanta


def test_el_mensaje_dice_que_lo_que_ya_salio_sigue_igual():
    """Es lo primero que va a preguntar quien tenga una caja viajando. Sin
    eso, «suspendido» lo manda a soporte a preguntar por su paquete."""
    assert "en camino" in ea.SUSPENDIDO
    assert "Mis envíos" in ea.SUSPENDIDO


class _BaseRota:
    """Una base que no contesta. `configuracion.leer` revienta al tocarla."""

    def __getattr__(self, nombre):
        raise ConnectionError("la base no contesta")

    def __getitem__(self, nombre):
        raise ConnectionError("la base no contesta")


def test_SI_LA_BASE_NO_CONTESTA_DEJA_MANDAR():
    """Falla abierto, como la recarga. Frenar algo que anda porque nuestra
    base tuvo un mal momento es cobrarle al usuario una falla nuestra."""
    assert corre(ea.esta_abierta(_BaseRota())) is True
    corre(ea.exigir_abierta(_BaseRota()))   # no levanta


# ══════════════════════════════════════════════════════════════════════════
# 2. Las dos puertas por las que nace un envío, y las que NO se cierran
# ══════════════════════════════════════════════════════════════════════════

_RUTAS = _BACKEND / "routes" / "envios.py"


def _cuerpo(nombre: str) -> ast.AsyncFunctionDef:
    arbol = ast.parse(_RUTAS.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.AsyncFunctionDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"no existe la ruta {nombre} en routes/envios.py")


def _llama_a_la_guarda(funcion: ast.AsyncFunctionDef):
    """Los índices (orden de aparición) de cada `encomiendas_abiertas.exigir_abierta(`."""
    hallados = []
    for i, nodo in enumerate(ast.walk(funcion)):
        if (isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "exigir_abierta"
                and isinstance(nodo.func.value, ast.Name)
                and nodo.func.value.id == "encomiendas_abiertas"):
            hallados.append(i)
    return hallados


@pytest.mark.parametrize("ruta", ["cotizar", "crear"])
def test_CADA_PUERTA_POR_LA_QUE_NACE_UN_ENVIO_PREGUNTA(ruta):
    assert _llama_a_la_guarda(_cuerpo(ruta)), (
        f"`{ruta}` no pregunta si el servicio está suspendido: con la llave "
        f"en 0 igual nacen envíos por ahí")


@pytest.mark.parametrize("ruta, trabajo", [
    ("cotizar", "envios_cotizador"), ("crear", "envios_crear")])
def test_la_guarda_va_ANTES_de_hacer_nada(ruta, trabajo):
    """Cotizar no cobra, pero persiste la cotización. Frenar después de eso
    deja rastro de algo que no tendría que haber empezado."""
    fuente = ast.get_source_segment(_RUTAS.read_text(encoding="utf-8"),
                                    _cuerpo(ruta))
    assert fuente.index("encomiendas_abiertas.exigir_abierta(") < fuente.index(
        f"{trabajo}.")


@pytest.mark.parametrize("ruta", [
    "obtener_catalogo", "pagar_cobro", "cargar_comprobante", "ver_foto",
    "seguimiento", "listar_envios", "ver_envio",
])
def test_ESTAS_NO_llevan_la_guarda(ruta):
    """Lo que ya está en camino sigue su curso. Cerrarle el comprobante o el
    pago a un envío que ya salió lo deja en el limbo."""
    assert not _llama_a_la_guarda(_cuerpo(ruta)), (
        f"`{ruta}` pregunta por la suspensión, y no tiene que hacerlo: es de "
        f"un envío que ya existe")


def test_LOS_NOMBRES_DE_LAS_RUTAS_SIGUEN_EXISTIENDO():
    """El test de arriba busca funciones por nombre. Si alguien renombra una,
    el parametrize de arriba pasaría a fallar con «no existe» —bien— pero un
    nombre que ya no está no se comprueba. Este test hace ruido a propósito."""
    for nombre in ("cotizar", "crear", "obtener_catalogo", "pagar_cobro",
                   "cargar_comprobante", "ver_foto", "seguimiento",
                   "listar_envios", "ver_envio"):
        _cuerpo(nombre)


# ══════════════════════════════════════════════════════════════════════════
# 3. `/envios/limites` dice por qué, y `/api/limits` lo publica
# ══════════════════════════════════════════════════════════════════════════

def test_LIMITES_DICE_SUSPENDIDO_Y_NO_A_MEDIO_CONFIGURAR(base):
    """Con la llave en 0, `disponible` es false y el motivo es la suspensión —
    no la lista de lo que falta configurar, que además no tiene por qué salir
    del lado de afuera."""
    from routes import envios as rutas
    poner(base, ea.CLAVE, ea.CERRADA)
    salida = corre(rutas.obtener_limites())
    assert salida["disponible"] is False
    assert salida["faltantes"] == [ea.SUSPENDIDO]


def test_limites_con_la_llave_abierta_no_dice_suspendido(base):
    from routes import envios as rutas
    poner(base, ea.CLAVE, ea.ABIERTA)
    salida = corre(rutas.obtener_limites())
    assert ea.SUSPENDIDO not in salida.get("faltantes", [])


def test_EL_ESTADO_VIAJA_EN_LIMITS(base):
    """La pantalla y el servidor tienen que leer lo mismo, de la misma ruta."""
    poner(base, ea.CLAVE, ea.CERRADA)
    assert corre(limits.limits_payload(base))["encomiendas"] is False
    poner(base, ea.CLAVE, ea.ABIERTA)
    assert corre(limits.limits_payload(base))["encomiendas"] is True


# ══════════════════════════════════════════════════════════════════════════
# 4. QUE NINGUNA PANTALLA OFREZCA LO QUE EL SERVIDOR VA A NEGAR
# ══════════════════════════════════════════════════════════════════════════
#
#   Mismo guardián que el de la recarga (`test_recarga_cerrada.py`, sección
#   4), con la misma ventana de TRES LINEAS DE CODIGO y por el mismo motivo:
#   una condición a cinco líneas del botón que controla es una condición que
#   el próximo que lea el archivo no va a ver.

LLEVAN_A_UN_ENVIO_NUEVO = ("'/envios/nuevo'", '"/envios/nuevo"',
                           "'Enviar un paquete'")
# App.jsx es la puerta misma; EnvioNuevo.jsx es la pantalla de destino.
SE_SALTEAN = ("App.jsx", "EnvioNuevo.jsx")
VENTANA = 3


def _es_comentario(linea):
    t = linea.strip()
    return t.startswith(("//", "/*", "*", "{/*"))


def _enlaces_a_un_envio_nuevo():
    encontrados = []
    for archivo in sorted(_SRC.rglob("*.jsx")) + sorted(_SRC.rglob("*.js")):
        if archivo.name in SE_SALTEAN:
            continue
        lineas = archivo.read_text(encoding="utf-8").splitlines()
        for n, linea in enumerate(lineas):
            if not any(f in linea for f in LLEVAN_A_UN_ENVIO_NUEVO):
                continue
            tiene, gastadas = False, 0
            for m in range(n, -1, -1):
                if not lineas[m].strip() or _es_comentario(lineas[m]):
                    continue
                if "encomiendas.abiertas" in lineas[m]:
                    tiene = True
                    break
                gastadas += 1
                if gastadas > VENTANA:
                    break
            encontrados.append(
                (archivo.relative_to(_REPO).as_posix(), n + 1, tiene))
    return encontrados


def test_SE_ENCONTRARON_los_enlaces_a_un_envio_nuevo():
    """Cuatro es lo que hay hoy: el menú, el botón de «Mis envíos» y los dos
    «Cotizar de nuevo» del detalle. Si baja, o el frontend perdió un botón, o
    este archivo dejó de encontrarlos — y el guardián de abajo pasa vacío."""
    enlaces = _enlaces_a_un_envio_nuevo()
    assert len(enlaces) >= 4, (
        f"sólo se encontraron {len(enlaces)} enlaces a un envío nuevo y son "
        f"cuatro: el recorrido dejó de reconocer cómo navega el frontend")


def test_CADA_enlace_a_un_envio_nuevo_mira_si_se_puede():
    sin_condicion = [
        f"{archivo}:{linea}"
        for archivo, linea, tiene_condicion in _enlaces_a_un_envio_nuevo()
        if not tiene_condicion
    ]
    assert not sin_condicion, (
        "estos enlaces llevan a mandar un paquete sin preguntar si se puede:\n  "
        + "\n  ".join(sin_condicion)
        + "\nCon el servicio suspendido la pantalla rebota y el usuario no "
          "sabe por qué.")


def test_LA_RUTA_DE_MANDAR_UNO_NUEVO_LLEVA_PUERTA_Y_LAS_OTRAS_NO():
    """La puerta ataja a quien tenga `/envios/nuevo` en favoritos. Pero NO va
    en «Mis envíos» ni en el detalle: lo que ya está en camino se tiene que
    poder ver."""
    app = (_SRC / "App.jsx").read_text(encoding="utf-8")
    rutas = {}
    for linea in app.splitlines():
        if "<Route path=" in linea:
            camino = linea.split('path="')[1].split('"')[0]
            rutas[camino] = linea
    assert "<PuertaEncomiendas>" in rutas["/envios/nuevo"], (
        "`/envios/nuevo` quedó sin puerta: quien la tenga en favoritos llena "
        "el formulario y se come un 503 al cotizar")
    for camino in ("/envios", "/envios/:envioId", "/seguimiento/:token"):
        assert "PuertaEncomiendas" not in rutas[camino], (
            f"`{camino}` lleva la puerta, y no tiene que llevarla: es de lo "
            f"que ya está en camino")


def test_la_puerta_deja_pasar_MIENTRAS_no_sabe():
    puerta = (_SRC / "components" / "PuertaEncomiendas.jsx").read_text(
        encoding="utf-8")
    assert "if (cargando) return null;" in puerta, (
        "`PuertaEncomiendas` dejó de mirar si todavía está cargando: va a "
        "rebotar a todo el mundo durante el primer instante")


def test_el_frontend_lo_saca_de_la_MISMA_ruta_que_lo_hace_cumplir():
    hook = (_SRC / "hooks" / "useEncomiendas.js").read_text(encoding="utf-8")
    assert "api.get('/limits')" in hook
    assert "r.data?.encomiendas" in hook
    # Un backend viejo que todavía no publica la clave se trata como abierto,
    # no como cerrado: durante un despliegue a medias no se esconde nada.
    assert "v === undefined ? true" in hook
