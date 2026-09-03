"""Load fixture rows into a provisioned database.

Fixture rows speak the metamodel's vocabulary (member names). This module
resolves them through each row-owning Entity's layout selection and hands
column-ordered tuples to the provider's ``load``. Missing members load as NULL.
Every row-owning entity in a (possibly multi-entity) descriptor is loaded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from ._declared_contributor import DeclaredContributor
from .case import Entity, Model
from .ddl_builder import declared_contributors
from .document_codec import encode_leaf
from .inheritance import assert_no_abstract_fixture_rows
from .storage_layout import (
    AttributeContributor,
    ColumnContributor,
    ColumnSlot,
    DocumentPath,
    EntityLayoutView,
    RelationalDocument,
    ValueObjectContributor,
)

if TYPE_CHECKING:
    from .providers import DatabaseProvider


def _member_name(slot: ColumnSlot) -> str | None:
    """The authorable fixture member behind *slot*, or absent.

    A framework-owned discriminator has no member: its value is derived from the
    concrete subtype's own ``tagValue`` (m-inheritance), and neither does a
    Relational Document Layout's shared Structured Column, which carries many
    members rather than one.
    """
    contributor = slot.contributor
    if isinstance(contributor, (AttributeContributor, ValueObjectContributor)):
        return contributor.name
    return None


def _document_member_names(view: EntityLayoutView, slot: ColumnSlot) -> tuple[str, ...]:
    """The top-level members *slot*'s shared Structured Column carries, in order.

    Read off the compiled placements rather than off the declarations, so
    residency has exactly one authority (m-storage-layout): a one-segment
    Document Path over this slot is a document-resident top-level member, and a
    conventional Value Object's inner members — whose paths are relative to that
    occurrence's own column — are longer and so never appear here.
    """
    return tuple(
        address.path[0]
        for address, placement in view.layout.placements.items()
        if len(address.path) == 1 and isinstance(placement, DocumentPath) and placement.slot == slot
    )


def _fixture_document(
    entity: Entity, names: tuple[str, ...], row: dict[str, Any]
) -> dict[str, Any]:
    """One fixture row's Structured Column.

    Each document-resident member is authored under its own member name, in the
    spelling it would take if the layout had given it a Column of its own — a
    leaf as the neutral wire value, an occurrence as that occurrence's own
    document — so one fixture file describes one logical row under either
    layout. An omitted key stays absent, an authored null becomes JSON null, and
    a ``many`` occurrence always contributes its array (m-document-codec).
    """
    facts = entity.runtime_facts
    attributes = {attribute["name"]: attribute for attribute in facts.get("attributes", []) or []}
    occurrences = {nested["name"]: nested for nested in facts.get("valueObjects", []) or []}
    document: dict[str, Any] = {}
    for name in names:
        occurrence = occurrences.get(name)
        if name not in row:
            if occurrence is not None and occurrence.get("multiplicity", "one") == "many":
                document[name] = []
            continue
        value = row[name]
        if occurrence is not None or value is None:
            document[name] = value
            continue
        document[name] = encode_leaf(attributes[name]["type"], value)
    return document


def _load_entity(
    entity: Entity,
    view: EntityLayoutView,
    db: DatabaseProvider,
    declarations: Mapping[ColumnContributor, DeclaredContributor],
    corruptions: Sequence[Mapping[str, Any]],
) -> set[int]:
    rows = entity.rows
    if not rows:
        return set()

    slots = view.columns
    document_slot = next(
        (slot for slot in slots if isinstance(slot.contributor, RelationalDocument)), None
    )
    document_names = () if document_slot is None else _document_member_names(view, document_slot)
    members = {name for slot in slots if (name := _member_name(slot)) is not None}
    members.update(document_names)
    columns = [slot.column for slot in slots]

    applied: set[int] = set()
    tuples: list[list[Any]] = []
    for row in rows:
        unknown = set(row) - members
        if unknown:
            raise ValueError(
                f"fixture row for {entity.name} references unknown member(s) {sorted(unknown)}"
            )
        cells = [_cell(slot, entity, view, document_names, row, declarations) for slot in slots]
        applied |= _corrupt_row(entity, view, columns, cells, row, corruptions)
        tuples.append(cells)

    db.load(view.layout.table, columns, tuples)
    return applied


def _primary_key_name(entity: Entity) -> str:
    """The declared member name of *entity*'s model primary key.

    `m-metamodel` admits no composite primary key, so one name addresses one row
    — which is what lets ``given.corrupt`` name a row by a single ``key`` value.
    """
    for attribute in entity.attributes:
        if attribute.get("primaryKey"):
            return str(attribute["name"])
    raise ValueError(f"{entity.name} declares no primary key to address a corruption by")


def _corrupt_row(
    entity: Entity,
    view: EntityLayoutView,
    columns: Sequence[str],
    cells: list[Any],
    row: Mapping[str, Any],
    corruptions: Sequence[Mapping[str, Any]],
) -> set[int]:
    """Write every corruption addressed at *row* into the physical cells it produced,
    and answer which of *corruptions* it applied.

    A corruption is stored state rather than an authored value, so it replaces
    what the conforming fixture produced instead of passing through the codec
    that produced it (`m-case-format` *Corrupting stored state*).
    """
    key = row.get(_primary_key_name(entity))
    applied: set[int] = set()
    for position, entry in enumerate(corruptions):
        if entry["entity"] != entity.canonical_name or entry["key"] != key:
            continue
        column, path = _corruption_target(entity, view, tuple(entry["member"]))
        index = columns.index(column)
        cells[index] = _thawed(cells[index])
        _write_at(cells[index], path, entry["value"])
        applied.add(position)
    return applied


def _corruption_target(
    entity: Entity, view: EntityLayoutView, member: tuple[Any, ...]
) -> tuple[str, tuple[Any, ...]]:
    """The Structured Column and in-document path one addressed member resolves to.

    The longest declared prefix of *member* that the Table Layout places answers
    it: a document-resident member contributes its own Document Path, a top-level
    Value Object occurrence under `Columns` contributes its own Structured Column
    with an empty path, and whatever the address did not consume — the nested
    member names and the array positions a placement never carries — follows.

    A member the layout places in a Column of its own is refused: only a
    Structured Column can hold a value its declaration contradicts.
    """
    placements = view.layout.placements
    for cut in range(len(member), 0, -1):
        prefix = member[:cut]
        candidates = [
            (address, placement)
            for address, placement in placements.items()
            if address.path == prefix
        ]
        owned = [
            placement for address, placement in candidates if address.owner == entity.canonical_name
        ]
        placement = next(iter(owned), None) or next(
            (placement for _address, placement in candidates), None
        )
        if placement is None:
            continue
        rest = member[cut:]
        if isinstance(placement, DocumentPath):
            return placement.slot.column, (*placement.path, *rest)
        if rest:
            return placement.slot.column, rest
        break
    raise ValueError(
        f"given.corrupt addresses {entity.canonical_name}.{'.'.join(str(s) for s in member)}, "
        "which this model does not place inside a Structured Column"
    )


def _thawed(document: Any) -> Any:
    """*document* rebuilt out of ordinary mutable containers.

    A fixture row's own sub-documents come straight from the parsed corpus, which
    is immutable and shared between cases, so a corruption writes into a copy of
    the cell rather than into the fixture every other case reads.
    """
    if isinstance(document, dict):
        return {key: _thawed(value) for key, value in cast("dict[Any, Any]", document).items()}
    if isinstance(document, list):
        return [_thawed(element) for element in cast("list[Any]", document)]
    return document


def _write_at(document: Any, path: tuple[Any, ...], value: Any) -> None:
    """Store *value* at *path* inside the already-built *document*."""
    current = document
    for segment in path[:-1]:
        current = current[segment]
    current[path[-1]] = value


def _cell(
    slot: ColumnSlot,
    entity: Entity,
    view: EntityLayoutView,
    document_names: tuple[str, ...],
    row: dict[str, Any],
    declarations: Mapping[ColumnContributor, DeclaredContributor],
) -> Any:
    """One row's value for one physical column.

    The shared Structured Column always carries a document, the empty object
    included: it is ``NOT NULL`` and every governed row holds one
    (m-storage-layout).
    """
    if isinstance(slot.contributor, RelationalDocument):
        return _fixture_document(entity, document_names, row)
    name = _member_name(slot)
    if name is None:
        return _tag_value(view)
    value = row.get(name)
    declared = declarations.get(slot.contributor)
    return value if declared is None else declared.fixture_value(value)


def _tag_value(view: EntityLayoutView) -> str:
    if view.discriminator is None:  # pragma: no cover - only a shared table has one
        raise ValueError(f"{view.entity} has a discriminator slot but no tag value")
    return view.discriminator.value


def load_model(
    model: Model, db: DatabaseProvider, corruptions: Sequence[Mapping[str, Any]] = ()
) -> None:
    """Insert every row-owning entity's fixture rows into its table via the provider.

    Fixture rows are keyed to row-owning entities only; an abstract inheritance
    node is rowless (m-inheritance), so a fixture keyed to one is refused before
    load and owns no layout selection here.

    Every corruption must reach a row: one that addresses none would leave a case
    asserting a verdict about storage nothing produced, which passes for the wrong
    reason rather than failing.
    """
    assert_no_abstract_fixture_rows(model)
    layout = model.storage_layout
    declarations = declared_contributors(model)
    applied: set[int] = set()
    for entity in model.entities:
        view = layout.entity(entity.canonical_name)
        if view is None:
            continue
        applied |= _load_entity(entity, view, db, declarations, corruptions)
    unapplied = [entry for position, entry in enumerate(corruptions) if position not in applied]
    if unapplied:
        raise ValueError(
            "given.corrupt addresses row(s) the model's fixtures do not hold: "
            f"{[(entry['entity'], entry['key']) for entry in unapplied]}"
        )
