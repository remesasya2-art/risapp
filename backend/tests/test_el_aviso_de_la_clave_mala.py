"""
tests/test_el_aviso_de_la_clave_mala.py — quien pone mal la contraseña ve
«Credenciales inválidas».

QUE PASABA

    El login con la clave equivocada contesta 401, y el cliente de la API
    (`frontend/src/utils/api.js`) trataba TODO 401 como «se venció la sesión»:
    borraba la marca de sesión y recargaba /login. La recarga se llevaba el
    aviso antes de que se viera. Comprobado en el navegador contra la versión
    de producción: con la clave mala, la pantalla parpadeaba y no decía nada.

LO QUE SE CUIDA

    Que un 401 sólo mande al login a quien TENIA sesión (el caso para el que
    se escribió), y que sin sesión el error llegue a la pantalla que hizo el
    pedido. No hay navegador en la suite: se lee el fuente. La prueba en el
    navegador está en el cuerpo del pull request.
"""
import re
from pathlib import Path

_API = Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "api.js"


def _el_manejador_del_401() -> str:
    fuente = _API.read_text(encoding="utf-8")
    sin_comentarios = re.sub(r"//[^\n]*", "", fuente)
    inicio = sin_comentarios.index("error.response?.status === 401")
    return sin_comentarios[inicio:sin_comentarios.index("return Promise.reject(error)", inicio)]


def test_SOLO_VUELVE_AL_LOGIN_QUIEN_TENIA_SESION():
    bloque = _el_manejador_del_401()
    # Se mira ANTES de borrar la marca: leerla después daría siempre vacío y
    # nadie volvería nunca al login, tampoco con la sesión vencida.
    assert bloque.index("getItem('has_session')") < bloque.index("removeItem('has_session')")
    redirecciones = re.findall(r"(if \(\w+\) )?window\.location\.href = '/login'", bloque)
    assert redirecciones == ["if (teniaSesion) "], redirecciones


def test_LA_SESION_VENCIDA_SIGUE_VOLVIENDO_AL_LOGIN():
    """La contracara: el arreglo no puede dejar a alguien con la sesión
    vencida mirando una pantalla que ya no le contesta."""
    bloque = _el_manejador_del_401()
    assert "const teniaSesion = localStorage.getItem('has_session');" in bloque
    assert "window.location.href = '/login'" in bloque
