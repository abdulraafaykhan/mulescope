"""Building blocks for MongoDB ``$jsonSchema`` validators.

Small typed helpers that keep the per-collection validator modules
(``validators_m1``, ``validators_baseline``) declarative and consistent with
the section 5 conventions: readable prefixed string ``_id`` or ``ObjectId``,
Decimal128 money, UTC ``date`` times, ``created_at`` on every document and
``updated_at`` + ``schema_version`` on mutable ones. Used only by the
validator modules in this package.
"""

import re
from collections.abc import Mapping, Sequence
from enum import StrEnum, unique
from typing import Any

from backend.app.domain.enums import IdPrefix

JsonSchema = dict[str, Any]
"""A ``$jsonSchema`` fragment or a full validator document."""

ID = "_id"
CREATED_AT = "created_at"
UPDATED_AT = "updated_at"
SCHEMA_VERSION = "schema_version"

ID_SUFFIX_PATTERN = "[A-Za-z0-9]+$"
"""Suffix after an ``IdPrefix``: the readable id body, e.g. ``000123``."""


@unique
class BsonType(StrEnum):
    """BSON type aliases accepted by the ``$jsonSchema`` ``bsonType`` keyword."""

    STRING = "string"
    OBJECT_ID = "objectId"
    DATE = "date"
    DECIMAL = "decimal"
    INT = "int"
    LONG = "long"
    DOUBLE = "double"
    BOOL = "bool"
    OBJECT = "object"
    ARRAY = "array"
    NULL = "null"


def bson(*types: BsonType) -> JsonSchema:
    """Build a field schema that accepts the given BSON types.

    Args:
        *types: One or more accepted BSON types.

    Returns:
        A schema fragment with a ``bsonType`` keyword.
    """
    values = [str(t) for t in types]
    return {"bsonType": values[0] if len(values) == 1 else values}


def nullable(*types: BsonType) -> JsonSchema:
    """Build a field schema that accepts the given types or ``null``.

    Args:
        *types: Accepted non-null BSON types.

    Returns:
        A schema fragment accepting ``types`` plus ``null``.
    """
    return bson(*types, BsonType.NULL)


def enum_of(values: Sequence[str]) -> JsonSchema:
    """Build a string field schema restricted to a closed set.

    Args:
        values: Allowed values, typically the members of a domain ``StrEnum``.

    Returns:
        A string schema fragment with an ``enum`` keyword.
    """
    return {"bsonType": str(BsonType.STRING), "enum": list(values)}


def array_of(items: JsonSchema) -> JsonSchema:
    """Build an array field schema.

    Args:
        items: Schema every array element must satisfy.

    Returns:
        An array schema fragment.
    """
    return {"bsonType": str(BsonType.ARRAY), "items": items}


def obj(properties: Mapping[str, JsonSchema], required: Sequence[str]) -> JsonSchema:
    """Build an embedded-object schema.

    Additional properties are allowed so that later milestones can extend
    documents without breaking existing data.

    Args:
        properties: Schema per property name.
        required: Property names that must be present.

    Returns:
        An object schema fragment.
    """
    schema: JsonSchema = {"bsonType": str(BsonType.OBJECT), "properties": dict(properties)}
    if required:
        schema["required"] = list(required)
    return schema


def prefixed_string_id(prefix: IdPrefix) -> JsonSchema:
    """Build the ``_id`` schema for a business entity with a readable id.

    Args:
        prefix: The entity's id prefix, e.g. ``IdPrefix.ACCOUNT`` (``ACC-``).

    Returns:
        A string schema whose ``pattern`` anchors the prefix, e.g. ``^ACC-...$``.
    """
    return {
        "bsonType": str(BsonType.STRING),
        "pattern": f"^{re.escape(prefix.value)}{ID_SUFFIX_PATTERN}",
    }


def object_id() -> JsonSchema:
    """Build the ``_id`` schema for high-volume or append-only collections.

    Returns:
        A schema fragment requiring an ``ObjectId``.
    """
    return bson(BsonType.OBJECT_ID)


def string_id() -> JsonSchema:
    """Build the ``_id`` schema for collections keyed by a plain string.

    Returns:
        A schema fragment requiring a string.
    """
    return bson(BsonType.STRING)


def document_validator(
    id_schema: JsonSchema,
    *,
    mutable: bool,
    properties: Mapping[str, JsonSchema] | None = None,
    required: Sequence[str] = (),
) -> JsonSchema:
    """Assemble a full ``{"$jsonSchema": ...}`` validator for a collection.

    Adds the convention fields: ``_id`` and ``created_at`` (``date``) are always
    required; ``updated_at`` (``date``) and ``schema_version`` (``int``) are
    required too when ``mutable`` is true.

    Args:
        id_schema: Schema for ``_id``.
        mutable: Whether documents in the collection are updated after insert.
        properties: Collection-specific field schemas.
        required: Collection-specific required field names.

    Returns:
        A validator document ready to pass as ``validator=`` to MongoDB.
    """
    props: dict[str, JsonSchema] = {ID: id_schema, CREATED_AT: bson(BsonType.DATE)}
    required_fields: list[str] = [ID, CREATED_AT]
    if mutable:
        props[UPDATED_AT] = bson(BsonType.DATE)
        props[SCHEMA_VERSION] = bson(BsonType.INT)
        required_fields += [UPDATED_AT, SCHEMA_VERSION]
    if properties:
        props.update(properties)
    required_fields += [name for name in required if name not in required_fields]
    return {
        "$jsonSchema": {
            "bsonType": str(BsonType.OBJECT),
            "required": required_fields,
            "properties": props,
        }
    }
