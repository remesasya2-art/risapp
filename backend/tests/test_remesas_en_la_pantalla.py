"""
tests/test_remesas_en_la_pantalla.py — Con remesas en pausa, ninguna pantalla
del cliente ofrece lo que el servidor va a negar.

La llave y sus guardas: tests/test_remesas_cerradas.py. Acá se mira el otro
lado: que la pantalla lea la misma llave, de la misma ruta, y que las dos
pantallas donde nace un envío tengan puerta. Se lee el código del frontend,
como hacen los tests de encomiendas y de la recarga.
"""
import pathlib
import re

_SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"


def _leer(*partes):
    return (_SRC.joinpath(*partes)).read_text(encoding="utf-8")


def test_LAS_DOS_PANTALLAS_DONDE_NACE_UN_ENVIO_TIENEN_PUERTA():
    """Esconder los botones no alcanza: desde un favorito o escribiendo la
    dirección se llega igual, y el 503 aparece recién al confirmar."""
    app = _leer("App.jsx")
    for ruta, pantalla in (("/send", "Send"), ("/send-reais", "SendReais")):
        linea = next(l for l in app.splitlines() if f'<Route path="{ruta}" ' in l)
        assert f"<PuertaRemesas><ConTema><{pantalla} /></ConTema></PuertaRemesas>" in linea, linea


def test_LO_QUE_YA_EMPEZO_NO_TIENE_PUERTA():
    app = _leer("App.jsx")
    for ruta in ("/history", "/envios/:transactionId/pagar"):
        lineas = [l for l in app.splitlines() if f'path="{ruta}"' in l]
        assert lineas, f"ya no existe la ruta {ruta}: revisá este test"
        for l in lineas:
            assert "PuertaRemesas" not in l, l


def test_LA_PUERTA_DEJA_PASAR_MIENTRAS_NO_SABE_Y_MANDA_AL_INICIO():
    puerta = _leer("components", "PuertaRemesas.jsx")
    assert "if (cargando) return null;" in puerta
    assert 'if (!abiertas) return <Navigate to="/" replace />;' in puerta


def test_EL_HOOK_LO_SACA_DE_LIMITS_Y_UN_BACKEND_VIEJO_CUENTA_COMO_ABIERTO():
    hook = _leer("hooks", "useRemesas.js")
    assert "api.get('/limits')" in hook
    assert "const v = r.data?.remesas;" in hook
    assert "abiertas: v === undefined ? true : Boolean(v)" in hook


def test_EL_MENU_OFRECE_GASTAR_SOLO_CON_REMESAS_ABIERTA():
    tablero = _leer("pages", "Dashboard.jsx")
    bloque = re.search(r"\.\.\.\(remesas\.abiertas \? \[(.*?)\] : \[\]\)", tablero, re.S)
    assert bloque, "las dos entradas de gastar ya no dependen de la llave"
    assert "'/send'" in bloque.group(1) and "'/send-reais'" in bloque.group(1)
    fuera = tablero.replace(bloque.group(0), "")
    assert "label: 'Gastar en Venezuela'" not in fuera, "quedó una entrada fija"


def test_SIN_BRASIL_EN_EL_MENU_EL_PAQUETE_NO_SE_VA_ARRIBA_DE_INICIO():
    """`findIndex` da -1 si no encuentra, y -1 + 1 es 0: sin el `|| 1`, con
    remesas en pausa «Enviar un paquete» quedaba primero, antes de Inicio."""
    assert "findIndex((m) => m.path === '/send-reais') + 1 || 1;" in _leer("pages", "Dashboard.jsx")


def test_LOS_DEMAS_BOTONES_DE_GASTAR_MIRAN_LA_LLAVE():
    assert "{remesas.abiertas && <Calculadora" in _leer("pages", "Dashboard.jsx")
    assert ") : remesas.abiertas ? (" in _leer("pages", "Dashboard.jsx"), "el historial vacío del inicio"
    assert "{remesas.abiertas && (\n        <div" in _leer("components", "dashboard", "BalanceCard.jsx")
    assert "remesas.abiertas && { clave: 'envio'" in _leer("components", "dashboard", "PrimerosPasos.jsx")
    assert '{remesas.abiertas && <Link to="/send"' in _leer("pages", "History.jsx")
