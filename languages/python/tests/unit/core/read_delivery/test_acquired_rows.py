"""How a flat Page's rows are judged: a read's level recording each row key once
judges them as it records them, and a write's acquisition leaves its occurrences
unjudged however its level is proved."""

from __future__ import annotations

from typing import Any, Final

import pytest

from parallax.core._execution._read_query import resolve_read_query
from parallax.core.internal import predicate as oa
from parallax.core.internal.base import StructuredDocument
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import entity_by_name
from parallax.core.internal.object_query import deserialize
from parallax.core.internal.read_delivery import _acquired_rows, _convert
from parallax.core.internal.read_delivery._page import ABSENT, ROOT_LEVEL, entity_state, page_rows
from parallax.core.internal.read_delivery._page_reader import FlatPageRequest, PageReader
from parallax.core.internal.read_delivery._read_plan import UNCACHED_READ_PLANNER, EmptyRead
from parallax.core.internal.temporal_read import Pin
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model, target
from tests.unit._prepared_read_support import compiled_read, result_row
from tests.unit.snapshot._encoded_page_models import ENCODED_ORDERS

_ENCODED: Final = model_of(ENCODED_ORDERS)
_DOCUMENT: Final = model("document")
_ADDRESS: Final = StructuredDocument({"street": "Main", "city": None, "geo": None, "phones": []})


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
    admitted = list(_acquired_rows.admitted_member_rows(stage.page))
    assert [row[2] for row in admitted] == [b"\x0e", b"\x0f"]
    assert all(row[3] == _ADDRESS for row in admitted)


def test_a_union_acquisition_keeps_colliding_concrete_keys_as_distinct_rows() -> None:
    compiled = compile_read(oa.TrueNode(), _DOCUMENT, POSTGRES, target(_DOCUMENT, "Document"))
    rows = (
        result_row(
            compiled,
            {
                "id": 1,
                "title": "Invoice A",
                "folder_id": 3,
                "currency": "USD",
                "amount_due": "10.00",
                "body": None,
                "paid_amount": None,
                "family_variant": "Invoice",
            },
        ),
        result_row(
            compiled,
            {
                "id": 1,
                "title": "Memo B",
                "folder_id": 3,
                "currency": None,
                "amount_due": None,
                "body": "Text",
                "paid_amount": None,
                "family_variant": "Memo",
            },
        ),
    )

    stage = PageReader().read_page(
        FlatPageRequest(CatalogedModel(_DOCUMENT), compiled, lambda: rows, Pin())
    )

    page = page_rows(stage.page)
    assert page.schema.may_repeat_rows(ROOT_LEVEL)
    assert list(page.logical_rows) == [0, 0]
    assert [page.layouts[root].concrete.name for root in page.roots] == ["Invoice", "Memo"]
    assert [row[1] for row in _acquired_rows.admitted_member_rows(stage.page)] == [
        "Invoice A",
        "Memo B",
    ]


def test_an_acquisition_projecting_no_value_object_leaves_its_occurrence_unjudged() -> None:
    order = entity_by_name(_ENCODED, "EncodedOrder")
    assert order is not None
    compiled = compile_read(oa.TrueNode(), _ENCODED, POSTGRES, order)
    rows = (result_row(compiled, {"id": 1, "name": "Ada", "badge_hex": "0e"}),)

    stage = PageReader().read_page(
        FlatPageRequest(CatalogedModel(_ENCODED), compiled, lambda: rows, Pin())
    )

    (row,) = _acquired_rows.publishable_member_rows(stage.page)
    assert row[:3] == (1, "Ada", b"\x0e")
    assert row[3] is ABSENT


def test_a_level_recording_each_key_once_judges_its_rows_as_it_records_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = resolve_read_query(
        deserialize({"target": "EncodedOrder", "predicate": {"true": {}}}),
        model=_ENCODED,
    )
    plan = UNCACHED_READ_PLANNER.plan(
        edition="",
        model=CatalogedModel(_ENCODED),
        dialect=POSTGRES,
        query=query,
        preference=None,
    )
    root = plan.root_read()
    assert not isinstance(root, EmptyRead)
    compiled, converter = root
    builder = plan.page_builder(None)
    refs = tuple(
        converter.record_row(result_row(compiled, cells), builder, source=ROOT_LEVEL)[0]
        for cells in (_order(1, "0e"), _order(2, "zz"))
    )
    page = page_rows(builder.finish(refs, Pin()))

    def refuse(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("reading a recorded row judged it again")

    monkeypatch.setattr(_convert, "judge_positions", refuse)
    monkeypatch.setattr(_convert.EntityReadMapping, "decode_payload", refuse)
    first, second = (entity_state(page, ref) for ref in page.roots)

    assert first.member_row[2] == b"\x0e"
    assert first.findings == ()
    assert [issue.code for issue in second.findings] == ["stored-data-leaf-undecodable"]
