#!/usr/bin/env python3
"""
La herramienta del cofre. Crear la llave, comprobarla y cifrar lo que ya está.

    python backend/scripts/cofre.py crear       genera una llave nueva
    python backend/scripts/cofre.py estado      dice cómo está todo hoy
    python backend/scripts/cofre.py verificar   ¿la llave que tengo es la buena?
    python backend/scripts/cofre.py cifrar      cifra los documentos ya guardados

POR QUE ESTO ES UN SCRIPT Y NO UN BOTON EN EL PANEL

    `cifrar` reescribe documentos de identidad de personas reales. Una operación
    así la dispara una persona, a una hora que eligió, después de leer qué hace
    y con un respaldo de la base a mano. Un botón invita a apretarlo.

    El mismo criterio que `backfill_recargas_ves_sin_banco.py`.

QUE HACE `cifrar`, EXACTAMENTE

    Recorre las verificaciones y, para cada documento en claro:

      1. lo cifra,
      2. LO ABRE DE NUEVO y comprueba que vuelve idéntico al original,
      3. recién ahí lo escribe.

    Si el paso 2 falla, no escribe y sigue con el siguiente. Nunca reemplaza un
    documento por algo que no se pudo comprobar que se recupera: la única forma
    de perder una foto sería escribir primero y confiar.

    Se puede cortar y volver a correr. Lo ya cifrado se saltea.

LO QUE NO HACE

    No borra nada, no toca `cpf_number` ni `document_number`, y no cambia
    ninguna variable de entorno. Prender el cofre es una decisión aparte.
"""
import argparse
import asyncio
import base64
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _cofre():
    from services import cofre
    return cofre


# ══════════════════════════════════════════════════════════════════════════
# crear
# ══════════════════════════════════════════════════════════════════════════

def crear(_args):
    cofre = _cofre()
    llave = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    huella = cofre.huella(base64.urlsafe_b64decode(llave))

    print()
    print("═" * 72)
    print("  LLAVE NUEVA DEL COFRE")
    print("═" * 72)
    print()
    print(f"  COFRE_LLAVE={llave}")
    print()
    print(f"  Huella: {huella}")
    print()
    print("─" * 72)
    print("  ESTO NO SE VUELVE A MOSTRAR. Y no hay forma de recuperarla:")
    print("  sin esta llave, los documentos cifrados con ella se pierden.")
    print()
    print("  ANTES de prender el cofre, dejá la llave en TRES lugares que no")
    print("  fallen juntos:")
    print()
    print("    1. La variable COFRE_LLAVE en el servidor.")
    print("    2. Un gestor de contraseñas (1Password, Bitwarden, el que uses).")
    print("    3. Escrita a mano en papel, guardada donde guardás lo importante.")
    print()
    print("  La HUELLA sí se puede compartir y anotar en cualquier lado: no")
    print("  revela la llave. Sirve para reconocer cuál es cuál.")
    print()
    print("  Cuando la tengas guardada, comprobá que copiaste bien:")
    print()
    print("    COFRE_LLAVE='<la que anotaste>' \\")
    print("      python backend/scripts/cofre.py verificar")
    print()
    print("  Ver docs/la-llave-del-cofre.md para los pasos completos.")
    print("═" * 72)
    print()
    return 0


# ══════════════════════════════════════════════════════════════════════════
# estado / verificar
# ══════════════════════════════════════════════════════════════════════════

async def _con_base(funcion):
    from database import db
    return await funcion(db)


def _sin_base(e):
    """Un traceback de veinte líneas no le dice a nadie qué hacer.

    Este script lo corre una persona en su computadora, probablemente apurada y
    con la base en otro lado. El error más común de todos es no tener puesta la
    dirección de la base, y merece una frase y no un volcado de pila.
    """
    print()
    print("  No se pudo hablar con la base de datos.")
    print()
    print("  Casi siempre es esto: falta la variable MONGO_URL, o apunta a una")
    print("  base que no está corriendo. Probá:")
    print()
    print("    MONGO_URL='<la de producción>' DB_NAME='<la base>' \\")
    print("      python backend/scripts/cofre.py <la orden>")
    print()
    print(f"  El detalle técnico, por si sirve: {type(e).__name__}")
    print()
    return 2


def estado(_args):
    cofre = _cofre()
    try:
        info = asyncio.run(_con_base(cofre.revisar))
    except Exception as e:
        return _sin_base(e)

    print()
    print(f"  Modo               : {info['modo']}")
    print(f"  Llave puesta       : {'sí' if info['hay_llave'] else 'NO'}")
    print(f"  Huella de la llave : {info['huella']}")
    print(f"  Llave anterior     : {'sí' if info['hay_llave_anterior'] else 'no'}")
    print(f"  Estado             : {'BIEN' if info['ok'] else '*** MAL ***'}")
    print(f"  {info['detalle']}")
    print()
    return 0 if info["ok"] else 1


def verificar(_args):
    """¿La llave que tengo a mano es la que cifró los documentos?

    Es la pregunta que hay que poder contestar sin restaurar nada, y sin la
    cual «respaldá la llave» es un consejo que nadie puede comprobar que siguió.
    """
    cofre = _cofre()
    if not cofre.llave_actual():
        print("\n  No hay una llave válida en COFRE_LLAVE.\n")
        return 1

    try:
        info = asyncio.run(_con_base(cofre.revisar))
    except Exception as e:
        print(f"\n  La llave se lee bien. Huella: {cofre.huella()}")
        return _sin_base(e)
    print()
    if info.get("motivo") == "sin_base":
        # Se dice lo que SI se sabe —la llave se lee y ésta es su huella— y se
        # separa de lo que no se pudo comprobar. Decir «la llave está mal»
        # cuando la base está caída manda a alguien a tocar justo lo que no hay
        # que tocar.
        print(f"  La llave se lee bien. Huella: {info['huella']}")
        print("  Pero no se pudo llegar a la base para comprobar que sea LA de")
        print("  los documentos. NO cambies la llave por esto.")
        return _sin_base(RuntimeError("sin base"))
    if info["modo"] == "apagado":
        print(f"  La llave se lee bien. Huella: {info['huella']}")
        print("  El cofre está apagado, así que no hay con qué compararla todavía.")
    elif info["ok"]:
        print(f"  SI: la llave de huella {info['huella']} es la correcta.")
        print("  Con ésta se abren los documentos guardados.")
    else:
        print(f"  NO: {info['detalle']}")
    print()
    return 0 if info["ok"] else 1


# ══════════════════════════════════════════════════════════════════════════
# cifrar
# ══════════════════════════════════════════════════════════════════════════

async def _cifrar(db, limite, seco):
    cofre = _cofre()
    if cofre.modo() != "cifrando":
        print("\n  COFRE_MODO no está en «cifrando». Prendelo antes de migrar,")
        print("  para que lo que se cifre acá se pueda seguir escribiendo así.\n")
        return 1
    if not cofre.llave_actual():
        print("\n  No hay una llave válida en COFRE_LLAVE.\n")
        return 1

    print(f"\n  Llave de huella {cofre.huella()}"
          f"{'  (SIMULACRO: no se escribe nada)' if seco else ''}\n")

    await cofre.sellar_testigo(db)

    mirados = cifrados = saltados = fallados = 0
    cursor = db.verifications.find({})
    async for v in cursor:
        if limite and mirados >= limite:
            break
        mirados += 1

        cambios = {}
        roto = False
        for campo in cofre.CAMPOS_KYC:
            original = v.get(campo)
            if not isinstance(original, str) or not original:
                continue
            if cofre.esta_cifrado(original):
                continue

            sellado = cofre.guardar(original)
            # LA COMPROBACION QUE HACE QUE ESTO SEA SEGURO: se abre lo que se
            # acaba de cerrar y se exige que vuelva idéntico. Sin este paso,
            # migrar es reemplazar una foto por algo que nadie miró.
            if cofre.abrir(sellado) != original:
                print(f"  !! {v.get('verification_id')} / {campo}: "
                      "no vuelve idéntico. NO se toca.")
                roto = True
                continue
            cambios[campo] = sellado

        if roto:
            fallados += 1
            continue
        if not cambios:
            saltados += 1
            continue

        if not seco:
            await db.verifications.update_one({"_id": v["_id"]}, {"$set": cambios})
        cifrados += 1
        if cifrados % 25 == 0:
            print(f"  ... {cifrados} verificaciones cifradas")

    print()
    print(f"  Miradas          : {mirados}")
    print(f"  Cifradas         : {cifrados}")
    print(f"  Ya estaban / sin documentos : {saltados}")
    print(f"  Con problemas    : {fallados}")
    if fallados:
        print("\n  Las que fallaron quedaron COMO ESTABAN. Revisalas antes de seguir.")
    print()
    return 1 if fallados else 0


def cifrar(args):
    from database import db
    try:
        return asyncio.run(_cifrar(db, args.limite, args.simulacro))
    except Exception as e:
        return _sin_base(e)


# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="orden", required=True)

    sub.add_parser("crear", help="genera una llave nueva")
    sub.add_parser("estado", help="cómo está el cofre hoy")
    sub.add_parser("verificar", help="¿la llave que tengo es la buena?")

    p = sub.add_parser("cifrar", help="cifra los documentos ya guardados")
    p.add_argument("--simulacro", action="store_true",
                   help="hace todo menos escribir. Corré esto primero.")
    p.add_argument("--limite", type=int, default=0,
                   help="mirar sólo las primeras N verificaciones")

    args = parser.parse_args()
    return {"crear": crear, "estado": estado,
            "verificar": verificar, "cifrar": cifrar}[args.orden](args)


if __name__ == "__main__":
    sys.exit(main())
