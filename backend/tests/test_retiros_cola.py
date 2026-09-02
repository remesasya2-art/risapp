"""
tests/test_retiros_cola.py — La cola de pagos.

EL DEFECTO QUE MAS IMPORTA DE ESTE ARCHIVO
    El panel mostraba «TOTAL VES NECESARIOS» sumando `amount_output` de TODOS
    los retiros pendientes. Pero un retiro sale en VES o en BRL —los dos viven
    con `type: "withdrawal"`— así que un envío en reales sumaba sus reales al
    total de bolívares. Quien mira ese número para saber cuánta plata poner en
    las cuentas venezolanas provisiona mal, y no tiene cómo darse cuenta.

    `test_el_total_a_provisionar_NO_mezcla_bolivares_con_reales` es ese caso.

LOS OTROS
    - El total en RIS decía «0,00» siempre: la ruta nunca devolvió el campo.
    - Se traían 200 retiros de cualquier estado y se filtraba en el navegador,
      así que pasados los 200 el pendiente más viejo se caía de la cola.
    - No era FIFO.
    - Una consulta a `users` por cada retiro.
    - «Unknown» por leer sólo `name`.
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


rt = _cargar("retiros")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
BASE = {}


@pytest.fixture(autouse=True)
def base_limpia():
    base = mongomock_motor.AsyncMongoMockClient()["risapp_test"]
    BASE["db"] = base
    corre(base.users.insert_one({
        "user_id": "usr_ana", "email": "ana@example.com", "full_name": "Ana Pérez",
    }))
    yield base
    BASE.clear()


def retiro(**extra):
    """Un retiro tal como lo escribe `POST /withdrawal`."""
    n = extra.pop("n", 1)
    horas = extra.pop("horas", 1)
    doc = {
        "transaction_id": f"wd_{n:012d}",
        "display_id": f"{n:06d}",
        "user_id": "usr_ana",
        "type": "withdrawal",
        "amount_input": 10.0, "currency_input": "RIS",
        "amount_output": 1380.0, "currency_output": "VES",
        "rate": 138.0,
        "status": "pending",
        "beneficiary_data": {"full_name": "Julio Marshall", "bank": "Banesco",
                             "cedula": "V-12345678", "account_number": "01340000"},
        "created_at": AHORA - timedelta(hours=horas),
    }
    doc.update(extra)
    corre(BASE["db"].transactions.insert_one(doc))
    return doc


def cola(**kw):
    kw.setdefault("ahora", AHORA)
    return corre(rt.cola(BASE["db"], **kw))


def contadores():
    return corre(rt.contadores(BASE["db"], ahora=AHORA))


# ─── 1. El total a provisionar ────────────────────────────────────────────

def test_el_total_a_provisionar_NO_mezcla_bolivares_con_reales():
    """EL DEFECTO GRAVE.

    El panel rotulaba «TOTAL VES NECESARIOS» una suma de `amount_output` que
    incluía los retiros en reales. Con estos datos, la cifra vieja daba 3.380
    «VES» —1.380 de bolívares más 2.000 de reales— y el operador provisionaba
    de más en Venezuela y de menos en Brasil.
    """
    retiro(n=1, amount_output=1380.0, currency_output="VES")
    retiro(n=2, amount_output=2000.0, currency_output="BRL")

    cajas = {m["moneda"]: m for m in contadores()["por_moneda"]}
    assert cajas["VES"]["total"] == 1380.0
    assert cajas["BRL"]["total"] == 2000.0
    # Y en ningún lado aparece la suma de las dos.
    assert 3380.0 not in [m["total"] for m in contadores()["por_moneda"]]


def test_cada_moneda_dice_TAMBIEN_cuantas_ordenes_son():
    """«20.000 VES» no dice lo mismo si son dos órdenes o cuarenta."""
    retiro(n=1, amount_output=1000.0, currency_output="VES")
    retiro(n=2, amount_output=500.0, currency_output="VES")
    retiro(n=3, amount_output=700.0, currency_output="BRL")
    cajas = {m["moneda"]: m for m in contadores()["por_moneda"]}
    assert cajas["VES"]["ordenes"] == 2
    assert cajas["BRL"]["ordenes"] == 1


def test_el_total_en_RIS_ya_no_dice_cero():
    """La pantalla leía `total_ris_pending` y la ruta nunca devolvió el campo:
    era `undefined` y se dibujaba «0,00» con la cola llena."""
    retiro(n=1, amount_input=10.0, currency_input="RIS")
    retiro(n=2, amount_input=25.5, currency_input="RIS")
    origen = {m["moneda"]: m["total"] for m in contadores()["por_origen"]}
    assert origen["RIS"] == 35.5


def test_el_debito_en_cripto_no_se_suma_a_los_RIS():
    """Un retiro de USDT debita USDT, no RIS. Mezclarlos infla el pasivo."""
    retiro(n=1, amount_input=10.0, currency_input="RIS")
    retiro(n=2, amount_input=100.0, currency_input="USDT")
    origen = {m["moneda"]: m["total"] for m in contadores()["por_origen"]}
    assert origen["RIS"] == 10.0
    assert origen["USDT"] == 100.0


def test_lo_ya_pagado_no_cuenta_como_plata_a_provisionar():
    retiro(n=1, amount_output=1380.0, status="completed")
    retiro(n=2, amount_output=500.0, status="rejected")
    assert contadores()["por_moneda"] == []


def test_un_retiro_sin_moneda_de_salida_cuenta_como_VES():
    """Los retiros viejos no guardaban `currency_output`. Dejarlos fuera del
    total escondería plata que hay que pagar igual."""
    retiro(n=1, amount_output=900.0)
    del_doc = corre(BASE["db"].transactions.update_one(
        {"transaction_id": "wd_000000000001"}, {"$unset": {"currency_output": ""}}))
    assert del_doc.modified_count == 1
    cajas = {m["moneda"]: m for m in contadores()["por_moneda"]}
    assert cajas["VES"]["total"] == 900.0


# ─── 2. La cola no pierde órdenes ─────────────────────────────────────────

def test_el_pendiente_MAS_VIEJO_no_se_pierde_detras_de_doscientos_pagados():
    """El corte de 200 se aplicaba antes de filtrar y del más nuevo al más
    viejo. Es gente esperando su plata."""
    retiro(n=0, horas=900, status="pending", transaction_id="wd_elviejo")
    for i in range(1, 230):
        retiro(n=i, horas=1, status="completed")
    pagina = cola(estado="pending")
    assert "wd_elviejo" in [w["transaction_id"] for w in pagina["withdrawals"]]
    assert pagina["total"] == 1


def test_con_historial_y_nada_pendiente_la_cola_viene_VACIA():
    for i in range(5):
        retiro(n=i, status="completed")
    pagina = cola(estado="pending")
    assert pagina["withdrawals"] == []
    assert pagina["total"] == 0


# ─── 3. FIFO ──────────────────────────────────────────────────────────────

def test_los_pendientes_salen_de_la_mas_VIEJA_a_la_mas_nueva():
    """Del otro lado hay alguien esperando un cobro."""
    retiro(n=1, horas=1, transaction_id="wd_nuevo")
    retiro(n=2, horas=200, transaction_id="wd_viejo")
    retiro(n=3, horas=50, transaction_id="wd_medio")
    ids = [w["transaction_id"] for w in cola(estado="pending")["withdrawals"]]
    assert ids == ["wd_viejo", "wd_medio", "wd_nuevo"]


def test_los_pagados_salen_de_la_mas_NUEVA_a_la_mas_vieja():
    retiro(n=1, horas=1, status="completed", transaction_id="wd_reciente")
    retiro(n=2, horas=200, status="completed", transaction_id="wd_antiguo")
    ids = [w["transaction_id"] for w in cola(estado="completed")["withdrawals"]]
    assert ids == ["wd_reciente", "wd_antiguo"]


def test_el_pendiente_lleva_su_posicion_y_sigue_contando_al_paginar():
    for i in range(5):
        retiro(n=i, horas=100 - i)
    assert [w["posicion"] for w in cola(estado="pending", limite=2)["withdrawals"]] == [1, 2]
    assert [w["posicion"] for w in
            cola(estado="pending", limite=2, saltear=2)["withdrawals"]] == [3, 4]


# ─── 4. Antigüedad ────────────────────────────────────────────────────────

def test_la_antiguedad_es_MAS_EXIGENTE_que_en_las_recargas():
    """Una recarga que tarda es un saldo que no aparece; un retiro que tarda es
    plata que alguien ya no tiene y todavía no recibió."""
    assert rt.ANTIGUEDAD_URGENTE < 24
    retiro(n=1, horas=13)
    assert cola()["withdrawals"][0]["antiguedad"]["nivel"] == "urgente"


def test_la_antiguedad_distingue_los_tres_niveles():
    retiro(n=1, horas=1, transaction_id="wd_ok")
    retiro(n=2, horas=5, transaction_id="wd_atencion")
    retiro(n=3, horas=30, transaction_id="wd_urgente")
    niveles = {w["transaction_id"]: w["antiguedad"]["nivel"]
               for w in cola()["withdrawals"]}
    assert niveles["wd_ok"] == "normal"
    assert niveles["wd_atencion"] == "atencion"
    assert niveles["wd_urgente"] == "urgente"


def test_un_retiro_SIN_FECHA_no_se_hace_pasar_por_recien_llegado():
    retiro(n=1, created_at=None)
    anti = cola()["withdrawals"][0]["antiguedad"]
    assert anti["horas"] is None
    assert anti["nivel"] == "desconocida"


def test_los_contadores_dicen_cuanto_espero_el_mas_viejo():
    retiro(n=1, horas=2)
    retiro(n=2, horas=90)
    assert contadores()["mas_vieja"]["horas"] == pytest.approx(90, abs=1)
    assert contadores()["mas_vieja"]["nivel"] == "urgente"


# ─── 5. Búsqueda ──────────────────────────────────────────────────────────

def test_se_puede_buscar_por_el_numero_de_orden():
    """Es lo que dicta el cliente cuando llama a reclamar."""
    retiro(n=43, display_id="000043", transaction_id="wd_elque")
    retiro(n=44, display_id="000044")
    pagina = cola(estado="pending", texto="000043")
    assert [w["transaction_id"] for w in pagina["withdrawals"]] == ["wd_elque"]


def test_se_puede_buscar_por_la_CEDULA_del_beneficiario():
    """Buscar sólo por nombre no alcanza: los nombres se escriben de mil
    formas y la cédula es lo único que el cliente dicta sin error."""
    retiro(n=1, transaction_id="wd_conced",
           beneficiary_data={"full_name": "Julio M", "cedula": "V-98765432"})
    retiro(n=2, beneficiary_data={"full_name": "Otro", "cedula": "V-111"})
    pagina = cola(estado="pending", texto="98765432")
    assert [w["transaction_id"] for w in pagina["withdrawals"]] == ["wd_conced"]


def test_se_puede_buscar_por_la_cuenta_de_destino():
    retiro(n=1, transaction_id="wd_cuenta",
           beneficiary_data={"full_name": "X", "account_number": "01020304050"})
    retiro(n=2, beneficiary_data={"full_name": "Y", "account_number": "999"})
    assert [w["transaction_id"] for w in
            cola(estado="pending", texto="0102030")["withdrawals"]] == ["wd_cuenta"]


def test_se_puede_buscar_por_el_nombre_del_beneficiario():
    retiro(n=1, transaction_id="wd_julio")
    assert cola(estado="pending", texto="Julio")["total"] == 1


def test_una_busqueda_sin_resultados_no_devuelve_TODA_la_cola():
    retiro(n=1)
    assert cola(estado="pending", texto="noexisteesto")["total"] == 0


# ─── 6. Filtro por moneda ─────────────────────────────────────────────────

def test_se_puede_ver_SOLO_lo_que_hay_que_pagar_en_una_moneda():
    """El operador que carga las cuentas venezolanas no quiere ver los reales."""
    retiro(n=1, currency_output="VES", transaction_id="wd_ves")
    retiro(n=2, currency_output="BRL", transaction_id="wd_brl")
    pagina = cola(estado="pending", moneda="VES")
    assert [w["transaction_id"] for w in pagina["withdrawals"]] == ["wd_ves"]
    assert pagina["total"] == 1


# ─── 7. Los campos que la ruta vieja no devolvía ──────────────────────────

def test_el_nombre_del_usuario_sale_de_full_name_y_no_dice_Unknown():
    retiro(n=1)
    assert cola()["withdrawals"][0]["user_name"] == "Ana Pérez"


def test_un_usuario_borrado_no_rompe_la_cola_ni_inventa_un_nombre():
    retiro(n=1, user_id="usr_fantasma")
    assert cola()["withdrawals"][0]["user_name"] == ""


def test_la_cola_dice_si_otro_operador_ya_esta_pagando_esta_orden():
    """El backend ya rechaza con 409 si otro la tiene; la ruta no devolvía el
    campo, así que al segundo operador le llegaba un error crudo."""
    retiro(n=1, assigned_to="usr_admin2", assigned_to_name="Marta")
    fila = cola()["withdrawals"][0]
    assert fila["assigned_to_name"] == "Marta"


def test_un_retiro_SIN_datos_del_beneficiario_se_marca():
    """No hay a quién pagarle, y hay que verlo antes de abrir la orden."""
    retiro(n=1, beneficiary_data={})
    fila = cola()["withdrawals"][0]
    assert fila["falta_beneficiario"] is True
    assert fila["falta_destino"] is True


def test_los_contadores_cuentan_los_retiros_sin_beneficiario():
    retiro(n=1, beneficiary_data={})
    retiro(n=2)
    assert contadores()["sin_beneficiario"] == 1


def test_los_comprobantes_se_cuentan_mirando_LOS_DOS_campos():
    """Conviven `proof_images` (lista) y `proof_image` (uno solo, viejo).
    Contar sólo el nuevo mostraría «0 imágenes» en retiros que sí lo tienen."""
    retiro(n=1, status="completed", proof_image="data:image/png;base64,AAA",
           transaction_id="wd_viejo_formato")
    retiro(n=2, status="completed", proof_images=["a", "b"],
           transaction_id="wd_nuevo_formato")
    por_id = {w["transaction_id"]: w["comprobantes"]
              for w in cola(estado="completed")["withdrawals"]}
    assert por_id["wd_viejo_formato"] == 1
    assert por_id["wd_nuevo_formato"] == 2


# ─── 8. Paginación y límites ──────────────────────────────────────────────

def test_el_total_cuenta_las_que_cumplen_el_filtro_no_las_de_la_pagina():
    for i in range(30):
        retiro(n=i)
    pagina = cola(estado="pending", limite=10)
    assert len(pagina["withdrawals"]) == 10
    assert pagina["total"] == 30
    assert pagina["hay_mas"] is True


def test_un_limite_disparatado_no_baja_la_coleccion_entera():
    retiro(n=1)
    assert cola(estado="pending", limite=99999)["limite"] == rt.LIMITE_MAXIMO


def test_un_estado_inventado_se_rechaza_y_no_devuelve_todo():
    """Tratarlo como «all» mostraría plata ya pagada como si esperara pago."""
    retiro(n=1)
    with pytest.raises(rt.ColaInvalida):
        cola(estado="pendiente")


def test_los_ocultos_al_admin_no_entran_ni_en_la_lista_ni_en_los_contadores():
    retiro(n=1)
    retiro(n=2, hidden_from_admin=True)
    assert cola(estado="pending")["total"] == 1
    assert contadores()["pendientes"] == 1


def test_una_recarga_no_se_cuela_en_la_cola_de_retiros():
    """Las dos viven en `transactions`: sin el filtro por tipo, la cola de
    pagos mostraría plata que ENTRA como si hubiera que pagarla."""
    retiro(n=1)
    corre(BASE["db"].transactions.insert_one({
        "transaction_id": "rech_1", "type": "recharge_ves", "status": "pending",
        "amount_output": 999.0, "created_at": AHORA}))
    assert cola(estado="pending")["total"] == 1
    assert contadores()["pendientes"] == 1


# ─── 9. Eficiencia ────────────────────────────────────────────────────────

class _DbEspia:
    """Cuenta las consultas a `users` sin cambiar el comportamiento.

    Se envuelve el `db` entero: `base.users` devuelve un objeto nuevo en cada
    acceso, así que parchear uno solo deja el contador en cero, que es
    indistinguible de «no consultó nada».
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
    """Sin esto, un contador roto haría pasar el test de abajo."""
    espia = _DbEspia(BASE["db"])
    corre(espia.users.find({}).to_list(None))
    assert espia.consultas_users == 1


def test_los_usuarios_se_traen_en_UNA_consulta_y_no_una_por_retiro():
    """La ruta vieja hacía un `find_one` a `users` POR CADA retiro."""
    for i in range(25):
        retiro(n=i)
    espia = _DbEspia(BASE["db"])
    pagina = corre(rt.cola(espia, estado="pending", limite=25, ahora=AHORA))
    assert len(pagina["withdrawals"]) == 25
    assert espia.consultas_users == 1, \
        f"{espia.consultas_users} consultas a users para 25 retiros"


# ─── 10. Montos ilegibles ─────────────────────────────────────────────────

def test_un_monto_ilegible_no_deja_al_operador_sin_cola():
    retiro(n=1, amount_output="no-es-un-numero")
    assert cola()["withdrawals"][0]["amount_output"] == 0.0


# ─── 11. La pantalla ──────────────────────────────────────────────────────

import re  # noqa: E402

_PANTALLA = os.path.abspath(os.path.join(
    _BACKEND, "..", "frontend", "src", "components", "admin", "Retiros.jsx"))


def _codigo(ruta):
    r"""El fuente SIN comentarios: un test que lee código lee código, no prosa.

    Sin sacarlos, el comentario que explica por qué el total YA NO se rotula
    «VES» a secas contaría como si lo rotulara.

    POR QUE NO ALCANZA UN `re.sub(r"/\*.*?\*/", ...)`
        Porque `accept="image/*"` contiene `/*` DENTRO DE UNA CADENA. Esa
        expresión lo toma por apertura de comentario y borra todo hasta el
        siguiente `*/` real: en este archivo eran 4.787 caracteres de código,
        el botón de pagar incluido. Un test que afirma que algo NO está
        habría pasado en verde justamente porque el limpiador lo borró.

        Así que se recorre el texto respetando comillas simples, dobles y
        backticks, y sólo se saca lo que es comentario de verdad.
    """
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()

    salida = []
    i, n = 0, len(texto)
    comilla = None
    while i < n:
        c = texto[i]
        if comilla:
            salida.append(c)
            if c == "\\" and i + 1 < n:
                salida.append(texto[i + 1])
                i += 2
                continue
            if c == comilla:
                comilla = None
            i += 1
            continue
        if c in "\"'`":
            comilla = c
            salida.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and texto[i + 1] == "*":
            fin = texto.find("*/", i + 2)
            i = n if fin < 0 else fin + 2
            continue
        if c == "/" and i + 1 < n and texto[i + 1] == "/":
            fin = texto.find("\n", i)
            i = n if fin < 0 else fin
            continue
        salida.append(c)
        i += 1
    return "".join(salida)


@pytest.fixture
def pantalla():
    if not os.path.exists(_PANTALLA):
        pytest.skip("el frontend no está en este checkout")
    return _codigo(_PANTALLA)


def test_la_pantalla_NO_rotula_un_total_unico_en_VES(pantalla):
    """El cartel viejo decía «TOTAL VES NECESARIOS» sobre una suma que incluía
    los reales. Ese rótulo no puede volver."""
    assert "TOTAL VES" not in pantalla.upper()
    assert "total_ves_pending" not in pantalla
    assert "por_moneda" in pantalla


def test_cada_monto_a_pagar_lleva_SU_moneda_al_lado(pantalla):
    """Escribir «VES» fijo al lado del monto muestra un retiro en reales como
    si fueran bolívares.

    Se afirma sobre LA CELDA, no sobre que el nombre del campo aparezca en
    algún lugar del archivo: con eso, cambiar la celda a un «VES» fijo dejaba
    pasar el test porque `currency_output` seguía usándose en otras cuatro
    partes.
    """
    fila = pantalla[pantalla.index("function Fila("):pantalla.index("function Detalle(")]
    assert "fmt(w.amount_output)" in fila, "la fila no muestra el monto a pagar"
    assert "{w.currency_output}" in fila, "el monto no lleva su moneda al lado"
    for fija in (" VES<", " BRL<", " VES</span>", ">VES<"):
        assert fija not in fila, f"la fila tiene una moneda escrita fija: {fija!r}"


def test_la_pantalla_le_pide_el_estado_al_servidor(pantalla):
    assert "status: estado" in pantalla
    assert ".filter(w => w.status" not in pantalla
    assert ".filter((w) => w.status" not in pantalla


def test_la_pantalla_pagina_y_no_baja_la_cola_entera(pantalla):
    assert "limit: POR_PAGINA" in pantalla
    assert "skip: pagina * POR_PAGINA" in pantalla


def test_registrar_el_pago_pasa_SIEMPRE_por_una_confirmacion(pantalla):
    """Cerrar la orden le avisa al usuario que ya cobró: si todavía no se
    transfirió, el reclamo aparece cuando nadie se acuerda."""
    assert "onPedirConfirmacion" in pantalla
    principal = pantalla[pantalla.index("data-testid={`pagar-") - 900:
                         pantalla.index("data-testid={`pagar-")]
    assert "onPagar" not in principal, "el botón principal cierra la orden sin confirmar"


def test_el_rechazo_EXIGE_un_motivo_escrito(pantalla):
    """Antes mandaba «Rechazado por administrador» fijo: al usuario le volvía
    la plata sin saber por qué, y reintentaba con el mismo error."""
    assert "Rechazado por administrador" not in pantalla
    assert "disabled={ocupado || !motivo.trim()}" in pantalla


def test_la_pantalla_usa_el_candado_por_operador(pantalla):
    assert "/admin/ordenes/tomar" in pantalla
    assert "/admin/ordenes/liberar" in pantalla
    assert "assigned_to_name" in pantalla


def test_la_pantalla_DIBUJA_la_antiguedad_de_cada_orden(pantalla):
    assert "espera(w.antiguedad)" in pantalla
    assert "SEMAFORO[w.antiguedad?.nivel]" in pantalla


def test_la_cola_se_dibuja_como_FILAS_y_no_como_tarjetas(pantalla):
    assert "<table" in pantalla
    assert "filas.map((w) => (\n                  <Fila" in pantalla


def test_el_detalle_se_abre_en_UNA_orden_por_vez(pantalla):
    assert "abierta={abierta === w.transaction_id}" in pantalla
    assert "const [abierta, setAbierta] = useState(null);" in pantalla


def test_al_cerrar_una_orden_se_abre_la_SIGUIENTE(pantalla):
    assert "const siguiente = (idActual)" in pantalla
    assert pantalla.count("siguiente(w.transaction_id);") == 2


def test_no_se_puede_cerrar_una_orden_SIN_comprobante(pantalla):
    """Es la única prueba de que la transferencia se hizo."""
    assert "comprobantes.length > 0 && !ocupado" in pantalla
    assert "puedePagar" in pantalla
