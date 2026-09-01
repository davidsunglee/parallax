"""Infer modeled canonical targets for positional SQL statement binds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.expressions.core import Expr

from .case import Case
from .storage_layout import ColumnSlot, ValueObjectContributor


@dataclass(frozen=True, slots=True)
class LiteralBindTarget:
    neutral_type: str


type CanonicalBindTarget = ColumnSlot | LiteralBindTarget


def infer_statement_bind_targets(
    case: Case,
    statement: str,
    binds: Sequence[object],
    dialect: str,
) -> dict[int, CanonicalBindTarget]:
    try:
        tree = sqlglot.parse_one(_indexed_placeholders(statement), read=_sqlglot_dialect(dialect))
    except sqlglot.ParseError:
        return {}
    targets = _insert_targets(case, tree)
    for placeholder in tree.find_all(exp.Placeholder):
        index = _placeholder_index(placeholder)
        if index is None or index in targets:
            continue
        operand = _compared_operand(placeholder)
        if operand is not None:
            target = _expression_target(case, tree, operand, binds)
            if target is not None:
                targets[index] = target
    return targets


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


def _sqlglot_dialect(dialect: str) -> str:
    return "mysql" if dialect == "mariadb" else dialect


def _placeholder_index(placeholder: exp.Placeholder) -> int | None:
    name = placeholder.this
    prefix = "__parallax_bind_"
    if not isinstance(name, str) or not name.startswith(prefix):
        return None
    try:
        return int(name.removeprefix(prefix))
    except ValueError:
        return None


def _insert_targets(case: Case, tree: Expr) -> dict[int, CanonicalBindTarget]:
    if not isinstance(tree, exp.Insert) or not isinstance(tree.this, exp.Schema):
        return {}
    table = tree.this.this
    if not isinstance(table, exp.Table):
        return {}
    layout = case.model.storage_layout.table(table.name)
    values = tree.expression
    if layout is None or not isinstance(values, exp.Values):
        return {}
    columns = tuple(
        identifier.name
        for identifier in tree.this.expressions
        if isinstance(identifier, exp.Identifier)
    )
    targets: dict[int, CanonicalBindTarget] = {}
    for row in values.expressions:
        if not isinstance(row, exp.Tuple):
            continue
        for column_name, expression in zip(columns, row.expressions, strict=False):
            placeholders = tuple(expression.find_all(exp.Placeholder))
            if isinstance(expression, exp.Placeholder):
                placeholders = (expression,)
            if len(placeholders) != 1 or not _transparent_placeholder(expression, placeholders[0]):
                continue
            index = _placeholder_index(placeholders[0])
            slot = layout.column(column_name)
            if index is not None and slot is not None:
                targets[index] = slot
    return targets


def _transparent_placeholder(expression: Expr, placeholder: exp.Placeholder) -> bool:
    current: Expr = placeholder
    while current is not expression:
        parent = current.parent
        if parent is None or not isinstance(parent, (exp.Cast, exp.Paren)):
            return False
        current = parent
    return True


def _compared_operand(placeholder: exp.Placeholder) -> Expr | None:
    current: Expr = placeholder
    parent = current.parent
    while isinstance(parent, (exp.Cast, exp.Paren)):
        current = parent
        parent = current.parent
    if isinstance(parent, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
        return parent.expression if current is parent.this else parent.this
    if isinstance(parent, exp.Between) and current in (
        parent.args.get("low"),
        parent.args.get("high"),
    ):
        return parent.this
    if isinstance(parent, exp.In) and current in parent.expressions:
        return parent.this
    return None


def _expression_target(
    case: Case, tree: Expr, expression: Expr, binds: Sequence[object]
) -> CanonicalBindTarget | None:
    if isinstance(expression, exp.Column):
        return _column_slot(case, tree, expression)
    columns = tuple(expression.find_all(exp.Column))
    if len(columns) != 1:
        return None
    slot = _column_slot(case, tree, columns[0])
    if slot is None or not isinstance(slot.contributor, ValueObjectContributor):
        return None
    path = _extraction_path(expression, binds)
    if not path:
        return None
    owner = case.model.entity(slot.contributor.owner)
    occurrence = next(
        (
            candidate
            for candidate in owner.value_objects
            if candidate.get("name") == slot.contributor.name
        ),
        None,
    )
    if occurrence is None:
        return None
    current = occurrence
    for segment in path[:-1]:
        nested = current.get("valueObjects", [])
        current = next(
            (
                candidate
                for candidate in nested
                if isinstance(candidate, Mapping) and candidate.get("name") == segment
            ),
            None,
        )
        if current is None:
            return None
    attributes = current.get("attributes", [])
    attribute = next(
        (
            candidate
            for candidate in attributes
            if isinstance(candidate, Mapping) and candidate.get("name") == path[-1]
        ),
        None,
    )
    neutral_type = None if attribute is None else attribute.get("type")
    return LiteralBindTarget(neutral_type) if isinstance(neutral_type, str) else None


def _extraction_path(expression: Expr, binds: Sequence[object]) -> tuple[str, ...]:
    indexed = sorted(
        (
            (index, binds[index])
            for placeholder in expression.find_all(exp.Placeholder)
            if (index := _placeholder_index(placeholder)) is not None and index < len(binds)
        ),
        key=lambda item: item[0],
    )
    if len(indexed) == 1 and isinstance(indexed[0][1], str) and indexed[0][1].startswith("$."):
        return tuple(segment for segment in indexed[0][1][2:].split(".") if segment)
    if indexed and all(isinstance(value, str) for _index, value in indexed):
        return tuple(value for _index, value in indexed if isinstance(value, str))
    return ()


def _column_slot(case: Case, tree: Expr, column: exp.Column) -> ColumnSlot | None:
    table_name: str | None = None
    if column.table:
        for table in tree.find_all(exp.Table):
            if table.alias_or_name == column.table:
                table_name = table.name
                break
    else:
        tables = {table.name for table in tree.find_all(exp.Table)}
        if len(tables) == 1:
            table_name = next(iter(tables))
    if table_name is not None:
        layout = case.model.storage_layout.table(table_name)
        return None if layout is None else layout.column(column.name)
    matches = tuple(
        slot
        for layout in case.model.storage_layout.tables
        if (slot := layout.column(column.name)) is not None
    )
    return matches[0] if len(matches) == 1 else None
