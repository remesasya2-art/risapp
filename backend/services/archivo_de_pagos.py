"""
services/archivo_de_pagos.py — El archivo que el operador pega en el banco.

QUE RESUELVE

    Para pagar un lote de órdenes en bolívares, alguien tiene que pasar los
    datos de cada beneficiario a la banca en línea. Hoy eso se hace mirando la
    pantalla y copiando de a uno: nombre, cédula, cuenta, monto, por orden.
    Con once órdenes son cuarenta y cuatro copiados, y cada uno es una chance
    de pegar el monto de una fila en la cuenta de otra.

    Acá se arma, de una sola vez, el texto completo ya AGRUPADO POR BANCO y
    numerado, en los tres formatos que el operador usa. Se baja, se pega, y se
    paga.

POR QUE TRES FORMATOS Y NO UNO

    Porque el banco pide cosas distintas en cada caso, y mezclarlos obliga a
    quien paga a ir salteando líneas:

      · PAGO MOVIL pide cédula, teléfono y código de banco. No hay cuenta.
      · MISMO BANCO —cuando el beneficiario está en el mismo banco desde el que
        se paga— es la lista más simple y la que el banco procesa más rápido.
      · OTROS BANCOS va agrupado por banco receptor, porque en la banca en
        línea se carga un banco por vez.

    De ahí que el banco pagador sea un dato del lote y no una constante: la
    MISMA orden va a «mismo banco» o a «otros bancos» según desde dónde se
    pague ese día.

LO QUE NO SE PUEDE ARMAR NO DESAPARECE

    Una orden a la que le falta la cuenta, o cuyo banco no se reconoce, NO se
    saltea en silencio. Va a una sección aparte al final del archivo, y también
    vuelve en la respuesta para que la pantalla la muestre.

    Un archivo que trae diez líneas cuando el lote tenía once es un pago que no
    se hizo y que nadie va a notar hasta que el cliente reclame. Es exactamente
    la clase de silencio que este repositorio ya pagó caro en otros lados.
"""
import re
from decimal import Decimal

from services import bancos_venezuela as bancos
from services.money import quantize_money, to_decimal

# Los tres destinos posibles de una orden dentro del archivo.
PAGO_MOVIL = "pago_movil"
MISMO_BANCO = "mismo_banco"
OTROS_BANCOS = "otros_bancos"
SIN_DATOS = "sin_datos"

# Una cuenta bancaria venezolana son veinte dígitos, siempre. Los primeros
# cuatro son el banco, y por eso sirve para adjudicar un comprobante: es única
# y aparece entera en las transferencias.
LARGO_DE_CUENTA = 20

# Los rótulos de cada sección, tal como los lee el operador.
TITULOS = {
    PAGO_MOVIL: "PAGO MÓVIL",
    MISMO_BANCO: "MISMO BANCO",
    OTROS_BANCOS: "TRANSFERENCIAS A OTROS BANCOS",
    SIN_DATOS: "⚠ SIN DATOS COMPLETOS — NO SE PUEDEN PAGAR ASÍ",
}


def monto(valor) -> str:
    """El monto como lo espera el banco: «30660,00».

    Sin separador de miles, coma decimal y siempre dos decimales. Es lo que
    muestran los archivos que hoy se arman a mano, y no es cosmética: un punto
    de miles metido en el campo de un formulario bancario lo rechaza, o peor,
    lo interpreta.
    """
    return f"{quantize_money(to_decimal(valor)):.2f}".replace(".", ",")


def documento(texto: str, *, con_prefijo: bool) -> str:
    """La cédula. Con «V-» para las transferencias, pelada para pago móvil.

    Los dos formatos salen del mismo dato guardado, que puede venir de las dos
    maneras según cuándo se cargó el beneficiario.
    """
    crudo = str(texto or "").strip().upper()
    letra = crudo[0] if crudo[:1] in ("V", "E", "J", "G", "P") else "V"
    digitos = re.sub(r"\D", "", crudo)
    if not digitos:
        return ""
    return f"{letra}-{digitos}" if con_prefijo else digitos


def _digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def clasificar(beneficiario, *, banco_pagador: str) -> str:
    """A qué sección del archivo va esta orden.

    `banco_pagador` es el código del banco desde el que se paga el lote. Que
    sea un parámetro y no una constante es lo que permite pagar el mismo lote
    desde Banesco un día y desde el Banco de Venezuela al siguiente sin tocar
    código.
    """
    b = beneficiario or {}
    tipo = str(b.get("tipo_pago") or b.get("payment_type") or "").strip().lower()
    codigo = bancos.codigo_de(b)

    if tipo in ("pago_movil", "pagomovil", "pago movil"):
        # El pago móvil necesita teléfono, cédula y banco. Sin los tres no se
        # puede cargar en ningún lado.
        if len(_digitos(b.get("telefono") or b.get("phone"))) < 10:
            return SIN_DATOS
        if not documento(b.get("documento") or b.get("cedula"), con_prefijo=False):
            return SIN_DATOS
        return PAGO_MOVIL if codigo else SIN_DATOS

    # Transferencia: hace falta la cuenta de veinte dígitos.
    cuenta = _digitos(b.get("cuenta") or b.get("account_number"))
    if len(cuenta) != LARGO_DE_CUENTA:
        return SIN_DATOS
    if not codigo:
        # La cuenta empieza con el código del banco. Si el campo del banco no
        # se reconoció, se usa ése antes de rendirse: está en el mismo número
        # que se va a pegar, así que no es una adivinanza.
        codigo = cuenta[:4] if cuenta[:4] in bancos.BANCOS else ""
    if not codigo:
        return SIN_DATOS
    return MISMO_BANCO if codigo == _digitos(banco_pagador) else OTROS_BANCOS


# ─── Cómo se escribe cada línea ───────────────────────────────────────────
#
# Los tres formatos son los que ya se usan a mano, copiados tal cual, incluida
# la cantidad de espacios: quien paga los lee de un vistazo todos los días y
# cambiarle la forma le cuesta más de lo que cualquier mejora le ahorraría.
# Por eso están acá arriba, juntos y a la vista, en vez de repartidos.

def _linea_transferencia(i, b, *, separador):
    return separador.join([
        str(i),
        str(b.get("nombre") or b.get("full_name") or "").strip(),
        documento(b.get("documento") or b.get("cedula"), con_prefijo=True),
        _digitos(b.get("cuenta") or b.get("account_number")),
        "BS",
        monto(b.get("_monto")),
    ])


def _bloque_pago_movil(b):
    """Cuatro líneas: cédula, teléfono, código de banco y monto.

    Sin numerar, porque así se pega: cada bloque se copia entero en el
    formulario del banco, y un número al principio sería un dato de más que hay
    que saltear a mano.
    """
    return "\n".join([
        documento(b.get("documento") or b.get("cedula"), con_prefijo=False),
        _digitos(b.get("telefono") or b.get("phone")),
        bancos.codigo_de(b),
        f"BS {monto(b.get('_monto'))}",
    ])


def _nombre_para_el_archivo(codigo, apodos):
    """El nombre del banco en el encabezado.

    `apodos` permite escribir «BNC» donde el catálogo dice «Banco Nacional de
    Crédito», que es como lo tiene anotado quien paga. Se configura desde el
    panel: obligar a editar código para cambiar un rótulo sería justo lo que
    este repositorio no hace.
    """
    codigo = _digitos(codigo)
    return (apodos or {}).get(codigo) or bancos.nombre_de(codigo)


def armar(ordenes, *, banco_pagador: str, apodos=None) -> dict:
    """El archivo completo, y qué quedó afuera.

    `ordenes` son las que ya vienen elegidas: acá no se filtra por estado ni se
    decide cuáles entran. Esta función sólo da forma, no toma decisiones sobre
    el lote — así se puede probar entera sin base de datos.

    Devuelve `{"texto", "por_seccion", "sin_datos", "total"}`.
    """
    cubos = {PAGO_MOVIL: [], MISMO_BANCO: [], SIN_DATOS: []}
    por_banco = {}

    for orden in ordenes:
        b = dict((orden.get("beneficiario") or {}))
        b["_monto"] = (orden.get("destino") or {}).get("valor", 0)
        b["_orden"] = orden.get("display_id") or orden.get("orden_id")
        seccion = clasificar(b, banco_pagador=banco_pagador)
        if seccion == OTROS_BANCOS:
            codigo = bancos.codigo_de(b) or _digitos(b.get("cuenta") or b.get("account_number"))[:4]
            por_banco.setdefault(codigo, []).append(b)
        else:
            cubos[seccion].append(b)

    partes = []

    if cubos[PAGO_MOVIL]:
        partes.append(f"— {TITULOS[PAGO_MOVIL]} ({len(cubos[PAGO_MOVIL])}) —")
        partes.append("")
        for b in cubos[PAGO_MOVIL]:
            partes.append(_bloque_pago_movil(b))
            partes.append("")

    if cubos[MISMO_BANCO]:
        titulo = _nombre_para_el_archivo(banco_pagador, apodos)
        partes.append(f"— {TITULOS[MISMO_BANCO]}: {titulo} ({len(cubos[MISMO_BANCO])}) —")
        partes.append("")
        for i, b in enumerate(cubos[MISMO_BANCO], 1):
            partes.append(_linea_transferencia(i, b, separador=" "))
            partes.append("")

    if por_banco:
        total_otros = sum(len(v) for v in por_banco.values())
        partes.append(f"— {TITULOS[OTROS_BANCOS]} ({total_otros}) —")
        partes.append("")
        # Los bancos por código, que es un orden estable y el mismo todos los
        # días: si cambiara de lote en lote, quien paga tendría que buscar el
        # suyo cada vez en vez de saber dónde está.
        for codigo in sorted(por_banco):
            grupo = por_banco[codigo]
            partes.append(f"— {_nombre_para_el_archivo(codigo, apodos)} ({len(grupo)}) —")
            partes.append("")
            # La numeración arranca de nuevo en cada banco, porque en la banca
            # en línea se carga un banco por vez y el número es la posición
            # dentro de ESA carga.
            for i, b in enumerate(grupo, 1):
                partes.append(_linea_transferencia(i, b, separador="  "))
                partes.append("")

    if cubos[SIN_DATOS]:
        partes.append(f"— {TITULOS[SIN_DATOS]} ({len(cubos[SIN_DATOS])}) —")
        partes.append("")
        for b in cubos[SIN_DATOS]:
            partes.append(f"{b.get('_orden') or '(sin número)'}  "
                          f"{str(b.get('nombre') or '').strip() or '(sin nombre)'}  "
                          f"BS {monto(b.get('_monto'))}")
            partes.append("")

    return {
        "texto": "\n".join(partes).strip() + "\n" if partes else "",
        "por_seccion": {
            PAGO_MOVIL: len(cubos[PAGO_MOVIL]),
            MISMO_BANCO: len(cubos[MISMO_BANCO]),
            OTROS_BANCOS: sum(len(v) for v in por_banco.values()),
            SIN_DATOS: len(cubos[SIN_DATOS]),
        },
        "sin_datos": [b.get("_orden") for b in cubos[SIN_DATOS]],
        "total": len(list(ordenes)),
    }
