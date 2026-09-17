"""En qué estado está una cuenta, decidido en UN solo lugar.

EL PROBLEMA QUE RESUELVE

    El panel mostraba tres números de usuarios, y los tres contaban cosas
    distintas. Medido corriendo las rutas con once cuentas sembradas —una
    borrada, dos con el correo vetado—:

        GET /admin/users           -> 11   todo, borrados incluidos
        la tabla en pantalla       ->  9   escondía a los vetados
        la tarjeta «Usuarios»      -> 10   escondía a los borrados

    Nadie puede conciliar esos tres, porque ninguno dice cuál está midiendo.

    Lo peor no era el número: era que la tabla ESCONDIA a los vetados. Vetabas
    a alguien y desaparecía del panel. No lo veías, no le mirabas el saldo, no
    lo sacabas de la lista desde ahí. Y desde que el login también los frena,
    quedaba una cuenta sobre la que acabás de actuar y que ya no podés mirar.

COMO SE ARREGLA

    Cada cuenta tiene UN estado, y los estados son excluyentes entre sí: la
    suma de los grupos da el total, siempre. Eso es lo que hace que los
    números se puedan conciliar, que es todo el punto.

    El orden importa y es a propósito: una cuenta borrada que además estaba
    vetada cuenta como borrada. Se elige lo más definitivo primero, porque es
    lo que explica por qué esa persona no puede entrar.
"""
BORRADA = "borrada"
VETADA = "vetada"
SUSPENDIDA = "suspendida"
ACTIVA = "activa"

# De lo más definitivo a lo menos. El orden decide el estado cuando una cuenta
# cumple más de una condición, y es lo que mantiene los grupos excluyentes.
LOS_ESTADOS = (BORRADA, VETADA, SUSPENDIDA, ACTIVA)


def de(usuario: dict, vetados=frozenset()) -> str:
    """El estado de esta cuenta. Siempre devuelve uno de `LOS_ESTADOS`.

    `vetados` son los correos en lista negra, en minúsculas. Se pasan hechos
    en vez de consultarlos acá porque esta función se llama una vez por fila y
    la lista negra es una sola consulta para toda la pantalla.
    """
    if usuario.get("is_deleted"):
        return BORRADA
    # Dos formas de estar vetado, y las dos cuentan: el botón de banear del
    # panel escribe `is_banned` en la cuenta Y agrega el correo a la lista
    # negra, pero la lista negra también se edita a mano, y a mano se agrega
    # el correo sin tocar la cuenta.
    if usuario.get("is_banned"):
        return VETADA
    correo = str(usuario.get("email") or "").lower().strip()
    if correo and correo in vetados:
        return VETADA
    if usuario.get("status") == "suspended":
        return SUSPENDIDA
    return ACTIVA


async def los_correos_vetados(base) -> frozenset:
    """Los correos de la lista negra, en UNA consulta."""
    correos = set()
    async for fila in base.blacklist.find({"type": "email"}, {"_id": 0, "value": 1}):
        valor = str(fila.get("value") or "").lower().strip()
        if valor:
            correos.add(valor)
    return frozenset(correos)


async def resumen(base) -> dict:
    """Cuántas cuentas hay de cada estado. Los grupos suman el total.

    La base se recibe por parámetro y no se busca sola: `admin_routes.py` abre
    su propio cliente de Mongo, y los tests sustituyen el de cada módulo de
    ruta. Un ayudante con base propia contestaría desde otro lado.
    """
    vetados = await los_correos_vetados(base)
    cuenta = {estado: 0 for estado in LOS_ESTADOS}
    total = 0
    async for u in base.users.find(
            {}, {"_id": 0, "email": 1, "is_deleted": 1, "is_banned": 1, "status": 1}):
        total += 1
        cuenta[de(u, vetados)] += 1
    cuenta["total"] = total
    return cuenta
