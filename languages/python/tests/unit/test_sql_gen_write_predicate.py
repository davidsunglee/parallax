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
CUSTOMER = _MODELS["customer"]
PAYMENT = _MODELS["payment"]


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


def test_value_object_document_column_renders_unaliased() -> None:
    # A value object's structured-DOCUMENT column is not an `Attribute`, so it does
    # not reach the unaliased formatter through `column_of` the way a scalar does.
    # It must render bare all the same: Customer is transactional/non-temporal and
    # unversioned, so this fragment is spliced into the READLESS
    # `update customer set … where <fragment>` template — where a leaked `t0` names
    # an alias the statement never declares (m-sql rule 1: DML is unaliased with
    # bare columns).
    sql, binds = compile_write_predicate(
        oa.NestedComparison(op="nestedEq", path="Customer.address.city", value="Boston"),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    assert sql == "jsonb_extract_path_text(address, ?) = ?"
    assert binds == ("city", "Boston")
    # The read lane is the control: identical but for the alias qualification, so
    # this pins the DIFFERENCE rather than merely the write's own text.
    read = compile_read(
        oa.NestedComparison(op="nestedEq", path="Customer.address.city", value="Boston"),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    read_where = read.sql.split(" where ", 1)[1]
    assert read_where == "jsonb_extract_path_text(t0.address, ?) = ?"
    assert read_where.replace("t0.", "") == sql


def test_to_many_value_object_traversal_keeps_only_its_own_element_alias() -> None:
    # The array paths reach the document column through a different dialect helper
    # (`array_guard`) than the scalar extraction above, so they leak independently.
    # The `t1` element alias MUST survive — this subquery declares it itself — while
    # the owning document column must go bare, exactly as the navigation hop above
    # keeps `t1` and drops the owner's alias.
    for op in (
        oa.NestedComparison(op="nestedEq", path="Customer.address.phones.number", value="555"),
        oa.NestedExists(path="Customer.address.phones"),
    ):
        sql, _ = compile_write_predicate(op, CUSTOMER, POSTGRES, "Customer")
        assert "t0." not in sql
        assert "jsonb_extract_path(address, ?)" in sql
        assert "jsonb_array_elements(" in sql and " t1" in sql


def test_inheritance_tag_guard_renders_unaliased() -> None:
    # The framework-owned TAG column is this target's own column and takes the
    # same rendering decision every declared attribute does. It is not reachable
    # through `column_of` (the tag is metadata, not an `Attribute`), so it leaks
    # independently — exactly as the value-object DOCUMENT column above does.
    #
    # This is a STRUCTURAL pin, deliberately independent of the write lane's own
    # `subtype-write-set-based-unsupported` rejection
    # (`_keyed_sql.lower_predicate_write`, pinned in `test_write_lowering.py`):
    # that rejection is policy and lives at the write boundary; `sql_gen` is a
    # pure renderer that must not depend on some caller having applied it. The
    # previous unreachability argument for this site — "every predicate-write
    # entry point rejects inheritance families first" — was WRONG (the exported
    # `lower_write` and `engine._lower_predicate_write_step` both bypassed the
    # buffer-time guards), which is the whole reason this renders through
    # `_Ctx.own_column` now rather than trusting a caller.
    op = oa.Narrow(
        entity="Payment",
        to=("CardPayment",),
        operand=oa.Comparison(op="eq", attr="CardPayment.cardNetwork", value="Visa"),
    )
    sql, binds = compile_write_predicate(op, PAYMENT, POSTGRES, "CardPayment")
    assert sql == "(card_network = ? and kind = ?)"
    assert binds == ("Visa", "card")
    assert "t0." not in sql
    # The read lane is the control, and it must be the MID-predicate spelling to
    # compare like with like: a TOP-LEVEL narrow is intercepted by the TPH read
    # compiler before `_lower_predicate` ever runs. Wrapped in a `group` both
    # lanes reach `_lower_branch_narrow`; the read then additionally appends the
    # concrete TARGET's own guard, which a bare write fragment has no analogue of
    # — so the comparison is against the read's leading grouped term, which does
    # coincide exactly modulo alias qualification, tag bind last in both.
    grouped = oa.Group(operand=op)
    write_sql, write_binds = compile_write_predicate(grouped, PAYMENT, POSTGRES, "CardPayment")
    read = compile_read(grouped, PAYMENT, POSTGRES, "CardPayment")
    read_where = read.sql.split(" where ", 1)[1]
    assert read_where == "((t0.card_network = ? and t0.kind = ?)) and t0.kind = ?"
    read_branch, _, _target_guard = read_where.rpartition(" and ")
    assert read_branch.replace("t0.", "") == write_sql
    assert write_binds == ("Visa", "card")
    assert read.binds == ("Visa", "card", "card")


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
