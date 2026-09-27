"""Infer modeled canonical targets for positional SQL statement binds."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from sqlglot import exp
from sqlglot.expressions.core import Expr

from ._sql_placeholders import parse_indexed_statement, placeholder_index
from .case import Case
from .storage_layout import (
    ColumnSlot,
    DocumentMember,
    RelationalDocument,
    ValueObjectContributor,
)


@dataclass(frozen=True, slots=True)
class LiteralBindTarget:
    neutral_type: str


type CanonicalBindTarget = ColumnSlot | LiteralBindTarget | DocumentMember


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
    targets.update(_update_targets(case, tree, binds))
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


def _update_targets(
    case: Case, tree: Expr, binds: Sequence[object]
) -> dict[int, CanonicalBindTarget]:
    if not isinstance(tree, exp.Update):
        return {}
    targets: dict[int, CanonicalBindTarget] = {}
    for assignment in tree.expressions:
        if not isinstance(assignment, exp.EQ) or not isinstance(assignment.this, exp.Column):
            continue
        slot = _column_slot(case, tree, assignment.this)
        placeholders = tuple(assignment.expression.find_all(exp.Placeholder))
        if isinstance(assignment.expression, exp.Placeholder):
            placeholders = (assignment.expression,)
        if len(placeholders) == 1 and _transparent_placeholder(
            assignment.expression, placeholders[0]
        ):
            index = placeholder_index(placeholders[0])
            if index is not None and slot is not None:
                targets[index] = slot
        elif slot is not None and isinstance(slot.contributor, RelationalDocument):
            targets.update(_path_assignment_targets(case, slot, assignment, binds))
    return targets


def _path_assignment_targets(
    case: Case, slot: ColumnSlot, assignment: exp.EQ, binds: Sequence[object]
) -> dict[int, CanonicalBindTarget]:
    members = {member.path: member for member in document_members(case, slot)}
    targets: dict[int, CanonicalBindTarget] = {}
    for path_placeholder, value_placeholder in _path_assignments(
        assignment.this, assignment.expression
    ):
        path_index = placeholder_index(path_placeholder)
        value_index = placeholder_index(value_placeholder)
        if path_index is None or value_index is None or path_index >= len(binds):
            continue
        member = members.get(_document_path(binds[path_index]))
        if member is not None:
            targets[value_index] = member
    return targets


def _path_assignments(
    column: exp.Column, expression: Expr
) -> Iterator[tuple[exp.Placeholder, exp.Placeholder]]:
    """The (path, value) placeholder pairs of ``m-dialect``'s document mutation
    expression over ``column``: nested ``jsonb_set`` or one N-pair ``json_set``."""
    if isinstance(expression, exp.JSONSet):
        arguments = expression.expressions
        if _names_column(expression.this, column) and len(arguments) % 2 == 0:
            for path, value in zip(arguments[::2], arguments[1::2], strict=True):
                if (
                    isinstance(path, exp.Placeholder)
                    and isinstance(value, exp.JSONExtract)
                    and isinstance(value.this, exp.Placeholder)
                ):
                    yield path, value.this
        return
    pairs: list[tuple[exp.Placeholder, exp.Placeholder]] = []
    current = expression
    while isinstance(current, exp.Anonymous) and current.name.lower() == "jsonb_set":
        if len(current.expressions) != 3:
            return
        current, path, value = current.expressions
        if not (
            isinstance(path, exp.Placeholder)
            and isinstance(value, exp.Cast)
            and isinstance(value.this, exp.Placeholder)
        ):
            return
        pairs.append((path, value.this))
    if _names_column(current, column):
        yield from pairs


def _names_column(expression: Expr, column: exp.Column) -> bool:
    return isinstance(expression, exp.Column) and expression.name == column.name


def _document_path(bind: object) -> tuple[str, ...]:
    if not isinstance(bind, str):
        return ()
    if bind.startswith("$."):
        return tuple(bind[2:].split("."))
    if bind.startswith("{") and bind.endswith("}"):
        return tuple(bind[1:-1].split(","))
    return ()


def document_members(case: Case, slot: ColumnSlot) -> tuple[DocumentMember, ...]:
    """The members the Structured Column ``slot`` carries whose Document Path every
    Entity sharing that column resolves to one address and declared type."""
    candidates = tuple(
        member
        for entity in case.model.entities
        if (view := case.model.storage_layout.entity(entity.canonical_name)) is not None
        and slot in view.layout.columns
        for member in case.model.storage_layout.document(entity.canonical_name).members
    )
    by_path: dict[tuple[str, ...], list[DocumentMember]] = {}
    for member in candidates:
        by_path.setdefault(member.path, []).append(member)
    return tuple(
        members[0]
        for members in by_path.values()
        if all(
            (member.address, member.type_spelling) == (members[0].address, members[0].type_spelling)
            for member in members[1:]
        )
    )


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
