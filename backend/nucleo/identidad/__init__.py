"""
Identidad y riesgo: quién es el titular, si se puede operar con él, y qué
pasa cuando algo no cierra.

POR QUE ESTA EN EL NUCLEO Y NO EN EL KYC QUE YA EXISTE

    La aplicación ya tiene un KYC: el cliente sube documento, CPF y selfie,
    un agente aprueba a ojo y le pone un nivel de riesgo. Eso alcanza para
    lo que la aplicación es hoy. Para una instituição de pagamento no: el
    Banco Central (Circular 3.978/2020) exige un legajo con vigencia,
    declaración de PEP y de origen de fondos, cruce con listas, monitoreo
    con umbrales, expediente de caso con plazos y comunicación al COAF. Y
    exige que eso sea del SISTEMA, no de la memoria de un agente.

    Se construye acá, con la misma regla que el resto del núcleo: apagado
    de fábrica, sólo el super administrador, y nada de la aplicación se
    importa.

LOS TRES PUERTOS, Y QUIEN LOS VA A IMPLEMENTAR

    Hoy la verificación es manual. La arquitectura queda lista para el día
    que se contrate a quien verifique: cada pieza externa entra por un
    puerto, y hoy los tres los implementa un simulador.

      Verificador   lee el documento, hace la prueba de vida, coteja la cara
                    y consulta la situación del CPF. Adaptadores previstos:
                    Serpro Datavalid (biometría y documento contra las bases
                    del gobierno) y la consulta de CPF de la Receita Federal.
      Listas        sanciones (CSNU, la lista de la ONU que el Brasil aplica
                    por ley; OFAC) y personas expuestas políticamente (la
                    lista de PEP de la CGU, en el Portal da Transparência).
      Comunicador   la comunicación al COAF, por el SISCOAF (mitad 2).

    Cambiar de proveedor es escribir un adaptador con la misma forma. El
    resto —el legajo, las reglas, los casos— no se entera.

LO QUE NO SE GUARDA ACA

    Las fotos. Los documentos y las selfies siguen en el cofre de la
    aplicación (cifrado), fuera del núcleo. Acá quedan los RESULTADOS: qué
    dijo el verificador, con qué puntaje, cuándo. Es lo que un auditor pide
    y lo que no expone a nadie si se filtra.
"""
from typing import Protocol

from nucleo.identidad import formas


class Verificador(Protocol):
    nombre: str

    async def verificar(self, sesion, *, documento: str, nombre: str, nacimiento: str) -> formas.ResultadoDeVerificacion:
        """Documento, prueba de vida, cotejo de rostro y situación del CPF."""


class Listas(Protocol):
    nombre: str

    async def consultar(self, sesion, *, documento: str, nombre: str) -> list[formas.Coincidencia]:
        """Sanciones y PEP. Lista vacía es «no aparece»."""


def verificador() -> Verificador:
    from nucleo.identidad.simulador import VerificadorDePrueba
    return VerificadorDePrueba()


def listas() -> Listas:
    from nucleo.identidad.simulador import ListasDePrueba
    return ListasDePrueba()
