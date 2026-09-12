"""
tests/test_bono_de_bienvenida.py — El bono de quien se registra y el del código.

LAS DOS REGLAS QUE SE PRUEBAN

    Quien se registra con el código de otro recibe un bono BLOQUEADO, que se
    libera al aprobarse su verificación de identidad y que después se gasta
    SOLO en envíos a Venezuela.

    El dueño del código cobra cuando su referido verifica. Eso vale para las
    primeras diez cuentas; de la once en adelante hace falta además que esa
    cuenta haga su primer envío, por encima de un mínimo.

LAS TRES GUARDAS QUE MAS IMPORTAN

    1. QUE EL DESBLOQUEO CUELGUE DE LAS TRES PUERTAS DEL KYC.

       Hay tres lugares que escriben `verification_status: "verified"`. Si el
       desbloqueo colgara de uno, a los aprobados por los otros dos el bono les
       quedaría bloqueado PARA SIEMPRE y en silencio. No hay error que mirar: el
       usuario ve plata que no puede usar y escribe a soporte.

       `test_las_tres_puertas_del_kyc_liberan_el_bono` lo comprueba llamando a
       las tres, y `test_ninguna_puerta_nueva_del_kyc_se_olvida_del_bono`
       recorre el repositorio y se pone rojo si aparece una cuarta.

    2. QUE EL BONO NO SE PUEDA GASTAR EN OTRA COSA.

       La regla del producto es «sólo envíos a Venezuela». Se sostiene porque el
       bono vive en su propia cuenta y una sola ruta sabe debitarla. Si otra
       ruta empezara a nombrarla, la regla se caería sin que ningún test de
       comportamiento lo note: por eso hay una guarda de FORMA que cuenta quién
       menciona esa cuenta.

    3. QUE UN DOCUMENTO NO COBRE DOS VECES.

       La misma persona con dos correos y su propio código. Al registrarse no
       hay con qué detectarlo; al aprobarse el KYC sí, porque ahí está el CPF.
"""
import asyncio
import ast
import os
import pathlib
import sys
from decimal import Decimal

import pytest
from bson import Decimal128

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import (                                      # noqa: E402
    ensenarle_decimal128_a_mongomock, usar_base)

# `mongomock` no sabe sumar `Decimal128`: un `$inc` con ese tipo revienta con
# un TypeError. No es un defecto del producto —MongoDB sí lo hace— pero sin
# esto ningún test que mueva plata puede correr, y este archivo mueve plata en
# casi todos. El parche vive en `conftest` porque el saldo en `Decimal128` es
# una propiedad de toda la aplicación y no de un módulo.
ensenarle_decimal128_a_mongomock()
from services import bonos, configuracion as cfg            # noqa: E402
from services.money import to_decimal128                    # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


async def _sembrar(base, *, tope=None, bono_referido=None, bono_referente=None,
                   minimo=None):
    """Quien refiere y quien fue referido, con la configuración del caso.

    La plata se escribe con `to_decimal128`, igual que la escribe la
    aplicación: `mongomock` conserva el tipo SOLO si el test lo inserta así, y
    un test que escribe 15.0 a secas pasa con el producto roto.
    """
    await base.users.insert_many([
        {"user_id": "u_refiere", "email": "refiere@example.com", "role": "user",
         "referral_code": "REFDUENO001",
         "balance_ris": to_decimal128(Decimal("0")),
         "balance_ris_bono": to_decimal128(Decimal("0"))},
        {"user_id": "u_referido", "email": "referido@example.com", "role": "user",
         "referral_code": "REFOTRO0002", "referred_by": "REFDUENO001",
         "verification_status": "pending",
         "balance_ris": to_decimal128(Decimal("0")),
         "balance_ris_bono": to_decimal128(Decimal("0"))},
    ])
    for clave, valor in (("referidos_que_pagan_con_solo_kyc", tope),
                         ("bono_al_referido", bono_referido),
                         ("bono_a_quien_refiere", bono_referente),
                         ("minimo_del_primer_envio", minimo)):
        if valor is not None:
            limpio, motivo = cfg.normalizar(clave, valor)
            assert motivo is None, motivo
            await cfg.escribir(base, clave, limpio)


async def _saldos(base, user_id):
    u = await base.users.find_one({"user_id": user_id})
    from services.money import from_db
    return (from_db(u.get("balance_ris")), from_db(u.get("balance_ris_bono")),
            (u.get("bono") or {}))


# ══════════════════════════════════════════════════════════════════════════
# 1. Al registrarse
# ══════════════════════════════════════════════════════════════════════════

def test_el_bono_se_acredita_bloqueado_y_en_su_propia_cuenta(base):
    async def caso():
        await _sembrar(base)
        informe = await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        assert informe["acreditado"] is True, informe

        ris, bono, estado = await _saldos(base, "u_referido")
        assert bono == Decimal("15.00"), "el bono no llegó a su cuenta"
        assert ris == Decimal("0.00"), (
            "el bono se acreditó al saldo normal. Ahí queda gastable en "
            "cualquier cosa y la regla «sólo envíos a Venezuela» se pierde.")
        assert estado["estado"] == bonos.BLOQUEADO
        assert estado["referente"] == "u_refiere"
        assert estado["pago_al_referente"] == bonos.PENDIENTE_KYC
    corre(caso())


def test_el_bono_se_guarda_en_decimal128(base):
    """La diferencia que `mongomock` no puede ver y que ya causó dos 500."""
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        crudo = await base.users.find_one({"user_id": "u_referido"})
        assert isinstance(crudo["balance_ris_bono"], Decimal128), (
            f"quedó en {type(crudo['balance_ris_bono']).__name__}")
    corre(caso())


def test_sin_codigo_no_hay_bono(base):
    async def caso():
        await _sembrar(base)
        informe = await bonos.al_registrarse(base, "u_referido", "")
        assert informe["acreditado"] is False
        assert (await _saldos(base, "u_referido"))[1] == Decimal("0.00")
    corre(caso())


def test_un_codigo_sin_dueno_no_acredita_ni_revienta(base):
    """Pasa si el dueño borró su cuenta en los 15 minutos de la pendiente."""
    async def caso():
        await _sembrar(base)
        informe = await bonos.al_registrarse(base, "u_referido", "REFFANTASMA")
        assert informe["acreditado"] is False
        assert informe["motivo"] == "codigo_sin_dueno"
    corre(caso())


def test_el_bono_en_cero_apaga_la_promocion_sin_desplegar(base):
    """Es la forma de cortarla desde el panel, y tiene que ser un no-op."""
    async def caso():
        await _sembrar(base, bono_referido="0")
        informe = await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        assert informe["acreditado"] is False
        assert informe["motivo"] == "bono_en_cero"
        assert (await _saldos(base, "u_referido"))[1] == Decimal("0.00")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Al aprobarse el KYC
# ══════════════════════════════════════════════════════════════════════════

def test_al_verificar_se_libera_el_bono_Y_LA_PLATA_NO_SE_MUEVE(base):
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        informe = await bonos.al_aprobarse_el_kyc(
            base, "u_referido", documento="111.222.333-44")
        assert informe["liberado"] is True, informe

        ris, bono, estado = await _saldos(base, "u_referido")
        assert estado["estado"] == bonos.LIBERADO
        assert bono == Decimal("15.00"), (
            "el bono se movió de cuenta al liberarse. Tiene que quedarse donde "
            "está: lo que cambia es el estado, no dónde vive la plata.")
        assert ris == Decimal("0.00")
    corre(caso())


def test_al_verificar_el_dueno_del_codigo_cobra_libre(base):
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        informe = await bonos.al_aprobarse_el_kyc(base, "u_referido",
                                                  documento="111")
        assert informe["pagado_al_referente"] is True, informe

        ris, bono, _ = await _saldos(base, "u_refiere")
        assert ris == Decimal("5.00"), "el dueño del código no cobró"
        assert bono == Decimal("0.00"), (
            "al dueño del código se le acreditó en la cuenta del bono. Él cobra "
            "LIBRE: ya es un usuario nuestro.")
    corre(caso())


def test_aprobar_dos_veces_no_paga_dos_veces(base):
    """La guarda más fácil de olvidar: un administrador aprueba, el panel se
    queda cargando, y aprueba otra vez."""
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")
        segunda = await bonos.al_aprobarse_el_kyc(base, "u_referido",
                                                  documento="111")
        assert segunda["liberado"] is False
        assert segunda["motivo"] == "sin_bono_bloqueado"

        ris, bono, _ = await _saldos(base, "u_refiere")
        assert ris == Decimal("5.00"), f"cobró dos veces: {ris}"
        assert (await _saldos(base, "u_referido"))[1] == Decimal("15.00")
    corre(caso())


def test_pasado_el_tope_el_dueno_del_codigo_espera_el_primer_envio(base):
    async def caso():
        # Tope en cero: el primer referido ya está «pasado el tope».
        await _sembrar(base, tope="0")
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        informe = await bonos.al_aprobarse_el_kyc(base, "u_referido",
                                                  documento="111")
        assert informe["liberado"] is True, "el bono del referido se libera igual"
        assert informe["pagado_al_referente"] is False
        assert informe["motivo"] == "espera_primer_envio"

        assert (await _saldos(base, "u_refiere"))[0] == Decimal("0.00")
        assert (await _saldos(base, "u_referido"))[2]["pago_al_referente"] \
            == bonos.PENDIENTE_ENVIO
    corre(caso())


def test_el_contador_de_referidos_no_se_reinicia(base):
    """Diez de por vida, no diez por mes. Fue decisión del dueño del proyecto."""
    async def caso():
        await _sembrar(base, tope="2")
        for i in range(4):
            uid = f"u_ref_{i}"
            await base.users.insert_one({
                "user_id": uid, "email": f"r{i}@example.com", "role": "user",
                "referred_by": "REFDUENO001",
                "balance_ris": to_decimal128(Decimal("0")),
                "balance_ris_bono": to_decimal128(Decimal("0"))})
            await bonos.al_registrarse(base, uid, "REFDUENO001")
            await bonos.al_aprobarse_el_kyc(base, uid, documento=f"doc{i}")

        dueno = await base.users.find_one({"user_id": "u_refiere"})
        assert dueno["referidos_con_kyc"] == 4, (
            "el contador tiene que sumar los cuatro, pagados o no")
        # Dos pagados (el tope) por 5 cada uno.
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("10.00")
        for i in (0, 1):
            assert (await _saldos(base, f"u_ref_{i}"))[2]["pago_al_referente"] \
                == bonos.PAGADO
        for i in (2, 3):
            assert (await _saldos(base, f"u_ref_{i}"))[2]["pago_al_referente"] \
                == bonos.PENDIENTE_ENVIO
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. El primer envío, para los que pasaron el tope
# ══════════════════════════════════════════════════════════════════════════

def test_el_primer_envio_por_encima_del_minimo_paga_al_referente(base):
    async def caso():
        await _sembrar(base, tope="0", minimo="100")
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("0.00")

        informe = await bonos.al_enviar_a_venezuela(base, "u_referido", "150")
        assert informe["pagado_al_referente"] is True, informe
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("5.00")
    corre(caso())


def test_un_envio_menor_al_minimo_no_paga(base):
    """Sin mínimo, un envío de diez reales alcanzaría para cobrar el bono."""
    async def caso():
        await _sembrar(base, tope="0", minimo="100")
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")

        informe = await bonos.al_enviar_a_venezuela(base, "u_referido", "10")
        assert informe["pagado_al_referente"] is False
        assert informe["motivo"] == "envio_menor_al_minimo"
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("0.00")
    corre(caso())


def test_dos_envios_no_pagan_dos_veces(base):
    async def caso():
        await _sembrar(base, tope="0", minimo="100")
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")
        await bonos.al_enviar_a_venezuela(base, "u_referido", "150")
        segundo = await bonos.al_enviar_a_venezuela(base, "u_referido", "150")
        assert segundo["pagado_al_referente"] is False
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("5.00")
    corre(caso())


def test_quien_cobro_con_el_kyc_no_vuelve_a_cobrar_al_enviar(base):
    async def caso():
        await _sembrar(base)          # tope de fábrica: 10
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")
        await bonos.al_enviar_a_venezuela(base, "u_referido", "500")
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("5.00")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. Un documento no cobra dos veces
# ══════════════════════════════════════════════════════════════════════════

def test_el_mismo_documento_con_dos_cuentas_cobra_una_sola_vez(base):
    async def caso():
        await _sembrar(base)
        await base.users.insert_one({
            "user_id": "u_clon", "email": "clon@example.com", "role": "user",
            "referred_by": "REFDUENO001",
            "balance_ris": to_decimal128(Decimal("0")),
            "balance_ris_bono": to_decimal128(Decimal("0"))})

        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_registrarse(base, "u_clon", "REFDUENO001")

        primero = await bonos.al_aprobarse_el_kyc(
            base, "u_referido", documento="123.456.789-00")
        assert primero["liberado"] is True

        # El mismo CPF, escrito distinto: los puntos y el guión no cuentan.
        segundo = await bonos.al_aprobarse_el_kyc(
            base, "u_clon", documento="12345678900")
        assert segundo["liberado"] is False, segundo
        assert segundo["motivo"] == "documento_repetido"

        ris_clon, bono_clon, estado_clon = await _saldos(base, "u_clon")
        assert bono_clon == Decimal("0.00"), (
            "el bono de la cuenta repetida sigue ahí. Un bono que no se va a "
            "pagar no puede quedar como deuda en el libro.")
        assert estado_clon["estado"] == bonos.ANULADO_POR_DOCUMENTO
        # Cobró una sola vez: 5 por el primero y nada por el clon.
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("5.00")
    corre(caso())


def test_el_documento_se_guarda_hasheado_y_nunca_en_claro(base):
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido",
                                        documento="123.456.789-00")
        filas = await base[bonos.COLECCION_DE_DOCUMENTOS].find({}).to_list(10)
        assert len(filas) == 1
        guardado = str(filas[0])
        for pedazo in ("123456789", "123.456.789", "789-00"):
            assert pedazo not in guardado, (
                f"el documento quedó en claro en la colección: {pedazo!r}")
        assert filas[0]["_id"] == bonos.huella_del_documento("12345678900")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. LA GUARDA GRANDE: las tres puertas del KYC
# ══════════════════════════════════════════════════════════════════════════
#
# Si el desbloqueo colgara de una sola, a los aprobados por las otras el bono
# les quedaría bloqueado para siempre y en silencio. Se vigila de dos formas:
# llamando a las tres (comportamiento) y recorriendo el repositorio (forma).

# Donde está permitido escribir `verification_status: "verified"` SIN liberar
# un bono, y por qué. La lista es corta a propósito: cada línea es una puerta
# que queda sin vigilar.
ESCRITURAS_PERMITIDAS_SIN_BONO = {
    # Crea una cuenta de ADMINISTRADOR nueva, con la verificación ya puesta.
    # Una cuenta que nace administradora no viene de un código de referido y no
    # tiene bono que liberar. No es una puerta del KYC.
    ("admin_routes.py", "create_sub_admin"),
}

LLAMADA_AL_BONO = "al_aprobarse_el_kyc"
MARCA_DE_VERIFICADO = '"verification_status": "verified"'


def _escrituras_del_estado_verificado():
    """`{(archivo, funcion): llama_al_bono}` de todo el backend, sin los tests.

    Se usa el árbol del código y no una búsqueda de texto por dos motivos.

    El primero: hace falta saber en qué FUNCION cae cada escritura, porque
    `routes/admin.py` tiene dos en dos funciones distintas y una búsqueda plana
    no las separa.

    El segundo lo descubrió este test de la peor forma: la primera versión
    marcó `routes/misc.py:get_admin_dashboard`, que no escribe nada —hace
    `count_documents({"verification_status": "verified"})`, o sea PREGUNTA
    cuántos hay verificados—. Un guardián que acusa lecturas obliga a poner
    excepciones falsas, y una lista de excepciones con entradas falsas adentro
    deja de decir nada.

    La diferencia entre las dos cosas es el tamaño del diccionario. Un filtro
    para contar tiene una sola clave; un `$set` o un documento que se inserta
    traen el campo acompañado —`verified_at`, el correo, el rol—. Así que se
    cuenta como escritura el diccionario con dos claves o más, o el que sea el
    valor de un `$set`.
    """
    encontradas = {}
    for ruta in sorted(_BACKEND.rglob("*.py")):
        partes = set(ruta.relative_to(_BACKEND).parts)
        if partes & {"tests", "scripts", "__pycache__", "venv"}:
            continue
        texto = ruta.read_text(encoding="utf-8")
        if MARCA_DE_VERIFICADO not in texto:
            continue
        try:
            arbol = ast.parse(texto)
        except SyntaxError:                                  # pragma: no cover
            continue

        # De cada nodo, quién lo contiene: hace falta para preguntar si un
        # diccionario es el valor de un `$set`.
        padre = {}
        for nodo in ast.walk(arbol):
            for hijo in ast.iter_child_nodes(nodo):
                padre[hijo] = nodo

        def _es_escritura(d):
            pone_el_estado = any(
                isinstance(k, ast.Constant) and k.value == "verification_status"
                and isinstance(v, ast.Constant) and v.value == "verified"
                for k, v in zip(d.keys, d.values))
            if not pone_el_estado:
                return False
            if len(d.keys) >= 2:
                return True
            arriba = padre.get(d)
            return isinstance(arriba, ast.Dict) and any(
                isinstance(k, ast.Constant) and k.value == "$set"
                for k in arriba.keys)

        escrituras = [d for d in ast.walk(arbol)
                      if isinstance(d, ast.Dict) and _es_escritura(d)]
        if not escrituras:
            continue

        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            propias = [d for d in escrituras
                       if nodo.lineno <= d.lineno <= (nodo.end_lineno or d.lineno)]
            if not propias:
                continue
            cuerpo = ast.get_source_segment(texto, nodo) or ""
            encontradas[(ruta.name, nodo.name)] = LLAMADA_AL_BONO in cuerpo
    return encontradas


# Las cuatro que tienen que aparecer. Escritas a mano para que el buscador no
# pueda quedarse callado: si encuentra menos, o si encuentra la LECTURA de
# `misc.py`, el test de abajo se pone rojo.
ESCRITURAS_ESPERADAS = {
    ("admin.py", "decide_verification"),
    ("admin.py", "process_verification"),
    ("kyc_admin.py", "approve_kyc"),
    ("admin_routes.py", "create_sub_admin"),
}


def test_el_buscador_de_puertas_del_kyc_sirve():
    """La comprobación de la guarda de abajo: que mire lo que tiene que mirar.

    Un buscador que encuentra de menos deja pasar una puerta sin vigilar. Uno
    que encuentra de más —lecturas, por ejemplo— obliga a poner excepciones
    falsas, y entonces la lista de excepciones deja de significar algo.
    """
    puertas = set(_escrituras_del_estado_verificado())
    faltan = ESCRITURAS_ESPERADAS - puertas
    assert not faltan, (
        f"el buscador ya no encuentra {sorted(faltan)}. Si esas funciones se "
        "renombraron o se movieron, hay que actualizar ESCRITURAS_ESPERADAS; "
        "si dejaron de escribir el estado, sobran de la lista.")
    assert ("misc.py", "get_admin_dashboard") not in puertas, (
        "el buscador está contando una LECTURA como escritura: "
        "`count_documents({\"verification_status\": \"verified\"})` pregunta "
        "cuántos hay verificados, no verifica a nadie.")


def test_ninguna_puerta_nueva_del_kyc_SE_OLVIDA_DEL_BONO():
    """LA GUARDA QUE IMPORTA.

    Quien agregue una cuarta forma de aprobar un KYC —o mueva una de las tres—
    se encuentra con este rojo y con el motivo. Sin esto, el defecto es
    invisible: el usuario ve plata que no puede usar y nadie sabe por qué.
    """
    olvidadas = [
        f"{archivo}:{funcion}"
        for (archivo, funcion), llama
        in sorted(_escrituras_del_estado_verificado().items())
        if not llama and (archivo, funcion) not in ESCRITURAS_PERMITIDAS_SIN_BONO
    ]
    assert not olvidadas, (
        f"{olvidadas} escribe(n) {MARCA_DE_VERIFICADO} y no llama(n) a "
        f"bonos.{LLAMADA_AL_BONO}. A las cuentas aprobadas por ahí el bono les "
        "va a quedar bloqueado PARA SIEMPRE y en silencio. Agregá la llamada, "
        "o agregá la función a ESCRITURAS_PERMITIDAS_SIN_BONO con el motivo "
        "escrito al lado.")


def test_las_tres_puertas_del_kyc_liberan_el_bono(base, monkeypatch):
    """Comportamiento, no forma: se llaman las puertas y se mira el resultado.

    La guarda de forma comprueba que la llamada ESTE; ésta comprueba que
    FUNCIONE. Las dos hacen falta: una llamada puesta en el lugar equivocado
    —adentro de la rama del rechazo, por ejemplo— pasa la primera y falla ésta.
    """
    from models.user import User
    from routes import admin as rutas_admin, kyc_admin as rutas_kyc

    jefa = User(user_id="u_jefa", name="Jefa", email="jefa@example.com",
                role="super_admin")

    async def sin_aviso(*a, **k):
        return None
    monkeypatch.setattr(rutas_admin, "create_notification", sin_aviso)
    monkeypatch.setattr(rutas_kyc, "create_notification", sin_aviso)

    async def preparar(uid):
        await base.users.insert_one({
            "user_id": uid, "email": f"{uid}@example.com", "role": "user",
            "referred_by": "REFDUENO001", "verification_status": "pending",
            "balance_ris": to_decimal128(Decimal("0")),
            "balance_ris_bono": to_decimal128(Decimal("0"))})
        await base.verifications.insert_one({
            "verification_id": f"v_{uid}", "user_id": uid, "status": "pending",
            "submitted_at": None, "cpf_number": f"999{uid}"})
        await bonos.al_registrarse(base, uid, "REFDUENO001")

    async def todo():
        await _sembrar(base, tope="100")

        # Puerta 1: aprobar por el id de la verificación. Recibe un `dict`
        # crudo, no un modelo: la firma es `(request, peticion, admin)`.
        await preparar("u_p1")
        await rutas_admin.decide_verification(
            {"verification_id": "v_u_p1", "approved": True},
            peticion=None, admin=jefa)
        assert (await _saldos(base, "u_p1"))[2]["estado"] == bonos.LIBERADO,             "la puerta de `decide_verification` no liberó el bono"

        # Puerta 2: la ruta vieja, que sigue viva.
        await preparar("u_p2")
        await rutas_admin.process_verification("u_p2", "approve", admin=jefa)
        assert (await _saldos(base, "u_p2"))[2]["estado"] == bonos.LIBERADO,             "la puerta vieja de `process_verification` no liberó el bono"

        # Puerta 3: el panel de KYC que se usa hoy.
        await preparar("u_p3")
        await rutas_kyc.approve_kyc("v_u_p3", payload={}, admin=jefa)
        assert (await _saldos(base, "u_p3"))[2]["estado"] == bonos.LIBERADO,             "la puerta del panel de KYC no liberó el bono"

        # Y los tres le pagaron al dueño del código: 5 por cada uno.
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("15.00")
    corre(todo())


# ══════════════════════════════════════════════════════════════════════════
# 6. Gastar el bono: sólo en el envío a Venezuela, y sólo si está liberado
# ══════════════════════════════════════════════════════════════════════════

async def _listo_para_enviar(base, uid, *, ris="0", bono="0",
                             estado=bonos.LIBERADO):
    """Una cuenta con saldo, un beneficiario y una tasa. Lo mínimo para enviar."""
    await base.users.update_one({"user_id": uid}, {"$set": {
        "balance_ris": to_decimal128(Decimal(ris)),
        "balance_ris_bono": to_decimal128(Decimal(bono)),
        "bono.estado": estado,
    }})
    await base.beneficiaries.insert_one({
        "beneficiary_id": f"b_{uid}", "user_id": uid, "full_name": "Tía",
        "bank": "Banco", "account_number": "1234", "payment_type": "transferencia"})
    if not await base.rates.find_one({}):
        await base.rates.insert_one({"ris_to_ves": 50.0, "updated_at": None})


async def _enviar(base, uid, monto):
    """Llama a la ruta de verdad, con la sesión sustituida."""
    from models.user import User
    from routes import transactions as rutas_tx

    class _Pedido:
        amount = float(monto)
        beneficiary_id = f"b_{uid}"
        idempotency_key = f"k_{uid}_{monto}"

    quien = User(user_id=uid, name="Quien", email=f"{uid}@example.com",
                 role="user")
    return await rutas_tx.create_withdrawal(_Pedido(), current_user=quien)


def test_el_envio_a_venezuela_gasta_PRIMERO_el_bono(base, monkeypatch):
    """El bono sólo sirve para esto; el saldo sirve para todo.

    Gastar primero el que menos sirve le deja a la persona la mayor libertad
    con lo que le queda.
    """
    from routes import transactions as rutas_tx

    async def sin_aviso(*a, **k):
        return None
    monkeypatch.setattr(rutas_tx, "create_notification", sin_aviso)

    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await _listo_para_enviar(base, "u_referido", ris="100", bono="15")

        await _enviar(base, "u_referido", 40)

        ris, bono, _ = await _saldos(base, "u_referido")
        assert bono == Decimal("0.00"), f"el bono no se usó: quedó {bono}"
        assert ris == Decimal("75.00"), (
            f"el saldo quedó en {ris} y tenía que quedar en 75.00: 15 del bono "
            "más 25 del saldo.")
    corre(caso())


def test_un_bono_BLOQUEADO_no_se_puede_gastar(base, monkeypatch):
    from fastapi import HTTPException
    from routes import transactions as rutas_tx

    async def sin_aviso(*a, **k):
        return None
    monkeypatch.setattr(rutas_tx, "create_notification", sin_aviso)

    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        # Saldo normal en cero y el bono bloqueado: no tiene con qué enviar.
        await _listo_para_enviar(base, "u_referido", ris="0", bono="15",
                                 estado=bonos.BLOQUEADO)
        with pytest.raises(HTTPException) as e:
            await _enviar(base, "u_referido", 10)
        assert e.value.status_code == 400
        assert "insuficiente" in e.value.detail.lower()

        _, bono, _ = await _saldos(base, "u_referido")
        assert bono == Decimal("15.00"), "se gastó un bono que estaba bloqueado"
    corre(caso())


def test_una_cuenta_VIEJA_sin_el_campo_del_bono_sigue_pudiendo_enviar(base,
                                                                      monkeypatch):
    """La regresión que más fácil se cuela con un campo nuevo.

    Las cuentas anteriores al bono no tienen `balance_ris_bono`. Si el filtro
    del débito nombrara esa cuenta siempre, un `$gte` contra un campo ausente
    no coincidiría y el envío se rechazaría por «saldo insuficiente» a TODO el
    que se registró antes de este cambio.
    """
    from routes import transactions as rutas_tx

    async def sin_aviso(*a, **k):
        return None
    monkeypatch.setattr(rutas_tx, "create_notification", sin_aviso)

    async def caso():
        await base.users.insert_one({
            "user_id": "u_vieja", "email": "vieja@example.com", "role": "user",
            "balance_ris": to_decimal128(Decimal("200"))})
        # Sin `balance_ris_bono` y sin `bono`, como quedó en la base.
        await base.beneficiaries.insert_one({
            "beneficiary_id": "b_u_vieja", "user_id": "u_vieja",
            "full_name": "Tía", "payment_type": "transferencia"})
        await base.rates.insert_one({"ris_to_ves": 50.0, "updated_at": None})

        await _enviar(base, "u_vieja", 30)
        u = await base.users.find_one({"user_id": "u_vieja"})
        from services.money import from_db
        assert from_db(u["balance_ris"]) == Decimal("170.00")
    corre(caso())


def test_el_libro_deja_UNA_LINEA_POR_CUENTA_de_la_que_salio_plata(base,
                                                                  monkeypatch):
    """Una sola línea por el total haría que el libro no cuadre con los saldos."""
    from routes import transactions as rutas_tx

    async def sin_aviso(*a, **k):
        return None
    monkeypatch.setattr(rutas_tx, "create_notification", sin_aviso)

    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await _listo_para_enviar(base, "u_referido", ris="100", bono="15")
        await _enviar(base, "u_referido", 40)

        lineas = await base.ledger.find(
            {"user_id": "u_referido", "movement_type": "envio_ves"}).to_list(10)
        por_cuenta = {l["account"]: Decimal(str(l["amount"])) for l in lineas}
        assert set(por_cuenta) == {"balance_ris", bonos.CUENTA_DEL_BONO}, (
            f"se esperaban dos líneas, una por cuenta; hay {sorted(por_cuenta)}")
        assert por_cuenta[bonos.CUENTA_DEL_BONO] == Decimal("15")
        assert por_cuenta["balance_ris"] == Decimal("25")
    corre(caso())


# ── La guarda de forma: que nadie más aprenda a gastar el bono ───────────

# Los únicos archivos que pueden nombrar la cuenta del bono. Cada uno tiene su
# motivo, y agregar uno tiene que costar tanto como pensarlo.
QUIEN_PUEDE_TOCAR_LA_CUENTA_DEL_BONO = {
    # El dueño del bono: lo otorga, lo libera y lo anula.
    "services/bonos.py",
    # Declara qué cuentas existen.
    "services/saldos.py",
    # El plan de cuentas: a qué cuenta contable corresponde.
    "services/contabilidad.py",
    # La ÚNICA ruta que puede gastarlo: el envío a Venezuela.
    "routes/transactions.py",
    # La cuenta nace en cero al crearse el usuario.
    "routes/auth.py",
}


def test_solo_el_envio_a_venezuela_sabe_gastar_el_bono():
    """La regla «sólo envíos a Venezuela» se sostiene sobre esto.

    No hay test de comportamiento que la vigile: habría que probar que CADA una
    de las veinte funciones que mueven plata no toca la cuenta del bono, y la
    que se agregue mañana no estaría en esa lista. Lo que sí se puede vigilar
    es quién la nombra.
    """
    culpables = []
    for ruta in sorted(_BACKEND.rglob("*.py")):
        rel = ruta.relative_to(_BACKEND).as_posix()
        if set(ruta.relative_to(_BACKEND).parts) & {
                "tests", "scripts", "__pycache__", "venv"}:
            continue
        if rel in QUIEN_PUEDE_TOCAR_LA_CUENTA_DEL_BONO:
            continue
        if bonos.CUENTA_DEL_BONO in ruta.read_text(encoding="utf-8"):
            culpables.append(rel)
    assert not culpables, (
        f"{culpables} nombra(n) {bonos.CUENTA_DEL_BONO!r}. El bono se gasta "
        "SOLO en envíos a Venezuela, y esa regla se sostiene porque una sola "
        "ruta sabe debitar esa cuenta. Si hace falta de verdad, agregá el "
        "archivo a QUIEN_PUEDE_TOCAR_LA_CUENTA_DEL_BONO con el motivo al lado.")


def test_el_buscador_de_quien_toca_el_bono_sirve():
    """Que encuentre los que TIENE que encontrar, o no está mirando nada."""
    encontrados = {
        ruta.relative_to(_BACKEND).as_posix()
        for ruta in _BACKEND.rglob("*.py")
        if not (set(ruta.relative_to(_BACKEND).parts)
                & {"tests", "scripts", "__pycache__", "venv"})
        and bonos.CUENTA_DEL_BONO in ruta.read_text(encoding="utf-8")
    }
    faltan = QUIEN_PUEDE_TOCAR_LA_CUENTA_DEL_BONO - encontrados
    assert not faltan, (
        f"el buscador ya no encuentra {sorted(faltan)}, que deberían nombrar la "
        "cuenta del bono. Si alguno dejó de usarla, sacalo de la lista; si el "
        "buscador se rompió, arreglalo.")


# ══════════════════════════════════════════════════════════════════════════
# 7. La contabilidad: el bono liberado es deuda, el bloqueado todavía no
# ══════════════════════════════════════════════════════════════════════════

def test_el_pozo_cuenta_el_bono_LIBERADO_y_no_el_bloqueado(base):
    """La conciliación pregunta «¿por cada RIS que alguien tiene, hay un real?».

    Un bono liberado se puede gastar: es deuda y tiene que estar respaldado.
    Uno bloqueado puede no liberarse nunca —si la persona no verifica, o si su
    documento ya cobró— así que contarlo mostraría un faltante que no es un
    faltante. Un control que denuncia un hueco inexistente se deja de mirar.
    """
    from services import contabilidad

    async def caso():
        await base.users.insert_many([
            {"user_id": "u_lib", "balance_ris": to_decimal128(Decimal("0")),
             "balance_ris_bono": to_decimal128(Decimal("15")),
             "bono": {"estado": bonos.LIBERADO}},
            {"user_id": "u_bloq", "balance_ris": to_decimal128(Decimal("0")),
             "balance_ris_bono": to_decimal128(Decimal("40")),
             "bono": {"estado": bonos.BLOQUEADO}},
        ])
        await base.bank_accounts.insert_one({
            "bank_id": "b1", "name": "Banco BR", "currency": "BRL",
            "balance": to_decimal128(Decimal("1000"))})

        informe = await contabilidad.conciliacion_pozo(db=base)
        assert informe["pasivo"]["total"] == "15.00", (
            f"el pasivo dio {informe['pasivo']['total']}: tiene que contar los "
            "15 liberados y no los 40 bloqueados.")
        desglose = informe["bono_de_bienvenida"]
        assert desglose["liberado_y_en_el_pasivo"] == "15.00"
        assert desglose["bloqueado_y_fuera_del_pasivo"] == "40.00"
        assert any("BLOQUEADO" in t for t in informe["no_incluido"]), (
            "el informe no explica por qué el bloqueado no está")
    corre(caso())


def test_los_asientos_del_bono_estan_declarados():
    """Un `movement_type` sin asiento cae en la cuenta puente y el chequeo de
    integridad lo denuncia. Mejor que falle acá."""
    from services import contabilidad
    for movimiento in ("bono_bienvenida", "bono_referido", "bono_liberado"):
        assert movimiento in contabilidad.ASIENTOS, movimiento
    # El bono es un GASTO de captación, no un movimiento de caja.
    assert contabilidad.ASIENTOS["bono_bienvenida"]["contra"] == "5.1.01"
    assert contabilidad.PLAN_DE_CUENTAS["5.1.01"]["tipo"] == contabilidad.EGRESO
    # Y la cuenta del usuario donde vive es un pasivo.
    assert contabilidad.CUENTA_DEL_USUARIO[bonos.CUENTA_DEL_BONO] == "2.1.05"
    assert contabilidad.PLAN_DE_CUENTAS["2.1.05"]["tipo"] == contabilidad.PASIVO


# ══════════════════════════════════════════════════════════════════════════
# 8. Que la ruta más llamada de la app no se caiga por el saldo nuevo
# ══════════════════════════════════════════════════════════════════════════

def test_auth_me_devuelve_el_saldo_del_bono_SIN_ROMPERSE(base, monkeypatch):
    """Casi se fue a producción así, y el defecto es de los peores que hay.

    `/auth/me` devuelve el documento del usuario entero y convertía a número
    sólo una lista de campos escrita a mano. `Decimal128` NO SE PUEDE
    SERIALIZAR A JSON, así que con el saldo del bono afuera de esa lista la
    ruta —la que llama CADA pantalla al abrirse— habría devuelto 500 a todo el
    que tuviera bono. Y habría aparecido recién en producción, cuando el
    primero cobrara.
    """
    from fastapi.encoders import jsonable_encoder
    from models.user import User
    from routes import auth as rutas_auth

    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        quien = User(user_id="u_referido", name="Quien",
                     email="referido@example.com", role="user")
        devuelto = await rutas_auth.get_me(current_user=quien)
        # Que serialice es la mitad de la prueba; la otra es que el número esté.
        jsonable_encoder(devuelto)
        assert devuelto["balance_ris_bono"] == 15.0
    corre(caso())


def test_auth_me_convierte_CUALQUIER_saldo_y_no_una_lista_escrita_a_mano(base):
    """La guarda de fondo: que el próximo saldo nuevo no repita el problema.

    Se inventa un campo `balance_` que no existe en ninguna parte del código y
    se exige que salga convertido igual. Si alguien vuelve a poner una lista
    de nombres, este test se pone rojo.
    """
    from fastapi.encoders import jsonable_encoder
    from models.user import User
    from routes import auth as rutas_auth

    async def caso():
        await _sembrar(base)
        await base.users.update_one({"user_id": "u_referido"}, {"$set": {
            "balance_de_algo_que_todavia_no_existe": to_decimal128(Decimal("7"))}})
        quien = User(user_id="u_referido", name="Quien",
                     email="referido@example.com", role="user")
        devuelto = await rutas_auth.get_me(current_user=quien)
        jsonable_encoder(devuelto)
        assert devuelto["balance_de_algo_que_todavia_no_existe"] == 7.0, (
            "el saldo inventado no se convirtió. Si volvió una lista de "
            "nombres escrita a mano, al próximo saldo nuevo le va a pasar lo "
            "mismo que casi le pasó al bono.")
    corre(caso())


def test_el_saldo_del_bono_llega_a_la_pantalla_con_su_leyenda(base):
    """La pantalla no arma el texto: lo manda el servidor.

    Si lo armara la pantalla, el monto y la condición podrían discrepar entre
    los dos lados, y el que se equivoca es siempre el que no se actualizó.
    """
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")

        bloqueado = await bonos.estado_para_la_pantalla(base, "u_referido")
        assert bloqueado["tiene"] is True
        assert bloqueado["bloqueado"] is True
        assert bloqueado["saldo"] == "15.00"
        assert "verificación" in bloqueado["leyenda"]

        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")
        liberado = await bonos.estado_para_la_pantalla(base, "u_referido")
        assert liberado["bloqueado"] is False
        assert "Venezuela" in liberado["leyenda"]

        # Quien no tiene bono no ve nada: un cero en pantalla invita a
        # preguntar por qué es cero.
        assert (await bonos.estado_para_la_pantalla(base, "u_refiere"))["tiene"] \
            is False
    corre(caso())


def test_auth_me_no_le_manda_al_navegador_el_id_de_quien_refirio(base):
    """`bono.referente` es el identificador de OTRA persona.

    La pantalla no lo necesita para nada: muestra un monto y una leyenda. Y el
    documento del usuario sale entero por esta ruta, así que sin reemplazar el
    subdocumento por su versión de pantalla, el id de quien refirió —y el
    código usado— viajarían al navegador de cada visitante.
    """
    from models.user import User
    from routes import auth as rutas_auth

    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        quien = User(user_id="u_referido", name="Quien",
                     email="referido@example.com", role="user")
        devuelto = await rutas_auth.get_me(current_user=quien)
        bono = devuelto["bono"]
        for interno in ("referente", "codigo", "pago_al_referente"):
            assert interno not in bono, (
                f"`bono.{interno}` llegó al navegador. Lo que la pantalla "
                f"necesita es el monto y la leyenda; lo que hay es {sorted(bono)}.")
        assert "u_refiere" not in str(bono)
        assert set(bono) == {"tiene", "saldo", "bloqueado", "leyenda"}
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 9. Los avisos: que salgan, y que no cuenten lo que no es asunto de nadie
# ══════════════════════════════════════════════════════════════════════════

async def _avisos_de(base, user_id):
    return await base.notifications.find({"user_id": user_id}).to_list(20)


def test_al_dueno_del_codigo_le_avisan_que_cobro(base):
    """Sin esto los cinco reales aparecían en su saldo y nadie le decía por qué.

    El único rastro era una línea en su historial, que hay que ir a buscar.
    """
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")

        avisos = await _avisos_de(base, "u_refiere")
        assert len(avisos) == 1, f"se esperaba un aviso y hay {len(avisos)}"
        assert avisos[0]["type"] == "bono_referido"
        assert "5,00" in avisos[0]["message"], (
            f"el aviso no dice cuánto cobró: {avisos[0]['message']!r}")
    corre(caso())


def test_el_aviso_del_que_refiere_NO_NOMBRA_AL_REFERIDO(base):
    """Quien invitó no tiene por qué enterarse de que esa persona completó su
    verificación de identidad, ni cuándo. Es dato de otro."""
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")

        texto = str(await _avisos_de(base, "u_refiere"))
        for dato_ajeno in ("u_referido", "referido@example.com"):
            assert dato_ajeno not in texto, (
                f"el aviso filtra {dato_ajeno!r}, que es dato de la otra "
                f"persona. El aviso completo: {texto}")
    corre(caso())


def test_al_referido_le_avisan_cuando_su_bono_queda_disponible(base):
    """Es el momento en que la plata pasa de promesa a gastable."""
    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        assert await _avisos_de(base, "u_referido") == [], (
            "no hay que avisar nada al otorgarlo: todavía no se puede usar")

        await bonos.al_aprobarse_el_kyc(base, "u_referido", documento="111")
        avisos = await _avisos_de(base, "u_referido")
        assert len(avisos) == 1
        assert avisos[0]["type"] == "bono_liberado"
        assert "15,00" in avisos[0]["message"]
        assert "Venezuela" in avisos[0]["message"], (
            "el aviso tiene que decir para qué sirve, que es la única "
            "condición que importa")
    corre(caso())


def test_un_aviso_que_falla_NO_DESHACE_LA_PLATA(base, monkeypatch):
    """La guarda de fondo de los dos avisos.

    Un aviso que no sale es un reclamo; una acreditación que se cae porque el
    aviso falló es plata que no llegó.
    """
    from services import notifications

    async def explota(*a, **k):
        raise RuntimeError("el servicio de avisos se cayó")
    monkeypatch.setattr(notifications, "create_notification", explota)

    async def caso():
        await _sembrar(base)
        await bonos.al_registrarse(base, "u_referido", "REFDUENO001")
        informe = await bonos.al_aprobarse_el_kyc(base, "u_referido",
                                                  documento="111")
        assert informe["liberado"] is True, informe
        assert informe["pagado_al_referente"] is True, informe
        assert (await _saldos(base, "u_refiere"))[0] == Decimal("5.00")
        assert (await _saldos(base, "u_referido"))[2]["estado"] == bonos.LIBERADO
    corre(caso())


def test_los_dos_avisos_del_bono_salen_tambien_por_correo():
    """La tabla del correo y la del código tienen que decir lo mismo.

    Hay un test que las compara en los dos sentidos; esto es el recordatorio
    en el archivo donde vive la función que los emite.
    """
    from services import avisos_por_correo
    for clase in ("bono_liberado", "bono_referido"):
        assert clase in avisos_por_correo.POR_CORREO, (
            f"{clase} mueve plata y no manda correo. Agregalo a POR_CORREO.")


# ══════════════════════════════════════════════════════════════════════════
# 10. La lista de referidos, y qué NO le cuenta de cada persona
# ══════════════════════════════════════════════════════════════════════════

async def _sembrar_referidos(base, cuantos, *, pagados=0):
    """`cuantos` cuentas con el código de u_refiere, `pagados` ya cobradas."""
    for i in range(cuantos):
        uid = f"u_lista_{i:03d}"
        await base.users.insert_one({
            "user_id": uid,
            "name": f"Persona{i} Apellido{i}",
            "full_name": f"Persona{i} Apellido{i} Segundo{i}",
            "email": f"persona{i}@secreto.example.com",
            "role": "user", "referred_by": "REFDUENO001",
            # Un dato bien sensible, para comprobar que no se filtra.
            "cpf": f"111222333{i:02d}",
            "verification_status": "pending",
            "balance_ris": to_decimal128(Decimal("0")),
            "balance_ris_bono": to_decimal128(Decimal("0")),
            "bono": {
                "estado": bonos.BLOQUEADO,
                "monto": "15.00",
                "codigo": "REFDUENO001",
                "referente": "u_refiere",
                "otorgado_en": None,
                "pago_al_referente": (bonos.PAGADO if i < pagados
                                      else bonos.PENDIENTE_KYC),
            },
        })


def test_la_lista_trae_los_numeros_que_cuenta_la_base(base):
    async def caso():
        await _sembrar(base)
        await base.users.delete_one({"user_id": "u_referido"})
        await _sembrar_referidos(base, 7, pagados=3)
        # Lo ganado sale del libro, no de multiplicar.
        await base.ledger.insert_many([
            {"user_id": "u_refiere", "movement_type": "bono_referido",
             "direction": "credit", "amount": 5.0},
            {"user_id": "u_refiere", "movement_type": "bono_referido",
             "direction": "credit", "amount": 5.0},
            # Uno de cuando el monto era otro: el libro dice la verdad y
            # multiplicar por el monto de hoy daría mal.
            {"user_id": "u_refiere", "movement_type": "bono_referido",
             "direction": "credit", "amount": 8.0},
        ])

        r = await bonos.mis_referidos(base, "u_refiere")
        assert r["total"] == 7
        assert r["cobrados"] == 3
        assert r["pendientes"] == 4
        assert r["ganado"] == "18.00", (
            f"lo ganado dio {r['ganado']}: tiene que salir del libro "
            "(5 + 5 + 8) y no de multiplicar los cobrados por el monto de hoy.")
    corre(caso())


# Lo único que puede llevar la fila de un referido. Cada fila es una persona
# que NO es quien mira la pantalla.
CAMPOS_PERMITIDOS_DE_UNA_FILA = {"nombre", "cuando", "cobrado", "motivo"}


def test_la_lista_NO_FILTRA_DATOS_DE_TERCEROS(base):
    """La guarda que más importa de esta pantalla, y la que más costó escribir.

    LA PRIMERA VERSION NO SERVIA, Y VALE CONTAR POR QUE.

    Buscaba datos ajenos en el texto de la respuesta —el correo, el CPF— y
    pasaba con el producto roto de DOS formas distintas:

      · Sacando la proyección de la consulta, no filtraba nada, porque las
        filas se arman con cuatro campos escritos a mano y no con el
        documento entero.
      · Agregando `"correo": persona.get("email")` a la fila, tampoco, porque
        la proyección hace que ese campo llegue en `None` y un `None` no
        contiene «secreto.example.com».

    O sea: dos guardas tapándose entre sí, y el test probando ninguna. Es el
    defecto que `CLAUDE.md` cuenta que ya apareció en este repositorio.

    Ahora se exige que la fila tenga EXACTAMENTE los campos permitidos. Así un
    campo de más se ve, valga lo que valga —incluso `None`—, y la de la
    proyección se prueba aparte, por la forma de la consulta.
    """
    async def caso():
        await _sembrar(base)
        await base.users.delete_one({"user_id": "u_referido"})
        await _sembrar_referidos(base, 3)

        r = await bonos.mis_referidos(base, "u_refiere")
        for fila in r["referidos"]:
            de_mas = set(fila) - CAMPOS_PERMITIDOS_DE_UNA_FILA
            assert not de_mas, (
                f"la fila de un referido lleva {sorted(de_mas)}, que no está "
                "en la lista de lo permitido. Cada fila es una persona que no "
                "es quien mira: si hace falta un campo más, agregalo a "
                "CAMPOS_PERMITIDOS_DE_UNA_FILA con el motivo escrito al lado.")
            assert set(fila) == CAMPOS_PERMITIDOS_DE_UNA_FILA, (
                f"a la fila le falta {sorted(CAMPOS_PERMITIDOS_DE_UNA_FILA - set(fila))}")

        # Y por si algún día las filas se armaran de otra forma: que en toda la
        # respuesta no aparezca ningún dato ajeno.
        crudo = str(r)
        for dato_ajeno in ("secreto.example.com", "111222333",
                           "balance_ris", "u_lista_000"):
            assert dato_ajeno not in crudo, (
                f"la respuesta filtra {dato_ajeno!r}: {crudo[:400]}")
    corre(caso())


def test_la_consulta_de_la_lista_usa_PROYECCION_POR_LISTA_DE_LO_PERMITIDO():
    """La otra mitad, y se vigila por la FORMA porque no se puede por el
    resultado.

    Sin proyección la respuesta sale igual —las filas se arman a mano— así que
    ningún test de comportamiento lo nota. Lo que cambia es que la aplicación
    se trae a memoria el documento COMPLETO de cada referido: sus fotos de
    documento de identidad, su CPF, sus saldos. Con veinte filas por página,
    veinte documentos enteros para mostrar cuatro campos.

    SE EXIGE QUE LA PROYECCION NOMBRE LOS CAMPOS. La primera versión de este
    test sólo pedía que hubiera un `{"_id": 0`, y pasaba con la proyección
    reducida a exactamente eso —que trae el documento entero menos el `_id`—.
    Una proyección que no nombra nada no es una lista de lo permitido: es el
    documento completo con otra cara.
    """
    import ast
    import re

    fuente = (_BACKEND / "services" / "bonos.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    cuerpo = None
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                and nodo.name == "mis_referidos"):
            cuerpo = ast.get_source_segment(fuente, nodo) or ""
    assert cuerpo, "no se encontró `mis_referidos` en services/bonos.py"

    consultas = re.findall(r"db\.users\.find\(filtro,\s*(\{[^}]*\})", cuerpo)
    assert consultas, (
        "la consulta de la lista dejó de llevar proyección. Sin ella se trae "
        "el documento entero de cada referido —documento de identidad, CPF, "
        "saldos— para mostrar cuatro campos.")

    for proyeccion in consultas:
        incluidos = set(re.findall(r'"(\w+)"\s*:\s*1', proyeccion))
        assert incluidos, (
            f"la proyección {proyeccion} no NOMBRA ningún campo. Una que sólo "
            'dice `{"_id": 0}` trae el documento entero menos el `_id`: es lo '
            "mismo que no tener proyección.")
        excluidos = set(re.findall(r'"(\w+)"\s*:\s*0', proyeccion)) - {"_id"}
        assert not excluidos, (
            f"la proyección excluye {sorted(excluidos)}. Tiene que ser una "
            "lista de lo PERMITIDO: una de exclusiones deja pasar cada campo "
            "nuevo del documento hasta que alguien se acuerde.")


def test_el_nombre_sale_acortado_y_sin_el_apellido_entero(base):
    async def caso():
        await _sembrar(base)
        await base.users.delete_one({"user_id": "u_referido"})
        await _sembrar_referidos(base, 1)
        r = await bonos.mis_referidos(base, "u_refiere")
        assert r["referidos"][0]["nombre"] == "Persona0 A.", (
            f"salió {r['referidos'][0]['nombre']!r}")
    corre(caso())


def test_cada_pendiente_dice_su_motivo(base):
    """Decisión del dueño del proyecto: el motivo se muestra.

    Sin el motivo la pantalla no sirve para lo único que se le pide, que es
    saber a quién recordarle.
    """
    async def caso():
        await _sembrar(base)
        await base.users.delete_one({"user_id": "u_referido"})
        await _sembrar_referidos(base, 1)
        await base.users.update_one({"user_id": "u_lista_000"}, {
            "$set": {"bono.pago_al_referente": bonos.PENDIENTE_ENVIO}})

        fila = (await bonos.mis_referidos(base, "u_refiere"))["referidos"][0]
        assert fila["cobrado"] is False
        assert "primer envío" in fila["motivo"], fila
    corre(caso())


def test_la_lista_esta_paginada_de_a_veinte(base):
    """Paginada desde el primer día, aunque hoy nadie tenga veinte.

    Una lista sin techo se descubre cuando alguien tiene cuatrocientos y la
    pantalla tarda diez segundos en abrir.
    """
    async def caso():
        await _sembrar(base)
        await base.users.delete_one({"user_id": "u_referido"})
        await _sembrar_referidos(base, 25)

        primera = await bonos.mis_referidos(base, "u_refiere", pagina=1)
        assert len(primera["referidos"]) == 20, (
            f"la primera página trajo {len(primera['referidos'])} filas")
        assert primera["hay_mas"] is True
        assert primera["total"] == 25, "el total es de todos, no de la página"

        segunda = await bonos.mis_referidos(base, "u_refiere", pagina=2)
        assert len(segunda["referidos"]) == 5
        assert segunda["hay_mas"] is False
    corre(caso())


def test_una_pagina_absurda_no_revienta(base):
    async def caso():
        await _sembrar(base)
        await _sembrar_referidos(base, 3)
        for pagina in (0, -5, 99):
            r = await bonos.mis_referidos(base, "u_refiere", pagina=pagina)
            assert r["total"] == 3
            assert isinstance(r["referidos"], list)
    corre(caso())


def test_quien_no_invito_a_nadie_ve_una_lista_vacia_y_no_un_error(base):
    async def caso():
        await _sembrar(base)
        r = await bonos.mis_referidos(base, "u_referido")
        assert r["total"] == 0
        assert r["referidos"] == []
        assert r["ganado"] == "0.00"
    corre(caso())


def test_la_ruta_devuelve_LOS_REFERIDOS_DE_QUIEN_PREGUNTA(base):
    """El `user_id` sale de la sesión y no de un parámetro.

    Si viniera por la dirección, cualquiera pediría la lista de otro cambiando
    un número —y ahí adentro van nombres de terceros—.
    """
    import inspect
    from routes import referidos as rutas

    firma = inspect.signature(rutas.mis_referidos)
    assert set(firma.parameters) == {"pagina", "current_user"}, (
        f"la ruta acepta {sorted(firma.parameters)}. Si aparece un `user_id` "
        "entre los parámetros, se puede pedir la lista de cualquiera.")

    async def caso():
        await _sembrar(base)
        await base.users.delete_one({"user_id": "u_referido"})
        await _sembrar_referidos(base, 2)
        from models.user import User
        quien = User(user_id="u_refiere", name="Dueño",
                     email="refiere@example.com", role="user")
        r = await rutas.mis_referidos(pagina=1, current_user=quien)
        assert r["total"] == 2
    corre(caso())
