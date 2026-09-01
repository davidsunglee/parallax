"""Load fixture rows into a provisioned database.

Fixture rows speak the metamodel's vocabulary (member names). This module
resolves them through each row-owning Entity's layout selection and hands
column-ordered tuples to the provider's ``load``. Missing members load as NULL.
Every row-owning entity in a (possibly multi-entity) descriptor is loaded.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .case import Entity, Model
from .ddl_builder import contributor_types
from .document_codec import encode_leaf
from .inheritance import assert_no_abstract_fixture_rows
from .portable_literal import decode
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
    types: Mapping[ColumnContributor, tuple[str, int | None]],
) -> None:
    rows = entity.rows
    if not rows:
        return

    slots = view.columns
    document_slot = next(
        (slot for slot in slots if isinstance(slot.contributor, RelationalDocument)), None
    )
    document_names = () if document_slot is None else _document_member_names(view, document_slot)
    members = {name for slot in slots if (name := _member_name(slot)) is not None}
    members.update(document_names)
    columns = [slot.column for slot in slots]

    tuples: list[list[Any]] = []
    for row in rows:
        unknown = set(row) - members
        if unknown:
            raise ValueError(
                f"fixture row for {entity.name} references unknown member(s) {sorted(unknown)}"
            )
        tuples.append([_cell(slot, entity, view, document_names, row, types) for slot in slots])

    db.load(view.layout.table, columns, tuples)


def _cell(
    slot: ColumnSlot,
    entity: Entity,
    view: EntityLayoutView,
    document_names: tuple[str, ...],
    row: dict[str, Any],
    types: Mapping[ColumnContributor, tuple[str, int | None]],
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
    declared = types.get(slot.contributor)
    if value is None or declared is None or (declared[0] == "timestamp" and value == "infinity"):
        return value
    return decode(value, declared[0])


def _tag_value(view: EntityLayoutView) -> str:
    if view.discriminator is None:  # pragma: no cover - only a shared table has one
        raise ValueError(f"{view.entity} has a discriminator slot but no tag value")
    return view.discriminator.value


def load_model(model: Model, db: DatabaseProvider) -> None:
    """Insert every row-owning entity's fixture rows into its table via the provider.

    Fixture rows are keyed to row-owning entities only; an abstract inheritance
    node is rowless (m-inheritance), so a fixture keyed to one is refused before
    load and owns no layout selection here.
    """
    assert_no_abstract_fixture_rows(model)
    layout = model.storage_layout
    types = contributor_types(model)
    for entity in model.entities:
        view = layout.entity(entity.canonical_name)
        if view is None:
            continue
        _load_entity(entity, view, db, types)
