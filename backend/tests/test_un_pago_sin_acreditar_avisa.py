"""
tests/test_un_pago_sin_acreditar_avisa.py

POR QUE EXISTE ESTE ARCHIVO

    El 20 de septiembre de 2026 un cliente pagó su envío con PIX y la orden se
    quedó en «esperando pago». El historial completo está en
    `docs/incidentes/2026-09-20-un-pix-pagado-que-no-avanzo-el-envio.md`.

    LA CAUSA

        El identificador de Mercado Pago se guardaba como NUMERO —es lo que
        devuelve su SDK— y se buscaba como TEXTO —es lo que manda el cuerpo
        del aviso—. MongoDB no los iguala, así que el receptor no encontraba
        el cobro, contestaba 200 y no tocaba nada.

        No se notaba en las recargas porque su pantalla pregunta sola y las
        rescataba. La del envío no pregunta: ahí el receptor era el único
        camino.

    LO QUE APARECIO BUSCANDOLA, Y ES PEOR

        El receptor tenía SEIS salidas que no acreditaban y no avisaban a
        nadie. Una línea en el registro y un 200. El cliente había pagado y
        nadie se iba a enterar hasta que reclamara.

        El arreglo de la causa evita ESE fallo. Los avisos evitan el silencio,
        que es lo que lo hizo durar.
"""
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                # noqa: E402
from services import pago_que_no_se_acredito as aviso         # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


@pytest.fixture
def avisos(monkeypatch):
    """Espía los avisos al equipo. Se mira lo que SALE, no que el nombre esté
    escrito en el archivo: esa lección la dejó una mutación en
    `test_el_barrido_de_cobros_vencidos`."""
    import services.notifications as notif
    salieron = []

    async def _espia(**kw):
        salieron.append(kw)
        return 1

    monkeypatch.setattr(notif, "avisar_al_personal", _espia)
    return salieron


# ══════════════════════════════════════════════════════════════════════════
# 1. LA CAUSA DEL INCIDENTE
# ══════════════════════════════════════════════════════════════════════════

def _buscar_como_el_receptor(base, mp_payment_id):
    """La MISMA consulta que hace el receptor, con la MISMA función.

    No se reescribe a mano: un test que reimplementa la consulta comprueba que
    la consulta del test funciona, no la del receptor.
    """
    return base.gestor_pix_payments.find_one({
        "mp_payment_id": {
            "$in": aviso.identificadores_posibles(mp_payment_id)}})


def test_EL_NUMERO_GUARDADO_SE_ENCUENTRA_BUSCANDO_EL_TEXTO(base):
    """El test que reproduce el incidente.

    Así lo guarda la cotización —un entero, que es lo que devuelve el SDK— y
    así llega el aviso —una cadena, que es lo que manda el cuerpo—.
    """
    corre(base.gestor_pix_payments.insert_one({
        "payment_id": "venv_abc", "mp_payment_id": 123456789,
        "gestor_id": "u1", "status": "pending"}))

    hallado = corre(_buscar_como_el_receptor(base, "123456789"))
    assert hallado is not None, (
        "el receptor no encuentra un cobro guardado con el identificador "
        "numérico cuando el aviso lo manda como texto: es el incidente del "
        "20 de septiembre, otra vez")
    assert hallado["payment_id"] == "venv_abc"


def test_y_el_texto_guardado_tambien(base):
    """El otro lado: cobros guardados como texto siguen encontrándose. Se
    buscan los dos porque en la base conviven los de antes y los de ahora."""
    corre(base.gestor_pix_payments.insert_one({
        "payment_id": "venv_def", "mp_payment_id": "987654321",
        "gestor_id": "u1", "status": "pending"}))
    hallado = corre(_buscar_como_el_receptor(base, "987654321"))
    assert hallado is not None
    assert hallado["payment_id"] == "venv_def"


@pytest.mark.parametrize("entrada, esperados", [
    ("123", ["123", 123]),
    (123, ["123", 123]),
    ("abc", ["abc"]),          # no es número: sólo la forma de texto
    (None, ["None"]),
])
def test_las_dos_formas_del_identificador(entrada, esperados):
    assert aviso.identificadores_posibles(entrada) == esperados


def test_un_identificador_que_no_es_numero_NO_ROMPE():
    """Si reventara, el receptor devolvería 500 y Mercado Pago reintentaría
    para siempre un aviso que nunca va a servir."""
    assert aviso.identificadores_posibles("no-es-un-numero") == ["no-es-un-numero"]


def test_el_receptor_USA_esa_funcion():
    """Si volviera a buscar por el valor crudo, vuelve el incidente.

    Se busca DENTRO del receptor y no en todo el archivo: la primera consulta
    a esa colección es de otra ruta, y mirando el archivo entero este test
    daba por buena la consulta equivocada.
    """
    cuerpo = _cuerpo_del_receptor()
    i = cuerpo.index("payment = await db.gestor_pix_payments.find_one(")
    consulta = cuerpo[i:cuerpo.index("})", i)]
    assert "identificadores_posibles" in consulta, (
        "el receptor dejó de usar las dos formas del identificador: un cobro "
        "guardado con el número no se va a encontrar con el texto")
    assert '"mp_payment_id": mp_payment_id' not in consulta


# ══════════════════════════════════════════════════════════════════════════
# 2. EL SILENCIO, que es lo que hizo durar el fallo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("motivo", [
    "no_encontrado", "no_esta_pendiente", "mercadopago_no_contesta",
    "monto_distinto", "no_se_pudo_confirmar"])
def test_CADA_MOTIVO_AVISA(base, avisos, motivo):
    assert corre(aviso.avisar(base, motivo=motivo, mp_payment_id=1)) is True
    assert len(avisos) == 1, f"«{motivo}» no le avisó a nadie"


@pytest.mark.parametrize("motivo", list(aviso.MOTIVOS))
def test_cada_motivo_tiene_su_mensaje_EN_CASTELLANO_LLANO(motivo):
    """Quien recibe el aviso puede ser el que atiende el chat, no quien
    escribió el código."""
    texto = aviso.MOTIVOS[motivo]
    assert len(texto) > 40
    for jerga in ("webhook", "payload", "null", "None", "status"):
        assert jerga not in texto, f"«{motivo}» dice «{jerga}»"


def test_el_aviso_dice_QUE_HACER():
    """«Un pago no se acreditó» sin más deja a quien lo lee buscando."""
    assert "mano" in aviso.QUE_HACER.lower()
    assert "Mercado Pago" in aviso.QUE_HACER


def test_EL_AVISO_SALE_UNA_VEZ_POR_PAGO(base, avisos):
    """Mercado Pago reintenta. Diez avisos del mismo problema es un equipo que
    aprende a ignorarlos, que es volver al silencio con más ruido."""
    for _ in range(4):
        corre(aviso.avisar(base, motivo="no_encontrado", mp_payment_id=777))
    assert len(avisos) == 1, f"salieron {len(avisos)} avisos del mismo pago"


def test_pero_DOS_PROBLEMAS_DISTINTOS_avisan_los_dos(base, avisos):
    corre(aviso.avisar(base, motivo="no_encontrado", mp_payment_id=777))
    corre(aviso.avisar(base, motivo="monto_distinto", mp_payment_id=777))
    assert len(avisos) == 2


def test_y_DOS_PAGOS_DISTINTOS_tambien(base, avisos):
    corre(aviso.avisar(base, motivo="no_encontrado", mp_payment_id=111))
    corre(aviso.avisar(base, motivo="no_encontrado", mp_payment_id=222))
    assert len(avisos) == 2


def test_el_reclamo_del_aviso_NO_PISA_el_de_acreditar(base, avisos):
    """Los dos usan `pagos_una_sola_vez`. Sin un prefijo propio, avisar de un
    problema con el pago 123 impediría acreditarlo después — o sea que el
    aviso causaría el fallo del que avisa."""
    from services import pagos_una_sola_vez
    corre(aviso.avisar(base, motivo="no_encontrado", mp_payment_id=555))
    todavia_se_puede = corre(pagos_una_sola_vez.reclamar(
        base, "555", proveedor="mercadopago"))
    assert todavia_se_puede is True, (
        "el aviso se comió el reclamo de acreditar: el pago no se va a poder "
        "acreditar nunca")


def test_SI_EL_AVISO_FALLA_NO_SE_CAE_EL_RECEPTOR(base, monkeypatch):
    """Quien llama está contestándole a Mercado Pago. Una excepción acá
    convierte un problema de UN pago en un reintento eterno de TODOS."""
    import services.notifications as notif

    async def _explota(**kw):
        raise RuntimeError("no hay a quién avisar")

    monkeypatch.setattr(notif, "avisar_al_personal", _explota)
    assert corre(aviso.avisar(base, motivo="no_encontrado",
                              mp_payment_id=1)) is False


def test_el_registro_queda_AUNQUE_no_se_avise(base, caplog, monkeypatch):
    """Es lo que queda para conciliar después."""
    import logging
    import services.notifications as notif

    async def _explota(**kw):
        raise RuntimeError("x")

    monkeypatch.setattr(notif, "avisar_al_personal", _explota)
    with caplog.at_level(logging.ERROR):
        corre(aviso.avisar(base, motivo="no_encontrado", mp_payment_id=42))
    assert any("PAGO SIN ACREDITAR" in r.getMessage() for r in caplog.records), (
        "no quedó nada en el registro: es lo único para conciliar después")
    assert any("42" in r.getMessage() for r in caplog.records), (
        "el registro no dice de qué pago habla")


# ══════════════════════════════════════════════════════════════════════════
# 3. Que el receptor los use de verdad
# ══════════════════════════════════════════════════════════════════════════

def _cuerpo_del_receptor():
    fuente = (_BACKEND / "routes" / "gestor_pix.py").read_text(encoding="utf-8")
    i = fuente.index("async def mercadopago_webhook(")
    c = fuente[i:]
    return c[:c.find("\n@")] if "\n@" in c else c


def test_LAS_SEIS_SALIDAS_AVISAN():
    """Las seis que devolvían 200 sin acreditar nada."""
    cuerpo = _cuerpo_del_receptor()
    assert cuerpo.count("await _sin_acreditar(") == 6, (
        f"hay {cuerpo.count('await _sin_acreditar(')} avisos y son seis "
        f"salidas: alguna volvió a quedarse callada")


def test_UN_AVISO_REPETIDO_NORMAL_NO_MOLESTA_A_NADIE():
    """Un cobro ya pagado que recibe su segundo aviso no es un problema. Si
    avisara, el equipo recibiría un aviso por cada reintento de cada pago que
    salió bien."""
    cuerpo = _cuerpo_del_receptor()
    assert 'if _estado not in ("paid", "approved", "completed"):' in cuerpo, (
        "se avisa de los avisos repetidos normales: eso es ruido, y el ruido "
        "es como se vuelve al silencio")


def test_el_receptor_sigue_contestando_200():
    """Si devolviera error, Mercado Pago reintentaría durante horas y después
    se rendiría igual, sin que nadie hubiera mirado nada. Lo que faltaba no
    era fallar más fuerte: era avisar."""
    cuerpo = _cuerpo_del_receptor()
    for salida in ("payment_not_found", "mp_service_unavailable",
                   "verification_failed", "amount_mismatch",
                   "processing_failed"):
        devuelve = [l for l in cuerpo.splitlines()
                    if salida in l and l.strip().startswith("return")]
        assert devuelve, f"«{salida}» ya no se devuelve"
        assert all('"received": True' in l for l in devuelve), (
            f"«{salida}» dejó de contestarle 200 a Mercado Pago: va a "
            f"reintentar durante horas y después rendirse igual")
