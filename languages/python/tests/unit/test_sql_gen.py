"""SQL read-compiler unit tests (m-sql lowering).

Direct lowering of representative nodes plus every refusal branch this phase
draws: unbound attribute references, the deferred navigation/temporal/array-
traversal nodes, and malformed value-object paths — each a loud
:class:`SqlGenError`, never a silent wrong emission. Inheritance-family read
lowering (table-per-hierarchy tag predicates / abstract-superset projection,
table-per-concrete-subtype union-all) is covered separately, below.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import (
    FamilyVariantPlan,
    SqlGenError,
    Statement,
    compile_read,
    family_variant_plan,
)

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
CUSTOMER = _MODELS["customer"]
PAYMENT = _MODELS["payment"]
ACCOUNT = _MODELS["account"]
ANIMAL = _MODELS["animal"]
DOCUMENT = _MODELS["document"]
PERSON = _MODELS["person"]
POLICY = _MODELS["policy"]


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


def test_nested_null_check_and_membership() -> None:
    is_null = compile_read(
        oa.NestedNullCheck(op="nestedIsNull", path="Customer.address.city"),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    assert "jsonb_extract_path_text(t0.address, ?) is null" in is_null.sql
    membership = compile_read(
        oa.NestedMembership(path="Customer.address.city", values=("Oslo", "Boston")),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    assert membership.sql.endswith("in (?, ?)")
    assert membership.binds == ("city", "Oslo", "Boston")


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


def test_narrow_nested_under_a_table_per_concrete_subtype_family_is_refused() -> None:
    # A narrow reached mid-predicate (nested inside and/or/not/group) is a grouped
    # branch predicate table-per-hierarchy lowers (below); no goldened corpus case
    # nests a narrow under table-per-concrete-subtype, so it refuses loudly rather
    # than guess a shape.
    op = oa.Or(
        operands=(
            oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All()),
            oa.Narrow(entity="Document", to=("Memo",), operand=oa.All()),
        )
    )
    with pytest.raises(SqlGenError, match="table-per-concrete-subtype"):
        compile_read(op, DOCUMENT, POSTGRES, "Document")


def test_malformed_value_object_paths() -> None:
    with pytest.raises(SqlGenError, match=r"needs Class\.valueObject\.attribute"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )
    with pytest.raises(SqlGenError, match="not a declared value object"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.mystery.city", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )
    with pytest.raises(SqlGenError, match="undeclared"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address.mystery", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


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


def test_nested_path_continuing_past_a_scalar_is_refused() -> None:
    with pytest.raises(SqlGenError, match="continues past scalar"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address.city.extra", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


def test_nested_path_ending_on_a_value_object_is_refused() -> None:
    with pytest.raises(SqlGenError, match="does not reach a scalar leaf"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address.geo", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


def test_top_level_many_value_object_any_element_needs_no_path_descent() -> None:
    # A `many` value object declared AT THE TOP LEVEL (the array IS the whole
    # document, not a nested member reached by descending through a `one` VO) is
    # not corpus-covered — customer.yaml's `phones` nests one level under `address`
    # — so this proves the degenerate zero-pre-segment guard: `array_guard` probes
    # the plain column reference directly, no `jsonb_extract_path` call at all.
    from parallax.core.descriptor import (
        Attribute,
        Entity,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    doc = Entity(
        name="Doc",
        table="doc",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="tags",
                column="tags",
                cardinality="many",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    meta = Metamodel(entities=(doc,))
    statement = compile_read(
        oa.NestedComparison(op="nestedEq", path="Doc.tags.label", value="x"),
        meta,
        POSTGRES,
        "Doc",
    )
    assert statement.sql == (
        "select t0.id from doc t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(t0.tags) = ? then t0.tags else cast(? as jsonb) end) "
        "t1 where jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert statement.binds == ("array", "[]", "label", "x")


def test_statement_is_frozen_value() -> None:
    statement = Statement("select 1", (1,))
    assert statement.sql == "select 1"
    assert statement.binds == (1,)


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


# --------------------------------------------------------------------------- #
# Inheritance-family reads (m-sql "Metamodel-extension lowering — inheritance";  #
# COR-3 Phase 7 increment 2). The 17 in-slice corpus cases (payment/animal for  #
# table-per-hierarchy, document for table-per-concrete-subtype) are the byte-  #
# exact acceptance surface (`test_compile_sweep`/`test_run_sweep`); these unit  #
# tests pin the seams the corpus alone would not isolate as clearly: each      #
# tag-predicate bucket in isolation, bind order, grouping, superset ordering,   #
# and the two strategies' familyVariant asymmetry.                            #
# --------------------------------------------------------------------------- #


def test_tph_tag_predicate_whole_family_root_injects_none() -> None:
    # Reading the abstract root untouched (no narrow) spans the whole shared
    # table: the absence of a tag predicate IS the contract (m-sql).
    statement = compile_read(oa.All(), PAYMENT, POSTGRES, "Payment")
    assert "where" not in statement.sql
    assert statement.binds == ()


def test_tph_tag_predicate_one_concrete_injects_eq() -> None:
    statement = compile_read(oa.All(), PAYMENT, POSTGRES, "CardPayment")
    assert statement.sql.endswith("where t0.kind = ?")
    assert statement.binds == ("card",)


def test_tph_tag_predicate_several_concretes_injects_in_alphabetical_order() -> None:
    # Pet (abstract subtype) resolves to {Cat, Dog} — a PROPER SUBSET of the whole
    # animal table — so it injects `in (...)`, never the whole-family "no tag" form,
    # even though it is reached with no narrow at all.
    statement = compile_read(oa.All(), ANIMAL, POSTGRES, "Pet")
    assert statement.sql.endswith("where t0.kind in (?, ?)")
    assert statement.binds == ("cat", "dog")


def test_tph_user_predicate_then_tag_binds_user_first() -> None:
    # The injected tag composes via `and` AFTER the user predicate — binds read
    # user-first, then tag (m-sql).
    statement = compile_read(
        oa.Comparison(op="greaterThan", attr="CardPayment.amount", value=60),
        PAYMENT,
        POSTGRES,
        "CardPayment",
    )
    assert statement.sql.endswith("where t0.amount > ? and t0.kind = ?")
    assert statement.binds == (60, "card")


def test_tph_narrow_to_one_concrete_from_an_abstract_target_still_carries_the_tag() -> None:
    # m-inheritance-012: narrowing the abstract root to ONE concrete still projects
    # the raw tag column (slot 2 is keyed to `targetEntity` being abstract, never to
    # the narrow's resolved cardinality) and still injects `=` (cardinality-keyed).
    statement = compile_read(
        oa.Narrow(
            entity="Animal",
            to=("Dog",),
            operand=oa.Comparison(op="greaterThan", attr="Dog.barkVolume", value=3),
        ),
        ANIMAL,
        POSTGRES,
        "Animal",
    )
    assert statement.sql == (
        "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.bark_volume, t0.kind "
        "from animal t0 where t0.bark_volume > ? and t0.kind = ?"
    )
    assert statement.binds == (3, "dog")


def test_tph_grouped_branch_predicates_join_by_or() -> None:
    # m-inheritance-015: an `or` of two narrowed branches groups EACH branch's
    # (predicate AND tag) in parens — no top-level tag at all, since the read's own
    # `targetEntity` (Animal, root) is untouched by any TOP-LEVEL narrow.
    statement = compile_read(
        oa.Or(
            operands=(
                oa.Narrow(
                    entity="Animal",
                    to=("Dog",),
                    operand=oa.Comparison(op="greaterThan", attr="Dog.barkVolume", value=5),
                ),
                oa.Narrow(
                    entity="Animal",
                    to=("Cat",),
                    operand=oa.Comparison(op="eq", attr="Cat.indoor", value=True),
                ),
            )
        ),
        ANIMAL,
        POSTGRES,
        "Animal",
    )
    assert statement.sql.endswith(
        "where (t0.bark_volume > ? and t0.kind = ?) or (t0.indoor = ? and t0.kind = ?)"
    )
    assert statement.binds == (5, "dog", True, "cat")


def test_tph_abstract_superset_projection_ordering() -> None:
    # Ancestry prefix (Animal's own, then Pet's own) first, never alphabetized
    # across the chain, THEN each concrete's own block in alphabetical subtype
    # order (Cat before Dog before WildBoar), THEN the raw tag column last.
    statement = compile_read(oa.All(), ANIMAL, POSTGRES, "Animal")
    assert statement.sql == (
        "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.indoor, t0.bark_volume, "
        "t0.tusk_length, t0.kind from animal t0"
    )


def test_tph_equivalent_narrow_spellings_collapse() -> None:
    # `to: [Pet]` (the abstract subtype) and `to: [Cat, Dog]` (its explicit concrete
    # descendants) resolve to the same effective set and MUST lower identically,
    # regardless of the authored `to` order or spelling (m-op-algebra / m-sql).
    by_abstract = compile_read(
        oa.Narrow(entity="Animal", to=("Pet",), operand=oa.All()), ANIMAL, POSTGRES, "Animal"
    )
    by_concretes = compile_read(
        oa.Narrow(entity="Animal", to=("Dog", "Cat"), operand=oa.All()), ANIMAL, POSTGRES, "Animal"
    )
    assert by_abstract == by_concretes


def test_tph_narrow_canonical_alphabetical_order_independent_of_authored_order() -> None:
    # The `to` list's authored order never leaks into the lowered `in (...)` list —
    # it is always the family's canonical alphabetical order.
    statement = compile_read(
        oa.Narrow(entity="Animal", to=("Dog", "Cat"), operand=oa.All()), ANIMAL, POSTGRES, "Animal"
    )
    assert statement.sql.endswith("where t0.kind in (?, ?)")
    assert statement.binds == ("cat", "dog")


def test_tpcs_single_concrete_is_an_ordinary_read_no_tag_no_union() -> None:
    statement = compile_read(oa.All(), DOCUMENT, POSTGRES, "Invoice")
    assert statement.sql == (
        "select t0.id, t0.title, t0.folder_id, t0.currency, t0.amount_due from invoice t0"
    )
    assert "union" not in statement.sql
    assert "family_variant" not in statement.sql


def test_tpcs_union_all_branch_order_alias_restart_casts_and_literal() -> None:
    statement = compile_read(oa.All(), DOCUMENT, POSTGRES, "FinancialDocument")
    branches = statement.sql.split(" union all ")
    assert len(branches) == 2
    # Alphabetical branch order (Invoice, Receipt); every branch restarts at `t0`.
    assert branches[0].startswith("select t0.id")
    assert branches[0].endswith("from invoice t0")
    assert branches[1].startswith("select t0.id")
    assert branches[1].endswith("from receipt t0")
    # Each branch NULL-casts the sibling's own column (a decimal placeholder here).
    assert "cast(null as decimal(18, 2)) paid_amount" in branches[0]
    assert "cast(null as decimal(18, 2)) amount_due" in branches[1]
    # Each branch projects its own subtype-name literal, unbound (never a `?`).
    assert branches[0].endswith("'Invoice' family_variant from invoice t0")
    assert branches[1] == (
        "select t0.id, t0.title, t0.folder_id, t0.currency, "
        "cast(null as decimal(18, 2)) amount_due, t0.paid_amount, "
        "'Receipt' family_variant from receipt t0"
    )
    assert statement.binds == ()


def test_tpcs_string_cast_placeholder_diverges_by_declared_length() -> None:
    # The abstract ROOT read pulls in Memo too, whose `body` needs a bounded
    # varchar(64) placeholder on the other two branches, and Memo's own branch
    # NULL-casts the FinancialDocument-only `currency` (varchar(3)).
    statement = compile_read(oa.All(), DOCUMENT, POSTGRES, "Document")
    assert "cast(null as varchar(64)) body" in statement.sql
    assert "cast(null as varchar(3)) currency" in statement.sql


def test_tpcs_equivalent_narrow_spellings_collapse() -> None:
    by_abstract = compile_read(
        oa.Narrow(entity="Document", to=("FinancialDocument",), operand=oa.All()),
        DOCUMENT,
        POSTGRES,
        "Document",
    )
    by_concretes = compile_read(
        oa.Narrow(entity="Document", to=("Receipt", "Invoice"), operand=oa.All()),
        DOCUMENT,
        POSTGRES,
        "Document",
    )
    assert by_abstract == by_concretes
    # And matches reading the abstract subtype directly, no narrow at all.
    direct = compile_read(oa.All(), DOCUMENT, POSTGRES, "FinancialDocument")
    assert by_abstract == direct


def test_tph_nested_narrow_with_a_trivial_branch_needs_no_grouping() -> None:
    # A nested narrow whose own operand is `all` (no extra predicate) lowers to the
    # bare tag fragment alone — a single term needs no disambiguating parens, unlike
    # its sibling branch here, which does compose a predicate with its tag guard.
    statement = compile_read(
        oa.Or(
            operands=(
                oa.Narrow(entity="Animal", to=("Dog",), operand=oa.All()),
                oa.Narrow(
                    entity="Animal",
                    to=("Cat",),
                    operand=oa.Comparison(op="eq", attr="Cat.indoor", value=True),
                ),
            )
        ),
        ANIMAL,
        POSTGRES,
        "Animal",
    )
    assert statement.sql.endswith("where t0.kind = ? or (t0.indoor = ? and t0.kind = ?)")
    assert statement.binds == ("dog", True, "cat")


def test_tph_abstract_instance_form_projects_the_value_object_document_last() -> None:
    # No corpus inheritance family combines with a value object; a synthetic family
    # proves the slot ordering: tag column (m-sql resolved Q6), THEN the value-object
    # document (m-sql *Read projection*: it rides last among ALL columns).
    from parallax.core.descriptor import Attribute, Entity, Inheritance, Metamodel, ValueObject

    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(ValueObject(name="meta", column="meta"),),
    )
    leaf = Entity(
        name="Leaf",
        table="root_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    meta = Metamodel(entities=(root, leaf))
    statement = compile_read(oa.All(), meta, POSTGRES, "Root", result_form="instance")
    assert statement.sql == "select t0.id, t0.x, t0.kind, t0.meta from root_tbl t0"


# --------------------------------------------------------------------------- #
# `familyVariant` materialization plan (engine-facing; the TPH/TPCS asymmetry). #
# --------------------------------------------------------------------------- #
def test_family_variant_plan_is_none_for_a_concrete_target_read() -> None:
    assert family_variant_plan(PAYMENT, "CardPayment", oa.All()) is None
    assert family_variant_plan(DOCUMENT, "Invoice", oa.All()) is None


def test_family_variant_plan_tph_derives_from_the_tag_map() -> None:
    plan = family_variant_plan(PAYMENT, "Payment", oa.All())
    assert plan == FamilyVariantPlan(
        kind="tag", column="kind", tag_map={"card": "CardPayment", "cash": "CashPayment"}
    )


def test_family_variant_plan_tph_holds_regardless_of_narrow_cardinality() -> None:
    # m-inheritance-012's own witness: narrowed down to ONE concrete, but the read's
    # OWN targetEntity (Animal) is abstract, so the plan still applies.
    narrowed = oa.Narrow(entity="Animal", to=("Dog",), operand=oa.All())
    plan = family_variant_plan(ANIMAL, "Animal", narrowed)
    assert plan is not None
    assert plan.kind == "tag"
    assert plan.tag_map is not None
    assert plan.tag_map["dog"] == "Dog"


def test_family_variant_plan_tpcs_is_literal_and_only_for_two_or_more_branches() -> None:
    plan = family_variant_plan(DOCUMENT, "Document", oa.All())
    assert plan == FamilyVariantPlan(kind="literal", column="family_variant")
    # A table-per-concrete-subtype narrow resolving to a SINGLE concrete carries none
    # — the settled asymmetry with table-per-hierarchy (m-sql, explicit).
    narrowed_to_one = oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All())
    assert family_variant_plan(DOCUMENT, "Document", narrowed_to_one) is None


# --------------------------------------------------------------------------- #
# Navigation lowering (m-sql "Joins by navigation"; COR-3 Phase 7 increment 3). #
# These feed already-canonicalized operations directly (the per-hop as-of      #
# rewrite is `parallax.core.navigate`'s job, tested in `test_navigate.py`) —   #
# this module only lowers whatever op-algebra tree it receives.               #
# --------------------------------------------------------------------------- #
def test_navigate_to_many_lowers_to_correlated_exists() -> None:
    op = oa.Navigate(
        rel="Order.items", op=oa.Comparison(op="eq", attr="OrderItem.sku", value="A-100")
    )
    statement = compile_read(op, ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and t1.sku = ?)"
    )
    assert statement.binds == ("A-100",)


def test_exists_with_no_inner_op_is_a_pure_correlation_check() -> None:
    statement = compile_read(oa.Exists(rel="Order.items"), ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id)"
    )
    assert statement.binds == ()


def test_not_exists_negates_the_semi_join() -> None:
    statement = compile_read(oa.NotExists(rel="Order.items"), ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id)"
    )


def test_navigate_composes_inside_the_boolean_algebra() -> None:
    op = oa.And(
        operands=(
            oa.NotExists(rel="Order.items"),
            oa.Comparison(op="eq", attr="Order.active", value=True),
        )
    )
    statement = compile_read(op, ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id) and t0.active = ?"
    )
    assert statement.binds == (True,)


def test_reverse_to_one_navigation_resolves_the_mirror_correlation() -> None:
    op = oa.Navigate(
        rel="OrderItem.order", op=oa.Comparison(op="eq", attr="Order.name", value="Ada")
    )
    statement = compile_read(op, ORDERS, POSTGRES, "OrderItem")
    assert statement.sql.endswith(
        "where exists (select 1 from orders t1 where t1.id = t0.order_id and t1.name = ?)"
    )
    assert statement.binds == ("Ada",)


def test_one_to_one_navigation_lowers_like_any_to_one_hop() -> None:
    op = oa.Navigate(
        rel="Person.passport", op=oa.Comparison(op="eq", attr="Passport.number", value="P-AAA")
    )
    statement = compile_read(op, PERSON, POSTGRES, "Person")
    assert statement.sql.endswith(
        "where exists (select 1 from passport t1 where t1.person_id = t0.id and t1.number = ?)"
    )


def test_nullable_many_to_one_exists_correlates_on_the_owned_fk() -> None:
    statement = compile_read(
        oa.Exists(rel="OrderStatus.orderItem"), ORDERS, POSTGRES, "OrderStatus"
    )
    assert statement.sql.endswith(
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
    statement = compile_read(op, ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith(
        "where exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id and t2.code = ?))"
    )
    assert statement.binds == ("PACKED",)


def test_not_exists_multi_hop_negates_only_the_outer_hop() -> None:
    op = oa.NotExists(rel="Order.items", op=oa.Exists(rel="OrderItem.statuses"))
    statement = compile_read(op, ORDERS, POSTGRES, "Order")
    assert statement.sql.endswith(
        "where not exists (select 1 from order_item t1 where t1.order_id = t0.id and "
        "exists (select 1 from order_status t2 where t2.order_item_id = t1.id))"
    )


# --------------------------------------------------------------------------- #
# Polymorphic navigation lowering (m-sql "Polymorphic navigation lowering").   #
# --------------------------------------------------------------------------- #
def test_tph_abstract_root_relationship_target_injects_no_tag() -> None:
    statement = compile_read(oa.Exists(rel="Person.animals"), ANIMAL, POSTGRES, "Person")
    assert statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id)"
    )


def test_tph_abstract_subtype_relationship_target_injects_the_in_list() -> None:
    statement = compile_read(oa.Exists(rel="Person.pets"), ANIMAL, POSTGRES, "Person")
    assert statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind in (?, ?))"
    )
    assert statement.binds == ("cat", "dog")


def test_tph_relationship_narrow_to_one_concrete_lowers_to_eq() -> None:
    op = oa.Exists(rel="Person.pets", op=oa.Narrow(entity="Pet", to=("Cat",), operand=oa.All()))
    statement = compile_read(op, ANIMAL, POSTGRES, "Person")
    assert statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind = ?)"
    )
    assert statement.binds == ("cat",)


def test_tph_relationship_narrow_to_abstract_subtype_matches_the_broad_relationship() -> None:
    op = oa.Exists(
        rel="Person.animals", op=oa.Narrow(entity="Animal", to=("Pet",), operand=oa.All())
    )
    statement = compile_read(op, ANIMAL, POSTGRES, "Person")
    assert statement.sql.endswith(
        "where exists (select 1 from animal t1 where t1.owner_id = t0.id and t1.kind in (?, ?))"
    )
    assert statement.binds == ("cat", "dog")


def test_tpcs_abstract_root_relationship_target_groups_every_branch_alphabetically() -> None:
    statement = compile_read(oa.Exists(rel="Folder.documents"), DOCUMENT, POSTGRES, "Folder")
    assert statement.sql.endswith(
        "where (exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from memo t2 where t2.folder_id = t0.id) "
        "or exists (select 1 from receipt t3 where t3.folder_id = t0.id))"
    )


def test_tpcs_relationship_narrow_drops_the_excluded_branch_but_keeps_its_alias_slot_free() -> None:
    op = oa.Exists(
        rel="Folder.documents",
        op=oa.Narrow(entity="Document", to=("FinancialDocument",), operand=oa.All()),
    )
    statement = compile_read(op, DOCUMENT, POSTGRES, "Folder")
    assert statement.sql.endswith(
        "where (exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from receipt t2 where t2.folder_id = t0.id))"
    )


def test_tpcs_relationship_narrow_to_a_single_concrete_is_one_exists_no_grouping() -> None:
    # m-sql "a single concrete is one EXISTS (no grouping)" — the TPCS analogue of
    # the TPH narrow-to-one-concrete case above.
    op = oa.Exists(
        rel="Folder.documents", op=oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All())
    )
    statement = compile_read(op, DOCUMENT, POSTGRES, "Folder")
    assert statement.sql.endswith(
        "where exists (select 1 from invoice t1 where t1.folder_id = t0.id)"
    )


# --------------------------------------------------------------------------- #
# To-many value-object array traversal (m-sql "To-many — exists / notExists   #
# and any-element predicates"; COR-3 Phase 7 increment 4). The 8 in-slice     #
# corpus cases (`m-value-object-015..-022`, customer.yaml's `address.phones`) #
# are the byte-exact acceptance surface (`test_compile_sweep`/                #
# `test_run_sweep`); these unit tests isolate seams the corpus alone would    #
# not pin as clearly: the guard fragment's exact shape, alias continuation,   #
# the deliberate absence of a Postgres negation `coalesce`, and paths the     #
# in-slice model does not happen to exercise (an intermediate nested VO       #
# before the `many` hop, and the refusal boundaries either side of the       #
# implemented lowering).                                                     #
# --------------------------------------------------------------------------- #
def test_nested_exists_bare_is_a_non_empty_test_no_where() -> None:
    statement = compile_read(
        oa.NestedExists(path="Customer.address.phones"), CUSTOMER, POSTGRES, "Customer"
    )
    assert statement.sql == (
        "select t0.id, t0.name from customer t0 where exists (select 1 from "
        "jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1)"
    )
    assert statement.binds == ("phones", "array", "phones", "[]")


def test_nested_not_exists_bare_negates_with_no_coalesce() -> None:
    # Postgres `EXISTS` is never NULL — unlike MariaDB's containment form (not
    # implemented; this claim is Postgres-only), the negated bare form needs no
    # `coalesce` wrap at all.
    statement = compile_read(
        oa.NestedNotExists(path="Customer.address.phones"), CUSTOMER, POSTGRES, "Customer"
    )
    assert statement.sql.startswith("select t0.id, t0.name from customer t0 where not exists (")
    assert "coalesce" not in statement.sql
    assert statement.binds == ("phones", "array", "phones", "[]")


def test_nested_exists_scoped_where_reuses_one_alias_for_every_conjunct() -> None:
    # Same-element semantics (m-value-object): every element predicate in the
    # scoped `where` binds the SAME unnested alias — one guard, one FROM clause —
    # never one subquery per conjunct (the any-element flat form's shape, below).
    op = oa.NestedExists(
        path="Customer.address.phones",
        where=oa.And(
            operands=(
                oa.NestedComparison(op="nestedEq", path="type", value="home"),
                oa.NestedComparison(op="nestedEq", path="number", value="555-9999"),
            )
        ),
    )
    statement = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert statement.sql.count("jsonb_array_elements(") == 1  # ONE guarded unnest, not two
    assert statement.sql == (
        "select t0.id, t0.name from customer t0 where exists (select 1 from "
        "jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where "
        "jsonb_extract_path_text(t1.value, ?) = ? and jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert statement.binds == (
        "phones",
        "array",
        "phones",
        "[]",
        "type",
        "home",
        "number",
        "555-9999",
    )


def test_nested_not_exists_scoped_where_negates_the_same_element_check() -> None:
    op = oa.NestedNotExists(
        path="Customer.address.phones",
        where=oa.NestedComparison(op="nestedEq", path="number", value="555-0000"),
    )
    statement = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert statement.sql.startswith("select t0.id, t0.name from customer t0 where not exists (")
    assert "coalesce" not in statement.sql
    assert statement.sql.endswith("where jsonb_extract_path_text(t1.value, ?) = ?)")
    assert statement.binds == ("phones", "array", "phones", "[]", "number", "555-0000")


def test_nested_exists_scoped_where_composes_or_not_and_group() -> None:
    # Not corpus-covered (the 8 in-slice cases only exercise a bare `and`/single
    # leaf inside `where`) — the scoped `elementPredicate` grammar also admits
    # `or`/`not`/`group`, element-relative and same-element exactly like `and`.
    op = oa.NestedExists(
        path="Customer.address.phones",
        where=oa.Group(
            operand=oa.Or(
                operands=(
                    oa.NestedComparison(op="nestedEq", path="type", value="home"),
                    oa.Not(operand=oa.NestedComparison(op="nestedEq", path="type", value="work")),
                )
            )
        ),
    )
    statement = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert statement.sql.endswith(
        "where (jsonb_extract_path_text(t1.value, ?) = ? or "
        "not jsonb_extract_path_text(t1.value, ?) = ?))"
    )
    assert statement.binds == ("phones", "array", "phones", "[]", "type", "home", "type", "work")


def test_flat_any_element_predicates_are_independent_not_same_element() -> None:
    # m-value-object-018's discriminating witness: two ANDed flat predicates
    # through the same `many` member open TWO independent subqueries (t1, t2),
    # each self-guarding — the contrast with the scoped `where` form above, which
    # shares ONE alias across every conjunct.
    op = oa.And(
        operands=(
            oa.NestedComparison(op="nestedEq", path="Customer.address.phones.type", value="home"),
            oa.NestedComparison(
                op="nestedEq", path="Customer.address.phones.number", value="555-9999"
            ),
        )
    )
    statement = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert statement.sql.count("jsonb_array_elements(") == 2  # TWO independent unnests
    assert statement.sql == (
        "select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then "
        "jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where "
        "jsonb_extract_path_text(t1.value, ?) = ?) and exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then "
        "jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t2 where "
        "jsonb_extract_path_text(t2.value, ?) = ?)"
    )
    assert statement.binds == (
        "phones",
        "array",
        "phones",
        "[]",
        "type",
        "home",
        "phones",
        "array",
        "phones",
        "[]",
        "number",
        "555-9999",
    )


def test_flat_any_element_scalar_collapse_uses_the_same_guard_fragment() -> None:
    # The guard fragment is identical regardless of context (bare exists, scoped
    # where, or a flat any-element predicate) — one canonical `<arr>` spelling
    # keyed only to the path, never re-derived per call site.
    guard = (
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end"
    )
    flat = compile_read(
        oa.NestedComparison(op="nestedEq", path="Customer.address.phones.number", value="555-0000"),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    bare = compile_read(
        oa.NestedExists(path="Customer.address.phones"), CUSTOMER, POSTGRES, "Customer"
    )
    assert guard in flat.sql
    assert guard in bare.sql


def test_nested_exists_over_a_one_cardinality_value_object_has_no_lowering_yet() -> None:
    # `geo` is `cardinality: one` — nestedExists over it is schema-legal
    # (m-op-algebra: "the value object at `path` is present (`one`)…") but has no
    # goldened Postgres lowering in this corpus, so it refuses loudly rather than
    # guess a shape.
    with pytest.raises(SqlGenError, match=r"one.*cardinality.*has no goldened lowering yet"):
        compile_read(oa.NestedExists(path="Customer.address.geo"), CUSTOMER, POSTGRES, "Customer")


def test_flat_any_element_ending_on_the_array_itself_is_refused() -> None:
    # `Customer.address.phones` names the array itself, not a field within an
    # element — a flat comparator needs a leaf inside the element.
    with pytest.raises(SqlGenError, match="ends on the `many` array itself"):
        compile_read(
            oa.NestedComparison(op="nestedEq", path="Customer.address.phones", value="x"),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


def test_nested_exists_where_element_relative_unknown_member_is_refused() -> None:
    op = oa.NestedExists(
        path="Customer.address.phones",
        where=oa.NestedComparison(op="nestedEq", path="mystery", value="x"),
    )
    with pytest.raises(SqlGenError, match="undeclared"):
        compile_read(op, CUSTOMER, POSTGRES, "Customer")


def test_nested_exists_path_naming_a_scalar_segment_is_refused() -> None:
    # `city` is a scalar leaf, not a nested value object — a nestedExists path
    # must stay value-object-terminated at every segment.
    with pytest.raises(SqlGenError, match="does not name a nested value object"):
        compile_read(oa.NestedExists(path="Customer.address.city"), CUSTOMER, POSTGRES, "Customer")


def test_many_member_nested_two_levels_deep_binds_every_path_segment_twice() -> None:
    # customer.yaml's `phones` nests directly under the top-level `address` (one
    # segment before the `many` hop); this synthetic model proves the general
    # case — a `many` member reached through an INTERMEDIATE nested `one` value
    # object — composes correctly with the existing extraction machinery: every
    # segment on the path from the document column to the array binds TWICE in
    # the guard, and the field-within-the-element binds once more, after.
    from parallax.core.descriptor import (
        Attribute,
        Entity,
        Metamodel,
        NestedValueObject,
        ValueObject,
        ValueObjectAttribute,
    )

    store = Entity(
        name="Store",
        table="store",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="profile",
                column="profile",
                value_objects=(
                    NestedValueObject(
                        name="shipping",
                        value_objects=(
                            NestedValueObject(
                                name="rates",
                                cardinality="many",
                                attributes=(ValueObjectAttribute(name="zone", type="string"),),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    meta = Metamodel(entities=(store,))

    flat = compile_read(
        oa.NestedComparison(op="nestedEq", path="Store.profile.shipping.rates.zone", value="west"),
        meta,
        POSTGRES,
        "Store",
    )
    assert flat.sql == (
        "select t0.id from store t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.profile, ?, ?)) = ? then "
        "jsonb_extract_path(t0.profile, ?, ?) else cast(? as jsonb) end) t1 where "
        "jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert flat.binds == ("shipping", "rates", "array", "shipping", "rates", "[]", "zone", "west")

    bare_exists = compile_read(
        oa.NestedExists(path="Store.profile.shipping.rates"), meta, POSTGRES, "Store"
    )
    assert bare_exists.binds == ("shipping", "rates", "array", "shipping", "rates", "[]")
