"""
models/envios_cotizacion.py — Lo que el formulario manda para cotizar.

UN SOLO FORMULARIO ALIMENTA TRES COTIZACIONES
    La del servicio que RIS App cobra, y las dos ORIENTATIVAS de los
    transportistas que el usuario contrata por su cuenta. El usuario carga los
    datos una vez.

LO QUE NO VIAJA EN LA PETICION
    - El CEP de destino del tramo 1: es una constante del servidor. Que el
      cliente pudiera elegir a donde se despacha seria dejarle elegir a donde va
      su propio paquete antes de que nadie lo revise.
    - A nombre de quien se rotula: lo arma el servidor con la nomina.
    - El precio: obviamente. Se calcula, no se manda.

LAS MEDIDAS VIAJAN EN TEXTO
    Mismo criterio que models/envios_tarifa y models/envios_config: un float en
    el borde de la API es como el ruido binario vuelve a entrar, y un peso de
    2.30 que llega como 2.2999999999999998 se cubica distinto.
"""

from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _medida(valor, campo: str, minimo=None, maximo=None) -> str:
    if valor is None:
        return valor
    texto = str(valor).strip()
    if not texto:
        raise ValueError(f"{campo} no puede estar vacío.")
    if "," in texto:
        raise ValueError(
            f"{campo} tiene una coma decimal ({texto!r}). Escribilo con punto: 2.30, no 2,30."
        )
    if "e" in texto.lower():
        raise ValueError(f"{campo} está en notación científica ({texto!r}).")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError(f"{campo} no es un número: {texto!r}.") from None
    if not numero.is_finite():
        raise ValueError(f"{campo} no es un número finito.")
    if minimo is not None and numero < Decimal(str(minimo)):
        raise ValueError(f"{campo} no puede ser menor que {minimo}.")
    if maximo is not None and numero > Decimal(str(maximo)):
        raise ValueError(f"{campo} no puede ser mayor que {maximo}.")
    return texto


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Origen(_Base):
    """Desde dónde despacha el usuario. Viene precargado de su perfil."""
    cep: str = Field(min_length=8, max_length=9)
    ciudad: Optional[str] = Field(default=None, max_length=80)
    # La UF es la clave con la que se busca la orientación del tramo 1. Es
    # opcional a proposito: sin ella la referencia vuelve como "sin_clave" y la
    # cotizacion se completa igual. Una orientacion ausente no puede impedir
    # cotizar el servicio, que es lo unico que RIS App cobra.
    uf: Optional[str] = Field(default=None, min_length=2, max_length=2)

    @field_validator("cep")
    @classmethod
    def _cep(cls, v):
        limpio = str(v).replace("-", "").replace(".", "").strip()
        if not (limpio.isdigit() and len(limpio) == 8):
            raise ValueError("El CEP de origen tiene ocho dígitos.")
        return limpio

    @field_validator("uf")
    @classmethod
    def _uf(cls, v):
        return None if v is None else str(v).strip().upper()


class Destinatario(_Base):
    nombre: str = Field(min_length=3, max_length=120)
    documento: str = Field(min_length=5, max_length=30)
    telefono: str = Field(min_length=7, max_length=30)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v):
        texto = " ".join(str(v).split())
        if len(texto.split()) < 2:
            raise ValueError(
                "Poné el nombre y el apellido de quien recibe: es lo que el mostrador "
                "compara contra el documento."
            )
        return texto


class Destino(_Base):
    """A dónde va en Venezuela. La agencia se elige del catálogo, por código."""
    agencia_codigo: str = Field(min_length=1, max_length=40)
    transportista_id: str = Field(min_length=1, max_length=60)
    codigo_postal: Optional[str] = Field(default=None, max_length=10)
    destinatario: Destinatario


class Paquete(_Base):
    """UNA caja. No hay `bultos` a proposito.

    El motor de tarifas sabe aplicar un descuento por cantidad, y exponer ese
    campo en la peticion lo convertia en una palanca de descuento que maneja el
    cliente: con una tabla que descuenta 25 % desde diez bultos, mandar
    `bultos: 100` con las mismas medidas bajaba el precio de 132 a 99 sin que
    nada verificara despues cuantas cajas se despacharon de verdad.

    El dia que haya envios de varias cajas, cada una tiene su peso y sus medidas
    —el cubado es por caja— asi que la peticion va a ser una LISTA de paquetes, y
    los bultos van a salir de contarla. Un entero suelto nunca fue eso.
    """
    # El tope de largo no es cosmetico: sin el, "2." seguido de dos millones de
    # treses vale 2.33 —pasa todos los rangos— y se guarda tal cual. Cuatro
    # campos asi son 8 MB por documento, y a 4.5 MB cada uno se pasa el limite de
    # 16 MB de Mongo. Un numero real de este dominio no llega a veinte caracteres.
    peso_kg: str = Field(max_length=20)
    largo_cm: str = Field(max_length=20)
    ancho_cm: str = Field(max_length=20)
    alto_cm: str = Field(max_length=20)
    contenido_descripcion: str = Field(min_length=1, max_length=500)
    valor_declarado_brl: str = Field(default="0", max_length=20)

    @field_validator("peso_kg", "largo_cm", "ancho_cm", "alto_cm")
    @classmethod
    def _medidas(cls, v, info):
        return _medida(v, info.field_name, minimo="0.001", maximo=100000)

    @field_validator("valor_declarado_brl")
    @classmethod
    def _valor(cls, v):
        return _medida(v, "el valor declarado", minimo=0, maximo=10000000)


class PedidoDeCotizacion(_Base):
    origen: Origen
    destino: Destino
    paquete: Paquete
    # Como se paga el tramo 3 (§4.6). "destino": lo paga quien recibe y RIS App
    # no toca esa plata. "prepago": lo paga el usuario, por el mismo camino de
    # remesas que ya existe, como FONDOS DE TERCEROS y nunca como ingreso.
    #
    # Se elige acá y no despues porque cambia lo que la pantalla le muestra al
    # usuario desde el primer paso — pero NO cambia ni un centavo de lo que se
    # cotiza: el flete no se cobra al cotizar, ni al crear, ni nunca dentro del
    # envio.
    modalidad_flete: Literal["destino", "prepago"] = "destino"
