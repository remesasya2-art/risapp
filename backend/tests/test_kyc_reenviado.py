"""
tests/test_kyc_reenviado.py — Cuando el usuario reenvía su KYC hay más de un
documento, y hay que mirar el último.

POR QUE ESTE ARCHIVO EXISTE

    `submit_verification` hace `insert_one` en `verifications` cada vez, y no
    tiene ninguna guarda contra reenviar. Es correcto: alguien a quien le
    rechazaron la foto por borrosa TIENE que poder mandar otra. Pero entonces
    un usuario puede tener dos, tres o cinco documentos en esa colección.

    Y trece lugares del backend leían con

        db.verifications.find_one({"user_id": ...})

    sin ordenar. Mongo devuelve en orden natural, que en la práctica es el
    PRIMERO insertado: el viejo, el que ya fue rechazado.

    Lo que eso provoca, sitio por sitio:
      - el usuario reenvía y en su pantalla sigue diciendo "rechazado"
      - el admin abre el KYC pendiente y ve la foto vieja, la borrosa, y
        vuelve a rechazar — para siempre
      - la recuperación de cuenta compara la identidad contra datos viejos

    No es un caso raro: le pasa a todo el que corrige algo y reenvía, que es
    exactamente para lo que sirve reenviar.

COMO SE PRUEBA
    Un test de comportamiento sobre el camino que ve el usuario, y una guarda
    de AST sobre los trece, porque el bug es de forma y reaparece igual en el
    sitio catorce.
"""
import asyncio
import ast
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import usar_base                                      # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


async def _dos_envios(base):
    """El caso de todos los días: le rechazaron el primero y mandó otro."""
    ahora = datetime.now(timezone.utc)
    await base.verifications.insert_one({
        "verification_id": "ver_VIEJA", "user_id": "usr_1",
        "status": "rejected", "rejection_reason": "Foto borrosa",
        "id_document_image": "la-borrosa",
        "submitted_at": ahora - timedelta(days=3)})
    await base.verifications.insert_one({
        "verification_id": "ver_NUEVA", "user_id": "usr_1",
        "status": "pending", "id_document_image": "la-buena",
        "submitted_at": ahora})
    await base.users.insert_one({
        "user_id": "usr_1", "email": "ana@ejemplo.com",
        "verification_status": "pending"})


def test_el_usuario_ve_el_estado_de_SU_ULTIMO_envio(base):
    """Si reenvió, su pantalla no puede seguir diciendo 'rechazado'."""
    async def caso():
        await _dos_envios(base)
        import routes.misc as misc
        v = await misc.db.verifications.find_one(
            {"user_id": "usr_1"}, {"_id": 0}, sort=[("submitted_at", -1)])
        assert v["verification_id"] == "ver_NUEVA", \
            "le mostró el envío viejo, el que ya le rechazaron"
        assert v["status"] == "pending"
    corre(caso())


def test_el_admin_revisa_los_documentos_NUEVOS(base):
    """Revisar la foto vieja significa rechazar de nuevo, para siempre."""
    async def caso():
        await _dos_envios(base)
        import routes.admin as adm
        usuarios = await adm.db.users.find(
            {"verification_status": "pending"}, {"_id": 0}).to_list(100)
        assert len(usuarios) == 1
        v = await adm.db.verifications.find_one(
            {"user_id": usuarios[0]["user_id"]}, {"_id": 0},
            sort=[("submitted_at", -1)])
        assert v["id_document_image"] == "la-buena", \
            "el admin está mirando la foto borrosa que ya rechazó"
    corre(caso())


def test_con_un_solo_envio_ordenar_no_cambia_nada(base):
    """El arreglo no puede alterar el caso normal, que es el 99%."""
    async def caso():
        await base.verifications.insert_one({
            "verification_id": "ver_UNICA", "user_id": "usr_2",
            "status": "pending",
            "submitted_at": datetime.now(timezone.utc)})
        v = await base.verifications.find_one(
            {"user_id": "usr_2"}, sort=[("submitted_at", -1)])
        assert v["verification_id"] == "ver_UNICA"
    corre(caso())


# ── La guarda: que no vuelva a aparecer un find_one sin ordenar ───────────

_FUENTES = sorted(p for p in __import__("pathlib").Path(_BACKEND).glob("routes/*.py")
                  if p.is_file())


def _sin_orden(arbol):
    """Los `verifications.find_one({... user_id ...})` que no ordenan."""
    malos = []
    for n in ast.walk(arbol):
        f = getattr(n, "func", None)
        if not (isinstance(n, ast.Call) and isinstance(f, ast.Attribute)
                and f.attr == "find_one"
                and isinstance(f.value, ast.Attribute)
                and f.value.attr == "verifications"):
            continue
        if not n.args or "user_id" not in ast.unparse(n.args[0]):
            continue
        if not any(k.arg == "sort" for k in n.keywords):
            malos.append(n.lineno)
    return malos


def test_ningun_find_one_de_verificaciones_por_usuario_queda_sin_ordenar():
    hallazgos = []
    for archivo in _FUENTES:
        for linea in _sin_orden(ast.parse(archivo.read_text())):
            hallazgos.append(f"{archivo.name}:{linea}")
    assert not hallazgos, (
        "Estos `verifications.find_one` filtran por user_id y no ordenan. Si "
        "el usuario reenvió su KYC hay varios documentos y Mongo devuelve el "
        "más viejo — el que ya fue rechazado.\n  " + "\n  ".join(hallazgos) +
        '\n\nAgregá sort=[("submitted_at", -1)].')


def test_LA_GUARDA_SE_ROMPE_si_alguien_saca_el_orden(tmp_path):
    """Una guarda que no se puede poner en rojo no guarda nada."""
    caso = tmp_path / "caso.py"
    caso.write_text(
        'async def f(user_id):\n'
        '    return await db.verifications.find_one({"user_id": user_id})\n')
    assert _sin_orden(ast.parse(caso.read_text())) == [2]

    seguro = tmp_path / "seguro.py"
    seguro.write_text(
        'async def f(user_id):\n'
        '    return await db.verifications.find_one(\n'
        '        {"user_id": user_id}, sort=[("submitted_at", -1)])\n')
    assert _sin_orden(ast.parse(seguro.read_text())) == []
