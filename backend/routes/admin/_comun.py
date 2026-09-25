"""
routes/admin/_comun.py — Lo que usan varias partes del panel a la vez.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
import logging

# El nombre del registro es el que tenía cuando todo vivía en `routes/admin.py`.
# Con `__name__`, cada parte anotaría con un nombre propio
# (`routes.admin.retiros`, `routes.admin.kyc`...) y cualquier filtro o búsqueda
# de los registros por `routes.admin` dejaría de encontrar esas líneas sin que
# nada avise.
logger = logging.getLogger("routes.admin")
# ─── El tope de las colas de trabajo ───────────────────────────────────────
#
# Dos bandejas —retiros pendientes y diferencias de pago— traían TODAS las
# filas, sin tope. No las acota el historial sino el trabajo sin procesar, así
# que mientras el equipo esté al día son chicas y nadie lo nota. El día que se
# atrase, la pantalla tarda proporcionalmente y no avisa antes de hacerlo.
#
# Mil es alto a propósito: una bandeja que de verdad tenga mil pendientes ya
# es un problema de operación, y recortarla a cien escondería ese problema
# justo en la pantalla donde hay que verlo.
TOPE_DE_UNA_COLA = 1000
