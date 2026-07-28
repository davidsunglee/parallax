"""Load fixture rows into a provisioned database.

Fixture rows speak the metamodel's vocabulary (member names). This module
resolves them through each row-owning Entity's layout selection and hands
column-ordered tuples to the provider's ``load``. Missing members load as NULL.
Every row-owning entity in a (possibly multi-entity) descriptor is loaded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .case import Entity, Model
from .inheritance import assert_no_abstract_fixture_rows
from .storage_layout import (
    AttributeContributor,
    ColumnSlot,
    EntityLayoutView,
    ValueObjectContributor,
)

if TYPE_CHECKING:
    from .providers import DatabaseProvider


def _member_name(slot: ColumnSlot) -> str | None:
    """The authorable fixture member behind *slot*, or absent.

    A framework-owned discriminator has no member: its value is derived from the
    concrete subtype's own ``tagValue`` (m-inheritance), never authored.
    """
    contributor = slot.contributor
    if isinstance(contributor, (AttributeContributor, ValueObjectContributor)):
        return contributor.name
    return None


def _load_entity(entity: Entity, view: EntityLayoutView, db: DatabaseProvider) -> None:
    rows = entity.rows
    if not rows:
        return

    slots = view.columns
    members = {name for slot in slots if (name := _member_name(slot)) is not None}
    columns = [slot.column for slot in slots]

    tuples: list[list[Any]] = []
    for row in rows:
        unknown = set(row) - members
        if unknown:
            raise ValueError(
                f"fixture row for {entity.name} references unknown member(s) {sorted(unknown)}"
            )
        tuples.append(
            [
                row.get(name) if (name := _member_name(slot)) is not None else _tag_value(view)
                for slot in slots
            ]
        )

    db.load(view.layout.table, columns, tuples)


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
    for entity in model.entities:
        view = layout.entity(entity.canonical_name)
        if view is None:
            continue
        _load_entity(entity, view, db)
