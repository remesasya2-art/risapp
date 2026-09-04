"""
Qué se puede escribir en un registro, y qué no.

POR QUE ESTO IMPORTA MAS DE LO QUE PARECE

    Un registro no es un archivo privado. Los de esta aplicación los ve
    cualquiera que entre al panel del proveedor de hosting, se copian a
    servicios de terceros para poder buscarlos, se guardan mucho más tiempo que
    los datos que describen, y sobreviven a cualquier borrado que hagamos en la
    base.

    O sea: todo lo que se escribe acá sale del perímetro que sí controlamos, y
    ya no vuelve.

    Y esta aplicación mueve remesas de venezolanos en Brasil. Un volcado de
    registros con correos, teléfonos y documentos no es «una filtración de
    datos»: es una lista de personas de una comunidad concreta, con cuánto
    manda cada una y a quién. Eso vale para quien quiera extorsionar, y vale
    para quien quiera perseguir.

QUE HABIA

    Treinta y cinco puntos que interpolaban datos personales o cuerpos enteros
    de pedidos de terceros. Los peores eran los que volcaban un `payload`
    completo —lo que manda el proveedor de pagos, sin acotar— y el que, cuando
    el libro de auditoría fallaba, escribía LA LINEA ENTERA en el registro:
    justo el dato más sensible del sistema, mandado al lugar menos protegido.

EL CRITERIO

    1. Donde se pueda, se registra el `user_id` y no el correo. El `user_id` no
       dice nada fuera de nuestra base; el correo identifica a una persona en
       cualquier lado.
    2. Donde el correo haga falta de verdad —cuando todavía no sabemos qué
       usuario es— se enmascara. `ju***@gmail.com` alcanza para que alguien de
       soporte reconozca a quien tiene enfrente, y no alcanza para armar una
       lista.
    3. De un cuerpo ajeno se registran las claves que se eligieron a mano, no
       lo que venga. Un `payload` completo hoy trae tres campos y mañana veinte.

LO QUE ESTO NO ES

    No es cifrado ni control de acceso a los registros. Es reducir lo que hay
    adentro para que, el día que alguien los lea sin permiso, encuentre lo menos
    posible.
"""
import re

_CORREO = re.compile(r"^([^@]+)@(.+)$")


def correo(valor) -> str:
    """De `nombre.apellido` arroba un dominio, quedan dos letras: `no***@`.

    Se conserva el dominio: sirve para reconocer un problema de entrega de
    correo, que es la razón real por la que esto se registra, y no identifica a
    nadie por sí solo.
    """
    texto = str(valor or "").strip()
    if not texto:
        return "(sin correo)"
    m = _CORREO.match(texto)
    if not m:
        return "(correo ilegible)"
    nombre, dominio = m.group(1), m.group(2)
    visible = nombre[:2] if len(nombre) > 2 else nombre[:1]
    return f"{visible}***@{dominio}"


def ultimos(valor, cuantos: int = 4) -> str:
    """Los últimos dígitos de un teléfono, un documento o una cuenta.

    Alcanza para cotejar contra lo que la persona dice por teléfono, y no
    alcanza para encontrarla.
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos:
        return "(vacío)"
    return f"...{digitos[-cuantos:]}" if len(digitos) > cuantos else "..."


# Las claves que nunca se copian a un registro, mire quien mire. Se comparan
# por «contiene», para que `id_document_image_back` caiga igual que
# `id_document_image`.
PROHIBIDAS = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "auth",
    "credential", "signature", "hash", "otp", "cvv", "card_number",
    "image", "selfie", "foto", "comprobante", "proof", "voucher",
    "cpf", "document_number", "cedula", "id_document",
    "phone", "telefono", "celular", "email", "correo",
    "full_name", "nombre", "name", "beneficiar", "address", "direccion",
)


def resumen(datos, claves, *, tope: int = 400) -> str:
    """De un cuerpo ajeno, sólo las claves que se pidieron.

    Se usa para los webhooks. Un `logger.info(f"webhook: {payload}")` escribe lo
    que el proveedor mande, hoy y siempre: hoy son tres campos inocuos y el día
    que agreguen el nombre del pagador pasa a estar en el registro sin que nadie
    haya decidido nada.

    Pedir las claves a mano invierte eso: lo nuevo no entra hasta que alguien lo
    agregue acá a propósito.
    """
    if not isinstance(datos, dict):
        return f"({type(datos).__name__})"
    partes = []
    for clave in claves:
        if clave not in datos:
            continue
        valor = datos[clave]
        if isinstance(valor, (dict, list)):
            valor = f"({type(valor).__name__})"
        partes.append(f"{clave}={str(valor)[:60]}")
    texto = " ".join(partes) if partes else "(sin campos conocidos)"
    return texto[:tope]


def sin_datos(datos, *, profundidad: int = 4):
    """La misma estructura, con los valores sensibles tapados.

    Para el caso en que hace falta registrar un documento entero porque algo
    falló y no se sabe qué —el libro de auditoría, sobre todo—. Se conserva la
    FORMA, que es lo que sirve para entender el error, y se tapa el contenido,
    que es lo que no tiene por qué salir de la base.
    """
    if profundidad <= 0:
        return "(...)"
    if isinstance(datos, dict):
        limpio = {}
        for clave, valor in datos.items():
            if any(p in str(clave).lower() for p in PROHIBIDAS):
                limpio[clave] = "(tapado)"
            else:
                limpio[clave] = sin_datos(valor, profundidad=profundidad - 1)
        return limpio
    if isinstance(datos, (list, tuple)):
        return [sin_datos(v, profundidad=profundidad - 1) for v in datos[:10]]
    if isinstance(datos, str) and len(datos) > 120:
        return datos[:120] + f"…(+{len(datos) - 120})"
    return datos
