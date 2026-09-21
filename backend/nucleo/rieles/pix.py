"""
Las formas del PIX, como las define el Banco Central.

    Sin base de datos y sin red: sólo los datos y las reglas de formato. Es
    lo que cualquier riel real va a tener que producir y entender, así que
    está escrito una vez, acá, y probado solo.

LAS PIEZAS

    Clave        CPF, CNPJ, correo, teléfono o clave aleatoria (EVP). Se
                 detecta el tipo por la forma y se valida (el CPF con sus
                 dígitos verificadores).
    EndToEndId   el identificador punta a punta del SPI: «E» + ISPB del PSP
                 que origina (8 dígitos) + año-mes-día-hora-minuto + 11
                 caracteres. Es el que se cita en cualquier disputa.
    txid         el identificador de un cobro, de 26 a 35 caracteres, el
                 que va dentro del BR Code.
    BR Code      el texto del QR PIX, según el Manual de Padrões para
                 Iniciação do Pix (formato EMV MPM, con CRC-16 al final).
    Mensajes     las que viajan por el SPI en ISO 20022: la orden de pago
                 (pacs.008), la respuesta de estado (pacs.002) con sus
                 códigos de rechazo, y la devolución (pacs.004) con sus
                 motivos, incluidos los del MED (mecanismo especial de
                 devolución, para fraude y falla operativa).

    Los códigos de rechazo son los del catálogo del SPI; acá hay un
    subconjunto con su explicación en castellano, para que el panel no
    muestre «AC06» a secas.
"""
import re
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ─── claves ───────────────────────────────────────────────────────────────

CPF, CNPJ, EMAIL, TELEFONE, EVP = "cpf", "cnpj", "email", "telefone", "evp"

_EVP = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TELEFONE = re.compile(r"^\+55\d{10,11}$")


class ClaveInvalida(ValueError):
    pass


def _cpf_valido(digitos: str) -> bool:
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for largo in (9, 10):
        suma = sum(int(d) * (largo + 1 - i) for i, d in enumerate(digitos[:largo]))
        esperado = (suma * 10) % 11 % 10
        if esperado != int(digitos[largo]):
            return False
    return True


def _cnpj_valido(digitos: str) -> bool:
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for largo in (12, 13):
        p = ([6] + pesos) if largo == 13 else pesos
        suma = sum(int(d) * p[i] for i, d in enumerate(digitos[:largo]))
        resto = suma % 11
        esperado = 0 if resto < 2 else 11 - resto
        if esperado != int(digitos[largo]):
            return False
    return True


def tipo_de_clave(texto: str) -> str:
    """Qué clase de clave es. Lanza ClaveInvalida si no es ninguna."""
    t = (texto or "").strip()
    if not t:
        raise ClaveInvalida("La clave está vacía.")
    if _EVP.match(t.lower()):
        return EVP
    if _TELEFONE.match(t):
        return TELEFONE
    if "@" in t:
        if _EMAIL.match(t) and len(t) <= 77:
            return EMAIL
        raise ClaveInvalida("El correo no tiene forma de correo.")
    digitos = re.sub(r"\D", "", t)
    if len(digitos) == 11 and digitos == t:
        if _cpf_valido(digitos):
            return CPF
        raise ClaveInvalida("El CPF no pasa los dígitos verificadores.")
    if len(digitos) == 14 and digitos == t:
        if _cnpj_valido(digitos):
            return CNPJ
        raise ClaveInvalida("El CNPJ no pasa los dígitos verificadores.")
    raise ClaveInvalida("No es una clave PIX: se espera CPF, CNPJ, correo, teléfono (+55…) o clave aleatoria.")


def normalizar_clave(texto: str) -> str:
    tipo = tipo_de_clave(texto)
    t = texto.strip()
    return t.lower() if tipo in (EMAIL, EVP) else t


# ─── identificadores ──────────────────────────────────────────────────────

_ALFABETO = string.ascii_uppercase + string.digits
_END_TO_END = re.compile(r"^E\d{8}\d{12}[A-Za-z0-9]{11}$")
_TXID = re.compile(r"^[A-Za-z0-9]{26,35}$")


def nuevo_end_to_end(ispb: str, momento: Optional[datetime] = None) -> str:
    """«E» + ISPB + aaaammddHHMM + 11 caracteres. El formato del SPI."""
    if not re.fullmatch(r"\d{8}", ispb or ""):
        raise ValueError("El ISPB son ocho dígitos.")
    momento = momento or datetime.now(timezone.utc)
    sufijo = "".join(secrets.choice(_ALFABETO) for _ in range(11))
    return f"E{ispb}{momento.strftime('%Y%m%d%H%M')}{sufijo}"


def es_end_to_end(texto: str) -> bool:
    return bool(_END_TO_END.match(texto or ""))


def nuevo_txid() -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(32))


def es_txid(texto: str) -> bool:
    return bool(_TXID.match(texto or ""))


# ─── BR Code ──────────────────────────────────────────────────────────────

def _crc16(datos: bytes) -> str:
    """CRC-16/CCITT-FALSE, el que pide el EMV: polinomio 0x1021, inicio 0xFFFF."""
    crc = 0xFFFF
    for b in datos:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def _campo(id_: str, valor: str) -> str:
    if len(valor) > 99:
        raise ValueError(f"El campo {id_} del BR Code no puede pasar de 99 caracteres.")
    return f"{id_}{len(valor):02d}{valor}"


def _sin_acentos(texto: str, largo: int) -> str:
    import unicodedata
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return plano.upper()[:largo]


def br_code(*, clave: str, monto_centavos: int, nombre: str, ciudad: str, txid: str,
            descripcion: Optional[str] = None) -> str:
    """El texto del QR PIX, en el formato EMV que exige el Banco Central.

    Lo que va adentro: la GUI «br.gov.bcb.pix», la clave, el monto con punto
    decimal, la moneda 986 (real), el país, el nombre y la ciudad del
    receptor en mayúsculas sin acentos, el txid, y el CRC al final."""
    if monto_centavos <= 0:
        raise ValueError("El monto del cobro es mayor que cero.")
    if not es_txid(txid):
        raise ValueError("El txid lleva de 26 a 35 caracteres alfanuméricos.")
    cuenta = _campo("00", "br.gov.bcb.pix") + _campo("01", clave)
    if descripcion:
        cuenta += _campo("02", _sin_acentos(descripcion, 40))
    cuerpo = (
        _campo("00", "01")                        # formato
        + _campo("01", "12")                      # dinámico: un cobro, una vez
        + _campo("26", cuenta)                    # datos de la cuenta PIX
        + _campo("52", "0000")                    # categoría del comercio
        + _campo("53", "986")                     # moneda: real brasileño
        + _campo("54", f"{monto_centavos // 100}.{monto_centavos % 100:02d}")
        + _campo("58", "BR")
        + _campo("59", _sin_acentos(nombre, 25))
        + _campo("60", _sin_acentos(ciudad, 15))
        + _campo("62", _campo("05", txid))
        + "6304"
    )
    return cuerpo + _crc16(cuerpo.encode("utf-8"))


def br_code_valido(texto: str) -> bool:
    """Comprueba el CRC. Un QR con un carácter cambiado no pasa."""
    if len(texto) < 8 or texto[-8:-4] != "6304":
        return False
    return _crc16(texto[:-4].encode("utf-8")) == texto[-4:].upper()


# ─── mensajes del SPI ─────────────────────────────────────────────────────

# pacs.002: cómo terminó una orden.
ACSP = "ACSP"   # aceptada, liquidación en curso
ACSC = "ACSC"   # aceptada y liquidada
RJCT = "RJCT"   # rechazada

MOTIVOS_DE_RECHAZO = {
    "AB03": "La liquidación se interrumpió por tiempo agotado en el SPI",
    "AB09": "Error al procesar el pago",
    "AB11": "El PSP del pagador no respondió a tiempo",
    "AC03": "La cuenta del receptor es inválida",
    "AC06": "La cuenta del receptor está bloqueada",
    "AC07": "La cuenta del receptor está cerrada",
    "AC14": "El tipo de cuenta del receptor es inválido",
    "AG03": "Tipo de transacción no admitido",
    "AM02": "Monto no permitido",
    "AM04": "Saldo insuficiente",
    "AM12": "Monto inválido",
    "BE01": "Los datos del receptor no coinciden con la clave",
    "BE17": "El texto libre es inválido",
    "DS04": "Orden rechazada por el PSP",
    "DS0G": "Pago no permitido por las reglas del PSP",
    "DS27": "El PSP del pagador está fuera de línea",
    "DT02": "Fecha de creación inválida",
    "ED05": "Falló la liquidación",
    "FF07": "Finalidad inválida",
    "FF08": "Identificador punta a punta inválido",
    "FRAD": "Origen fraudulento",
    "RR04": "Motivo regulatorio",
}

# pacs.004: por qué se devuelve. FR01 y BE08 son los del MED.
MOTIVOS_DE_DEVOLUCION = {
    "MD06": "Devolución pedida por el usuario receptor",
    "SL02": "Devolución por un servicio específico del PSP",
    "FR01": "Fraude (MED)",
    "BE08": "Falla operativa del PSP (MED)",
}


@dataclass(frozen=True)
class TitularDeClave:
    """Lo que el DICT contesta sobre una clave."""
    clave: str
    tipo: str
    nombre: str
    documento_enmascarado: str
    ispb: str
    banco: str


@dataclass(frozen=True)
class Cobro:
    txid: str
    monto: int
    codigo_br: str
    clave_receptora: str


@dataclass(frozen=True)
class OrdenDePago:
    """pacs.008: lo que se manda al SPI para pagar."""
    end_to_end: str
    monto: int
    clave_destino: str
    receptor: TitularDeClave
    pagador_cuenta: str
    descripcion: str = ""


@dataclass(frozen=True)
class RespuestaDeEstado:
    """pacs.002: qué pasó con una orden."""
    end_to_end: str
    estado: str                                   # ACSP, ACSC, RJCT
    motivo: Optional[str] = None                  # código del catálogo si es RJCT
    momento: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def motivo_explicado(self) -> Optional[str]:
        if not self.motivo:
            return None
        return f"{self.motivo}: {MOTIVOS_DE_RECHAZO.get(self.motivo, 'motivo no catalogado')}"


@dataclass(frozen=True)
class Devolucion:
    """pacs.004: devolver (parte de) un pago recibido."""
    end_to_end_original: str
    end_to_end: str
    monto: int
    motivo: str                                   # código de MOTIVOS_DE_DEVOLUCION

    def __post_init__(self):
        if self.motivo not in MOTIVOS_DE_DEVOLUCION:
            raise ValueError(f"Motivo de devolución desconocido: {self.motivo}.")
        if self.monto <= 0:
            raise ValueError("La devolución es por más que cero.")


def enmascarar_documento(documento: str) -> str:
    """Como lo muestra el DICT: un CPF se ve «***.456.789-**»."""
    d = re.sub(r"\D", "", documento or "")
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/****-**"
    return "***"
