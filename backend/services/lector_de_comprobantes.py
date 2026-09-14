"""
services/lector_de_comprobantes.py — Qué dice la foto de un comprobante.

PARA QUE SIRVE Y PARA QUE NO

    Sirve para ADJUDICAR: decir cuál de las órdenes del lote corresponde a
    esta captura. No sirve —y no se usa— para decidir si un pago está bien
    hecho. Eso lo decide una persona mirando la foto.

    La diferencia importa. Un lector que se equivoca adjudicando le pone la
    foto equivocada a una orden: molesto, visible, y se arregla con un clic.
    Un lector que se equivoca APROBANDO acredita plata que no se pagó.

POR QUE NO SE DEVUELVE «EL MONTO» SINO TODOS LOS MONTOS

    Un comprobante tiene varios números con forma de monto: el que se
    transfirió, la comisión, el saldo que queda, a veces el límite diario.
    Elegir «el primero» es elegir al azar.

    Así que se devuelven TODOS, y quien adjudica pregunta otra cosa: «¿está
    el monto de esta orden entre los que aparecen en la foto?». Esa pregunta
    sí tiene una respuesta correcta, y no depende de en qué renglón lo puso
    el banco.

    Vale igual para las cuentas, los teléfonos y las cédulas.

POR QUE SE LEE TRES VECES CADA IMAGEN

    Tesseract está entrenado sobre texto negro en papel blanco. Un
    comprobante en modo oscuro, sin invertir, no se lee: sale vacío.

    Y hay un caso peor, que es el que obligó a esto: el comprobante de pago
    móvil del BDV pone el monto en texto BLANCO adentro de un recuadro GRIS,
    sobre fondo NEGRO. Invertir la imagen entera lo deja en negro sobre gris,
    que tiene tan poco contraste como antes. El umbral local —preguntar si
    cada punto es más claro o más oscuro que el promedio de SU vecindario, en
    vez de compararlo contra un número fijo para toda la imagen— lo saca
    limpio, porque no le importa si el vecindario es blanco, gris o negro.

    Se pasa TRES veces: la imagen derecha, la capa de lo que es más oscuro
    que su vecindario, y la capa de lo que es más claro. Y son dos capas
    separadas, no una sola con las dos cosas: juntarlas fue el primer intento
    y no leyó absolutamente nada, porque alrededor de una letra clara el
    fondo es más oscuro que el promedio, así que la letra sale marcada Y su
    contorno también, y las letras quedan huecas. Tesseract no lee letras
    huecas: devuelve la página vacía.

    Lo que sale de las tres pasadas se junta. Juntar es seguro porque acá no
    se elige nada: se recolectan candidatos que después tienen que COINCIDIR
    con un dato de la orden. Un número de más que no coincide con nada no
    hace daño; un número de menos deja una foto sin adjudicar.

SI NO HAY LECTOR, NO SE ROMPE NADA

    `tesseract` es un programa del sistema, no una librería de Python: puede
    no estar instalado en el servidor. Si falta, esto devuelve vacío y lo
    dice, y la pantalla pasa a adjudicación manual — que es exactamente lo
    que se hacía antes de esto. Nunca levanta.
"""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Cuánto se agranda antes de leer. Las tipografías finas de los comprobantes
# de teléfono se leen mal a tamaño original y bien al doble.
AGRANDAR = 2

# El radio del vecindario del umbral local, en puntos de la imagen ya
# agrandada. Tiene que ser holgadamente mayor que el grosor de un trazo: si
# fuera parecido, el promedio del vecindario de una letra gruesa sería la
# letra misma y su interior no se marcaría. Probado de 15 a 40 sobre los
# cuatro formatos de comprobante, con el mismo resultado en todo el rango.
VECINDARIO = 25

# Cuánto tiene que destacar un punto sobre su vecindario para contar como
# tinta. Bajo deja pasar el ruido del JPEG; alto se come las letras finas.
DESTAQUE = 10

# Los idiomas que se le piden a tesseract. El español trae las palabras de los
# comprobantes («Referencia», «Cédula»); el inglés está porque varios bancos
# mezclan («Amount», «Date») y porque si el paquete de español no estuviera
# instalado, con el inglés solo los NUMEROS igual salen.
IDIOMAS = "spa+eng"

# Cuánto se le da a `tesseract` para una pasada antes de matarlo. Una captura
# de teléfono se lee en menos de tres segundos; lo que tarde treinta no va a
# terminar, y mientras tanto tiene un procesador tomado.
SEGUNDOS_POR_FOTO = 30

# Una cuenta venezolana son 20 dígitos. Se escriben de corrido, en grupos de
# cuatro, o con guiones: se sacan los separadores antes de buscar.
_CUENTA = re.compile(r"\d{20}")
# Un teléfono venezolano: 0 + código de operadora + 7 dígitos.
_TELEFONO = re.compile(r"0(?:412|414|416|424|426)\d{7}")
# Una cédula, con o sin la letra adelante. Seis a nueve dígitos: por debajo de
# seis es cualquier número suelto de la pantalla.
_CEDULA = re.compile(r"\b[VEJGP]?-?\s?(\d{6,9})\b")
# Un monto con separador de miles y dos decimales, como lo escribe la banca
# venezolana: 1.234,56. Los enteros sin decimales quedan afuera a propósito:
# cualquier número de referencia los imita.
_MONTO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
# La referencia de la operación. Nueve o más dígitos seguidos.
_REFERENCIA = re.compile(r"\d{9,13}")

# Los separadores que la gente y los bancos meten adentro de un número.
_SEPARADORES = re.compile(r"[\s\-.·•]")


class SinLector(RuntimeError):
    """No hay `tesseract` en esta máquina. Lo maneja quien llama, no el usuario."""


def _sin_separadores(texto: str) -> str:
    return _SEPARADORES.sub("", texto or "")


def solo_digitos(valor) -> str:
    """Los dígitos de un valor, sin nada más. Para comparar dos escrituras."""
    return "".join(c for c in str(valor or "") if c.isdigit())


def sin_adornos(texto) -> str:
    """MAYUSCULAS, sin tildes y sin puntuación. Para comparar nombres.

    El OCR devuelve «MUNOZ» donde el panel guarda «MUÑOZ», y al revés según
    la foto. Comparar sin adornos es la única forma de que coincidan.
    """
    crudo = unicodedata.normalize("NFKD", str(texto or ""))
    sin_tildes = "".join(c for c in crudo if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9 ]", " ", sin_tildes.upper())


# Dónde buscar el programa cuando no está en el PATH del proceso.
#
# POR QUE HACE FALTA BUSCARLO
#
#     `tesseract` se instala desde la configuración del despliegue, y dónde
#     aterriza depende de cómo se construyó la imagen: `apt` lo deja en
#     /usr/bin, `nix` en /nix/store con un enlace que no siempre queda en el
#     PATH del proceso que sirve la aplicación. Instalado y no encontrado se
#     ve exactamente igual que no instalado, y la primera vez costó una vuelta
#     entera de despliegue no poder distinguirlos.
#
# LA VARIABLE VA PRIMERO, Y ES LA SALIDA SIN TOCAR CODIGO
#
#     Si mañana aterriza en un lugar que esta lista no tiene, se pone
#     `TESSERACT_CMD` en el panel del servidor y anda. Acá configurar nunca
#     puede exigir editar código y volver a desplegar.
VARIABLE_DEL_PROGRAMA = "TESSERACT_CMD"

DONDE_SUELE_ESTAR = (
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
)


def _donde_esta_el_programa() -> str:
    """La ruta del programa: la de la variable, la del PATH, o la que se
    encuentre en los lugares de siempre. Vacío si no hay ninguna."""
    import os
    import shutil

    puesta = (os.environ.get(VARIABLE_DEL_PROGRAMA) or "").strip()
    if puesta:
        return puesta
    encontrado = shutil.which("tesseract")
    if encontrado:
        return encontrado
    for ruta in DONDE_SUELE_ESTAR:
        if os.path.isfile(ruta) and os.access(ruta, os.X_OK):
            return ruta
    return ""


def _apuntar_a_donde_este():
    """Le dice a pytesseract dónde está el programa, si hizo falta buscarlo."""
    import pytesseract

    ruta = _donde_esta_el_programa()
    if ruta:
        pytesseract.pytesseract.tesseract_cmd = ruta
    return ruta


def por_que_no_hay_lector() -> str:
    """Vacío si el lector anda; si no, POR QUE no anda, en una línea.

    LA DIFERENCIA CON UN BOOLEANO, Y POR QUE VALE LA PENA

        Antes esto era un sí/no, y la pantalla decía «el servidor no tiene el
        lector instalado» pasara lo que pasara. La primera vez que falló de
        verdad, ese mensaje era una conjetura: podía ser que el programa no
        estuviera, que estuviera en otro lado, o que faltara el idioma. Sin
        saber cuál, arreglarlo son vueltas de despliegue a ciegas.

        El motivo lo lee un super administrador en su panel, no un cliente.
    """
    try:
        import pytesseract
    except Exception as e:
        return (f"Falta la librería pytesseract en el servidor ({e}). "
                "Tiene que estar en backend/requirements.txt.")

    ruta = _apuntar_a_donde_este()
    if not ruta:
        return ("No se encuentra el programa «tesseract» en el servidor. "
                f"Instalalo en el despliegue, o poné la variable "
                f"{VARIABLE_DEL_PROGRAMA} con su ruta.")

    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        return f"El programa está en {ruta} pero no se pudo ejecutar: {e}"

    return ""


def idiomas_instalados() -> list:
    """Los idiomas que tiene el lector. Vacío si no se pudo preguntar.

    Sirve para distinguir «no hay lector» de «hay lector pero le falta el
    español», que se arreglan de formas distintas y que sin esto se ven igual.
    """
    try:
        import pytesseract
        _apuntar_a_donde_este()
        return sorted(pytesseract.get_languages(config=""))
    except Exception as e:
        logger.info("lector_de_comprobantes: no se pudieron listar los idiomas (%s)", e)
        return []


def hay_lector() -> bool:
    """¿Se puede leer una foto en este servidor? No levanta nunca."""
    motivo = por_que_no_hay_lector()
    if motivo:
        logger.info("lector_de_comprobantes: sin lector — %s", motivo)
        return False
    return True


def _derecha(imagen):
    """La imagen en gris y agrandada. Sirve para casi todos los comprobantes."""
    return imagen.resize((imagen.width * AGRANDAR, imagen.height * AGRANDAR))


def _capas_de_umbral_local(grande):
    """Dos imágenes en blanco y negro: la tinta oscura y la tinta clara.

    DOS, SEPARADAS, Y NO UNA CON LAS DOS COSAS

        Juntarlas fue el primer intento y tesseract devolvió la página VACIA.
        El motivo se ve mirando el resultado: alrededor de una letra clara el
        fondo queda más oscuro que el promedio del vecindario, así que se
        marca la letra Y su contorno, y las letras salen huecas. Un contorno
        no es una letra para un lector entrenado sobre trazos llenos.

        Separadas, cada capa es lo que tesseract espera: trazos llenos,
        negros, sobre blanco. Una de las dos sale casi en blanco y no aporta
        nada, que no cuesta nada; la otra trae el renglón que faltaba.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    punto = np.asarray(grande, dtype=np.int16)
    vecindario = np.asarray(grande.filter(ImageFilter.BoxBlur(VECINDARIO)),
                            dtype=np.int16)
    oscura = np.where(punto < vecindario - DESTAQUE, 0, 255).astype(np.uint8)
    clara = np.where(punto > vecindario + DESTAQUE, 0, 255).astype(np.uint8)
    return Image.fromarray(oscura), Image.fromarray(clara)


def _un_solo_hilo_por_lectura():
    """UN HILO POR LECTURA, Y NO ES UN DETALLE DE AFINACION.

    `tesseract` viene con OpenMP y por omisión abre tantos hilos como
    procesadores tenga la máquina. Leyendo varias fotos a la vez eso se
    multiplica: cuatro lecturas en paralelo en un servidor de cuatro
    procesadores son dieciséis hilos peleando por cuatro.

    Lo que pasó al probarlo así fue peor que «lento»: la carga del servidor se
    fue a 35, ninguna lectura terminaba, y los `tesseract` seguían dando
    vueltas después de que el pedido se cortara por tiempo — o sea que el
    servidor quedaba inservible para todo lo demás, no sólo para esto.

    Con un hilo cada una tarda prácticamente lo mismo —una página sola no se
    paraleliza bien— y el paralelismo se decide arriba, donde se sabe cuántas
    fotos hay. Se pone en el ambiente porque es la única perilla que
    `tesseract` ofrece para esto: no hay parámetro de línea de comandos.
    """
    import os
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")


def _texto_de(imagen, idiomas: str) -> str:
    import pytesseract
    _un_solo_hilo_por_lectura()
    # Si el programa no está en el PATH, acá se le dice dónde está. Sin esto,
    # `hay_lector()` podría decir que sí —porque buscó— y la lectura fallar.
    _apuntar_a_donde_este()
    try:
        # El corte por tiempo mata el proceso. Sin él, una foto que `tesseract`
        # no puede digerir deja un proceso comiendo un procesador para siempre,
        # y el siguiente pedido encuentra el servidor más lento todavía.
        return pytesseract.image_to_string(
            imagen, lang=idiomas, timeout=SEGUNDOS_POR_FOTO)
    except Exception as e:
        # Si falta el paquete de español, tesseract no lee NADA en vez de leer
        # sin él. Los números no dependen del idioma, así que se reintenta con
        # el inglés antes de darse por vencido.
        if idiomas != "eng":
            logger.info("lector_de_comprobantes: %s falló, se reintenta con eng: %s",
                        idiomas, e)
            return _texto_de(imagen, "eng")
        raise


def texto_de_la_imagen(datos: bytes) -> str:
    """Todo lo que se pudo leer de la foto, de las dos pasadas, junto.

    Levanta `SinLector` si no hay tesseract. Cualquier otra falla también
    levanta: quien llama decide qué hacer, porque «no se pudo leer esta foto»
    y «no hay lector en el servidor» se le cuentan distinto al operador.
    """
    import io

    from PIL import Image

    motivo = por_que_no_hay_lector()
    if motivo:
        raise SinLector(motivo)

    with Image.open(io.BytesIO(datos)) as abierta:
        grande = _derecha(abierta.convert("L"))
        pasadas = (grande,) + _capas_de_umbral_local(grande)
        partes = [_texto_de(p, IDIOMAS) for p in pasadas]
    return "\n".join(partes)


def senales_del_texto(texto: str) -> dict:
    """Los candidatos que hay en el texto. Todos, sin elegir ninguno.

    Se devuelven listas porque un comprobante tiene varios montos y a veces
    varias cuentas, y acá no hay forma de saber cuál es «el» que importa. El
    que importa lo decide la orden contra la que se compara.
    """
    plano = _sin_separadores(texto)
    return {
        "cuentas": sorted(set(_CUENTA.findall(plano))),
        "telefonos": sorted(set(_TELEFONO.findall(plano))),
        "cedulas": sorted(set(_CEDULA.findall(texto))),
        "montos": sorted(set(_MONTO.findall(texto))),
        "referencias": sorted(set(_REFERENCIA.findall(plano))),
        "texto": sin_adornos(texto),
    }


def vacio() -> dict:
    """Lo que devuelve una foto que no se pudo leer. Misma forma, sin datos."""
    return {"cuentas": [], "telefonos": [], "cedulas": [], "montos": [],
            "referencias": [], "texto": ""}


def leer(datos: bytes) -> dict:
    """Las señales de una foto. Levanta `SinLector`; el resto lo absorbe.

    Una foto rota, girada o ilegible devuelve vacío: es una foto sin
    adjudicar, que el operador resuelve a mano. Que UNA foto no se lea no
    puede voltear la carga entera.
    """
    try:
        return senales_del_texto(texto_de_la_imagen(datos))
    except SinLector:
        raise
    except Exception as e:
        logger.warning("lector_de_comprobantes: no se pudo leer una foto: %s", e)
        return vacio()
