"""
Las formas de identidad y riesgo: sin base ni red, sólo datos y reglas.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ─── el legajo ────────────────────────────────────────────────────────────

INCOMPLETO, EN_REVISION, APROBADO, RECHAZADO, VENCIDO = "incompleto", "en_revision", "aprobado", "rechazado", "vencido"
ESTADOS_DEL_LEGAJO = (INCOMPLETO, EN_REVISION, APROBADO, RECHAZADO, VENCIDO)

BAJO, MEDIO, ALTO = "bajo", "medio", "alto"
NIVELES_DE_RIESGO = (BAJO, MEDIO, ALTO)

# Cuánto vale un legajo aprobado antes de que haya que renovarlo. La
# Circular 3.978 pide que el conocimiento del cliente se mantenga
# actualizado, con más frecuencia cuanto más riesgo; estos son los plazos
# de la casa, y se ajustan cuando el oficial de cumplimiento lo diga.
MESES_DE_VIGENCIA = {BAJO: 24, MEDIO: 24, ALTO: 12}

# Los orígenes de fondos que se pueden declarar. Un catálogo cerrado, para
# que la estadística después signifique algo.
ORIGENES_DE_FONDOS = ("salario", "actividad_propia", "jubilacion", "renta_de_bienes", "herencia", "ahorros", "otro")

PUNTAJE_MINIMO = 80


@dataclass(frozen=True)
class ResultadoDeVerificacion:
    """Lo que el verificador contesta. Los puntajes van de 0 a 100."""
    proveedor: str
    puntaje_documento: int
    puntaje_vida: int
    puntaje_rostro: int
    situacion_cpf: str                      # regular, irregular, cancelado, desconocida
    nombre_en_documento: str
    documento_vencido: bool
    motivos: tuple = ()                     # por qué no se aprueba, si no se aprueba
    momento: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def aprobada(self) -> bool:
        return not self.motivos


def evaluar(*, proveedor: str, puntaje_documento: int, puntaje_vida: int, puntaje_rostro: int,
            situacion_cpf: str, nombre_en_documento: str, nombre_declarado: str,
            documento_vencido: bool) -> ResultadoDeVerificacion:
    """Convierte lo que devolvió el proveedor en una decisión con motivos.
    La regla es una sola y está acá: cada puntaje al menos PUNTAJE_MINIMO,
    documento vigente, CPF regular y nombre que coincida."""
    motivos = []
    if puntaje_documento < PUNTAJE_MINIMO:
        motivos.append(f"documento con puntaje {puntaje_documento} (mínimo {PUNTAJE_MINIMO})")
    if puntaje_vida < PUNTAJE_MINIMO:
        motivos.append(f"prueba de vida con puntaje {puntaje_vida} (mínimo {PUNTAJE_MINIMO})")
    if puntaje_rostro < PUNTAJE_MINIMO:
        motivos.append(f"el rostro no coincide con el documento (puntaje {puntaje_rostro})")
    if documento_vencido:
        motivos.append("el documento está vencido")
    if situacion_cpf != "regular":
        motivos.append(f"el CPF no está regular en la Receita ({situacion_cpf})")
    if _plano(nombre_en_documento) != _plano(nombre_declarado):
        motivos.append(f"el nombre del documento («{nombre_en_documento}») no es el declarado")
    return ResultadoDeVerificacion(
        proveedor=proveedor, puntaje_documento=puntaje_documento, puntaje_vida=puntaje_vida,
        puntaje_rostro=puntaje_rostro, situacion_cpf=situacion_cpf, nombre_en_documento=nombre_en_documento,
        documento_vencido=documento_vencido, motivos=tuple(motivos))


def _plano(texto: str) -> str:
    import unicodedata
    return " ".join(unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower().split())


# ─── las listas ───────────────────────────────────────────────────────────

SANCIONES, PEP = "sanciones", "pep"
LISTAS_CONOCIDAS = {"CSNU": SANCIONES, "OFAC": SANCIONES, "PEP-CGU": PEP}


@dataclass(frozen=True)
class Coincidencia:
    lista: str                              # CSNU, OFAC, PEP-CGU
    documento: str
    nombre: str
    detalle: str
    puntaje: int = 100                      # cuán parecido: 100 es el documento exacto

    @property
    def clase(self) -> str:
        return LISTAS_CONOCIDAS.get(self.lista, SANCIONES)
