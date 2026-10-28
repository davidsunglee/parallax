"""Parse positional-bind SQL with stable indexed placeholder identities."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.expressions.core import Expr

_PLACEHOLDER_PREFIX = "__parallax_bind_"

# One array parameter compared through `any`, bare or cast to an array type
# (`any(?)`, `any(cast(? as bigint[]))`).
_ANY_ARRAY_PARAMETER = re.compile(
    r"\bany\s*\(\s*(?:\?|cast\s*\(\s*\?\s+as\s+[a-z ]+\[\s*\]\s*\))\s*\)",
    flags=re.IGNORECASE,
)

_UNNEST = re.compile(r"\bunnest\s*\(", flags=re.IGNORECASE)


def array_bind_indexes(statement: str) -> frozenset[int]:
    """The positional indexes of the binds the PostgreSQL *statement* passes as one
    array each: compared through ``any``, or read apart as an ``unnest`` argument
    that binds one placeholder through casts and parentheses alone, as the
    column-array INSERT recognizer reads it."""
    indexes = {
        statement[: match.start()].count("?") for match in _ANY_ARRAY_PARAMETER.finditer(statement)
    }
    tree = parse_indexed_statement(statement, "postgres") if _UNNEST.search(statement) else None
    if tree is not None:
        indexes.update(
            index
            for unnest in tree.find_all(exp.Unnest)
            for argument in unnest.expressions
            if (index := bound_placeholder_index(argument)) is not None
        )
    return frozenset(indexes)


def bound_placeholder_index(expression: Expr) -> int | None:
    """The index of the one placeholder *expression* binds, seen through casts
    and parentheses alone."""
    placeholders = tuple(expression.find_all(exp.Placeholder))
    if isinstance(expression, exp.Placeholder):
        placeholders = (expression,)
    if len(placeholders) != 1 or not transparent_placeholder(expression, placeholders[0]):
        return None
    return placeholder_index(placeholders[0])


def transparent_placeholder(expression: Expr, placeholder: exp.Placeholder) -> bool:
    """Whether *expression* is *placeholder* wrapped in casts and parentheses alone."""
    current: Expr = placeholder
    while current is not expression:
        parent = current.parent
        if parent is None or not isinstance(parent, (exp.Cast, exp.Paren)):
            return False
        current = parent
    return True


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
