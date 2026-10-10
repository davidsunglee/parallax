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


@dataclass(frozen=True, slots=True)
class DocumentBindTarget:
    members: tuple[DocumentMember, ...]


type CanonicalBindTarget = ColumnSlot | LiteralBindTarget | DocumentMember | DocumentBindTarget


def infer_statement_bind_targets(
    case: Case,
    statement: str,
    binds: Sequence[object],
    dialect: str,
) -> dict[int, CanonicalBindTarget]:
    tree = parse_indexed_statement(statement, dialect)
    if tree is None:
        return {}
    targets = _insert_targets(case, tree, binds)
    targets.update(_update_targets(case, tree, binds))
    for placeholder in tree.find_all(exp.Placeholder):
        index = placeholder_index(placeholder)
        if index is None or index in targets:
            continue
        operand = _compared_operand(placeholder)
        if operand is not None:
            target = _expression_target(case, operand, binds)
            if target is not None:
                targets[index] = target
    return targets


def _insert_targets(
    case: Case, tree: Expr, binds: Sequence[object]
) -> dict[int, CanonicalBindTarget]:
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
        cells = dict(zip(columns, row.expressions, strict=False))
        known = {column: _operand_value(cell, binds) for column, cell in cells.items()}
        for column_name, expression in cells.items():
            placeholders = tuple(expression.find_all(exp.Placeholder))
            if isinstance(expression, exp.Placeholder):
                placeholders = (expression,)
            if len(placeholders) != 1 or not _transparent_placeholder(expression, placeholders[0]):
                continue
            index = placeholder_index(placeholders[0])
            slot = layout.column(column_name)
            if index is not None and slot is not None:
                targets[index] = _slot_target(case, slot, known)
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
        slot, guarded = _column_slot(case, assignment.this, binds)
        placeholders = tuple(assignment.expression.find_all(exp.Placeholder))
        if isinstance(assignment.expression, exp.Placeholder):
            placeholders = (assignment.expression,)
        if len(placeholders) == 1 and _transparent_placeholder(
            assignment.expression, placeholders[0]
        ):
            index = placeholder_index(placeholders[0])
            if index is not None and slot is not None:
                targets[index] = _slot_target(case, slot, guarded)
        elif slot is not None and isinstance(slot.contributor, RelationalDocument):
            members = _document_members(case, slot, guarded)
            targets.update(_path_assignment_targets(members, assignment, binds))
    return targets


def _path_assignment_targets(
    members: Sequence[DocumentMember], assignment: exp.EQ, binds: Sequence[object]
) -> dict[int, CanonicalBindTarget]:
    by_path = {member.path: member for member in members}
    targets: dict[int, CanonicalBindTarget] = {}
    for path_placeholder, value_placeholder in _path_assignments(
        assignment.this, assignment.expression
    ):
        path_index = placeholder_index(path_placeholder)
        value_index = placeholder_index(value_placeholder)
        if path_index is None or value_index is None or path_index >= len(binds):
            continue
        member = by_path.get(_document_path(binds[path_index]))
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


def _slot_target(case: Case, slot: ColumnSlot, known: Mapping[str, object]) -> CanonicalBindTarget:
    if isinstance(slot.contributor, RelationalDocument):
        return DocumentBindTarget(_document_members(case, slot, known))
    return slot


def _document_members(
    case: Case, slot: ColumnSlot, known: Mapping[str, object]
) -> tuple[DocumentMember, ...]:
    """The members a row of the Structured Column ``slot`` carries.

    ``known`` holds the column values the statement pins for that row. A
    table-per-hierarchy tag value among them names the one concrete row owner whose
    members apply. Without it, only a Document Path every row owner resolves to one
    address and declared type is typed, since disjoint siblings may reuse a path
    with different declarations (``m-storage-layout``).
    """
    views = tuple(
        view
        for entity in case.model.entities
        if (view := case.model.storage_layout.entity(entity.canonical_name)) is not None
        and slot in view.layout.columns
    )
    tagged = tuple(
        view
        for view in views
        if view.discriminator is not None
        and known.get(view.discriminator.slot.column) == view.discriminator.value
    )
    if len(tagged) == 1:
        return case.model.storage_layout.document(tagged[0].entity).members
    by_path: dict[tuple[str, ...], list[DocumentMember]] = {}
    for view in views:
        for member in case.model.storage_layout.document(view.entity).members:
            by_path.setdefault(member.path, []).append(member)
    return tuple(
        members[0]
        for members in by_path.values()
        if all(
            (member.address, member.type_spelling) == (members[0].address, members[0].type_spelling)
            for member in members[1:]
        )
    )


def _guarded_values(
    table: exp.Table, scopes: Sequence[Expr], binds: Sequence[object]
) -> dict[str, object]:
    guards: dict[str, list[object]] = {}
    for scope in scopes:
        where = scope.args.get("where")
        if where is None:
            continue
        for comparison in _conjuncts(where.this):
            if not isinstance(comparison, exp.EQ):
                continue
            for guarded, operand in (
                (comparison.this, comparison.expression),
                (comparison.expression, comparison.this),
            ):
                if isinstance(guarded, exp.Column) and _column_table(guarded) is table:
                    guards.setdefault(guarded.name, []).append(_operand_value(operand, binds))
    return {column: values[0] for column, values in guards.items() if len(values) == 1}


def _conjuncts(condition: Expr) -> Iterator[Expr]:
    while isinstance(condition, exp.Paren):
        condition = condition.this
    if isinstance(condition, exp.And):
        yield from _conjuncts(condition.this)
        yield from _conjuncts(condition.expression)
    else:
        yield condition


def _operand_value(expression: Expr | None, binds: Sequence[object]) -> object:
    while isinstance(expression, (exp.Cast, exp.Paren)):
        expression = expression.this
    if isinstance(expression, exp.Placeholder):
        index = placeholder_index(expression)
        return binds[index] if index is not None and index < len(binds) else None
    if isinstance(expression, exp.Literal) and expression.is_string:
        return expression.this
    return None


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
    case: Case, expression: Expr, binds: Sequence[object]
) -> CanonicalBindTarget | None:
    if isinstance(expression, exp.Column):
        compared, guarded = _column_slot(case, expression, binds)
        return None if compared is None else _slot_target(case, compared, guarded)
    if _counts_elements(expression):
        return None
    columns = tuple(expression.find_all(exp.Column))
    if len(columns) != 1:
        return None
    slot, guarded = _column_slot(case, columns[0], binds)
    path = _extraction_path(expression, binds)
    if slot is None or not path:
        return None
    if isinstance(slot.contributor, ValueObjectContributor):
        neutral_type = _value_object_leaf_type(
            case, slot.contributor.owner, slot.contributor.name, path
        )
    elif isinstance(slot.contributor, RelationalDocument) and isinstance(expression, exp.Cast):
        # Only a casting extraction binds a declared-type value; a text-compared one
        # binds the stored text as it stands, which a corrupted Continuation Order
        # coordinate may hold (m-sql *Continuation coordinates*).
        neutral_type = _document_leaf_type(case, _document_members(case, slot, guarded), path)
    else:
        return None
    return None if neutral_type is None else LiteralBindTarget(neutral_type)


_ELEMENT_COUNTS = frozenset({"json_length", "jsonb_array_length", "json_array_length"})


def _counts_elements(expression: Expr) -> bool:
    """Whether ``expression`` counts an array's elements, whose value is never
    one of those elements however the array's path is spelled."""
    return isinstance(expression, exp.Anonymous) and str(expression.this).lower() in _ELEMENT_COUNTS


def _document_leaf_type(
    case: Case, members: Sequence[DocumentMember], path: tuple[str, ...]
) -> str | None:
    for member in members:
        if path[: len(member.path)] != member.path:
            continue
        inner = path[len(member.path) :]
        if member.type_spelling is not None:
            return None if inner else member.type_spelling
        if inner:
            return _value_object_leaf_type(
                case, member.address.owner, member.address.path[0], inner
            )
    return None


def _value_object_leaf_type(
    case: Case, owner: str, occurrence_name: str, path: tuple[str, ...]
) -> str | None:
    current = next(
        (
            candidate
            for candidate in case.model.entity(owner).value_objects
            if candidate.get("name") == occurrence_name
        ),
        None,
    )
    for segment in path[:-1]:
        if current is None:
            return None
        current = next(
            (
                candidate
                for candidate in current.get("valueObjects", [])
                if isinstance(candidate, Mapping) and candidate.get("name") == segment
            ),
            None,
        )
    if current is None:
        return None
    attribute = next(
        (
            candidate
            for candidate in current.get("attributes", [])
            if isinstance(candidate, Mapping) and candidate.get("name") == path[-1]
        ),
        None,
    )
    neutral_type = None if attribute is None else attribute.get("type")
    return neutral_type if isinstance(neutral_type, str) else None


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


def _column_slot(
    case: Case, column: exp.Column, binds: Sequence[object]
) -> tuple[ColumnSlot | None, dict[str, object]]:
    """The slot ``column`` reads and the column values its row is guarded to.

    A row is guarded only by a top-level ``and`` equality of its table's own
    scope, or of a ``select *`` derived table it passes through, whose column
    reads that same table; a nested query or a disjunct pins some other row.
    """
    source = _column_source(column)
    if source is None:
        matches = tuple(
            slot
            for layout in case.model.storage_layout.tables
            if (slot := layout.column(column.name)) is not None
        )
        return (matches[0] if len(matches) == 1 else None), {}
    table, scopes = source
    layout = None if table is None else case.model.storage_layout.table(table.name)
    if table is None or layout is None:
        return None, {}
    return layout.column(column.name), _guarded_values(table, scopes, binds)


def _column_table(column: exp.Column) -> exp.Table | None:
    source = _column_source(column)
    return None if source is None else source[0]


def _column_source(column: exp.Column) -> tuple[exp.Table | None, tuple[Expr, ...]] | None:
    """The table ``column`` reads and the scopes that filter its rows.

    A qualifier resolves in the column's own query scope and then its enclosing
    ones, so ``union all`` branches may reuse an alias. A ``select *`` derived table
    passes through to its one source; any other derived table reads no table.
    """
    scope: Expr | None = _query_scope(column)
    while scope is not None:
        sources = _scope_sources(scope)
        if column.table:
            source = next((s for s in sources if s.alias_or_name == column.table), None)
        else:
            source = sources[0] if len(sources) == 1 else None
        if source is not None:
            return _passed_through(source, (scope,))
        scope = _query_scope(scope.parent) if column.table and scope.parent else None
    return None


def _passed_through(
    source: exp.Table | exp.Subquery, scopes: tuple[Expr, ...]
) -> tuple[exp.Table | None, tuple[Expr, ...]]:
    while isinstance(source, exp.Subquery):
        inner = source.this
        if not isinstance(inner, exp.Select) or not inner.is_star:
            return None, scopes
        sources = _scope_sources(inner)
        if len(sources) != 1:
            return None, scopes
        scopes = (*scopes, inner)
        source = sources[0]
    return source, scopes


def _query_scope(node: Expr) -> Expr:
    scope = node.find_ancestor(exp.Select)
    return node.root() if scope is None else scope


def _scope_sources(scope: Expr) -> tuple[exp.Table | exp.Subquery, ...]:
    return tuple(
        source
        for source in scope.find_all(exp.Table, exp.Subquery)
        if (isinstance(source.parent, (exp.From, exp.Join)) or source.parent is scope)
        and _query_scope(source) is scope
    )
