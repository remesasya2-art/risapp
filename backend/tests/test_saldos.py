"""
tests/test_saldos.py — El saldo de los usuarios y su línea en el libro.

QUE SE PRUEBA ACA, Y POR QUE

    `services/saldos.py` es el dueño único de `users.balance_ris` y
    `users.balance_ris_terceros`. Vino a tapar dos cosas que estaban copiadas
    por todo el backend:

    1. EL SALDO ANTERIOR SE CALCULABA SOBRE UN VALOR CRUDO DE LA BASE.
       `usuario.get("balance_ris") - monto`, con el campo a veces en
       `Decimal128`, es un `TypeError`. Cuatro sitios lo hacían dentro de un
       `try` que sólo loguea —la plata se movía y la línea del libro se perdía
       en silencio— y uno lo hacía fuera de todo `try`.

    2. HABIA CAMINOS QUE MOVIAN SALDO SIN ASENTAR NADA.

    Los tests de acá van contra mongomock y no contra dobles escritos a mano:
    esto mueve plata, y un doble sólo falla donde su autor pensó que podía
    fallar. Cada propiedad se prueba con el saldo guardado de las DOS formas
    —`float` y `Decimal128`— porque el punto entero del módulo es que dé lo
    mismo.
"""
import asyncio
import os
import subprocess
import sys
import textwrap
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base   # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import saldos                                        # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


async def _usuario(base, saldo, campo="balance_ris", user_id="usr_ana"):
    await base.users.insert_one({
        "user_id": user_id, "email": "ana@example.com",
        "name": "Ana", "role": "user", campo: saldo})
    return user_id


async def _saldo_crudo(base, user_id="usr_ana", campo="balance_ris"):
    doc = await base.users.find_one({"user_id": user_id})
    return doc[campo]


async def _lineas(base, user_id="usr_ana"):
    return await base.ledger.find({"user_id": user_id}).to_list(100)


# ══════════════════════════════════════════════════════════════════════════
# 1. El tipo guardado no importa: es la razón de ser del módulo
# ══════════════════════════════════════════════════════════════════════════

# Las dos formas en que `balance_ris` existe hoy en la base: las rutas viejas lo
# dejaron en `float`, las nuevas escriben `Decimal128`. El mismo usuario puede
# tener una u otra según quién lo tocó último.
GUARDADO_COMO = [
    pytest.param(1000.0, id="float"),
    pytest.param(Decimal128(Decimal("1000.00")), id="Decimal128"),
]


@pytest.mark.parametrize("saldo_inicial", GUARDADO_COMO)
def test_acredita_y_el_saldo_anterior_sale_exacto(base, saldo_inicial):
    async def caso():
        await _usuario(base, saldo_inicial)
        r = await saldos.mover(base, "usr_ana", 250.50, movimiento="recarga_pix")
        assert r["saldo_anterior"] == Decimal("1000.00")
        assert r["saldo_nuevo"] == Decimal("1250.50")
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("1250.50")
    corre(caso())


@pytest.mark.parametrize("saldo_inicial", GUARDADO_COMO)
def test_debita_y_el_saldo_anterior_sale_exacto(base, saldo_inicial):
    async def caso():
        await _usuario(base, saldo_inicial)
        r = await saldos.mover(base, "usr_ana", -300, movimiento="envio_ves")
        assert r["saldo_anterior"] == Decimal("1000.00")
        assert r["saldo_nuevo"] == Decimal("700.00")
    corre(caso())


@pytest.mark.parametrize("saldo_inicial", GUARDADO_COMO)
def test_el_libro_anota_los_saldos_reales_no_una_cuenta_aparte(base, saldo_inicial):
    """EL TEST CENTRAL. Es lo que se perdía cuando la resta reventaba."""
    async def caso():
        await _usuario(base, saldo_inicial)
        await saldos.mover(base, "usr_ana", 250.50, movimiento="recarga_pix")
        linea, = await _lineas(base)
        assert linea["balance_before"] == 1000.00
        assert linea["balance_after"] == 1250.50
        assert linea["amount"] == 250.50
        assert linea["direction"] == "credit"
        assert linea["signed_amount"] == 250.50
        assert linea["account"] == "balance_ris"
        assert linea["movement_type"] == "recarga_pix"
    corre(caso())


def test_un_usuario_sin_el_campo_de_saldo_arranca_en_cero(base):
    """Un usuario viejo puede no tener `balance_ris_terceros` escrito nunca.

    `saldo_de` tiene que devolver 0 y no reventar: leer con `float(...)` sobre
    un campo ausente es un `TypeError`, y sobre un `Decimal128` también.
    """
    async def caso():
        await base.users.insert_one({"user_id": "usr_nuevo", "role": "user"})
        assert saldos.saldo_de(await base.users.find_one({"user_id": "usr_nuevo"})) \
            == Decimal("0.00")
        r = await saldos.mover(base, "usr_nuevo", 75, movimiento="recarga_pix")
        assert r["saldo_anterior"] == Decimal("0.00")
        assert r["saldo_nuevo"] == Decimal("75.00")
        linea, = await _lineas(base, "usr_nuevo")
        assert (linea["balance_before"], linea["balance_after"]) == (0.0, 75.0)
    corre(caso())


def test_saldo_de_sobre_None_no_revienta():
    """`mover` lo usa sobre el documento que devuelve la relectura, que puede
    no existir. Devolver 0 es lo correcto; reventar acá taparía el error real."""
    assert saldos.saldo_de(None) == Decimal("0.00")
    assert saldos.saldo_de({}, "balance_ris_terceros") == Decimal("0.00")


def test_el_saldo_se_guarda_en_Decimal128_venga_de_donde_venga(base):
    """Un saldo que nació en float queda migrado después del primer movimiento."""
    async def caso():
        await _usuario(base, 1000.0)
        await saldos.mover(base, "usr_ana", 1, movimiento="recarga_pix")
        assert isinstance(await _saldo_crudo(base), Decimal128)
    corre(caso())


def test_sumar_centavos_no_deriva(base):
    """Cien movimientos de 0.01 dan 1.00 exacto, no 0.9999999999999."""
    async def caso():
        await _usuario(base, Decimal128(Decimal("0.00")))
        for _ in range(100):
            await saldos.mover(base, "usr_ana", 0.01, movimiento="recarga_pix")
        assert saldos.saldo_de(await base.users.find_one({"user_id": "usr_ana"})) \
            == Decimal("1.00")
    corre(caso())


def test_en_produccion_restarle_un_float_a_un_Decimal128_REVIENTA():
    """La razón de existir del módulo, demostrada en un intérprete limpio.

    No se puede comprobar en este proceso: `conftest` le enseña aritmética a
    `Decimal128` para que mongomock pueda hacer `$inc`, y ese mismo parche tapa
    justamente el error que hay que demostrar. Así que se levanta un Python sin
    parchar y se reproduce la expresión EXACTA que había en el producto.

    Si algún día `bson` le da aritmética con floats a `Decimal128`, este test
    falla y avisa de que el módulo puede simplificarse.
    """
    guion = textwrap.dedent("""
        from decimal import Decimal
        from bson.decimal128 import Decimal128

        # Lo que hacía routes/gestor_pix.py, FUERA de todo try:
        #     balance_after = (updated or {}).get("balance_ris")
        #     balance_before = balance_after - amount_ris
        balance_after = Decimal128(Decimal("1250.50"))
        amount_ris = 250.50
        try:
            balance_after - amount_ris
        except TypeError:
            print("REVIENTA")
        else:
            raise SystemExit("ya no revienta: revisar si services/saldos.py sigue haciendo falta")
    """)
    proceso = subprocess.run([sys.executable, "-c", guion],
                             capture_output=True, text=True)
    assert proceso.returncode == 0, proceso.stderr
    assert "REVIENTA" in proceso.stdout


# ══════════════════════════════════════════════════════════════════════════
# 2. El saldo posterior sale de la ESCRITURA, no de una lectura vieja
# ══════════════════════════════════════════════════════════════════════════

def test_el_saldo_posterior_sale_de_la_escritura(base):
    """Dos movimientos seguidos encadenan: el anterior del 2º es el nuevo del 1º.

    Con el patrón viejo —leer, escribir, y anotar lectura+monto— dos operaciones
    sobre el mismo usuario anotaban las dos el mismo saldo posterior, y ninguno
    de los dos era el real.
    """
    async def caso():
        await _usuario(base, Decimal128(Decimal("500.00")))
        a = await saldos.mover(base, "usr_ana", 100, movimiento="recarga_pix")
        b = await saldos.mover(base, "usr_ana", 100, movimiento="recarga_pix")
        assert a["saldo_nuevo"] == Decimal("600.00")
        assert b["saldo_anterior"] == a["saldo_nuevo"]
        assert b["saldo_nuevo"] == Decimal("700.00")
        primera, segunda = await _lineas(base)
        assert (primera["balance_after"], segunda["balance_before"]) == (600.0, 600.0)
        assert segunda["balance_after"] == 700.0
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. El guard de saldo va DENTRO del filtro de la escritura
# ══════════════════════════════════════════════════════════════════════════

def test_sin_saldo_no_escribe_nada(base):
    async def caso():
        await _usuario(base, Decimal128(Decimal("100.00")))
        with pytest.raises(saldos.SaldoInsuficiente) as e:
            await saldos.mover(base, "usr_ana", -500, movimiento="envio_ves",
                               exigir_saldo=True)
        assert e.value.pedido == Decimal("500.00")
        assert e.value.disponible == Decimal("100.00")
        # Ni el saldo ni el libro se tocaron.
        assert saldos.saldo_de(await base.users.find_one({"user_id": "usr_ana"})) \
            == Decimal("100.00")
        assert await _lineas(base) == []
    corre(caso())


def test_con_el_saldo_justo_el_debito_pasa(base):
    async def caso():
        await _usuario(base, Decimal128(Decimal("100.00")))
        r = await saldos.mover(base, "usr_ana", -100, movimiento="envio_ves",
                               exigir_saldo=True)
        assert r["saldo_nuevo"] == Decimal("0.00")
    corre(caso())


def test_sin_exigir_saldo_el_saldo_puede_quedar_negativo(base):
    """La devolución de un envío rechazado no puede fallar por falta de saldo."""
    async def caso():
        await _usuario(base, Decimal128(Decimal("10.00")))
        r = await saldos.mover(base, "usr_ana", -50, movimiento="envio_ves")
        assert r["saldo_nuevo"] == Decimal("-40.00")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. Los errores se distinguen: buscar donde no es cuesta tiempo de operador
# ══════════════════════════════════════════════════════════════════════════

def test_usuario_que_no_existe(base):
    async def caso():
        with pytest.raises(saldos.UsuarioInexistente):
            await saldos.mover(base, "usr_fantasma", 100, movimiento="recarga_pix")
    corre(caso())


def test_no_confunde_usuario_inexistente_con_saldo_insuficiente(base):
    """Con `exigir_saldo`, un usuario que no existe NO puede reportarse como
    falta de saldo: mandaría al operador a reponer plata que no arregla nada."""
    async def caso():
        with pytest.raises(saldos.UsuarioInexistente):
            await saldos.mover(base, "usr_fantasma", -100, movimiento="envio_ves",
                               exigir_saldo=True)
    corre(caso())


def test_no_se_puede_mover_una_cuenta_que_este_modulo_no_administra(base):
    """Las billeteras cripto tienen su propio libro; este módulo no las toca."""
    async def caso():
        await _usuario(base, 100.0, campo="balance_usdt")
        with pytest.raises(saldos.CuentaDesconocida):
            await saldos.mover(base, "usr_ana", 10, movimiento="deposito_cripto",
                               cuenta="balance_usdt")
    corre(caso())


def test_mover_cero_no_escribe_ni_saldo_ni_linea(base):
    async def caso():
        await _usuario(base, Decimal128(Decimal("100.00")))
        r = await saldos.mover(base, "usr_ana", 0, movimiento="ajuste_admin")
        assert r["saldo_nuevo"] == Decimal("100.00")
        assert r["entry_id"] is None
        assert await _lineas(base) == []
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. La cuenta de terceros es otra cuenta, y el libro lo dice
# ══════════════════════════════════════════════════════════════════════════

def test_la_cuenta_de_terceros_no_toca_el_saldo_principal(base):
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_gestor", "role": "socio_gestor",
            "balance_ris": Decimal128(Decimal("50.00")),
            "balance_ris_terceros": Decimal128(Decimal("800.00"))})
        r = await saldos.mover(base, "usr_gestor", -300, movimiento="envio_ves",
                               cuenta="balance_ris_terceros", exigir_saldo=True)
        assert r["saldo_nuevo"] == Decimal("500.00")
        doc = await base.users.find_one({"user_id": "usr_gestor"})
        assert saldos.saldo_de(doc, "balance_ris") == Decimal("50.00")
        linea, = await _lineas(base, "usr_gestor")
        assert linea["account"] == "balance_ris_terceros"
        assert linea["direction"] == "debit"
        assert linea["amount"] == 300.0
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 6. El cupo sin KYC viaja en la MISMA escritura que el saldo
# ══════════════════════════════════════════════════════════════════════════

def test_el_cupo_se_consume_en_la_misma_escritura_que_el_saldo(base):
    async def caso():
        await _usuario(base, Decimal128(Decimal("0.00")))
        await saldos.mover(base, "usr_ana", 120, movimiento="recarga_pix",
                           consumir_cupo=True)
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert doc["kyc_quota"]["ops"] == 1
        assert doc["kyc_quota"]["ris"] == 120.0
        assert saldos.saldo_de(doc) == Decimal("120.00")
    corre(caso())


def test_sin_consumir_cupo_el_contador_no_se_toca(base):
    async def caso():
        await _usuario(base, Decimal128(Decimal("0.00")))
        await saldos.mover(base, "usr_ana", 120, movimiento="recarga_pix")
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert "kyc_quota" not in doc
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 7. El contexto del negocio llega entero al libro
# ══════════════════════════════════════════════════════════════════════════

def test_el_contexto_viaja_tal_cual_al_libro(base):
    async def caso():
        await _usuario(base, Decimal128(Decimal("0.00")))
        await saldos.mover(
            base, "usr_ana", 500, movimiento="recarga_ves",
            reference_kind="transaction", reference_id="tx_abc",
            transaction_id="tx_abc", display_id="R-0007",
            actor_type="admin", actor_id="usr_super", actor_email="super@x.com",
            rate=92.0, rate_kind="ves_to_ris",
            amount_output=46000.0, currency_output="VES",
            counterparty={"full_name": "Beneficiario"},
            metadata={"destination_bank_id": "bnk_1"},
            notes="Recarga VES aprobada")
        linea, = await _lineas(base)
        assert linea["reference"] == {"kind": "transaction", "id": "tx_abc"}
        assert linea["transaction_id"] == "tx_abc"
        assert linea["display_id"] == "R-0007"
        assert linea["rate"] == 92.0
        assert linea["amount_output"] == 46000.0
        assert linea["currency_output"] == "VES"
        assert linea["metadata"] == {"destination_bank_id": "bnk_1"}
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 8. Si el libro falla, la plata NO se deshace — pero se grita
# ══════════════════════════════════════════════════════════════════════════

def test_si_el_asiento_falla_el_saldo_igual_se_mueve_y_queda_en_el_log(base, monkeypatch, caplog):
    """Deshacer un movimiento que ya ocurrió sería peor que quedarse sin línea.

    Pero una línea que falta y nadie nombra es exactamente el agujero que este
    módulo vino a tapar: tiene que quedar en el log, a nivel ERROR y con todo lo
    necesario para reponerla a mano.
    """
    async def _falla(**kw):
        return None            # es lo que devuelve `record_ris_entry` si no pudo
    monkeypatch.setattr(saldos, "record_ris_entry", _falla)

    async def caso():
        await _usuario(base, Decimal128(Decimal("100.00")))
        with caplog.at_level("ERROR"):
            r = await saldos.mover(base, "usr_ana", 50, movimiento="recarga_pix")
        assert r["saldo_nuevo"] == Decimal("150.00")
        assert r["entry_id"] is None
        assert saldos.saldo_de(await base.users.find_one({"user_id": "usr_ana"})) \
            == Decimal("150.00")
        texto = caplog.text
        assert "LIBRO SIN LINEA" in texto
        for dato in ("usr_ana", "balance_ris", "recarga_pix", "50", "100.00", "150.00"):
            assert dato in texto, f"falta {dato!r} en el log: no se puede reponer la línea"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 9. Las guardas de arquitectura: que el agujero no se vuelva a abrir
# ══════════════════════════════════════════════════════════════════════════
#
# Estas dos miran el ARBOL de sintaxis del backend, no el texto. Es deliberado:
# los docstrings de este proyecto citan código de ejemplo —`kyc_quota.consume_inc`
# documenta literalmente `{"$inc": {"balance_ris": monto, ...}}`— y un grep lo
# contaría como un movimiento de plata. Sobre el AST, una cadena es una cadena.

import ast                                                          # noqa: E402
from pathlib import Path                                            # noqa: E402

_RAIZ = Path(_BACKEND)
_FUENTES = sorted(
    p for p in (list(_RAIZ.glob("routes/*.py"))
                + list(_RAIZ.glob("services/*.py"))
                + [_RAIZ / "admin_routes.py"])
    if p.is_file())

_CUENTAS_RIS = {"balance_ris", "balance_ris_terceros"}
# Lo que cuenta como «acá se asienta la línea».
_ASIENTA = {"record_ris_entry", "mover", "_asentar", "record_crypto_entry"}


def _funcion_que_contiene(arbol, linea):
    elegida = None
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fin = max(getattr(x, "lineno", nodo.lineno) for x in ast.walk(nodo))
            if nodo.lineno <= linea <= fin and (
                    elegida is None or nodo.lineno > elegida.lineno):
                elegida = nodo
    return elegida


def _mueve_saldo_ris(nodo):
    """¿Este `$inc` toca una cuenta de saldo RIS? Se mira el dict, no el texto."""
    if not isinstance(nodo, ast.Dict):
        return False
    for clave, valor in zip(nodo.keys, nodo.values):
        if not (isinstance(clave, ast.Constant) and clave.value == "$inc"):
            continue
        if not isinstance(valor, ast.Dict):
            continue
        for campo in valor.keys:
            if isinstance(campo, ast.Constant) and campo.value in _CUENTAS_RIS:
                return True
    return False


def _nombre_llamado(nodo):
    fn = nodo.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return ""


def test_todo_movimiento_de_saldo_RIS_deja_linea_en_el_libro():
    """LA GUARDA CENTRAL de este PR.

    Para cada `$inc` sobre `balance_ris` o `balance_ris_terceros` en el backend,
    la función que lo contiene tiene que asentar la línea. Seis caminos no lo
    hacían: el webhook de tarjeta, el envío de un gestor, la aprobación de
    recarga y el ajuste manual del panel viejo, y la devolución del puente.

    Si alguien agrega un `$inc` nuevo y se olvida del libro, este test lo grita
    con el archivo y la línea.
    """
    huerfanos = []
    for ruta in _FUENTES:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not _mueve_saldo_ris(nodo):
                continue
            fn = _funcion_que_contiene(arbol, nodo.lineno)
            if fn is None:
                huerfanos.append(f"{ruta.name}:{nodo.lineno} (fuera de función)")
                continue
            llamadas = {_nombre_llamado(c) for c in ast.walk(fn)
                        if isinstance(c, ast.Call)}
            if not (llamadas & _ASIENTA):
                huerfanos.append(f"{ruta.relative_to(_RAIZ)}:{nodo.lineno} "
                                 f"en {fn.name}()")

    assert huerfanos == [], (
        "hay movimientos de saldo RIS que no dejan línea en el libro:\n  "
        + "\n  ".join(huerfanos)
        + "\n\nUsá services/saldos.mover(), que mueve y asienta en la misma "
          "operación.")


def test_todo_movimiento_que_se_usa_esta_en_el_plan_contable():
    """Un `movement_type` que el plan no conoce va a la cuenta puente.

    No desaparece —eso sería peor— pero el chequeo de integridad lo denuncia y
    el balance queda con un renglón «sin clasificar». Los tipos que este PR
    introduce (`recarga_brl`, `ajuste_admin`) tienen que estar en el mapa.
    """
    from services.contabilidad import ASIENTOS

    usados = {}
    for ruta in _FUENTES:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Call)
                    and _nombre_llamado(nodo) in ("mover", "transferir")):
                continue
            for kw in nodo.keywords:
                if kw.arg == "movimiento" and isinstance(kw.value, ast.Constant):
                    usados.setdefault(kw.value.value, []).append(
                        f"{ruta.relative_to(_RAIZ)}:{nodo.lineno}")

    assert usados, "el escáner no encontró ninguna llamada a saldos.mover()"
    # Y que de verdad esté mirando las dos operaciones, no sólo una: el
    # traspaso del gestor usa el valor por defecto, así que se comprueba aparte.
    from services.saldos import transferir
    import inspect
    por_defecto = inspect.signature(transferir).parameters["movimiento"].default
    assert por_defecto in ASIENTOS, (
        f"el movimiento por defecto del traspaso ({por_defecto!r}) no está en "
        "ASIENTOS")
    faltantes = {t: d for t, d in usados.items() if t not in ASIENTOS}
    assert faltantes == {}, (
        "estos movement_type se usan y no están en ASIENTOS de "
        f"services/contabilidad.py: {faltantes}")


def test_la_cuenta_del_usuario_esta_declarada_para_las_dos_cuentas():
    """Sin esto, una línea de terceros se contabilizaría contra 2.1.01."""
    from services.contabilidad import CUENTA_DEL_USUARIO
    for cuenta in saldos.CUENTAS:
        assert cuenta in CUENTA_DEL_USUARIO, (
            f"{cuenta} no tiene cuenta contable declarada")
    assert CUENTA_DEL_USUARIO["balance_ris"] != CUENTA_DEL_USUARIO["balance_ris_terceros"]


# ══════════════════════════════════════════════════════════════════════════
# 10. El traspaso entre las dos cuentas del gestor
# ══════════════════════════════════════════════════════════════════════════

async def _gestor(base, personal, terceros):
    await base.users.insert_one({
        "user_id": "usr_gestor", "email": "g@example.com", "name": "Gestor",
        "role": "socio_gestor",
        "balance_ris": personal, "balance_ris_terceros": terceros})


@pytest.mark.parametrize("como", [
    pytest.param(float, id="float"),
    pytest.param(lambda x: Decimal128(Decimal(str(x))), id="Decimal128"),
])
def test_el_traspaso_mueve_las_dos_cuentas(base, como):
    async def caso():
        await _gestor(base, como(1000), como(200))
        r = await saldos.transferir(base, "usr_gestor", 300,
                                    de="balance_ris", a="balance_ris_terceros")
        assert r["saldo_origen"] == Decimal("700.00")
        assert r["saldo_destino"] == Decimal("500.00")
        doc = await base.users.find_one({"user_id": "usr_gestor"})
        assert saldos.saldo_de(doc, "balance_ris") == Decimal("700.00")
        assert saldos.saldo_de(doc, "balance_ris_terceros") == Decimal("500.00")
    corre(caso())


def test_el_traspaso_deja_las_dos_patas_en_el_libro(base):
    async def caso():
        await _gestor(base, Decimal128(Decimal("1000.00")), Decimal128(Decimal("200.00")))
        await saldos.transferir(base, "usr_gestor", 300,
                                de="balance_ris", a="balance_ris_terceros")
        lineas = await _lineas(base, "usr_gestor")
        assert len(lineas) == 2
        salida = next(x for x in lineas if x["account"] == "balance_ris")
        entrada = next(x for x in lineas if x["account"] == "balance_ris_terceros")
        assert (salida["direction"], salida["amount"]) == ("debit", 300.0)
        assert (salida["balance_before"], salida["balance_after"]) == (1000.0, 700.0)
        assert (entrada["direction"], entrada["amount"]) == ("credit", 300.0)
        assert (entrada["balance_before"], entrada["balance_after"]) == (200.0, 500.0)
        assert {x["movement_type"] for x in lineas} == {"traspaso_interno"}
    corre(caso())


def test_las_dos_patas_del_traspaso_se_anulan_en_la_contabilidad(base):
    """No entra ni sale plata de la empresa: la cuenta de traspasos queda en 0.

    Si las dos patas no se anularan, cada traspaso de un gestor inflaría una
    cuenta del balance y el estado dejaría de cuadrar solo.
    """
    from services.contabilidad import asiento_de, PLAN_DE_CUENTAS

    async def caso():
        await _gestor(base, Decimal128(Decimal("1000.00")), Decimal128(Decimal("0.00")))
        await saldos.transferir(base, "usr_gestor", 300,
                                de="balance_ris", a="balance_ris_terceros")
        saldo_por_cuenta = {}
        for linea in await _lineas(base, "usr_gestor"):
            a = asiento_de(linea)
            assert a["clasificado"], f"traspaso_interno no está en el plan: {a}"
            saldo_por_cuenta[a["debe"]] = saldo_por_cuenta.get(a["debe"], 0) + a["monto"]
            saldo_por_cuenta[a["haber"]] = saldo_por_cuenta.get(a["haber"], 0) - a["monto"]

        # La cuenta tiene que APARECER —las dos patas pasaron por ella— y quedar
        # en cero. Con `.get(..., 0)` esto pasaba aunque el traspaso se hubiera
        # contabilizado contra otra cuenta cualquiera.
        assert "2.1.99" in saldo_por_cuenta, (
            "las patas del traspaso no pasaron por la cuenta de traspasos "
            f"internos: {saldo_por_cuenta}")
        assert saldo_por_cuenta["2.1.99"] == 0, (
            f"la cuenta de traspasos internos no quedó en cero: {saldo_por_cuenta}")
        # Y el traspaso movió lo que tenía que mover, entre las dos del usuario.
        assert saldo_por_cuenta["2.1.01"] == 300      # el pasivo personal baja
        assert saldo_por_cuenta["2.1.02"] == -300     # el de terceros sube
        assert PLAN_DE_CUENTAS["2.1.99"]["tipo"] == "pasivo", (
            "la contrapartida del traspaso tiene que ser un pasivo: contra una "
            "cuenta de activo, cada traspaso de un gestor inflaría el activo de "
            "la empresa sin que haya entrado un peso")
        # Ningún banco ni ninguna caja se movió: acá no entró ni salió plata.
        assert not [c for c in saldo_por_cuenta if c.startswith("1.")], (
            f"un traspaso interno tocó una cuenta de activo: {saldo_por_cuenta}")
    corre(caso())


def test_el_traspaso_sin_saldo_no_escribe_nada(base):
    """La comprobación va dentro del filtro: no hay ventana entre mirar y mover."""
    async def caso():
        await _gestor(base, Decimal128(Decimal("100.00")), Decimal128(Decimal("0.00")))
        with pytest.raises(saldos.SaldoInsuficiente) as e:
            await saldos.transferir(base, "usr_gestor", 300,
                                    de="balance_ris", a="balance_ris_terceros")
        assert e.value.disponible == Decimal("100.00")
        doc = await base.users.find_one({"user_id": "usr_gestor"})
        assert saldos.saldo_de(doc, "balance_ris") == Decimal("100.00")
        assert saldos.saldo_de(doc, "balance_ris_terceros") == Decimal("0.00")
        assert await _lineas(base, "usr_gestor") == []
    corre(caso())


def test_el_traspaso_con_el_saldo_justo_pasa(base):
    async def caso():
        await _gestor(base, Decimal128(Decimal("300.00")), Decimal128(Decimal("0.00")))
        r = await saldos.transferir(base, "usr_gestor", 300,
                                    de="balance_ris", a="balance_ris_terceros")
        assert (r["saldo_origen"], r["saldo_destino"]) == (Decimal("0.00"), Decimal("300.00"))
    corre(caso())


@pytest.mark.parametrize("monto", [0, -50])
def test_el_traspaso_exige_un_monto_positivo(base, monto):
    async def caso():
        await _gestor(base, Decimal128(Decimal("100.00")), Decimal128(Decimal("0.00")))
        with pytest.raises(ValueError):
            await saldos.transferir(base, "usr_gestor", monto,
                                    de="balance_ris", a="balance_ris_terceros")
    corre(caso())


def test_el_traspaso_a_la_misma_cuenta_es_un_error(base):
    async def caso():
        await _gestor(base, Decimal128(Decimal("100.00")), Decimal128(Decimal("0.00")))
        with pytest.raises(ValueError):
            await saldos.transferir(base, "usr_gestor", 10,
                                    de="balance_ris", a="balance_ris")
    corre(caso())


def test_el_traspaso_no_alcanza_a_las_billeteras_cripto(base):
    async def caso():
        await _gestor(base, Decimal128(Decimal("100.00")), Decimal128(Decimal("0.00")))
        with pytest.raises(saldos.CuentaDesconocida):
            await saldos.transferir(base, "usr_gestor", 10,
                                    de="balance_ris", a="balance_usdt")
    corre(caso())
