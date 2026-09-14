"""
services/cpf.py — Qué es un CPF válido, y qué no.

POR QUE NO ALCANZA CON CONTAR ONCE DIGITOS

    El CPF lleva dos dígitos verificadores al final, calculados sobre los nueve
    primeros. O sea que de los cien mil millones de números de once cifras, sólo
    uno de cada cien es un CPF posible: la cuenta descarta el 99%.

    Hasta ahora la aplicación contaba once dígitos y nada más. Con eso,
    «12345678900» entra, y entra igual un teléfono tipeado en el campo
    equivocado. Y el CPF del pagador es lo que ata una recarga a la persona que
    la hizo: un número que no es de nadie no ata nada.

    El dedo que se equivoca en UN dígito es el caso que esto agarra siempre: al
    cambiar una cifra, la cuenta deja de dar. Es exactamente el error que más
    pasa y el que más caro sale, porque queda guardado y nadie lo mira hasta que
    hay que reclamar un pago.

LOS ONCE REPETIDOS SE RECHAZAN A PROPOSITO

    «11111111111», «00000000000» y los otros nueve pasan la cuenta de los
    verificadores —son un resultado legítimo de la fórmula— pero no existen como
    documento. Son los que aparecen cuando alguien quiere sacarse de encima un
    campo obligatorio, y el código de la aplicación ya usaba «00000000000» como
    valor por omisión para mandarle a Mercado Pago.

NO SE COMPRUEBA CONTRA LA RECEITA FEDERAL

    Esto dice que el número está bien formado, no que sea de quien lo escribe.
    Eso lo dice la foto del documento cuando se revisa el KYC, y es una decisión
    de una persona. Acá se corta lo que es imposible, que es barato y no falla
    nunca; lo otro necesita ojos.
"""
import re

# Los once dígitos repetidos. Se arma en vez de escribirse a mano porque la
# lista escrita a mano es la que termina con diez elementos y nadie lo nota.
_TODOS_IGUALES = {str(d) * 11 for d in range(10)}

_NO_DIGITO = re.compile(r"\D")


def normalizar(valor) -> str:
    """Los once dígitos, sin puntos ni guiones. Lo que se guarda y se compara.

    Se guarda normalizado y no como lo escribió la persona: «123.456.789-09» y
    «12345678909» son el mismo documento, y si se guardaran las dos formas la
    comparación de la recarga fallaría según cómo lo hubiera tipeado ese día.
    """
    return _NO_DIGITO.sub("", str(valor or ""))


def _digito(digitos: str, peso_inicial: int) -> str:
    """Un dígito verificador. La cuenta que define la Receita Federal."""
    suma = sum(int(d) * (peso_inicial - i) for i, d in enumerate(digitos))
    resto = (suma * 10) % 11
    # 10 y 11 valen cero. Es parte de la fórmula, no un caso borde nuestro.
    return "0" if resto >= 10 else str(resto)


def es_valido(valor) -> bool:
    """`True` si el número puede ser un CPF. No levanta: es para decidir."""
    n = normalizar(valor)
    if len(n) != 11 or n in _TODOS_IGUALES:
        return False
    return n[9] == _digito(n[:9], 10) and n[10] == _digito(n[:10], 11)


def para_mostrar(valor) -> str:
    """«123.456.789-09». Para la pantalla, nunca para guardar ni comparar."""
    n = normalizar(valor)
    if len(n) != 11:
        return n
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def tapado(valor) -> str:
    """«•••.456.789-••», para mostrarlo sin publicarlo entero.

    Se dejan los seis del medio: alcanzan para que la persona reconozca cuál de
    sus documentos es, y no alcanzan para que alguien que mira la pantalla por
    encima del hombro se lo lleve.
    """
    n = normalizar(valor)
    if len(n) != 11:
        return ""
    return f"•••.{n[3:6]}.{n[6:9]}-••"
