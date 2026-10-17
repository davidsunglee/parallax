"""Navigation lowering (m-sql "Joins by navigation" / "Polymorphic navigation").

These lower temporally resolved queries (resolving each hop's visibility is
`parallax.core.navigate`'s job, tested in `test_navigate.py`) — this module
only lowers whatever Predicate tree it receives, and decides join sharing from
the perspective each hop carries.

Beyond the correlated `EXISTS` and scalar-subquery shapes themselves, this suite pins the ALIAS
sequence: one statement allocates one depth-first, source-ordered sequence
shared across every nested and sibling subquery, which is the state invariant
the private-module split must preserve.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Literal

import pytest

from parallax.conformance.models import accepted_model
from parallax.core import inheritance, storage_layout
from parallax.core import predicate as oa
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import AsOf
from parallax.core.predicate import ModelRejectedError
from parallax.core.predicate._perspective import (
    AtPerspective,
    LatestPerspective,
    TemporalPerspective,
)
from parallax.core.predicate._resolved import (
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRelationship,
)
from parallax.core.sql_gen._context import StatementBuilder, table_layout
from parallax.core.sql_gen._navigation import (
    plan_relationship_candidates,
    shared_relationship_is_eligible,
)
from parallax.core.sql_gen._predicate import EntityScope
from parallax.core.temporal_read import Bitemporal
from parallax.core.temporal_read import view as temporal_view
from tests._support.sql import compile_read, compile_write_predicate
from tests.unit._corpus_model_support import formed, model, target

ORDERS = model("orders")
ANIMAL = model("animal")
DOCUMENT = model("document")
PERSON = model("person")
TRAVERSAL = model("predicate-traversal")
POLICY = model("policy")
TWIN = model("scalar-collection-layout-twin-columns")
BEAST = model("composed-beast-reader")


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


@pytest.mark.parametrize("kind", ["any", "none"])
def test_a_disjunctive_where_stays_whole_beside_the_correlation(
    kind: Literal["any", "none"],
) -> None:
    either = oa.Or(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("sku"), value="A-100"),
            oa.Comparison(op="eq", subject=oa.FieldSubject("sku"), value="B-200"),
        )
    )
    compiled = compile_read(
        oa.Quantifier(kind, "Order.items", either), ORDERS, POSTGRES, target(ORDERS, "Order")
    )
    assert compiled.statement.sql.endswith(
        "exists (select 1 from order_item t1 where t1.order_id = t0.id "
        "and (t1.sku = ? or t1.sku = ?))"
    )


def test_a_negated_conjunction_is_negated_whole() -> None:
    op = oa.Not(
        oa.And(
            operands=(
                oa.Quantifier("none", "Order.items"),
                oa.Comparison(op="eq", subject=oa.FieldSubject("Order.active"), value=True),
            )
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where not (not exists (select 1 from order_item t1 where t1.order_id = t0.id) "
        "and t0.active = ?)"
    )


def test_a_field_past_a_primary_key_hop_reads_a_shared_join() -> None:
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("OrderItem.order.name"), value="Ada")
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql.endswith(
        "from order_item t0 left join orders t1 on t1.id = t0.order_id where t1.name = ?"
    )
    assert compiled.statement.binds == ("Ada",)


def test_a_field_past_a_unique_foreign_key_hop_reads_a_shared_join() -> None:
    # The passport's unique `person_id` index is the key the correlation fixes.
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Person.passport.number"), value="P-AAA")
    compiled = compile_read(op, PERSON, POSTGRES, target(PERSON, "Person"))
    assert compiled.statement.sql.endswith(
        "from person t0 left join passport t1 on t1.person_id = t0.id where t1.number = ?"
    )


def test_a_field_two_hops_away_joins_each_hop_in_source_alias_order() -> None:
    op = oa.Comparison(
        op="eq", subject=oa.FieldSubject("OrderStatus.orderItem.order.name"), value="Ada"
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.statement.sql.endswith(
        "from order_status t0 left join order_item t1 on t1.id = t0.order_item_id "
        "left join orders t2 on t2.id = t1.order_id where t2.name = ?"
    )


def test_readless_predicate_dml_nests_the_scalars_in_source_alias_order() -> None:
    # The inner hop's subquery precedes the outer one's FROM in the statement
    # text, so it takes the lower alias (m-sql source-order allocation).
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Parking.vehicle.dealer.name"), value="N")
    compiled = compile_write_predicate(op, TRAVERSAL, POSTGRES, target(TRAVERSAL, "Parking"))
    assert not compiled.selection
    assert compiled.sql == (
        "(select (select t1.name from traversal_dealer t1 where t1.id = t2.dealer_id) "
        "from traversal_bike t2 where t2.id = vehicle_id union all "
        "select (select t3.name from traversal_dealer t3 where t3.id = t4.dealer_id) "
        "from traversal_car t4 where t4.id = vehicle_id) = ?"
    )


def test_readless_predicate_dml_selects_its_keys_through_a_shared_prefix() -> None:
    op = oa.Comparison(
        op="eq", subject=oa.FieldSubject("OrderStatus.orderItem.order.name"), value="Ada"
    )
    compiled = compile_write_predicate(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.selection
    assert compiled.sql == (
        "select t0.id from order_status t0 left join order_item t1 on t1.id = t0.order_item_id "
        "left join orders t2 on t2.id = t1.order_id where t2.name = ?"
    )
    assert compiled.binds == ("Ada",)


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
        "where (exists (select 1 from inv t1 left join owner t2 on t2.id = t1.owner_id "
        "where t1.folder_id = t0.id and t2.name = ?) "
        "or exists (select 1 from rec t3 left join owner t4 on t4.id = t3.owner_id "
        "where t3.folder_id = t0.id and t4.name = ?))"
    )


def test_presence_two_hops_away_tests_its_target_at_the_joined_prefix() -> None:
    # Presence alone opens no join for its own target: only the dotted prefix joins.
    compiled = compile_read(
        oa.Presence("exists", "Leash.collar.pet"), TRAVERSAL, POSTGRES, target(TRAVERSAL, "Leash")
    )
    assert compiled.statement.sql.endswith(
        "left join traversal_collar t1 on t1.id = t0.collar_id "
        "where exists (select 1 from traversal_pet t2 where t2.id = t1.pet_id)"
    )


_SEATS = oa.Comparison(op="greaterThan", subject=oa.FieldSubject("seats"), value=2)


def test_a_match_tests_its_whole_operand_in_every_candidate_branch() -> None:
    narrowed = oa.Narrow(to=("Car",), operand=oa.Or(operands=(_SEATS, _title("maker", "Saab"))))
    parking = target(TRAVERSAL, "Parking")
    positive = compile_read(
        oa.Presence("exists", "Parking.vehicle", narrowed), TRAVERSAL, POSTGRES, parking
    )
    negative = compile_read(
        oa.Presence("notExists", "Parking.vehicle", narrowed), TRAVERSAL, POSTGRES, parking
    )
    branches = (
        "exists (select 1 from traversal_bike t1 where t1.id = t0.vehicle_id and 1 = 0) "
        "or exists (select 1 from traversal_car t2 where t2.id = t0.vehicle_id "
        "and (t2.seats > ? or t2.maker = ?))"
    )
    assert positive.statement.sql.endswith(f"where ({branches})")
    assert negative.statement.sql.endswith(f"where not ({branches})")
    assert positive.statement.binds == negative.statement.binds == (2, "Saab")


def test_a_match_past_a_dotted_prefix_is_false_where_the_prefix_reaches_nothing() -> None:
    compiled = compile_read(
        oa.Presence("notExists", "Leash.collar.pet", _title("name", "Rex")),
        TRAVERSAL,
        POSTGRES,
        target(TRAVERSAL, "Leash"),
    )
    assert compiled.statement.sql.endswith(
        "left join traversal_collar t1 on t1.id = t0.collar_id where not exists "
        "(select 1 from traversal_pet t2 where t2.id = t1.pet_id and t2.name = ?)"
    )


def test_a_narrow_of_a_joined_target_tests_its_presence_and_keeps_its_operand() -> None:
    claim = target(POLICY, "Claim")
    coverage = "left join coverage t1 on t1.id = t0.coverage_id and t1.thru_z = ? and t1.out_z = ?"
    bare = compile_read(
        oa.Narrow(path="Claim.coverage", to=("Coverage",), operand=oa.TrueNode()),
        POLICY,
        POSTGRES,
        claim,
        temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
    )
    assert f"{coverage} where (not t1.id is null) and t0.thru_z = ?" in bare.statement.sql
    amount = oa.Comparison(op="greaterThan", subject=oa.FieldSubject("amount"), value="1.00")
    operand = compile_read(
        oa.Narrow(path="Claim.coverage", to=("Coverage",), operand=amount),
        POLICY,
        POSTGRES,
        claim,
        temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
    )
    assert (
        f"{coverage} where case when not t1.id is null then t1.amount > ? else false end "
        "and t0.thru_z = ?"
    ) in operand.statement.sql


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


def _dormant_target_model(strategy: Literal["tph", "tpcs"]) -> Metamodel:
    """``Holder`` relates to ``Empty``, an abstract subtype with no concrete
    descendant beside the concrete sibling ``Leaf``."""
    shared = strategy == "tph"
    root: dict[str, object] = {
        "name": "Thing",
        "namespace": "probe",
        "inheritance": {
            "role": "root",
            "strategy": "table-per-hierarchy" if shared else "table-per-concrete-subtype",
            **({"tag": {"column": "kind"}} if shared else {}),
        },
        "attributes": [
            {"name": "id", "type": "int64", "primaryKey": True},
            {"name": "title", "type": "string", "maxLength": 16},
            {"name": "holderId", "type": "int64", "nullable": True},
        ],
        "relationships": [
            {
                "name": "holder",
                "cardinality": "many-to-one",
                "join": {
                    "source": "holderId",
                    "target": {"entity": "probe.Holder", "attribute": "id"},
                },
            }
        ],
        **({"table": "thing"} if shared else {}),
    }
    leaf: dict[str, object] = {
        "name": "Leaf",
        "namespace": "probe",
        "inheritance": {
            "role": "concrete-subtype",
            "parent": "probe.Thing",
            **({"tagValue": "leaf"} if shared else {}),
        },
        **({} if shared else {"table": "leaf"}),
    }
    return accepted_model(
        {
            "entities": [
                root,
                leaf,
                {
                    "name": "Empty",
                    "namespace": "probe",
                    "inheritance": {"role": "abstract-subtype", "parent": "probe.Thing"},
                },
                {
                    "name": "Holder",
                    "namespace": "probe",
                    "table": "holder",
                    "attributes": [
                        {"name": "id", "type": "int64", "primaryKey": True},
                        {"name": "emptyId", "type": "int64", "nullable": True},
                        {"name": "nextId", "type": "int64", "nullable": True},
                    ],
                    "relationships": [
                        {
                            "name": "empties",
                            "cardinality": "one-to-many",
                            "join": {
                                "source": "id",
                                "target": {"entity": "probe.Empty", "attribute": "holderId"},
                            },
                        },
                        {
                            "name": "empty",
                            "cardinality": "many-to-one",
                            "join": {
                                "source": "emptyId",
                                "target": {"entity": "probe.Empty", "attribute": "id"},
                            },
                        },
                        {
                            "name": "next",
                            "cardinality": "many-to-one",
                            "join": {
                                "source": "nextId",
                                "target": {"entity": "probe.Holder", "attribute": "id"},
                            },
                        },
                    ],
                },
            ]
        }
    )


def _title(path: str, value: str = "x") -> oa.Comparison:
    return oa.Comparison(op="eq", subject=oa.FieldSubject(path), value=value)


@pytest.mark.parametrize("strategy", ["tph", "tpcs"])
@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (oa.Quantifier("any", "Holder.empties"), "1 = 0"),
        (oa.Quantifier("any", "Holder.empties", _title("title")), "1 = 0"),
        (oa.Quantifier("none", "Holder.empties"), "1 = 1"),
        (oa.Quantifier("all", "Holder.empties", _title("title")), "1 = 1"),
        (oa.Presence("exists", "Holder.empty"), "1 = 0"),
        (oa.Presence("notExists", "Holder.empty"), "1 = 1"),
        (oa.Presence("exists", "Holder.empty", _title("title")), "1 = 0"),
        (oa.Presence("notExists", "Holder.empty", _title("title")), "1 = 1"),
        (_title("Holder.empty.title"), "cast(null as boolean)"),
        (oa.NullCheck(op="isNull", subject=oa.FieldSubject("Holder.empty.holderId")), "1 = 1"),
        (oa.NullCheck(op="isNotNull", subject=oa.FieldSubject("Holder.empty.holderId")), "1 = 0"),
    ],
)
def test_a_relationship_to_a_target_without_concrete_subtypes_reaches_no_candidate(
    strategy: Literal["tph", "tpcs"], predicate: oa.PredicateNode, expected: str
) -> None:
    model = _dormant_target_model(strategy)
    compiled = compile_read(predicate, model, POSTGRES, target(model, "Holder"))
    assert compiled.statement.sql.endswith(f"from holder t0 where {expected}")
    assert compiled.statement.binds == ()


@pytest.mark.parametrize("strategy", ["tph", "tpcs"])
@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (oa.Quantifier("any", "Holder.empty.holder.empties"), "false"),
        (oa.Quantifier("none", "Holder.empty.holder.empties"), "true"),
        (oa.Presence("exists", "Holder.empty.holder"), "false"),
        (_title("Holder.empty.holder.empty.title"), "cast(null as boolean)"),
    ],
)
def test_a_position_past_a_target_without_candidates_answers_its_absence(
    strategy: Literal["tph", "tpcs"], predicate: oa.PredicateNode, expected: str
) -> None:
    model = _dormant_target_model(strategy)
    compiled = compile_read(predicate, model, POSTGRES, target(model, "Holder"))
    assert compiled.statement.sql.endswith(f"from holder t0 where {expected}")
    assert compiled.statement.binds == ()


def test_a_relationship_to_a_target_without_candidates_answers_inside_a_hop() -> None:
    model = _dormant_target_model("tpcs")
    compiled = compile_read(
        oa.Quantifier("none", "Holder.next.empties"), model, POSTGRES, target(model, "Holder")
    )
    assert compiled.statement.sql.endswith(
        "where coalesce((select 1 = 1 from holder t1 where t1.id = t0.next_id), true)"
    )


_NEXT = "from holder t1 where t1.id = t0.next_id)"


@pytest.mark.parametrize("strategy", ["tph", "tpcs"])
@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (
            oa.Quantifier("any", "Holder.next.empty.holder.empties"),
            f"coalesce((select false {_NEXT}, false)",
        ),
        (
            oa.Presence("exists", "Holder.next.empty.holder"),
            f"coalesce((select false {_NEXT}, false)",
        ),
        (_title("Holder.next.empty.title"), f"(select cast(null as boolean) {_NEXT}"),
        (
            oa.NullCheck(op="isNull", subject=oa.FieldSubject("Holder.next.empty.holderId")),
            f"coalesce((select 1 = 1 {_NEXT}, 1 = 1)",
        ),
    ],
)
def test_a_target_without_candidates_answers_inside_every_preceding_hop(
    strategy: Literal["tph", "tpcs"], predicate: oa.PredicateNode, expected: str
) -> None:
    model = _dormant_target_model(strategy)
    compiled = compile_read(predicate, model, POSTGRES, target(model, "Holder"))
    assert compiled.statement.sql.endswith(f"from holder t0 where {expected}")
    assert compiled.statement.binds == ()


# --------------------------------------------------------------------------- #
# Shared to-one joins (m-sql "Shared to-one joins").                           #
# --------------------------------------------------------------------------- #
CUSTOMER = model("customer")
_ORDER_ITEM_ROW = "select t0.id, t0.order_id, t0.sku, t0.quantity, t0.shipped_on from order_item t0"
_ADA = oa.Comparison(op="eq", subject=oa.FieldSubject("OrderItem.order.name"), value="Ada")
_ACTIVE = oa.Comparison(op="eq", subject=oa.FieldSubject("OrderItem.order.active"), value=True)


def test_fields_and_presence_of_one_target_share_its_join_under_negation() -> None:
    op = oa.Not(oa.And(operands=(oa.Presence("exists", "OrderItem.order"), _ADA, _ACTIVE)))
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql == (
        f"{_ORDER_ITEM_ROW} left join orders t1 on t1.id = t0.order_id "
        "where not (not t1.id is null and t1.name = ? and t1.active = ?)"
    )
    assert compiled.statement.binds == ("Ada", True)


def test_absence_of_a_shared_target_reads_its_primary_key() -> None:
    op = oa.Or(operands=(oa.Presence("notExists", "OrderItem.order"), _ADA))
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql.endswith(
        "left join orders t1 on t1.id = t0.order_id where t1.id is null or t1.name = ?"
    )


def test_a_common_prefix_is_joined_once_beneath_every_suffix() -> None:
    op = oa.Or(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("OrderStatus.orderItem.sku"), value="S"),
            oa.Group(
                oa.And(
                    operands=(
                        oa.Comparison(
                            op="eq",
                            subject=oa.FieldSubject("OrderStatus.orderItem.order.name"),
                            value="Ada",
                        ),
                        oa.NullCheck(
                            op="isNull", subject=oa.FieldSubject("OrderStatus.orderItem.shippedOn")
                        ),
                    )
                )
            ),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.statement.sql.endswith(
        "from order_status t0 left join order_item t1 on t1.id = t0.order_item_id "
        "left join orders t2 on t2.id = t1.order_id "
        "where t1.sku = ? or (t2.name = ? and t1.shipped_on is null)"
    )
    assert compiled.statement.binds == ("S", "Ada")


def test_every_scalar_operation_reads_a_shared_join() -> None:
    def item(member: str) -> oa.FieldSubject:
        return oa.FieldSubject(f"OrderStatus.orderItem.{member}")

    op = oa.And(
        operands=(
            oa.Membership(op="in", subject=item("sku"), values=("A",)),
            oa.Range(subject=item("quantity"), lower=1, upper=9),
            oa.StringMatch(op="startsWith", subject=item("sku"), value="S"),
            oa.NullCheck(op="isNotNull", subject=item("shippedOn")),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.statement.sql.endswith(
        "left join order_item t1 on t1.id = t0.order_item_id where t1.sku in (?) and "
        "t1.quantity between ? and ? and t1.sku like ? and not t1.shipped_on is null"
    )
    assert compiled.statement.binds == ("A", 1, 9, "S%")


def test_distinct_relationships_to_one_entity_open_their_own_joins() -> None:
    op = oa.And(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("OrderStatus.order.name"), value="A"),
            oa.Comparison(
                op="eq", subject=oa.FieldSubject("OrderStatus.orderItem.order.name"), value="B"
            ),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.statement.sql.endswith(
        "from order_status t0 left join orders t1 on t1.id = t0.order_id "
        "left join order_item t2 on t2.id = t0.order_item_id "
        "left join orders t3 on t3.id = t2.order_id where t1.name = ? and t3.name = ?"
    )


def test_joins_take_their_aliases_and_binds_before_the_predicate() -> None:
    # The quantifier's subquery is earlier in the predicate than the dotted field,
    # but the field's join precedes the whole `where`.
    op = oa.And(
        operands=(
            oa.Quantifier(
                "any",
                "OrderItem.statuses",
                oa.Comparison(op="eq", subject=oa.FieldSubject("code"), value="PACKED"),
            ),
            _ADA,
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql.endswith(
        "left join orders t1 on t1.id = t0.order_id where exists (select 1 from order_status t2 "
        "where t2.order_item_id = t0.id and t2.code = ?) and t1.name = ?"
    )
    assert compiled.statement.binds == ("PACKED", "Ada")


def test_a_tag_guard_binds_in_its_join_ahead_of_the_predicate() -> None:
    family = _tph_owner_model()
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Leash.dog.name"), value="Rex")
    compiled = compile_read(op, family, POSTGRES, target(family, "Leash"))
    assert compiled.statement.sql.endswith(
        "from leash t0 left join pet t1 on t1.id = t0.dog_id and t1.kind = ? where t1.name = ?"
    )
    assert compiled.statement.binds == ("dog", "Rex")


def test_a_match_reuses_a_shared_target_beneath_its_presence() -> None:
    op = oa.And(
        operands=(
            oa.Comparison(op="notEq", subject=oa.FieldSubject("OrderItem.order.name"), value="X"),
            oa.Presence(
                "notExists",
                "OrderItem.order",
                oa.Comparison(op="eq", subject=oa.FieldSubject("active"), value=True),
            ),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql.endswith(
        "left join orders t1 on t1.id = t0.order_id where t1.name <> ? "
        "and not case when t1.id is null then false else (t1.active = ?) is true end"
    )
    assert compiled.statement.binds == ("X", True)


def test_a_compound_match_reading_its_target_row_reuses_the_shared_target() -> None:
    operand = oa.Or(
        operands=(
            oa.Not(oa.NullCheck(op="isNull", subject=oa.FieldSubject("sku"))),
            oa.StringMatch(op="startsWith", subject=oa.FieldSubject("name"), value="A"),
        )
    )
    op = oa.And(operands=(_ADA, oa.Presence("exists", "OrderItem.order", operand)))
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql.endswith(
        "left join orders t1 on t1.id = t0.order_id where t1.name = ? and case when t1.id "
        "is null then false else (not t1.sku is null or t1.name like ?) is true end"
    )


def test_a_match_alone_opens_no_join() -> None:
    op = oa.Presence(
        "exists",
        "OrderItem.order",
        oa.Comparison(op="eq", subject=oa.FieldSubject("name"), value="Ada"),
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.statement.sql == (
        f"{_ORDER_ITEM_ROW} where exists "
        "(select 1 from orders t1 where t1.id = t0.order_id and t1.name = ?)"
    )


def _location_where(*operands: oa.PredicateNode) -> str:
    compiled = compile_read(
        oa.And(operands=operands), CUSTOMER, POSTGRES, target(CUSTOMER, "Location")
    )
    return compiled.statement.sql.partition(" from location t0 ")[2]


_CUSTOMER_NAMED = oa.Comparison(
    op="eq", subject=oa.FieldSubject("Location.customer.name"), value="Ada"
)


def test_a_converted_document_member_keeps_its_scalar_form_beside_a_shared_join() -> None:
    # Uniqueness is not evaluation safety: the elevation's cast stays inside the
    # candidate subquery while the name, on the same eligible target, joins.
    assert _location_where(
        _CUSTOMER_NAMED,
        oa.Comparison(
            op="greaterThan",
            subject=oa.FieldSubject("Location.customer.address.geo.elevation"),
            value=5.0,
        ),
    ) == (
        "left join customer t1 on t1.id = t0.customer_id where t1.name = ? and "
        "(select cast(jsonb_extract_path_text(t2.address, ?, ?) as double precision) "
        "from customer t2 where t2.id = t0.customer_id) > ?"
    )


def test_a_text_compared_document_member_reads_the_shared_join() -> None:
    assert _location_where(
        _CUSTOMER_NAMED,
        oa.Comparison(
            op="eq", subject=oa.FieldSubject("Location.customer.address.city"), value="Oslo"
        ),
    ) == (
        "left join customer t1 on t1.id = t0.customer_id "
        "where t1.name = ? and jsonb_extract_path_text(t1.address, ?) = ?"
    )


def test_the_same_conversion_inside_a_match_keeps_its_correlated_exists() -> None:
    # The presence guard excludes only a missing customer, not customers no
    # location reaches, which a joined-row filter may also be tested against.
    assert _location_where(
        _CUSTOMER_NAMED,
        oa.Presence(
            "exists",
            "Location.customer",
            oa.Comparison(
                op="greaterThan", subject=oa.FieldSubject("address.geo.elevation"), value=5.0
            ),
        ),
    ) == (
        "left join customer t1 on t1.id = t0.customer_id where t1.name = ? and "
        "exists (select 1 from customer t2 where t2.id = t0.customer_id and "
        "cast(jsonb_extract_path_text(t2.address, ?, ?) as double precision) > ?)"
    )


def test_a_match_reading_through_a_further_hop_joins_it_inside_its_correlated_exists() -> None:
    op = oa.And(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("OrderStatus.orderItem.sku"), value="S"),
            oa.Presence(
                "exists",
                "OrderStatus.orderItem",
                oa.Comparison(op="eq", subject=oa.FieldSubject("order.name"), value="Ada"),
            ),
        )
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.statement.sql.endswith(
        "left join order_item t1 on t1.id = t0.order_item_id where t1.sku = ? and "
        "exists (select 1 from order_item t2 left join orders t3 on t3.id = t2.order_id "
        "where t2.id = t0.order_item_id and t3.name = ?)"
    )


def test_a_match_past_a_dotted_prefix_keeps_its_scalar_form_when_its_operand_quantifies() -> None:
    compiled = compile_read(
        oa.Presence(
            "notExists",
            "OrderStatus.orderItem.order",
            oa.Quantifier(
                "any",
                "items",
                oa.Comparison(op="eq", subject=oa.FieldSubject("sku"), value="S"),
            ),
        ),
        ORDERS,
        POSTGRES,
        target(ORDERS, "OrderStatus"),
    )
    assert compiled.statement.sql.endswith(
        "from order_status t0 where not coalesce((select exists (select 1 from orders t1 "
        "where t1.id = t3.order_id and exists (select 1 from order_item t2 "
        "where t2.order_id = t1.id and t2.sku = ?)) "
        "from order_item t3 where t3.id = t0.order_item_id), false)"
    )


def test_a_quantifier_past_a_dotted_prefix_joins_nothing_inside_its_scalar_subquery() -> None:
    compiled = compile_read(
        oa.Quantifier(
            "any",
            "OrderStatus.orderItem.order.items",
            oa.Comparison(op="eq", subject=oa.FieldSubject("order.name"), value="Ada"),
        ),
        ORDERS,
        POSTGRES,
        target(ORDERS, "OrderStatus"),
    )
    assert compiled.statement.sql.endswith(
        "from order_status t0 left join order_item t1 on t1.id = t0.order_item_id "
        "where coalesce((select exists (select 1 from order_item t2 where t2.order_id = t4.id "
        "and (select t3.name from orders t3 where t3.id = t2.order_id) = ?) "
        "from orders t4 where t4.id = t1.order_id and t1.id = t0.order_item_id), false)"
    )


def test_a_multi_table_target_keeps_its_full_candidate_assertion() -> None:
    op = oa.And(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Parking.vehicle.maker"), value="Saab"),
            oa.Presence("exists", "Parking.vehicle"),
        )
    )
    compiled = compile_read(op, TRAVERSAL, POSTGRES, target(TRAVERSAL, "Parking"))
    assert compiled.statement.sql.endswith(
        "where (select t1.maker from traversal_bike t1 where t1.id = t0.vehicle_id union all "
        "select t2.maker from traversal_car t2 where t2.id = t0.vehicle_id) = ? and "
        "(exists (select 1 from traversal_bike t3 where t3.id = t0.vehicle_id) "
        "or exists (select 1 from traversal_car t4 where t4.id = t0.vehicle_id))"
    )


def test_a_narrow_whose_operand_reads_past_its_target_keeps_a_monomorphic_envelope() -> None:
    # A joined narrowing admits only an operand over its target's own row; this
    # one reads a further hop, so the single hop stays the narrowing's subquery.
    compiled = compile_read(
        oa.Narrow(
            path="Claim.coverage",
            to=("Coverage",),
            operand=oa.Comparison(op="eq", subject=oa.FieldSubject("policy.name"), value="Auto"),
        ),
        POLICY,
        POSTGRES,
        target(POLICY, "Claim"),
        temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
    )
    assert "join" not in compiled.statement.sql
    assert "where (coalesce((select array [ (select t1.name from policy t1 where " in (
        compiled.statement.sql
    )


_MARCH = "2024-03-01T00:00:00Z"


@pytest.mark.parametrize(
    ("valid_time", "transaction_time", "visible"),
    [
        ("latest", "latest", "t1.thru_z = ? and t1.out_z = ?"),
        (_MARCH, "latest", "t1.from_z <= ? and t1.thru_z > ? and t1.out_z = ?"),
        (_MARCH, _MARCH, "t1.from_z <= ? and t1.thru_z > ? and t1.in_z <= ? and t1.out_z > ?"),
    ],
)
def test_a_temporal_target_at_one_coordinate_per_axis_reads_a_shared_join(
    valid_time: str, transaction_time: str, visible: str
) -> None:
    # Latest ends fix the physical key; a finite instant fixes no end, so the
    # logical key and one perspective per axis prove the one milestone instead.
    compiled = compile_read(
        oa.Comparison(
            op="greaterThan", subject=oa.FieldSubject("Claim.coverage.amount"), value="1.00"
        ),
        POLICY,
        POSTGRES,
        target(POLICY, "Claim"),
        temporal={"valid-time": AsOf(valid_time), "transaction-time": AsOf(transaction_time)},
    )
    assert f"from claim t0 left join coverage t1 on t1.id = t0.coverage_id and {visible} " in (
        compiled.statement.sql
    )
    assert " where t1.amount > ? and " in compiled.statement.sql


def test_each_temporal_hop_is_proven_at_the_coordinates_propagated_to_it() -> None:
    compiled = compile_read(
        oa.Comparison(op="eq", subject=oa.FieldSubject("Claim.coverage.policy.name"), value="A"),
        POLICY,
        POSTGRES,
        target(POLICY, "Claim"),
        temporal={"valid-time": AsOf(_MARCH), "transaction-time": AsOf("latest")},
    )
    assert compiled.statement.sql.endswith(
        "left join coverage t1 on t1.id = t0.coverage_id and t1.from_z <= ? and t1.thru_z > ? "
        "and t1.out_z = ? left join policy t2 on t2.id = t1.policy_id and t2.from_z <= ? "
        "and t2.thru_z > ? and t2.out_z = ? where t2.name = ? and t0.from_z <= ? "
        "and t0.thru_z > ? and t0.out_z = ?"
    )


@pytest.mark.parametrize(
    ("unique", "expected"),
    [
        (True, "left join badge t1 on t1.holder_id = t0.id and t1.thru_z = ? and t1.out_z = ? "),
        (False, "where (select t1.code from badge t1 where t1.holder_id = t0.id and t1.thru_z"),
    ],
)
def test_a_temporal_target_correlated_off_its_logical_key_needs_a_unique_key(
    unique: bool, expected: str
) -> None:
    # One perspective per axis identifies one milestone of one logical object;
    # a badge reached by its holder is not reached by its own key.
    family = _document_model(
        _entity("Holder", relationships=[_rel("badge", "id", "Badge", "holderId", "one-to-one")]),
        _entity(
            "Badge",
            "holderId",
            temporality="bitemporal",
            members=[{"name": "code", "type": "string", "maxLength": 8}],
            indices=[{"name": "badge_holder", "attributes": ["holderId"], "unique": unique}],
        ),
    )
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Holder.badge.code"), value="B")
    compiled = compile_read(op, family, POSTGRES, target(family, "Holder"))
    assert expected in compiled.statement.sql


@pytest.mark.parametrize(
    ("unique", "expected"),
    [
        (True, "left join badge t1 on t1.holder_id = t0.id where t1.code = ?"),
        (False, "where (select t1.code from badge t1 where t1.holder_id = t0.id) = ?"),
    ],
)
def test_only_a_unique_key_proves_a_declared_one_to_one_target(unique: bool, expected: str) -> None:
    # The nullable `holder_id` is the correlated Column: strict equality never
    # matches its null, so a unique index over it proves at most one badge, and
    # the declared one-to-one cardinality alone proves nothing.
    family = _badge_model(unique=unique)
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Holder.badge.code"), value="B")
    compiled = compile_read(op, family, POSTGRES, target(family, "Holder"))
    assert compiled.statement.sql.endswith(expected)


# --------------------------------------------------------------------------- #
# Eligibility read directly from a hop's typed visibility.                    #
# --------------------------------------------------------------------------- #
def _hop(model: Metamodel, source: str, path: str) -> ResolvedRelationship:
    """The unresolved to-many relationship ``path`` reaches from ``source``."""
    resolved = oa.validate_predicate(target(model, source), oa.Quantifier("any", path), model)
    assert isinstance(resolved, ResolvedQuantifier)
    assert isinstance(resolved.collection, ResolvedRelationship)
    return resolved.collection


def _to_one(model: Metamodel, source: str, path: str) -> ResolvedRelationship:
    resolved = oa.validate_predicate(target(model, source), oa.Presence("exists", path), model)
    assert isinstance(resolved, ResolvedPresence)
    assert isinstance(resolved.target, ResolvedRelationship)
    return resolved.target


def _eligible(
    model: Metamodel, source: str, hop: ResolvedRelationship, visibility: TemporalPerspective
) -> bool:
    entity = target(model, source)
    facet, storage = inheritance.view(model), storage_layout.view(model)
    scope = EntityScope(
        StatementBuilder(model, facet, storage, POSTGRES),
        entity,
        table_layout(storage, facet, entity.identity),
    )
    seen = dataclasses.replace(hop, temporal_visibility=visibility)
    candidates = plan_relationship_candidates(seen, position=None, scope=scope)
    return shared_relationship_is_eligible(seen, candidates, scope)


_INSTANT = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _axes(model: Metamodel, name: str) -> Bitemporal:
    shape = temporal_view(model).shape(target(model, name).identity)
    assert isinstance(shape, Bitemporal)
    return shape


def _seen(model: Metamodel, name: str, *, valid: bool, tx: bool) -> TemporalPerspective:
    """``name``'s visibility: Latest on each axis flagged, else At one instant."""
    shape = _axes(model, name)
    return TemporalPerspective(
        valid_time=(
            LatestPerspective(shape.valid_time)
            if valid
            else AtPerspective(shape.valid_time, _INSTANT)
        ),
        transaction_time=(
            LatestPerspective(shape.transaction_time)
            if tx
            else AtPerspective(shape.transaction_time, _INSTANT)
        ),
    )


def _temporal_badges(*, unique: bool) -> Metamodel:
    return _document_model(
        _entity("Holder", relationships=[_rel("badge", "id", "Badge", "holderId", "one-to-one")]),
        _entity(
            "Badge",
            "holderId",
            temporality="bitemporal",
            indices=[{"name": "badge_holder", "attributes": ["holderId"], "unique": unique}],
        ),
    )


def test_a_physical_unique_key_the_correlation_fixes_proves_a_non_temporal_hop() -> None:
    hop = _to_one(ORDERS, "OrderItem", "OrderItem.order")
    assert _eligible(ORDERS, "OrderItem", hop, TemporalPerspective())


@pytest.mark.parametrize("unique", [True, False])
def test_a_nullable_correlated_column_is_proven_only_by_a_unique_key(unique: bool) -> None:
    family = _badge_model(unique=unique)
    hop = _to_one(family, "Holder", "Holder.badge")
    assert _eligible(family, "Holder", hop, TemporalPerspective()) is unique


@pytest.mark.parametrize(
    ("valid", "tx"),
    [(True, True), (False, True), (True, False), (False, False)],
    ids=["latest-latest", "at-latest", "latest-at", "at-at"],
)
def test_a_temporal_hop_correlated_by_its_logical_key_is_proven_at_any_perspective(
    valid: bool, tx: bool
) -> None:
    # Latest ends complete the physical key; an instant fixes no end, so the
    # logical key and the perspective's one milestone per axis prove it instead.
    hop = _to_one(POLICY, "Claim", "Claim.coverage")
    assert _eligible(POLICY, "Claim", hop, _seen(POLICY, "Coverage", valid=valid, tx=tx))


@pytest.mark.parametrize("latest", [True, False], ids=["latest", "at"])
def test_a_temporal_hop_off_its_logical_key_needs_a_unique_key_the_correlation_fixes(
    latest: bool,
) -> None:
    for unique in (True, False):
        family = _temporal_badges(unique=unique)
        hop = _to_one(family, "Holder", "Holder.badge")
        visibility = _seen(family, "Badge", valid=latest, tx=latest)
        assert _eligible(family, "Holder", hop, visibility) is unique


def test_several_physical_candidates_are_never_proven_unique() -> None:
    hop = _hop(DOCUMENT, "Folder", "Folder.documents")
    assert not _eligible(DOCUMENT, "Folder", hop, TemporalPerspective())


def test_a_locking_read_locks_only_its_root_beside_a_shared_join() -> None:
    compiled = compile_read(
        _ADA, ORDERS, POSTGRES, target(ORDERS, "OrderItem"), limit=5, preference="locking"
    )
    assert compiled.statement.sql == (
        f"{_ORDER_ITEM_ROW} left join orders t1 on t1.id = t0.order_id where t1.name = ? "
        "limit ? for share of t0"
    )
    assert compiled.statement.binds == ("Ada", 5)


def test_readless_predicate_dml_reads_a_presence_through_its_key_selection_s_join() -> None:
    op = oa.Not(oa.And(operands=(oa.Presence("exists", "OrderItem.order"), _ADA)))
    compiled = compile_write_predicate(op, ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    assert compiled.selection
    assert compiled.sql == (
        "select t0.id from order_item t0 left join orders t1 on t1.id = t0.order_id "
        "where not (not t1.id is null and t1.name = ?)"
    )


def test_readless_predicate_dml_keeps_a_match_alone_in_place() -> None:
    # Matching alone opens no join, so nothing is shared and the operand's own
    # further hop stays in its local form.
    ada = oa.Comparison(op="eq", subject=oa.FieldSubject("order.name"), value="Ada")
    op = oa.Presence("exists", "OrderStatus.orderItem", ada)
    compiled = compile_write_predicate(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert not compiled.selection
    assert compiled.sql == (
        "exists (select 1 from order_item t1 where t1.id = order_item_id "
        "and (select t2.name from orders t2 where t2.id = t1.order_id) = ?)"
    )


def test_a_key_selection_joins_inside_a_match_its_shared_target_cannot_answer() -> None:
    # The match's operand reads past its target, so it keeps its own `exists`;
    # the selection is a set-level scope, so that body joins its proven hop.
    order = oa.Comparison(op="eq", subject=oa.FieldSubject("order.name"), value="Ada")
    op = oa.And(
        operands=(
            oa.Comparison(
                op="lessThan", subject=oa.FieldSubject("OrderStatus.orderItem.quantity"), value=3
            ),
            oa.Presence("exists", "OrderStatus.orderItem", order),
        )
    )
    compiled = compile_write_predicate(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    read = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "OrderStatus"))
    assert compiled.sql == (
        "select t0.id from order_status t0 left join order_item t1 on t1.id = t0.order_item_id "
        "where t1.quantity < ? and exists (select 1 from order_item t2 left join orders t3 "
        "on t3.id = t2.order_id where t2.id = t0.order_item_id and t3.name = ?)"
    )
    assert read.statement.sql.endswith(compiled.sql.removeprefix("select t0.id"))


def test_readless_predicate_dml_keeps_a_quantifier_operand_s_scalar_form() -> None:
    op = oa.Quantifier(
        "any",
        "Order.items",
        oa.Comparison(op="eq", subject=oa.FieldSubject("order.name"), value="Ada"),
    )
    compiled = compile_write_predicate(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.sql == (
        "exists (select 1 from order_item t1 where t1.order_id = id "
        "and (select t2.name from orders t2 where t2.id = t1.order_id) = ?)"
    )


def _vehicle_desk_model() -> Metamodel:
    return _document_model(
        _entity("Desk", "spanId", relationships=[_rel("span", "spanId", "Span")]),
        _entity(
            "Span",
            "vehicleId",
            temporality="bitemporal",
            relationships=[_rel("vehicle", "vehicleId", "Vehicle")],
        ),
        {
            "name": "Vehicle",
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [_KEY, _reference("dealerId")],
            "relationships": [_rel("dealer", "dealerId", "Dealer")],
        },
        _concrete("Car", "Vehicle", table="car"),
        _concrete("Bike", "Vehicle", table="bike"),
        _entity("Dealer", members=[{"name": "name", "type": "string", "maxLength": 8}]),
    )


_SPAN_REACHED = "t1.id = t0.span_id and t1.thru_z = ? and t1.out_z = ?"


def test_an_unproven_hop_behind_a_joined_prefix_reads_only_that_prefix_s_candidates() -> None:
    # Each vehicle branch repeats the span join's terms, so its candidates are the
    # joined span's alone wherever the term is evaluated; the dealer, though
    # proven, nests in the branch's select list rather than joining inside a
    # subquery that runs once per row.
    family = _vehicle_desk_model()
    op = oa.Comparison(op="eq", subject=oa.FieldSubject("Desk.span.vehicle.dealer.name"), value="x")
    compiled = compile_read(op, family, POSTGRES, target(family, "Desk"))
    assert compiled.statement.sql.endswith(
        f"from desk t0 left join span t1 on {_SPAN_REACHED} where (select (select t2.name "
        "from dealer t2 where t2.id = t3.dealer_id) from bike t3 where t3.id = t1.vehicle_id "
        f"and {_SPAN_REACHED} union all select (select t4.name from dealer t4 where "
        f"t4.id = t5.dealer_id) from car t5 where t5.id = t1.vehicle_id and {_SPAN_REACHED}) = ?"
    )
    assert compiled.statement.binds == (*(INFINITY,) * 6, "x")


def test_a_presence_past_an_unproven_hop_keeps_its_absence_default_behind_the_join() -> None:
    family = _vehicle_desk_model()
    compiled = compile_read(
        oa.Presence("notExists", "Desk.span.vehicle.dealer"),
        family,
        POSTGRES,
        target(family, "Desk"),
    )
    assert compiled.statement.sql.endswith(
        f"from desk t0 left join span t1 on {_SPAN_REACHED} where not coalesce((select exists "
        "(select 1 from dealer t2 where t2.id = t3.dealer_id) from bike t3 where "
        f"t3.id = t1.vehicle_id and {_SPAN_REACHED} union all select exists (select 1 from "
        f"dealer t4 where t4.id = t5.dealer_id) from car t5 where t5.id = t1.vehicle_id and "
        f"{_SPAN_REACHED}), false)"
    )


def test_a_conversion_past_proven_hops_shares_all_but_its_last_hop() -> None:
    # The cast cannot be a filter over the joined crate, so the crate is read by a
    # subquery confined to the joined box, while the box itself is shared.
    family = _document_model(
        _entity("Shelf", "boxId", relationships=[_rel("box", "boxId", "Box")]),
        _entity("Box", "crateId", relationships=[_rel("crate", "crateId", "Crate")]),
        _entity(
            "Crate",
            layout={"document": {"column": "payload"}},
            members=[{"name": "weight", "type": "decimal(18,2)"}],
        ),
    )
    op = oa.Comparison(
        op="greaterThan", subject=oa.FieldSubject("Shelf.box.crate.weight"), value="1.00"
    )
    compiled = compile_read(op, family, POSTGRES, target(family, "Shelf"))
    assert compiled.statement.sql.endswith(
        "from shelf t0 left join box t1 on t1.id = t0.box_id where (select "
        "cast(jsonb_extract_path_text(t2.payload, ?) as decimal(18, 2)) from crate t2 "
        "where t2.id = t1.crate_id and t1.id = t0.box_id) > ?"
    )


def _pet_owner_model() -> Metamodel:
    return _document_model(
        _entity("Leash", "collarId", relationships=[_rel("collar", "collarId", "Collar")]),
        _entity("Collar", "petId", relationships=[_rel("pet", "petId", "Pet")]),
        {
            "name": "Pet",
            "table": "pet",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [_KEY, {"name": "name", "type": "string", "maxLength": 8}],
        },
        {
            **_concrete("Dog", "Pet", tagValue="dog"),
            "attributes": [_reference("ownerId")],
            "relationships": [_rel("owner", "ownerId", "Owner")],
        },
        _concrete("Cat", "Pet", tagValue="cat"),
        _entity("Owner", members=[{"name": "name", "type": "string", "maxLength": 8}]),
    )


def _partial_pet_owner_model() -> Metamodel:
    """``_pet_owner_model``'s family composed without ``Cat``: the shared ``pet``
    table may hold rows this model's tag vocabulary does not name."""
    return _document_model(
        _entity("Leash", "collarId", relationships=[_rel("collar", "collarId", "Collar")]),
        _entity("Collar", "petId", relationships=[_rel("pet", "petId", "Pet")]),
        {
            "name": "Pet",
            "table": "pet",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [_KEY, {"name": "name", "type": "string", "maxLength": 8}],
        },
        {
            **_concrete("Dog", "Pet", tagValue="dog"),
            "attributes": [_reference("ownerId")],
            "relationships": [_rel("owner", "ownerId", "Owner")],
        },
        _entity("Owner", members=[{"name": "name", "type": "string", "maxLength": 8}]),
    )


def test_a_partially_composed_root_quantifier_candidate_carries_no_tag_guard() -> None:
    compiled = compile_read(
        oa.Quantifier("any", "Keeper.beasts"), BEAST, POSTGRES, target(BEAST, "Keeper")
    )
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from beast t1 where t1.keeper_id = t0.id)"
    )
    narrowed = compile_read(
        oa.Quantifier("any", "Keeper.beasts", oa.Narrow(to=("Wolf",), operand=oa.TrueNode())),
        BEAST,
        POSTGRES,
        target(BEAST, "Keeper"),
    )
    assert narrowed.statement.sql.endswith(
        "where exists (select 1 from beast t1 where t1.keeper_id = t0.id and t1.kind = ?)"
    )
    assert narrowed.statement.binds == ("wolf",)


def test_a_partially_composed_root_shares_its_to_one_source_unguarded() -> None:
    family = _partial_pet_owner_model()
    compiled = compile_read(
        oa.Comparison(op="eq", subject=oa.FieldSubject("Leash.collar.pet.name"), value="Rex"),
        family,
        POSTGRES,
        target(family, "Leash"),
    )
    assert compiled.statement.sql.endswith(
        "from leash t0 left join collar t1 on t1.id = t0.collar_id "
        "left join pet t2 on t2.id = t1.pet_id where t2.name = ?"
    )
    narrowed = compile_read(
        oa.Narrow(path="Collar.pet", to=("Dog",), operand=oa.TrueNode()),
        family,
        POSTGRES,
        target(family, "Collar"),
    )
    assert narrowed.statement.sql.endswith(
        "left join pet t1 on t1.id = t0.pet_id where (not t1.id is null and t1.kind = ?)"
    )
    assert narrowed.statement.binds == ("dog",)


def test_a_partially_composed_root_correlated_candidate_carries_no_tag_guard() -> None:
    # Only the narrowing's own membership test reads the tag; the candidate
    # subquery itself ranges over the whole shared table.
    family = _partial_pet_owner_model()
    op = oa.Narrow(
        path="Leash.collar.pet",
        to=("Dog",),
        operand=oa.Comparison(op="eq", subject=oa.FieldSubject("owner.name"), value="Ann"),
    )
    compiled = compile_read(op, family, POSTGRES, target(family, "Leash"))
    assert compiled.statement.sql.endswith(
        "where (coalesce((select array [ case when t3.kind = ? then (select t2.name from owner "
        "t2 where t2.id = t3.owner_id) = ? else false end ] from pet t3 where t3.id = t1.pet_id "
        "and t1.id = t0.collar_id), array [ false ])) [ 1 ]"
    )


def test_a_predicate_write_keeps_the_partially_composed_root_candidate_unguarded() -> None:
    compiled = compile_write_predicate(
        oa.Quantifier("any", "Keeper.beasts"), BEAST, POSTGRES, target(BEAST, "Keeper")
    )
    assert compiled.sql == "exists (select 1 from beast t1 where t1.keeper_id = id)"
    assert compiled.binds == ()


def test_a_joined_narrow_stays_one_term_under_negation_and_disjunction() -> None:
    narrowed = oa.Narrow(path="Collar.pet", to=("Dog",), operand=oa.TrueNode())
    op = oa.Or(
        operands=(
            oa.Not(operand=narrowed),
            oa.Comparison(op="eq", subject=oa.FieldSubject("Collar.id"), value=13),
        )
    )
    compiled = compile_read(op, TRAVERSAL, POSTGRES, target(TRAVERSAL, "Collar"))
    assert compiled.statement.sql.endswith(
        "left join traversal_pet t1 on t1.id = t0.pet_id "
        "where not (not t1.id is null and t1.kind = ?) or t0.id = ?"
    )
    assert compiled.statement.binds == ("dog", 13)


def test_a_narrow_whose_operand_reads_past_its_target_keeps_its_candidate_subquery() -> None:
    # The same narrowing over a joined pet would test the owner's subquery on pets
    # no leash reaches, so only the collar is shared and the pet keeps its
    # envelope, confined to the joined collar.
    family = _pet_owner_model()
    op = oa.Narrow(
        path="Leash.collar.pet",
        to=("Dog",),
        operand=oa.Comparison(op="eq", subject=oa.FieldSubject("owner.name"), value="Ann"),
    )
    compiled = compile_read(op, family, POSTGRES, target(family, "Leash"))
    assert compiled.statement.sql.endswith(
        "from leash t0 left join collar t1 on t1.id = t0.collar_id where (coalesce((select "
        "array [ case when t3.kind = ? then (select t2.name from owner t2 where t2.id = "
        "t3.owner_id) = ? else false end ] from pet t3 where t3.id = t1.pet_id and "
        "t1.id = t0.collar_id), array [ false ])) [ 1 ]"
    )
    assert compiled.statement.binds == ("dog", "Ann")


def test_a_narrowing_of_the_read_row_joins_the_hops_its_operand_reads() -> None:
    family = _pet_owner_model()
    op = oa.Narrow(
        to=("Dog",),
        operand=oa.Comparison(op="eq", subject=oa.FieldSubject("Dog.owner.name"), value="Ann"),
    )
    compiled = compile_read(op, family, POSTGRES, target(family, "Pet"))
    assert compiled.statement.sql.endswith(
        "from pet t0 left join owner t1 on t1.id = t0.owner_id where (t1.name = ? and t0.kind = ?)"
    )
    assert compiled.statement.binds == ("Ann", "dog")


def test_a_union_branch_outside_a_narrowing_joins_nothing_for_its_operand() -> None:
    family = _document_model(
        {
            "name": "Vehicle",
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [_KEY],
        },
        {
            **_concrete("Car", "Vehicle", table="car"),
            "attributes": [_reference("ownerId")],
            "relationships": [_rel("owner", "ownerId", "Owner")],
        },
        _concrete("Bike", "Vehicle", table="bike"),
        _entity("Owner", members=[{"name": "name", "type": "string", "maxLength": 8}]),
    )
    op = oa.Narrow(
        to=("Car",),
        operand=oa.Comparison(op="eq", subject=oa.FieldSubject("Car.owner.name"), value="Ann"),
    )
    compiled = compile_read(op, family, POSTGRES, target(family, "Vehicle"))
    bike, car = compiled.statement.sql.split(" union all ")
    assert "join" not in bike
    assert bike.endswith("from bike t0 where 1 = 0")
    assert "from car t0 left join owner t1 on t1.id = t0.owner_id where t1.name = ?" in car


def test_a_partition_of_a_table_per_hierarchy_read_joins_its_proven_hops() -> None:
    family = _document_model(
        _entity("Account", members=[{"name": "name", "type": "string", "maxLength": 8}]),
        {
            "name": "Payment",
            "table": "payment",
            "layout": {"document": {"column": "payload"}},
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [_KEY, _reference("accountId")],
            "relationships": [_rel("account", "accountId", "Account")],
        },
        {
            **_concrete("Card", "Payment", tagValue="card"),
            "attributes": [{"name": "detail", "type": "string", "maxLength": 8}],
        },
        {
            **_concrete("Cash", "Payment", tagValue="cash"),
            "attributes": [{"name": "detail", "type": "decimal(18,2)"}],
        },
    )
    detail = oa.Or(
        operands=(
            oa.Narrow(
                to=("Card",),
                operand=oa.Comparison(op="eq", subject=oa.FieldSubject("Card.detail"), value="v"),
            ),
            oa.Narrow(
                to=("Cash",),
                operand=oa.Comparison(
                    op="greaterThan", subject=oa.FieldSubject("Cash.detail"), value="1.00"
                ),
            ),
        )
    )
    named = oa.Comparison(op="eq", subject=oa.FieldSubject("Payment.account.name"), value="A")
    compiled = compile_read(
        oa.And(operands=(detail, named)), family, POSTGRES, target(family, "Payment")
    )
    card, cash = compiled.statement.sql.split(" union all ")
    for branch, alias in ((card, "p1"), (cash, "p2")):
        assert (
            f"offset 0) {alias} left join account t1 on t1.id = {alias}.account_id where "
        ) in branch
        assert branch.endswith(" and t1.name = ?")


def test_a_universal_joins_its_operands_proven_hop_beside_its_counterexample() -> None:
    op = oa.Quantifier(
        "all",
        "Order.items",
        oa.Comparison(op="eq", subject=oa.FieldSubject("order.name"), value="Ada"),
    )
    compiled = compile_read(op, ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith(
        "where not exists (select 1 from order_item t1 left join orders t2 on "
        "t2.id = t1.order_id where t1.order_id = t0.id and not (t2.name = ?) is true)"
    )


_KEY: dict[str, object] = {"name": "id", "type": "int64", "primaryKey": True}


def _reference(name: str) -> dict[str, object]:
    return {"name": name, "type": "int64", "nullable": True}


def _rel(
    name: str, source: str, entity: str, attribute: str = "id", cardinality: str = "many-to-one"
) -> dict[str, object]:
    return {
        "name": name,
        "cardinality": cardinality,
        "join": {"source": source, "target": {"entity": entity, "attribute": attribute}},
    }


def _entity(
    name: str,
    *references: str,
    members: list[dict[str, object]] | None = None,
    relationships: list[dict[str, object]] | None = None,
    **declared: object,
) -> dict[str, object]:
    """A standalone Entity on its own table, keyed by `id`, with a nullable
    Int64 Attribute per reference."""
    return {
        "name": name,
        "table": name.lower(),
        "attributes": [_KEY, *map(_reference, references), *(members or [])],
        "relationships": relationships or [],
        **declared,
    }


def _concrete(name: str, parent: str, **declared: object) -> dict[str, object]:
    inheritance: dict[str, object] = {"role": "concrete-subtype", "parent": parent}
    if "tagValue" in declared:
        inheritance["tagValue"] = declared.pop("tagValue")
    return {"name": name, "inheritance": inheritance, **declared}


def _document_model(*entities: dict[str, object]) -> Metamodel:
    from parallax.descriptor._ingest import ingest_document

    return formed(ingest_document({"entities": list(entities)}))


def _tph_owner_model() -> Metamodel:
    from parallax.descriptor._records import (
        Attribute,
        DefiningRelationship,
        Entity,
        Inheritance,
        RelationshipJoin,
        RelationshipTarget,
    )
    from parallax.descriptor._records import Metamodel as Records

    pet = Entity(
        name="Pet",
        table="pet",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="name", type="string", column="name", max_length=32),
        ),
    )
    dog = Entity(
        name="Dog", inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="dog")
    )
    cat = Entity(
        name="Cat", inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="cat")
    )
    leash = Entity(
        name="Leash",
        table="leash",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="dogId", type="int64", column="dog_id", nullable=True),
        ),
        relationships=(
            DefiningRelationship(
                name="dog",
                cardinality="many-to-one",
                join=RelationshipJoin(
                    source="dogId", target=RelationshipTarget(entity="Dog", attribute="id")
                ),
            ),
        ),
    )
    return formed(Records(entities=(pet, dog, cat, leash)))


def _badge_model(*, unique: bool) -> Metamodel:
    from parallax.descriptor._records import (
        Attribute,
        DefiningRelationship,
        Entity,
        Index,
        RelationshipJoin,
        RelationshipTarget,
    )
    from parallax.descriptor._records import Metamodel as Records

    holder = Entity(
        name="Holder",
        table="holder",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        relationships=(
            DefiningRelationship(
                name="badge",
                cardinality="one-to-one",
                join=RelationshipJoin(
                    source="id", target=RelationshipTarget(entity="Badge", attribute="holderId")
                ),
            ),
        ),
    )
    badge = Entity(
        name="Badge",
        table="badge",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="holderId", type="int64", column="holder_id", nullable=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(Index(name="badge_holder", attributes=("holderId",), unique=unique),),
    )
    return formed(Records(entities=(holder, badge)))


_TAGS: dict[str, object] = {"name": "tags", "type": "string", "multiplicity": "many"}
_SCORES: dict[str, object] = {"name": "scores", "type": "int32", "multiplicity": "many"}
_PARCELS: dict[str, object] = {
    "name": "parcels",
    "multiplicity": "many",
    "attributes": [{"name": "sku", "type": "string"}, {"name": "qty", "type": "int32"}],
}


def _element(op: oa.ComparisonOp, value: oa.ScalarLiteral) -> oa.Comparison:
    return oa.Comparison(op=op, subject=oa.CURRENT_SCALAR_ELEMENT, value=value)


def _crate_model() -> Metamodel:
    return _document_model(
        _entity("Shelf", "boxId", relationships=[_rel("box", "boxId", "Box")]),
        _entity("Box", "crateId", relationships=[_rel("crate", "crateId", "Crate")]),
        _entity("Crate", members=[_TAGS, _SCORES], valueObjects=[_PARCELS]),
    )


_CRATE_JOINS = (
    "from shelf t0 left join box t1 on t1.id = t0.box_id left join crate t2 on t2.id = t1.crate_id"
)


def test_document_collections_of_a_shared_target_read_one_owner_result_relation() -> None:
    # One relation per owner; each quantifier, of either collection, keeps its column.
    family = _crate_model()
    sku = oa.Comparison(op="eq", subject=oa.FieldSubject("sku"), value="s")
    op = oa.And(
        operands=(
            oa.Quantifier("any", "Shelf.box.crate.tags", _element("eq", "a")),
            oa.Quantifier("none", "Shelf.box.crate.parcels", sku),
        )
    )
    compiled = compile_read(op, family, POSTGRES, target(family, "Shelf"))
    assert compiled.statement.sql.endswith(
        f"{_CRATE_JOINS} left join (select t5.id, exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(t5.tags) = ? then t5.tags else cast(? as jsonb) end) t3 where "
        "case when jsonb_typeof(t3.value) = ? then t3.value #>> ? end = ?) q0, not exists "
        "(select 1 from jsonb_array_elements(case when jsonb_typeof(t5.parcels) = ? then "
        "t5.parcels else cast(? as jsonb) end) t4 where jsonb_extract_path_text(t4.value, ?) = ?) "
        "q1 from crate t5) r0 on r0.id = t2.id where coalesce(r0.q0, false) and "
        "coalesce(r0.q1, true)"
    )
    assert compiled.statement.binds == (
        *("array", "[]", "string", "{}", "a"),
        *("array", "[]", "sku", "s"),
    )


def test_owner_results_are_keyed_by_every_physical_primary_key_column() -> None:
    family = _document_model(
        _entity("Desk", "spanId", relationships=[_rel("span", "spanId", "Span")]),
        _entity("Span", temporality="bitemporal", members=[_TAGS]),
    )
    op = oa.Quantifier("any", "Desk.span.tags", _element("eq", "a"))
    compiled = compile_read(op, family, POSTGRES, target(family, "Desk"))
    assert compiled.statement.sql.endswith(
        "left join span t1 on t1.id = t0.span_id and t1.thru_z = ? and t1.out_z = ? "
        "left join (select t3.id, t3.thru_z, t3.out_z, exists (select 1 from "
        "jsonb_array_elements(case when jsonb_typeof(t3.tags) = ? then t3.tags else "
        "cast(? as jsonb) end) t2 where case when jsonb_typeof(t2.value) = ? then "
        "t2.value #>> ? end = ?) q0 from span t3) r0 on r0.id = t1.id and r0.thru_z = t1.thru_z "
        "and r0.out_z = t1.out_z where coalesce(r0.q0, false)"
    )


def test_owner_results_read_a_document_resident_collection_at_its_placed_path() -> None:
    family = _document_model(
        _entity("Desk", "spanId", relationships=[_rel("span", "spanId", "Span")]),
        _entity("Span", layout={"document": {"column": "payload"}}, members=[_TAGS]),
    )
    compiled = compile_read(
        oa.Quantifier("none", "Desk.span.tags"), family, POSTGRES, target(family, "Desk")
    )
    assert compiled.statement.sql.endswith(
        "left join span t1 on t1.id = t0.span_id left join (select t3.id, not exists (select 1 "
        "from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t3.payload, ?)) = ? "
        "then jsonb_extract_path(t3.payload, ?) else cast(? as jsonb) end) t2) q0 from span t3) "
        "r0 on r0.id = t1.id where coalesce(r0.q0, true)"
    )
    assert compiled.statement.binds == ("tags", "array", "tags", "[]")


def test_a_result_column_takes_no_name_a_key_column_spells() -> None:
    family = _document_model(
        _entity("Desk", "spanId", relationships=[_rel("span", "spanId", "Span", "q0")]),
        {
            "name": "Span",
            "table": "span",
            "attributes": [{"name": "q0", "type": "int64", "primaryKey": True}, _TAGS],
        },
    )
    compiled = compile_read(
        oa.Quantifier("any", "Desk.span.tags"), family, POSTGRES, target(family, "Desk")
    )
    assert compiled.statement.sql.endswith(
        "(select t3.q0, exists (select 1 from jsonb_array_elements(case when jsonb_typeof(t3.tags) "
        "= ? then t3.tags else cast(? as jsonb) end) t2) q1 from span t3) r0 on r0.q0 = t1.q0 "
        "where coalesce(r0.q1, false)"
    )


@pytest.mark.parametrize(
    ("op", "evaluated"),
    [
        pytest.param(
            oa.Quantifier("any", "Shelf.box.crate.scores", _element("greaterThan", 3)),
            "coalesce((select exists (select 1 from jsonb_array_elements(case when "
            "jsonb_typeof(t3.scores) = ? then t3.scores else cast(? as jsonb) end) t2 where "
            "case when jsonb_typeof(t2.value) = ? then cast(t2.value #>> ? as bigint) end > ?)",
            id="scalar-element-cast",
        ),
        pytest.param(
            oa.Quantifier(
                "all",
                "Shelf.box.crate.parcels",
                oa.Comparison(op="greaterThan", subject=oa.FieldSubject("qty"), value=3),
            ),
            "coalesce((select not exists (select 1 from jsonb_array_elements(case when "
            "jsonb_typeof(t3.parcels) = ? then t3.parcels else cast(? as jsonb) end) t2 where "
            "not (cast(jsonb_extract_path_text(t2.value, ?) as bigint) > ?) is true)",
            id="value-object-member-cast",
        ),
    ],
)
def test_a_quantifier_whose_element_projection_can_fail_is_confined_past_the_shared_prefix(
    op: oa.Quantifier, evaluated: str
) -> None:
    # Owner results would test the cast on every crate's elements; confined to
    # the joined box, the quantifier reads only the crate the shelf reaches.
    family = _crate_model()
    compiled = compile_read(op, family, POSTGRES, target(family, "Shelf"))
    assert compiled.statement.sql.endswith(
        "from shelf t0 left join box t1 on t1.id = t0.box_id where "
        f"{evaluated} from crate t3 where t3.id = t1.crate_id and t1.id = t0.box_id), "
        f"{'false' if op.kind == 'any' else 'true'})"
    )


def test_a_failing_projection_one_proven_hop_away_keeps_its_scalar_form() -> None:
    family = _crate_model()
    op = oa.Quantifier("any", "Box.crate.scores", _element("greaterThan", 3))
    compiled = compile_read(op, family, POSTGRES, target(family, "Box"))
    assert compiled.statement.sql.endswith(
        "from box t0 where coalesce((select exists (select 1 from jsonb_array_elements(case when "
        "jsonb_typeof(t2.scores) = ? then t2.scores else cast(? as jsonb) end) t1 where case when "
        "jsonb_typeof(t1.value) = ? then cast(t1.value #>> ? as bigint) end > ?) from crate t2 "
        "where t2.id = t0.crate_id), false)"
    )


def _lot_model() -> Metamodel:
    return _document_model(
        _entity("Lot", "dealerId", relationships=[_rel("dealer", "dealerId", "Dealer")]),
        _entity(
            "Dealer",
            members=[_TAGS],
            relationships=[{"name": "vehicles", "reverseOf": "Vehicle.dealer"}],
        ),
        {
            "name": "Vehicle",
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [
                _KEY,
                _reference("dealerId"),
                {"name": "maker", "type": "string", "maxLength": 8},
            ],
            "relationships": [_rel("dealer", "dealerId", "Dealer")],
        },
        _concrete(
            "Car",
            "Vehicle",
            table="car",
            attributes=[{"name": "seats", "type": "int32", "nullable": True}],
        ),
        _concrete("Bike", "Vehicle", table="bike"),
    )


_MAKER = oa.Comparison(op="eq", subject=oa.FieldSubject("maker"), value="x")
_CAR = oa.Narrow(to=("Car",), operand=oa.TrueNode())
_DEALER_JOIN = "from lot t0 left join dealer t1 on t1.id = t0.dealer_id where "


@pytest.mark.parametrize(
    ("op", "where"),
    [
        pytest.param(
            oa.Quantifier("any", "Lot.dealer.vehicles", _MAKER),
            "(exists (select 1 from bike t2 where t2.dealer_id = t1.id and t2.maker = ?) or "
            "exists (select 1 from car t3 where t3.dealer_id = t1.id and t3.maker = ?))",
            id="every-branch",
        ),
        pytest.param(
            oa.Quantifier("any", "Lot.dealer.vehicles", _CAR),
            "exists (select 1 from car t2 where t2.dealer_id = t1.id)",
            id="selected-branch",
        ),
        pytest.param(
            oa.Quantifier("all", "Lot.dealer.vehicles", _CAR),
            "not (exists (select 1 from bike t2 where t2.dealer_id = t1.id and not (1 = 0) is "
            "true) or exists (select 1 from car t3 where t3.dealer_id = t1.id and not (1 = 1) "
            "is true))",
            id="unselected-counterexample",
        ),
    ],
)
def test_a_related_collection_of_a_shared_target_is_quantified_at_its_joined_row(
    op: oa.Quantifier, where: str
) -> None:
    family = _lot_model()
    compiled = compile_read(op, family, POSTGRES, target(family, "Lot"))
    assert compiled.statement.sql.endswith(_DEALER_JOIN + where)


def test_a_related_quantifier_narrowing_with_an_operand_stays_in_its_hop() -> None:
    family = _lot_model()
    roomy = oa.Narrow(
        to=("Car",),
        operand=oa.Comparison(op="greaterThan", subject=oa.FieldSubject("seats"), value=2),
    )
    compiled = compile_read(
        oa.Quantifier("any", "Lot.dealer.vehicles", roomy), family, POSTGRES, target(family, "Lot")
    )
    assert compiled.statement.sql.endswith(
        "from lot t0 where coalesce((select exists (select 1 from car t1 "
        "where t1.dealer_id = t2.id and t1.seats > ?) from dealer t2 "
        "where t2.id = t0.dealer_id), false)"
    )


def test_each_union_branch_reads_its_own_owner_results() -> None:
    family = _lot_model()
    op = oa.Quantifier("any", "Vehicle.dealer.tags", _element("eq", "a"))
    compiled = compile_read(op, family, POSTGRES, target(family, "Vehicle"))
    branch = (
        "left join dealer t1 on t1.id = t0.dealer_id left join (select t3.id, exists (select 1 "
        "from jsonb_array_elements(case when jsonb_typeof(t3.tags) = ? then t3.tags else "
        "cast(? as jsonb) end) t2 where case when jsonb_typeof(t2.value) = ? then t2.value #>> ? "
        "end = ?) q0 from dealer t3) r0 on r0.id = t1.id where coalesce(r0.q0, false)"
    )
    assert compiled.statement.sql.count(branch) == 2
    assert compiled.statement.binds == ("array", "[]", "string", "{}", "a") * 2


def test_a_match_body_reads_its_own_owner_results() -> None:
    family = _crate_model()
    op = oa.Presence("exists", "Shelf.box", oa.Quantifier("any", "crate.tags", _element("eq", "a")))
    compiled = compile_read(op, family, POSTGRES, target(family, "Shelf"))
    assert compiled.statement.sql.endswith(
        "from shelf t0 where exists (select 1 from box t1 left join crate t2 "
        "on t2.id = t1.crate_id left join (select t4.id, exists (select 1 from "
        "jsonb_array_elements(case when "
        "jsonb_typeof(t4.tags) = ? then t4.tags else cast(? as jsonb) end) t3 where case when "
        "jsonb_typeof(t3.value) = ? then t3.value #>> ? end = ?) q0 from crate t4) r0 on "
        "r0.id = t2.id where t1.id = t0.box_id and coalesce(r0.q0, false))"
    )


def test_a_collection_past_an_unproven_hop_is_confined_and_reads_no_owner_results() -> None:
    family = _document_model(
        _entity("Desk", "spanId", relationships=[_rel("span", "spanId", "Span")]),
        _entity(
            "Span",
            "vehicleId",
            temporality="bitemporal",
            relationships=[_rel("vehicle", "vehicleId", "Vehicle")],
        ),
        {
            "name": "Vehicle",
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [_KEY, _reference("dealerId")],
            "relationships": [_rel("dealer", "dealerId", "Dealer")],
        },
        _concrete("Car", "Vehicle", table="car"),
        _concrete("Bike", "Vehicle", table="bike"),
        _entity("Dealer", members=[_TAGS]),
    )
    op = oa.Quantifier("none", "Desk.span.vehicle.dealer.tags", _element("eq", "a"))
    compiled = compile_read(op, family, POSTGRES, target(family, "Desk"))
    dealer = (
        "select coalesce((select not exists (select 1 from jsonb_array_elements(case when "
        "jsonb_typeof(t{tags}.tags) = ? then t{tags}.tags else cast(? as jsonb) end) t{element} "
        "where case when jsonb_typeof(t{element}.value) = ? then t{element}.value #>> ? end = ?) "
        "from dealer t{tags} where t{tags}.id = t{vehicle}.dealer_id), true) "
    )
    assert compiled.statement.sql.endswith(
        f"from desk t0 left join span t1 on {_SPAN_REACHED} where coalesce(("
        + dealer.format(element=2, tags=3, vehicle=4)
        + f"from bike t4 where t4.id = t1.vehicle_id and {_SPAN_REACHED} union all "
        + dealer.format(element=5, tags=6, vehicle=7)
        + f"from car t7 where t7.id = t1.vehicle_id and {_SPAN_REACHED}), true)"
    )


def test_a_locking_read_locks_only_its_root_beside_owner_results() -> None:
    family = _crate_model()
    op = oa.Quantifier("any", "Shelf.box.crate.tags", _element("eq", "a"))
    compiled = compile_read(
        op, family, POSTGRES, target(family, "Shelf"), limit=3, preference="locking"
    )
    assert compiled.statement.sql.endswith(
        f"{_CRATE_JOINS} left join (select t4.id, exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(t4.tags) = ? then t4.tags else cast(? as jsonb) end) t3 where "
        "case when jsonb_typeof(t3.value) = ? then t3.value #>> ? end = ?) q0 from crate t4) r0 "
        "on r0.id = t2.id where coalesce(r0.q0, false) limit ? for share of t0"
    )


def test_readless_predicate_dml_selects_its_keys_through_owner_results() -> None:
    family = _crate_model()
    op = oa.Quantifier("any", "Shelf.box.crate.tags", _element("eq", "a"))
    compiled = compile_write_predicate(op, family, POSTGRES, target(family, "Shelf"))
    assert compiled.selection
    assert compiled.sql == (
        f"select t0.id {_CRATE_JOINS} left join (select t4.id, exists (select 1 from "
        "jsonb_array_elements(case when jsonb_typeof(t4.tags) = ? then t4.tags else "
        "cast(? as jsonb) end) t3 where case when jsonb_typeof(t3.value) = ? then "
        "t3.value #>> ? end = ?) q0 from crate t4) r0 on r0.id = t2.id where coalesce(r0.q0, false)"
    )


_ELEVATION = oa.Comparison(
    op="greaterThan", subject=oa.FieldSubject("address.geo.elevation"), value=5.0
)


@pytest.mark.parametrize(
    ("op", "family", "root"),
    [
        pytest.param(
            oa.And(
                operands=(
                    _CUSTOMER_NAMED,
                    oa.Comparison(
                        op="greaterThan",
                        subject=oa.FieldSubject("Location.customer.address.geo.elevation"),
                        value=5.0,
                    ),
                )
            ),
            CUSTOMER,
            "Location",
            id="conversion-kept-local",
        ),
        pytest.param(
            oa.And(
                operands=(
                    _CUSTOMER_NAMED,
                    oa.Presence("exists", "Location.customer", _ELEVATION),
                )
            ),
            CUSTOMER,
            "Location",
            id="conversion-in-a-match",
        ),
        pytest.param(
            oa.Quantifier("any", "Shelf.box.crate.scores", _element("greaterThan", 3)),
            _crate_model(),
            "Shelf",
            id="failing-element-confined",
        ),
        pytest.param(
            oa.Comparison(
                op="eq", subject=oa.FieldSubject("Ticket.parking.vehicle.maker"), value="Saab"
            ),
            TRAVERSAL,
            "Ticket",
            id="unproven-hop-confined",
        ),
    ],
)
def test_a_key_selection_evaluates_every_demand_where_a_read_does(
    op: oa.PredicateNode, family: Metamodel, root: str
) -> None:
    # The write selection is planned by the read's own demand planner, so a
    # demand unsafe over a joined row keeps the guard or confinement it keeps
    # in the read rather than a placement of the write's own.
    compiled = compile_write_predicate(op, family, POSTGRES, target(family, root))
    read = compile_read(op, family, POSTGRES, target(family, root))
    assert compiled.selection
    assert compiled.sql.partition(" from ")[2] == read.statement.sql.partition(" from ")[2]
    assert read.statement.binds[len(read.statement.binds) - len(compiled.binds) :] == (
        compiled.binds
    )
