"""Write-predicate lowering (`m-batch-write` "Predicate-selected readless forms").

`compile_write_predicate` renders a BARE, UNALIASED where-clause fragment —
`balance < ?`, never the resolving read's `t0.balance < ?` — for the readless
`update`/`delete` templates in `parallax.snapshot.handle`.

Its single production caller (`lower_predicate_write`) is exercised indirectly
by `test_where_verbs.py`, `test_batch_write.py`, and
`test_transaction_predicate_writes.py`, but nothing pins this function BY NAME.
That matters structurally: the unaliased lane reaches the SAME predicate
dispatch a read's `where` clause does, differing only in how a column reference
is formatted — so a fork in the predicate vocabulary would show up here first
and nowhere else.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import SqlGenError, compile_read, compile_write_predicate

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
ACCOUNT = _MODELS["account"]


# --------------------------------------------------------------------------- #
# Unaliased column rendering — the one thing that differs from a read.        #
# --------------------------------------------------------------------------- #
def test_comparison_renders_the_column_unaliased() -> None:
    sql, binds = compile_write_predicate(
        oa.Comparison(op="lessThan", attr="Account.balance", value=100),
        ACCOUNT,
        POSTGRES,
        "Account",
    )
    assert sql == "balance < ?"
    assert binds == (100,)


def test_the_rendered_fragment_is_a_predicate_not_a_statement() -> None:
    # A bare fragment: no `select`, no `from`, no owning table alias anywhere —
    # it is spliced into `update <table> set … where <fragment>` by the caller.
    sql, _ = compile_write_predicate(
        oa.Comparison(op="lessThan", attr="Account.balance", value=100),
        ACCOUNT,
        POSTGRES,
        "Account",
    )
    assert "select" not in sql
    assert "from" not in sql
    assert "t0." not in sql


def test_all_renders_the_empty_fragment_and_none_renders_unsatisfiable() -> None:
    assert compile_write_predicate(oa.All(), ACCOUNT, POSTGRES, "Account") == ("", ())
    assert compile_write_predicate(oa.NoneOp(), ACCOUNT, POSTGRES, "Account") == ("1 = 0", ())


# --------------------------------------------------------------------------- #
# One shared vocabulary with reads (m-sql): the write lane reuses the read's  #
# dispatch through an unaliased column formatter rather than forking SQL text #
# assembly, so every operator renders identically modulo the `t0.` prefix and #
# binds in exactly the same order.                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "op, expected_sql, expected_binds",
    [
        (
            oa.Comparison(op="greaterThan", attr="Account.balance", value=5),
            "balance > ?",
            (5,),
        ),
        (oa.NullCheck(op="isNull", attr="Account.owner"), "owner is null", ()),
        (oa.NullCheck(op="isNotNull", attr="Account.owner"), "not owner is null", ()),
        (
            oa.Between(attr="Account.balance", lower=1, upper=9),
            "balance between ? and ?",
            (1, 9),
        ),
        (
            oa.Membership(op="in", attr="Account.id", values=(1, 2)),
            "id in (?, ?)",
            (1, 2),
        ),
        (
            oa.StringMatch(op="startsWith", attr="Account.owner", value="A"),
            "owner like ?",
            ("A%",),
        ),
        (
            oa.StringMatch(op="contains", attr="Account.owner", value="A"),
            "owner like ?",
            ("%A%",),
        ),
        (
            oa.Not(operand=oa.Comparison(op="eq", attr="Account.owner", value="a")),
            "not owner = ?",
            ("a",),
        ),
        (
            oa.Or(
                operands=(
                    oa.Comparison(op="eq", attr="Account.owner", value="a"),
                    oa.Comparison(op="eq", attr="Account.owner", value="b"),
                )
            ),
            "owner = ? or owner = ?",
            ("a", "b"),
        ),
        (
            oa.Group(
                operand=oa.Or(
                    operands=(
                        oa.Comparison(op="eq", attr="Account.owner", value="a"),
                        oa.Not(operand=oa.Comparison(op="eq", attr="Account.owner", value="b")),
                    )
                )
            ),
            "(owner = ? or not owner = ?)",
            ("a", "b"),
        ),
    ],
)
def test_write_predicate_vocabulary_matches_the_read_dispatch(
    op: oa.Operation, expected_sql: str, expected_binds: tuple[object, ...]
) -> None:
    sql, binds = compile_write_predicate(op, ACCOUNT, POSTGRES, "Account")
    assert sql == expected_sql
    assert binds == expected_binds
    # The same node lowers through the same dispatch inside a read's `where`
    # clause, differing ONLY in the alias qualification of each column: strip the
    # root alias from the read's clause and the two fragments coincide exactly,
    # binds included.
    read = compile_read(op, ACCOUNT, POSTGRES, "Account")
    read_where = read.sql.split(" where ", 1)[1]
    assert read_where.replace("t0.", "") == expected_sql
    assert read.binds == expected_binds


def test_write_predicate_binds_follow_operand_order() -> None:
    # `And.operands` order is significant precisely because it drives bind order;
    # the write lane accumulates into the same ordered bind list a read does.
    sql, binds = compile_write_predicate(
        oa.And(
            operands=(
                oa.Comparison(op="lessThan", attr="Account.balance", value=100),
                oa.Comparison(op="eq", attr="Account.owner", value="ada"),
                oa.Comparison(op="eq", attr="Account.version", value=3),
            )
        ),
        ACCOUNT,
        POSTGRES,
        "Account",
    )
    assert sql == "balance < ? and owner = ? and version = ?"
    assert binds == (100, "ada", 3)


def test_navigation_correlates_an_aliased_subquery_against_the_unaliased_owner() -> None:
    # A hop opens its own aliased sub-select exactly as it does in a read, but the
    # correlation's OWNER side stays unaliased — the readless `delete from orders
    # where exists (...)` shape.
    sql, binds = compile_write_predicate(oa.Exists(rel="Order.items"), ORDERS, POSTGRES, "Order")
    assert sql == "exists (select 1 from order_item t1 where t1.order_id = id)"
    assert binds == ()


# --------------------------------------------------------------------------- #
# Refusals — identical to the read lane's, since it is the same dispatcher.   #
# --------------------------------------------------------------------------- #
def test_unbound_attribute_is_refused() -> None:
    with pytest.raises(SqlGenError, match="names no attribute"):
        compile_write_predicate(
            oa.Comparison(op="eq", attr="Account.mystery", value=1), ACCOUNT, POSTGRES, "Account"
        )


@pytest.mark.parametrize(
    "op",
    [
        oa.Limit(operand=oa.All(), count=3),
        oa.Distinct(operand=oa.All()),
        oa.OrderBy(operand=oa.All(), keys=()),
    ],
)
def test_a_result_shaping_directive_reaching_a_write_predicate_is_refused(
    op: oa.Operation,
) -> None:
    # `op` MUST arrive bare — a set-based write target is validated bare upstream,
    # so a directive here is a caller wiring defect and refuses exactly as it would
    # inside an ordinary read's predicate (no directive PEELING happens here).
    with pytest.raises(SqlGenError, match="result-shaping directive nested inside a predicate"):
        compile_write_predicate(op, ORDERS, POSTGRES, "Order")


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
        compile_write_predicate(op, ORDERS, POSTGRES, "Order")
