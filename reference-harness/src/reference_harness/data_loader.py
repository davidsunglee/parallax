"""Load fixture rows into a provisioned database.

Fixture rows speak the metamodel's vocabulary (attribute names). This module
resolves them to DB columns via the descriptor and hands column-ordered tuples
to the provider's ``load``. Missing attributes load as NULL. Every entity in a
(possibly multi-entity) descriptor is loaded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .case import Entity, Model
from .ddl_builder import column_order

if TYPE_CHECKING:
    from .providers import DatabaseProvider


def _attribute_to_column(entity: Entity) -> dict[str, str]:
    """Map every loadable element name to its column.

    Scalar attributes plus each valueObject (whose fixture value is a nested
    dict/list loaded into its single dialect-mapped document column, Phase 9).
    """
    mapping = {attribute["name"]: attribute["column"] for attribute in entity.attributes}
    mapping.update(
        {value_object["name"]: value_object["column"] for value_object in entity.value_objects}
    )
    return mapping


def _load_entity(entity: Entity, db: DatabaseProvider) -> None:
    rows = entity.rows
    if not rows:
        return

    name_to_column = _attribute_to_column(entity)
    columns = list(column_order(entity))
    column_to_name = {column: name for name, column in name_to_column.items()}

    tuples: list[list[Any]] = []
    for row in rows:
        unknown = set(row) - set(name_to_column)
        if unknown:
            raise ValueError(
                f"fixture row for {entity.name} references unknown attribute(s) {sorted(unknown)}"
            )
        tuples.append([row.get(column_to_name[column]) for column in columns])

    db.load(entity.table, columns, tuples)


def load_model(model: Model, db: DatabaseProvider) -> None:
    """Insert every entity's fixture rows into its table via the provider."""
    for entity in model.entities:
        _load_entity(entity, db)
