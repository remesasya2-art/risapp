"""
Los secretos del núcleo: credenciales y certificados, por nombre.

POR QUE UN PUERTO

    Hoy el único secreto es la cadena de conexión a Postgres. Los adaptadores
    reales que vienen (SPI, DICT, STA, SISCOAF, el verificador de identidad,
    las listas) traen cada uno su certificado o su credencial, y si cada
    adaptador leyera el entorno por su cuenta habría ocho formas de guardar
    un secreto y ninguna de rotarlo. Acá hay UN catálogo con nombre y para
    qué sirve cada uno, UN puerto para leerlos, y hoy UN adaptador: variables
    de entorno `NUCLEO_SECRETO_<NOMBRE>`. Mañana, un gestor de secretos con
    la misma firma, y ningún adaptador cambia.

EL VALOR NO SE MUESTRA NUNCA

    Lo que sale de acá hacia la pestaña o la bitácora es si está configurado
    y una HUELLA (los primeros doce caracteres del SHA-256). La huella alcanza
    para saber que el secreto cambió —una rotación— sin decir cuál es. No hay
    función que devuelva el valor a una ruta; `leer` es para los adaptadores.
"""
import hashlib
import os
from typing import Optional, Protocol

from nucleo import base, modo

# nombre → (para qué, obligatorio en ACTIVO). En laboratorio sólo hace falta
# la base: todo lo demás son simuladores que no piden credencial.
CATALOGO = {
    "base_de_datos": ("La base Postgres del núcleo (NUCLEO_DATABASE_URL)", True),
    "certificado_spi": ("El certificado con el que se firma cada mensaje al SPI (PIX)", True),
    "credencial_dict": ("La credencial del directorio de claves PIX (DICT)", True),
    "credencial_sta": ("La credencial del sistema de transferencia de archivos del BCB (reportes)", True),
    "credencial_siscoaf": ("La credencial del SISCOAF (comunicaciones al COAF)", True),
    "credencial_verificador": ("La credencial del verificador de identidad (documento, vida, rostro)", True),
    "credencial_listas": ("La credencial del proveedor de listas de sanciones y PEP", True),
    "llave_de_respaldo": ("La llave con la que se firma cada respaldo del libro", False),
}
OBLIGATORIOS_EN_LABORATORIO = ("base_de_datos",)


class Secretos(Protocol):
    nombre: str

    def leer(self, nombre: str) -> Optional[str]:
        """El valor, o None si no está configurado. SOLO para los adaptadores."""


class DesdeEntorno:
    nombre = "variables-de-entorno"

    @staticmethod
    def variable(nombre: str) -> str:
        return base.VARIABLE if nombre == "base_de_datos" else f"NUCLEO_SECRETO_{nombre.upper()}"

    def leer(self, nombre: str) -> Optional[str]:
        if nombre not in CATALOGO:
            raise KeyError(f"No existe el secreto «{nombre}» en el catálogo.")
        if nombre == "base_de_datos":
            # La base «configurada» es la que está en uso: en los tests y en la
            # vista previa la apunta `base.usar`, sin variable de entorno.
            return base._url_en_uso or (os.environ.get(base.VARIABLE) or "").strip() or None
        return (os.environ.get(self.variable(nombre)) or "").strip() or None


def secretos() -> Secretos:
    return DesdeEntorno()


def huella(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:12]


def obligatorios(modo_vigente: int) -> tuple:
    if modo_vigente == modo.ACTIVO:
        return tuple(n for n, (_, en_activo) in CATALOGO.items() if en_activo)
    return OBLIGATORIOS_EN_LABORATORIO


async def estado(modo_vigente: int = modo.LABORATORIO, anotar_rotaciones: bool = True) -> list:
    """Uno por secreto del catálogo: si está, su huella, si hace falta en el
    modo vigente. Si la huella cambió desde la última vez que se miró, deja
    «secreto.rotado» en la bitácora (la rotación es un hecho de operación)."""
    from nucleo.operacion import bitacora
    puerto = secretos()
    salida = []
    for nombre, (para_que, _) in CATALOGO.items():
        valor = puerto.leer(nombre)
        h = huella(valor) if valor else None
        fila = {"nombre": nombre, "para_que": para_que, "variable": DesdeEntorno.variable(nombre),
                "configurado": valor is not None, "huella": h, "obligatorio": nombre in obligatorios(modo_vigente),
                "rotado": False}
        if anotar_rotaciones and h and base.hay_base():
            visto = await bitacora.ultimo("secreto.visto", nombre)
            anterior = (visto or {}).get("despues", {}).get("huella") if visto else None
            if anterior != h:
                await bitacora.anotar_sin_romper(actor=puerto.nombre, accion="secreto.visto", objetivo=nombre,
                                                 antes={"huella": anterior} if anterior else None, despues={"huella": h},
                                                 detalle="rotado" if anterior else "configurado")
                fila["rotado"] = anterior is not None
        salida.append(fila)
    return salida


def faltantes(modo_vigente: int) -> list:
    puerto = secretos()
    return [n for n in obligatorios(modo_vigente) if not puerto.leer(n)]
