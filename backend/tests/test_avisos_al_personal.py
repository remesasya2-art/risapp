"""
tests/test_avisos_al_personal.py — A quién le llega un aviso de trabajo.

QUE SOSTIENE ESTE ARCHIVO

    Un aviso de trabajo —«hay un KYC nuevo», «la tasa venció»— no es de nadie
    en particular: es de quien pueda resolverlo. Elegir mal al destinatario
    tiene dos formas, y las dos son caras:

    LE LLEGA A QUIEN NO PUEDE HACER NADA
        El aviso de una orden de Bitcoin pagada le llegaba también a los
        `admin`, que no pueden abrir el panel de Bitcoin. Un aviso sobre el que
        no se puede actuar enseña a ignorar los avisos.

    LE LLEGA A QUIEN YA NO ESTA
        Ninguna de las cinco versiones sueltas de este código miraba
        `is_active`. Un administrador dado de baja seguía recibiendo cada KYC
        nuevo, cada operación con Bitcoin y cada alerta de tasa después de
        irse de la empresa. Eso no es ruido: es información del negocio
        saliendo hacia una cuenta que ya nadie controla.

    NO LE LLEGA A NADIE
        Y el trabajo queda esperando sin que nadie sepa que existe. Por eso
        «no había a quién avisar» se registra como error y no como silencio.
"""
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import los_py_de, usar_base                       # noqa: E402
from services import notifications as n              # noqa: E402

# La de verdad, agarrada ANTES de que el fixture de abajo la reemplace. Sin
# esto, el test del push caído volvía a instalar el doble creyendo que instalaba
# la original, y verificaba el doble.
_PUSH_REAL = n._push_sin_romper


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def sin_push(monkeypatch):
    """El push sale a un servicio ajeno. Acá no se prueba eso."""
    enviados = []

    async def _push(user_id, title, message, data):
        enviados.append(user_id)
        return True

    monkeypatch.setattr(n, "_push_sin_romper", _push)
    return enviados


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def poblar(base, gente):
    corre(base.users.insert_many([dict(g) for g in gente]))


# El equipo de ejemplo. Cada uno está por una razón distinta.
EQUIPO = [
    {"user_id": "jefa",     "role": "super_admin"},
    {"user_id": "revisora", "role": "admin", "permissions": ["kyc.view"]},
    {"user_id": "cajero",   "role": "admin", "permissions": ["envios.view"]},
    {"user_id": "mesa",     "role": "agent", "permissions": ["kyc.view"]},
    {"user_id": "cliente",  "role": "user"},
]


# ─── Quién entra en la lista ──────────────────────────────────────────────

def test_el_permiso_manda_no_el_rol(base):
    """Quien puede ver los KYC recibe el aviso de KYC. El resto, no."""
    poblar(base, EQUIPO)
    quienes = corre(n.personal_que_puede("kyc.view"))

    assert sorted(p["user_id"] for p in quienes) == ["jefa", "mesa", "revisora"], (
        "El destinatario se elige por permiso. `cajero` es admin pero no puede "
        "abrir los KYC, y `mesa` no es admin pero sí puede.")


def test_el_cliente_nunca_recibe_un_aviso_de_trabajo(base):
    """Ni siquiera si por un error de datos le quedó un permiso suelto."""
    poblar(base, EQUIPO + [
        {"user_id": "colado", "role": "user", "permissions": ["kyc.view"]},
    ])
    quienes = corre(n.personal_que_puede("kyc.view"))

    assert "colado" not in [p["user_id"] for p in quienes], (
        "Un cliente con un permiso pegado por error no atiende la mesa. El "
        "rol es el primer filtro; el permiso, el segundo.")


def test_el_que_se_fue_deja_de_recibir(base):
    """Lo que faltaba en las cinco versiones sueltas de esto."""
    poblar(base, EQUIPO + [
        {"user_id": "exempleada", "role": "admin",
         "permissions": ["kyc.view"], "is_active": False},
    ])
    quienes = corre(n.personal_que_puede("kyc.view"))

    assert "exempleada" not in [p["user_id"] for p in quienes], (
        "Una persona dada de baja seguía recibiendo cada KYC nuevo. No entra "
        "más al panel: el aviso no tiene a dónde ir, y los datos del cliente "
        "que trae, sí.")


def test_un_super_administrador_dado_de_baja_tampoco(base):
    """El super administrador entra siempre; dado de baja, no existe."""
    poblar(base, [
        {"user_id": "jefa", "role": "super_admin"},
        {"user_id": "exjefe", "role": "super_admin", "is_active": False},
    ])

    por_permiso = [p["user_id"] for p in corre(n.personal_que_puede("kyc.view"))]
    solo_super = [p["user_id"]
                  for p in corre(n.personal_que_puede(solo_super_admin=True))]

    assert por_permiso == ["jefa"]
    assert solo_super == ["jefa"], (
        "`solo_super_admin` es la otra puerta: si no mirara `is_active`, la "
        "mitad de los avisos seguiría yéndose a una cuenta cerrada.")


def test_sin_el_campo_is_active_se_considera_activo(base):
    """Las cuentas viejas no tienen el campo. No se las puede dar por baja."""
    poblar(base, [{"user_id": "antigua", "role": "admin",
                   "permissions": ["kyc.view"]}])

    assert [p["user_id"] for p in corre(n.personal_que_puede("kyc.view"))] == ["antigua"]


def test_el_super_administrador_entra_sin_tener_el_permiso_en_la_lista(base):
    """Es quien destraba: no se le pide la lista de permisos."""
    poblar(base, [{"user_id": "jefa", "role": "super_admin", "permissions": []}])

    assert [p["user_id"] for p in corre(n.personal_que_puede("kyc.view"))] == ["jefa"]


def test_sin_permiso_va_a_todo_el_equipo(base):
    """Un aviso sin permiso declarado es para el personal entero, no para nadie."""
    poblar(base, EQUIPO)
    quienes = [p["user_id"] for p in corre(n.personal_que_puede())]

    assert sorted(quienes) == ["cajero", "jefa", "mesa", "revisora"]
    assert "cliente" not in quienes


def test_solo_super_admin_deja_afuera_a_los_admin(base):
    """La puerta del panel de Bitcoin es `get_super_admin`, no un permiso."""
    poblar(base, EQUIPO)
    quienes = [p["user_id"] for p in corre(n.personal_que_puede(solo_super_admin=True))]

    assert quienes == ["jefa"]


def test_hay_un_techo_de_destinatarios(base):
    """Contra un error de configuración, no como paginación.

    Si mañana una cuenta mal migrada deja a todos los usuarios como `admin`,
    un aviso no puede convertirse en cien mil escrituras.
    """
    poblar(base, [{"user_id": f"a{i}", "role": "admin"}
                  for i in range(n._TOPE_DESTINATARIOS + 50)])

    assert len(corre(n.personal_que_puede())) == n._TOPE_DESTINATARIOS


def test_no_trae_el_usuario_entero(base):
    """Se piden tres campos. Lo demás es documento de identidad y teléfono."""
    poblar(base, [{"user_id": "jefa", "role": "super_admin",
                   "name": "Jefa", "password_hash": "no-deberia-salir",
                   "document_number": "tampoco"}])

    persona = corre(n.personal_que_puede())[0]
    assert set(persona) <= {"user_id", "name", "role"}, (
        f"Vinieron campos de más: {sorted(persona)}")


# ─── Cómo se guarda el aviso ──────────────────────────────────────────────

def test_el_aviso_del_equipo_queda_marcado_como_de_trabajo(base):
    poblar(base, EQUIPO)
    cuantos = corre(n.avisar_al_personal(
        title="Hay un KYC nuevo", message="Revisalo", permiso="kyc.view"))

    guardados = corre(base.notifications.find({}, {"_id": 0}).to_list(50))
    assert cuantos == 3
    assert {g["ambito"] for g in guardados} == {n.TRABAJO}, (
        "Sin esta marca el panel no puede tener su propia bandeja: el aviso "
        "del equipo cae mezclado con «te aprobaron el KYC».")


def test_el_aviso_de_una_persona_es_personal_por_omision(base):
    corre(n.create_notification("cliente", "Te aprobamos el KYC", "Listo"))

    guardado = corre(base.notifications.find_one({}, {"_id": 0}))
    assert guardado["ambito"] == n.PERSONAL


def test_los_avisos_viejos_no_tienen_ambito_y_eso_esta_bien(base):
    """No se reescribe lo ya guardado: al leerlos, la ausencia se lee como
    personal, que es lo que eran casi todos."""
    corre(base.notifications.insert_one(
        {"notification_id": "viejo", "user_id": "cliente", "read": False}))

    guardado = corre(base.notifications.find_one({"notification_id": "viejo"}))
    assert "ambito" not in guardado


# ─── Que avisar no pueda tirar el trabajo que lo disparó ──────────────────

def test_si_la_base_no_contesta_no_levanta(base, caplog):
    """Quien llama acaba de guardar un KYC de verdad. Ese trabajo ya está
    hecho: que no se pueda avisar se anota, no se devuelve como un 500."""
    class _Rota:
        def find(self, *a, **k):
            raise RuntimeError("la base no contesta")

    base.users = _Rota()
    with caplog.at_level(logging.ERROR):
        cuantos = corre(n.avisar_al_personal(title="x", message="y"))

    assert cuantos == 0
    assert any("no se pudo averiguar a quién avisar" in m for m in caplog.messages)


def test_si_uno_falla_los_demas_reciben(base, monkeypatch):
    """Veinte destinatarios y una fila rota no pueden costar diecinueve avisos."""
    poblar(base, EQUIPO)
    original = n.create_notification

    async def _a_veces(user_id, *a, **k):
        if user_id == "revisora":
            raise RuntimeError("esta fila está rota")
        return await original(user_id, *a, **k)

    monkeypatch.setattr(n, "create_notification", _a_veces)
    cuantos = corre(n.avisar_al_personal(
        title="Hay un KYC nuevo", message="Revisalo", permiso="kyc.view"))

    assert cuantos == 2, (
        "Un destinatario roto se llevó puestos a los otros. Cada aviso va por "
        "su cuenta.")


def test_si_el_push_falla_el_aviso_igual_queda_guardado(base, monkeypatch):
    """El push es una cortesía que sale a un servicio ajeno. Su caída no puede
    llevarse puesto el aviso, que es lo que la persona sí va a ver al entrar."""
    async def _push_roto(user_id, title, message, data):
        raise RuntimeError("el servicio de push no contesta")

    monkeypatch.setattr(n, "_push_sin_romper", _PUSH_REAL)
    monkeypatch.setattr("services.push_notifications.send_push_to_user", _push_roto)

    corre(n.create_notification("cliente", "Te aprobamos el KYC", "Listo"))

    assert corre(base.notifications.count_documents({})) == 1, (
        "El aviso se perdió porque falló el push. Si `create_notification` "
        "retorna, el aviso tiene que estar guardado.")


def test_que_no_haya_nadie_queda_registrado(base, caplog):
    """El trabajo queda esperando y nadie sabe que existe. Es una condición de
    configuración, no un caso normal."""
    poblar(base, [{"user_id": "cliente", "role": "user"}])
    with caplog.at_level(logging.WARNING):
        cuantos = corre(n.avisar_al_personal(
            title="Hay un KYC nuevo", message="Revisalo", permiso="kyc.view"))

    assert cuantos == 0
    assert any("nadie puede recibir el aviso" in m for m in caplog.messages)


def test_los_avisos_salen_a_la_vez(base, monkeypatch):
    """De a uno, avisarle a veinte administradores son veinte viajes
    encadenados y el cliente mira la ruedita hasta que termina el último."""
    poblar(base, [{"user_id": f"a{i}", "role": "admin"} for i in range(10)])
    en_vuelo, pico = 0, 0
    original = n.create_notification

    async def _lento(*a, **k):
        nonlocal en_vuelo, pico
        en_vuelo += 1
        pico = max(pico, en_vuelo)
        await asyncio.sleep(0)
        try:
            return await original(*a, **k)
        finally:
            en_vuelo -= 1

    monkeypatch.setattr(n, "create_notification", _lento)
    corre(n.avisar_al_personal(title="x", message="y"))

    assert pico > 1, (
        f"Los avisos salieron de a uno (pico={pico}). Encadenados, el que "
        "disparó la acción espera por los diez.")


# ─── Que no vuelva a haber cinco formas de hacer esto ─────────────────────

def _archivos_del_backend():
    for carpeta in ("routes", "services"):
        raiz = os.path.join(_BACKEND, carpeta)
        for nombre in los_py_de(raiz):
            if nombre.endswith(".py"):
                yield f"{carpeta}/{nombre}", os.path.join(raiz, nombre)


def _busca_usuarios_por_rol(nodo):
    """¿Esta función hace `db.users.find({"role": ...})`?

    Mira el FILTRO, no el cuerpo entero. `user.get("role")` después de buscar
    por `user_id` es otra cosa —un aviso personal— y marcarlo sería enseñar a
    ignorar esta guarda.
    """
    import ast
    for hijo in ast.walk(nodo):
        if not isinstance(hijo, ast.Call):
            continue
        f = hijo.func
        if not (isinstance(f, ast.Attribute) and f.attr in ("find", "find_one")):
            continue
        coleccion = f.value
        if not (isinstance(coleccion, ast.Attribute) and coleccion.attr == "users"):
            continue
        if not hijo.args or not isinstance(hijo.args[0], ast.Dict):
            continue
        claves = [k.value for k in hijo.args[0].keys
                  if isinstance(k, ast.Constant)]
        if "role" in claves:
            return True
    return False


def test_nadie_vuelve_a_armarse_su_propia_lista_de_administradores():
    """La guarda de forma, porque el bug reaparece igual en el sitio sexto.

    El patrón es siempre el mismo: buscar usuarios POR ROL y, en la misma
    función, crear un aviso para cada uno. Escrito a mano se olvida
    `is_active` —las cinco veces se olvidó—, se elige el rol por costumbre y
    cada copia pone un tope distinto.

    Si esto se pone rojo, el arreglo no es agregarle `is_active` a la copia
    nueva: es llamar a `avisar_al_personal`.
    """
    import ast
    culpables = []
    for etiqueta, ruta in _archivos_del_backend():
        with open(ruta, encoding="utf-8") as f:
            fuente = f.read()
        for nodo in ast.walk(ast.parse(fuente)):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            volcado = ast.dump(nodo)
            if "create_notification" in volcado and _busca_usuarios_por_rol(nodo):
                culpables.append(f"{etiqueta}::{nodo.name}")

    assert not culpables, (
        "Estas funciones se arman su propia lista de destinatarios en vez de "
        "usar `avisar_al_personal`:\n  " + "\n  ".join(culpables))


def test_la_guarda_de_arriba_reconoce_el_patron_que_persigue():
    """Una guarda que nunca vio un culpable no prueba que sepa reconocerlo.

    Acá se le pone delante el código EXACTO que había en `routes/misc.py`
    antes de este cambio. Si esto no lo detecta, el test de arriba está en
    verde por no encontrar nada, no por estar limpio.
    """
    import ast
    como_estaba = ast.parse('''
async def submit_verification(data, current_user):
    admins = await db.users.find({"role": "super_admin"}).to_list(50)
    for admin in admins:
        await create_notification(user_id=admin["user_id"], title="KYC")
''')
    funcion = como_estaba.body[0]
    assert _busca_usuarios_por_rol(funcion)
    assert "create_notification" in ast.dump(funcion)


# ─── Los dos sitios que se convirtieron, por su comportamiento ────────────

UNA_FOTO = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="


def test_el_kyc_nuevo_le_llega_a_quien_puede_revisarlo(base, monkeypatch):
    """El caso real: alguien manda su documento y el equipo tiene que enterarse.

    Antes iba a los super administradores a mano y sin mirar `is_active`. Con
    eso, la persona que revisa los KYC todos los días no se enteraba, y quien
    se fue de la empresa sí.
    """
    from models.user import User
    from routes import misc

    poblar(base, EQUIPO + [
        {"user_id": "exrevisora", "role": "admin",
         "permissions": ["kyc.view"], "is_active": False},
    ])

    datos = misc.VerificationSubmit(
        full_name="Persona de Prueba", document_number="12345678",
        cpf_number="00000000000", phone_number="+5511999999999",
        id_document_image=UNA_FOTO, id_document_image_back=UNA_FOTO,
        cpf_image=UNA_FOTO, selfie_image=UNA_FOTO, document_type="rg")
    quien_envia = User(user_id="cliente", email="cliente@ejemplo.com",
                       full_name="Persona de Prueba")

    corre(misc.submit_verification(datos, quien_envia))

    avisados = corre(base.notifications.find({}, {"_id": 0}).to_list(50))
    assert sorted(a["user_id"] for a in avisados) == ["jefa", "mesa", "revisora"], (
        f"Recibieron {sorted(a['user_id'] for a in avisados)}. El aviso va a "
        "quien puede abrir el KYC, y a nadie que se haya ido.")
    assert {a["ambito"] for a in avisados} == {n.TRABAJO}
    assert avisados[0]["data"]["verification_id"].startswith("ver_"), (
        "Sin el identificador, el aviso obliga a buscar el KYC a mano.")


class _PedidoFalso:
    """El webhook de Blink, con la firma ya dada por buena.

    La firma se prueba en `test_webhooks_firmados.py`; acá se prueba a quién
    le llega el aviso cuando el pago entra.
    """

    def __init__(self, cuerpo: dict):
        import json
        self._crudo = json.dumps(cuerpo).encode()
        self._cuerpo = cuerpo
        self.headers = {"svix-id": "msg_1",
                        "svix-timestamp": str(int(time.time())),
                        "svix-signature": "v1,da-igual"}

    async def body(self):
        return self._crudo

    async def json(self):
        return self._cuerpo


def test_la_orden_de_bitcoin_pagada_no_le_llega_a_quien_no_puede_abrir_el_panel(
        base, monkeypatch):
    """El panel de Bitcoin lo guarda `get_super_admin`: no hay permiso suelto.

    El aviso le llegaba también a los `admin`, que lo abren y se encuentran
    con que esa sección no existe para ellos. Un aviso sobre el que no se
    puede actuar enseña a ignorar los avisos.
    """
    from routes import btc_lightning as btc

    monkeypatch.setattr(btc, "_verify_blink_signature", lambda *a, **k: True)
    poblar(base, EQUIPO)
    corre(base.btc_remesas.insert_one({
        "remesa_id": "btc_abc123def", "payment_hash": "hash_1",
        "user_id": "cliente", "estado": "pendiente", "ves_recibe": 4500.0,
        "usd_cliente": 50.0,
        "expira_en": datetime.now(timezone.utc) + timedelta(minutes=10),
        "beneficiario_data": {"full_name": "Quien Recibe",
                              "id_document": "V-12345678",
                              "bank_code": "0102", "phone_number": "0412",
                              "payment_type": "transferencia"}}))

    corre(btc.webhook_blink(_PedidoFalso(
        {"transaction": {"status": "PAID",
                         "initiationVia": {"paymentHash": "hash_1"}}})))

    del_equipo = corre(base.notifications.find(
        {"ambito": n.TRABAJO}, {"_id": 0}).to_list(50))
    assert [a["user_id"] for a in del_equipo] == ["jefa"], (
        f"Recibieron {[a['user_id'] for a in del_equipo]}. Sólo el super "
        "administrador puede abrir el panel de Bitcoin.")

    personales = corre(base.notifications.find(
        {"ambito": n.PERSONAL}, {"_id": 0}).to_list(50))
    assert [a["user_id"] for a in personales] == ["cliente"], (
        "El que pagó también tiene que enterarse, y por su propia bandeja.")


def test_el_pago_de_bitcoin_que_llega_tarde_tambien(base, monkeypatch):
    """La otra mitad: la orden venció, la plata llegó igual y hay que decidir
    a mano. Eso lo decide el super administrador, que es quien entra al panel.
    """
    from routes import btc_lightning as btc

    monkeypatch.setattr(btc, "_verify_blink_signature", lambda *a, **k: True)
    poblar(base, EQUIPO)
    corre(base.btc_remesas.insert_one({
        "remesa_id": "btc_vencida", "payment_hash": "hash_2",
        "user_id": "cliente", "estado": "pendiente", "ves_recibe": 4500.0,
        "expira_en": datetime.now(timezone.utc) - timedelta(minutes=1),
        "beneficiario_data": {}}))

    corre(btc.webhook_blink(_PedidoFalso(
        {"transaction": {"status": "PAID",
                         "initiationVia": {"paymentHash": "hash_2"}}})))

    avisados = corre(base.notifications.find({}, {"_id": 0}).to_list(50))
    assert [a["user_id"] for a in avisados] == ["jefa"]
    assert avisados[0]["type"] == "warning"
    assert avisados[0]["data"]["motivo"] == "vencida"

    quedo = corre(base.btc_remesas.find_one({"remesa_id": "btc_vencida"}))
    assert quedo["estado"] == "revision_manual", (
        "El aviso salió pero la orden no quedó marcada: el aviso manda a "
        "mirar algo que el panel no muestra.")
