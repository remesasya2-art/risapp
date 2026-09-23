"""
models/envios_salida.py — Lo que el cliente ve de sus envíos, y lo que ve
cualquiera con el enlace de seguimiento.

POR QUE, SI EL MODULO YA ARMA TODO CAMPO POR CAMPO

    Las respuestas de envíos ya se construyen a mano, clave por clave
    (`services/envios_consulta.py`, `services/envios_seguimiento.py`). El
    contrato no cambia nada de lo que se ve: es la segunda capa. Una función
    que arma el diccionario se puede ensanchar con un `**envio` en una tarde
    apurada; el contrato, que vive al lado del nombre de la ruta, corta igual.

    La ruta que más lo necesita es `/envios/seguimiento/{token}`: no pide
    sesión, y su enlace se comparte por WhatsApp.

LOS TIPOS SON LOS DE LA RESPUESTA DE HOY

    Cada campo copia lo que la ruta ya devolvía. Casi todos son `Escalar`, un
    valor simple de cualquier tipo: los montos salen como texto, las fechas
    como fecha o como texto según la edad del documento, y un envío a medio
    migrar puede traer un número donde otro trae un texto. El contrato
    recorta; no convierte, y no puede contestar 500 por un documento viejo.
    Lo único que no deja pasar en un campo simple es un documento entero
    (ver `_sin_estructura`). Las rutas usan `exclude_unset`, así que lo que la
    función no pone sigue sin salir, en vez de salir como null.
"""
from typing import Annotated, Any, List, Optional

from pydantic import BaseModel, BeforeValidator, create_model


def _sin_estructura(valor):
    """Un valor suelto pasa; un documento o una lista, no.

    `Any` a secas deja pasar CUALQUIER cosa, sub-documentos incluidos, y así el
    contrato no cortaba nada. Lo encontró su propio test: con la función de la
    lista devolviendo de más, `destino.destinatario` —que la función convierte
    en el nombre— salía como el documento entero de quien recibe, con su
    cédula y su teléfono. Un campo que es un texto, un número o una fecha no
    puede traer un diccionario adentro: si llega uno, es un error de quien
    armó la respuesta, y se muestra vacío en vez de mostrarse de más.
    """
    return None if isinstance(valor, (dict, list, tuple, set)) else valor


# Un valor de cualquier tipo SIMPLE. Ver `_sin_estructura`.
Escalar = Annotated[Optional[Any], BeforeValidator(_sin_estructura)]


def _libre(nombre: str, campos) -> type:
    """Un modelo con esos campos, todos opcionales y de un valor simple."""
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


# ══════════════════════════════════════════════════════════════════════════
# 1. La dirección de despacho en Brasil
# ══════════════════════════════════════════════════════════════════════════

# Lo que el cliente ve del bloque de despacho. LISTA DE LO PERMITIDO.
#
# Antes eran tres copias de una lista de lo prohibido —en cotizar, en
# confirmar y en el detalle— que sacaban a mano `retirador_id`,
# `retirador_motivo` y `congelado_at`. Funcionaban, pero el primer campo nuevo
# que se le agregara al bloque en `services/envios_retiro.py` viajaba solo a
# las tres pantallas, y había que acordarse de tres lugares para taparlo.
#
# `retirador_nombre` va a propósito: es el «A/C» de la etiqueta, el nombre con
# el que el mostrador entrega la caja. Su identificador interno no.
LO_QUE_VE_DEL_RETIRO = (
    "destinatario", "razon_social", "retirador_nombre", "agencia",
    "linea_agencia", "modalidad", "caixa_postal", "ciudad", "uf", "cep",
    "texto_copiable",
)

RetiroQueVeElCliente = _libre("RetiroQueVeElCliente", LO_QUE_VE_DEL_RETIRO)


def retiro_para_el_cliente(despacho) -> dict:
    """El bloque de despacho recortado a lo que se muestra.

    Lo usan las tres pantallas que lo muestran: la cotización, la
    confirmación y el detalle. Una sola lista para las tres.
    """
    despacho = despacho if isinstance(despacho, dict) else {}
    return {k: despacho[k] for k in LO_QUE_VE_DEL_RETIRO if k in despacho}


# ══════════════════════════════════════════════════════════════════════════
# 2. El seguimiento público: sin sesión, y sin un solo dato personal
# ══════════════════════════════════════════════════════════════════════════

class DestinoPublico(BaseModel):
    ciudad: Escalar = None
    estado: Escalar = None


class PasoPublico(BaseModel):
    estado: Escalar = None
    titulo: Escalar = None
    detalle: Escalar = None
    at: Escalar = None


class SeguimientoPublico(BaseModel):
    display_id: Escalar = None
    estado: Escalar = None
    estado_titulo: Escalar = None
    estado_detalle: Escalar = None
    destino: Optional[DestinoPublico] = None
    guia_transportista: Escalar = None
    creado_at: Escalar = None
    timeline: List[PasoPublico] = []


# ══════════════════════════════════════════════════════════════════════════
# 3. Los envíos del cliente
# ══════════════════════════════════════════════════════════════════════════

class DestinoDeMiEnvio(BaseModel):
    ciudad: Escalar = None
    estado: Escalar = None
    agencia: Escalar = None
    destinatario: Escalar = None


class FilaDeMiEnvio(BaseModel):
    envio_id: Escalar = None
    display_id: Escalar = None
    estado: Escalar = None
    creado_at: Escalar = None
    destino: Optional[DestinoDeMiEnvio] = None
    es_estimado: Escalar = None
    total_ris: Escalar = None
    moneda: Escalar = None
    codigo_objeto: Escalar = None
    hay_algo_que_pagar: Escalar = None
    a_pagar_ris: Escalar = None
    vence_at: Escalar = None


class MisEnvios(BaseModel):
    envios: List[FilaDeMiEnvio] = []
    pagina: Escalar = None
    hay_mas: Escalar = None
    degradado: Escalar = None


# Sólo las medidas. Nada de quién las tomó ni cuándo: el bloque `verificado`
# guarda el identificador del operador que pesó.
Medidas = _libre("Medidas", ("peso_kg", "largo_cm", "ancho_cm", "alto_cm", "valor_declarado"))


class PaqueteDeMiEnvio(BaseModel):
    declarado: Optional[Medidas] = None
    verificado: Optional[Medidas] = None
    contenido: Escalar = None


Comprobante = _libre("Comprobante", ("codigo_objeto", "posteado_at", "foto_asset_id", "verificado_at"))

UnCobro = _libre("UnCobro", ("partida", "concepto", "monto_ris", "estado", "pagado_at"))


class PasoDeMiEnvio(BaseModel):
    estado: Escalar = None
    titulo: Escalar = None
    at: Escalar = None


class DetalleDeMiEnvio(FilaDeMiEnvio):
    paquete: Optional[PaqueteDeMiEnvio] = None
    modalidad_flete: Escalar = None
    retiro: Optional[RetiroQueVeElCliente] = None
    comprobante: Optional[Comprobante] = None
    cobros: List[UnCobro] = []
    terminos_version: Escalar = None
    tracking_token: Escalar = None
    guia_transportista: Escalar = None
    timeline: List[PasoDeMiEnvio] = []


# ══════════════════════════════════════════════════════════════════════════
# 4. Lo que el formulario necesita para cotizar
# ══════════════════════════════════════════════════════════════════════════

UnaAgencia = _libre("UnaAgencia", ("codigo", "nombre", "estado", "ciudad", "direccion", "zona"))

UnOrigen = _libre("UnOrigen", ("cep", "cep_legible", "ciudad", "uf"))


class UnTransportista(BaseModel):
    transportista_id: Escalar = None
    codigo: Escalar = None
    nombre: Escalar = None
    agencias: List[UnaAgencia] = []


class CatalogoDeEnvios(BaseModel):
    transportistas: List[UnTransportista] = []
    origenes: List[UnOrigen] = []
    disponible: Escalar = None
    degradado: Escalar = None


# `limites` e `impuesto_por` son mapas cuyas claves decide la configuración
# (una por límite vigente), así que van como están. Es configuración pública:
# la misma que la pantalla le muestra a quien todavía no inició sesión.
class LimitesDeEnvio(BaseModel):
    disponible: Escalar = None
    faltantes: Optional[List[Escalar]] = None
    limites: Optional[Any] = None
    impuesto_por: Optional[Any] = None
    tarifa_version: Escalar = None
    moneda: Escalar = None
    prohibidos: Optional[Any] = None
    terminos_version: Escalar = None
    descripcion_min_caracteres: Escalar = None
