"""The declared positions a golden statement's binds occupy, and the zero-sign
check `m-case-format` *Canonical literal oracles* applies at them.

A canonical bind compares by `m-wire`'s variant-aware comparison for its resolved
declaration, so a declared ``float32``/``float64`` position — a scalar Column or a
Value Object leaf inside a document bind — distinguishes ``-0.0`` from ``0.0``,
while a Json position and a document key no declaration names keep JSON-value
equality. Nothing in a bind value says which it is, so the position is read off
the statement and the case's model: a Column an ``insert`` lists or an ``update``
assigns, a document path a mutation expression assigns, or the operand a bind is
compared with. A position this cannot resolve stays untyped and compares as
JSON; a type is never guessed from a value.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import sqlglot
from sqlglot import exp

from parallax.core import storage_layout
from parallax.core.base import Float32, Float64, NeutralType
from parallax.core.metamodel import (
    AttributeIdentity,
    Leaf,
    MemberShape,
    Metamodel,
    Multiplicity,
    Occurrence,
    ValueObjectIdentity,
)
from parallax.core.storage_layout import ColumnSlot, RelationalDocument, TableLayout

__all__ = [
    "BindPosition",
    "Document",
    "Elements",
    "assert_zero_signs",
    "declares_float",
    "statement_bind_positions",
    "zero_signs_agree",
]


@dataclass(frozen=True, slots=True)
class Document:
    """A JSON object whose named keys hold declared positions; any other key is Json."""

    members: Mapping[str, BindPosition]


@dataclass(frozen=True, slots=True)
class Elements:
    """A JSON array, each element at ``element``: a Value Object ``many``."""

    element: BindPosition


type BindPosition = NeutralType | Document | Elements

_BIND: Final = "bind"
_COMPARISONS: Final = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)


def statement_bind_positions(
    model: Metamodel, sql: str, binds: Sequence[object], *, dialect: str = "postgres"
) -> dict[int, BindPosition]:
    """Each bind index of the canonical ``sql`` whose declared position resolves.

    ``binds`` are the statement's golden binds, read only where a statement names
    a document path or a discriminator tag through a bind.
    """
    try:
        tree = sqlglot.parse_one(_indexed(sql), read=dialect)
    except sqlglot.ParseError:
        return {}
    layouts = {layout.table.name: layout for layout in storage_layout.view(model).tables}
    statement = _Statement(model, layouts, binds)
    positions = statement.written(tree)
    for placeholder in tree.find_all(exp.Placeholder):
        index = _index(placeholder)
        if index is None or index in positions:
            continue
        position = statement.compared(placeholder)
        if position is not None:
            positions[index] = position
    return positions


def assert_zero_signs(
    observed: Sequence[object],
    expected: Sequence[object],
    positions: Mapping[int, BindPosition],
    *,
    label: str = "bind",
) -> None:
    """Every bind at a resolved position carries the golden's zero sign there."""
    for index, position in sorted(positions.items()):
        if index < len(observed) and index < len(expected):
            assert zero_signs_agree(observed[index], expected[index], position), (
                f"{label} {index}: {observed[index]!r} carries a zero sign the golden "
                f"{expected[index]!r} does not"
            )


def declares_float(position: BindPosition) -> bool:
    """Whether ``position`` is, or holds, a declared ``float32``/``float64``."""
    match position:
        case Float32() | Float64():
            return True
        case Document(members):
            return any(declares_float(member) for member in members.values())
        case Elements(element):
            return declares_float(element)
        case _:
            return False


def zero_signs_agree(observed: object, expected: object, position: BindPosition) -> bool:
    """Whether every declared float zero ``position`` reaches carries one sign on
    both sides; everything else — value equality included — is the caller's."""
    match position:
        case Float32() | Float64():
            return _same_zero_sign(observed, expected)
        case Document(members):
            if not isinstance(observed, Mapping) or not isinstance(expected, Mapping):
                return True
            observed_map = cast("Mapping[str, object]", observed)
            expected_map = cast("Mapping[str, object]", expected)
            return all(
                zero_signs_agree(observed_map[name], expected_map[name], member)
                for name, member in members.items()
                if name in observed_map and name in expected_map
            )
        case Elements(element):
            if not isinstance(observed, list) or not isinstance(expected, list):
                return True
            pairs = zip(
                cast("list[object]", observed), cast("list[object]", expected), strict=False
            )
            return all(zero_signs_agree(left, right, element) for left, right in pairs)
        case _:
            return True


def _same_zero_sign(observed: object, expected: object) -> bool:
    if not (_is_number(observed) and _is_number(expected)):
        return True
    left, right = float(cast("float", observed)), float(cast("float", expected))
    if left != 0.0 or right != 0.0:
        return True
    return math.copysign(1.0, left) == math.copysign(1.0, right)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _indexed(sql: str) -> str:
    """``sql`` with its N-th ``?`` outside a quoted run spelled ``:bindN``."""
    out: list[str] = []
    quote: str | None = None
    count = 0
    for character in sql:
        if quote is not None:
            quote = None if character == quote else quote
            out.append(character)
        elif character in "'\"`":
            quote = character
            out.append(character)
        elif character == "?":
            out.append(f":{_BIND}{count}")
            count += 1
        else:
            out.append(character)
    return "".join(out)


def _index(placeholder: exp.Expr) -> int | None:
    name = placeholder.this if isinstance(placeholder, exp.Placeholder) else None
    if not isinstance(name, str) or not name.startswith(_BIND):
        return None
    digits = name.removeprefix(_BIND)
    return int(digits) if digits.isdigit() else None


def _unwrapped(expression: exp.Expr) -> exp.Expr:
    while isinstance(expression, exp.Paren):
        expression = expression.this
    return expression


def _bare_bind(expression: exp.Expr) -> int | None:
    """The bind index of an operand that is one bind, however parenthesized or cast."""
    while isinstance(expression, (exp.Paren, exp.Cast)):
        expression = expression.this
    return _index(expression)


class _Statement:
    """One statement's bind resolution over the model's Table Layouts."""

    def __init__(
        self, model: Metamodel, layouts: Mapping[str, TableLayout], binds: Sequence[object]
    ) -> None:
        self._model = model
        self._layouts = layouts
        self._binds = binds

    def written(self, tree: exp.Expr) -> dict[int, BindPosition]:
        if isinstance(tree, exp.Insert):
            return self._inserted(tree)
        if isinstance(tree, exp.Update):
            return self._assigned(tree)
        return {}

    def compared(self, placeholder: exp.Placeholder) -> BindPosition | None:
        """The position of the operand ``placeholder`` is compared with, where the
        operand is a Column or a casting extraction of one Column's document."""
        operand = _compared_operand(placeholder)
        if operand is None:
            return None
        operand = _unwrapped(operand)
        if isinstance(operand, exp.Column):
            slot = self._column_slot(operand)
            return None if slot is None else self._slot_position(slot, self._guards(operand))
        if not isinstance(operand, exp.Cast):
            # A text extraction binds the stored text as it stands (m-sql
            # continuation coordinates), so only a casting one binds a declared value.
            return None
        extraction = _unwrapped(operand.this)
        arguments = (
            extraction.expressions
            if isinstance(extraction, exp.Anonymous)
            and extraction.name.lower() == "jsonb_extract_path_text"
            else []
        )
        if not arguments or not isinstance(arguments[0], exp.Column):
            return None
        path = [self._bound_text(argument) for argument in arguments[1:]]
        slot = self._column_slot(arguments[0])
        if slot is None or not path or None in path:
            return None
        document = self._slot_position(slot, self._guards(arguments[0]))
        leaf = _at_path(document, cast("list[str]", path))
        return None if isinstance(leaf, (Document, Elements)) else leaf

    def _inserted(self, tree: exp.Insert) -> dict[int, BindPosition]:
        target = tree.this
        values = tree.expression
        if not isinstance(target, exp.Schema) or not isinstance(values, exp.Values):
            return {}
        layout = self._layouts.get(target.this.name) if isinstance(target.this, exp.Table) else None
        if layout is None:
            return {}
        columns = [identifier.name for identifier in target.expressions]
        positions: dict[int, BindPosition] = {}
        for row in values.expressions:
            if not isinstance(row, exp.Tuple):
                continue
            cells = dict(zip(columns, row.expressions, strict=False))
            known = {name: self._literal(cell) for name, cell in cells.items()}
            for name, cell in cells.items():
                index = _bare_bind(cell)
                slot = _slot_named(layout, name)
                position = None if slot is None else self._slot_position(slot, known)
                if index is not None and position is not None:
                    positions[index] = position
        return positions

    def _assigned(self, tree: exp.Update) -> dict[int, BindPosition]:
        table = tree.this
        layout = self._layouts.get(table.name) if isinstance(table, exp.Table) else None
        if layout is None:
            return {}
        known = self._guards(tree)
        positions: dict[int, BindPosition] = {}
        for assignment in tree.expressions:
            if not isinstance(assignment, exp.EQ) or not isinstance(assignment.this, exp.Column):
                continue
            slot = _slot_named(layout, assignment.this.name)
            position = None if slot is None else self._slot_position(slot, known)
            if position is None:
                continue
            index = _bare_bind(assignment.expression)
            if index is not None:
                positions[index] = position
                continue
            for path_index, value_index in _path_assignments(assignment):
                path = _text_array_path(self._bound(path_index))
                member = None if path is None else _at_path(position, path)
                if member is not None:
                    positions[value_index] = member
        return positions

    def _slot_position(self, slot: ColumnSlot, known: Mapping[str, object]) -> BindPosition | None:
        contributor = slot.contributor
        if isinstance(contributor, AttributeIdentity):
            entity = self._model.entity(contributor.entity)
            attribute = None if entity is None else entity.attribute(contributor.name)
            return None if attribute is None else attribute.type
        if isinstance(contributor, ValueObjectIdentity):
            entity = self._model.entity(contributor.entity)
            occurrence = None if entity is None else entity.value_object(contributor.path[0])
            return None if occurrence is None else _occurrence(occurrence.definition)
        if isinstance(contributor, RelationalDocument):
            return self._relational_document(slot, known)
        return None

    def _relational_document(self, slot: ColumnSlot, known: Mapping[str, object]) -> Document:
        """The shared document ``slot`` holds for the row owner ``known`` tags.

        Without a tag naming one owner, only the keys every possible owner
        declares alike are typed: disjoint siblings may reuse one path with
        different declarations (`m-storage-layout`).
        """
        facet = storage_layout.view(self._model)
        owners: list[tuple[Document, str | None, str | None]] = []
        for entity in self._model.entities:
            view = facet.entity(entity.identity)
            if view is None or slot not in view.columns:
                continue
            residents = view.document_residents
            document = (
                Document({})
                if residents is None
                else _placed_document(residents.shape, [p.path for p in residents.placements])
            )
            tag = view.discriminator
            owners.append(
                (
                    document,
                    None if tag is None else tag.slot.column.name,
                    None if tag is None else tag.value,
                )
            )
        tagged = [
            document for document, column, value in owners if column and known.get(column) == value
        ]
        if len(tagged) == 1:
            return tagged[0]
        return _agreement([document for document, _column, _value in owners])

    def _column_slot(self, column: exp.Column) -> ColumnSlot | None:
        """The slot a Column reference reads, resolved through its own query scope
        outward; a derived-table source stays unresolved."""
        scope = column.find_ancestor(exp.Select, exp.Update)
        while scope is not None:
            tables = [
                table
                for table in _scope_tables(scope)
                if not column.table or column.table == table.alias_or_name
            ]
            if len(tables) == 1:
                layout = self._layouts.get(tables[0].name)
                return None if layout is None else _slot_named(layout, column.name)
            if tables or not column.table or scope.parent is None:
                return None
            scope = scope.parent.find_ancestor(exp.Select, exp.Update)
        return None

    def _guards(self, node: exp.Expr) -> dict[str, object]:
        """The Column values the query scope around ``node`` pins by equality."""
        scope = (
            node
            if isinstance(node, (exp.Select, exp.Update))
            else node.find_ancestor(exp.Select, exp.Update)
        )
        where = None if scope is None else scope.args.get("where")
        guards: dict[str, list[object]] = {}
        if isinstance(where, exp.Where):
            for comparison in where.find_all(exp.EQ):
                for column, value in (
                    (comparison.this, comparison.expression),
                    (comparison.expression, comparison.this),
                ):
                    if isinstance(column, exp.Column):
                        guards.setdefault(column.name, []).append(self._literal(value))
        return {name: values[0] for name, values in guards.items() if len(values) == 1}

    def _literal(self, expression: exp.Expr) -> object:
        index = _bare_bind(expression)
        if index is not None:
            return self._bound(index)
        expression = _unwrapped(expression)
        return (
            expression.this
            if isinstance(expression, exp.Literal) and expression.is_string
            else None
        )

    def _bound(self, index: int) -> object:
        return self._binds[index] if index < len(self._binds) else None

    def _bound_text(self, expression: exp.Expr) -> str | None:
        index = _bare_bind(expression)
        value = None if index is None else self._bound(index)
        return value if isinstance(value, str) else None


def _compared_operand(placeholder: exp.Placeholder) -> exp.Expr | None:
    current: exp.Expr = placeholder
    while isinstance(current.parent, (exp.Paren, exp.Cast)):
        current = current.parent
    parent = current.parent
    if isinstance(parent, _COMPARISONS):
        return parent.expression if current is parent.this else parent.this
    if isinstance(parent, exp.Between) and current is not parent.this:
        return parent.this
    if isinstance(parent, exp.In) and current is not parent.this:
        return parent.this
    return None


def _scope_tables(scope: exp.Expr) -> Iterator[exp.Table]:
    """The Tables ``scope`` reads directly: its FROM and JOIN sources, or an
    update's target."""
    if isinstance(scope, exp.Update) and isinstance(scope.this, exp.Table):
        yield scope.this
    for source in scope.find_all(exp.Table):
        if isinstance(source.parent, (exp.From, exp.Join)) and source.parent.parent is scope:
            yield source


def _path_assignments(assignment: exp.EQ) -> Iterator[tuple[int, int]]:
    """The (path, value) bind pairs of a nested ``jsonb_set`` over the assigned
    Column itself, innermost first."""
    pairs: list[tuple[int, int]] = []
    current = assignment.expression
    while isinstance(current, exp.Anonymous) and current.name.lower() == "jsonb_set":
        if len(current.expressions) != 3:
            return
        current, path, value = current.expressions
        path_index, value_index = _index(path), _bare_bind(value)
        if path_index is None or value_index is None:
            return
        pairs.append((path_index, value_index))
    if isinstance(current, exp.Column) and current.name == assignment.this.name:
        yield from reversed(pairs)


def _text_array_path(value: object) -> list[str] | None:
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        return value[1:-1].split(",")
    return None


def _slot_named(layout: TableLayout, name: str) -> ColumnSlot | None:
    return next((slot for slot in layout.columns if slot.column.name == name), None)


def _at_path(position: BindPosition | None, path: Sequence[str]) -> BindPosition | None:
    for segment in path:
        if not isinstance(position, Document):
            return None
        position = position.members.get(segment)
    return position


def _occurrence(definition: Occurrence) -> BindPosition:
    document = _document(definition.shape)
    return Elements(document) if definition.multiplicity is Multiplicity.MANY else document


def _document(shape: MemberShape) -> Document:
    return Document({member.name: _member(member) for member in shape.members})


def _member(member: Leaf | Occurrence) -> BindPosition:
    return member.type if isinstance(member, Leaf) else _occurrence(member)


def _placed_document(shape: MemberShape, paths: Sequence[Sequence[str]]) -> Document:
    """A shared document whose resident members sit at their own Document Paths."""
    root: dict[str, object] = {}
    for member, path in zip(shape.members, paths, strict=True):
        node = root
        for segment in path[:-1]:
            node = cast("dict[str, object]", node.setdefault(segment, {}))
        node[path[-1]] = _member(member)
    return _frozen(root)


def _frozen(node: Mapping[str, object]) -> Document:
    return Document(
        {
            name: _frozen(cast("Mapping[str, object]", value))
            if isinstance(value, dict)
            else cast("BindPosition", value)
            for name, value in node.items()
        }
    )


def _agreement(documents: Sequence[Document]) -> Document:
    """The keys every document declares with one position."""
    if not documents:
        return Document({})
    first, *rest = documents
    return Document(
        {
            name: position
            for name, position in first.members.items()
            if all(other.members.get(name) == position for other in rest)
        }
    )
