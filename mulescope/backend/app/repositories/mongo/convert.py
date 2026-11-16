"""Conversions at the repository boundary.

Decimal128 money becomes ``float`` rupees, account numbers are masked to the
last four digits, and ``_id`` becomes ``id`` for read models. Used by every
Mongo repository; nothing above the repositories sees BSON types.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import Decimal128, ObjectId


def to_float(value: Any) -> float:
    """Decimal128 / int / float / None -> float rupees."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    return float(value)


def mask_account_no(account_no: str | None) -> str:
    """``123456789012`` -> ``XXXX9012``."""
    if not account_no:
        return ""
    return f"XXXX{account_no[-4:]}"


def utc(dt: datetime | None) -> datetime | None:
    """Make naive datetimes from the driver explicit UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def plain(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recursively convert BSON values to JSON-friendly Python values."""
    if doc is None:
        return None
    return {("id" if k == "_id" else k): _plain_value(v) for k, v in doc.items()}


def _plain_value(v: Any) -> Any:
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, datetime):
        return utc(v)
    if isinstance(v, dict):
        return {k: _plain_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain_value(x) for x in v]
    return v
