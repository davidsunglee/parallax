"""The row lane's two consumers of a flat Page: row-form publication, whose rows
a level recording each row key once judges as it records them, and a write's
acquisition, whose occurrences stay unjudged however its level is proved."""

from __future__ import annotations

from typing import Any, Final, cast

import pytest

from parallax.core._execution._concurrency import CONCURRENCY
from parallax.core._execution._read_query import resolve_read_query
from parallax.core.base import PresentDocument
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.object_query import deserialize
from parallax.core.read_delivery import _convert, _row_lane
from parallax.core.read_delivery._page import ROOT_LEVEL, page_rows
from parallax.core.read_delivery._page_reader import FlatPageRequest, FlatPageResult, PageReader
from parallax.core.read_delivery._read_plan import UNCACHED_READ_PLANNER, EmptyRead
from parallax.core.read_delivery._row_lane import (
    _published_rows,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.temporal_read import Pin
from tests.unit._prepared_read_support import compiled_read, result_row
from tests.unit.snapshot._encoded_page_models import ENCODED_ORDERS

_ENCODED: Final = model_of(ENCODED_ORDERS)
_ADDRESS: Final = PresentDocument({"street": "Main", "city": None, "geo": None, "phones": []})


def _order(order_id: int, badge: str) -> dict[str, object]:
    return {"id": order_id, "name": "Ada", "badge_hex": badge, "address": _ADDRESS}


def test_an_acquisition_defers_its_payload_on_a_level_that_records_each_key_once() -> None:
    compiled = compiled_read(_ENCODED, "EncodedOrder")
    rows = (result_row(compiled, _order(1, "0e")), result_row(compiled, _order(2, "0f")))

    stage = PageReader().read_page(
        FlatPageRequest(CatalogedModel(_ENCODED), compiled, lambda: rows, Pin())
    )

    page = page_rows(stage.page)
    assert not page.schema.may_repeat_rows(ROOT_LEVEL)
    assert list(page.logical_rows) == [0, 1]
    assert [page.decoders.pending(fetched_row) for fetched_row in (0, 1)] == [True, True]
    admitted = list(_row_lane.admitted_member_rows(stage.page))
    assert [row[2] for row in admitted] == [b"\x0e", b"\x0f"]
    assert all(row[3] == _ADDRESS for row in admitted)


def test_a_row_form_read_judges_its_rows_as_it_records_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cataloged = CatalogedModel(_ENCODED)
    query = resolve_read_query(
        deserialize({"target": "EncodedOrder", "predicate": {"true": {}}}),
        model=_ENCODED,
        form="rows",
    )
    plan = UNCACHED_READ_PLANNER.plan(
        edition="",
        model=cataloged,
        dialect=POSTGRES,
        query=query,
        result_form="row",
        preference=None,
    )
    root = plan.root_read()
    assert not isinstance(root, EmptyRead)
    compiled, converter = root
    builder = plan.page_builder(None)
    recorded = [
        converter.record_row(result_row(compiled, cells), builder, source=ROOT_LEVEL)
        for cells in (
            {"id": 1, "name": "Ada", "badge_hex": "0e"},
            {"id": 2, "name": "Ada", "badge_hex": "zz"},
        )
    ]
    stage = FlatPageResult(
        tuple(item[3] for item in recorded),
        tuple(item[2] for item in recorded),
        builder.finish(tuple(item[0] for item in recorded), Pin()),
    )

    def refuse(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("row-form publication judged a recorded row again")

    monkeypatch.setattr(_convert, "judge_positions", refuse)
    monkeypatch.setattr(_convert.EntityReadMapping, "decode_payload", refuse)
    first, second = _published_rows(stage, _ENCODED, CONCURRENCY, converter.row_publisher())

    assert dict(cast("Any", first))["badge_hex"] == "0e"
    assert [issue.code for issue in cast("Any", second).issues] == ["stored-data-leaf-undecodable"]
