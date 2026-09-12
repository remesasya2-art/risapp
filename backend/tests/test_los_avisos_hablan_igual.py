"""
tests/test_los_avisos_hablan_igual.py — Que los avisos suenen a una sola voz.

LO QUE PASABA

    Veintidós avisos de dinero, escritos por turnos a lo largo de meses, y
    ninguno parecido al otro:

        ✅ Retiro Completado          Retiro Completado
        ❌ Recarga VES Rechazada      Deposito confirmado
        💰 Pago PIX Confirmado        Pago recibido
        💳 Pago con Tarjeta Aprobado  Envío Solicitado

    Emoji en siete de veintidós. Mayúsculas en cada palabra, que es cómo se
    escribe en inglés y no en español. Acentos faltando en «Deposito», «sera»
    y «esta». Y la plata con `f"{x:.2f}"`, que da «4500.00»: punto decimal y
    sin separador de miles, o sea el formato de otro país.

    Leídos de a uno no se nota. Leídos juntos en la bandeja parecen de cuatro
    empresas distintas, y eso es exactamente lo que hace dudar de si un correo
    que habla de tu plata es de verdad.

POR QUE HAY UN TEST Y NO SOLO UNA CONVENCION ESCRITA

    Porque la convención escrita ya existía —el repositorio entero está en
    español llano— y aun así pasó. Estos avisos se agregan de a uno, meses
    aparte, y quien agrega el número veintitrés no va a leer los otros
    veintidós.
"""
import ast
import os
import pathlib
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

# Las clases de aviso que le hablan al usuario de su plata o de su paquete.
# Los avisos de trabajo —«hay un KYC nuevo»— no están: los lee el equipo en el
# panel y no tienen por qué sonar igual.
AL_USUARIO = {
    "withdrawal_pending", "withdrawal_completed", "withdrawal_rejected",
    "recharge_approved", "recharge_rejected", "pix_received", "card_received",
    "credit_deposit", "btc_payment", "crypto_send_paid", "crypto_send_refunded",
    "crypto_send_awaiting_topup", "crypto_send_underpaid_review",
    "btc_enviado", "btc_remesa_enviada", "gestor_transaction", "partner_bonus",
    "envio",
}

# Lo que SI va con mayúscula en medio de una frase: nombres propios, marcas y
# monedas. Todo lo demás en minúscula, como se escribe en español.
NOMBRES_PROPIOS = {
    "RIS", "VES", "BRL", "BTC", "USDT", "USDC", "USD", "PIX", "KYC", "APP",
    "Bitcoin", "Brasil", "Venezuela", "Pacaraima", "Santa", "Elena",
    "App", "BTC-VES", "Bs", "R$", "Motivo",
}


def avisos_al_usuario():
    """Cada `create_notification` que le habla al usuario: (archivo, línea,
    clase, título literal, mensaje literal).

    Se lee el ARBOL y no el texto. Con una expresión regular, un emoji dentro
    de un comentario contaría como si estuviera en un título.
    """
    raiz = pathlib.Path(_BACKEND)
    for archivo in sorted(raiz.glob("routes/*.py")) + sorted(raiz.glob("services/*.py")):
        arbol = ast.parse(archivo.read_text(), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
            if nombre != "create_notification":
                continue
            claves = {k.arg: k.value for k in nodo.keywords if k.arg}
            tipo = claves.get("notification_type")
            if not (isinstance(tipo, ast.Constant) and tipo.value in AL_USUARIO):
                continue
            titulo = claves.get("title")
            mensaje = claves.get("message")
            yield (str(archivo.relative_to(raiz)), nodo.lineno, tipo.value,
                   titulo.value if isinstance(titulo, ast.Constant) else None,
                   ast.unparse(mensaje) if mensaje is not None else "")


def test_la_guarda_encuentra_los_avisos_que_persigue():
    """Una guarda que no encuentra nada pasa siempre."""
    todos = list(avisos_al_usuario())
    assert len(todos) >= 20, todos
    assert len({t for _, _, t, _, _ in todos}) >= 12


def hay_emoji(texto: str) -> bool:
    """Un emoji, y no cualquier carácter raro: las tildes y la ñ están muy por
    debajo de este límite, y las comillas tipográficas también."""
    return any(ord(c) >= 0x2190 for c in texto or "")


def test_ningun_titulo_lleva_emoji():
    """Siete de veintidós llevaban. Un asunto de correo con emoji lo marcan
    como promoción varios programas, y un aviso de que se movió tu plata no
    puede terminar en la pestaña de promociones."""
    con = [(a, l, t) for a, l, _, t, _ in avisos_al_usuario() if hay_emoji(t)]
    assert con == [], con


def test_la_guarda_del_emoji_reconoce_un_emoji():
    assert hay_emoji("✅ Retiro Completado")
    assert hay_emoji("💰 Comisión")
    # y no se confunde con el español
    assert not hay_emoji("Tu envío se completó")
    assert not hay_emoji("Tu depósito de R$ 250,00 está acreditado")


def palabras_en_mayuscula_de_mas(titulo: str):
    """Las palabras con mayúscula que no deberían tenerla.

    En español sólo va en mayúscula la primera palabra y los nombres propios.
    «Retiro Completado» es la forma inglesa, y conviviendo con «Pago recibido»
    se lee como dos empresas.
    """
    palabras = re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ$-]+", titulo or "")
    return [p for p in palabras[1:]
            if p[:1].isupper() and p not in NOMBRES_PROPIOS]


def test_los_titulos_estan_escritos_en_espanol_y_no_en_ingles():
    malos = [(a, l, t, palabras_en_mayuscula_de_mas(t))
             for a, l, _, t, _ in avisos_al_usuario()
             if t and palabras_en_mayuscula_de_mas(t)]
    assert malos == [], malos


def test_la_guarda_de_las_mayusculas_distingue_los_dos_casos():
    assert palabras_en_mayuscula_de_mas("Retiro Completado") == ["Completado"]
    assert palabras_en_mayuscula_de_mas("Pago con Tarjeta Aprobado") == [
        "Tarjeta", "Aprobado"]
    # y deja pasar el español correcto, con sus nombres propios
    assert palabras_en_mayuscula_de_mas("Tu retiro se completó") == []
    assert palabras_en_mayuscula_de_mas("Recibimos tu pago por PIX") == []
    assert palabras_en_mayuscula_de_mas("Tu envío a Brasil está en cola") == []


# `4500.00` en vez de `4.500,00`. Atrapa `:.2f`, `:,.2f` y `:.8f`.
PLATA_A_MANO = re.compile(r"\{[^{}]*:,?\.\d+f\}")


def test_la_plata_de_los_avisos_pasa_por_el_formateador():
    """`f"{x:.2f}"` da «4500.00»: punto decimal y sin separador de miles. Es el
    formato de otro país, y convivía con el correcto en la misma bandeja.

    `services/money.para_mostrar` es el único lugar donde se decide cómo se
    escribe un monto. Antes había tres: eso, una función privada en
    `services/limits.py`, y `:.2f` suelto en los avisos.
    """
    malos = [(a, l, t, PLATA_A_MANO.findall(m))
             for a, l, t, _, m in avisos_al_usuario()
             if PLATA_A_MANO.search(m)]
    assert malos == [], malos


def test_la_guarda_del_formato_reconoce_los_tres_casos_que_habia():
    for viejo in ('f"Tu retiro de {x:.2f} VES"',
                  'f"Tu envío de {y:,.2f} Bs"',
                  'f"Te acreditamos {z:.8f} BTC"'):
        assert PLATA_A_MANO.search(viejo), viejo
    # y deja pasar lo que ya pasa por el formateador
    assert not PLATA_A_MANO.search('f"Ya enviamos {para_mostrar(x, \'VES\')}"')


def test_el_formateador_escribe_la_plata_como_se_lee():
    from services.money import para_mostrar
    assert para_mostrar("4500", "VES") == "4.500,00 VES"
    assert para_mostrar("1234567.891", "Bs") == "1.234.567,89 Bs"
    assert para_mostrar("0.5") == "0,50"
    # y vacío, no «0,00», cuando no hay monto: «0,00 Bs» se lee como «no te
    # mandamos nada», que es una acusación y no un dato que falta.
    assert para_mostrar(None, "VES") == ""
    assert para_mostrar("", "VES") == ""


def test_no_quedan_dos_formateadores_de_plata():
    """`services/comprobante.plata` es un alias y no una copia. Con dos
    copias, el mismo monto se ve distinto en el correo y en el aviso."""
    fuente = (pathlib.Path(_BACKEND) / "services" / "comprobante.py").read_text()
    cuerpo = fuente.split("def plata(", 1)[1].split("\ndef ", 1)[0]
    assert "para_mostrar" in cuerpo
    # y no rehace la cuenta por su cuenta
    assert ":,." not in cuerpo
