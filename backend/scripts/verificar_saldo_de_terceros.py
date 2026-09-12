"""
scripts/verificar_saldo_de_terceros.py — Quién tiene plata de terceros parada.

PARA QUE SIRVE

    Al desarmar el área de socios gestores desaparece la única pantalla que
    mostraba `balance_ris_terceros`: el saldo donde un gestor guardaba plata
    que NO es suya, sino de sus clientes.

    Borrar la pantalla no borra la plata —sigue en la base—, pero la deja
    donde nadie la mira, que es la peor forma de perderla. Este guion dice, en
    un renglón por persona, quién tiene cuánto.

COMO SE CORRE

    Contra la base de verdad, desde donde esté configurada la conexión
    (por ejemplo, en el servidor de la aplicación):

        python scripts/verificar_saldo_de_terceros.py

    NO ESCRIBE NADA. Sólo lee y muestra. Se puede correr las veces que haga
    falta y en cualquier momento.

QUE ESPERAR

    Si no aparece nadie, el área se puede borrar sin más y no hay plata de
    nadie en juego.

    Si aparece alguien, ESO HAY QUE RESOLVERLO ANTES de desplegar: esa plata
    es de sus clientes, y cuando la pantalla no esté, esa persona no va a
    tener cómo verla ni cómo moverla.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Los dos saldos de terceros que existen. `balance_terceros` es el nombre
# viejo y `balance_ris_terceros` el que usa el código de hoy; se miran los dos
# porque una cuenta vieja puede tener el campo con el nombre anterior.
CAMPOS = ("balance_ris_terceros", "balance_terceros")


async def main() -> int:
    from database import db
    from services.money import from_db, para_mostrar

    filtro = {"$or": [{c: {"$nin": [None, 0, 0.0]}} for c in CAMPOS]}
    proyeccion = {"_id": 0, "user_id": 1, "email": 1, "role": 1,
                  **{c: 1 for c in CAMPOS}}

    gente = await db.users.find(filtro, proyeccion).to_list(None)

    # Se filtra otra vez acá porque un Decimal128 con valor cero NO lo agarra
    # el `$nin` de arriba: para Mongo, Decimal128("0.00") y el entero 0 son
    # valores distintos. Sin esta segunda pasada el listado saldría lleno de
    # cuentas en cero y nadie lo leería.
    con_saldo = []
    for p in gente:
        total = sum((from_db(p.get(c)) for c in CAMPOS), from_db(0))
        if total > 0:
            con_saldo.append((p, total))

    if not con_saldo:
        print("Nadie tiene saldo de terceros. El área se puede borrar sin más.")
        return 0

    print(f"HAY {len(con_saldo)} CUENTA(S) CON PLATA DE TERCEROS.")
    print("Esto hay que resolverlo ANTES de desplegar: es plata de sus")
    print("clientes, y al sacar la pantalla no van a tener cómo verla.\n")
    print(f"{'usuario':<26} {'rol':<14} {'saldo de terceros':>20}")
    print("-" * 62)
    for p, total in sorted(con_saldo, key=lambda x: -x[1]):
        print(f"{(p.get('user_id') or '')[:25]:<26} "
              f"{(p.get('role') or '')[:13]:<14} "
              f"{para_mostrar(total, 'RIS'):>20}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
