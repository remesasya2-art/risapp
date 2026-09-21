"""
El simulador de identidad: un verificador y unas listas de mentira, con
las respuestas que van a dar los de verdad.

LAS PERSONAS DE PRUEBA

    Cada CPF de prueba se porta distinto, para ver cada camino:

      12345678909   Ana Prueba        todo bien
      98765432100   Beto Prueba       todo bien
      cara          Carla Cara        el rostro no coincide con el documento
      vencido       Dario Vencido     documento vencido
      nombre        Elena Otra        el documento dice otro nombre
      irregular     Fabio Irregular   CPF irregular en la Receita
      sancionado    Gustavo Listado   aparece en la lista del CSNU
      pep           Helena Publica    aparece en la lista de PEP de la CGU

    Los CPF se generan con dígitos verificadores válidos a partir de una
    base fija, así que son los mismos en cada corrida y ninguno es real.
"""
import secrets

from sqlalchemy import select

from nucleo.esquema import sim_listas, sim_personas
from nucleo.identidad import formas

NOMBRE_VERIFICADOR = "simulador-datavalid"
NOMBRE_LISTAS = "simulador-listas"

NORMAL, CARA, VENCIDO, NOMBRE, IRREGULAR, SANCIONADO, PEP = (
    "normal", "cara_no_coincide", "documento_vencido", "nombre_distinto", "cpf_irregular", "sancionado", "pep")


def cpf_de_prueba(base9: str) -> str:
    """Un CPF con dígitos verificadores válidos a partir de nueve dígitos."""
    d = base9
    for largo in (9, 10):
        suma = sum(int(x) * (largo + 1 - i) for i, x in enumerate(d[:largo]))
        d += str((suma * 10) % 11 % 10)
    return d


PERSONAS_DE_PRUEBA = (
    # cpf,                        nombre,             nacimiento,   comportamiento
    ("12345678909",               "Ana Prueba",       "1990-05-12", NORMAL),
    ("98765432100",               "Beto Prueba",      "1985-11-03", NORMAL),
    (cpf_de_prueba("111222333"),  "Carla Cara",       "1992-02-20", CARA),
    (cpf_de_prueba("222333444"),  "Dario Vencido",    "1978-07-07", VENCIDO),
    (cpf_de_prueba("333444555"),  "Elena Otra",       "1995-09-15", NOMBRE),
    (cpf_de_prueba("444555666"),  "Fabio Irregular",  "1980-01-30", IRREGULAR),
    (cpf_de_prueba("555666777"),  "Gustavo Listado",  "1970-12-01", SANCIONADO),
    (cpf_de_prueba("666777888"),  "Helena Publica",   "1975-04-22", PEP),
)


async def sembrar(sesion) -> int:
    """Deja las personas y las listas de prueba en la base si no están."""
    existentes = {c for (c,) in (await sesion.execute(select(sim_personas.c.documento))).all()}
    filas = [dict(documento=c, nombre=n, nacimiento=nac, comportamiento=comp)
             for c, n, nac, comp in PERSONAS_DE_PRUEBA if c not in existentes]
    if filas:
        await sesion.execute(sim_personas.insert(), filas)
    en_listas = {(l, d) for l, d in (await sesion.execute(select(sim_listas.c.lista, sim_listas.c.documento))).all()}
    listas = []
    for c, n, _nac, comp in PERSONAS_DE_PRUEBA:
        if comp == SANCIONADO and ("CSNU", c) not in en_listas:
            listas.append(dict(lista="CSNU", documento=c, nombre=n, detalle="Resolución 1267 del Consejo de Seguridad (prueba)"))
        if comp == PEP and ("PEP-CGU", c) not in en_listas:
            listas.append(dict(lista="PEP-CGU", documento=c, nombre=n, detalle="Cargo público de prueba, mandato vigente"))
    if listas:
        await sesion.execute(sim_listas.insert(), listas)
    return len(filas) + len(listas)


class VerificadorDePrueba:
    nombre = NOMBRE_VERIFICADOR

    async def verificar(self, sesion, *, documento: str, nombre: str, nacimiento: str) -> formas.ResultadoDeVerificacion:
        await sembrar(sesion)
        p = (await sesion.execute(select(sim_personas).where(sim_personas.c.documento == documento))).first()
        comportamiento = p.comportamiento if p else NORMAL
        nombre_en_documento = p.nombre if p else nombre
        puntajes = dict(puntaje_documento=97, puntaje_vida=95, puntaje_rostro=93)
        situacion, vencido = "regular", False
        if comportamiento == CARA:
            puntajes["puntaje_rostro"] = 41
        elif comportamiento == VENCIDO:
            vencido = True
        elif comportamiento == NOMBRE:
            nombre_en_documento = "Elena Distinta"
        elif comportamiento == IRREGULAR:
            situacion = "irregular"
        return formas.evaluar(proveedor=self.nombre, situacion_cpf=situacion, nombre_en_documento=nombre_en_documento,
                              nombre_declarado=nombre, documento_vencido=vencido, **puntajes)


class ListasDePrueba:
    nombre = NOMBRE_LISTAS

    async def consultar(self, sesion, *, documento: str, nombre: str) -> list[formas.Coincidencia]:
        await sembrar(sesion)
        filas = (await sesion.execute(select(sim_listas).where(sim_listas.c.documento == documento))).all()
        return [formas.Coincidencia(lista=f.lista, documento=f.documento, nombre=f.nombre, detalle=f.detalle) for f in filas]


def nuevo_id(prefijo: str) -> str:
    return f"{prefijo}_{secrets.token_hex(6)}"
