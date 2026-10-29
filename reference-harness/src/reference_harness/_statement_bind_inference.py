"""Infer modeled canonical targets for positional SQL statement binds."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from sqlglot import exp
from sqlglot.expressions.core import Expr

from ._postgres_arrays import column_array_element
from ._sql_placeholders import (
    bound_placeholder_index,
    parse_indexed_statement,
    placeholder_index,
    transparent_placeholder,
)
from .case import Case
from .ddl_builder import declared_contributors, slot_neutral_type
from .storage_layout import (
    AttributeContributor,
    ColumnSlot,
    DocumentMember,
    RelationalDocument,
    TableLayout,
    ValueObjectContributor,
)


@dataclass(frozen=True, slots=True)
class LiteralBindTarget:
    neutral_type: str


@dataclass(frozen=True, slots=True)
class DocumentBindTarget:
    members: tuple[DocumentMember, ...]


@dataclass(frozen=True, slots=True)
class DocumentArrayBindTarget:
    """A column array bound into a shared Structured Column: element ``i`` is row
    ``i``'s document, typed by the members that row's own tag selects."""

    elements: tuple[DocumentBindTarget, ...]


type CanonicalBindTarget = (
    ColumnSlot | LiteralBindTarget | DocumentMember | DocumentBindTarget | DocumentArrayBindTarget
)


class ColumnArrayShapeError(ValueError):
    """A column-array INSERT whose binds are not one equal-length array per column."""


def column_array_rows(statement: str, binds: Sequence[object]) -> list[list[object]] | None:
    """The rows the PostgreSQL column-array INSERT *statement* writes, in array
    order, each aligned with its column list; ``None`` for any other statement.

    PostgreSQL pads shorter ``unnest`` arguments with ``NULL``, so arrays of unequal
    length are refused rather than read as the rows the database would store. An
    INSERT reading ``unnest`` in any other shape is refused rather than left
    ungraded, since its ``unnest`` arguments still bind as arrays.
    """
    tree = parse_indexed_statement(statement, "postgres")
    found = None if tree is None else _column_arrays(tree)
    if found is None:
        if isinstance(tree, exp.Insert) and tree.find(exp.Unnest) is not None:
            raise ColumnArrayShapeError(
                "reads unnest outside the column-array form "
                "insert into t(…) select * from unnest(…)"
            )
        return None
    columns, arrays = found
    if len(arrays) != len(columns):
        raise ColumnArrayShapeError(
            f"renders {len(arrays)} column array(s) for {len(columns)} column(s)"
        )
    if [bound_placeholder_index(array) for array in arrays] != list(range(len(binds))):
        raise ColumnArrayShapeError(
            f"carries {len(binds)} bind(s) for {len(arrays)} column array(s), each of which "
            f"binds exactly one array in column order"
        )
    lengths: dict[str, int] = {}
    for column, value in zip(columns, binds, strict=True):
        if not isinstance(value, list):
            raise ColumnArrayShapeError(f"binds {value!r} to column {column}, not an array")
        lengths[column] = len(value)
    if len(set(lengths.values())) > 1:
        raise ColumnArrayShapeError(f"binds column arrays of unequal lengths {lengths}")
    return [list(row) for row in zip(*binds, strict=True)]


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
    targets.update(
        (index, target)
        for argument, target, _column in _grouped_sources(case, tree, binds)
        if (index := bound_placeholder_index(argument)) is not None
    )
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
    layout = _insert_layout(case, tree)
    if not isinstance(tree, exp.Insert) or layout is None:
        return {}
    if isinstance(tree.expression, exp.Values):
        return _value_row_targets(case, layout, _insert_columns(tree), tree.expression, binds)
    found = _column_arrays(tree)
    return {} if found is None else _column_array_targets(case, layout, *found, binds)


def _value_row_targets(
    case: Case,
    layout: TableLayout,
    columns: tuple[str, ...],
    values: exp.Values,
    binds: Sequence[object],
) -> dict[int, CanonicalBindTarget]:
    targets: dict[int, CanonicalBindTarget] = {}
    for row in values.expressions:
        if not isinstance(row, exp.Tuple):
            continue
        cells = dict(zip(columns, row.expressions, strict=False))
        known = {column: _operand_value(cell, binds) for column, cell in cells.items()}
        for column_name, expression in cells.items():
            index = bound_placeholder_index(expression)
            slot = layout.column(column_name)
            if index is not None and slot is not None:
                targets[index] = _slot_target(case, slot, known)
    return targets


def _column_array_targets(
    case: Case,
    layout: TableLayout,
    columns: tuple[str, ...],
    arrays: tuple[Expr, ...],
    binds: Sequence[object],
) -> dict[int, CanonicalBindTarget]:
    """Each column array's target: its column's slot, whose declaration types
    every element, or, for a shared Structured Column, one document target per
    row, because table-per-hierarchy siblings may declare one path differently
    and only the tag in the same row position says which sibling owns it."""
    cells = dict(zip(columns, arrays, strict=False))
    known = {column: _operand_value(array, binds) for column, array in cells.items()}
    targets: dict[int, CanonicalBindTarget] = {}
    for column_name, array in cells.items():
        index = bound_placeholder_index(array)
        slot = layout.column(column_name)
        if index is None or slot is None:
            continue
        if not isinstance(slot.contributor, RelationalDocument):
            targets[index] = slot
            continue
        documents = known[column_name]
        rows = len(documents) if isinstance(documents, list) else 0
        targets[index] = DocumentArrayBindTarget(
            tuple(
                DocumentBindTarget(_document_members(case, slot, _array_row(known, row)))
                for row in range(rows)
            )
        )
    return targets


def _array_row(arrays: Mapping[str, object], row: int) -> dict[str, object]:
    return {
        column: values[row]
        for column, values in arrays.items()
        if isinstance(values, list) and row < len(values)
    }


def _insert_layout(case: Case, tree: Expr) -> TableLayout | None:
    if not isinstance(tree, exp.Insert) or not isinstance(tree.this, exp.Schema):
        return None
    table = tree.this.this
    return case.model.storage_layout.table(table.name) if isinstance(table, exp.Table) else None


def _insert_columns(tree: exp.Insert) -> tuple[str, ...]:
    return tuple(
        identifier.name
        for identifier in tree.this.expressions
        if isinstance(identifier, exp.Identifier)
    )


def _column_arrays(tree: Expr) -> tuple[tuple[str, ...], tuple[Expr, ...]] | None:
    """The column list and ``unnest`` arguments of a column-array INSERT
    (``insert into t(a, b) select * from unnest(cast(? as bigint[]), …)``), or
    ``None`` for any other statement."""
    if not isinstance(tree, exp.Insert) or not isinstance(tree.this, exp.Schema):
        return None
    select = tree.expression
    if not isinstance(select, exp.Select) or [
        key for key, value in select.args.items() if value and key not in ("expressions", "from_")
    ]:
        return None
    if len(select.expressions) != 1 or not isinstance(select.expressions[0], exp.Star):
        return None
    source = select.args.get("from_")
    unnest = source.this if isinstance(source, exp.From) else None
    if not isinstance(unnest, exp.Unnest) or [
        key for key, value in unnest.args.items() if value and key != "expressions"
    ]:
        return None
    return _insert_columns(tree), tuple(unnest.expressions)


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
        if len(placeholders) == 1 and transparent_placeholder(
            assignment.expression, placeholders[0]
        ):
            index = placeholder_index(placeholders[0])
            if index is not None and slot is not None:
                targets[index] = _slot_target(case, slot, guarded)
        elif slot is not None and isinstance(slot.contributor, RelationalDocument):
            members = _document_members(case, slot, guarded)
            targets.update(_path_assignment_targets(members, assignment, binds))
    return targets


@dataclass(frozen=True, slots=True)
class _GroupedSource:
    """A grouped effect's target layout and alias, and its source alias and the
    array argument each source column reads."""

    layout: TableLayout
    target: str
    alias: str
    arguments: Mapping[str, Expr]

    def argument(self, expression: Expr | None) -> Expr | None:
        if isinstance(expression, exp.Column) and expression.table == self.alias:
            return self.arguments.get(expression.name)
        return None


def _grouped_source(case: Case, tree: Expr) -> _GroupedSource | None:
    if not isinstance(tree, exp.Update) or not isinstance(tree.this, exp.Table):
        return None
    source = tree.args.get("from_")
    unnest = source.this if isinstance(source, exp.From) else None
    if not isinstance(unnest, exp.Unnest):
        return None
    alias = unnest.args.get("alias")
    layout = case.model.storage_layout.table(tree.this.name)
    if not isinstance(alias, exp.TableAlias) or layout is None:
        return None
    arguments = dict(
        zip((column.name for column in alias.columns), unnest.expressions, strict=False)
    )
    return _GroupedSource(layout, tree.this.alias_or_name, alias.name, arguments)


def _grouped_sources(
    case: Case, tree: Expr, binds: Sequence[object]
) -> Iterator[tuple[Expr, ColumnSlot | DocumentMember, str]]:
    """Each source array of a grouped effect (``update t set … from unnest(…) with
    ordinality v(…) … returning v.ord``) beside what types its elements: the slot
    of the column a source column is assigned to or compared with, or the document
    member a path assignment writes it to, and that column's name."""
    grouped = _grouped_source(case, tree)
    if grouped is None:
        return
    for assignment in tree.expressions:
        if isinstance(assignment, exp.EQ) and isinstance(assignment.this, exp.Column):
            yield from _assigned_sources(case, grouped, assignment, binds)
    where = tree.args.get("where")
    for comparison in () if where is None else _conjuncts(where.this):
        if isinstance(comparison, exp.EQ):
            yield from _compared_sources(grouped, comparison)


def _assigned_sources(
    case: Case, grouped: _GroupedSource, assignment: exp.EQ, binds: Sequence[object]
) -> Iterator[tuple[Expr, ColumnSlot | DocumentMember, str]]:
    slot = grouped.layout.column(assignment.this.name)
    if slot is None:
        return
    argument = grouped.argument(assignment.expression)
    if argument is not None:
        yield argument, slot, slot.column
        return
    if not isinstance(slot.contributor, RelationalDocument):
        return
    by_path = {member.path: member for member in _document_members(case, slot, {})}
    for path, value in _sourced_paths(assignment.expression):
        index = placeholder_index(path)
        member = (
            by_path.get(_document_path(binds[index]))
            if index is not None and index < len(binds)
            else None
        )
        argument = grouped.argument(value)
        if member is not None and argument is not None:
            yield argument, member, slot.column


def _compared_sources(
    grouped: _GroupedSource, comparison: exp.EQ
) -> Iterator[tuple[Expr, ColumnSlot | DocumentMember, str]]:
    for guarded, operand in (
        (comparison.this, comparison.expression),
        (comparison.expression, comparison.this),
    ):
        argument = grouped.argument(operand)
        if (
            argument is not None
            and isinstance(guarded, exp.Column)
            and guarded.table == grouped.target
            and (slot := grouped.layout.column(guarded.name)) is not None
        ):
            yield argument, slot, slot.column


def _sourced_paths(expression: Expr) -> Iterator[tuple[exp.Placeholder, Expr]]:
    """The (path placeholder, value) pairs of a nested ``jsonb_set`` whose values
    are read from a grouped effect's source rather than bound."""
    current = expression
    while isinstance(current, exp.Anonymous) and current.name.lower() == "jsonb_set":
        if len(current.expressions) != 3:
            return
        current, path, value = current.expressions
        if isinstance(path, exp.Placeholder):
            yield path, value


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


def _compared_operand(placeholder: exp.Placeholder) -> Expr | None:
    """The operand ``placeholder`` is compared with; an array bound through
    ``any`` is compared element by element with it."""
    current: Expr = placeholder
    parent = current.parent
    while isinstance(parent, (exp.Cast, exp.Paren, exp.Any)):
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


@dataclass(frozen=True, slots=True)
class ArrayCastMismatch:
    """A Postgres array parameter not cast to the array of the unmodified type
    its compared operand compares in, or, for a column array, the type its
    ``column`` is declared with; ``cast`` is ``None`` for an uncast one."""

    index: int
    cast: str | None
    expected: str
    column: str | None = None


def array_cast_mismatches(
    case: Case, statement: str, binds: Sequence[object]
) -> tuple[ArrayCastMismatch, ...]:
    """Every array parameter of the Postgres *statement* whose cast is not the
    m-dialect *array parameter cast form* of its compared operand — a column's own
    type, a cast extraction's type, or text for a text extraction — or of the
    column a column array inserts into. An operand this cannot type is not
    judged."""
    tree = parse_indexed_statement(statement, "postgres")
    if tree is None:
        return ()
    mismatches: list[ArrayCastMismatch] = []
    for array in tree.find_all(exp.Any):
        comparison = array.parent
        if not isinstance(comparison, exp.EQ):
            continue
        operand = comparison.this if array is comparison.expression else comparison.expression
        expected = _compared_type(case, operand, binds)
        mismatch = None if expected is None else _array_cast_mismatch(array.this, expected)
        if mismatch is not None:
            mismatches.append(mismatch)
    mismatches.extend(_column_array_cast_mismatches(case, tree))
    mismatches.extend(_grouped_source_cast_mismatches(case, tree, binds))
    return tuple(sorted(mismatches, key=lambda mismatch: mismatch.index))


def _grouped_source_cast_mismatches(
    case: Case, tree: Expr, binds: Sequence[object]
) -> Iterator[ArrayCastMismatch]:
    declarations = declared_contributors(case.model)
    for argument, target, column in _grouped_sources(case, tree, binds):
        element = (
            "jsonb"
            if isinstance(target, DocumentMember)
            else column_array_element(slot_neutral_type(target, declarations))
        )
        mismatch = _array_cast_mismatch(argument, exp.DataType.build(element, dialect="postgres"))
        if mismatch is not None:
            yield ArrayCastMismatch(mismatch.index, mismatch.cast, mismatch.expected, column)


def _column_array_cast_mismatches(case: Case, tree: Expr) -> Iterator[ArrayCastMismatch]:
    layout = _insert_layout(case, tree)
    found = _column_arrays(tree)
    if layout is None or found is None:
        return
    declarations = declared_contributors(case.model)
    for column, array in zip(*found, strict=False):
        slot = layout.column(column)
        if slot is None:
            continue
        expected = exp.DataType.build(
            column_array_element(slot_neutral_type(slot, declarations)), dialect="postgres"
        )
        mismatch = _array_cast_mismatch(array, expected)
        if mismatch is not None:
            yield ArrayCastMismatch(mismatch.index, mismatch.cast, mismatch.expected, column)


def _array_cast_mismatch(parameter: Expr, expected: exp.DataType) -> ArrayCastMismatch | None:
    """The first cast wrapping the one placeholder *parameter* binds that is not
    to the array of *expected* unmodified, since any one of them could truncate or
    round an element; the placeholder uncast is itself a mismatch."""
    index = bound_placeholder_index(parameter)
    if index is None:
        return None
    for cast in tuple(parameter.find_all(exp.Cast)) or (None,):
        element = None if cast is None else _array_element(cast.to)
        if element is None or element.this != expected.this or element.expressions:
            return ArrayCastMismatch(
                index,
                None if element is None else element.sql(dialect="postgres").lower(),
                expected.sql(dialect="postgres").lower(),
            )
    return None


def _array_element(data_type: exp.DataType) -> exp.DataType | None:
    if data_type.this is not exp.DType.ARRAY or len(data_type.expressions) != 1:
        return None
    element = data_type.expressions[0]
    return element if isinstance(element, exp.DataType) else None


def _compared_type(case: Case, operand: Expr, binds: Sequence[object]) -> exp.DataType | None:
    """The unmodified type ``operand`` compares in, where it is a column, a cast,
    a text extraction, or a guarded or scalar-subquery reading of one."""
    while isinstance(operand, exp.Paren):
        operand = operand.this
    if isinstance(operand, exp.Case) and len(operand.args.get("ifs") or ()) == 1:
        return _compared_type(case, operand.args["ifs"][0].args["true"], binds)
    if isinstance(operand, exp.Subquery) and isinstance(operand.this, exp.Select):
        selected = operand.this.expressions
        return _compared_type(case, selected[0], binds) if len(selected) == 1 else None
    if isinstance(operand, exp.Cast):
        return exp.DataType(this=operand.to.this)
    if isinstance(operand, exp.Column):
        slot, _guarded = _column_slot(case, operand, binds)
        contributor = None if slot is None else slot.contributor
        if not isinstance(contributor, AttributeContributor):
            return None
        neutral_type = case.model.entity(contributor.owner).attribute_by_name(contributor.name)
        return exp.DataType.build(column_array_element(neutral_type["type"]), dialect="postgres")
    text_extraction = isinstance(operand, exp.JSONBExtractScalar) or (
        isinstance(operand, exp.Anonymous) and operand.name.lower() == "jsonb_extract_path_text"
    )
    return exp.DataType.build("text") if text_extraction else None


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
