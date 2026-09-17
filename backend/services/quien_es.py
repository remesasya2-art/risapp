"""Quién es el cliente de cada fila del panel.

EL PROBLEMA QUE RESUELVE

    Las listas del panel muestran transacciones, y la transacción guarda el
    `user_id`, no el nombre. Para poner «Ana Ribeiro» al lado de la fila hay
    que ir a buscar el usuario. Eso se hacía FILA POR FILA: una ida y vuelta
    a la base por cada renglón de la pantalla.

    Medido sobre el código: diez pantallas hacían 1 + N consultas. Las
    recargas pendientes traen hasta mil filas, o sea hasta mil consultas para
    pintar una tabla. Y cinco de esas pantallas pedían el usuario ENTERO
    —con el hash de la contraseña, la semilla del segundo factor, las
    credenciales de la huella y la suscripción de avisos adentro— para leerle
    el nombre y el correo.

    Tres pantallas más se habían escrito su propio diccionario de caché, las
    tres iguales y las tres sin proyección. Que el mismo apaño esté copiado
    tres veces es la señal de que faltaba este archivo.

LO QUE NO ES

    Esto no es «el panel está lento». Con los usuarios que hay hoy, N es
    chico y nadie nota la diferencia. Lo que arregla de verdad y ahora es la
    lista de lo permitido: que el hash de la contraseña de un cliente no
    viaje por la red ni quede en memoria del proceso para mostrar su nombre.
    Lo otro es la forma, que deja de empeorar sola cuando la app crezca.

POR QUE NO VIVE EN `perfil.py`

    Ahí están las otras dos listas de lo permitido, y sería el lugar obvio.
    Pero `perfil.py` hoy no toca la base: no importa `database`, y lo importan
    casi todas las rutas. Meterle una consulta le agrega esa dependencia a
    todas ellas. La lista de acá es otra cosa además: no es «el perfil de
    alguien», es «el nombre que va al lado de una fila».
"""


# ─── Lo que muestra UNA FILA ───────────────────────────────────────────────
#
# Lista de lo PERMITIDO, no de lo prohibido. Una lista de lo prohibido deja
# pasar cada campo nuevo del usuario hasta que alguien se acuerde de
# agregarlo, y acá el campo nuevo que se cuele viaja por la red en cada
# renglón de cada tabla del panel.
#
# Son los cinco campos que las pantallas leen de verdad; salieron de recorrer
# los diez lugares y anotar qué le piden al usuario. `full_name` y `name`
# están los dos porque las pantallas no coinciden: unas muestran `name` a
# secas y otras prefieren `full_name` si lo hay. Unificarlas cambiaría lo que
# se ve en pantalla, y eso es otra decisión, no ésta.
LO_QUE_MUESTRA_UNA_FILA = {
    "_id": 0,
    "user_id": 1,
    "name": 1,
    "full_name": 1,
    "email": 1,
    "display_id": 1,
}


class Directorio:
    """Los clientes de una pantalla, sin preguntar dos veces por el mismo.

    LA BASE SE LE PASA, NO LA BUSCA SOLO

        La primera versión hacía `from database import db` acá adentro. Un
        test del reporte de mermas se puso rojo y tenía razón: ese test
        sustituye `db` en el módulo de la ruta, y el ayudante seguía hablando
        con otra base. En producción las dos apuntan al mismo Mongo y no se
        nota; en los tests y en la vista previa, no.

        Y hay un caso donde tampoco se notaría por casualidad:
        `admin_routes.py` abre SU PROPIO cliente de Mongo, distinto del de
        `database.py`. Un ayudante con base propia le contestaría desde otro
        lado.

        Por eso la recibe. Cada pantalla le pasa el mismo `db` que usa para
        todo lo demás, y no hay dos verdades posibles.

    Se usa de dos formas, según cómo venga la lista:

      - Si las filas ya están en memoria, `de_las_filas()` las precarga en UNA
        consulta y después `ya_conocido(uid)` no toca la base.
      - Si las filas llegan de a una (varios cursores, por ejemplo), `de(uid)`
        consulta la primera vez que ve a cada uno y después se acuerda.

    La segunda forma sigue siendo una consulta por cliente DISTINTO, no por
    fila. Es lo que ya hacían a mano las tres pantallas que traían su propio
    diccionario; lo que suman al usar esto es la proyección.
    """

    def __init__(self, base):
        self._base = base
        self._vistos: dict[str, dict] = {}

    async def precargar(self, ids) -> None:
        """Una sola consulta para todos los que todavía no conoce."""
        faltan = {i for i in ids if i and i not in self._vistos}
        if not faltan:
            return
        cursor = self._base.users.find({"user_id": {"$in": list(faltan)}},
                                       LO_QUE_MUESTRA_UNA_FILA)
        async for u in cursor:
            self._vistos[u["user_id"]] = u
        # Los que la consulta no trajo se anotan igual, en blanco. Sin esto,
        # una fila cuyo usuario se borró hace que `precargar` lo busque de
        # nuevo en cada llamada, que es justo lo que este archivo evita.
        for i in faltan:
            self._vistos.setdefault(i, {})

    def ya_conocido(self, uid) -> dict:
        """Lo que ya se cargó. Devuelve {} si no está: nunca consulta."""
        return self._vistos.get(uid) or {}

    async def de(self, uid) -> dict:
        """Uno solo, consultando la primera vez que lo ve."""
        if not uid:
            return {}
        if uid not in self._vistos:
            await self.precargar([uid])
        return self._vistos.get(uid) or {}


async def de_las_filas(base, filas, campo: str = "user_id") -> Directorio:
    """El directorio de esas filas, ya cargado. UNA consulta."""
    d = Directorio(base)
    await d.precargar(f.get(campo) for f in filas)
    return d
