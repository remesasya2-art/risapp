"""
tests/test_la_tasa_vieja_no_le_gana_al_panel.py — Que un número congelado deje
de hacerse pasar por la tasa de hoy.

QUE PASABA, Y POR QUE NO SE VEIA

    El motor contable leía el dólar del BCV así:

        bcv = (bcv_doc or {}).get("rates", {}).get("dolar") or rates.get("usd_to_ves")

    O sea: el último número que trajo el raspador le GANA al que el operador
    carga a mano en el panel. Y sin mirar de cuándo es.

    El raspador estuvo roto semanas —el sitio del BCV manda la cadena de
    certificados incompleta y la conexión se rechazaba— así que la contabilidad
    quedó calculando con un número viejo, congelado. Y como ese número le ganaba
    al del panel, cambiar la tasa a mano NO CAMBIABA NADA. Un fallo sin ningún
    síntoma visible: los informes salían, los asientos se hacían, y todos los
    bolívares se pasaban a dólares a una tasa que ya no era.

LAS DOS MITADES QUE SE PRUEBAN ACA

    · Que una tasa VIGENTE siga ganando (si no, se habría resuelto ignorando
      siempre al raspador, que es el defecto opuesto).
    · Que una tasa VENCIDA pierda — y que un raspado SIN FECHA cuente como
      vencido, porque lo que no se puede afirmar vigente no puede ganarle a lo
      que una persona cargó a mano.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                   # noqa: E402

from services import accounting_engine as ae                     # noqa: E402
from services import aviso_de_bcv                                # noqa: E402
from services import bcv_scraper                                 # noqa: E402
from services import configuracion                              # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def _hace(horas):
    return datetime.now(timezone.utc) - timedelta(hours=horas)


async def _sembrar(base, *, panel=None, raspado=None, hace_horas=None,
                   con_fecha=True):
    """Deja la base como estaría en producción.

    `panel` es `rates.usd_to_ves`, el número que el operador carga a mano.
    `raspado` es `bcv_rates.rates.dolar`, el que trae el raspador.
    """
    tasas = {"ris_to_ves": 110, "ves_to_ris_rate": 140, "brl_to_usd": 5.0}
    if panel is not None:
        tasas["usd_to_ves"] = panel
    await base.rates.insert_one(tasas)
    if raspado is not None:
        doc = {"rates": {"dolar": raspado}, "value_date": "01/01/2026"}
        if con_fecha:
            doc["fetched_at"] = _hace(hace_horas if hace_horas is not None else 1)
        await base.bcv_rates.insert_one(doc)


# ══════════════════════════════════════════════════════════════════════════
# 1. Quién le gana a quién en el motor contable
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_TASA_VIGENTE_LE_GANA_A_LA_DEL_PANEL(base):
    """La otra mitad, y va primero a propósito.

    Si esto no pasara, el arreglo sería «ignorar siempre al raspador», que es el
    defecto opuesto: el dato oficial del Banco Central dejaría de usarse.
    """
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=2))
    tasas = corre(ae._get_active_rates())
    assert tasas["bcv_ves_usd"] == 50


def test_UNA_TASA_VENCIDA_PIERDE_CONTRA_LA_DEL_PANEL(base):
    """LA GUARDA PRINCIPAL.

    Raspado de hace tres días, límite de veinticuatro horas: gana el panel.
    """
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=72))
    tasas = corre(ae._get_active_rates())
    assert tasas["bcv_ves_usd"] == 40, (
        "la tasa vieja le volvió a ganar a la que el operador carga a mano: "
        "cambiar la tasa en el panel no cambia la contabilidad")


def test_UN_RASPADO_SIN_FECHA_CUENTA_COMO_VENCIDO(base):
    """Lo que no se puede afirmar vigente no gana.

    Un documento sin `fetched_at` podría ser de hoy o del año pasado. Tratarlo
    como fresco sería creerle a lo que no se sabe.
    """
    corre(_sembrar(base, panel=40, raspado=50, con_fecha=False))
    tasas = corre(ae._get_active_rates())
    assert tasas["bcv_ves_usd"] == 40


def test_sin_nada_en_el_panel_la_vieja_se_usa_igual(base):
    """Vencida pasa a ser el ULTIMO recurso, no deja de existir.

    Cortar acá tampoco sirve: si el panel no tiene nada cargado, un número viejo
    es mejor que un informe que no se puede generar.
    """
    corre(_sembrar(base, panel=None, raspado=50, hace_horas=200))
    tasas = corre(ae._get_active_rates())
    assert tasas["bcv_ves_usd"] == 50


def test_sin_ninguna_de_las_dos_el_motor_corta(base):
    corre(_sembrar(base, panel=None, raspado=None))
    with pytest.raises(ae.TasaSinConfigurar) as e:
        corre(ae._get_active_rates())
    assert "bcv" in e.value.clave.lower()


def test_una_tasa_ilegible_pasa_a_la_siguiente(base):
    """Antes esto tiraba un `ValueError` pelado, que nadie podía traducir a
    «andá a configurar tal cosa»."""
    corre(_sembrar(base, panel=45, raspado="cincuenta", hace_horas=1))
    tasas = corre(ae._get_active_rates())
    assert tasas["bcv_ves_usd"] == 45


def test_si_las_dos_son_ilegibles_el_motor_corta(base):
    corre(_sembrar(base, panel="cuarenta", raspado="cincuenta", hace_horas=1))
    with pytest.raises(ae.TasaSinConfigurar):
        corre(ae._get_active_rates())


@pytest.mark.parametrize("valor", [0, -50])
def test_una_tasa_en_cero_o_negativa_no_cuenta(base, valor):
    """Cero divide, y negativo da vuelta el signo de la ganancia."""
    corre(_sembrar(base, panel=45, raspado=valor, hace_horas=1))
    tasas = corre(ae._get_active_rates())
    assert tasas["bcv_ves_usd"] == 45


# ══════════════════════════════════════════════════════════════════════════
# 2. El límite lo pone el panel, no el código
# ══════════════════════════════════════════════════════════════════════════

def test_EL_LIMITE_SALE_DEL_PANEL(base):
    """La regla del proyecto: configurar no puede requerir editar código.

    Con el límite de fábrica (24 h) un raspado de hace tres horas sirve. Bajando
    el límite a una hora desde el panel, el mismo raspado deja de servir.
    """
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=3))
    assert corre(ae._get_active_rates())["bcv_ves_usd"] == 50

    corre(configuracion.escribir(base, "bcv_horas_de_vigencia", 1))
    assert corre(ae._get_active_rates())["bcv_ves_usd"] == 40, (
        "cambiar el límite en el panel no cambió nada: el número volvió a estar "
        "escrito en el código")


def test_el_limite_esta_en_el_catalogo_de_la_pantalla():
    """La pantalla se dibuja con lo que manda el API, así que estar en el
    catálogo es lo único que hace falta para que aparezca."""
    claves = [a["clave"] for a in configuracion.catalogo_para_la_pantalla()]
    assert "bcv_horas_de_vigencia" in claves


def test_si_el_ajuste_no_se_puede_leer_se_usan_veinticuatro_horas(base):
    """Que la base no conteste no puede tirar abajo la contabilidad."""
    class BaseRota:
        def __getitem__(self, _nombre):
            raise RuntimeError("la base no contesta")

    assert corre(bcv_scraper.horas_de_vigencia(BaseRota())) == \
        bcv_scraper.HORAS_DE_VIGENCIA_POR_OMISION


# ══════════════════════════════════════════════════════════════════════════
# 3. `vigencia()`, que es lo que decide
# ══════════════════════════════════════════════════════════════════════════

def test_vigencia_cuenta_las_horas(base):
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=5))
    estado = corre(bcv_scraper.vigencia(base))
    assert estado["hay_raspado"] is True
    assert estado["dolar"] == 50
    assert 4.9 < estado["edad_horas"] < 5.1
    assert estado["vencida"] is False
    assert estado["sirve"] is True
    assert estado["horas_de_vigencia"] == 24
    assert estado["fetched_at"]


def test_vigencia_sin_ningun_raspado(base):
    corre(_sembrar(base, panel=40, raspado=None))
    estado = corre(bcv_scraper.vigencia(base))
    assert estado["hay_raspado"] is False
    assert estado["sirve"] is False
    # No hay nada que haya vencido: no hay nada.
    assert estado["vencida"] is False


def test_vigencia_con_el_reloj_desfasado(base):
    """Una fecha futura es raro, pero no es viejo."""
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=-10))
    estado = corre(bcv_scraper.vigencia(base))
    assert estado["edad_horas"] == 0
    assert estado["sirve"] is True


def test_la_pantalla_del_panel_recibe_la_antiguedad(base):
    """`get_latest` es lo que alimenta la tarjeta del panel."""
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=100))
    doc = corre(bcv_scraper.get_latest(base))
    assert doc["vencida"] is True
    assert doc["edad_horas"] > 99
    assert doc["horas_de_vigencia"] == 24


# ══════════════════════════════════════════════════════════════════════════
# 4. El aviso: una vez por raspado vencido, no una por revisión
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def avisos(monkeypatch):
    """Intercepta los avisos al personal, sin mandar nada."""
    mandados = []

    async def falso(**kwargs):
        mandados.append(kwargs)
        return 1

    from services import notifications
    monkeypatch.setattr(notifications, "avisar_al_personal", falso)
    return mandados


def test_se_avisa_cuando_la_tasa_vence(base, avisos):
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=72))
    estado = corre(bcv_scraper.vigencia(base))
    assert corre(aviso_de_bcv.avisar_si_vencio(base, estado)) == 1
    assert len(avisos) == 1
    assert avisos[0]["solo_super_admin"] is True
    assert "3 días" in avisos[0]["message"]
    # El mensaje lo lee una persona que tiene que ir a hacer algo.
    assert "Tasas" in avisos[0]["message"]


def test_NO_SE_AVISA_DOS_VECES_POR_EL_MISMO_RASPADO(base, avisos):
    """El revisor corre cada hora. Sin esto serían veinticuatro avisos por día
    por el mismo problema, y a los dos días nadie mira ningún aviso."""
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=72))
    estado = corre(bcv_scraper.vigencia(base))
    for _ in range(5):
        corre(aviso_de_bcv.avisar_si_vencio(base, estado))
    assert len(avisos) == 1


def test_se_vuelve_a_avisar_si_el_raspado_cambia(base, avisos):
    """Cuando el raspador se recupera y después vuelve a quedarse atrás, el
    aviso tiene que estar disponible otra vez. Es lo que hace que la marca
    guarde la FECHA del raspado y no un «ya avisé»."""
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=72))
    corre(aviso_de_bcv.avisar_si_vencio(base, corre(bcv_scraper.vigencia(base))))
    assert len(avisos) == 1

    corre(base.bcv_rates.insert_one(
        {"rates": {"dolar": 51}, "fetched_at": _hace(48)}))
    corre(aviso_de_bcv.avisar_si_vencio(base, corre(bcv_scraper.vigencia(base))))
    assert len(avisos) == 2


def test_no_se_avisa_cuando_la_tasa_esta_al_dia(base, avisos):
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=2))
    estado = corre(bcv_scraper.vigencia(base))
    assert corre(aviso_de_bcv.avisar_si_vencio(base, estado)) == 0
    assert avisos == []


def test_no_se_avisa_si_nunca_hubo_raspado(base, avisos):
    """No hay nada que haya vencido. Avisar acá sería ruido el primer día."""
    corre(_sembrar(base, panel=40, raspado=None))
    corre(aviso_de_bcv.avisar_si_vencio(base, corre(bcv_scraper.vigencia(base))))
    assert avisos == []


def test_que_falle_el_aviso_no_rompe_nada(base, monkeypatch):
    """Avisar es un agregado sobre la protección, y la protección ya actuó."""
    async def explota(**kwargs):
        raise RuntimeError("no hay a quién avisar")

    from services import notifications
    monkeypatch.setattr(notifications, "avisar_al_personal", explota)
    corre(_sembrar(base, panel=40, raspado=50, hace_horas=72))
    estado = corre(bcv_scraper.vigencia(base))
    assert corre(aviso_de_bcv.avisar_si_vencio(base, estado)) == 0


def test_un_raspado_sin_fecha_tambien_avisa(base, avisos):
    corre(_sembrar(base, panel=40, raspado=50, con_fecha=False))
    estado = corre(bcv_scraper.vigencia(base))
    assert corre(aviso_de_bcv.avisar_si_vencio(base, estado)) == 1
    assert "no tiene fecha" in avisos[0]["message"]
