"""Adapt logical statement binds at dialect-owned JSON mutation expressions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlglot
from sqlglot import exp

from ..document_codec import is_document


def adapt_document_scalar_binds(
    statement: str,
    binds: Sequence[Any],
    dialect: str,
) -> tuple[Any, ...]:
    """Render logical JSON scalars as the text a document mutation expression parses."""
    try:
        tree = sqlglot.parse_one(_indexed_placeholders(statement), read=_sqlglot_dialect(dialect))
    except sqlglot.ParseError:
        return tuple(binds)
    scalar_indices = {
        index
        for placeholder in tree.find_all(exp.Placeholder)
        if (index := _placeholder_index(placeholder)) is not None
        and _is_document_mutation_value(placeholder, dialect)
    }
    return tuple(
        json.dumps(value) if index in scalar_indices and not is_document(value) else value
        for index, value in enumerate(binds)
    )


def _is_document_mutation_value(placeholder: exp.Placeholder, dialect: str) -> bool:
    parent = placeholder.parent
    if dialect == "postgres":
        if not isinstance(parent, exp.Cast):
            return False
        function = parent.parent
        return isinstance(function, exp.Anonymous) and function.name.lower() == "jsonb_set"
    if dialect == "mariadb":
        return isinstance(parent, exp.JSONExtract) and isinstance(parent.parent, exp.JSONSet)
    return False


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
            parts.append(f":__parallax_bind_{index}")
            index += 1
        else:
            parts.append(character)
        cursor += 1
    return "".join(parts)


def _placeholder_index(placeholder: exp.Placeholder) -> int | None:
    name = placeholder.this
    prefix = "__parallax_bind_"
    if not isinstance(name, str) or not name.startswith(prefix):
        return None
    try:
        return int(name.removeprefix(prefix))
    except ValueError:
        return None


def _sqlglot_dialect(dialect: str) -> str:
    return "mysql" if dialect == "mariadb" else dialect
