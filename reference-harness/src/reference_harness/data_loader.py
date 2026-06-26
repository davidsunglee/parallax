"""Load fixture rows into a provisioned database.

Fixture rows speak the metamodel's vocabulary (attribute names). This module
resolves them to DB columns via the descriptor and hands column-ordered tuples
to the provider's ``load``. Missing attributes load as NULL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .case import Model
from .ddl_builder import column_order

if TYPE_CHECKING:
    from .providers import DatabaseProvider


def _attribute_to_column(model: Model) -> dict[str, str]:
    return {attribute["name"]: attribute["column"] for attribute in model.attributes}


def load_model(model: Model, db: DatabaseProvider) -> None:
    """Insert *model*'s fixture rows into its table via the provider."""
    rows = model.rows
    if not rows:
        return

    name_to_column = _attribute_to_column(model)
    columns = list(column_order(model))
    column_to_name = {column: name for name, column in name_to_column.items()}

    tuples: list[list[Any]] = []
    for row in rows:
        unknown = set(row) - set(name_to_column)
        if unknown:
            raise ValueError(
                f"fixture row for {model.class_name} references unknown "
                f"attribute(s) {sorted(unknown)}"
            )
        tuples.append([row.get(column_to_name[column]) for column in columns])

    db.load(model.table, columns, tuples)
