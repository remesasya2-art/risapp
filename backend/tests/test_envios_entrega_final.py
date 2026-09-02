"""
tests/test_envios_entrega_final.py — Lo que pasa DESPUES de que terminamos.

POR QUE EXISTE ESTE MODULO
    `entregado_transportista` es TERMINAL: nuestro servicio termina cuando la
    caja queda en la oficina del transportista de destino. Pero para el usuario
    el envio no termino ahi — termina cuando su familiar tiene la caja, y eso
    pasa dias despues, en un mostrador al que no tenemos acceso.

    El equipo si lo averigua: entra a la web del transportista y ve que la guia
    figura retirada, y por quien. Hasta ahora ese dato se quedaba en la cabeza
    de quien lo miro.

LO QUE ESTOS TESTS DEFIENDEN
    Que esto NO se convierta en un estado. Es una OBSERVACION de tercero —
    alguien leyo una pagina web— y no algo que hicimos nosotros. Sacar
    `entregado_transportista` de `TERMINALES` para modelarlo tocaria desvios,
    cobros y la pantalla del usuario: desproporcionado, y arriesga plata.

CONTRA MONGOMOCK, NO CONTRA UN DOBLE
    La proyeccion del historial usa claves con punto (`destino.agencia_nombre`).
    El doble escrito a mano de la suite de operacion no las entiende y devolveria
    un bloque vacio, asi que los tests pasarian afirmando lo contrario de lo que
    hace la base de verdad.
"""

import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)


def _cargar(nombre):
    """Por ruta directa, para no arrastrar services/__init__.py."""
    if "services" not in sys.modules:
        paquete = types.ModuleType("services")
        paquete.__path__ = [os.path.join(_BACKEND, "services")]
        sys.modules["services"] = paquete
    completo = f"services.{nombre}"
    if completo in sys.modules:
        return sys.modules[completo]
    ruta = os.path.join(_BACKEND, "services", f"{nombre}.py")
    spec = importlib.util.spec_from_file_location(completo, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[completo] = modulo
    spec.loader.exec_module(modulo)
    return modulo


ef = _cargar("envios_entrega_final")
seg = _cargar("envios_seguimiento")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)
BASE = {}


class _Operador:
    user_id = "usr_operador"


def envio(estado="entregado_transportista", envio_id="env_aaa111", **extra):
    doc = {
        "envio_id": envio_id, "display_id": "E000123", "user_id": "usr_ana",
        "estado": estado, "created_at": AHORA - timedelta(days=5),
        "origen": {"codigo_objeto": "AA123456789BR"},
        "destino": {"agencia_nombre": "Centro", "ciudad": "El Tigre",
                    "estado_ve": "Anzoátegui",
                    "destinatario": {"nombre": "Ana Pérez"}},
        "entrega": {"guia": "GUIA-99887"},
        "cotizacion": {"total_final_ris": "132.00"},
    }
    doc.update(extra)
    return doc


@pytest.fixture(autouse=True)
def base_limpia():
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()["risapp_test"]
    usar_base(base)
    BASE["db"] = base
    yield base
    BASE.clear()


def guardado(envio_id="env_aaa111"):
    return corre(BASE["db"].envios.find_one({"envio_id": envio_id}, {"_id": 0}))


def avisos():
    return corre(BASE["db"].notifications.find({}, {"_id": 0}).to_list(50))


# ─── 1. Registrar el retiro ───────────────────────────────────────────────

def test_se_registra_quien_retiro_y_el_usuario_se_entera():
    corre(BASE["db"].envios.insert_one(envio()))
    r = corre(ef.registrar(_Operador(), "env_aaa111",
                           retirado_por="  José Martínez  ",
                           retirado_at="2026-09-01", documento="V-9876543",
                           fuente="Web MRW", db=BASE["db"], ahora=AHORA))

    assert r["ok"] is True
    final = guardado()["entrega_final"]
    assert final["retirado_por"] == "José Martínez"        # recortado
    assert final["documento"] == "V-9876543"
    assert final["fuente"] == "Web MRW"
    assert final["registrado_por"] == "usr_operador"
    assert final["retirado_at"].date().isoformat() == "2026-09-01"

    aviso = avisos()[0]
    assert aviso["user_id"] == "usr_ana"
    assert "José Martínez" in aviso["message"]
    assert aviso["data"]["accion"]["path"] == "/envios/env_aaa111"


def test_el_envio_NO_cambia_de_estado():
    """Esto es una observación de tercero, no algo que hicimos nosotros.

    Si esto moviera el envío, `entregado_transportista` dejaría de ser terminal
    y eso gobierna desvíos, cobros y la pantalla del usuario. Un cambio así por
    una línea informativa es desproporcionado y arriesga plata.
    """
    corre(BASE["db"].envios.insert_one(envio()))
    corre(ef.registrar(_Operador(), "env_aaa111", retirado_por="José Martínez",
                       db=BASE["db"], ahora=AHORA))
    assert guardado()["estado"] == "entregado_transportista"

    # Y la marca de la bitácora no es un estado de la máquina.
    estados = _cargar("envios_estados")
    assert ef.MARCA_RETIRO not in estados.TRANSICIONES
    assert ef.MARCA_RETIRO not in estados.TERMINALES


def test_sin_nombre_no_se_registra():
    """Sin el nombre, esto no dice nada que el usuario no supiera ya —que la
    caja llegó a la oficina— y el aviso sería ruido."""
    corre(BASE["db"].envios.insert_one(envio()))
    for vacio in ("", "   ", "Jo"):
        with pytest.raises(ef.RetiroInvalido) as e:
            corre(ef.registrar(_Operador(), "env_aaa111", retirado_por=vacio,
                               db=BASE["db"], ahora=AHORA))
        assert e.value.http == 400
    assert "entrega_final" not in (guardado() or {})
    assert avisos() == []


def test_no_se_registra_sobre_un_envio_que_todavia_no_entregamos():
    """«Lo retiraron en la oficina» sobre una caja que sigue en Pacaraima no es
    un dato incompleto: es un dato falso, y viaja al usuario como aviso."""
    corre(BASE["db"].envios.insert_one(envio(estado="en_transito_int")))
    with pytest.raises(ef.RetiroInvalido) as e:
        corre(ef.registrar(_Operador(), "env_aaa111", retirado_por="José Martínez",
                           db=BASE["db"], ahora=AHORA))
    assert e.value.http == 409
    # El MENSAJE, no solo el codigo. El filtro del `update_one` tambien lleva el
    # estado —defensa en profundidad, y esta bien que este— asi que sacar la
    # guarda explicita seguia dando 409, pero con «el envio cambio mientras
    # trabajabas»: un mensaje que manda a recargar y reintentar algo que nunca
    # va a andar. Sin esta asercion, la mutacion pasaba.
    assert "todavía no está entregado" in e.value.mensaje
    assert "entrega_final" not in guardado()
    assert avisos() == []


def test_un_envio_que_no_existe_no_se_inventa():
    with pytest.raises(ef.RetiroInvalido) as e:
        corre(ef.registrar(_Operador(), "env_no_existe", retirado_por="José M",
                           db=BASE["db"], ahora=AHORA))
    assert e.value.http == 404


def test_una_fecha_ilegible_no_frena_el_registro():
    """Se cae al momento del registro: peor dato, pero dato al fin. El operador
    lo ve en pantalla y lo corrige."""
    corre(BASE["db"].envios.insert_one(envio()))
    corre(ef.registrar(_Operador(), "env_aaa111", retirado_por="José Martínez",
                       retirado_at="ayer a la tarde", db=BASE["db"], ahora=AHORA))
    # Se compara la distancia y no la igualdad: BSON trunca a milisegundos y
    # devuelve el datetime sin tzinfo, asi que `== AHORA` falla por la
    # representacion y no por el comportamiento, que es lo que se prueba aca.
    guardada = guardado()["entrega_final"]["retirado_at"]
    assert abs(guardada.replace(tzinfo=timezone.utc) - AHORA).total_seconds() < 1


def test_corregir_el_nombre_deja_rastro():
    """Lo tipea una persona leyendo la web de otra empresa. Se va a equivocar, y
    la corrección tiene que verse, no pisarse en silencio."""
    corre(BASE["db"].envios.insert_one(envio()))
    corre(ef.registrar(_Operador(), "env_aaa111", retirado_por="Jose Martines",
                       db=BASE["db"], ahora=AHORA))
    r = corre(ef.registrar(_Operador(), "env_aaa111", retirado_por="José Martínez",
                           db=BASE["db"], ahora=AHORA))

    assert r["correccion"] is True
    assert guardado()["entrega_final"]["retirado_por"] == "José Martínez"

    eventos = corre(BASE["db"].envios_eventos.find({}, {"_id": 0}).to_list(10))
    assert len(eventos) == 2, "la corrección tiene que dejar su propia línea"
    assert eventos[1]["detalle"]["correccion"] is True
    assert eventos[0]["a_estado"] == ef.MARCA_RETIRO

    # Y el aviso de la corrección lo dice, en vez de repetir el original.
    assert "Corregimos" in avisos()[1]["title"]


def test_un_aviso_que_falla_no_desguarda_el_dato():
    corre(BASE["db"].envios.insert_one(envio()))

    async def romper(*a, **k):
        raise RuntimeError("caído")
    BASE["db"].notifications.insert_one = romper

    r = corre(ef.registrar(_Operador(), "env_aaa111", retirado_por="José Martínez",
                           db=BASE["db"], ahora=AHORA))
    assert r["ok"] is True
    assert guardado()["entrega_final"]["retirado_por"] == "José Martínez"


def test_el_paso_aparece_en_la_linea_de_tiempo_del_usuario():
    """Para el usuario ESTE es el último paso de su envío: para él termina
    cuando su familiar tiene la caja, no cuando la dejamos en un mostrador."""
    assert ef.MARCA_RETIRO in seg.PUBLICO
    titulo, detalle = seg.PUBLICO[ef.MARCA_RETIRO]
    assert titulo and detalle


# ─── 2. El historial ──────────────────────────────────────────────────────

def test_el_historial_trae_lo_que_el_equipo_necesita_leer():
    corre(BASE["db"].envios.insert_one(envio()))
    r = corre(ef.historial(db=BASE["db"]))
    fila = r["envios"][0]

    # La proyeccion usa claves con punto: si no funcionaran, estos tres serian
    # None y la pantalla mostraria una fila vacia.
    assert fila["destinatario"] == "Ana Pérez"
    assert fila["agencia"] == "Centro"
    assert fila["ciudad"] == "El Tigre"
    assert fila["codigo_objeto"] == "AA123456789BR"
    assert fila["guia"] == "GUIA-99887"


def test_el_historial_no_devuelve_el_token_de_seguimiento():
    """El token es una credencial: con él se ve el envío sin sesión, y esta lista
    se pinta en una pantalla que alguien deja abierta.

    Lo que lo protege es `_fila`, que arma la salida a partir de una lista blanca
    de claves: aunque la consulta trajera el documento entero, el token no sale.
    Se afirman las DOS cosas por separado —la lista blanca y la proyección— para
    que romper cualquiera de las dos se vea.
    """
    corre(BASE["db"].envios.insert_one(envio(tracking_token="tok_secreto_xyz")))
    r = corre(ef.historial(db=BASE["db"]))
    assert "tok_secreto_xyz" not in repr(r)

    # 1. La lista blanca: aun con el documento entero delante, no lo copia.
    suelto = ef._fila({"envio_id": "x", "tracking_token": "tok_secreto_xyz",
                       "cobros": {"inicial": {"monto_ris": "132.00"}}})
    assert "tok_secreto_xyz" not in repr(suelto)
    assert "cobros" not in suelto

    # 2. Y la proyeccion, que es lo que evita traer el documento entero por la
    #    red en una pantalla que se refresca sola.
    assert "tracking_token" not in ef._PROYECCION
    assert "cobros" not in ef._PROYECCION


def test_el_historial_marca_las_que_esperan_que_alguien_las_mire():
    """Entregadas al transportista y todavía sin retirar: son exactamente las
    filas que el equipo tiene que ir a buscar a la web del transportista."""
    corre(BASE["db"].envios.insert_many([
        envio(envio_id="env_1"),
        envio(envio_id="env_2", estado="en_transito_int"),
        envio(envio_id="env_3",
              entrega_final={"retirado_por": "José Martínez"}),
    ]))
    por_id = {f["envio_id"]: f for f in corre(ef.historial(db=BASE["db"]))["envios"]}
    assert por_id["env_1"]["espera_retiro"] is True
    assert por_id["env_2"]["espera_retiro"] is False    # todavía no es nuestra
    assert por_id["env_3"]["espera_retiro"] is False    # ya se registró


def test_se_busca_por_display_id_y_por_codigo_de_objeto():
    corre(BASE["db"].envios.insert_many([
        envio(envio_id="env_1"),
        envio(envio_id="env_2", display_id="E000999",
              origen={"codigo_objeto": "BB987654321BR"}),
    ]))
    uno = corre(ef.historial(buscar="e000999", db=BASE["db"]))["envios"]
    assert [f["envio_id"] for f in uno] == ["env_2"]

    # El codigo pegado de la web del transportista, con espacios y guiones.
    dos = corre(ef.historial(buscar=" bb 9876-54321 br ", db=BASE["db"]))["envios"]
    assert [f["envio_id"] for f in dos] == ["env_2"]


def test_se_filtra_por_estado():
    corre(BASE["db"].envios.insert_many([
        envio(envio_id="env_1"),
        envio(envio_id="env_2", estado="en_transito_int"),
    ]))
    r = corre(ef.historial(estado="en_transito_int", db=BASE["db"]))
    assert [f["envio_id"] for f in r["envios"]] == ["env_2"]


def test_el_historial_dice_cuando_hay_mas():
    """Truncar en silencio hace que el equipo crea que vio todo."""
    corre(BASE["db"].envios.insert_many(
        [envio(envio_id=f"env_{i}") for i in range(8)]))
    r = corre(ef.historial(limite=5, db=BASE["db"]))
    assert len(r["envios"]) == 5
    assert r["hay_mas"] is True

    ultimo = corre(ef.historial(limite=5, saltear=5, db=BASE["db"]))
    assert len(ultimo["envios"]) == 3
    assert ultimo["hay_mas"] is False


def test_el_limite_no_lo_elige_el_que_llama():
    """`limite` viene de la query string. Sin tope, `?limite=999999` es una
    lectura de la colección entera servida a quien la pida."""
    corre(BASE["db"].envios.insert_many(
        [envio(envio_id=f"env_{i}") for i in range(3)]))
    r = corre(ef.historial(limite=10 ** 9, db=BASE["db"]))
    assert len(r["envios"]) == 3          # no revienta y no ignora el tope
    assert ef.TOPE <= 200


def test_si_no_se_puede_leer_el_historial_no_revienta():
    class _Rota:
        def find(self, *a, **k):
            raise RuntimeError("mongo caído")
    BASE["db"].envios = _Rota()
    r = corre(ef.historial(db=BASE["db"]))
    assert r["envios"] == [] and r["degradado"] is True
