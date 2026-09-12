"""
services/codigos.py — Los códigos de un solo uso que se mandan por correo.

POR QUE UN MODULO Y NO UNA LINEA EN CADA LADO

    Había dos formas de generar un código en el proyecto, y la que estaba en el
    lugar más delicado era la mala:

        routes/auth.py       secrets.randbelow(10)    — bien
        routes/recovery.py   random.randint(...)      — MAL

    `random` es un generador PREDECIBLE. No es un defecto de estilo: está
    hecho para simulaciones, arranca desde una semilla, y quien vea unos
    cuantos valores puede calcular los que siguen. En el código que deja
    cambiar la contraseña de una cuenta, eso es la puerta.

    `secrets` usa la fuente de azar del sistema operativo, la misma que usan
    las llaves. Es la única que sirve acá.

EL ALFABETO NO TIENE NI CEROS NI LETRA O

    El código se lee de un correo y se tipea a mano, muchas veces desde un
    teléfono. Un cero y una O mayúscula se ven casi iguales en casi todas las
    tipografías, y lo mismo pasa con el uno, la I y la L.

    Quien se equivoca gasta un intento de los que tiene, y con tres intentos
    eso significa volver a empezar por culpa de la tipografía. Se sacan esos
    cinco caracteres y el problema no existe.

    Quedan 31 símbolos. Con ocho posiciones son unas 850 mil millones de
    combinaciones: adivinarlo no es un camino, y el tope de intentos cierra el
    que quedaba.
"""
import hmac
import secrets

# Sin 0, O, 1, I ni L. Ver el encabezado.
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

LARGO = 8


def nuevo(largo: int = LARGO) -> str:
    """Un código nuevo, con la fuente de azar del sistema."""
    return "".join(secrets.choice(ALFABETO) for _ in range(largo))


def normalizar(escrito: str) -> str:
    """Lo que la persona tipeó, listo para comparar.

    Se aceptan las minúsculas y los espacios que agrega quien copia y pega
    desde el correo. Rechazar un código por una minúscula sería gastarle un
    intento a alguien que lo escribió bien.
    """
    return "".join((escrito or "").split()).upper()


def coincide(escrito: str, guardado: str) -> bool:
    """¿Es este el código? Se compara SIN ATAJOS.

    `hmac.compare_digest` tarda lo mismo acierte o no. Un `==` común corta en
    la primera letra distinta, y esa diferencia de tiempo —medible, aunque sea
    de microsegundos— deja adivinar el código letra por letra en vez de entero.
    """
    if not guardado:
        return False
    return hmac.compare_digest(normalizar(escrito), normalizar(guardado))
