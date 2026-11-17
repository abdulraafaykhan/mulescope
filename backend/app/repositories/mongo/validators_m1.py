"""Full ``$jsonSchema`` validators for the collections M1 writes.

Covers ``customers``, ``accounts``, ``counterparties``, ``transactions``,
``complaints``, ``alerts`` and ``dataset_meta`` with required fields and BSON
types taken from build prompt section 5. Money is ``decimal`` (Decimal128 INR)
and times are ``date`` (UTC). Additional properties are allowed so later
milestones can extend documents. Assembled by ``validators``; not imported
elsewhere.

Optional fields are deliberately not tightened beyond what section 5 states:
values whose closed set is not yet defined (statuses, kinds, directions) are
plain strings, and ``vpa`` on ``accounts`` / ``counterparties`` may be absent
but is a string when present, so a sparse/partial unique index can cover it.
"""

from collections.abc import Mapping
from types import MappingProxyType

from backend.app.domain.enums import Channel, IdPrefix
from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.validators_common import (
    BsonType,
    JsonSchema,
    array_of,
    bson,
    document_validator,
    enum_of,
    nullable,
    obj,
    object_id,
    prefixed_string_id,
    string_id,
)

_STRING = bson(BsonType.STRING)
_DATE = bson(BsonType.DATE)
_MONEY = bson(BsonType.DECIMAL)
_OBJECT = bson(BsonType.OBJECT)
_INTEGER = bson(BsonType.INT, BsonType.LONG)

CUSTOMERS_VALIDATOR: JsonSchema = document_validator(
    prefixed_string_id(IdPrefix.CUSTOMER),
    mutable=True,
    properties={
        "kyc": obj(
            {
                "name": _STRING,
                "dob": _DATE,
                "occupation": _STRING,
                "declared_income": _MONEY,
                "pan_masked": _STRING,
                "city": _STRING,
                "kyc_status": _STRING,
                "kyc_refreshed_at": nullable(BsonType.DATE),
            },
            required=[
                "name",
                "dob",
                "occupation",
                "declared_income",
                "pan_masked",
                "city",
                "kyc_status",
                "kyc_refreshed_at",
            ],
        ),
        "risk_rating": _STRING,
    },
    required=["kyc", "risk_rating"],
)

ACCOUNTS_VALIDATOR: JsonSchema = document_validator(
    prefixed_string_id(IdPrefix.ACCOUNT),
    mutable=True,
    properties={
        "customer_id": prefixed_string_id(IdPrefix.CUSTOMER),
        "account_no": _STRING,
        "ifsc": _STRING,
        "vpa": _STRING,
        "type": _STRING,
        "status": _STRING,
        "opened_at": _DATE,
        "branch": _STRING,
        "balance": _MONEY,
        "declared_monthly_turnover": nullable(BsonType.DECIMAL),
    },
    required=[
        "customer_id",
        "account_no",
        "ifsc",
        "type",
        "status",
        "opened_at",
        "branch",
        "balance",
        "declared_monthly_turnover",
    ],
)

COUNTERPARTIES_VALIDATOR: JsonSchema = document_validator(
    prefixed_string_id(IdPrefix.COUNTERPARTY),
    mutable=True,
    properties={
        "kind": _STRING,
        "display_name": _STRING,
        "vpa": _STRING,
        "bank_ifsc": nullable(BsonType.STRING),
        "first_seen_at": _DATE,
    },
    required=["kind", "display_name", "bank_ifsc", "first_seen_at"],
)

TRANSACTIONS_VALIDATOR: JsonSchema = document_validator(
    object_id(),
    mutable=False,
    properties={
        "transfer_id": _STRING,
        "account_id": prefixed_string_id(IdPrefix.ACCOUNT),
        "direction": _STRING,
        "amount": _MONEY,
        "channel": enum_of([c.value for c in Channel]),
        "ts": _DATE,
        "counterparty": obj(
            {
                "type": _STRING,
                "ref_id": nullable(BsonType.STRING),
                "name": nullable(BsonType.STRING),
            },
            required=["type", "ref_id", "name"],
        ),
        "remarks": nullable(BsonType.STRING),
        "balance_after": _MONEY,
        "status": _STRING,
    },
    required=[
        "transfer_id",
        "account_id",
        "direction",
        "amount",
        "channel",
        "ts",
        "counterparty",
        "remarks",
        "balance_after",
        "status",
    ],
)

COMPLAINTS_VALIDATOR: JsonSchema = document_validator(
    prefixed_string_id(IdPrefix.COMPLAINT),
    mutable=True,
    properties={
        "victim_account_id": _STRING,
        "beneficiary_ref": _STRING,
        "linked_transfer_ids": array_of(_STRING),
        "reported_at": _DATE,
        "amount": _MONEY,
        "status": _STRING,
    },
    required=[
        "victim_account_id",
        "beneficiary_ref",
        "linked_transfer_ids",
        "reported_at",
        "amount",
        "status",
    ],
)

ALERTS_VALIDATOR: JsonSchema = document_validator(
    prefixed_string_id(IdPrefix.ALERT),
    mutable=True,
    properties={
        "account_id": prefixed_string_id(IdPrefix.ACCOUNT),
        "rule_id": _STRING,
        "rule_version": _STRING,
        "window": obj({"start": _DATE, "end": _DATE}, required=["start", "end"]),
        "trigger_metrics": _OBJECT,
        "priority": _INTEGER,
        "status": _STRING,
        "dedupe_key": _STRING,
    },
    required=[
        "account_id",
        "rule_id",
        "rule_version",
        "window",
        "trigger_metrics",
        "priority",
        "status",
        "dedupe_key",
    ],
)

DATASET_META_VALIDATOR: JsonSchema = document_validator(
    string_id(),
    mutable=False,
    properties={
        "seed": _INTEGER,
        "generator_version": _STRING,
        "counts": _OBJECT,
        "generated_at": _DATE,
    },
    required=["seed", "generator_version", "counts", "generated_at"],
)

M1_VALIDATORS: Mapping[str, JsonSchema] = MappingProxyType(
    {
        Col.CUSTOMERS: CUSTOMERS_VALIDATOR,
        Col.ACCOUNTS: ACCOUNTS_VALIDATOR,
        Col.COUNTERPARTIES: COUNTERPARTIES_VALIDATOR,
        Col.TRANSACTIONS: TRANSACTIONS_VALIDATOR,
        Col.COMPLAINTS: COMPLAINTS_VALIDATOR,
        Col.ALERTS: ALERTS_VALIDATOR,
        Col.DATASET_META: DATASET_META_VALIDATOR,
    }
)
"""Full validators keyed by collection name."""
