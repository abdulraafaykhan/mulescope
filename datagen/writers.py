"""Turns the generated dataset into documents and bulk-loads MongoDB.

Collections are created with validators and indexes first (``bootstrap``),
then documents are inserted with ``insert_many(ordered=False)`` in batches.
Ground truth goes only to the truth database. Money is Decimal128 INR, times
are UTC datetimes, and account numbers are stored in full (masked at the
repository boundary when read).
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from bson import Decimal128, ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import BulkWriteError

from datagen.context import GenContext
from datagen.ledger import FinalLedger
from datagen.timebase import to_datetime

SCHEMA_VERSION = 1


def money(paise: int) -> Decimal128:
    """Paise -> Decimal128 rupees with two decimals."""
    sign = "-" if paise < 0 else ""
    p = abs(int(paise))
    return Decimal128(f"{sign}{p // 100}.{p % 100:02d}")


def _stamp(doc: dict[str, Any], created: datetime, mutable: bool = True) -> dict[str, Any]:
    doc["created_at"] = created
    if mutable:
        doc["updated_at"] = created
        doc["schema_version"] = SCHEMA_VERSION
    return doc


def customer_docs(ctx: GenContext) -> list[dict[str, Any]]:
    created = to_datetime(ctx.tb.end_ts)
    out = []
    for c in ctx.customers.values():
        out.append(_stamp({
            "_id": c.id,
            "kyc": {
                "name": c.name,
                "dob": datetime(c.dob.year, c.dob.month, c.dob.day, tzinfo=UTC),
                "occupation": c.occupation,
                "declared_income": money(c.declared_income * 100),
                "pan_masked": ctx.names.pan_masked(),
                "city": c.city,
                "kyc_status": c.kyc_status,
                "kyc_refreshed_at": to_datetime(c.kyc_refreshed_ts) if c.kyc_refreshed_ts else None,
            },
            "risk_rating": c.risk_rating,
        }, created))
    return out


def account_docs(ctx: GenContext, final_balance: dict[str, int]) -> list[dict[str, Any]]:
    created = to_datetime(ctx.tb.end_ts)
    out = []
    for a in ctx.accounts.values():
        doc: dict[str, Any] = {
            "_id": a.id,
            "customer_id": a.customer_id,
            "account_no": a.account_no,
            "ifsc": a.ifsc,
            "type": a.type,
            "status": a.status,
            "opened_at": to_datetime(a.opened_ts),
            "branch": a.branch,
            "holder_name": a.holder_name,
            "balance": money(final_balance.get(a.id, 0)),
            "declared_monthly_turnover": money(a.declared_turnover * 100) if a.declared_turnover else None,
        }
        if a.vpa:
            doc["vpa"] = a.vpa
        out.append(_stamp(doc, created))
    return out


def counterparty_docs(ctx: GenContext) -> list[dict[str, Any]]:
    created = to_datetime(ctx.tb.end_ts)
    out = []
    for c in ctx.counterparties.values():
        doc: dict[str, Any] = {"_id": c.id, "kind": c.kind, "display_name": c.display_name, "bank_ifsc": c.bank_ifsc, "first_seen_at": to_datetime(c.first_seen_ts)}
        if c.vpa:
            doc["vpa"] = c.vpa
        out.append(_stamp(doc, created))
    return out


def transaction_docs(ledger: FinalLedger) -> Iterable[dict[str, Any]]:
    cols = ledger.cols
    for i in range(len(ledger)):
        ts = int(cols["ts"][i])
        oid = ObjectId(struct.pack(">I", ts & 0xFFFFFFFF) + struct.pack(">Q", i))
        when = to_datetime(ts)
        cp_type = cols["cp_type"][i]
        yield {
            "_id": oid,
            "transfer_id": str(ledger.transfer_ids[i]),
            "account_id": cols["account"][i],
            "direction": "credit" if int(cols["sign"][i]) > 0 else "debit",
            "amount": money(int(cols["paise"][i])),
            "channel": cols["channel"][i],
            "ts": when,
            "counterparty": {"type": cp_type, "ref_id": cols["cp_ref"][i], "name": cols["cp_name"][i]},
            "remarks": cols["remarks"][i],
            "balance_after": money(int(ledger.balance_after[i])),
            "status": "posted",
            "created_at": when,
        }


def complaint_docs(ctx: GenContext, ledger: FinalLedger) -> list[dict[str, Any]]:
    group_to_tid: dict[int, str] = {}
    wanted = {g for c in ctx.complaints for g in c["groups"]}
    for g, tid in zip(ledger.cols["group"], ledger.transfer_ids, strict=True):
        if int(g) in wanted:
            group_to_tid[int(g)] = str(tid)
    out = []
    for c in ctx.complaints:
        reported = to_datetime(c["reported_ts"])
        out.append(_stamp({
            "_id": ctx.ids.next("CMP-"),
            "victim_account_id": c["victim"],
            "beneficiary_ref": c["beneficiary"],
            "linked_transfer_ids": [group_to_tid[g] for g in c["groups"]],
            "reported_at": reported,
            "amount": money(c["paise"]),
            "status": "open",
        }, reported))
    return out


def truth_docs(ctx: GenContext) -> list[dict[str, Any]]:
    created = to_datetime(ctx.tb.end_ts)
    return [{"_id": f"GT-{t['account_id']}", **t, "created_at": created} for t in ctx.truth]


async def insert_all(db: AsyncDatabase[Any], name: str, docs: Iterable[dict[str, Any]], batch_size: int) -> int:
    """Bulk insert in batches; raises with the first validation error explained."""
    total = 0
    batch: list[dict[str, Any]] = []

    async def flush() -> None:
        nonlocal total
        if not batch:
            return
        try:
            await db[name].insert_many(batch, ordered=False)
        except BulkWriteError as exc:
            first = exc.details.get("writeErrors", [{}])[0]
            raise RuntimeError(f"insert into {name} failed: {first.get('errmsg')} {first.get('errInfo')}") from exc
        total += len(batch)
        batch.clear()

    for doc in docs:
        batch.append(doc)
        if len(batch) >= batch_size:
            await flush()
    await flush()
    return total
