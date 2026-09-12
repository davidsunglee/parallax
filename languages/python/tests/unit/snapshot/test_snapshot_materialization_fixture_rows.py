from __future__ import annotations

from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.db_port import MappingRow
from parallax.snapshot import prepare_model
from parallax.snapshot.handle._publication import read_projection
from tests.unit._snapshot_materialization_support import (
    Layout,
    compiled_levels,
    fetch_plan,
    metamodel,
    query,
    rows_per_level,
    workload,
)


def _rows(layout: Layout) -> tuple[tuple[MappingRow, ...], ...]:
    meta = metamodel(layout)
    model = read_projection(prepare_model(workload(layout), edition=f"fixture-rows-{layout}")).model
    plan = fetch_plan(query(layout, meta), meta)
    reads = compiled_levels(layout, plan, meta)
    return rows_per_level(layout, model, plan, reads)


# The stress fixtures author only Owner id/name/favoriteId and Node
# id/ownerId/label/tags. Driver rows must preserve those values and omissions
# under each physical layout: Columns exposes nullable omitted scalars as SQL
# nulls and empty tags in their own document column, while Document puts only
# the authored document-resident members in payload. This distinguishes catalog
# row ownership from a helper that fills omitted members locally.
def test_materialization_driver_rows_preserve_the_sparse_fixture_payload() -> None:
    columns = _rows("columns")
    assert columns[0][0] == {"id": 1000, "name": "owner-0", "favorite_id": 10000}
    columns_node = columns[1][0]
    assert {
        name: value
        for name, value in columns_node.items()
        if value is not None and value is not SQL_NULL
    } == {
        "id": 10000,
        "owner_id": 1000,
        "label": "node-0-0",
        "tags": PresentDocument([]),
        "kind": "alpha",
    }

    document = _rows("document")
    assert document[0][0] == {
        "id": 1000,
        "favorite_id": 10000,
        "payload": PresentDocument({"name": "owner-0"}),
    }
    assert document[1][0] == {
        "id": 10000,
        "owner_id": 1000,
        "kind": "alpha",
        "payload": PresentDocument({"label": "node-0-0", "tags": []}),
    }
