"""Compiled locking continuation pages, executed against the provider."""

from __future__ import annotations

from contextlib import closing

import pytest

from parallax.conformance import concurrency_runner, models, provision
from parallax.conformance.concurrency_runner import ConcurrencyStep
from parallax.conformance.profile import ProvisionedRun
from parallax.core import continuation, read_planning
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import CompiledEntity, Metamodel
from parallax.core.object_query import OrderKey, object_query, validate_object_query
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.predicate import TrueNode
from parallax.core.sql_gen._compile import compile_read, compile_template


def _model(stem: str) -> Metamodel:
    return models.load_model(models.default_models_dir() / f"{stem}.yaml")


def _target(metamodel: Metamodel, name: str) -> CompiledEntity:
    return next(entity for entity in metamodel.entities if entity.identity.name == name)


def test_locking_continuation_binds_document_coordinates_in_projection_order(
    profile_run: ProvisionedRun,
) -> None:
    metamodel = _model("document-layout")
    entity = _target(metamodel, "Trip")
    query = object_query(
        entity.identity,
        TrueNode(),
        order_by=(
            OrderKey(attr="parallax.compatibility.Trip.travelerId"),
            OrderKey(attr="parallax.compatibility.Trip.nights"),
        ),
    )
    pages = continuation.plan(validate_object_query(entity, query, metamodel), metamodel)
    cold = pages.after(ContinuationCoordinate((1, 0, 50)), limit=1)
    current = pages.after(ContinuationCoordinate((1, 1, 52)), limit=2)
    template = compile_template(
        read_planning.plan(
            cold, metamodel, projection=read_planning.ReadProjectionRequest("none", False)
        ).root,
        metamodel,
        POSTGRES,
        shared_lock=True,
    )
    compiled = template.render(query=current)
    profile_run.reset(metamodel, provision.load_fixtures("models/document-layout.yaml"))
    with closing(profile_run.control(autocommit=False)) as connection:
        rows = connection.execute(
            POSTGRES.to_driver_sql(compiled.statement.sql),
            compiled.statement.wire_binds(),
            compiled.document_reads,
        )
    assert compiled.document_reads == ((2, 3),)
    assert [tuple(row[:2]) for row in rows] == [(51, 1), (53, 2)]
    assert [tuple(row[-3:]) for row in rows] == [(1, 3, 51), (2, 7, 53)]
    assert all(len(row) == 6 for row in rows)


@pytest.mark.parametrize("locked_id", [5, 7], ids=["ordinary-branch", "null-tail-branch"])
def test_a_narrowed_abstract_continuation_locks_its_concrete_rows(
    profile_run: ProvisionedRun, locked_id: int
) -> None:
    metamodel = _model("predicate-traversal")
    entity = _target(metamodel, "Vehicle")
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
        read_planning.plan(
            page, metamodel, projection=read_planning.ReadProjectionRequest("none", False)
        ).root,
        metamodel,
        POSTGRES,
        shared_lock=True,
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
