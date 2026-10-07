from __future__ import annotations

import pytest

from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.execution import prepare_model
from parallax.core.execution._publication import read_projection
from tests.unit._snapshot_materialization_support import (
    LAYOUTS,
    Layout,
    StressPort,
    batch,
    compiled_levels,
    query,
    read_plan,
    rows_per_level,
    verify,
    workload,
)

_NODE_COLUMNS = (
    "id",
    "kind",
    "owner_id",
    "label",
    "flag",
    "small",
    "big",
    "ratio",
    "measure",
    "amount",
    "blob_hex",
    "day",
    "clock",
    "instant",
    "token",
    "rank",
    "weight",
    "primary_tag",
    "tags",
)
_UNAUTHORED_SCALARS = 13


def _first_rows(layout: Layout) -> tuple[tuple[tuple[str, ...], tuple[object, ...]] | None, ...]:
    model = read_projection(prepare_model(workload(layout), edition=f"fixture-rows-{layout}")).model
    plan = read_plan(model, query(layout, model.meta))
    reads = compiled_levels(layout, plan)
    positional = rows_per_level(layout, model, plan, reads)
    return tuple(
        None if read is None else (read.result_keys, level_rows[0])
        for read, level_rows in zip(reads, positional, strict=True)
    )


# The stress fixtures author only Owner id/name/favoriteId and Node
# id/ownerId/label/tags. Driver rows must preserve those values and omissions
# under each physical layout, in the compiled select-list order: Columns exposes
# the unauthored nullable scalars as nulls, the encoded primary tag as SQL_NULL,
# and the empty tags in their own document column, while Document puts only the
# authored document-resident members in payload. This distinguishes catalog row
# ownership from a helper that fills omitted members locally.
def test_materialization_driver_rows_preserve_the_sparse_fixture_payload() -> None:
    columns = _first_rows("columns")
    assert columns[0] == (("id", "name", "favorite_id"), (1000, "owner-0", 10000))
    assert columns[1] == (
        _NODE_COLUMNS,
        (
            10000,
            "alpha",
            1000,
            "node-0-0",
            *([None] * _UNAUTHORED_SCALARS),
            SQL_NULL,
            PresentDocument([]),
        ),
    )

    document = _first_rows("document")
    assert document[0] == (
        ("id", "favorite_id", "payload"),
        (1000, 10000, PresentDocument({"name": "owner-0"})),
    )
    assert document[1] == (
        ("id", "kind", "owner_id", "payload"),
        (10000, "alpha", 1000, PresentDocument({"label": "node-0-0", "tags": []})),
    )


@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_stress_batch_forms_its_stated_page_through_the_production_read_loop(
    layout: Layout,
) -> None:
    model = read_projection(prepare_model(workload(layout), edition=f"fixture-rows-{layout}")).model
    validated = query(layout, model.meta)
    plan = read_plan(model, validated)
    reads = compiled_levels(layout, plan)
    port = StressPort(reads, rows_per_level(layout, model, plan, reads))
    verify(model, plan, batch(model, validated, plan, port).page)
