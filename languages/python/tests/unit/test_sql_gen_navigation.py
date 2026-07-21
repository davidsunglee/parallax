"""Navigation lowering (m-sql "Joins by navigation" / "Polymorphic navigation").

These feed already-canonicalized operations directly (the per-hop as-of rewrite
is `parallax.core.navigate`'s job, tested in `test_navigate.py`) — this module
only lowers whatever op-algebra tree it receives.

Beyond the correlated `EXISTS` shapes themselves, this suite pins the ALIAS
sequence: one statement allocates one depth-first, source-ordered sequence
shared across every nested and sibling subquery, which is the state invariant
the private-module split must preserve.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import compile_read

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
ANIMAL = _MODELS["animal"]
DOCUMENT = _MODELS["document"]
PERSON = _MODELS["person"]


def test_navigate_to_many_lowers_to_correlated_exists() -> None:
    op = oa.Navigate(
        rel="Order.items", op=oa.Comparison(op="eq", attr="OrderItem.sku", value="A-100")
    )
    compiled = compile_read(op, ORDERS, POSTGRES, "Order")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and t1.sku = ?)"
    )
    assert compiled.statement.binds == ("A-100",)


def test_exists_with_no_inner_op_is_a_pure_correlation_check() -> None:
    compiled = compile_read(oa.Exists(rel="Order.items"), ORDERS, POSTGRES, "Order")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id)"
    )
    assert compiled.statement.binds == ()


def test_not_exists_negates_the_semi_join() -> None:
    compiled = compile_read(oa.NotExists(rel="Order.items"), ORDERS, POSTGRES, "Order")
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id)"
    )


def test_navigate_composes_inside_the_boolean_algebra() -> None:
    op = oa.And(
        operands=(
            oa.NotExists(rel="Order.items"),
            oa.Comparison(op="eq", attr="Order.active", value=True),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, "Order")
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id) and t0.active = ?"
    )
    assert compiled.statement.binds == (True,)


def test_reverse_to_one_navigation_resolves_the_mirror_correlation() -> None:
    op = oa.Navigate(
        rel="OrderItem.order", op=oa.Comparison(op="eq", attr="Order.name", value="Ada")
    )
    compiled = compile_read(op, ORDERS, POSTGRES, "OrderItem")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from orders t1 where t1.id = t0.order_id and t1.name = ?)"
    )
    assert compiled.statement.binds == ("Ada",)


def test_one_to_one_navigation_lowers_like_any_to_one_hop() -> None:
    op = oa.Navigate(
        rel="Person.passport", op=oa.Comparison(op="eq", attr="Passport.number", value="P-AAA")
    )
    compiled = compile_read(op, PERSON, POSTGRES, "Person")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from passport t1 where t1.person_id = t0.id and t1.number = ?)"
    )


def test_nullable_many_to_one_exists_correlates_on_the_owned_fk() -> None:
    compiled = compile_read(oa.Exists(rel="OrderStatus.orderItem"), ORDERS, POSTGRES, "OrderStatus")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.id = t0.order_item_id)"
    )


def test_multi_hop_exists_continues_the_single_alias_sequence() -> None:
    op = oa.Exists(
        rel="Order.items",
        op=oa.Exists(
            rel="OrderItem.statuses",
            op=oa.Comparison(op="eq", attr="OrderStatus.code", value="PACKED"),
        ),
    )
    compiled = compile_read(op, ORDERS, POSTGRES, "Order")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id and t2.code = ?))"
    )
    assert compiled.statement.binds == ("PACKED",)


def test_not_exists_multi_hop_negates_only_the_outer_hop() -> None:
    op = oa.NotExists(rel="Order.items", op=oa.Exists(rel="OrderItem.statuses"))
    compiled = compile_read(op, ORDERS, POSTGRES, "Order")
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id))"
    )


def test_sibling_hops_continue_one_alias_sequence() -> None:
    # Depth-first, SOURCE-ORDER allocation across nested AND sibling subqueries
    # (m-sql): each hop takes its alias at the point it opens its subquery, before
    # descending, so an interior hop's number is strictly lower than anything its
    # own interior allocates, and a LATER SIBLING takes the next integer after the
    # whole preceding subtree — never restarting, and never interleaving.
    #
    # `items` opens t1 and its interior `statuses` opens t2; the sibling `tags`
    # then takes t3, not t2. The multi-hop pin above covers only nesting, which
    # cannot distinguish one shared sequence from a per-subtree counter.
    op = oa.And(
        operands=(
            oa.Exists(rel="Order.items", op=oa.Exists(rel="OrderItem.statuses")),
            oa.Exists(rel="Order.tags"),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, "Order")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id)) and "
        "exists (select 1 from order_tag t3 where t3.order_id = t0.id)"
    )


# --------------------------------------------------------------------------- #
# Polymorphic navigation lowering (m-sql "Polymorphic navigation lowering").   #
# --------------------------------------------------------------------------- #
def test_tph_abstract_root_relationship_target_injects_no_tag() -> None:
    compiled = compile_read(oa.Exists(rel="Person.animals"), ANIMAL, POSTGRES, "Person")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id)"
    )


def test_tph_abstract_subtype_relationship_target_injects_the_in_list() -> None:
    compiled = compile_read(oa.Exists(rel="Person.pets"), ANIMAL, POSTGRES, "Person")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind in (?, ?))"
    )
    assert compiled.statement.binds == ("cat", "dog")


def test_tph_relationship_narrow_to_one_concrete_lowers_to_eq() -> None:
    op = oa.Exists(rel="Person.pets", op=oa.Narrow(entity="Pet", to=("Cat",), operand=oa.All()))
    compiled = compile_read(op, ANIMAL, POSTGRES, "Person")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind = ?)"
    )
    assert compiled.statement.binds == ("cat",)


def test_tph_relationship_narrow_to_abstract_subtype_matches_the_broad_relationship() -> None:
    op = oa.Exists(
        rel="Person.animals", op=oa.Narrow(entity="Animal", to=("Pet",), operand=oa.All())
    )
    compiled = compile_read(op, ANIMAL, POSTGRES, "Person")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind in (?, ?))"
    )
    assert compiled.statement.binds == ("cat", "dog")


def test_tpcs_abstract_root_relationship_target_groups_every_branch_alphabetically() -> None:
    compiled = compile_read(oa.Exists(rel="Folder.documents"), DOCUMENT, POSTGRES, "Folder")
    assert compiled.statement.sql.endswith(
        "where (exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from memo t2 where t2.folder_id = t0.id) "
        "or exists (select 1 from receipt t3 where t3.folder_id = t0.id))"
    )


def test_tpcs_relationship_narrow_drops_the_excluded_branch_but_keeps_its_alias_slot_free() -> None:
    op = oa.Exists(
        rel="Folder.documents",
        op=oa.Narrow(entity="Document", to=("FinancialDocument",), operand=oa.All()),
    )
    compiled = compile_read(op, DOCUMENT, POSTGRES, "Folder")
    assert compiled.statement.sql.endswith(
        "where (exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from receipt t2 where t2.folder_id = t0.id))"
    )


def test_tpcs_relationship_narrow_to_a_single_concrete_is_one_exists_no_grouping() -> None:
    # m-sql "a single concrete is one EXISTS (no grouping)" — the TPCS analogue of
    # the TPH narrow-to-one-concrete case above.
    op = oa.Exists(
        rel="Folder.documents", op=oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All())
    )
    compiled = compile_read(op, DOCUMENT, POSTGRES, "Folder")
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from invoice t1 where t1.folder_id = t0.id)"
    )
