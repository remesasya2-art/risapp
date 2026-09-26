"""
services/configuracion_ajuste.py — Qué es un ajuste de Configuración.

Vivía al principio de `services/configuracion.py`. Se movió tal cual cuando
ese archivo llegó a su tope de 800 líneas y las llaves de los servicios
pasaron a `services/configuracion_servicios.py`: los dos archivos necesitan
esta clase, y si viviera en configuracion.py se importarían el uno al otro.
`configuracion.py` la vuelve a exportar, así que quien la usaba por ahí sigue
igual.
"""

# Los dos tipos que hay. No hace falta un tercero todavía, y un tipo que no se
# usa es una rama sin probar.
DINERO = "dinero"
ENTERO = "entero"


class Ajuste:
    """Un número configurable, con todo lo que hace falta para validarlo y
    para dibujarlo en la pantalla.

    `minimo` y `maximo` no son adorno. El bono se paga solo, a cada cuenta que
    se registra: un cero de más al tipear —1500 en vez de 150— es plata que
    sale sin que nadie lo apruebe. El tope es la red.
    """

    def __init__(self, *, tipo, defecto, minimo, maximo, etiqueta, ayuda,
                 unidad=""):
        self.tipo = tipo
        self.defecto = defecto
        self.minimo = minimo
        self.maximo = maximo
        self.etiqueta = etiqueta
        self.ayuda = ayuda
        self.unidad = unidad
