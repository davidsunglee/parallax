"""Read a PostgreSQL grouped effect as the keyed updates it applies, one per row.

A grouped effect (`m-sql` *Grouped effects*) is one ``update <table> t set … from
unnest(cast(? as T[]), …) with ordinality v(c1, …, ord) where … returning v.ord``
statement: row ``i`` of its source carries the per-row values of the ``i``-th
keyed update it applies, read wherever the statement names ``v.cN``. Spelling each
row back as the lone update it stands for lets every per-row cross-check grade a
grouped golden exactly as it grades one statement per row, without restating any
production layout rule here.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sqlglot import exp
from sqlglot.expressions.core import Expr

from ._sql_placeholders import (
    bound_placeholder_index,
    parse_indexed_statement,
    placeholder_index,
)
from .sql_normalize import normalize

_LONE_PREFIX = "__parallax_lone_"
_LONE_PLACEHOLDER = re.compile(r"%\(" + _LONE_PREFIX + r"\d+\)s")


class GroupedEffectShapeError(ValueError):
    """A grouped effect whose source does not bind one equal-length array per
    source column, or that returns anything but its source ordinal."""


def ungrouped_effect(statement: str, binds: Sequence[Any]) -> list[tuple[str, list[Any]]] | None:
    """Each keyed update the grouped effect *statement* applies, in source order,
    as the canonical lone ``update`` it stands for with its own binds; ``None``
    for any other statement.

    Every ``v.cN`` the statement reads becomes that row's element of the array
    bound to source column ``cN`` — cast to ``jsonb`` where the array is a
    ``jsonb[]``, as a lone document path assignment casts its value — every
    shared scalar keeps its own bind, and the target alias is dropped.
    """
    tree = parse_indexed_statement(statement, "postgres")
    if not isinstance(tree, exp.Update):
        return None
    source = _source(tree)
    if source is None:
        return None
    unnest, alias, ordinal = source
    columns = [identifier.name for identifier in alias.columns]
    arguments = list(unnest.expressions)
    if len(columns) != len(arguments):
        raise GroupedEffectShapeError(
            f"names {len(columns)} source column(s) for {len(arguments)} array(s)"
        )
    returning = tree.args.get("returning")
    returned = None if returning is None else returning.expressions
    if (
        not returned
        or len(returned) != 1
        or not isinstance(returned[0], exp.Column)
        or returned[0].table != alias.name
        or returned[0].name != ordinal
    ):
        raise GroupedEffectShapeError(f"returns something other than {alias.name}.{ordinal}")
    arrays: dict[str, list[Any]] = {}
    documents: set[str] = set()
    for column, argument in zip(columns, arguments, strict=True):
        index = bound_placeholder_index(argument)
        value = binds[index] if index is not None and index < len(binds) else None
        if not isinstance(value, list):
            raise GroupedEffectShapeError(f"binds source column {column} to no array")
        arrays[column] = value
        if isinstance(argument, exp.Cast) and "jsonb" in argument.to.sql("postgres").lower():
            documents.add(column)
    lengths = {len(values) for values in arrays.values()}
    if len(lengths) != 1:
        raise GroupedEffectShapeError(f"binds source arrays of unequal lengths {sorted(lengths)}")
    (rows,) = lengths
    target = tree.this.alias_or_name if isinstance(tree.this, exp.Table) else ""
    return [_lone(tree, alias.name, target, arrays, documents, binds, row) for row in range(rows)]


def _source(tree: exp.Update) -> tuple[exp.Unnest, exp.TableAlias, str] | None:
    source = tree.args.get("from_")
    unnest = source.this if isinstance(source, exp.From) else None
    if not isinstance(unnest, exp.Unnest):
        return None
    alias = unnest.args.get("alias")
    ordinal = unnest.args.get("offset")
    if not isinstance(alias, exp.TableAlias) or not isinstance(ordinal, exp.Identifier):
        raise GroupedEffectShapeError("reads an unnest source without an alias and ordinality")
    return unnest, alias, ordinal.name


def _lone(
    tree: exp.Update,
    source: str,
    target: str,
    arrays: dict[str, list[Any]],
    documents: set[str],
    binds: Sequence[Any],
    row: int,
) -> tuple[str, list[Any]]:
    lone = tree.copy()
    lone.set("from_", None)
    lone.set("returning", None)
    table = lone.this
    if isinstance(table, exp.Table):
        table.set("alias", None)
    lone_binds: list[Any] = []
    for node in list(lone.walk(bfs=False)):
        if isinstance(node, exp.Column) and node.table == source:
            marker: Expr = _marker(len(lone_binds))
            lone_binds.append(arrays[node.name][row])
            if node.name in documents:
                marker = exp.Cast(this=marker, to=exp.DataType.build("jsonb"))
            node.replace(marker)
        elif isinstance(node, exp.Column) and node.table == target:
            node.set("table", None)
        elif isinstance(node, exp.Placeholder):
            index = placeholder_index(node)
            if index is not None:
                lone_binds.append(binds[index])
                node.replace(_marker(len(lone_binds) - 1))
    rendered = _LONE_PLACEHOLDER.sub("?", lone.sql(dialect="postgres"))
    return normalize(rendered, "postgres"), lone_binds


def _marker(index: int) -> exp.Placeholder:
    return exp.Placeholder(this=f"{_LONE_PREFIX}{index}")


def sourced_path_value_indexes(statement: str) -> frozenset[int]:
    """The positional indexes of the arrays whose elements a PostgreSQL grouped
    effect assigns at a document path (``jsonb_set(…, ?, v.cN)``).

    Each element is one path's JSON value, ``null`` included: a path assignment
    writes JSON ``null`` rather than SQL ``NULL``, which would null the whole
    document ``jsonb_set`` returns.
    """
    tree = parse_indexed_statement(statement, "postgres")
    if not isinstance(tree, exp.Update):
        return frozenset()
    try:
        source = _source(tree)
    except GroupedEffectShapeError:
        return frozenset()
    if source is None:
        return frozenset()
    unnest, alias, _ordinal = source
    arguments = dict(
        zip((column.name for column in alias.columns), unnest.expressions, strict=False)
    )
    indexes: set[int] = set()
    for function in tree.find_all(exp.Anonymous):
        if function.name.lower() != "jsonb_set" or len(function.expressions) != 3:
            continue
        value = function.expressions[2]
        if isinstance(value, exp.Column) and value.table == alias.name:
            argument = arguments.get(value.name)
            index = None if argument is None else bound_placeholder_index(argument)
            if index is not None:
                indexes.add(index)
    return frozenset(indexes)
