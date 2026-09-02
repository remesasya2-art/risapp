"""
Diagnóstico de las recargas VES que nacieron sin banco. **NO ESCRIBE NADA.**

POR QUE ESTE SCRIPT NO ARREGLA NADA
    Podría: sabemos resolver un nombre de banco contra contabilidad, y muchas de
    estas recargas tienen el banco en algún lado. Pero cada una de estas filas es
    plata de una persona esperando, y elegirle el banco a una transferencia que
    nadie miró es acreditar contra una cuenta que nadie eligió.

    Las que ya están cargadas las resuelve **una persona**, desde el panel,
    mirando el comprobante. Este script solo dice cuántas son y cómo están, para
    que quien las resuelva sepa el tamaño de lo que tiene delante.

COMO SE USA

    cd backend && python migrations/backfill_recargas_ves_sin_banco.py

Lee la variable de entorno `MONGO_URL` igual que la aplicación. Es de solo
lectura: no tiene una sola escritura, y hay un test que lo verifica sobre el
árbol sintáctico.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient

    url = os.environ.get("MONGO_URL")
    if not url:
        print("Falta MONGO_URL en el entorno.")
        return 1
    cliente = AsyncIOMotorClient(url)
    base = cliente[os.environ.get("DB_NAME", "risapp")]

    pendientes = await base.transactions.count_documents(
        {"type": "recharge_ves", "status": "pending"})
    sin_banco = await base.transactions.count_documents(
        {"type": "recharge_ves", "status": "pending",
         "$or": [{"destination_bank_id": None}, {"destination_bank_id": {"$exists": False}}]})
    sin_comprobante = await base.transactions.count_documents(
        {"type": "recharge_ves", "status": "pending",
         "$or": [{"proof_image": None}, {"proof_image": {"$exists": False}}]})
    # Las que tienen el banco CRUDO pero no el resuelto: son las que la rama de
    # `resolve_ves_bank` puede destrabar sola al aprobarlas, sin que nadie elija.
    con_crudo = await base.transactions.count_documents(
        {"type": "recharge_ves", "status": "pending",
         "destination_bank": {"$nin": [None, ""]},
         "$or": [{"destination_bank_id": None}, {"destination_bank_id": {"$exists": False}}]})

    print(f"Recargas VES pendientes ............... {pendientes}")
    print(f"  sin banco resuelto .................. {sin_banco}")
    print(f"    de esas, con el banco crudo ....... {con_crudo}  "
          f"(se resuelven solas al aprobar)")
    print(f"    a elegir a mano ................... {sin_banco - con_crudo}")
    print(f"  sin comprobante ..................... {sin_comprobante}  "
          f"(hay que confirmarlas con el usuario)")

    bancos = await base.bank_accounts.find(
        {"currency": "VES"}, {"_id": 0, "bank_id": 1, "name": 1}).to_list(200)
    print(f"\nBancos en VES cargados en contabilidad: {len(bancos)}")
    for b in bancos:
        print(f"  {b.get('bank_id')}  {b.get('name')}")
    if not bancos:
        print("  NINGUNO. Sin al menos un banco en VES, las recargas nuevas se van")
        print("  a rechazar al crearse. Cargalos en Contabilidad → Bancos.")

    cliente.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
