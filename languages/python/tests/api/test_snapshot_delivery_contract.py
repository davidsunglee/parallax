"""Streamed delivery behavior that only a mutable real database can prove."""

from __future__ import annotations

from typing import Any, cast

import pytest

from parallax.conformance import case_format, engine, provision
from parallax.conformance.case_format import default_cases_dir
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.snapshot import connect


def _seeded(profile_run: Any) -> None:
    case = case_format.load_case(default_cases_dir() / "m-object-query-001-order-by-limit.yaml")
    profile_run.reset(
        engine.load_case_metamodel(case), provision.load_fixtures(str(case.document["model"]))
    )


def _write(profile_run: Any, sql: str) -> None:
    control = profile_run.control()
    try:
        control.execute_write(sql, ())
    finally:
        control.close()


@pytest.mark.parametrize("batch_size", [1, 2, 8])
def test_a_leading_null_under_a_dropped_constraint_is_never_lost_at_a_page_boundary(
    profile_run: Any, batch_size: int
) -> None:
    _seeded(profile_run)
    _write(profile_run, "alter table orders alter column active drop not null")
    _write(profile_run, "update orders set active = null where id = 42")
    query = Order.where(Order.all).order_by(Order.active.asc())

    with (
        connect(profile_run.port, ORDERS_MODEL) as db,
        db.stream(query, batch_size=batch_size) as stream,
    ):
        roots = list(stream.checked())

    assert all(isinstance(root, Order) for root in roots)
    typed = cast("list[Order]", roots)
    assert [root.id for root in typed] == [3, 5, 1, 2, 4, 42]
    assert typed[-1].active is None


@pytest.mark.parametrize("movement", ["ahead-to-behind", "behind-to-ahead"])
def test_moving_an_authored_sort_key_can_skip_or_duplicate_a_root(
    profile_run: Any, movement: str
) -> None:
    _seeded(profile_run)
    query = Order.where(Order.all).order_by(Order.qty.asc())

    with (
        connect(profile_run.port, ORDERS_MODEL) as db,
        db.stream(query, batch_size=1) as stream,
    ):
        roots = iter(stream)
        delivered = [next(roots).id]
        if movement == "ahead-to-behind":
            _write(profile_run, "update orders set qty = 1 where id = 2")
        else:
            _write(profile_run, "update orders set qty = 100 where id = 1")
        delivered.extend(root.id for root in roots)

    if movement == "ahead-to-behind":
        assert delivered == [1, 3, 4, 5, 42]
    else:
        assert delivered == [1, 2, 3, 4, 5, 42, 1]
