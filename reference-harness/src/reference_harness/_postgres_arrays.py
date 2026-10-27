"""The m-dialect *array parameter cast form*: what a Postgres array bind is cast to."""

from __future__ import annotations

# m-core neutral type -> the unmodified PostgreSQL element type an array compared
# with a column of that type is cast to. A decimal casts to bare `decimal`.
_COLUMN_ELEMENTS = {
    "boolean": "boolean",
    "int32": "int",
    "int64": "bigint",
    "float32": "real",
    "float64": "double precision",
    "string": "text",
    "bytes": "bytea",
    "date": "date",
    "time": "time",
    "timestamp": "timestamptz",
    "uuid": "uuid",
}


def column_array_element(neutral_type: str) -> str:
    """The element type of an array compared with a column of *neutral_type*."""
    return "decimal" if neutral_type.startswith("decimal(") else _COLUMN_ELEMENTS[neutral_type]


def column_array_parameter(neutral_type: str) -> str:
    """The cast array parameter compared with a column of *neutral_type*."""
    return f"cast(? as {column_array_element(neutral_type)}[])"
