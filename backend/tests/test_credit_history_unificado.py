"""
Tests del historial cripto unificado (GET /api/credits/history).

Corren AISLADOS: no tocan Mongo ni levantan el servidor. `build_history_pipeline`
está separado del handler justamente para poder ejercitarlo así.

Se valida en dos capas:

  1. Estructura del pipeline: que el $match de cada rama filtre por usuario y
     moneda, que acepte `currency_input` en mayúscula y minúscula, que el $sort
     sea por fecha descendente y que el $facet lleve el $skip/$limit de la página.

  2. Semántica, corriendo el pipeline sobre un mini-intérprete en memoria
     (`_run_pipeline`) que implementa SOLO las etapas y operadores que usamos.
     No es MongoDB: es una referencia ejecutable del comportamiento esperado
     (orden, total combinado, normalización de reembolsos). La ejecución real
     contra $unionWith exige MongoDB >= 4.4 y se verifica en staging.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.credits import build_history_pipeline  # noqa: E402


USER = "user_test"
OTHER_USER = "user_otro"


def dt(day, hour=0):
    return datetime(2026, 8, day, hour, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Mini-intérprete: solo las etapas/operadores que usa build_history_pipeline.
# --------------------------------------------------------------------------

def _type_of(value):
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def _field(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _eval(expr, doc):
    if isinstance(expr, str) and expr.startswith("$"):
        return _field(doc, expr[1:])
    if not isinstance(expr, dict):
        return expr
    if "$literal" in expr:
        return expr["$literal"]
    if "$toLower" in expr:
        value = _eval(expr["$toLower"], doc)
        return value.lower() if isinstance(value, str) else value
    if "$type" in expr:
        return _type_of(_eval(expr["$type"], doc))
    if "$ifNull" in expr:
        first, second = expr["$ifNull"]
        value = _eval(first, doc)
        return value if value is not None else _eval(second, doc)
    if "$cond" in expr:
        cond, then, otherwise = expr["$cond"]
        return _eval(then, doc) if _eval(cond, doc) else _eval(otherwise, doc)
    if "$in" in expr:
        needle, haystack = expr["$in"]
        return _eval(needle, doc) in _eval(haystack, doc)
    if "$gt" in expr:
        left, right = expr["$gt"]
        left, right = _eval(left, doc), _eval(right, doc)
        if left is None or right is None:
            return False
        return left > right
    raise AssertionError(f"operador no soportado por el intérprete de test: {expr}")


def _matches(doc, query):
    for field, cond in query.items():
        value = _field(doc, field)
        if isinstance(cond, dict) and "$in" in cond:
            if value not in cond["$in"]:
                return False
        elif value != cond:
            return False
    return True


def _project(doc, projection):
    out = {}
    for key, spec in projection.items():
        if key == "_id":
            continue
        if spec == 1:
            if key in doc:
                out[key] = doc[key]
        else:
            value = _eval(spec, doc)
            if value is not None or isinstance(spec, dict) and ("$gt" in spec or "$literal" in spec):
                out[key] = value
    return out


def _run_pipeline(pipeline, collections, base):
    docs = [dict(d) for d in collections[base]]
    for stage in pipeline:
        (name, spec), = stage.items()
        if name == "$match":
            docs = [d for d in docs if _matches(d, spec)]
        elif name == "$project":
            docs = [_project(d, spec) for d in docs]
        elif name == "$addFields":
            for d in docs:
                for key, expr in spec.items():
                    d[key] = _eval(expr, d)
        elif name == "$unionWith":
            docs = docs + _run_pipeline(spec["pipeline"], collections, spec["coll"])
        elif name == "$sort":
            for field, direction in reversed(list(spec.items())):
                docs.sort(key=lambda d: d.get(field), reverse=direction == -1)
        elif name == "$skip":
            docs = docs[spec:]
        elif name == "$limit":
            docs = docs[:spec]
        elif name == "$count":
            docs = [{spec: len(docs)}] if docs else []
        elif name == "$facet":
            return [{k: _run_pipeline(sub, {"__f": docs}, "__f") for k, sub in spec.items()}]
        else:
            raise AssertionError(f"etapa no soportada por el intérprete de test: {name}")
    return docs


# --------------------------------------------------------------------------
# Fixture: depósitos + envíos + reembolsos mezclados, y ruido que NO debe salir.
# --------------------------------------------------------------------------

@pytest.fixture
def collections():
    return {
        "crypto_deposits": [
            {"order_id": "dep_1", "user_id": USER, "currency": "usdt", "amount": 50.0,
             "credit_amount": 50.0, "credited": True, "status": "finished",
             "network": "trc20", "created_at": dt(1)},
            {"order_id": "dep_2", "user_id": USER, "currency": "usdc", "amount": 20.0,
             "credited": False, "status": "pending", "created_at": dt(6)},
            # Ruido: otro usuario.
            {"order_id": "dep_otro", "user_id": OTHER_USER, "currency": "usdt",
             "amount": 999.0, "status": "finished", "created_at": dt(7)},
        ],
        "transactions": [
            # Envío simple, ticker en mayúscula (como lo escribe el código actual).
            {"transaction_id": "tx_send", "display_id": "000020", "user_id": USER,
             "type": "withdrawal", "currency_input": "USDT", "amount_input": 10.0,
             "amount_output": 7150.0, "currency_output": "VES", "status": "completed",
             "funded_from": "balance", "beneficiary_data": {"full_name": "julian"},
             "created_at": dt(3)},
            # Reembolso NUEVO: booleano + refund_amount.
            {"transaction_id": "tx_refund_nuevo", "display_id": "000021", "user_id": USER,
             "type": "withdrawal", "currency_input": "USDT", "amount_input": 10.0,
             "amount_output": 7150.0, "status": "rejected", "funded_from": "payment",
             "refunded_to_balance": True, "refunded_to_balance_field": "balance_usdt",
             "refund_amount": 9.93, "created_at": dt(5)},
            # Reembolso VIEJO: el monto vivía en refunded_to_balance como float.
            {"transaction_id": "tx_refund_legacy", "display_id": "000022", "user_id": USER,
             "type": "withdrawal", "currency_input": "USDT", "amount_input": 4.0,
             "amount_output": 2860.0, "status": "rejected", "funded_from": "payment",
             "refunded_to_balance": 4.0, "refunded_to_balance_field": "balance_usdt",
             "created_at": dt(2)},
            # Ticker en minúscula: tiene que entrar igual.
            {"transaction_id": "tx_lower", "display_id": "000023", "user_id": USER,
             "type": "withdrawal", "currency_input": "usdc", "amount_input": 1.0,
             "amount_output": 715.0, "status": "pending", "created_at": dt(4)},
            # Ruido: envío en RIS, no es cripto.
            {"transaction_id": "tx_ris", "user_id": USER, "type": "withdrawal",
             "currency_input": "RIS", "amount_input": 5.0, "created_at": dt(8)},
            # Ruido: recarga, no es withdrawal.
            {"transaction_id": "tx_recarga", "user_id": USER, "type": "recharge",
             "currency_input": "USDT", "amount_input": 5.0, "created_at": dt(9)},
            # Ruido: otro usuario.
            {"transaction_id": "tx_otro", "user_id": OTHER_USER, "type": "withdrawal",
             "currency_input": "USDT", "amount_input": 5.0, "created_at": dt(10)},
        ],
    }


def _facet(collections, key=None, skip=0, limit=10):
    pipeline = build_history_pipeline(USER, key, skip, limit)
    result = _run_pipeline(pipeline, collections, "crypto_deposits")[0]
    total = result["total"][0]["count"] if result["total"] else 0
    return result["items"], total


# --------------------------------------------------------------------------
# 1. Estructura del pipeline
# --------------------------------------------------------------------------

def test_pipeline_filtra_por_usuario_y_moneda():
    pipeline = build_history_pipeline(USER, "usdt", 0, 10)
    deposit_match = pipeline[0]["$match"]
    assert deposit_match["user_id"] == USER
    assert deposit_match["currency"] == "usdt"

    union = pipeline[2]["$unionWith"]
    assert union["coll"] == "transactions"
    send_match = union["pipeline"][0]["$match"]
    assert send_match["user_id"] == USER
    assert send_match["type"] == "withdrawal"
    # Acepta las dos formas en que puede estar guardado el ticker.
    assert set(send_match["currency_input"]["$in"]) == {"USDT", "usdt"}


def test_pipeline_sin_moneda_incluye_las_dos():
    pipeline = build_history_pipeline(USER, None, 0, 10)
    assert pipeline[0]["$match"]["currency"] == {"$in": ["usdt", "usdc"]}
    send_match = pipeline[2]["$unionWith"]["pipeline"][0]["$match"]
    assert set(send_match["currency_input"]["$in"]) == {"USDT", "usdt", "USDC", "usdc"}


def test_pipeline_ordena_desc_y_pagina_en_el_facet():
    pipeline = build_history_pipeline(USER, None, 20, 10)
    assert pipeline[-2] == {"$sort": {"date": -1}}
    facet = pipeline[-1]["$facet"]
    assert facet["items"] == [{"$skip": 20}, {"$limit": 10}]
    assert facet["total"] == [{"$count": "count"}]


# --------------------------------------------------------------------------
# 2. Semántica: depósito + envío + reembolso mezclados
# --------------------------------------------------------------------------

def test_mezcla_depositos_envios_y_reembolsos_ordenados_por_fecha(collections):
    items, total = _facet(collections)

    # 2 depósitos + 4 envíos cripto del usuario. El envío en RIS, la recarga y
    # todo lo del otro usuario quedan afuera.
    assert total == 6
    assert [i.get("order_id") or i["transaction_id"] for i in items] == [
        "dep_2",           # día 6
        "tx_refund_nuevo", # día 5
        "tx_lower",        # día 4
        "tx_send",         # día 3
        "tx_refund_legacy",# día 2
        "dep_1",           # día 1
    ]
    assert [i["kind"] for i in items] == [
        "deposit", "send", "send", "send", "send", "deposit",
    ]


def test_total_es_combinado_y_no_por_fuente(collections):
    # La página trae 2 items pero el total tiene que seguir siendo el de las
    # dos colecciones juntas: es el bug que evitamos al usar $facet.
    items, total = _facet(collections, limit=2)
    assert len(items) == 2
    assert total == 6


def test_paginacion_atraviesa_las_dos_fuentes(collections):
    pagina_1, _ = _facet(collections, skip=0, limit=3)
    pagina_2, _ = _facet(collections, skip=3, limit=3)
    ids_1 = {i.get("order_id") or i["transaction_id"] for i in pagina_1}
    ids_2 = {i.get("order_id") or i["transaction_id"] for i in pagina_2}
    assert not ids_1 & ids_2
    assert len(ids_1 | ids_2) == 6


def test_filtro_por_moneda(collections):
    items, total = _facet(collections, key="usdt")
    assert total == 4
    assert {i["currency"] for i in items} == {"usdt"}

    items, total = _facet(collections, key="usdc")
    assert total == 2
    assert {i["currency"] for i in items} == {"usdc"}


def test_envio_expone_monto_cripto_y_ves(collections):
    items, _ = _facet(collections, key="usdt")
    envio = next(i for i in items if i.get("transaction_id") == "tx_send")
    assert envio["kind"] == "send"
    assert envio["amount"] == 10.0
    assert envio["amount_output"] == 7150.0
    assert envio["currency"] == "usdt"
    assert envio["beneficiary_data"]["full_name"] == "julian"
    assert envio["funded_from"] == "balance"


def test_reembolso_nuevo_y_viejo_se_normalizan_igual(collections):
    items, _ = _facet(collections, key="usdt")
    nuevo = next(i for i in items if i.get("transaction_id") == "tx_refund_nuevo")
    legacy = next(i for i in items if i.get("transaction_id") == "tx_refund_legacy")

    assert nuevo["refunded_to_balance"] is True
    assert nuevo["refund_amount"] == 9.93

    # El documento viejo guardaba el monto en refunded_to_balance; el pipeline
    # lo traduce a la misma forma, así el frontend no distingue el origen.
    assert legacy["refunded_to_balance"] is True
    assert legacy["refund_amount"] == 4.0


def test_envio_sin_reembolso_no_marca_devolucion(collections):
    items, _ = _facet(collections, key="usdt")
    envio = next(i for i in items if i.get("transaction_id") == "tx_send")
    assert envio["refunded_to_balance"] is False
    assert envio.get("refund_amount") is None


def test_deposito_conserva_los_campos_de_hoy(collections):
    items, _ = _facet(collections, key="usdt")
    deposito = next(i for i in items if i.get("order_id") == "dep_1")
    assert deposito["kind"] == "deposit"
    assert deposito["amount"] == 50.0
    assert deposito["credit_amount"] == 50.0
    assert deposito["credited"] is True
    assert deposito["status"] == "finished"
    assert deposito["network"] == "trc20"
