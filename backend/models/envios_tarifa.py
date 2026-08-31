"""
models/envios_tarifa.py — El esquema de una version de tarifa.

QUE ES ESTE DOCUMENTO
    El precio del unico servicio que RIS App cobra: retiro en Pacaraima,
    repesaje y traslado hasta la oficina del transportista en Santa Elena. Una
    tabla de escalones por peso facturable, y un puñado de palancas alrededor.

    NO tiene zonas ni pares origen-destino. El servicio termina siempre en el
    mismo mostrador, asi que su precio es una funcion de una sola variable. Si
    algun dia este modelo pide una zona, algo se rompio en el negocio antes que
    en el codigo.

REGLA DE ORO: UNA VERSION NUNCA SE MODIFICA
    Para cambiar precios se crea una version nueva y se cierra la anterior con
    `vigente_hasta`. Los envios en vuelo siguen apuntando a la version con la que
    se cotizaron, que es lo que impide cobrarle a alguien un aumento posterior a
    lo que acepto.

    El borrador es la excepcion y por eso vive aparte: se edita todo lo que haga
    falta, no afecta a nadie, y recien al publicar se convierte en una version.

TODO EN TEXTO, NUNCA EN FLOAT
    Mismo criterio que models/envios_config.py: un float en el borde de la API
    es como el ruido binario vuelve a entrar, y services/money.py existe para
    que eso no pase.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _numero(valor, campo: str, minimo=None, maximo=None) -> str:
    if valor is None:
        return valor
    texto = str(valor).strip()
    if not texto:
        raise ValueError(f"{campo} no puede estar vacío.")
    if "," in texto:
        raise ValueError(
            f"{campo} tiene una coma decimal ({texto!r}). Escribilo con punto: 1.50, no 1,50."
        )
    # Notacion cientifica: nadie tipea "1E-30" en una planilla de precios, pero
    # Decimal la acepta y despues rompe el motor. Un multiplo de redondeo de
    # 1E-30 pasa todos los rangos (es finito y esta entre 0 y 10000) y hace que
    # cotizar levante InvalidOperation por exceso de digitos, ya con la version
    # publicada y cobrando.
    if "e" in texto.lower():
        raise ValueError(
            f"{campo} esta en notacion cientifica ({texto!r}). Escribilo con todos "
            f"sus digitos."
        )
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


class Escalon(_Base):
    """Una franja de la tabla. El editor la muestra como una fila de planilla."""
    desde_kg: str
    hasta_kg: str
    precio: str

    @field_validator("desde_kg", "hasta_kg")
    @classmethod
    def _pesos(cls, v, info):
        return _numero(v, info.field_name, minimo=0, maximo=100000)

    @field_validator("precio")
    @classmethod
    def _precio(cls, v):
        return _numero(v, "el precio del escalón", minimo=0, maximo=1000000)


class ReglaPesoPropia(_Base):
    """La regla de RIS App. Vive acá y no en una ficha de transportista porque
    cambia junto con los precios y se versiona con ellos."""
    divisor: int = Field(gt=0, le=100000)
    escalon_kg: str = "0.5"
    minimo_kg: str = "1.0"
    umbral_cubado_kg: Optional[str] = None

    @field_validator("escalon_kg", "minimo_kg", "umbral_cubado_kg")
    @classmethod
    def _numeros(cls, v, info):
        return _numero(v, info.field_name, minimo=0, maximo=1000)


class Margen(_Base):
    tipo: Literal["porcentual", "fijo"] = "porcentual"
    valor: str = "0"

    @field_validator("valor")
    @classmethod
    def _valor(cls, v):
        # El techo lo pone validar_tarifa según el tipo: acá solo se descarta lo
        # que no es un número.
        return _numero(v, "el margen", minimo=0, maximo=1000000)


class Sobrecargo(_Base):
    codigo: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    nombre: str = Field(min_length=2, max_length=80)
    tipo: Literal["fijo", "porcentual", "por_kg"]
    valor: str
    activo: bool = True
    condicion: dict = {}

    @field_validator("valor")
    @classmethod
    def _valor(cls, v):
        return _numero(v, "el valor del sobrecargo", minimo=0, maximo=1000000)


class DescuentoCantidad(_Base):
    desde_bultos: int = Field(ge=2, le=1000)
    descuento: str

    @field_validator("descuento")
    @classmethod
    def _pct(cls, v):
        return _numero(v, "el descuento", minimo=0, maximo=1)


class RecargoTemporada(_Base):
    nombre: str = Field(min_length=2, max_length=60)
    desde: str
    hasta: str
    multiplicador: str
    activo: bool = True

    @field_validator("multiplicador")
    @classmethod
    def _mult(cls, v):
        return _numero(v, "el multiplicador de temporada", minimo="0.5", maximo=3)

    @field_validator("desde", "hasta")
    @classmethod
    def _fecha(cls, v, info):
        texto = str(v).strip()
        partes = texto.split("-")
        if len(partes) != 3 or not all(p.isdigit() for p in partes):
            raise ValueError(f"{info.field_name} tiene que ser una fecha AAAA-MM-DD.")
        return texto


class RedondeoFinal(_Base):
    decimales: int = Field(default=2, ge=0, le=4)
    multiplo: Optional[str] = None

    @field_validator("multiplo")
    @classmethod
    def _multiplo(cls, v):
        return _numero(v, "el múltiplo de redondeo", minimo="0.01", maximo=10000)


class LimitesPropios(_Base):
    peso_max_kg: Optional[str] = None
    lado_max_cm: Optional[str] = None
    suma_lados_max_cm: Optional[str] = None
    valor_declarado_max: Optional[str] = None

    @field_validator("*")
    @classmethod
    def _numeros(cls, v, info):
        return _numero(v, info.field_name, minimo=0, maximo=1000000)


class TarifaEnvio(_Base):
    """Una versión completa. Es lo que el editor guarda como borrador y lo que,
    al publicar, se congela y no se toca nunca más."""
    modo_tarifa: Literal["peso", "peso_o_volumen"] = "peso"
    moneda: str = Field(default="RIS", max_length=8)
    regla_peso: ReglaPesoPropia
    escalones_peso: list[Escalon] = Field(min_length=1)
    adicional_por_kg: str
    escalones_volumen: list[Escalon] = []
    adicional_por_m3: Optional[str] = None
    tarifa_minima: str = "0"
    margen: Margen = Margen()
    sobrecargos: list[Sobrecargo] = []
    descuentos_cantidad: list[DescuentoCantidad] = []
    recargos_temporada: list[RecargoTemporada] = []
    redondeo_final: RedondeoFinal = RedondeoFinal()
    limites_propios: LimitesPropios = LimitesPropios()
    prohibidos: list[str] = []

    @field_validator("adicional_por_kg", "adicional_por_m3", "tarifa_minima")
    @classmethod
    def _numeros(cls, v, info):
        return _numero(v, info.field_name, minimo=0, maximo=1000000)


class TarifaBorrador(TarifaEnvio):
    """La misma tarifa, a medio cargar.

    POR QUE EXISTE UN MODELO APARTE
        Guardar tiene que poder hacerse con la tabla incompleta: alguien carga
        cuatro escalones un martes y vuelve el jueves. Si la ruta del borrador
        exigiera una tarifa completa, la unica forma de empezar a cargar precios
        seria terminarlos de una sentada — o editar la base a mano, que es
        exactamente lo que este editor viene a evitar.

    HEREDA DE TarifaEnvio A PROPOSITO
        Asi cada campo nuevo que se le agregue a una version aparece solo en el
        borrador, con sus mismas validaciones. Lo unico que cambia es que los
        tres campos obligatorios dejan de serlo. Lo que NO se relaja es el tipo
        de cada valor: un precio con coma decimal se rechaza igual, porque
        guardarlo mal hoy es publicarlo mal manana.

    LOS DOS METADATOS
        `actualizado_por` y `actualizado_at` los estampa el servidor, pero
        viajan en el GET, y la pantalla reenvia el objeto que recibio. Sin
        declararlos, `extra="forbid"` hacia que el segundo guardado de la vida
        del editor fuera un 422. Se aceptan y se descartan.
    """
    regla_peso: Optional[ReglaPesoPropia] = None
    escalones_peso: list[Escalon] = []
    adicional_por_kg: Optional[str] = None

    actualizado_por: Optional[str] = None
    actualizado_at: Optional[datetime] = None

    def como_borrador(self) -> dict:
        """El borrador sin los metadatos del guardado anterior."""
        datos = self.model_dump()
        datos.pop("actualizado_por", None)
        datos.pop("actualizado_at", None)
        return datos


class CajaDePrueba(_Base):
    """Una caja del simulador. Media docena de estas se guardan y se recotizan
    solas con cada cambio: si una salta de golpe, se ve antes de publicar."""
    nombre: str = Field(default="", max_length=60)
    peso_kg: str
    largo_cm: str
    ancho_cm: str
    alto_cm: str
    valor_declarado: str = "0"
    bultos: int = Field(default=1, ge=1, le=1000)

    @field_validator("peso_kg", "largo_cm", "ancho_cm", "alto_cm")
    @classmethod
    def _medidas(cls, v, info):
        return _numero(v, info.field_name, minimo="0.001", maximo=100000)

    @field_validator("valor_declarado")
    @classmethod
    def _valor(cls, v):
        return _numero(v, "el valor declarado", minimo=0, maximo=10000000)
