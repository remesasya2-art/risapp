"""
tests/test_contratos_de_envios.py — lo que el cliente ve de sus envíos, y lo
que ve cualquiera con el enlace de seguimiento, sale por un contrato; y la
dirección de despacho se recorta con UNA lista de lo permitido en los tres
lugares que la muestran. Ver models/envios_salida.py.

Las respuestas de envíos ya se armaban campo por campo, así que el contrato
es la segunda capa. Por eso casi todos los tests de la segunda capa
sustituyen la función que arma la respuesta por una que devuelve de más: si
no, el contrato no tiene nada que cortar y el test pasa sin probarlo.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

ANA = User(user_id="usr_ana", name="Ana", email="ana@ejemplo.test", role="user")
AHORA = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
TOKEN = "a" * 40

# Un campo que HOY no existe en el bloque de despacho. Con la lista de lo
# prohibido de antes, habría viajado a la pantalla el día que alguien lo
# agregara en services/envios_retiro.py.
CAMPO_NUEVO = {"retirador_telefono": "+55 95 99999-0000"}


def ya(c):
    return asyncio.run(c)


def un_envio(**cambios):
    doc = {
        "envio_id": "env_001", "display_id": "E000001", "user_id": "usr_ana",
        "estado": "en_transito_int", "tracking_token": TOKEN, "created_at": AHORA,
        "modalidad_flete": "destino",
        "destino_brasil": {
            "destinatario": "RISApp LTDA - A/C María Gómez", "razon_social": "RISApp LTDA",
            "retirador_nombre": "María Gómez", "retirador_id": "col_aaaa1111",
            "retirador_motivo": "designado", "congelado_at": AHORA,
            "agencia": "Agencia Centro", "linea_agencia": "Agencia Centro - Pacaraima",
            "modalidad": "caixa_postal", "caixa_postal": "123", "ciudad": "Pacaraima",
            "uf": "RR", "cep": "69345-000", "texto_copiable": "RISApp LTDA\nA/C María Gómez",
            **CAMPO_NUEVO,
        },
        "destino": {"ciudad": "Caracas", "estado_ve": "Miranda", "agencia_nombre": "Centro",
                    "transportista_id": "trp_interno", "zona_tarifa": "Z3",
                    "destinatario": {"nombre": "Pedro Pérez", "documento": "V-12345678",
                                     "telefono": "+58 412 0000000"}},
        "paquete": {"declarado": {"peso_kg": "2.30"},
                    "verificado": {"peso_kg": "2.50", "verificado_por": "usr_operador"},
                    "contenido_descripcion": "Ropa"},
        "cotizacion": {"total_estimado_ris": "132.00", "total_final_ris": None,
                       "es_estimado": True, "moneda": "RIS", "margen_ris": "22.00",
                       "terminos_version": "t1"},
        "cobros": {"inicial": {"monto_ris": "132.00", "estado": "pagado",
                               "detalle": {"margen": "22.00"}}},
        "origen": {"codigo_objeto": "AA123456789BR", "comprobante_asset_id": "ast_x",
                   "posteado_at": AHORA, "verificado": {"at": AHORA, "por": "usr_operador"}},
        "entrega": {"guia": "GUIA-1"},
        "ip": "10.0.0.7",
    }
    doc.update(cambios)
    return doc


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["contratos_envios"]
    usar_base(m)
    ya(m.envios.insert_one(un_envio()))
    ya(m.envios_eventos.insert_many([
        {"envio_id": "env_001", "a_estado": "esperando_postagem",
         "created_at": AHORA - timedelta(days=2), "detalle": {"por": "usr_operador"}},
        {"envio_id": "env_001", "a_estado": "en_transito_int", "created_at": AHORA,
         "detalle": {"monto_ris": "132.00"}},
    ]))
    return m


def cliente(quien=ANA):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.envios import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    return TestClient(app)


def sustituir(monkeypatch, modulo, nombre, devuelve):
    async def falsa(*a, **k):
        return devuelve
    monkeypatch.setattr(modulo, nombre, falsa)


# ══════════════════════════════════════════════════════════════════════════
# 1. La dirección de despacho: una sola lista de lo permitido
# ══════════════════════════════════════════════════════════════════════════

def test_EL_DETALLE_NO_MUESTRA_LO_QUE_NO_ESTA_EN_LA_LISTA_DEL_RETIRO(base):
    r = cliente().get("/api/envios/env_001")
    assert r.status_code == 200, r.text
    retiro = r.json()["retiro"]
    assert retiro["texto_copiable"] == "RISApp LTDA\nA/C María Gómez", "lo que la etiqueta copia sigue"
    assert retiro["retirador_nombre"] == "María Gómez", "el «A/C» de la etiqueta es a propósito"
    for interno in ("retirador_id", "retirador_motivo", "congelado_at", "retirador_telefono"):
        assert interno not in retiro, interno
    assert "col_aaaa1111" not in r.text and "+55 95" not in r.text


def test_LA_LISTA_DEL_RETIRO_DEJA_AFUERA_LO_QUE_NO_CONOCE():
    """La diferencia con la lista de lo prohibido: un campo nuevo NO pasa."""
    from models.envios_salida import retiro_para_el_cliente
    salida = retiro_para_el_cliente({**un_envio()["destino_brasil"], "disponible": True,
                                     "faltantes": ["x"]})
    assert "retirador_telefono" not in salida and "disponible" not in salida
    assert "faltantes" not in salida and "retirador_id" not in salida
    assert retiro_para_el_cliente(None) == {} and retiro_para_el_cliente("roto") == {}


def test_LA_CONFIRMACION_RECORTA_EL_RETIRO_CON_LA_MISMA_LISTA():
    from services.envios_crear import _resultado
    retiro = _resultado(un_envio())["retiro"]
    assert retiro["texto_copiable"] and "retirador_telefono" not in retiro
    assert "retirador_id" not in retiro and "congelado_at" not in retiro


def test_LOS_TRES_LUGARES_USAN_LA_MISMA_LISTA():
    """Cotizar, confirmar y el detalle. Si uno vuelve a su lista propia de lo
    prohibido, el primer campo nuevo del bloque viaja a esa pantalla."""
    raiz = Path(__file__).resolve().parents[1] / "services"
    for archivo in ("envios_cotizador.py", "envios_crear.py", "envios_consulta.py"):
        fuente = (raiz / archivo).read_text(encoding="utf-8")
        assert '"retiro": retiro_para_el_cliente(despacho)' in fuente, archivo
        assert 'if k not in ("retirador_id"' not in fuente and '"retirador_motivo", "congelado_at")' not in fuente, archivo


# ══════════════════════════════════════════════════════════════════════════
# 2. El detalle y la lista del cliente
# ══════════════════════════════════════════════════════════════════════════

def test_EL_DETALLE_SIGUE_MOSTRANDO_LO_DE_SIEMPRE(base):
    d = cliente().get("/api/envios/env_001").json()
    assert d["display_id"] == "E000001" and d["tracking_token"] == TOKEN
    assert d["destino"] == {"ciudad": "Caracas", "estado": "Miranda", "agencia": "Centro",
                            "destinatario": "Pedro Pérez"}
    assert d["paquete"]["declarado"] == {"peso_kg": "2.30"}, "sin nulls por las medidas que no hay"
    assert d["paquete"]["verificado"] == {"peso_kg": "2.50"}
    assert d["cobros"][0]["monto_ris"] == "132.00" and d["cobros"][0]["estado"] == "pagado"
    assert [p["estado"] for p in d["timeline"]] == ["esperando_postagem", "en_transito_int"]
    assert d["comprobante"]["codigo_objeto"] == "AA123456789BR"


def test_EL_CONTRATO_DEL_DETALLE_CORTA_SOLO(base, monkeypatch):
    """Si la función que arma el detalle devolviera el envío entero."""
    import services.envios_consulta as consulta
    envio = un_envio()
    sustituir(monkeypatch, consulta, "detalle", {
        **envio, "retiro": envio["destino_brasil"],
        "paquete": {"declarado": {"peso_kg": "2.30", "tomado_por": "usr_operador"}},
        "cobros": [{"partida": "inicial", "monto_ris": "132.00", "detalle": {"margen": "22.00"}}],
        "timeline": [{"estado": "en_transito_int", "titulo": "En camino", "detalle": {"por": "usr_operador"}}],
    })
    r = cliente().get("/api/envios/env_001")
    assert r.status_code == 200, r.text
    for secreto in ("usr_operador", "col_aaaa1111", "margen", "10.0.0.7", "V-12345678",
                    "trp_interno", '"user_id"', "+55 95"):
        assert secreto not in r.text, secreto


def test_LA_LISTA_NO_MUESTRA_EL_DOCUMENTO_DEL_DESTINATARIO(base):
    r = cliente().get("/api/envios")
    assert r.status_code == 200
    fila = r.json()["envios"][0]
    assert fila["destino"]["destinatario"] == "Pedro Pérez"
    assert "V-12345678" not in r.text and "margen" not in r.text and '"user_id"' not in r.text


def test_EL_CONTRATO_DE_LA_LISTA_CORTA_SOLO(base, monkeypatch):
    import services.envios_consulta as consulta
    sustituir(monkeypatch, consulta, "listar", {
        "envios": [un_envio()], "pagina": 1, "hay_mas": False, "degradado": False,
        "consulta_mongo": {"user_id": "usr_ana"}})
    r = cliente().get("/api/envios")
    assert r.status_code == 200, r.text
    for secreto in ("V-12345678", "margen", "10.0.0.7", "col_aaaa1111", "consulta_mongo", '"user_id"'):
        assert secreto not in r.text, secreto


def test_UN_ENVIO_VIEJO_CON_OTRA_FORMA_NO_CONTESTA_500(base):
    """Montos como número, fechas como texto: el contrato recorta, no convierte."""
    ya(base.envios.insert_one(un_envio(
        envio_id="env_002", display_id="E000002", created_at="2025-01-02",
        cotizacion={"total_estimado_ris": 90, "moneda": "RIS"},
        paquete={"declarado": {"peso_kg": 1.5}})))
    assert cliente().get("/api/envios").status_code == 200
    r = cliente().get("/api/envios/env_002")
    assert r.status_code == 200 and r.json()["total_ris"] == 90


# ══════════════════════════════════════════════════════════════════════════
# 3. El seguimiento público: sin sesión
# ══════════════════════════════════════════════════════════════════════════

def test_EL_SEGUIMIENTO_PUBLICO_SIGUE_IGUAL(base):
    r = cliente(None).get(f"/api/envios/seguimiento/{TOKEN}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"display_id", "estado", "estado_titulo", "estado_detalle", "destino",
                      "guia_transportista", "creado_at", "timeline"}
    assert d["destino"] == {"ciudad": "Caracas", "estado": "Miranda"}
    assert "Pedro" not in r.text and "V-12345678" not in r.text and "env_001" not in r.text


def test_EL_CONTRATO_DEL_SEGUIMIENTO_CORTA_SOLO(base, monkeypatch):
    """La ruta sin sesión. Si `seguir` devolviera de más, el enlace que anda
    por WhatsApp mostraría quién recibe y con qué documento."""
    import services.envios_seguimiento as seguimiento
    envio = un_envio()
    sustituir(monkeypatch, seguimiento, "seguir", {
        **envio, "destino": envio["destino"],
        "timeline": [{"estado": "en_transito_int", "titulo": "En camino", "at": AHORA,
                      "detalle_interno": {"por": "usr_operador"}}]})
    r = cliente(None).get(f"/api/envios/seguimiento/{TOKEN}")
    assert r.status_code == 200, r.text
    for secreto in ("Pedro", "V-12345678", "+58 412", "usr_operador", "env_001", "usr_ana",
                    "margen", "col_aaaa1111", "10.0.0.7", "tracking_token", "trp_interno"):
        assert secreto not in r.text, secreto
    assert r.json()["destino"] == {"ciudad": "Caracas"}, "estado_ve no es un campo del contrato"


# ══════════════════════════════════════════════════════════════════════════
# 4. El catálogo y los límites
# ══════════════════════════════════════════════════════════════════════════

def test_EL_CONTRATO_DEL_CATALOGO_CORTA_SOLO(base, monkeypatch):
    import services.envios_catalogo as catalogo
    sustituir(monkeypatch, catalogo, "catalogo", {
        "transportistas": [{"transportista_id": "trp_1", "codigo": "TRP-7K2M", "nombre": "Transporte",
                            "costo_interno": "9.99", "agencias": [
                                {"codigo": "AG1", "nombre": "Centro", "ciudad": "Caracas",
                                 "activa": True, "contacto_privado": "+58 000"}]}],
        "origenes": [{"cep": "69345000", "cep_legible": "69345-000", "ciudad": "Pacaraima",
                      "uf": "RR", "propuesto_por": "usr_ana"}],
        "disponible": True, "degradado": False, "cache_hasta": "mañana"})
    r = cliente().get("/api/envios/catalogo")
    assert r.status_code == 200, r.text
    for secreto in ("costo_interno", "contacto_privado", "propuesto_por", "cache_hasta", '"activa"'):
        assert secreto not in r.text, secreto
    assert r.json()["transportistas"][0]["agencias"][0]["codigo"] == "AG1"


def test_EL_CONTRATO_DE_LOS_LIMITES_CORTA_SOLO_Y_NO_INVENTA_CLAVES(base, monkeypatch):
    import services.envios_catalogo as catalogo
    sustituir(monkeypatch, catalogo, "limites", {
        "disponible": True, "faltantes": [], "limites": {"peso_max_kg": 30.0},
        "impuesto_por": {"peso_max_kg": "TRP-7K2M"}, "tarifa_version": "t1",
        "moneda": "RIS", "prohibidos": ["armas"], "terminos_version": "v1",
        "margen_por_defecto": "0.2"})
    import services.encomiendas_abiertas as abiertas
    sustituir(monkeypatch, abiertas, "esta_abierta", True)
    r = cliente(None).get("/api/envios/limites")
    assert r.status_code == 200, r.text
    assert "margen_por_defecto" not in r.text
    assert "descripcion_min_caracteres" not in r.json(), "lo que no vino no sale como null"
    assert r.json()["limites"] == {"peso_max_kg": 30.0}


# ══════════════════════════════════════════════════════════════════════════
# 5. Cada ruta tiene el suyo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("camino,modelo", [
    ("/envios", "MisEnvios"),
    ("/envios/{envio_id}", "DetalleDeMiEnvio"),
    ("/envios/seguimiento/{token}", "SeguimientoPublico"),
    ("/envios/catalogo", "CatalogoDeEnvios"),
    ("/envios/limites", "LimitesDeEnvio"),
])
def test_CADA_RUTA_TIENE_SU_CONTRATO_Y_NO_INVENTA_NULLS(camino, modelo):
    from routes.envios import router
    (ruta,) = [r for r in router.routes if r.path == camino and "GET" in r.methods]
    assert getattr(ruta.response_model, "__name__", None) == modelo
    assert ruta.response_model_exclude_unset is True
