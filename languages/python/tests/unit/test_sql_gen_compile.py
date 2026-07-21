"""Ordinary read assembly (m-sql lowering): projection, directives, clause tail.

The non-family, non-navigation, non-value-object lane of the read compiler: the
`Statement` value itself, ordinary scalar/row projection, result-shaping
directive composition and its refusals, the read-lock suffix and its `distinct`
suppression, the deferred-node refusals, and the bind-ORDER invariants the
whole compiler rests on (projection binds before predicate binds, limit bind
last). Inheritance families, navigation hops, value-object traversal, and write
predicates each have their own suite.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import SqlGenError, Statement, compile_read

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
CUSTOMER = _MODELS["customer"]
ACCOUNT = _MODELS["account"]
SCALARS = _MODELS["scalars"]


def test_all_projects_scalar_columns() -> None:
    statement = compile_read(oa.All(), ORDERS, POSTGRES, "Order")
    assert statement.sql == (
        "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0"
    )
    assert statement.binds == ()


def test_none_lowers_to_unsatisfiable() -> None:
    statement = compile_read(oa.NoneOp(), ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith("where 1 = 0")


def test_instance_form_projects_value_object_document_last() -> None:
    # Instance-form (the object lane, m-sql *Read projection* slot 4): the value
    # object's document column rides the owner's SELECT, last among all columns.
    instance = compile_read(oa.All(), CUSTOMER, POSTGRES, "Customer", result_form="instance")
    assert instance.sql == "select t0.id, t0.name, t0.address from customer t0"
    # Row-form (the default values lane) omits slot 4 — the scalars alone.
    row = compile_read(oa.All(), CUSTOMER, POSTGRES, "Customer")
    assert row.sql == "select t0.id, t0.name from customer t0"


def test_unbound_attribute_is_refused() -> None:
    with pytest.raises(SqlGenError, match="names no attribute"):
        compile_read(
            oa.Comparison(op="eq", attr="Order.mystery", value=1), ORDERS, POSTGRES, "Order"
        )


@pytest.mark.parametrize(
    "op, message",
    [
        (oa.AsOf(operand=oa.All(), as_of_attr="Order.p", date="now"), "temporal wrapper reached"),
        (
            oa.DeepFetch(operand=oa.All(), paths=((oa.PathSegment(rel="Order.items"),),)),
            "deep fetch .* increment 5",
        ),
    ],
)
def test_deferred_nodes_are_refused(op: oa.Operation, message: str) -> None:
    with pytest.raises(SqlGenError, match=message):
        compile_read(op, ORDERS, POSTGRES, "Order")


def test_directive_nested_in_predicate_is_refused() -> None:
    op = oa.Not(operand=oa.Distinct(operand=oa.All()))
    with pytest.raises(SqlGenError, match="result-shaping directive nested"):
        compile_read(op, ORDERS, POSTGRES, "Order")


def test_stacked_duplicate_directive_is_refused() -> None:
    # limit(limit(all, 10), 5): the outer cap of 5 must not be silently overwritten
    # by peeling the inner cap of 10. Stacked same-kind directives have no defined
    # composition, so lowering refuses loudly.
    op = oa.Limit(operand=oa.Limit(operand=oa.All(), count=10), count=5)
    with pytest.raises(SqlGenError, match=r"stacked `limit` directives"):
        compile_read(op, ORDERS, POSTGRES, "Order")


def test_single_of_each_directive_still_composes() -> None:
    # One of each directive (distinct/orderBy/limit) is the canonical stack and
    # lowers to the ordered clauses, unaffected by the duplicate-directive guard.
    op = oa.Limit(
        operand=oa.OrderBy(
            operand=oa.Distinct(operand=oa.All()),
            keys=(oa.OrderKey(attr="Order.id", direction="asc"),),
        ),
        count=5,
    )
    statement = compile_read(op, ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith("order by t0.id asc limit ?")
    assert "select distinct" in statement.sql


def test_statement_is_frozen_value() -> None:
    statement = Statement("select 1", (1,))
    assert statement.sql == "select 1"
    assert statement.binds == (1,)


# --------------------------------------------------------------------------- #
# Bind ORDER across the four phases (m-sql; the state invariants the private   #
# split must preserve). Bind order is produced STRUCTURALLY by call ordering   #
# — projection, then the user predicate, then any framework guard, then the    #
# limit — never by a sorting pass, so these pins are what catch a reordered    #
# lowering that still emits byte-identical SQL text.                           #
#                                                                              #
# `ScalarThing` is the only corpus model with a bind-EMITTING projection: a    #
# `bytes` column projects `encode(t0.payload, ?) payload_hex` with the bind    #
# `hex` (m-dialect). Combining it with a bind-emitting predicate and a         #
# trailing limit is a shape no Docker-free corpus case reaches — the one that  #
# does (`m-navigate-024`) is `compileEligibility: run-only` — so the pins are  #
# built from the corpus-loaded model directly.                                 #
# --------------------------------------------------------------------------- #
def test_projection_binds_precede_predicate_binds() -> None:
    # The projection's own dialect bind (`hex`) is spliced into the context BEFORE
    # the predicate lowers, so it leads the tuple however many predicate binds
    # follow. Placeholder order in the SQL and bind order must agree.
    statement = compile_read(
        oa.Comparison(op="greaterThan", attr="ScalarThing.f64", value=1.5),
        SCALARS,
        POSTGRES,
        "ScalarThing",
    )
    assert statement.sql == (
        "select t0.id, t0.f32, t0.f64, encode(t0.payload, ?) payload_hex, t0.local_time, "
        "t0.external_id from scalar_thing t0 where t0.f64 > ?"
    )
    assert statement.binds == ("hex", 1.5)


def test_limit_bind_lands_after_predicate_binds() -> None:
    # The limit clause is appended by the shared clause tail AFTER the `where`
    # clause is already assembled, so its bind is last — behind both the
    # projection bind and every user-predicate bind.
    statement = compile_read(
        oa.Limit(
            operand=oa.Comparison(op="greaterThan", attr="ScalarThing.f64", value=1.5), count=3
        ),
        SCALARS,
        POSTGRES,
        "ScalarThing",
    )
    assert statement.sql.endswith("from scalar_thing t0 where t0.f64 > ? limit ?")
    assert statement.binds == ("hex", 1.5, 3)


# --------------------------------------------------------------------------- #
# Read-lock suffix (m-sql *Read-lock suffix*, via the m-dialect seam).         #
# --------------------------------------------------------------------------- #
def test_locking_object_find_matches_the_scenario_find_golden() -> None:
    # The exact m-unit-work-001 step-1 golden: an in-transaction object find in the
    # default `locking` mode carries the shared-row-lock suffix, last in the statement.
    statement = compile_read(
        oa.Comparison(op="eq", attr="Account.id", value=7),
        ACCOUNT,
        POSTGRES,
        "Account",
        lock="locking",
    )
    assert statement.sql == (
        "select t0.id, t0.owner, t0.balance, t0.version from account t0 "
        "where t0.id = ? for share of t0"
    )
    assert statement.binds == (7,)


def test_optimistic_and_default_reads_take_no_lock() -> None:
    for lock in (None, "optimistic"):
        statement = compile_read(oa.All(), ACCOUNT, POSTGRES, "Account", lock=lock)  # type: ignore[arg-type]
        assert "for share" not in statement.sql


def test_distinct_read_suppresses_the_lock_even_in_locking_mode() -> None:
    # A `distinct` result has no identifiable base row to lock (read-lock suppression).
    statement = compile_read(
        oa.Distinct(operand=oa.All()), ACCOUNT, POSTGRES, "Account", lock="locking"
    )
    assert "for share" not in statement.sql
