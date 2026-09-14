"""
tests/test_cpf_de_la_cuenta.py — Que quien paga sea el titular de la cuenta.

LO QUE SE VIGILA, POR ORDEN DE DAÑO

    1. Que una cuenta no pueda pagar con el CPF de otra persona. Es la atadura
       entera: sin ella, cualquiera recarga la cuenta de cualquiera y la
       plataforma no puede decir de quién vino cada real.
    2. Que el CPF no se pueda cambiar solo una vez atado. Si el cliente pudiera
       cambiarlo, el que quiere pagar con el de otro simplemente lo cambiaría
       antes, y la atadura no ataría nada.
    3. Que un CPF sea de una sola cuenta. Con un cupo de 200 R$ por cuenta sin
       verificar, sin esto la misma persona abre cuentas en serie.
    4. Que la cuenta sin CPF —las creadas antes de que el registro lo pidiera—
       pueda atarlo en su primera recarga. Sin esto el cambio las rompe a
       todas, que es peor que el problema que vino a resolver.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                              # noqa: E402
from services import cpf_de_la_cuenta as cdc                # noqa: E402

UNO = "52998224725"
OTRO = "11144477735"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_cpf"]
    usar_base(b)
    return b


def _correr(corrutina):
    return asyncio.run(corrutina)


async def _usuario(base, user_id="u1", cpf=None):
    doc = {"user_id": user_id, "email": f"{user_id}@ejemplo.com"}
    if cpf:
        doc["cpf_number"] = cpf
    await base.users.insert_one(doc)
    return doc


# ══════════════════════════════════════════════════════════════════════════
# 1. Pagar con el CPF de otro
# ══════════════════════════════════════════════════════════════════════════

def test_NO_SE_PUEDE_PAGAR_CON_EL_CPF_DE_OTRO(base):
    """Es la atadura entera. Sin esto, cualquiera recarga la cuenta de cualquiera."""
    async def caso():
        u = await _usuario(base, cpf=UNO)
        with pytest.raises(cdc.CpfDeOtro):
            await cdc.exigir_para_pagar(base, u, OTRO)
    _correr(caso())


def test_CON_EL_CPF_DE_LA_CUENTA_SE_PAGA(base):
    async def caso():
        u = await _usuario(base, cpf=UNO)
        assert await cdc.exigir_para_pagar(base, u, UNO) == UNO
    _correr(caso())


def test_LOS_PUNTOS_Y_EL_GUION_NO_IMPIDEN_PAGAR(base):
    """La pantalla manda «529.982.247-25» y la base guarda «52998224725»."""
    async def caso():
        u = await _usuario(base, cpf=UNO)
        assert await cdc.exigir_para_pagar(base, u, "529.982.247-25") == UNO
    _correr(caso())


def test_UN_CPF_INVENTADO_NO_SIRVE_PARA_PAGAR(base):
    """Once dígitos no son un CPF. Antes esto entraba."""
    async def caso():
        u = await _usuario(base)
        with pytest.raises(cdc.CpfInvalido):
            await cdc.exigir_para_pagar(base, u, "12345678900")
    _correr(caso())


def test_EL_CPF_DE_RELLENO_DEL_CODIGO_VIEJO_NO_PASA(base):
    """«00000000000» era el valor por omisión que se le mandaba a Mercado Pago."""
    async def caso():
        u = await _usuario(base)
        with pytest.raises(cdc.CpfInvalido):
            await cdc.exigir_para_pagar(base, u, "00000000000")
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Atado una vez, no se cambia solo
# ══════════════════════════════════════════════════════════════════════════

def test_LA_CUENTA_SIN_CPF_LO_ATA_EN_SU_PRIMERA_RECARGA(base):
    """Son todas las cuentas creadas antes de que el registro lo pidiera."""
    async def caso():
        u = await _usuario(base)
        assert await cdc.exigir_para_pagar(base, u, UNO) == UNO

        guardado = await base.users.find_one({"user_id": "u1"})
        assert guardado["cpf_number"] == UNO
        assert guardado.get("cpf_declarado_en") is not None
    _correr(caso())


def test_UNA_VEZ_ATADO_YA_NO_SE_CAMBIA(base):
    """Si el cliente pudiera cambiarlo, la atadura no ataría nada."""
    async def caso():
        u = await _usuario(base)
        await cdc.atar(base, "u1", UNO)
        with pytest.raises(cdc.CpfDeOtro):
            await cdc.atar(base, "u1", OTRO)
        guardado = await base.users.find_one({"user_id": "u1"})
        assert guardado["cpf_number"] == UNO, "se lo dejó cambiar"
    _correr(caso())


def test_ATAR_EL_MISMO_DOS_VECES_NO_MOLESTA(base):
    """Reintentar una recarga no puede convertirse en un error."""
    async def caso():
        await _usuario(base)
        assert await cdc.atar(base, "u1", UNO) == UNO
        assert await cdc.atar(base, "u1", "529.982.247-25") == UNO
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. Un CPF, una cuenta
# ══════════════════════════════════════════════════════════════════════════

def test_UN_CPF_NO_PUEDE_ABRIR_DOS_CUENTAS(base):
    """Con un cupo de 200 R$ por cuenta, sin esto se abren cuentas en serie."""
    async def caso():
        await _usuario(base, "u1", cpf=UNO)
        with pytest.raises(cdc.CpfEnUso):
            await cdc.revisar_para_registrar(base, UNO)
    _correr(caso())


def test_TAMPOCO_SE_PUEDE_ATAR_EL_CPF_DE_OTRA_CUENTA(base):
    """La otra puerta: una cuenta vieja atando el CPF que ya usa otra."""
    async def caso():
        await _usuario(base, "u1", cpf=UNO)
        await _usuario(base, "u2")
        with pytest.raises(cdc.CpfEnUso):
            await cdc.atar(base, "u2", UNO)
    _correr(caso())


def test_UN_CPF_LIBRE_SI_PUEDE_REGISTRARSE(base):
    async def caso():
        await _usuario(base, "u1", cpf=UNO)
        assert await cdc.revisar_para_registrar(base, OTRO) == OTRO
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. La lista negra
# ══════════════════════════════════════════════════════════════════════════

def test_UN_CPF_VETADO_NO_ABRE_CUENTA(base):
    async def caso():
        await base.blacklist.insert_one({"type": "cpf", "value": UNO})
        with pytest.raises(cdc.CpfVetado):
            await cdc.revisar_para_registrar(base, UNO)
    _correr(caso())


def test_EL_VETO_SE_ENCUENTRA_AUNQUE_SE_ESCRIBA_CON_PUNTOS(base):
    """La lista guarda dígitos pelados. Si las dos normalizaciones se separan,
    el veto deja de encontrarse y nadie se entera."""
    async def caso():
        await base.blacklist.insert_one({"type": "cpf", "value": UNO})
        with pytest.raises(cdc.CpfVetado):
            await cdc.revisar_para_registrar(base, "529.982.247-25")
    _correr(caso())


def test_EL_MENSAJE_DEL_VETO_NO_DICE_QUE_ESTA_VETADO(base):
    """Si lo dijera, el registro sería una forma de averiguar quién está en la
    lista: se prueba un CPF y el mensaje contesta."""
    async def caso():
        await base.blacklist.insert_one({"type": "cpf", "value": UNO})
        try:
            await cdc.revisar_para_registrar(base, UNO)
        except cdc.CpfVetado as e:
            assert "lista" not in str(e).lower()
            assert "veta" not in str(e).lower()
    _correr(caso())


def test_UN_CPF_VETADO_TAMPOCO_SE_PUEDE_ATAR_DESPUES(base):
    """Vetarlo después de que la cuenta existe tiene que cerrar esta puerta."""
    async def caso():
        await _usuario(base)
        await base.blacklist.insert_one({"type": "cpf", "value": UNO})
        with pytest.raises(cdc.CpfVetado):
            await cdc.atar(base, "u1", UNO)
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. El KYC: no lo vuelve a pedir, pero si discrepa se avisa
# ══════════════════════════════════════════════════════════════════════════

def test_SI_EL_KYC_TRAE_OTRO_CPF_QUEDA_ANOTADO(base):
    """Un CPF declarado sin foto no prueba nada. Que DISCREPE sí dice algo."""
    async def caso():
        await _usuario(base, cpf=UNO)
        salida = await cdc.anotar_si_el_kyc_discrepa(base, "u1", OTRO)
        assert salida["discrepa"]
        assert salida["declarado"] == UNO and salida["en_el_kyc"] == OTRO
    _correr(caso())


def test_SI_EL_KYC_TRAE_EL_MISMO_NO_SE_MARCA_NADA(base):
    """Es el caso normal: no puede ensuciar la ficha de todo el mundo."""
    async def caso():
        await _usuario(base, cpf=UNO)
        assert not (await cdc.anotar_si_el_kyc_discrepa(
            base, "u1", "529.982.247-25"))["discrepa"]
    _correr(caso())


def test_LA_CUENTA_SIN_CPF_DECLARADO_NO_DISCREPA_DE_NADA(base):
    """Las cuentas viejas no declararon ninguno: no hay contra qué comparar,
    y marcarlas a todas sería marcar a nadie."""
    async def caso():
        await _usuario(base)
        assert not (await cdc.anotar_si_el_kyc_discrepa(
            base, "u1", UNO))["discrepa"]
    _correr(caso())
