"""
El interruptor del núcleo: apagado, laboratorio o activo.

DE FABRICA, APAGADO. Y FALLA CERRADO.

    Al revés que la recarga o las encomiendas, que fallan abierto porque
    frenar le cobra al usuario una falla nuestra. Acá no hay ningún usuario
    al que frenar: el núcleo no tiene clientes hasta que haya licencia. Si la
    configuración no se puede leer, se asume APAGADO, que es el estado en el
    que no puede pasar nada.

TRES ESTADOS EN UN NUMERO

    0  apagado      las rutas contestan 404 a todo el mundo. Nada en pantalla.
    1  laboratorio  el super administrador ve la pestaña «Núcleo» con datos
                    de prueba. Los clientes, nada.
    2  activo       reservado para cuando haya licencia. HOY SE COMPORTA
                    IGUAL QUE LABORATORIO, y un test lo sostiene: nadie puede
                    prender el núcleo de verdad cambiando un número.

    404 y no 403 en apagado, a propósito: un 403 dice «esto existe y no
    podés»; un 404 no dice nada. Mientras esté apagado, la arquitectura no se
    anuncia.
"""
from fastapi import HTTPException

CLAVE = "nucleo_modo"

APAGADO = 0
LABORATORIO = 1
ACTIVO = 2

NOMBRES = {APAGADO: "apagado", LABORATORIO: "laboratorio", ACTIVO: "activo"}


async def leer(db=None) -> int:
    """El modo vigente. Ante cualquier duda, APAGADO."""
    try:
        from services import configuracion
        if db is None:
            from database import db as real
            db = real
        valor = int(await configuracion.leer(db, CLAVE))
    except Exception:
        return APAGADO
    return valor if valor in NOMBRES else APAGADO


def se_puede_usar(modo: int) -> bool:
    """Si con este modo las rutas del núcleo contestan. ACTIVO no agrega
    nada sobre LABORATORIO todavía: ver el encabezado."""
    return modo in (LABORATORIO, ACTIVO)


async def exigir_encendido() -> int:
    """Dependencia de las rutas del núcleo. 404 si está apagado."""
    modo = await leer()
    if not se_puede_usar(modo):
        raise HTTPException(status_code=404, detail="Not Found")
    return modo
