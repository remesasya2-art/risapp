"""
La bitácora del núcleo: quién hizo qué, con el antes y el después.

    La aplicación tiene su libro de auditoría (`services/auditoria.py`); el
    núcleo no puede usarlo por la frontera, y además necesita algo que la
    auditoría de una aplicación no tiene: que se pueda PROBAR que no se
    tocó. Por eso cada renglón lleva el hash del anterior y el suyo, igual
    que los asientos del libro. Cambiar un renglón rompe la cadena desde ahí.

    Se anota DESPUES de que la acción salió bien, y si la bitácora falla no
    deshace la acción: la acción ya está hecha y confirmada, y un renglón
    perdido con un ERROR en el registro es mejor que decirle a una persona
    que algo falló cuando en realidad pasó. Igual que en la auditoría de la
    aplicación, y por el mismo motivo.

    Excepción: cuando la acción y la bitácora van en LA MISMA sesión
    (`anotar(sesion, …)`), entran juntas o no entra ninguna. Lo usa el cuatro
    ojos, donde la decisión y su rastro no pueden separarse.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from nucleo import base
from nucleo.esquema import HASH_DEL_PRINCIPIO, bitacora

logger = logging.getLogger("nucleo.bitacora")


def _ahora():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _json(v) -> Optional[str]:
    return None if v is None else json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def hash_de(momento: datetime, actor: str, accion: str, objetivo: str, antes: Optional[str], despues: Optional[str],
            detalle: Optional[str], hash_previo: str) -> str:
    partes = [_aware(momento).isoformat(), actor, accion, objetivo, antes or "", despues or "", detalle or "", hash_previo]
    return hashlib.sha256("\x1f".join(partes).encode("utf-8")).hexdigest()


async def _ultimo_hash(sesion) -> str:
    fila = (await sesion.execute(select(bitacora.c.hash).order_by(bitacora.c.id.desc()).limit(1))).first()
    return fila[0] if fila else HASH_DEL_PRINCIPIO


async def anotar(sesion, *, actor: str, accion: str, objetivo: str, antes=None, despues=None,
                 detalle: Optional[str] = None, ahora: Optional[datetime] = None) -> dict:
    """Un renglón más, encadenado al anterior, en la sesión que se le da."""
    ahora = ahora or _ahora()
    a, d = _json(antes), _json(despues)
    previo = await _ultimo_hash(sesion)
    h = hash_de(ahora, actor, accion, objetivo, a, d, detalle, previo)
    r = await sesion.execute(bitacora.insert().values(
        momento=ahora, actor=actor, accion=accion, objetivo=objetivo, antes=a, despues=d,
        detalle=(detalle or None), hash_previo=previo, hash=h))
    return {"id": r.inserted_primary_key[0], "hash": h}


async def anotar_sin_romper(*, actor: str, accion: str, objetivo: str, antes=None, despues=None,
                            detalle: Optional[str] = None) -> Optional[dict]:
    """Para las rutas: la acción ya está hecha; si esto falla, queda el ERROR
    en el registro y la acción no se deshace. Ver el encabezado."""
    try:
        async with base.sesion() as s:
            return await anotar(s, actor=actor, accion=accion, objetivo=objetivo, antes=antes, despues=despues, detalle=detalle)
    except Exception:
        logger.exception("nucleo: no se pudo anotar en la bitácora %s %s", accion, objetivo)
        return None


async def verificar_cadena(sesion) -> dict:
    """Recorre la bitácora entera y recalcula cada hash."""
    filas = (await sesion.execute(select(bitacora).order_by(bitacora.c.id))).all()
    previo = HASH_DEL_PRINCIPIO
    for f in filas:
        if f.hash_previo != previo:
            return {"ok": False, "renglones": len(filas), "roto_en": f.id, "motivo": "el hash previo no coincide con el renglón anterior"}
        if hash_de(f.momento, f.actor, f.accion, f.objetivo, f.antes, f.despues, f.detalle, f.hash_previo) != f.hash:
            return {"ok": False, "renglones": len(filas), "roto_en": f.id, "motivo": "el contenido no coincide con su hash: el renglón fue alterado"}
        previo = f.hash
    return {"ok": True, "renglones": len(filas), "roto_en": None, "motivo": None, "hash_final": previo}


def _fila(f) -> dict:
    return {"id": f.id, "momento": _aware(f.momento).isoformat(), "actor": f.actor, "accion": f.accion,
            "objetivo": f.objetivo, "antes": json.loads(f.antes) if f.antes else None,
            "despues": json.loads(f.despues) if f.despues else None, "detalle": f.detalle, "hash": f.hash}


async def listar(limite: int = 100, accion: Optional[str] = None, objetivo: Optional[str] = None) -> list:
    async with base.sesion() as s:
        consulta = select(bitacora).order_by(bitacora.c.id.desc()).limit(limite)
        if accion:
            consulta = consulta.where(bitacora.c.accion == accion)
        if objetivo:
            consulta = consulta.where(bitacora.c.objetivo == objetivo)
        return [_fila(f) for f in (await s.execute(consulta)).all()]


async def ultimo(accion: str, objetivo: str) -> Optional[dict]:
    async with base.sesion() as s:
        f = (await s.execute(select(bitacora).where(bitacora.c.accion == accion, bitacora.c.objetivo == objetivo)
                             .order_by(bitacora.c.id.desc()).limit(1))).first()
        return _fila(f) if f else None
