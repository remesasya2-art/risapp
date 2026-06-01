"""
Migration: ensure all legacy documents in accounting-related collections have
the `hidden_from_admin: false` flag explicitly set. This prevents the new
AccountingV2 endpoints from miscounting documents that pre-date the flag.

Idempotent — safe to re-run.

Usage:
    cd /app/backend && python3 -m migrations.001_hidden_from_admin
"""
import asyncio
from database import db


async def run() -> dict:
    results = {}
    collections = [
        "bank_accounts",
        "transactions",
        "usdt_lots",
        "p2p_sales",
        "gateway_fee_ledger",
        "bank_ledger",
    ]
    for coll_name in collections:
        r = await db[coll_name].update_many(
            {"hidden_from_admin": {"$exists": False}},
            {"$set": {"hidden_from_admin": False}},
        )
        results[coll_name] = {
            "matched": r.matched_count,
            "modified": r.modified_count,
        }
    return results


if __name__ == "__main__":
    out = asyncio.run(run())
    for k, v in out.items():
        print(f"{k}: matched={v['matched']} modified={v['modified']}")
