"""``accounts`` and ``customers`` read access, masked at the boundary.

Two small classes, one per collection. Account numbers leave this module as
``account_no_masked`` only; PAN is already stored masked.
"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.convert import mask_account_no, plain


def _masked(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    out = plain(doc)
    if out is None:
        return None
    out["account_no_masked"] = mask_account_no(out.pop("account_no", None))
    return out


class MongoAccountRepository:
    """Reads accounts."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.ACCOUNTS]

    async def get(self, account_id: str) -> dict[str, Any] | None:
        return _masked(await self._col.find_one({"_id": account_id}))

    async def many(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        async for d in self._col.find({"_id": {"$in": ids}}):
            m = _masked(d)
            if m:
                out[m["id"]] = m
        return out

    async def by_customer(self, customer_id: str) -> list[dict[str, Any]]:
        return [m async for d in self._col.find({"customer_id": customer_id}) if (m := _masked(d))]


class MongoCustomerRepository:
    """Reads customers (KYC)."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.CUSTOMERS]

    async def get(self, customer_id: str) -> dict[str, Any] | None:
        return plain(await self._col.find_one({"_id": customer_id}))

    async def many(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        return {d["_id"]: plain(d) async for d in self._col.find({"_id": {"$in": ids}})}  # type: ignore[misc]


class MongoComplaintRepository:
    """Reads fraud complaints."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.COMPLAINTS]

    async def for_beneficiary(self, account_id: str) -> list[dict[str, Any]]:
        return [plain(d) async for d in self._col.find({"beneficiary_ref": account_id})]  # type: ignore[misc]


class MongoCounterpartyRepository:
    """Reads external counterparties."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.COUNTERPARTIES]

    async def many(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        return {d["_id"]: plain(d) async for d in self._col.find({"_id": {"$in": ids}})}  # type: ignore[misc]
