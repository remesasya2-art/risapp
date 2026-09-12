"""
tests/test_codigo_para_cambiar_la_clave.py — La contraseña no se cambia sola.

LO QUE PASABA

    Para cambiar la contraseña alcanzaba con la contraseña actual. Quien se
    llevaba un teléfono con la sesión abierta —o robaba una sesión— tenía la
    cuenta: entraba a Perfil, ponía la contraseña que el navegador ya tenía
    guardada, y cambiaba la contraseña dejando al dueño afuera.

    Ahora hace falta TAMBIEN el correo. Y si alguien lo intenta, al dueño le
    llega un correo que no pidió: la primera señal de que algo pasa.

Y EL OTRO ARREGLO, QUE ES EL GRAVE

    El código de «olvidé mi contraseña» se generaba con `random.randint`.

    `random` es un generador PREDECIBLE: arranca de una semilla y quien vea
    unos cuantos valores puede calcular los que siguen. No es un detalle de
    estilo. En el código que deja cambiar la contraseña de una cuenta ajena,
    es la puerta.

    El registro, en el mismo proyecto, ya usaba `secrets`. Estaba bien en el
    lugar menos delicado y mal en el más delicado.
"""
import ast
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import codigos                       # noqa: E402


# ─── El generador ─────────────────────────────────────────────────────────

def test_el_codigo_es_alfanumerico():
    assert any(c.isalpha() for c in "".join(codigos.nuevo() for _ in range(20)))
    assert all(c in codigos.ALFABETO for c in codigos.nuevo())


def test_no_tiene_los_caracteres_que_se_confunden():
    """Se lee de un correo y se tipea a mano, muchas veces desde un teléfono.

    Un cero y una O mayúscula se ven casi iguales; el uno, la I y la L,
    también. Quien se equivoca gasta un intento de los tres que tiene, y
    volver a empezar por culpa de la tipografía es un mal motivo.
    """
    for confundible in "0O1IL":
        assert confundible not in codigos.ALFABETO, (
            f"{confundible!r} está en el alfabeto y se confunde con otro.")


def test_dos_codigos_seguidos_no_son_iguales():
    assert len({codigos.nuevo() for _ in range(50)}) == 50


def test_acepta_minusculas_y_espacios_pegados_del_correo():
    """Rechazar un código por una minúscula sería gastarle un intento a
    alguien que lo escribió bien."""
    codigo = codigos.nuevo()
    assert codigos.coincide(codigo.lower(), codigo)
    assert codigos.coincide(f"  {codigo[:4]} {codigo[4:]}  ", codigo)


def test_la_comparacion_no_corta_en_la_primera_letra_distinta():
    """Lo único de este archivo que se vigila por la FORMA, y con motivo.

    Un `==` común corta apenas encuentra una letra distinta. Esa diferencia de
    tiempo —microsegundos, pero medible repitiendo— deja adivinar el código
    letra por letra en vez de entero, y baja el problema de mil millones de
    combinaciones a unas pocas decenas de pruebas.

    `hmac.compare_digest` tarda lo mismo acierte o no. No hay forma de probar
    eso corriendo la función: dos códigos distintos dan `False` con cualquiera
    de las dos. Lo que sí se puede exigir es que la llamada esté.
    """
    import ast
    ruta = os.path.join(_BACKEND, "services", "codigos.py")
    with open(ruta, encoding="utf-8") as f:
        arbol = ast.parse(f.read())

    comparar = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "compare_digest"]

    assert comparar, (
        "`coincide` dejó de usar `hmac.compare_digest`. Un `==` común deja "
        "adivinar el código letra por letra.")


def test_un_codigo_distinto_no_pasa():
    assert not codigos.coincide("AAAAAAAA", "BBBBBBBB")
    assert not codigos.coincide("", "BBBBBBBB")
    assert not codigos.coincide("BBBBBBBB", "")
    assert not codigos.coincide("BBBBBBBB", None)


# ─── Que nadie vuelva a usar el generador predecible ──────────────────────

CON_CODIGOS = ["routes/recovery.py", "routes/auth.py", "services/codigos.py"]


@pytest.mark.parametrize("archivo", CON_CODIGOS)
def test_ningun_codigo_sale_de_random(archivo):
    """La guarda. `random` es para simulaciones, no para credenciales.

    Se mira el ARBOL y no el texto: así los comentarios de este proyecto
    —que nombran `random` justamente para contar esta historia— no pueden
    hacer pasar ni fallar el test por error.
    """
    with open(os.path.join(_BACKEND, archivo), encoding="utf-8") as f:
        arbol = ast.parse(f.read())

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            assert all(a.name != "random" for a in nodo.names), (
                f"{archivo} importa `random`, que es predecible. Para algo que "
                "se usa como credencial va `secrets`.")
        if isinstance(nodo, ast.ImportFrom):
            assert nodo.module != "random", f"{archivo} importa de `random`."


def test_la_guarda_de_arriba_reconoce_lo_que_persigue():
    """Una guarda que nunca vio un culpable no prueba que sepa reconocerlo."""
    arbol = ast.parse("import random\ncodigo = random.randint(100000, 999999)")
    importa_random = any(
        isinstance(n, ast.Import) and any(a.name == "random" for a in n.names)
        for n in ast.walk(arbol))
    assert importa_random


# ─── El cambio de contraseña estando adentro ──────────────────────────────

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import FastAPI, HTTPException          # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

from conftest import usar_base                      # noqa: E402
from routes import auth as rutas_auth               # noqa: E402
from routes.dependencies import get_current_user    # noqa: E402
from utils.security import hash_password            # noqa: E402


def corre(coro):
    return asyncio.run(coro)


class _Quien:
    user_id = "cliente"
    role = "user"


_app = FastAPI()
_app.include_router(rutas_auth.router, prefix="/api")
_app.dependency_overrides[get_current_user] = lambda: _Quien()
cliente = TestClient(_app, raise_server_exceptions=False)

LA_DE_ANTES = "LaDeAntes123!"
LA_NUEVA = "LaNuevaQueVa456!"


@pytest.fixture
def base(monkeypatch):
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    corre(b.users.insert_one({
        "user_id": "cliente", "email": "cliente@ejemplo.com",
        "name": "Quien Sea", "password_hash": hash_password(LA_DE_ANTES)}))
    # El freno por dirección de internet no es lo que se prueba acá.
    from routes import security_2fa
    monkeypatch.setattr(security_2fa, "frenar", lambda *a, **k: None)
    return b


@pytest.fixture
def correos(monkeypatch):
    salieron = []

    async def _enviar(destinatario, asunto, html, *, que_es="correo"):
        salieron.append({"a": destinatario, "asunto": asunto, "html": html})
        return True

    from services import correo
    monkeypatch.setattr(correo, "enviar", _enviar)
    monkeypatch.setattr(rutas_auth.correo, "enviar", _enviar)
    return salieron


def _codigo_guardado(base):
    doc = corre(base.codigos_de_cambio.find_one({"user_id": "cliente"}))
    return doc["codigo"] if doc else None


def pedir_codigo(clave=LA_DE_ANTES):
    return cliente.post("/api/auth/change-password/pedir-codigo",
                        json={"current_password": clave})


def cambiar(codigo, clave=LA_DE_ANTES, nueva=LA_NUEVA):
    return cliente.post("/api/auth/change-password", json={
        "current_password": clave, "new_password": nueva,
        "confirm_password": nueva, "codigo": codigo})


def test_el_camino_completo(base, correos):
    r = pedir_codigo()
    assert r.status_code == 200, r.text
    assert len(correos) == 1
    assert correos[0]["a"] == "cliente@ejemplo.com"

    codigo = _codigo_guardado(base)
    assert codigo and codigo in correos[0]["html"], (
        "El código tiene que ir en el correo, o no sirve de nada.")

    assert cambiar(codigo).status_code == 200
    from utils.security import verify_password
    quien = corre(base.users.find_one({"user_id": "cliente"}))
    assert verify_password(LA_NUEVA, quien["password_hash"])


def test_sin_codigo_no_se_cambia_nada(base, correos):
    """El corazón del cambio: la contraseña actual ya no alcanza."""
    r = cambiar("CUALQUIER")
    assert r.status_code == 400
    assert "Pedí un código" in r.json()["detail"]

    from utils.security import verify_password
    quien = corre(base.users.find_one({"user_id": "cliente"}))
    assert verify_password(LA_DE_ANTES, quien["password_hash"]), (
        "La contraseña cambió sin código.")


def test_con_la_clave_actual_equivocada_no_se_manda_ningun_codigo(base, correos):
    assert pedir_codigo("noEsEsta1!").status_code == 400
    assert correos == []
    assert _codigo_guardado(base) is None


def test_un_codigo_equivocado_gasta_un_intento(base, correos):
    pedir_codigo()
    r = cambiar("AAAAAAAA")
    assert r.status_code == 400
    assert "2 intentos" in r.json()["detail"]


def test_se_acaban_los_intentos_y_el_codigo_bueno_ya_no_sirve(base, correos):
    """Tres intentos alcanzan para equivocarse tipeando y no para adivinar."""
    pedir_codigo()
    codigo = _codigo_guardado(base)

    for _ in range(3):
        cambiar("AAAAAAAA")

    r = cambiar(codigo)
    assert r.status_code == 400
    assert "intentos" in r.json()["detail"]

    from utils.security import verify_password
    quien = corre(base.users.find_one({"user_id": "cliente"}))
    assert verify_password(LA_DE_ANTES, quien["password_hash"])


def test_un_codigo_vencido_no_sirve(base, correos):
    pedir_codigo()
    codigo = _codigo_guardado(base)
    corre(base.codigos_de_cambio.update_one(
        {"user_id": "cliente"},
        {"$set": {"expira_en": datetime.now(timezone.utc) - timedelta(minutes=1)}}))

    r = cambiar(codigo)
    assert r.status_code == 400 and "venció" in r.json()["detail"]


def test_el_codigo_se_gasta_y_no_vale_dos_veces(base, correos):
    pedir_codigo()
    codigo = _codigo_guardado(base)
    assert cambiar(codigo).status_code == 200

    # La segunda vez hay que pasar la contraseña nueva, que ya es la de verdad.
    r = cambiar(codigo, clave=LA_NUEVA, nueva="OtraMasQueVa789!")
    assert r.status_code == 400, "El mismo código sirvió dos veces."


def test_pedir_otro_codigo_invalida_el_anterior(base, correos):
    pedir_codigo()
    viejo = _codigo_guardado(base)
    pedir_codigo()
    nuevo = _codigo_guardado(base)

    assert viejo != nuevo
    assert cambiar(viejo).status_code == 400, "El código viejo siguió sirviendo."


def test_si_el_correo_no_sale_se_dice_y_no_se_deja_esperando(base, monkeypatch):
    """Quedarse mirando una pantalla que pide un código que nunca va a llegar
    es peor que un error claro."""
    async def _no_sale(*a, **k):
        return False

    monkeypatch.setattr(rutas_auth.correo, "enviar", _no_sale)
    assert pedir_codigo().status_code == 503


def test_el_correo_avisa_que_alguien_puede_tener_la_contrasena(base, correos):
    """Si el dueño no pidió esto, el correo es la señal de que algo pasa."""
    pedir_codigo()
    assert "Si no pediste este cambio" in correos[0]["html"]
