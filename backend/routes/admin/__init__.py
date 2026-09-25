"""
routes/admin — Las rutas del panel de administración, en una parte por tema.

Antes eran un solo archivo, `routes/admin.py`, de más de 3.300 líneas. Se
dividió moviendo el código tal cual: las mismas rutas, con las mismas URLs,
los mismos métodos y la misma función detrás de cada una.

POR QUE ESTE ARCHIVO Y NO UN `admin.py` AL LADO DE LA CARPETA

    Python no deja tener las dos cosas. Con una carpeta `admin/` que tiene
    `__init__.py`, el `admin.py` de al lado se ignora; sin `__init__.py`, gana
    `admin.py` y las partes de la carpeta no se pueden importar. Este archivo
    ocupa el lugar que tenía `admin.py`: quien hace
    `from routes.admin import router` sigue recibiendo el panel entero, y ni
    `routes/__init__.py` ni `server.py` tuvieron que cambiar.

POR QUE NO VUELVE A EXPORTAR LAS FUNCIONES DE CADA PARTE

    Se podría, para que `routes.admin.process_withdrawal` siguiera existiendo.
    Pero un test que sustituye algo en `routes.admin` (un aviso, la base) no
    cambiaría nada en la parte donde el código vive ahora: seguiría en verde
    sin probar lo que dice. Sin la copia acá, ese test falla a la vista y se
    apunta a la parte correcta.

EL ORDEN DE LA LISTA IMPORTA

    FastAPI atiende cada pedido con la PRIMERA ruta que coincide, en el orden
    en que se registraron (ver `tests/test_rutas_alcanzables.py`). Al dividir,
    el orden cambió para las rutas que se juntaron por tema; se comprobó que
    ninguna URL cambió de dueño. Si se agrega una parte o se mueve una ruta,
    ese test es el que avisa si una tapa a otra.
"""
from fastapi import APIRouter

from routes.admin import (kyc, lotes, mantenimiento, pagos_incompletos,
                          pendientes, recargas_ves, reportes, retiros, soporte,
                          tasas, usuarios)

router = APIRouter()
for _parte in (mantenimiento, usuarios, retiros, recargas_ves, lotes,
               pagos_incompletos, reportes, tasas, kyc, soporte, pendientes):
    router.include_router(_parte.router)
