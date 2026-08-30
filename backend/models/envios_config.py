"""
models/envios_config.py — Los esquemas de lo que el panel puede editar.

POR QUE ESTO EXISTE
    Un panel que escribe JSON libre en Mongo es una bomba de tiempo: un typo en
    una clave rompe la cotizacion en produccion y nadie sabe quien lo hizo. Un
    modelo por bloque de configuracion —igual que los de models/requests.py—
    convierte ese typo en un mensaje que dice que campo esta mal, antes de
    guardar.

    La regla que gobierna todo el panel: **ningun numero que alguien de negocio
    pueda querer mover un martes vive en el codigo, y ningun nombre propio de una
    empresa tampoco**. Lo que vive aca es la FORMA de esos datos, nunca sus
    valores.

DECIMALES COMO TEXTO, A PROPOSITO
    Los montos y los pesos se declaran `str` y no `float`. Un float en el borde
    de la API es como un 0.1 + 0.2 entra al sistema: services/money.py existe
    justamente para que eso no pase, y aceptar un float aca seria abrirle la
    puerta de nuevo. El validador comprueba que el texto sea un numero, y el
    calculo lo hace Decimal.
"""

from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _decimal_valido(valor, campo: str, minimo=None, maximo=None) -> str:
    """Un número escrito como texto. Rechaza la coma decimal y los no finitos.

    La coma se rechaza en vez de convertirse: "1,5" puede ser uno y medio o mil
    quinientos según quién lo escriba, y adivinar mal en un precio es peor que
    pedirle a la persona que lo escriba con punto.
    """
    if valor is None:
        return valor
    texto = str(valor).strip()
    if not texto:
        raise ValueError(f"{campo} no puede estar vacío.")
    if "," in texto:
        raise ValueError(
            f"{campo} tiene una coma decimal ({texto!r}). Escribilo con punto: 1.50, no 1,50."
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
    # Un campo de más es casi siempre un typo en el nombre de otro. Rechazarlo
    # convierte "guardé y no pasó nada" en un mensaje que dice qué se escribió mal.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ─── Bloques que componen la ficha de un transportista ────────────────────

class ReglaPeso(_Base):
    """Cómo cubica ese transportista. No hay divisor global: es de cada uno."""
    divisor: int = Field(gt=0, le=100000)
    escalon_kg: str = "0.5"
    minimo_kg: str = "0"
    umbral_cubado_kg: Optional[str] = None   # None = el cubado se aplica siempre

    @field_validator("escalon_kg", "minimo_kg", "umbral_cubado_kg")
    @classmethod
    def _numeros(cls, v, info):
        return _decimal_valido(v, info.field_name, minimo=0, maximo=1000)


class LimitesFisicos(_Base):
    """Lo que ese transportista acepta. Todo opcional: lo que no se declara, no
    restringe — inventar un techo que después nadie puede explicar es peor."""
    peso_max_kg: Optional[str] = None
    lado_max_cm: Optional[str] = None
    suma_lados_max_cm: Optional[str] = None
    largo_min_cm: Optional[str] = None
    ancho_min_cm: Optional[str] = None
    alto_min_cm: Optional[str] = None
    suma_lados_min_cm: Optional[str] = None
    valor_declarado_max: Optional[str] = None

    @field_validator("*")
    @classmethod
    def _numeros(cls, v, info):
        return _decimal_valido(v, info.field_name, minimo=0, maximo=1000000)


class CuentaBancaria(_Base):
    """La cuenta del transportista de destino, para el flete prepago (§4.6).

    Es el campo más sensible del panel: quien pueda editarlo puede redirigir
    todos los fletes. Por eso la ruta que lo escribe pide confirmación tipeada,
    avisa al equipo, y versiona en vez de pisar.
    """
    banco: str = Field(min_length=2, max_length=80)
    tipo_cuenta: Literal["corriente", "ahorro", "pago_movil", "otro"] = "corriente"
    numero: str = Field(min_length=4, max_length=40)
    titular: str = Field(min_length=2, max_length=120)
    documento: str = Field(min_length=4, max_length=30)

    @field_validator("numero")
    @classmethod
    def _solo_digitos(cls, v):
        limpio = v.replace("-", "").replace(" ", "")
        if not limpio.isdigit():
            raise ValueError("El número de cuenta solo puede tener dígitos.")
        return limpio


class Transportista(_Base):
    """Una empresa de envíos. El código es cómo la nombra el sistema; el nombre,
    cómo la lee el usuario. El código no cambia nunca: los envíos viejos, los
    logs y los tests lo referencian."""
    codigo: str = Field(min_length=3, max_length=20, pattern=r"^[A-Z0-9\-]+$")
    nombre: str = Field(min_length=2, max_length=80)
    rol: Literal["brasil", "venezuela"]
    activo: bool = True
    orden: int = Field(default=1, ge=0, le=999)
    moneda: Optional[str] = Field(default=None, max_length=8)
    regla_peso: ReglaPeso
    limites: LimitesFisicos = LimitesFisicos()
    plantilla_rastreo: Optional[str] = Field(default=None, max_length=300)
    fuente_referencia: Optional[str] = Field(default=None, max_length=300)
    notas: Optional[str] = Field(default=None, max_length=2000)
    # Solo tiene sentido en el rol venezuela; la ruta lo verifica.
    cuenta_bancaria: Optional[CuentaBancaria] = None


class Agencia(_Base):
    """Una oficina de un transportista. El código es único DENTRO de la empresa:
    dos empresas distintas pueden llamar "001" a su sucursal central."""
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=2, max_length=120)
    estado: str = Field(min_length=2, max_length=60)
    ciudad: str = Field(min_length=2, max_length=60)
    direccion: Optional[str] = Field(default=None, max_length=300)
    zona: Optional[str] = Field(default=None, max_length=40)
    codigo_postal: Optional[str] = Field(default=None, max_length=20)
    activa: bool = True
    # Marca la oficina donde RIS App entrega. Solo una puede tenerla, y la ruta
    # lo verifica: dos puntos de entrega es un envío que no sabe a dónde va.
    es_punto_entrega: bool = False


# ─── Bloques de app_settings ──────────────────────────────────────────────

class ConfigOperacion(_Base):
    """Los números que mueven la operación sin tocar el precio."""
    tolerancia_ajuste_ris: str = "2.00"
    ttl_cotizacion_horas: int = Field(default=48, ge=1, le=720)
    ttl_espera_postagem_dias: int = Field(default=30, ge=1, le=365)
    plazo_pago_pendiente_dias: int = Field(default=7, ge=1, le=90)
    dias_guarda: int = Field(default=30, ge=1, le=180)
    alertas_guarda_dias: list[int] = [7, 15, 25]
    banda_variacion_pct: str = "0.15"

    @field_validator("tolerancia_ajuste_ris")
    @classmethod
    def _tolerancia(cls, v):
        return _decimal_valido(v, "la tolerancia de ajuste", minimo=0, maximo=1000)

    @field_validator("banda_variacion_pct")
    @classmethod
    def _banda(cls, v):
        return _decimal_valido(v, "la banda de variación", minimo=0, maximo=1)

    @field_validator("alertas_guarda_dias")
    @classmethod
    def _alertas(cls, v):
        if not v:
            raise ValueError("Tiene que haber al menos un aviso antes de que venza la guarda.")
        if sorted(v) != v:
            raise ValueError("Los avisos de guarda tienen que ir de menor a mayor.")
        return v


class ConfigContenido(_Base):
    """Lo que el usuario lee y acepta. Cambia con un criterio de aduana, no con
    un deploy."""
    prohibidos: list[str] = Field(min_length=1)
    terminos_version: str = Field(min_length=3, max_length=40)
    texto_estimado: str = Field(min_length=20, max_length=4000)
    descripcion_min_caracteres: int = Field(default=10, ge=3, le=200)

    @field_validator("prohibidos")
    @classmethod
    def _sin_vacios(cls, v):
        limpios = [x.strip() for x in v if x and x.strip()]
        if not limpios:
            raise ValueError("La lista de prohibidos no puede quedar vacía.")
        return limpios


class ConfigPuntoOrigen(_Base):
    """La agencia de Pacaraima a la que el usuario despacha."""
    nombre: str = Field(min_length=2, max_length=120)
    cep: str = Field(min_length=8, max_length=9)
    ciudad: str = "Pacaraima"
    uf: str = "RR"
    modalidad: Literal["caixa_postal", "posta_restante", "otro"] = "caixa_postal"
    caixa_postal: Optional[str] = Field(default=None, max_length=20)
    razon_social: str = Field(min_length=2, max_length=120)
    plantilla_direccion: str = Field(min_length=10, max_length=1000)

    @field_validator("cep")
    @classmethod
    def _cep(cls, v):
        limpio = v.replace("-", "")
        if not (limpio.isdigit() and len(limpio) == 8):
            raise ValueError("El CEP tiene ocho dígitos.")
        return limpio


# El registro que usa la ruta. Un bloque que no está acá no se puede guardar, y
# es a propósito: agregar un bloque es agregar su esquema.
ESQUEMAS = {
    "operacion": ConfigOperacion,
    "contenido": ConfigContenido,
    "punto_origen": ConfigPuntoOrigen,
}

# Los campos que NUNCA se escriben completos en un log de auditoría. El número de
# cuenta se guarda enmascarado: el log lo lee más gente de la que puede editar la
# cuenta, y un número completo ahí es una copia del dato sensible en un lugar con
# menos control que el original.
CAMPOS_SENSIBLES = ("numero", "documento")
