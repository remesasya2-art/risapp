"""
services/servicios.py — Los servicios de RIS, cada uno con su llave.

QUE ES UN SERVICIO

    RIS ofrece tres cosas que se prenden y se apagan por separado: remesas,
    encomiendas y el banco. Cada una tiene sus clientes, sus datos y su propia
    gerencia en el panel, y su llave en Configuración. Lo que tienen en común
    —el personal, la auditoría, el respaldo, la configuración— es la
    «plataforma», que no se apaga. Ver docs/banco/README.md.

POR QUE ESTE CATALOGO, SI LAS LLAVES YA ESTABAN EN CONFIGURACION

    Las llaves estaban, pero sueltas entre treinta ajustes y escritas como
    números: «0 = en pausa, 1 = abierto». Para decidir qué servicio está
    prendido había que conocer la tabla de cada una. Esto las junta con
    nombre, con el nombre de cada estado y con lo que pasa en cada uno, para
    que la tarjeta «Servicios» del panel las muestre como lo que son.

    No es otro lugar donde se guarda nada. El valor sigue siendo el ajuste de
    siempre, se cambia por la misma ruta de Configuración (con su validación,
    sus seguros entre ajustes, los cuatro ojos del núcleo y el libro de
    auditoría) y lo sigue leyendo el módulo de cada llave. Acá sólo se le pone
    nombre.

CADA SERVICIO, CON LOS ESTADOS QUE DE VERDAD USA

    Remesas y encomiendas tienen dos. El banco tiene tres, porque ya los
    tenía (`nucleo/modo.py`): apagado, laboratorio y activo. Se evaluó darles
    tres a todos, con un «sólo gerencia» en el medio; no funcionaría en
    remesas ni en encomiendas, porque las cuentas del personal tienen
    prohibido mover plata y nadie podría probar nada en ese modo.
"""
from services import configuracion


class Estado:
    def __init__(self, valor: int, nombre: str, detalle: str):
        self.valor = valor
        self.nombre = nombre
        self.detalle = detalle


class Servicio:
    def __init__(self, clave: str, nombre: str, llave: str, descripcion: str,
                 estados: list):
        self.clave = clave
        self.nombre = nombre
        self.llave = llave
        self.descripcion = descripcion
        self.estados = estados


SERVICIOS = [
    Servicio(
        "remesas", "Remesas", "remesas_abiertas",
        "Gastar en Venezuela y en Brasil, cargar saldo y la vía cripto.",
        [Estado(0, "En pausa",
                "No nacen envíos nuevos y no se carga saldo; la cripto queda "
                "en sólo salida. Lo que ya está en curso termina y el panel "
                "sigue entero."),
         Estado(1, "Abierto", "Los clientes gastan en Venezuela y en Brasil.")]),
    Servicio(
        "encomiendas", "Encomiendas", "encomiendas_abiertas",
        "Mandar paquetes a Venezuela.",
        [Estado(0, "Suspendido",
                "No se cotizan ni se confirman encomiendas nuevas. Las que "
                "están en camino siguen su curso."),
         Estado(1, "Abierto", "Los clientes mandan paquetes.")]),
    Servicio(
        "banco", "Banco", "nucleo_modo",
        "Cuentas de pago, PIX, tarjetas, boletos y TED, con su propia base y "
        "sus propios clientes.",
        [Estado(0, "Apagado", "No existe: ni rutas ni sección en el panel."),
         Estado(1, "Laboratorio",
                "Sólo el super administrador lo ve, con plata de prueba. Los "
                "clientes no ven nada."),
         Estado(2, "Activo",
                "Reservado para cuando haya licencia o socio. Hoy hace lo "
                "mismo que el laboratorio.")]),
]

POR_CLAVE = {s.clave: s for s in SERVICIOS}


def _nombre_del_estado(servicio: Servicio, valor: int) -> str:
    for e in servicio.estados:
        if e.valor == valor:
            return e.nombre
    return str(valor)


async def estado_de_todos(db) -> list:
    """Cada servicio con su estado de ahora. Una sola lectura de la base.

    `encendido` es lo que mira el menú del panel para marcar «apagado»: el
    valor 0 de cada llave. El laboratorio del banco cuenta como encendido,
    porque la gerencia lo usa.
    """
    ajustes = await configuracion.leer_todo(db)
    salida = []
    for s in SERVICIOS:
        valor = int(ajustes[s.llave])
        salida.append({
            "servicio": s.clave,
            "nombre": s.nombre,
            "descripcion": s.descripcion,
            "llave": s.llave,
            "valor": valor,
            "estado": _nombre_del_estado(s, valor),
            "encendido": valor > 0,
            "estados": [{"valor": e.valor, "nombre": e.nombre, "detalle": e.detalle}
                        for e in s.estados],
        })
    return salida
