from __future__ import annotations

from contextlib import closing

import pytest

from parallax.conformance import concurrency_runner, provision
from parallax.conformance.concurrency_runner import ConcurrencyStep
from parallax.conformance.profile import ProvisionedRun
from parallax.core import continuation, deep_fetch
from parallax.core.dialect import POSTGRES
from parallax.core.object_query import OrderKey, object_query, validate_object_query
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.predicate import TrueNode
from parallax.core.sql_gen._compile import compile_read
from tests.unit._corpus_model_support import model, target


@pytest.mark.parametrize("locked_id", [5, 7], ids=["ordinary-branch", "null-tail-branch"])
def test_a_narrowed_abstract_continuation_locks_its_concrete_rows(
    profile_run: ProvisionedRun, locked_id: int
) -> None:
    metamodel = model("predicate-traversal")
    entity = target(metamodel, "Vehicle")
    query = object_query(
        entity.identity,
        TrueNode(),
        narrow_to=("parallax.compatibility.Car",),
        order_by=(OrderKey(attr="parallax.compatibility.Vehicle.dealerId"),),
    )
    page = continuation.plan(validate_object_query(entity, query, metamodel), metamodel).after(
        ContinuationCoordinate((3, 1)), limit=2
    )
    compiled = compile_read(
        deep_fetch.plan(
            page, metamodel, projection=deep_fetch.ReadProjectionRequest("none", False)
        ).root,
        metamodel,
        POSTGRES,
        lock="locking",
    )
    expected = (
        {
            "id": 5,
            "maker": "Volvo",
            "dealer_id": 40,
            "seats": 4,
            "parallax_seek_0": 40,
            "parallax_seek_1": 5,
        },
        {
            "id": 7,
            "maker": "Saab",
            "dealer_id": None,
            "seats": None,
            "parallax_seek_0": None,
            "parallax_seek_1": 7,
        },
    )
    rounds = (
        {
            "A": ConcurrencyStep(
                statements=((compiled.statement.sql, compiled.statement.binds),),
                kind="read",
                expect_rows=expected,
            )
        },
        {
            "B": ConcurrencyStep(
                statements=(("update traversal_bike set gears = ? where id = ?", (22, 6)),),
                kind="write",
                expect_rows=None,
            )
        },
        {
            "B": ConcurrencyStep(
                statements=(("update traversal_car set seats = ? where id = ?", (2, locked_id)),),
                kind="write",
                expect_rows=None,
                blocks=True,
            )
        },
    )
    profile_run.reset(metamodel, provision.load_fixtures("models/predicate-traversal.yaml"))
    with closing(profile_run.control(autocommit=True)) as observer:
        result = concurrency_runner.run_rounds(
            rounds,
            lambda: profile_run.control(autocommit=False),
            lock_waits=concurrency_runner.lock_waits_on(observer),
        )

    read = result.rounds[0]["A"]
    assert read.error is None
    assert read.rows == expected
    other_table = result.rounds[1]["B"]
    assert other_table.error is None
    assert other_table.affected == (1,)
    locked = result.rounds[2]["B"]
    assert locked.waited
    assert locked.error is not None
    assert locked.error.category == "lockWaitTimeout"
    assert locked.error.native_code == "55P03"
