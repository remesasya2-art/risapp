"""
tests/test_la_reserva_del_cpf.py — Un CPF, una cuenta, desde el primer instante.

EL AGUJERO QUE ESTO CIERRA, Y POR QUE NO ERA EL QUE SE CREIA

    El código decía que la ventana era de milisegundos y que el índice único de
    `users.cpf_number` la tapaba. Las dos cosas eran optimistas.

    Al registrarse, el CPF NO SE GUARDA EN LA CUENTA: la cuenta todavía no
    existe. Queda en `pending_verifications` esperando que la persona confirme
    su correo, y la comprobación sólo miraba `users`. O sea que durante los
    QUINCE MINUTOS que dura el código de verificación, otra persona se
    registraba con el mismo CPF y pasaba igual. No hacía falta que fuera
    simultáneo: alcanzaba con que fuera en el mismo cuarto de hora.

    Así aparecieron los CPF repetidos que hoy impiden crear ese índice único.

LO QUE SE VIGILA, POR ORDEN DE DAÑO

    1. Que dos registros con el mismo CPF no pasen los dos, aunque ninguno haya
       confirmado el correo todavía. Es el agujero de arriba.
    2. Que confirmar el correo deje el CPF anclado a esa cuenta para siempre.
    3. Que un registro abandonado SUELTE el CPF. Sin esto, un dedo equivocado
       que tipea el CPF de un tercero le bloquea la cuenta a esa persona.
    4. Que nada suelte nunca una reserva ya anclada.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import FastAPI                                 # noqa: E402
from fastapi.testclient import TestClient                   # noqa: E402

from conftest import ensenarle_decimal128_a_mongomock, usar_base   # noqa: E402
from routes import auth as rutas_auth                       # noqa: E402
from routes import security_2fa                             # noqa: E402
from services import cpf_de_la_cuenta as cdc                # noqa: E402

UNO = "52998224725"
OTRO = "11144477735"
TERCERO = "12345678909"


@pytest.fixture
def base():
    ensenarle_decimal128_a_mongomock()
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_reserva_cpf"]
    usar_base(b)
    return b


@pytest.fixture
def cliente(base, monkeypatch):
    """El registro entero, sin correo y sin limitador.

    El correo se sustituye porque mandarlo de verdad desde la suite le
    escribiría a una casilla ajena; ya pasó en este repositorio. El limitador se
    vacía porque con `TestClient` todos los pedidos vienen de la misma IP.
    """
    async def sin_correo(*a, **k):
        return True
    monkeypatch.setattr(rutas_auth, "send_verification_email", sin_correo)
    try:
        security_2fa.limiter.limiter.storage.reset()
    except Exception:
        pass

    app = FastAPI()
    app.include_router(rutas_auth.router, prefix="/api")
    return TestClient(app)


def correr(corrutina):
    return asyncio.run(corrutina)


def registrar(cliente, correo="ana@ejemplo.com", cpf=UNO, **extra):
    return cliente.post("/api/auth/register", json={
        "name": "Ana", "email": correo, "cpf_number": cpf,
        "password": "Clave.larga1!", "confirm_password": "Clave.larga1!",
        **extra})


def confirmar(cliente, base, correo="ana@ejemplo.com"):
    """Mete el código que le llegó por correo, leyéndolo de la base."""
    pendiente = correr(base.pending_verifications.find_one({"email": correo}))
    return cliente.post("/api/auth/verify-email", json={
        "email": correo, "code": pendiente["verification_code"]})


def reserva(base, cpf=UNO):
    return correr(base[cdc.COLECCION_TOMADOS].find_one({"_id": cpf}))


def envejecer(base, cpf=UNO, minutos=30):
    """Le corre el vencimiento a una reserva para atrás.

    Hace falta porque mongomock no tiene el barrendero de Mongo, y porque
    esperar quince minutos reales en un test no es una opción. Es lo mismo que
    ve la aplicación cuando el barrendero todavía no pasó: el documento sigue
    ahí, vencido.
    """
    correr(base[cdc.COLECCION_TOMADOS].update_one(
        {"_id": cpf},
        {"$set": {"vence_en": datetime.now(timezone.utc)
                  - timedelta(minutes=minutos)}}))


# ══════════════════════════════════════════════════════════════════════════
# 1. El agujero: dos registros en el mismo cuarto de hora
# ══════════════════════════════════════════════════════════════════════════

def test_DOS_REGISTROS_CON_EL_MISMO_CPF_NO_PASAN_LOS_DOS(cliente, base):
    """ESTE es el test del error real. Antes los dos daban 200: el primero
    dejaba el CPF en `pending_verifications`, no en `users`, y la comprobación
    sólo miraba `users`."""
    assert registrar(cliente, "ana@ejemplo.com", UNO).status_code == 200

    r = registrar(cliente, "beto@ejemplo.com", UNO)
    assert r.status_code == 400, r.text
    assert correr(base.pending_verifications.count_documents(
        {"email": "beto@ejemplo.com"})) == 0


def test_EL_SEGUNDO_SE_ENTERA_DE_QUE_HAY_UN_REGISTRO_EMPEZADO(cliente):
    """El mensaje tiene que mandarlo a su correo, no a iniciar sesión en una
    cuenta que todavía no existe."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    detalle = registrar(cliente, "beto@ejemplo.com", UNO).json()["detail"]
    assert "correo" in detalle.lower(), detalle


def test_EL_SEGUNDO_SI_PUEDE_REGISTRARSE_CON_OTRO_CPF(cliente):
    registrar(cliente, "ana@ejemplo.com", UNO)
    assert registrar(cliente, "beto@ejemplo.com", OTRO).status_code == 200


def test_EL_MISMO_CORREO_NO_SE_CHOCA_CONSIGO_MISMO(cliente):
    """Mandar el formulario dos veces —porque se equivocó la contraseña, o
    porque el primer correo no llegó— no puede bloquearle su propio CPF."""
    assert registrar(cliente, "ana@ejemplo.com", UNO).status_code == 200
    assert registrar(cliente, "ana@ejemplo.com", UNO).status_code == 200


def test_EL_CPF_QUEDA_TOMADO_APENAS_SE_REGISTRA(cliente, base):
    """La regla pedida: tomado desde que se escribe, no quince minutos
    después."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    assert reserva(base, UNO) is not None


def test_NO_SE_TOMA_EL_CPF_SI_EL_REGISTRO_IBA_A_FALLAR_IGUAL(cliente, base):
    """La reserva va después de todas las comprobaciones. Si se tomara antes,
    una contraseña mal repetida le bloquearía el CPF quince minutos a alguien
    que ni siquiera llegó a registrarse."""
    r = cliente.post("/api/auth/register", json={
        "name": "Ana", "email": "ana@ejemplo.com", "cpf_number": UNO,
        "password": "Clave.larga1!", "confirm_password": "Otra.distinta1!"})
    assert r.status_code == 400
    assert reserva(base, UNO) is None


# ══════════════════════════════════════════════════════════════════════════
# 2. Confirmar el correo ancla el CPF
# ══════════════════════════════════════════════════════════════════════════

def test_CONFIRMAR_EL_CORREO_ANCLA_EL_CPF(cliente, base):
    registrar(cliente, "ana@ejemplo.com", UNO)
    assert confirmar(cliente, base).status_code == 200

    quedo = reserva(base, UNO)
    assert quedo["user_id"], quedo
    assert correr(base.users.find_one({"email": "ana@ejemplo.com"}))["user_id"] \
        == quedo["user_id"]


def test_LA_RESERVA_ANCLADA_YA_NO_CADUCA(cliente, base):
    """Sin `vence_en`, el barrendero de Mongo ni la mira. Es exactamente así
    como una reserva pasa a ser para siempre."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    assert "vence_en" in reserva(base, UNO)

    confirmar(cliente, base)
    assert "vence_en" not in reserva(base, UNO)


def test_DESPUES_DE_CONFIRMAR_EL_CPF_NO_ABRE_OTRA_CUENTA(cliente, base):
    registrar(cliente, "ana@ejemplo.com", UNO)
    confirmar(cliente, base)
    r = registrar(cliente, "beto@ejemplo.com", UNO)
    assert r.status_code == 400
    assert "cuenta" in r.json()["detail"].lower()


def test_UN_PENDIENTE_VIEJO_SIN_RESERVA_IGUAL_SE_PUEDE_CONFIRMAR(cliente, base):
    """Los registros que ya estaban en vuelo cuando esto se desplegó no tienen
    reserva. Si el anclaje los rechazara, esa gente quedaría sin poder terminar
    de registrarse y sin entender por qué."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    correr(base[cdc.COLECCION_TOMADOS].delete_many({}))

    assert confirmar(cliente, base).status_code == 200
    assert reserva(base, UNO)["user_id"]


def test_NO_SE_CREA_LA_CUENTA_SI_EL_CPF_SE_LO_LLEVO_OTRO(cliente, base):
    """El anclaje va ANTES del insert. Al revés quedaría una cuenta creada con
    el CPF de otra persona, que es justo lo que se quiere evitar."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    correr(base[cdc.COLECCION_TOMADOS].delete_many({}))
    correr(cdc.anclar(base, UNO, "u_otro"))

    assert confirmar(cliente, base).status_code == 400
    assert correr(base.users.count_documents({"email": "ana@ejemplo.com"})) == 0


# ══════════════════════════════════════════════════════════════════════════
# 3. El registro abandonado suelta el CPF
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_RESERVA_VENCIDA_SE_LA_LLEVA_EL_SIGUIENTE(cliente, base):
    """Sin caducidad, un dedo equivocado que tipea el CPF de un tercero le
    bloquea la cuenta a esa persona PARA SIEMPRE."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    envejecer(base, UNO)

    assert registrar(cliente, "beto@ejemplo.com", UNO).status_code == 200
    assert reserva(base, UNO)["correo"] == "beto@ejemplo.com"


def test_UNA_RESERVA_VIVA_NO_SE_LA_LLEVA_NADIE(cliente, base):
    """La mutación de la de arriba: que la caducidad no sea una puerta abierta."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    assert registrar(cliente, "beto@ejemplo.com", UNO).status_code == 400


def test_EMPEZAR_DE_NUEVO_SUELTA_EL_CPF_ANTERIOR(cliente, base):
    """Se equivocó de CPF y vuelve a empezar. El equivocado no puede quedar
    tomado quince minutos por nada."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    registrar(cliente, "ana@ejemplo.com", OTRO)

    assert reserva(base, UNO) is None
    assert reserva(base, OTRO) is not None


def test_EL_CODIGO_VENCIDO_SUELTA_EL_CPF(cliente, base):
    registrar(cliente, "ana@ejemplo.com", UNO)
    correr(base.pending_verifications.update_one(
        {"email": "ana@ejemplo.com"},
        {"$set": {"code_expires_at": datetime.now(timezone.utc)
                  - timedelta(minutes=1)}}))

    assert confirmar(cliente, base).status_code == 400
    assert reserva(base, UNO) is None


def test_LOS_INTENTOS_AGOTADOS_SUELTAN_EL_CPF(cliente, base):
    registrar(cliente, "ana@ejemplo.com", UNO)
    correr(base.pending_verifications.update_one(
        {"email": "ana@ejemplo.com"}, {"$set": {"attempts": 5}}))

    assert confirmar(cliente, base).status_code == 400
    assert reserva(base, UNO) is None


def test_REENVIAR_EL_CODIGO_LE_CORRE_EL_VENCIMIENTO_A_LA_RESERVA(cliente, base):
    """Si no lo acompañara, el CPF quedaría libre mientras el código todavía
    sirve, y otro podría tomarlo justo antes de que el dueño confirme."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    envejecer(base, UNO)

    assert cliente.post("/api/auth/resend-verification-code",
                        json={"email": "ana@ejemplo.com"}).status_code == 200
    assert not cdc._vencida(reserva(base, UNO), datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════════════════════════
# 4. Nada suelta una reserva anclada
# ══════════════════════════════════════════════════════════════════════════

def test_SOLTAR_POR_CORREO_NO_TOCA_UNA_ANCLADA(base):
    """Sin la condición `user_id: {$exists: False}`, un registro abandonado con
    el mismo correo que una cuenta que ya existe le soltaría el CPF a esa
    cuenta."""
    correr(cdc.anclar(base, UNO, "u1", correo="ana@ejemplo.com"))
    assert correr(cdc.soltar_las_del_correo(base, "ana@ejemplo.com")) == 0
    assert reserva(base, UNO) is not None


def test_SOLTAR_EL_ANCLA_SOLO_SIRVE_PARA_LA_PROPIA(base):
    correr(cdc.anclar(base, UNO, "u1"))
    assert correr(cdc.soltar_el_ancla(base, UNO, "u_otro")) is False
    assert correr(cdc.soltar_el_ancla(base, UNO, "u1")) is True


def test_ANCLAR_NO_PISA_LA_RESERVA_DE_OTRO(base):
    """Anclar sobre lo de otro sería robarle el CPF con una cuenta creada un
    segundo después."""
    correr(cdc.tomar(base, UNO, correo="ana@ejemplo.com"))
    with pytest.raises(cdc.CpfEnUso):
        correr(cdc.anclar(base, UNO, "u_beto", correo="beto@ejemplo.com"))


# ══════════════════════════════════════════════════════════════════════════
# 5. `tomar` y `atar` a mano
# ══════════════════════════════════════════════════════════════════════════

def test_TOMAR_DOS_VECES_EL_MISMO_CPF_CON_CORREOS_DISTINTOS_FALLA(base):
    correr(cdc.tomar(base, UNO, correo="ana@ejemplo.com"))
    with pytest.raises(cdc.CpfEnUso):
        correr(cdc.tomar(base, UNO, correo="beto@ejemplo.com"))


def test_ATAR_DEJA_EL_CPF_ANCLADO(base):
    """La cuenta vieja, sin CPF, que lo declara en su primera recarga."""
    correr(base.users.insert_one({"user_id": "u1", "email": "a@ejemplo.com"}))
    assert correr(cdc.atar(base, "u1", UNO)) == UNO
    assert reserva(base, UNO)["user_id"] == "u1"


def test_ATAR_NO_PUEDE_LLEVARSE_EL_CPF_DE_UN_REGISTRO_EN_CURSO(base):
    correr(base.users.insert_one({"user_id": "u1", "email": "a@ejemplo.com"}))
    correr(cdc.tomar(base, UNO, correo="ana@ejemplo.com"))
    with pytest.raises(cdc.CpfEnUso):
        correr(cdc.atar(base, "u1", UNO))


def test_ATAR_SUELTA_EL_ANCLA_SI_LA_CUENTA_YA_TENIA_OTRO_CPF(base):
    """Un CPF anclado a una cuenta que no lo tiene queda bloqueado para todos y
    sin dueño que lo use. Es basura que nadie sabría que hay que limpiar."""
    correr(base.users.insert_one(
        {"user_id": "u1", "email": "a@ejemplo.com", "cpf_number": OTRO}))
    with pytest.raises(cdc.CpfDeOtro):
        correr(cdc.atar(base, "u1", UNO))
    assert reserva(base, UNO) is None


# ══════════════════════════════════════════════════════════════════════════
# 6. La siembra de las cuentas que ya existen
# ══════════════════════════════════════════════════════════════════════════

def test_LA_SIEMBRA_LE_DA_SU_RESERVA_A_CADA_CUENTA(base):
    """La colección nace vacía, y vacía quiere decir «todos los CPF están
    libres»: sin sembrarla, el CPF de cada cuenta que ya existe podría ser
    tomado por un registro nuevo."""
    correr(base.users.insert_many([
        {"user_id": "u1", "email": "a@ejemplo.com", "cpf_number": UNO},
        {"user_id": "u2", "email": "b@ejemplo.com", "cpf_number": OTRO},
        {"user_id": "u3", "email": "c@ejemplo.com"},
    ]))
    resumen = correr(cdc.sembrar(base))

    assert resumen["creadas"] == 2
    assert resumen["repetidos"] == []
    assert reserva(base, UNO)["user_id"] == "u1"


def test_LA_SIEMBRA_DELATA_LOS_CPF_REPETIDOS(base):
    """Los repetidos son los que impiden crear el índice único, y hasta ahora
    averiguar cuáles eran obligaba a consultar la base a mano."""
    correr(base.users.insert_many([
        {"user_id": "u1", "email": "a@ejemplo.com", "cpf_number": UNO},
        {"user_id": "u2", "email": "b@ejemplo.com", "cpf_number": UNO},
    ]))
    resumen = correr(cdc.sembrar(base))

    assert len(resumen["repetidos"]) == 1
    delatado = resumen["repetidos"][0]
    assert {delatado["lo_tiene"], delatado["tambien"]} == {"u1", "u2"}


def test_LA_SIEMBRA_NO_ESCRIBE_EL_CPF_ENTERO_EN_EL_REGISTRO(base):
    """El registro de la aplicación lo lee más gente de la que tiene por qué ver
    el documento de un cliente. Con el `user_id` al lado alcanza para encontrar
    la cuenta."""
    correr(base.users.insert_many([
        {"user_id": "u1", "email": "a@ejemplo.com", "cpf_number": UNO},
        {"user_id": "u2", "email": "b@ejemplo.com", "cpf_number": UNO},
    ]))
    resumen = correr(cdc.sembrar(base))
    assert UNO not in resumen["repetidos"][0]["cpf"]


def test_LA_SIEMBRA_SE_PUEDE_CORRER_DE_NUEVO_SIN_DELATAR_A_NADIE(base):
    """Corre en cada arranque. Si la segunda vez tomara sus propias reservas por
    repetidos, el registro se llenaría de una alarma falsa por cada cuenta."""
    correr(base.users.insert_one(
        {"user_id": "u1", "email": "a@ejemplo.com", "cpf_number": UNO}))
    correr(cdc.sembrar(base))
    resumen = correr(cdc.sembrar(base))

    assert resumen["creadas"] == 0
    assert resumen["ya_estaban"] == 1
    assert resumen["repetidos"] == []


def test_DESPUES_DE_SEMBRAR_ESE_CPF_NO_ABRE_OTRA_CUENTA(cliente, base):
    correr(base.users.insert_one(
        {"user_id": "u1", "email": "a@ejemplo.com", "cpf_number": UNO}))
    correr(cdc.sembrar(base))
    correr(base.users.delete_many({}))   # queda sólo la reserva

    assert registrar(cliente, "beto@ejemplo.com", UNO).status_code == 400


def test_BORRAR_LA_CUENTA_SIN_VERIFICAR_SUELTA_SU_ANCLA(cliente, base):
    """El registro borra la cuenta sin verificar que tuviera ese correo. Si su
    CPF quedara anclado, sería un CPF atado a una cuenta que ya no existe:
    bloqueado para todos y sin nadie que sepa que hay que limpiarlo."""
    correr(base.users.insert_one(
        {"user_id": "u_vieja", "email": "ana@ejemplo.com",
         "cpf_number": UNO, "email_verified": False}))
    correr(cdc.sembrar(base))

    assert registrar(cliente, "ana@ejemplo.com", OTRO).status_code == 200
    assert reserva(base, UNO) is None


def test_VOLVER_A_MANDAR_EL_MISMO_CPF_NO_SUELTA_LA_RESERVA_UN_INSTANTE(cliente, base):
    """Soltarla y volver a tomarla deja un instante en que el CPF está libre, y
    en ese instante otro se lo lleva. Se comprueba mirando `tomado_en`: si la
    reserva fuera otra, la fecha sería otra."""
    registrar(cliente, "ana@ejemplo.com", UNO)
    cuando = reserva(base, UNO)["tomado_en"]

    registrar(cliente, "ana@ejemplo.com", UNO)
    assert reserva(base, UNO)["tomado_en"] == cuando


def test_SACAR_UNA_VENCIDA_NO_SE_LLEVA_LA_QUE_ENTRO_DESPUES(base):
    """Dos pedidos pueden leer la misma reserva vencida. El primero la saca y
    pone la suya; si el segundo borrara por `_id` a secas, borraría la del
    primero —que está viva— y los dos se irían creyendo que tienen el CPF."""
    correr(cdc.tomar(base, UNO, correo="beto@ejemplo.com"))
    la_de_beto = reserva(base, UNO)

    # Lo que haría el segundo, que leyó la vencida de antes: su `marca` ya no
    # es la que está guardada.
    assert correr(cdc._sacar_la_vencida(base, UNO, "marca_de_la_vencida")) is False
    assert reserva(base, UNO) == la_de_beto

    # Y con la marca correcta sí la saca, que es para lo que existe.
    assert correr(cdc._sacar_la_vencida(base, UNO, la_de_beto["marca"])) is True


def test_EL_CPF_TOMADO_SE_AVISA_ANTES_QUE_LA_CONTRASENA(cliente):
    """El aviso del CPF llega antes que el de la contraseña, a propósito.

    Es lo único que aporta la comprobación temprana: `tomar` frenaría igual el
    registro unas líneas más adelante, con el mismo mensaje. La diferencia es
    que sin ella la persona arregla primero la contraseña, la manda de nuevo, y
    RECIEN AHI se entera de que ese CPF no era una opción.
    """
    registrar(cliente, "ana@ejemplo.com", UNO)
    r = cliente.post("/api/auth/register", json={
        "name": "Beto", "email": "beto@ejemplo.com", "cpf_number": UNO,
        "password": "Clave.larga1!", "confirm_password": "Otra.distinta1!"})

    assert r.status_code == 400
    assert "cpf" in r.json()["detail"].lower(), r.text
