"""Parse positional-bind SQL with stable indexed placeholder identities."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.expressions.core import Expr

_PLACEHOLDER_PREFIX = "__parallax_bind_"

# One array parameter, bare or cast to an array type (`?`, `cast(? as bigint[])`).
_ARRAY_PARAMETER = r"(?:\?|cast\s*\(\s*\?\s+as\s+[a-z ]+\[\s*\]\s*\))"

# The array parameters passed as one array each: compared through `any`, or read
# apart as the column arrays of `unnest`.
_ARRAY_PARAMETERS = re.compile(
    rf"\b(?:any\s*\(\s*{_ARRAY_PARAMETER}|unnest\s*\(\s*{_ARRAY_PARAMETER}"
    rf"(?:\s*,\s*{_ARRAY_PARAMETER})*)\s*\)",
    flags=re.IGNORECASE,
)


def array_bind_indexes(statement: str) -> frozenset[int]:
    """The positional indexes of the binds *statement* passes as one array each."""
    indexes: set[int] = set()
    for match in _ARRAY_PARAMETERS.finditer(statement):
        first = statement[: match.start()].count("?")
        indexes.update(range(first, first + match.group().count("?")))
    return frozenset(indexes)


def parse_indexed_statement(statement: str, dialect: str) -> Expr | None:
    try:
        return sqlglot.parse_one(
            _indexed_placeholders(statement),
            read="mysql" if dialect == "mariadb" else dialect,
        )
    except sqlglot.ParseError:
        return None


def placeholder_index(placeholder: exp.Placeholder) -> int | None:
    name = placeholder.this
    if not isinstance(name, str) or not name.startswith(_PLACEHOLDER_PREFIX):
        return None
    try:
        return int(name.removeprefix(_PLACEHOLDER_PREFIX))
    except ValueError:
        return None


def _indexed_placeholders(statement: str) -> str:
    parts: list[str] = []
    quote = ""
    index = 0
    cursor = 0
    while cursor < len(statement):
        character = statement[cursor]
        if quote:
            parts.append(character)
            if character == quote:
                if cursor + 1 < len(statement) and statement[cursor + 1] == quote:
                    parts.append(statement[cursor + 1])
                    cursor += 1
                else:
                    quote = ""
        elif character in "\"'`":
            quote = character
            parts.append(character)
        elif character == "?":
            parts.append(f":{_PLACEHOLDER_PREFIX}{index}")
            index += 1
        else:
            parts.append(character)
        cursor += 1
    return "".join(parts)
