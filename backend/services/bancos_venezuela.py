"""
services/bancos_venezuela.py — La tabla de bancos, de este lado.

POR QUE EXISTE

    La lista de bancos venezolanos —código de cuatro dígitos y nombre— vivía
    SOLO en el frontend, escrita a mano dentro de `pages/Send.jsx` y repetida
    en otras cuatro pantallas. El servidor no la tenía.

    Mientras lo único que se hacía con ella era mostrarle un nombre a quien
    carga un beneficiario, daba igual. Deja de dar igual cuando el servidor
    tiene que AGRUPAR pagos por banco y escribir su nombre en un archivo que
    alguien va a pegar en la banca en línea: ahí el nombre es un dato
    operativo, no una etiqueta.

    Cinco copias de una lista son cinco listas que se van a separar. Ésta es la
    del servidor; las del navegador se pueden unificar después contra ella, y
    ese trabajo no es parte de este cambio.

COMO SE GUARDA UN BANCO EN UN BENEFICIARIO, QUE NO ES DE UNA SOLA FORMA

    El formulario de la aplicación guarda distinto según el método de pago:

      · Pago móvil  → `bank` = el CODIGO («0134»), porque es lo que pide el
        banco al momento de pagar.
      · Transferencia → `bank` = el NOMBRE y `bank_code` = el código.

    Y hay datos viejos donde falta uno de los dos. `codigo_de` mira los dos
    campos y también reconoce un nombre, para que un beneficiario cargado hace
    un año no quede afuera del archivo sin que nadie se entere.
"""
import re
import unicodedata

# Código de cuatro dígitos → nombre. La misma lista que usa el formulario, para
# que un beneficiario cargado en la aplicación siempre encuentre su banco.
BANCOS = {
    "0001": "Banco Central de Venezuela",
    "0102": "Banco de Venezuela",
    "0104": "Banco Venezolano de Crédito",
    "0105": "Banco Mercantil",
    "0108": "Banco Provincial",
    "0114": "Bancaribe",
    "0115": "Banco Exterior",
    "0128": "Banco Caroní",
    "0134": "Banesco",
    "0137": "Sofitasa",
    "0138": "Banco Plaza",
    "0145": "Banco de Comercio Exterior",
    "0146": "Banco de la Gente Emprendedora",
    "0151": "Fondo Común",
    "0152": "Bandes",
    "0156": "100% Banco",
    "0157": "DelSur Banco Universal",
    "0163": "Banco del Tesoro",
    "0166": "Banco Agrícola",
    "0168": "Bancrecer",
    "0169": "R4 Banco Microfinanciero",
    "0171": "Banco Activo",
    "0172": "Bancamiga",
    "0173": "Banco Internacional de Desarrollo",
    "0174": "Banplus",
    "0175": "Banco Digital de los Trabajadores",
    "0177": "Banco de las Fuerzas Armadas (BANFANB)",
    "0178": "N58 Banco Digital",
    "0191": "Banco Nacional de Crédito",
    "0601": "I.M.C.P",
    "0732": "Fonden",
    "2017": "ONT",
    "6000": "Banavih",
}


def _sin_adornos(texto: str) -> str:
    """Un nombre de banco comparable: sin acentos, sin puntuación, en una línea.

    Hace falta porque el mismo banco aparece escrito de varias formas según de
    dónde venga el dato: «Banesco», «BANESCO BANCO UNIVERSAL S.A.C.A.», «Banco
    Provincial» y «Provincial» son todos el mismo, y un `==` los separa.
    """
    plano = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z0-9 ]", " ", plano).upper().split())


# Nombre normalizado → código. Se arma una sola vez al importar.
_POR_NOMBRE = {_sin_adornos(nombre): codigo for codigo, nombre in BANCOS.items()}


def codigo_de(beneficiario) -> str:
    """El código de cuatro dígitos del banco de este beneficiario, o «».

    Mira `bank_code` y `bank`, en ese orden, y acepta que cualquiera de los dos
    traiga el código o el nombre. No adivina: si no reconoce nada devuelve
    vacío, y quien llama decide qué hacer con eso. Un banco adivinado mal es un
    pago que sale hacia otro lado.
    """
    if not isinstance(beneficiario, dict):
        return ""
    for campo in ("bank_code", "banco_codigo", "bank", "banco"):
        crudo = str(beneficiario.get(campo) or "").strip()
        if not crudo:
            continue
        digitos = re.sub(r"\D", "", crudo)
        if digitos in BANCOS:
            return digitos
        # Un nombre: «Banesco», «BANESCO BANCO UNIVERSAL S.A.C.A.»…
        plano = _sin_adornos(crudo)
        if plano in _POR_NOMBRE:
            return _POR_NOMBRE[plano]
        # …o un nombre que contiene al del catálogo. Se exige que el del
        # catálogo tenga al menos cinco letras para no emparejar por una
        # palabra suelta como «BANCO», que está en casi todos.
        for nombre, codigo in _POR_NOMBRE.items():
            if len(nombre) >= 5 and nombre in plano:
                return codigo
    return ""


def nombre_de(codigo: str) -> str:
    """El nombre del banco, o el código pelado si no está en la tabla.

    Nunca devuelve vacío: en el archivo que lee el operador, un encabezado sin
    nombre es peor que uno con un número — al menos el número se puede buscar.
    """
    limpio = re.sub(r"\D", "", str(codigo or ""))
    return BANCOS.get(limpio) or (limpio or "Banco sin identificar")
