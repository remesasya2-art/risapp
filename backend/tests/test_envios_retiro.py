"""
A nombre de quien y a donde despacha el usuario.

CONTEXTO
    El usuario manda su paquete a una agencia de Pacaraima. Esa caja tiene que
    llegar rotulada de forma que el equipo pueda retirarla en el mostrador. Este
    modulo arma ese bloque y lo devuelve como texto para copiar.

LA REGLA QUE EVITA EL DESASTRE SILENCIOSO
    El nombre se CONGELA en el envio al cotizar. Cambiar la nomina hoy no cambia
    la etiqueta de una caja que ya esta viajando, porque el mostrador compara esa
    etiqueta contra un documento y no contra la base de datos.

    Es lo opuesto a la cuenta bancaria del transportista, que deliberadamente NO
    se congela. Los dos criterios conviven y los dos tienen razon: uno protege
    contra pagarle a una cuenta muerta, el otro contra reclamar una caja con un
    nombre que ya no dice lo mismo que la etiqueta.

QUE SE CUBRE
    1. La direccion se renderiza desde una plantilla editable, sin str.format.
    2. La linea de agencia depende de la modalidad y no son intercambiables.
    3. Sin nadie de turno la cotizacion NO se cae: cae al nombre de la empresa.
    4. Un colaborador con la autorizacion vencida no puede retirar aunque este
       activo.
    5. El CPF y el telefono no salen nunca hacia el usuario.

Los modulos se cargan por ruta directa para no arrastrar services/__init__.py.
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


ret = _cargar("envios_retiro")


def corre(coro):
    return asyncio.run(coro)


def _proyectar(doc, proyeccion):
    """El doble respeta las proyecciones. Un fake que las ignora escondió en PR D
    un endpoint que devolvía todos los límites en null."""
    if not proyeccion:
        return dict(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return {k: v for k, v in doc.items() if k in incluir}
    excluir = [k for k, v in proyeccion.items() if not v]
    return {k: v for k, v in doc.items() if k not in excluir}


class _Coleccion:
    def __init__(self, filas=None):
        self.filas = filas if filas is not None else []

    def _match(self, d, filtro):
        return all(d.get(k) == v for k, v in filtro.items())

    class _Cursor:
        def __init__(self, filas):
            self.filas = filas

        async def to_list(self, n):
            return list(self.filas)[:n] if n else list(self.filas)

    def find(self, filtro, proyeccion=None):
        return self._Cursor([_proyectar(d, proyeccion)
                             for d in self.filas if self._match(d, filtro)])

    async def find_one(self, filtro, proyeccion=None):
        for d in self.filas:
            if self._match(d, filtro):
                return _proyectar(d, proyeccion)
        return None


class _Db:
    def __init__(self, **colecciones):
        self._c = {k: _Coleccion(v) for k, v in colecciones.items()}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))


AHORA = datetime.now(timezone.utc)

PUNTO = {
    "setting_id": ret.SETTING_PUNTO_ORIGEN,
    "nombre": "AC Pacaraima", "cep": "69355000", "ciudad": "Pacaraima", "uf": "RR",
    "modalidad": "caixa_postal", "caixa_postal": "123",
    "razon_social": "RIS App LTDA",
    "plantilla_direccion": ret.PLANTILLA_POR_DEFECTO,
    "retirador_activo_id": "col_aaaa1111",
}

MARIA = {"colaborador_id": "col_aaaa1111", "nombre": "María Gómez",
         "cpf": "111.222.333-44", "telefono": "+55 95 99999-0000", "activo": True,
         "creado_at": AHORA - timedelta(days=30),
         "autorizado_desde": AHORA - timedelta(days=30), "autorizado_hasta": None}
JOSE = {"colaborador_id": "col_bbbb2222", "nombre": "José Ferreira",
        "cpf": "555.666.777-88", "telefono": "+55 95 98888-0000", "activo": True,
        "creado_at": AHORA - timedelta(days=10),
        "autorizado_desde": AHORA - timedelta(days=10), "autorizado_hasta": None}


def db_completa(punto=None, nomina=None):
    return _Db(app_settings=[punto or dict(PUNTO)],
               colaboradores_retiro=list(nomina if nomina is not None else [MARIA, JOSE]))


# ─── 1. La dirección que el usuario copia ─────────────────────────────────

def test_el_bloque_se_arma_entero_y_se_puede_copiar():
    b = corre(ret.bloque_de_despacho(db=db_completa(), ahora=AHORA))
    assert b["disponible"] is True
    assert b["destinatario"] == "RIS App LTDA - A/C María Gómez"
    assert b["texto_copiable"] == (
        "RIS App LTDA\n"
        "A/C María Gómez\n"
        "Caixa Postal 123 - AC Pacaraima\n"
        "Pacaraima - RR\n"
        "CEP 69355-000")


def test_el_cep_se_copia_con_guion_aunque_se_guarde_sin_el():
    """Se guarda normalizado para poder compararlo; se copia como se escribe en
    un sobre, que es la forma a la que el mostrador está acostumbrado."""
    b = corre(ret.bloque_de_despacho(db=db_completa(), ahora=AHORA))
    assert b["cep"] == "69355-000"


def test_la_plantilla_es_editable_y_no_se_concatena_en_el_codigo():
    punto = {**PUNTO, "plantilla_direccion": "{razon_social} / {ciudad} ({uf}) / CEP {cep}"}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto), ahora=AHORA))
    assert b["texto_copiable"] == "RIS App LTDA / Pacaraima (RR) / CEP 69355-000"


@pytest.mark.parametrize("modalidad,extra,esperado", [
    ("caixa_postal", {"caixa_postal": "123"}, "Caixa Postal 123 - AC Pacaraima"),
    ("posta_restante", {}, "Posta Restante - AC Pacaraima"),
    ("otro", {"direccion": "Av. Brasil, s/n"}, "Av. Brasil, s/n - AC Pacaraima"),
])
def test_la_linea_de_agencia_depende_de_la_modalidad(modalidad, extra, esperado):
    """No son intercambiables: una Caixa Postal tiene número y una Posta Restante
    no. Poner "Caixa Postal" sin número manda al usuario a un casillero que no
    existe."""
    assert ret.linea_agencia({**PUNTO, "modalidad": modalidad, "caixa_postal": None,
                              **extra}) == esperado


def test_una_caixa_postal_sin_numero_no_inventa_uno():
    linea = ret.linea_agencia({**PUNTO, "caixa_postal": None})
    assert linea == "Caixa Postal - AC Pacaraima"


# ─── 2. La plantilla no puede ser una vía de entrada ──────────────────────

def test_la_plantilla_no_se_renderiza_con_format():
    """`.format` sobre una plantilla editable desde el panel deja leer internals
    de Python desde un string de configuración. Se reemplazan tokens de una lista
    blanca y nada más."""
    punto = {**PUNTO,
             "plantilla_direccion": "{razon_social.__class__.__mro__} y {razon_social}"}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto), ahora=AHORA))
    # El assert que importa: con `.format` esto rinde "(<class 'str'>, <class
    # 'object'>)". El token queda literal, que es lo correcto.
    assert "{razon_social.__class__.__mro__}" in b["texto_copiable"]
    assert "class" not in b["texto_copiable"].replace("__class__", "")
    assert "RIS App LTDA" in b["texto_copiable"]


def test_una_llave_suelta_en_la_plantilla_no_rompe_la_cotizacion():
    punto = {**PUNTO, "plantilla_direccion": "{razon_social} — 50 % { descuento"}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto), ahora=AHORA))
    assert b["disponible"] is True
    assert "RIS App LTDA" in b["texto_copiable"]


def test_un_token_que_no_existe_queda_a_la_vista():
    """Borrarlo en silencio produciría una dirección incompleta que parece
    completa. Que se lea "{telefono}" en la vista previa es cómo el super
    administrador se entera de que ese dato no está."""
    punto = {**PUNTO, "plantilla_direccion": "{razon_social}\nTel {telefono}"}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto), ahora=AHORA))
    assert "{telefono}" in b["texto_copiable"]


# ─── 3. Nadie de turno no puede frenar la operación ───────────────────────

def test_sin_nomina_se_despacha_igual_a_nombre_de_la_empresa():
    """Un problema interno de nómina no puede dejar a un usuario sin poder
    despachar. Una razón social sin A/C igual se retira; lo que pasa es que el
    mostrador no sabe a quién llamar."""
    b = corre(ret.bloque_de_despacho(db=db_completa(nomina=[]), ahora=AHORA))
    assert b["disponible"] is True
    assert b["destinatario"] == "RIS App LTDA"
    assert b["retirador_nombre"] is None
    assert b["retirador_motivo"] == "sin_nomina"


def test_sin_nombre_no_queda_una_linea_ac_colgada():
    """"A/C" a secas en una etiqueta es peor que no poner nada."""
    b = corre(ret.bloque_de_despacho(db=db_completa(nomina=[]), ahora=AHORA))
    assert "A/C" not in b["texto_copiable"]
    assert b["texto_copiable"].startswith("RIS App LTDA\nCaixa Postal")


def test_si_el_designado_no_puede_retirar_se_usa_un_suplente_y_se_avisa():
    de_licencia = {**MARIA, "activo": False}
    b = corre(ret.bloque_de_despacho(db=db_completa(nomina=[de_licencia, JOSE]),
                                     ahora=AHORA))
    assert b["retirador_nombre"] == "José Ferreira"
    assert b["retirador_motivo"] == "suplente"


def test_una_autorizacion_vencida_no_retira_aunque_la_ficha_este_activa():
    """Enterarse de esto en el mostrador es enterarse con el paquete adentro."""
    vencida = {**MARIA, "autorizado_hasta": AHORA - timedelta(days=1)}
    colaborador, motivo = corre(ret.retirador_de_turno(PUNTO,
                                                       db=db_completa(nomina=[vencida]),
                                                       ahora=AHORA))
    assert colaborador is None and motivo == "sin_nomina"


def test_una_autorizacion_que_todavia_no_empezo_tampoco():
    futura = {**MARIA, "autorizado_desde": AHORA + timedelta(days=5)}
    colaborador, _ = corre(ret.retirador_de_turno(PUNTO,
                                                  db=db_completa(nomina=[futura]),
                                                  ahora=AHORA))
    assert colaborador is None


def test_sin_designar_se_usa_alguien_de_la_nomina_y_el_motivo_lo_dice():
    punto = {**PUNTO, "retirador_activo_id": None}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto), ahora=AHORA))
    assert b["retirador_nombre"] == "María Gómez"      # la más antigua, no "cualquiera"
    assert b["retirador_motivo"] == "sin_designar"


def test_el_activo_se_filtra_en_python_y_no_en_la_query():
    """Regla dura del proyecto: `{"activo": True}` no matchea un 1 ni un "true",
    y este proyecto ya se comió ese bug tres veces."""
    con_uno = {**MARIA, "activo": 1}
    colaborador, motivo = corre(ret.retirador_de_turno(
        PUNTO, db=db_completa(nomina=[con_uno]), ahora=AHORA))
    assert colaborador is not None and motivo == "designado"


# ─── 4. Lo que no puede fallar ────────────────────────────────────────────

def test_sin_punto_de_origen_se_dice_que_falta_en_vez_de_armar_media_direccion():
    """Una dirección a medias es una caja despachada a la nada."""
    b = corre(ret.bloque_de_despacho(db=_Db(app_settings=[]), ahora=AHORA))
    assert b["disponible"] is False
    assert any("razón social" in f for f in b["faltantes"])
    assert any("agencia" in f for f in b["faltantes"])


def test_si_la_base_no_contesta_no_se_lanza():
    base = db_completa()

    async def revienta(*a, **k):
        raise RuntimeError("timeout")
    base.app_settings.find_one = revienta

    b = corre(ret.bloque_de_despacho(db=base, ahora=AHORA))
    assert b["disponible"] is False and b["faltantes"]


def test_un_corte_de_base_no_congela_una_etiqueta_sin_nombre():
    """La regla de "un problema interno no puede dejar al usuario sin despachar"
    es sobre la nómina VACÍA, que es un estado real y estable. Un failover de dos
    segundos es otra cosa: congelarlo deja una caja rotulada sin A/C para
    siempre, indistinguible en la cola de un `sin_nomina` legítimo, y sin forma
    de contestar después por qué esa caja salió sin nombre."""
    base = db_completa()
    base.colaboradores_retiro.find = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    b = corre(ret.bloque_de_despacho(db=base, ahora=AHORA))
    assert b["disponible"] is False
    assert any("Reintentá" in f for f in b["faltantes"])


def test_los_datos_personales_no_salen_en_el_bloque():
    """El CPF y el teléfono existen para la autorización ante el transportista y
    se quedan del lado interno. Al usuario le llega el nombre y nada más."""
    b = corre(ret.bloque_de_despacho(db=db_completa(), ahora=AHORA))
    plano = repr(b)
    assert MARIA["cpf"] not in plano
    assert MARIA["telefono"] not in plano
    assert "cpf" not in b and "telefono" not in b


def test_un_token_sin_valor_no_deja_un_renglon_en_blanco():
    """Un renglón vacío en el medio de una dirección lo lee el mostrador como un
    dato faltante, y con razón: parece que ahí iba algo que se perdió."""
    punto = {**PUNTO, "modalidad": "posta_restante", "caixa_postal": None,
             "plantilla_direccion": "{razon_social}\n{caixa_postal}\n{ciudad} - {uf}"}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto), ahora=AHORA))
    assert b["texto_copiable"] == "RIS App LTDA\nPacaraima - RR"
    assert "\n\n" not in b["texto_copiable"]


# ─── 5. Lo que encontro la revision adversarial ───────────────────────────

def test_el_token_del_nombre_se_saca_sin_llevarse_la_razon_social():
    """EL DEFECTO P0. La primera versión borraba la línea entera, y la plantilla
    natural pone las dos cosas juntas: sin nómina, la caja salía rotulada sin
    razón social y sin A/C — o sea, sin nada contra qué comparar en el mostrador,
    que es exactamente lo que este módulo existe para evitar."""
    punto = {**PUNTO, "plantilla_direccion":
             "{razon_social} A/C {retirador_nombre}\n{linea_agencia}\nCEP {cep}"}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto, nomina=[]), ahora=AHORA))
    assert b["texto_copiable"].startswith("RIS App LTDA")
    assert "A/C" not in b["texto_copiable"]
    assert "CEP 69355-000" in b["texto_copiable"]


def test_una_plantilla_de_una_sola_linea_no_queda_vacia_sin_nomina():
    punto = {**PUNTO, "plantilla_direccion":
             "{razon_social}, A/C {retirador_nombre}, {linea_agencia}, CEP {cep}"}
    b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto, nomina=[]), ahora=AHORA))
    assert b["texto_copiable"]
    assert "RIS App LTDA" in b["texto_copiable"]


@pytest.mark.parametrize("activo", [False, 0, "false", "no", "0", "off", "False"])
def test_una_baja_escrita_de_cualquier_forma_da_de_baja(activo):
    """El `is False` fallaba ABIERTO: dar de baja con un script que escribe
    `activo: 0` dejaba a la persona saliendo rotulada en todas las cotizaciones
    nuevas. Es el mismo bug que el módulo dice estar evitando, del lado
    contrario."""
    de_baja = {**MARIA, "activo": activo}
    colaborador, motivo = corre(ret.retirador_de_turno(
        PUNTO, db=db_completa(nomina=[de_baja]), ahora=AHORA))
    assert colaborador is None and motivo == "sin_nomina"


@pytest.mark.parametrize("hasta", ["31/12/2025", 1735603200, 20251231,
                                   "2025-12-31 (vencido)", "ayer"])
def test_una_fecha_de_vencimiento_ilegible_no_es_sin_vencimiento(hasta):
    """Acá se falla CERRADO, al revés que en el resto del módulo. Una fecha
    presente pero que no se puede leer es un dato roto, y leerlo como permiso
    ilimitado es el único error de este archivo que termina con una caja retenida
    en el mostrador."""
    dudoso = {**MARIA, "autorizado_hasta": hasta}
    colaborador, _ = corre(ret.retirador_de_turno(
        PUNTO, db=db_completa(nomina=[dudoso]), ahora=AHORA))
    assert colaborador is None


def test_una_ficha_sin_fecha_de_vencimiento_si_es_sin_vencimiento():
    """Ausente e ilegible no son lo mismo: la mayoría de las autorizaciones no
    vencen, y tratarlas como rotas dejaría la nómina vacía."""
    sin_tope = {**MARIA, "autorizado_hasta": None}
    colaborador, motivo = corre(ret.retirador_de_turno(
        PUNTO, db=db_completa(nomina=[sin_tope]), ahora=AHORA))
    assert colaborador is not None and motivo == "designado"


def test_autorizado_hasta_el_31_incluye_el_31_entero():
    """El formulario manda una fecha sin hora y Pydantic la vuelve medianoche.
    Cortando ahí, con la ficha diciendo "hasta el 31", el colaborador dejaba de
    poder retirar a las 20 h del 30, hora de Roraima. Una fecha sin hora es un
    día, no un instante."""
    hoy = datetime(2026, 12, 31, tzinfo=timezone.utc)
    ficha = {**MARIA, "autorizado_hasta": hoy}       # "hasta el 31/12/2026"

    for hora in (0, 4, 12, 23):
        momento = hoy.replace(hour=hora, minute=30)
        colaborador, _ = corre(ret.retirador_de_turno(
            PUNTO, db=db_completa(nomina=[ficha]), ahora=momento))
        assert colaborador is not None, f"a las {hora}:30 del 31 todavía puede retirar"

    colaborador, _ = corre(ret.retirador_de_turno(
        PUNTO, db=db_completa(nomina=[ficha]),
        ahora=hoy + timedelta(days=1)))
    assert colaborador is None                        # el 1 de enero ya no


def test_una_hora_explicita_de_vencimiento_se_respeta_tal_cual():
    """Solo se extiende al fin del día lo que llegó SIN hora. Una fecha con hora
    es una decisión, no un formulario de calendario."""
    corte = datetime(2026, 12, 31, 9, 0, tzinfo=timezone.utc)
    ficha = {**MARIA, "autorizado_hasta": corte}
    antes, _ = corre(ret.retirador_de_turno(PUNTO, db=db_completa(nomina=[ficha]),
                                            ahora=corte - timedelta(minutes=1)))
    despues, _ = corre(ret.retirador_de_turno(PUNTO, db=db_completa(nomina=[ficha]),
                                              ahora=corte + timedelta(minutes=1)))
    assert antes is not None and despues is None


def test_quien_sale_rotulado_no_depende_del_orden_de_mongo():
    """La cola de retiro se agrupa POR EL NOMBRE CONGELADO. Si dos cotizaciones
    del mismo día se congelan con nombres distintos porque Mongo devolvió las
    fichas en otro orden, el que viaja a Pacaraima puede reclamar la mitad de las
    cajas y tiene que volver con otra persona."""
    punto = {**PUNTO, "retirador_activo_id": None}
    for nomina in ([MARIA, JOSE], [JOSE, MARIA]):
        b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto, nomina=nomina),
                                         ahora=AHORA))
        assert b["retirador_nombre"] == "María Gómez"


def test_el_desempate_no_se_rompe_sin_fecha_de_alta():
    sin_fecha = [{k: v for k, v in c.items() if k != "creado_at"} for c in (JOSE, MARIA)]
    punto = {**PUNTO, "retirador_activo_id": None}
    for nomina in (sin_fecha, list(reversed(sin_fecha))):
        b = corre(ret.bloque_de_despacho(db=db_completa(punto=punto, nomina=nomina),
                                         ahora=AHORA))
        assert b["retirador_nombre"] == "María Gómez"   # col_aaaa1111 < col_bbbb2222


def test_el_modulo_no_menciona_ninguna_marca():
    """Los nombres de las empresas de transporte se cargan desde el panel y se
    referencian por código. Nunca entran al repositorio."""
    ruta = os.path.join(_BACKEND, "services", "envios_retiro.py")
    fuente = open(ruta, encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
        assert marca not in fuente
