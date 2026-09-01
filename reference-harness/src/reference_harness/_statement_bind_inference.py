"""Infer modeled canonical targets for positional SQL statement binds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlglot import exp
from sqlglot.expressions.core import Expr

from ._sql_placeholders import parse_indexed_statement, placeholder_index
from .case import Case
from .ddl_builder import contributor_types
from .portable_literal import (
    PortableLiteralError,
    canonicalize_observed,
    decode_canonical,
)
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
    tree = parse_indexed_statement(statement, dialect)
    if tree is None:
        return {}
    targets = _insert_targets(case, tree)
    targets.update(_update_targets(case, tree))
    for placeholder in tree.find_all(exp.Placeholder):
        index = placeholder_index(placeholder)
        if index is None or index in targets:
            continue
        operand = _compared_operand(placeholder)
        if operand is not None:
            target = _expression_target(case, tree, operand, binds)
            if target is not None:
                targets[index] = target
    return targets


def managed_statement_binds(
    case: Case,
    statement: str,
    binds: Sequence[object],
    dialect: str,
) -> tuple[object, ...]:
    """Decode modeled direct-column binds for provider execution."""
    managed = list(binds)
    types = contributor_types(case.model)
    for index, target in infer_statement_bind_targets(case, statement, binds, dialect).items():
        if not isinstance(target, ColumnSlot) or index >= len(managed):
            continue
        declared = types.get(target.contributor)
        value = managed[index]
        if (
            declared is None
            or value is None
            or (declared[0] == "timestamp" and value == "infinity")
        ):
            continue
        try:
            canonical = canonicalize_observed(value, declared[0])
            managed[index] = decode_canonical(canonical, declared[0])
        except PortableLiteralError:
            continue
    return tuple(managed)


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
            index = placeholder_index(placeholders[0])
            slot = layout.column(column_name)
            if index is not None and slot is not None:
                targets[index] = slot
    return targets


def _update_targets(case: Case, tree: Expr) -> dict[int, CanonicalBindTarget]:
    if not isinstance(tree, exp.Update):
        return {}
    targets: dict[int, CanonicalBindTarget] = {}
    for assignment in tree.expressions:
        if not isinstance(assignment, exp.EQ) or not isinstance(assignment.this, exp.Column):
            continue
        placeholders = tuple(assignment.expression.find_all(exp.Placeholder))
        if isinstance(assignment.expression, exp.Placeholder):
            placeholders = (assignment.expression,)
        if len(placeholders) != 1 or not _transparent_placeholder(
            assignment.expression, placeholders[0]
        ):
            continue
        index = placeholder_index(placeholders[0])
        slot = _column_slot(case, tree, assignment.this)
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
            if (index := placeholder_index(placeholder)) is not None and index < len(binds)
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
