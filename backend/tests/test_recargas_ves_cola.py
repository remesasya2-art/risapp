"""
tests/test_recargas_ves_cola.py — La cola de recargas VES.

QUE DEFIENDEN ESTOS TESTS
    La pantalla vieja pedía las 100 recargas más nuevas de cualquier estado y
    filtraba las pendientes en el navegador. Eso escondía dos defectos que no se
    ven mirando la pantalla un día tranquilo, y los dos tienen su test acá:

      - la pantalla en blanco cuando hay historial y nada pendiente;
      - la orden pendiente que se pierde cuando hay más de cien recargas.

    El segundo es el grave: es plata esperando que nadie ve.

CONTRA MONGOMOCK, NO CONTRA UN DOBLE
    Un doble escrito a mano ordena y corta como su autor cree que ordena y corta
    Mongo. Lo que hay que verificar acá es justamente eso.
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


cv = _cargar("recargas_ves")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
BASE = {}


@pytest.fixture(autouse=True)
def base_limpia():
    base = mongomock_motor.AsyncMongoMockClient()["risapp_test"]
    BASE["db"] = base
    corre(base.users.insert_one({
        "user_id": "usr_ana", "email": "ana@example.com",
        "full_name": "Ana Pérez", "phone": "+58 412 000",
    }))
    yield base
    BASE.clear()


def recarga(**extra):
    """Una recarga VES tal como la escribe `POST /recharge/ves`."""
    n = extra.pop("n", 1)
    horas = extra.pop("horas", 1)
    doc = {
        "transaction_id": f"rech_{n:012d}",
        "user_id": "usr_ana",
        "type": "recharge_ves",
        "amount_ves": 100000.0,
        "amount_ris": 555.56,
        "rate_used": 180.0,
        "status": "pending",
        "destination_bank_id": "bk_ves_1",
        "destination_bank_name": "Banesco",
        "proof_image": "data:image/png;base64,AAA",
        "created_at": AHORA - timedelta(hours=horas),
    }
    doc.update(extra)
    corre(BASE["db"].transactions.insert_one(doc))
    return doc


def cola(**kw):
    kw.setdefault("ahora", AHORA)
    return corre(cv.cola(BASE["db"], **kw))


def contadores():
    return corre(cv.contadores(BASE["db"], ahora=AHORA))


# ─── 1. Los dos defectos que escondía el filtro en el navegador ───────────

def test_con_historial_y_nada_pendiente_la_cola_viene_VACIA_de_verdad():
    """El defecto de la pantalla en blanco.

    El cartel de «no hay nada» estaba atado a que la lista viniera vacía, pero
    lo que se dibujaba era la lista ya filtrada. Con recargas viejas y ninguna
    pendiente, la lista NO venía vacía, el cartel no aparecía, y el filtro no
    dejaba nada: una página muda. Ahora el servidor devuelve exactamente lo que
    se va a dibujar, así que vacío significa vacío.
    """
    for i in range(5):
        recarga(n=i, status="approved")
    pagina = cola(estado="pending")
    assert pagina["recharges"] == []
    assert pagina["total"] == 0


def test_la_pendiente_MAS_VIEJA_no_se_pierde_detras_de_cien_procesadas():
    """El defecto grave: plata esperando que nadie ve.

    El corte de 100 se aplicaba antes de filtrar y ordenando de la más nueva a
    la más vieja. Con más de cien recargas, la pendiente más vieja quedaba fuera
    del corte y desaparecía de la cola.
    """
    recarga(n=0, horas=500, status="pending", transaction_id="rech_lavieja")
    for i in range(1, 130):
        recarga(n=i, horas=1, status="approved")

    pagina = cola(estado="pending")
    ids = [r["transaction_id"] for r in pagina["recharges"]]
    assert "rech_lavieja" in ids, "la pendiente más vieja se perdió"
    assert pagina["total"] == 1


# ─── 2. El orden de una cola de trabajo ───────────────────────────────────

def test_las_pendientes_salen_de_la_mas_VIEJA_a_la_mas_nueva():
    """FIFO: quien más esperó, primero. Al revés entierra lo que más urge."""
    recarga(n=1, horas=1, transaction_id="rech_nueva")
    recarga(n=2, horas=100, transaction_id="rech_vieja")
    recarga(n=3, horas=50, transaction_id="rech_media")
    ids = [r["transaction_id"] for r in cola(estado="pending")["recharges"]]
    assert ids == ["rech_vieja", "rech_media", "rech_nueva"]


def test_las_procesadas_salen_de_la_mas_NUEVA_a_la_mas_vieja():
    """En el historial se busca «qué pasó recién», no quién esperó más."""
    recarga(n=1, horas=1, status="approved", transaction_id="rech_reciente")
    recarga(n=2, horas=100, status="approved", transaction_id="rech_antigua")
    ids = [r["transaction_id"] for r in cola(estado="approved")["recharges"]]
    assert ids == ["rech_reciente", "rech_antigua"]


def test_la_pendiente_lleva_su_posicion_en_la_cola():
    """Para poder decir «sos la número 3» sin contar a ojo."""
    recarga(n=1, horas=100)
    recarga(n=2, horas=50)
    filas = cola(estado="pending")["recharges"]
    assert [f["posicion"] for f in filas] == [1, 2]


def test_la_posicion_sigue_contando_en_la_segunda_pagina():
    """Reiniciarla en cada página haría que dos órdenes sean «la número 1»."""
    for i in range(5):
        recarga(n=i, horas=100 - i)
    filas = cola(estado="pending", limite=2, saltear=2)["recharges"]
    assert [f["posicion"] for f in filas] == [3, 4]


# ─── 3. Antigüedad: el semáforo de la cola ────────────────────────────────

def test_la_antiguedad_marca_lo_que_lleva_mas_de_un_dia_como_URGENTE():
    """Una orden de hace tres días y una de hace dos minutos se veían igual."""
    recarga(n=1, horas=48)
    assert cola()["recharges"][0]["antiguedad"]["nivel"] == "urgente"


def test_la_antiguedad_distingue_los_tres_niveles():
    recarga(n=1, horas=1, transaction_id="rech_ok")
    recarga(n=2, horas=10, transaction_id="rech_atencion")
    recarga(n=3, horas=48, transaction_id="rech_urgente")
    niveles = {r["transaction_id"]: r["antiguedad"]["nivel"]
               for r in cola()["recharges"]}
    assert niveles["rech_ok"] == "normal"
    assert niveles["rech_atencion"] == "atencion"
    assert niveles["rech_urgente"] == "urgente"


def test_una_orden_SIN_FECHA_no_se_hace_pasar_por_recien_llegada():
    """Poner cero horas ahí la mostraría como la más fresca de la cola, que es
    justo lo contrario de lo que hay que sospechar de un dato faltante."""
    recarga(n=1, created_at=None)
    anti = cola()["recharges"][0]["antiguedad"]
    assert anti["horas"] is None
    assert anti["nivel"] == "desconocida"


def test_la_antiguedad_lee_una_fecha_guardada_como_TEXTO():
    """Parte del código graba `created_at` como ISO y parte como datetime."""
    recarga(n=1, created_at="2026-08-31T12:00:00+00:00")
    assert cola()["recharges"][0]["antiguedad"]["horas"] == pytest.approx(48, abs=1)


# ─── 4. Los contadores ────────────────────────────────────────────────────

def test_los_contadores_cuentan_TODO_y_no_solo_la_pagina():
    """Sacados de la página dirían «50» para siempre con paginación."""
    for i in range(60):
        recarga(n=i)
    c = contadores()
    assert c["pendientes"] == 60
    assert len(cola(estado="pending", limite=10)["recharges"]) == 10


def test_los_contadores_dicen_CUANTA_PLATA_esta_esperando():
    """El número que dice si la cola es un problema o un trámite."""
    recarga(n=1, amount_ves=100000.0)
    recarga(n=2, amount_ves=250000.0)
    recarga(n=3, amount_ves=999.0, status="approved")
    assert contadores()["ves_pendiente"] == 350000.0


def test_los_contadores_no_suman_la_plata_ya_procesada():
    recarga(n=1, amount_ves=100000.0, status="approved")
    assert contadores()["ves_pendiente"] == 0


def test_los_contadores_marcan_las_que_NO_SE_PUEDEN_aprobar():
    """Las que nacieron sin banco: hay que resolverlas a mano, una por una."""
    recarga(n=1, destination_bank_id=None, destination_bank=None)
    recarga(n=2, proof_image=None)
    recarga(n=3)
    c = contadores()
    assert c["sin_banco"] == 1
    assert c["sin_comprobante"] == 1


def test_los_contadores_dicen_cuanto_espero_la_MAS_VIEJA():
    """Es el único número que dice si la cola se está atrasando."""
    recarga(n=1, horas=2)
    recarga(n=2, horas=72)
    mas_vieja = contadores()["mas_vieja"]
    assert mas_vieja["horas"] == pytest.approx(72, abs=1)
    assert mas_vieja["nivel"] == "urgente"


# ─── 5. Búsqueda ──────────────────────────────────────────────────────────

def test_se_puede_buscar_por_mail_del_usuario():
    recarga(n=1)
    corre(BASE["db"].users.insert_one({"user_id": "usr_otro", "email": "beto@x.com",
                                       "full_name": "Beto"}))
    recarga(n=2, user_id="usr_otro", transaction_id="rech_beto")
    pagina = cola(estado="pending", texto="beto@x.com")
    assert [r["transaction_id"] for r in pagina["recharges"]] == ["rech_beto"]


def test_se_puede_buscar_por_nombre_del_usuario():
    recarga(n=1, transaction_id="rech_ana")
    assert cola(estado="pending", texto="Ana")["total"] == 1


def test_se_puede_buscar_por_el_id_de_la_orden():
    recarga(n=1, transaction_id="rech_abc123")
    recarga(n=2, transaction_id="rech_zzz999")
    pagina = cola(estado="pending", texto="abc123")
    assert [r["transaction_id"] for r in pagina["recharges"]] == ["rech_abc123"]


def test_se_puede_buscar_por_los_tres_digitos_de_la_referencia():
    """Es el dato que trae el cliente cuando reclama un pago."""
    recarga(n=1, reference_digits="447", transaction_id="rech_conref")
    recarga(n=2, reference_digits="118")
    pagina = cola(estado="all", texto="447")
    assert [r["transaction_id"] for r in pagina["recharges"]] == ["rech_conref"]


def test_una_busqueda_sin_resultados_no_devuelve_TODA_la_cola():
    """El error clásico: el filtro se arma vacío y devuelve el universo."""
    recarga(n=1)
    assert cola(estado="pending", texto="noexisteestemail")["total"] == 0


# ─── 6. Los campos que la ruta vieja no devolvía ──────────────────────────

def test_el_nombre_sale_de_full_name_y_no_dice_Unknown():
    """La ruta vieja leía sólo `name`; los usuarios nuevos guardan `full_name`,
    así que al operador le aparecía «Unknown» sobre plata real."""
    recarga(n=1)
    assert cola()["recharges"][0]["user_name"] == "Ana Pérez"


def test_un_usuario_borrado_no_rompe_la_cola_ni_inventa_un_nombre():
    """La plata sigue registrada aunque el usuario ya no esté."""
    recarga(n=1, user_id="usr_fantasma")
    fila = cola()["recharges"][0]
    assert fila["user_name"] == ""
    assert fila["user_id"] == "usr_fantasma"


def test_la_cola_dice_si_otro_operador_ya_esta_en_esta_orden():
    """`assigned_to` existe en la base y el backend ya rechaza con 409 si otro
    la tiene, pero la ruta no lo devolvía: la pantalla no tenía cómo avisar."""
    recarga(n=1, assigned_to="usr_admin2", assigned_to_name="Marta")
    fila = cola()["recharges"][0]
    assert fila["assigned_to"] == "usr_admin2"
    assert fila["assigned_to_name"] == "Marta"


def test_cada_orden_dice_QUE_LE_FALTA_para_poder_aprobarse():
    """Calcularlo en el servidor evita que el listado y el botón discrepen."""
    recarga(n=1, destination_bank_id=None, destination_bank=None, proof_image=None)
    fila = cola()["recharges"][0]
    assert fila["falta_banco"] is True
    assert fila["falta_comprobante"] is True


def test_cada_orden_trae_un_numero_que_se_puede_dictar_por_telefono():
    """Las recargas VES nunca tuvieron `display_id`: el operador sólo contaba
    con `rech_9f2c8a1b4d5e`, que nadie dicta por teléfono sin equivocarse."""
    recarga(n=1, transaction_id="rech_9f2c8a1b4d5e")
    assert cola()["recharges"][0]["referencia"] == "RV-8A1B4D5E"


def test_la_referencia_humana_es_ESTABLE():
    """Si cambiara entre dos llamadas, no serviría para citarla."""
    assert cv.referencia_humana("rech_9f2c8a1b4d5e") == cv.referencia_humana("rech_9f2c8a1b4d5e")
    assert cv.referencia_humana("rech_aaa") != cv.referencia_humana("rech_bbb")


# ─── 7. Paginación y límites ──────────────────────────────────────────────

def test_el_total_cuenta_las_que_CUMPLEN_EL_FILTRO_no_las_de_la_pagina():
    """Sin esto la pantalla no puede saber si hay una página siguiente."""
    for i in range(30):
        recarga(n=i)
    pagina = cola(estado="pending", limite=10)
    assert len(pagina["recharges"]) == 10
    assert pagina["total"] == 30
    assert pagina["hay_mas"] is True


def test_la_ultima_pagina_dice_que_no_hay_mas():
    for i in range(15):
        recarga(n=i)
    assert cola(estado="pending", limite=10, saltear=10)["hay_mas"] is False


def test_un_limite_disparatado_no_baja_la_coleccion_entera():
    for i in range(5):
        recarga(n=i)
    assert cola(estado="pending", limite=99999)["limite"] == cv.LIMITE_MAXIMO


def test_un_estado_inventado_se_rechaza_y_no_devuelve_todo():
    """Tratarlo como «all» mostraría plata ya acreditada como si esperara."""
    recarga(n=1)
    with pytest.raises(cv.ColaInvalida):
        cola(estado="pendiente")


def test_las_ocultas_al_admin_no_entran_ni_en_la_lista_ni_en_los_contadores():
    recarga(n=1)
    recarga(n=2, hidden_from_admin=True)
    assert cola(estado="pending")["total"] == 1
    assert contadores()["pendientes"] == 1


# ─── 8. Eficiencia ────────────────────────────────────────────────────────

class _DbEspia:
    """Cuenta las consultas a `users` sin cambiar el comportamiento.

    Se envuelve el `db` entero y no se parcha `base.users.find`, porque
    `base.users` devuelve un objeto nuevo en cada acceso: parchear uno no
    alcanza a los demás y el contador queda en cero, que es indistinguible de
    «no consultó nada».
    """

    def __init__(self, base):
        self._base = base
        self.consultas_users = 0

    @property
    def users(self):
        real = self._base.users
        espia = self

        class _Coleccion:
            def find(self, *a, **k):
                espia.consultas_users += 1
                return real.find(*a, **k)

            def __getattr__(self, nombre):
                return getattr(real, nombre)

        return _Coleccion()

    def __getattr__(self, nombre):
        return getattr(self._base, nombre)


def test_el_espia_de_verdad_cuenta():
    """Sin esto, un contador roto haría pasar los dos tests de abajo."""
    espia = _DbEspia(BASE["db"])
    corre(espia.users.find({}).to_list(None))
    assert espia.consultas_users == 1


def test_los_usuarios_se_traen_en_UNA_consulta_y_no_una_por_recarga():
    """La ruta vieja hacía un `find_one` a `users` POR CADA recarga: cien
    recargas, cien viajes a la base en una sola petición."""
    for i in range(25):
        recarga(n=i)
    espia = _DbEspia(BASE["db"])
    pagina = corre(cv.cola(espia, estado="pending", limite=25, ahora=AHORA))
    assert len(pagina["recharges"]) == 25
    assert espia.consultas_users == 1, \
        f"{espia.consultas_users} consultas a users para 25 recargas"


def test_buscar_agrega_UNA_consulta_y_no_una_por_fila():
    """La búsqueda por nombre necesita resolver los usuarios primero; eso son
    dos consultas en total, no dos por recarga."""
    for i in range(25):
        recarga(n=i)
    espia = _DbEspia(BASE["db"])
    corre(cv.cola(espia, estado="pending", texto="Ana", limite=25, ahora=AHORA))
    assert espia.consultas_users == 2


def test_una_cola_vacia_no_consulta_usuarios_al_pedo():
    espia = _DbEspia(BASE["db"])
    corre(cv.cola(espia, estado="pending", ahora=AHORA))
    assert espia.consultas_users == 0


# ─── 9. Montos ────────────────────────────────────────────────────────────

def test_un_monto_ilegible_no_deja_al_operador_sin_cola():
    """Una fila rota no puede tumbar la pantalla entera."""
    recarga(n=1, amount_ves="no-es-un-numero")
    assert cola()["recharges"][0]["amount_ves"] == 0.0


def test_el_monto_se_lee_del_campo_viejo_si_el_nuevo_no_esta():
    """Las recargas viejas guardaban `amount_input`, no `amount_ves`."""
    recarga(n=1, amount_ves=None, amount_input=77000.0)
    assert cola()["recharges"][0]["amount_ves"] == 77000.0


# ─── 10. La pantalla ──────────────────────────────────────────────────────
#
# Estos leen el fuente del frontend. Son guardias contra que una edición futura
# vuelva a poner la cola en el navegador, o saque la confirmación de aprobar.

import re  # noqa: E402

_FRONT = os.path.abspath(os.path.join(_BACKEND, "..", "frontend", "src"))
_PANTALLA = os.path.join(_FRONT, "components", "admin", "RecargasVES.jsx")


def _codigo(ruta):
    """El fuente SIN comentarios.

    Sin sacarlos, el comentario que explica por qué la pantalla ya NO filtra en
    el navegador cuenta como si filtrara. Un test que lee código fuente tiene
    que leer código, no prosa.
    """
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return "\n".join(l for l in texto.split("\n")
                     if not l.lstrip().startswith("//"))


@pytest.fixture
def pantalla():
    if not os.path.exists(_PANTALLA):
        pytest.skip("el frontend no está en este checkout")
    return _codigo(_PANTALLA)


def test_la_pantalla_le_pide_el_ESTADO_al_servidor(pantalla):
    """Si vuelve a traer todo y filtrar en el navegador, vuelven los dos
    defectos: la pantalla muda y la pendiente vieja que se cae de la cola."""
    assert "status: estado" in pantalla
    assert ".filter(r => r.status" not in pantalla
    assert ".filter((r) => r.status" not in pantalla


def test_la_pantalla_pagina_y_no_baja_la_cola_entera(pantalla):
    assert "limit: POR_PAGINA" in pantalla
    assert "skip: pagina * POR_PAGINA" in pantalla


def test_aprobar_pasa_SIEMPRE_por_una_confirmacion(pantalla):
    """El botón que ve el operador abre la confirmación; el que acredita es
    otro. Antes un solo clic movía plata real y no había vuelta atrás."""
    assert "onPedirConfirmacion" in pantalla
    assert "confirmando" in pantalla
    # El botón principal NO puede llamar a la función que acredita.
    principal = pantalla[pantalla.index("data-testid={`approve-recharge-") - 900:
                         pantalla.index("data-testid={`approve-recharge-")]
    assert "onAprobar" not in principal, "el botón principal acredita sin confirmar"


def test_la_pantalla_usa_el_candado_por_operador(pantalla):
    """El backend ya rechazaba con 409 si otro operador tenía la orden; la
    pantalla no lo mostraba y al segundo le llegaba un error crudo."""
    assert "/admin/ordenes/tomar" in pantalla
    assert "/admin/ordenes/liberar" in pantalla
    assert "assigned_to_name" in pantalla


def test_la_pantalla_DIBUJA_la_antiguedad_de_cada_orden(pantalla):
    """Sin esto una orden de tres días y una de dos minutos se ven igual.

    Se afirma sobre lo que se DIBUJA, no sobre que exista una constante con el
    nombre correcto: renombrar la tabla de colores dejaba pasar este test
    aunque el reloj ya no apareciera en ninguna orden.
    """
    assert "espera(r.antiguedad)" in pantalla, "la orden no muestra cuánto esperó"
    assert "SEMAFORO[r.antiguedad?.nivel]" in pantalla, "el reloj no cambia de color"


def test_el_boton_de_aprobar_se_apaga_si_falta_el_banco(pantalla):
    """Dejarlo activo manda al operador a un 400 que ya se puede evitar."""
    assert "falta_banco" in pantalla
    assert "puedeAprobar" in pantalla
