"""Adapt logical statement binds at dialect-owned JSON mutation expressions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlglot import exp

from .._sql_placeholders import parse_indexed_statement, placeholder_index
from ..document_codec import is_document


def adapt_document_scalar_binds(
    statement: str,
    binds: Sequence[Any],
    dialect: str,
) -> tuple[Any, ...]:
    """Render logical JSON scalars as the text a document mutation expression parses."""
    tree = parse_indexed_statement(statement, dialect)
    if tree is None:
        return tuple(binds)
    scalar_indices = {
        index
        for placeholder in tree.find_all(exp.Placeholder)
        if (index := placeholder_index(placeholder)) is not None
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
