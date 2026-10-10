"""Navigation lowering (m-sql "Joins by navigation" / "Polymorphic navigation").

These feed already-canonicalized queries directly (the per-hop as-of rewrite
is `parallax.core.navigate`'s job, tested in `test_navigate.py`) — this module
only lowers whatever Predicate tree it receives.

Beyond the correlated `EXISTS` and scalar-subquery shapes themselves, this suite pins the ALIAS
sequence: one statement allocates one depth-first, source-ordered sequence
shared across every nested and sibling subquery, which is the state invariant
the private-module split must preserve.
"""

from __future__ import annotations

import pytest

from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.object_query import AsOf
from parallax.core.predicate import ModelRejectedError
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import formed, model, target

ORDERS = model("orders")
ANIMAL = model("animal")
DOCUMENT = model("document")
PERSON = model("person")


def test_an_unknown_relationship_is_rejected() -> None:
    with pytest.raises(ModelRejectedError) as caught:
        compile_read(
            oa.Quantifier("any", "Order.missing"), ORDERS, POSTGRES, target(ORDERS, "Order")
        )
    assert caught.value.rule == "path-unknown-member"


def test_a_to_many_any_lowers_to_a_correlated_exists() -> None:
    op = oa.Quantifier(
        "any", "Order.items", oa.Comparison(op="eq", subject=oa.FieldSubject("sku"), value="A-100")
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and t1.sku = ?)"
    )
    assert compiled.statement.binds == ("A-100",)


def test_a_bare_any_is_a_pure_correlation_check() -> None:
    compiled = compile_read(
        oa.Quantifier("any", "Order.items"), ORDERS, POSTGRES, target(ORDERS, "Order")
    )
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id)"
    )
    assert compiled.statement.binds == ()


def test_none_negates_the_correlated_exists() -> None:
    compiled = compile_read(
        oa.Quantifier("none", "Order.items"), ORDERS, POSTGRES, target(ORDERS, "Order")
    )
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id)"
    )


def test_all_lowers_to_the_absence_of_a_counterexample() -> None:
    # Every element must make the predicate TRUE, so an element where it is false
    # or unknown is a counterexample.
    op = oa.Quantifier(
        "all", "Order.items", oa.Comparison(op="eq", subject=oa.FieldSubject("sku"), value="A-100")
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id "
        "and not (t1.sku = ?) is true)"
    )


def test_a_quantifier_composes_inside_the_boolean_algebra() -> None:
    op = oa.And(
        operands=(
            oa.Quantifier("none", "Order.items"),
            oa.Comparison(op="eq", subject=oa.FieldSubject("Order.active"), value=True),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id) and t0.active = ?"
    )
    assert compiled.statement.binds == (True,)


def test_a_field_past_a_reverse_to_one_hop_reads_a_correlated_scalar() -> None:
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("OrderItem.order.name"), value="Ada")
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql.endswith(
        "where (select t1.name from orders t1 where t1.id = t0.order_id) = ?"
    )
    assert compiled.statement.binds == ("Ada",)


def test_a_field_past_a_one_to_one_hop_reads_like_any_to_one_hop() -> None:
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Person.passport.number"), value="P-AAA")
    compiled = compile_read(op, PERSON, POSTGRES, target(PERSON, "Person"))
    assert compiled.statement.sql.endswith(
        "where (select t1.number from passport t1 where t1.person_id = t0.id) = ?"
    )


def test_a_field_two_hops_away_nests_the_scalars_in_source_alias_order() -> None:
    # The inner hop's subquery precedes the outer one's FROM in the statement
    # text, so it takes the lower alias (m-sql source-order allocation).
    op = oa.Comparison(
        op="eq", subject=oa.FieldSubject("OrderStatus.orderItem.order.name"), value="Ada"
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.statement.sql.endswith(
        "where (select (select t1.name from orders t1 where t1.id = t2.order_id) "
        "from order_item t2 where t2.id = t0.order_item_id) = ?"
    )


def test_presence_of_a_nullable_many_to_one_correlates_on_the_owned_fk() -> None:
    compiled = compile_read(
        oa.Presence("exists", "OrderStatus.orderItem"),
        ORDERS,
        POSTGRES,
        target(ORDERS, "OrderStatus"),
    )
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.id = t0.order_item_id)"
    )


def test_a_nested_quantifier_continues_the_single_alias_sequence() -> None:
    op = oa.Quantifier(
        "any",
        "Order.items",
        oa.Quantifier(
            "any",
            "statuses",
            oa.Comparison(op="eq", subject=oa.FieldSubject("code"), value="PACKED"),
        ),
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id and t2.code = ?))"
    )
    assert compiled.statement.binds == ("PACKED",)


def test_none_over_a_nested_quantifier_negates_only_the_outer_hop() -> None:
    op = oa.Quantifier("none", "Order.items", oa.Quantifier("any", "statuses"))
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id))"
    )


def test_sibling_hops_continue_one_alias_sequence() -> None:
    # Depth-first, SOURCE-ORDER allocation across nested AND sibling subqueries
    # (m-sql): `items` opens t1 and its interior `statuses` opens t2; the sibling
    # `tags` then takes t3, not t2.
    op = oa.And(
        operands=(
            oa.Quantifier("any", "Order.items", oa.Quantifier("any", "statuses")),
            oa.Quantifier("any", "Order.tags"),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id)) and "
        "exists (select 1 from order_tag t3 where t3.order_id = t0.id)"
    )


# --------------------------------------------------------------------------- #
# Polymorphic navigation lowering (m-sql "Polymorphic navigation lowering").   #
# --------------------------------------------------------------------------- #
def test_tph_abstract_root_relationship_target_injects_no_tag() -> None:
    compiled = compile_read(
        oa.Quantifier("any", "Person.animals"), ANIMAL, POSTGRES, target(ANIMAL, "Person")
    )
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id)"
    )


def test_tph_abstract_subtype_relationship_target_injects_the_in_list() -> None:
    compiled = compile_read(
        oa.Quantifier("any", "Person.pets"), ANIMAL, POSTGRES, target(ANIMAL, "Person")
    )
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind in (?, ?))"
    )
    assert compiled.statement.binds == ("cat", "dog")


def test_tph_relationship_narrow_to_one_concrete_lowers_to_eq() -> None:
    op = oa.Quantifier("any", "Person.pets", oa.Narrow(to=("Cat",), operand=oa.TrueNode()))
    compiled = compile_read(op, ANIMAL, POSTGRES, target(ANIMAL, "Person"))
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind = ?)"
    )
    assert compiled.statement.binds == ("cat",)


def test_tph_relationship_narrow_to_abstract_subtype_matches_the_broad_relationship() -> None:
    op = oa.Quantifier("any", "Person.animals", oa.Narrow(to=("Pet",), operand=oa.TrueNode()))
    compiled = compile_read(op, ANIMAL, POSTGRES, target(ANIMAL, "Person"))
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind in (?, ?))"
    )
    assert compiled.statement.binds == ("cat", "dog")


def test_tpcs_abstract_root_relationship_target_groups_every_branch_alphabetically() -> None:
    compiled = compile_read(
        oa.Quantifier("any", "Folder.documents"), DOCUMENT, POSTGRES, target(DOCUMENT, "Folder")
    )
    assert compiled.statement.sql.endswith(
        "where (exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from memo t2 where t2.folder_id = t0.id) "
        "or exists (select 1 from receipt t3 where t3.folder_id = t0.id))"
    )


def test_tpcs_relationship_narrow_drops_the_excluded_branch_but_keeps_its_alias_slot_free() -> None:
    op = oa.Quantifier(
        "any", "Folder.documents", oa.Narrow(to=("FinancialDocument",), operand=oa.TrueNode())
    )
    compiled = compile_read(op, DOCUMENT, POSTGRES, target(DOCUMENT, "Folder"))
    assert compiled.statement.sql.endswith(
        "where (exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from receipt t2 where t2.folder_id = t0.id))"
    )


def test_tpcs_relationship_narrow_to_a_single_concrete_is_one_exists_no_grouping() -> None:
    op = oa.Quantifier("any", "Folder.documents", oa.Narrow(to=("Invoice",), operand=oa.TrueNode()))
    compiled = compile_read(op, DOCUMENT, POSTGRES, target(DOCUMENT, "Folder"))
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from invoice t1 where t1.folder_id = t0.id)"
    )


def test_a_universal_over_tpcs_keeps_every_branch_as_a_counterexample_source() -> None:
    # Branch selection by the interior narrow would drop the branches holding the
    # counterexamples, so `all` searches every declared branch and lets the
    # narrow decide each branch's verdict.
    op = oa.Quantifier("all", "Folder.documents", oa.Narrow(to=("Invoice",), operand=oa.TrueNode()))
    compiled = compile_read(op, DOCUMENT, POSTGRES, target(DOCUMENT, "Folder"))
    assert compiled.statement.sql.endswith(
        "where not (exists (select 1 from invoice t1 where t1.folder_id = t0.id "
        "and not (1 = 1) is true) "
        "or exists (select 1 from memo t2 where t2.folder_id = t0.id and not (1 = 0) is true) "
        "or exists (select 1 from receipt t3 where t3.folder_id = t0.id "
        "and not (1 = 0) is true))"
    )


def test_tpcs_branches_take_their_aliases_as_each_branch_opens() -> None:
    # A grouped TPCS hop allocates each branch's alias AT THE POINT THAT BRANCH
    # OPENS, not all branches up front: branch 2's number follows everything
    # branch 1's own interior allocated.
    #
    # Every other TPCS branch pin above has a NON-NAVIGATING interior, so its
    # branches allocate nothing between them and `t1, t2, t3` reads the same under
    # either strategy. Only a branch whose interior
    # itself opens a subquery can tell them apart: per-branch gives
    # `inv t1 -> owner t2` then `rec t3 -> owner t4`, while up-front allocation
    # would give `inv t1 / rec t2` and interiors `t3 / t4`.
    #
    # No corpus model reaches this shape — it needs a TPCS-target relationship
    # whose concretes are themselves navigable, and `document`'s are not — so this
    # synthetic family is the witness, in the idiom of the TPCS branch-context pin
    # in `test_sql_gen_inheritance.py`.
    from parallax.descriptor._records import (
        Attribute,
        DefiningRelationship,
        Entity,
        Inheritance,
        Metamodel,
        RelationshipJoin,
        RelationshipTarget,
    )

    doc = Entity(
        name="Doc",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="ownerId", type="int64", column="owner_id", nullable=True),
            Attribute(name="folderId", type="int64", column="folder_id", nullable=True),
        ),
        relationships=(
            DefiningRelationship(
                name="owner",
                cardinality="many-to-one",
                join=RelationshipJoin(
                    source="ownerId", target=RelationshipTarget(entity="Owner", attribute="id")
                ),
            ),
        ),
    )
    inv = Entity(
        name="Inv",
        table="inv",
        inheritance=Inheritance(role="concrete-subtype", parent="Doc"),
        attributes=(Attribute(name="due", type="int32", column="due"),),
    )
    rec = Entity(
        name="Rec",
        table="rec",
        inheritance=Inheritance(role="concrete-subtype", parent="Doc"),
        attributes=(Attribute(name="paid", type="int32", column="paid"),),
    )
    owner = Entity(
        name="Owner",
        table="owner",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="name", type="string", column="name", max_length=32),
        ),
    )
    folder = Entity(
        name="Folder",
        table="folder",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        relationships=(
            DefiningRelationship(
                name="docs",
                cardinality="one-to-many",
                join=RelationshipJoin(
                    source="id", target=RelationshipTarget(entity="Doc", attribute="folderId")
                ),
            ),
        ),
    )
    meta = formed(Metamodel(entities=(doc, inv, rec, owner, folder)))

    op = oa.Quantifier(
        "any",
        "Folder.docs",
        oa.Comparison(op="eq", subject=oa.FieldSubject("owner.name"), value="N"),
    )
    compiled = compile_read(op, meta, POSTGRES, target(meta, "Folder"))
    assert compiled.statement.sql.endswith(
        "where (exists (select 1 from inv t1 where t1.folder_id = t0.id and "
        "(select t2.name from owner t2 where t2.id = t1.owner_id) = ?) "
        "or exists (select 1 from rec t3 where t3.folder_id = t0.id and "
        "(select t4.name from owner t4 where t4.id = t3.owner_id) = ?))"
    )


TRAVERSAL = model("predicate-traversal")
POLICY = model("policy")
TWIN = model("scalar-collection-layout-twin-columns")


def test_presence_two_hops_away_nests_inside_the_first_hop() -> None:
    compiled = compile_read(
        oa.Presence("exists", "Leash.collar.pet"), TRAVERSAL, POSTGRES, target(TRAVERSAL, "Leash")
    )
    assert compiled.statement.sql.endswith(
        "where coalesce((select exists (select 1 from traversal_pet t1 where t1.id = t2.pet_id) "
        "from traversal_collar t2 where t2.id = t0.collar_id), false)"
    )


def test_a_narrow_over_a_monomorphic_target_tests_presence_and_its_operand() -> None:
    bare = compile_read(
        oa.Narrow(path="Claim.coverage", to=("Coverage",), operand=oa.TrueNode()),
        POLICY,
        POSTGRES,
        target(POLICY, "Claim"),
        temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
    )
    assert "coalesce((select true from coverage t1 where t1.id = t0.coverage_id" in (
        bare.statement.sql
    )
    operand = compile_read(
        oa.Narrow(
            path="Claim.coverage",
            to=("Coverage",),
            operand=oa.Comparison(
                op="greaterThan", subject=oa.FieldSubject("amount"), value="1.00"
            ),
        ),
        POLICY,
        POSTGRES,
        target(POLICY, "Claim"),
        temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
    )
    assert "(coalesce((select array [ t1.amount > ? ] from coverage t1" in operand.statement.sql


def test_presence_of_a_single_value_object_inside_an_element_reads_the_element() -> None:
    compiled = compile_read(
        oa.Quantifier("any", "CollectionTwinItem.parts", oa.Presence("exists", "note")),
        TWIN,
        POSTGRES,
        target(TWIN, "CollectionTwinItem"),
    )
    assert compiled.statement.sql.endswith(
        "t1 where coalesce(jsonb_typeof(jsonb_extract_path(t1.value, ?)) = ?, false))"
    )
