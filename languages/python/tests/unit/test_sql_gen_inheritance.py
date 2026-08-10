"""Inheritance-family read lowering (m-sql "Metamodel-extension lowering").

The 17 in-slice corpus cases (payment/animal for table-per-hierarchy, document
for table-per-concrete-subtype) are the byte-exact acceptance surface
(`test_compile_sweep` / `test_run_sweep`); these unit tests pin the seams the
corpus alone would not isolate as clearly: each tag-predicate bucket in
isolation, bind order, grouping, superset ordering, the two strategies'
familyVariant asymmetry, and the per-branch alias/bind state a
table-per-concrete-subtype `union all` restarts.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

import pytest
from _sql_gen_support import formed, model, target

from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import SqlGenError, compile_read

PAYMENT = model("payment")
ANIMAL = model("animal")
DOCUMENT = model("document")
DOCUMENT_LAYOUT = model("document-layout")
INSTRUMENT = model("instrument")
RATE = model("rate")


def test_narrow_nested_under_a_table_per_concrete_subtype_family_partitions_branches() -> None:
    # A TPCS union evaluates a nested narrow against each concrete branch: the
    # selected branches receive true and every other branch receives false.
    op = oa.Or(
        operands=(
            oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All()),
            oa.Narrow(entity="Document", to=("Memo",), operand=oa.All()),
        )
    )
    compiled = compile_read(op, DOCUMENT, POSTGRES, target(DOCUMENT, "Document"))
    assert compiled.statement.sql.endswith(
        "from invoice t0 where 1 = 1 or 1 = 0 union all "
        "select t0.id, t0.title, t0.folder_id, cast(null as varchar(3)) currency, "
        "cast(null as decimal(18, 2)) amount_due, t0.body, "
        "cast(null as decimal(18, 2)) paid_amount, 'Memo' family_variant "
        "from memo t0 where 1 = 0 or 1 = 1 union all "
        "select t0.id, t0.title, t0.folder_id, t0.currency, "
        "cast(null as decimal(18, 2)) amount_due, cast(null as varchar(64)) body, "
        "t0.paid_amount, 'Receipt' family_variant from receipt t0 where 1 = 0 or 1 = 0"
    )
    assert compiled.statement.binds == ()


def test_tpcs_document_union_decodes_each_branch_before_padding() -> None:
    compiled = compile_read(
        oa.All(),
        DOCUMENT_LAYOUT,
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Publication"),
        result_form="instance",
    )
    assert compiled.structured_column == "payload"
    assert compiled.transform_row(
        {
            "id": 10,
            "payload": {"title": "Systems", "detail": "ISBN-10", "pages": 320},
            "family_variant": "Book",
        }
    ) == {
        "id": 10,
        "title": "Systems",
        "detail": "ISBN-10",
        "pages": 320,
        "familyVariant": "Book",
    }
    assert compiled.transform_row(
        {
            "id": 20,
            "payload": {"title": "Frames", "detail": 850, "minutes": 95},
            "family_variant": "Film",
        }
    ) == {
        "id": 20,
        "title": "Frames",
        "detail": 850,
        "minutes": 95,
        "familyVariant": "Film",
    }
    row_compiled = compile_read(
        oa.All(), DOCUMENT_LAYOUT, POSTGRES, target(DOCUMENT_LAYOUT, "Publication")
    )
    assert (
        row_compiled.transform_row(
            {
                "id": 10,
                "payload": {"title": "Systems", "detail": "ISBN-10", "pages": 320},
                "family_variant": "Book",
            }
        )["minutes"]
        is None
    )

    transform = cast("Any", row_compiled)._transform
    book_only = replace(transform, documents=(transform.documents[0],))
    without_sibling_document_members = replace(row_compiled, _transform=book_only)
    assert without_sibling_document_members.transform_row(
        {
            "id": 20,
            "payload": {"title": "Frames"},
            "family_variant": "Film",
        }
    ) == {
        "id": 20,
        "title": None,
        "detail": None,
        "pages": None,
        "minutes": None,
        "familyVariant": "Film",
    }


def test_tpcs_document_single_branch_projects_and_decodes_its_document() -> None:
    compiled = compile_read(
        oa.Narrow(entity="Publication", to=("Book",), operand=oa.All()),
        DOCUMENT_LAYOUT,
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Publication"),
        result_form="instance",
    )
    assert compiled.statement.sql == "select t0.id, t0.payload from publication_book t0"
    assert compiled.transform_row(
        {
            "id": 10,
            "payload": {"title": "Systems", "detail": "ISBN-10", "pages": 320},
        }
    ) == {"id": 10, "title": "Systems", "detail": "ISBN-10", "pages": 320}


def test_a_narrow_naming_an_undeclared_entity_is_refused() -> None:
    # `validate_operation` runs upstream, so a narrow reaching this compiler is
    # already position-valid; an unresolvable member therefore means the caller
    # skipped that step, and refusing loudly is what keeps it from silently
    # lowering to an empty position.
    op = oa.Narrow(entity="Animal", to=("Unicorn",), operand=oa.All())
    with pytest.raises(SqlGenError, match="names an entity the model does not declare"):
        compile_read(op, ANIMAL, POSTGRES, target(ANIMAL, "Animal"))


def test_tph_tag_predicate_whole_family_root_injects_none() -> None:
    # Reading the abstract root untouched (no narrow) spans the whole shared
    # table: the absence of a tag predicate IS the contract (m-sql).
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, target(PAYMENT, "Payment"))
    assert "where" not in compiled.statement.sql
    assert compiled.statement.binds == ()


def test_tph_tag_predicate_one_concrete_injects_eq() -> None:
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, target(PAYMENT, "CardPayment"))
    assert compiled.statement.sql.endswith("where t0.kind = ?")
    assert compiled.statement.binds == ("card",)


def test_tph_tag_predicate_several_concretes_injects_in_alphabetical_order() -> None:
    # Pet (abstract subtype) resolves to {Cat, Dog} — a PROPER SUBSET of the whole
    # animal table — so it injects `in (...)`, never the whole-family "no tag" form,
    # even though it is reached with no narrow at all.
    compiled = compile_read(oa.All(), ANIMAL, POSTGRES, target(ANIMAL, "Pet"))
    assert compiled.statement.sql.endswith("where t0.kind in (?, ?)")
    assert compiled.statement.binds == ("cat", "dog")


def test_tph_user_predicate_then_tag_binds_user_first() -> None:
    # The injected tag composes via `and` AFTER the user predicate — binds read
    # user-first, then tag (m-sql).
    compiled = compile_read(
        oa.Comparison(op="greaterThan", attr="CardPayment.amount", value=60),
        PAYMENT,
        POSTGRES,
        target(PAYMENT, "CardPayment"),
    )
    assert compiled.statement.sql.endswith("where t0.amount > ? and t0.kind = ?")
    assert compiled.statement.binds == (60, "card")


def test_tph_narrow_to_one_concrete_from_an_abstract_target_still_carries_the_tag() -> None:
    # m-inheritance-012: narrowing the abstract root to ONE concrete still projects
    # the raw discriminator slot (its projection is keyed to `targetEntity` being
    # abstract, never to the narrow's resolved cardinality) and still injects `=`
    # (cardinality-keyed).
    compiled = compile_read(
        oa.Narrow(
            entity="Animal",
            to=("Dog",),
            operand=oa.Comparison(op="greaterThan", attr="Dog.barkVolume", value=3),
        ),
        ANIMAL,
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id, t0.bark_volume "
        "from animal t0 where t0.bark_volume > ? and t0.kind = ?"
    )
    assert compiled.statement.binds == (3, "dog")


def test_tph_grouped_branch_predicates_join_by_or() -> None:
    # m-inheritance-015: an `or` of two narrowed branches groups EACH branch's
    # (predicate AND tag) in parens — no top-level tag at all, since the read's own
    # `targetEntity` (Animal, root) is untouched by any TOP-LEVEL narrow.
    compiled = compile_read(
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
        target(ANIMAL, "Animal"),
    )
    assert compiled.statement.sql.endswith(
        "where (t0.bark_volume > ? and t0.kind = ?) or (t0.indoor = ? and t0.kind = ?)"
    )
    assert compiled.statement.binds == (5, "dog", True, "cat")


def test_tph_heterogeneous_document_predicate_partitions_by_variant() -> None:
    op = oa.Or(
        operands=(
            oa.Narrow(
                entity="Payment",
                to=("CardPayment",),
                operand=oa.Comparison(op="eq", attr="CardPayment.detail", value="visa-4242"),
            ),
            oa.Narrow(
                entity="Payment",
                to=("CashPayment",),
                operand=oa.Comparison(op="greaterThan", attr="CashPayment.detail", value=10.0),
            ),
        )
    )
    compiled = compile_read(
        op,
        DOCUMENT_LAYOUT,
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
    )

    assert " union all " in compiled.statement.sql
    assert compiled.statement.binds == (
        "card",
        "detail",
        "visa-4242",
        "cash",
        "detail",
        Decimal("10.0"),
    )
    card_branch, cash_branch = compiled.statement.sql.split(" union all ")
    assert "from (select * from payment_document t0 where t0.kind = ? offset 0) p1" in card_branch
    assert "cast(" not in card_branch
    assert "from (select * from payment_document t0 where t0.kind = ? offset 0) p2" in cash_branch
    assert "cast(jsonb_extract_path_text" in cash_branch


def test_tph_top_level_narrow_partitions_before_variant_specific_document_cast() -> None:
    compiled = compile_read(
        oa.Narrow(
            entity="Payment",
            to=("CashPayment",),
            operand=oa.Comparison(op="greaterThan", attr="CashPayment.detail", value=10.0),
        ),
        DOCUMENT_LAYOUT,
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
    )

    assert (
        "from (select * from payment_document t0 where t0.kind = ? offset 0) p1"
        in compiled.statement.sql
    )
    assert compiled.statement.sql.endswith(
        "where cast(jsonb_extract_path_text(p1.payload, ?) as decimal(18, 2)) > ?"
    )
    assert compiled.statement.binds == ("cash", "detail", Decimal("10.0"))


def _heterogeneous_payment_predicate() -> oa.Operation:
    return oa.Or(
        operands=(
            oa.Narrow(
                entity="Payment",
                to=("CardPayment",),
                operand=oa.Comparison(op="eq", attr="CardPayment.detail", value="visa-4242"),
            ),
            oa.Narrow(
                entity="Payment",
                to=("CashPayment",),
                operand=oa.Comparison(op="greaterThan", attr="CashPayment.detail", value=10.0),
            ),
        )
    )


def test_tph_document_partition_wraps_result_shaping_around_the_union() -> None:
    op = oa.Limit(
        operand=oa.OrderBy(
            operand=oa.Distinct(operand=_heterogeneous_payment_predicate()),
            keys=(oa.OrderKey(attr="Payment.id", direction="asc"),),
        ),
        count=1,
    )
    compiled = compile_read(op, DOCUMENT_LAYOUT, POSTGRES, target(DOCUMENT_LAYOUT, "Payment"))

    assert compiled.statement.sql.startswith("select distinct u.id, u.kind, u.payload from (")
    assert compiled.statement.sql.endswith("order by u.id asc limit ?")
    assert compiled.statement.binds[-1] == 1


def test_tph_document_partition_locks_base_rows_through_one_outer_read() -> None:
    compiled = compile_read(
        oa.Limit(operand=_heterogeneous_payment_predicate(), count=1),
        DOCUMENT_LAYOUT,
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
        lock="locking",
    )

    assert compiled.statement.sql.count("select ") == 5
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.kind, t0.payload from payment_document t0 join ("
    )
    assert (
        "select p1.id from (select * from payment_document t1 where t1.kind = ? offset 0) p1"
        in (compiled.statement.sql)
    )
    assert compiled.statement.sql.endswith("limit ? for share of t0")
    assert compiled.statement.binds == (
        "card",
        "detail",
        "visa-4242",
        "cash",
        "detail",
        Decimal("10.0"),
        1,
    )


def test_tph_document_materialization_decodes_only_the_tagged_variant_shape() -> None:
    compiled = compile_read(
        oa.All(),
        DOCUMENT_LAYOUT,
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
        result_form="instance",
    )

    assert compiled.transform_row(
        {
            "id": 1,
            "kind": "card",
            "payload": {"detail": "visa-4242", "authorizationCode": "AUTH-7"},
        }
    ) == {
        "id": 1,
        "detail": "visa-4242",
        "authorization_code": "AUTH-7",
        "familyVariant": "CardPayment",
    }
    assert compiled.transform_row({"id": 2, "kind": "cash", "payload": {"detail": "12.50"}}) == {
        "id": 2,
        "detail": Decimal("12.50"),
        "familyVariant": "CashPayment",
    }
    with pytest.raises(SqlGenError, match="names no concrete subtype"):
        compiled.transform_row({"id": 3, "kind": "wire", "payload": {"detail": "x"}})


def test_tph_document_row_projection_pads_members_outside_the_tagged_variant() -> None:
    compiled = compile_read(oa.All(), DOCUMENT_LAYOUT, POSTGRES, target(DOCUMENT_LAYOUT, "Payment"))

    assert compiled.transform_row({"id": 2, "kind": "cash", "payload": {"detail": "12.50"}}) == {
        "id": 2,
        "detail": Decimal("12.50"),
        "authorization_code": None,
        "familyVariant": "CashPayment",
    }


def test_tph_concrete_document_read_uses_only_that_variants_shape() -> None:
    compiled = compile_read(
        oa.All(), DOCUMENT_LAYOUT, POSTGRES, target(DOCUMENT_LAYOUT, "CardPayment")
    )

    assert compiled.transform_row(
        {
            "id": 1,
            "payload": {"detail": "visa-4242", "authorizationCode": "AUTH-7"},
        }
    ) == {"id": 1, "detail": "visa-4242", "authorization_code": "AUTH-7"}


def test_tph_document_family_with_no_resident_members_projects_no_document() -> None:
    from parallax.descriptor._records import (
        Attribute,
        DocumentLayout,
        Entity,
        Inheritance,
        Metamodel,
    )

    root = Entity(
        name="EmptyRoot",
        table="empty_root",
        layout=DocumentLayout(column="payload"),
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    concrete = Entity(
        name="EmptyLeaf",
        inheritance=Inheritance(role="concrete-subtype", parent="EmptyRoot", tag_value="leaf"),
    )
    meta = formed(Metamodel(entities=(root, concrete)))

    compiled = compile_read(oa.All(), meta, POSTGRES, target(meta, "EmptyRoot"))
    assert compiled.statement.sql == "select t0.id, t0.kind from empty_root t0"
    assert compiled.transform_row({"id": 1, "kind": "leaf"}) == {
        "id": 1,
        "familyVariant": "EmptyLeaf",
    }


def test_user_binds_precede_framework_tag_binds() -> None:
    # m-sql "Grouped branch predicates": the tag guard is appended AFTER the branch
    # predicate and "binds read branch-predicate-first then tag". The two top-level
    # paths above already honor it; this pins the THIRD, deepest one — a narrow
    # inside a polymorphic navigation hop, where the guard is injected into a
    # correlated subquery's `where` alongside the interior predicate.
    #
    # This is the shape that regressed: when the guard fragment was built by a
    # bind-as-you-render helper passed as an ARGUMENT to the function that lowers
    # the interior, Python's argument evaluation pushed the tag bind FIRST, so the
    # SQL read `bark_volume = ? and kind = ?` while the binds read `('dog', 5)` —
    # executing as `bark_volume = 'dog' and kind = 5`. Asserting SQL and binds
    # TOGETHER is the point: either half alone stays green under that defect.
    compiled = compile_read(
        oa.Exists(
            rel="Person.animals",
            op=oa.Narrow(
                entity="Animal",
                to=("Dog",),
                operand=oa.Comparison(op="eq", attr="Dog.barkVolume", value=5),
            ),
        ),
        ANIMAL,
        POSTGRES,
        target(ANIMAL, "Person"),
    )
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 "
        "where t1.owner_id = t0.id and t1.bark_volume = ? and t1.kind = ?)"
    )
    assert compiled.statement.binds == (5, "dog")


def test_tph_abstract_superset_projection_follows_shared_table_layout_tiers() -> None:
    # The shared Table Layout's tier order: the `Identity` slot, then the raw
    # `Discriminator` slot, then the `Domain` slots in their stable encounter
    # order — ancestry prefix (Animal's own, then Pet's own) first, never
    # alphabetized across the chain, then each concrete's own block in
    # alphabetical subtype order (Cat before Dog before WildBoar).
    compiled = compile_read(oa.All(), ANIMAL, POSTGRES, target(ANIMAL, "Animal"))
    assert compiled.statement.sql == (
        "select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id, t0.indoor, "
        "t0.bark_volume, t0.tusk_length from animal t0"
    )


def test_tph_narrowed_projection_drops_slots_outside_the_position() -> None:
    # Applicability is the Table Layout's own per-slot answer: narrowing to
    # Cat/Dog keeps every slot applicable to one of them and drops WildBoar's
    # own `tusk_length`, without disturbing the surviving tier order.
    compiled = compile_read(
        oa.Narrow(entity="Animal", to=("Cat", "Dog"), operand=oa.All()),
        ANIMAL,
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id, t0.indoor, "
        "t0.bark_volume from animal t0"
    )
    assert "tusk_length" not in compiled.statement.sql


def test_tph_equivalent_narrow_spellings_collapse() -> None:
    # `to: [Pet]` (the abstract subtype) and `to: [Cat, Dog]` (its explicit concrete
    # descendants) resolve to the same effective set and MUST lower identically,
    # regardless of the authored `to` order or spelling (m-op-algebra / m-sql).
    by_abstract = compile_read(
        oa.Narrow(entity="Animal", to=("Pet",), operand=oa.All()),
        ANIMAL,
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    by_concretes = compile_read(
        oa.Narrow(entity="Animal", to=("Dog", "Cat"), operand=oa.All()),
        ANIMAL,
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    # The LOWERING is what must collapse. `narrow_to` deliberately does not: it
    # reports the narrow the caller AUTHORED, which materialization resolves for
    # itself — so the two compiled reads are compared statement to statement.
    assert by_abstract.statement == by_concretes.statement


def test_tph_narrow_canonical_alphabetical_order_independent_of_authored_order() -> None:
    # The `to` list's authored order never leaks into the lowered `in (...)` list —
    # it is always the family's canonical alphabetical order.
    compiled = compile_read(
        oa.Narrow(entity="Animal", to=("Dog", "Cat"), operand=oa.All()),
        ANIMAL,
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    assert compiled.statement.sql.endswith("where t0.kind in (?, ?)")
    assert compiled.statement.binds == ("cat", "dog")


def test_tpcs_single_concrete_is_an_ordinary_read_no_tag_no_union() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, target(DOCUMENT, "Invoice"))
    assert compiled.statement.sql == (
        "select t0.id, t0.title, t0.folder_id, t0.currency, t0.amount_due from invoice t0"
    )
    assert "union" not in compiled.statement.sql
    assert "family_variant" not in compiled.statement.sql


def test_tpcs_union_all_branch_order_alias_restart_casts_and_literal() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, target(DOCUMENT, "FinancialDocument"))
    branches = compiled.statement.sql.split(" union all ")
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
    assert compiled.statement.binds == ()


def test_tpcs_union_predicate_on_a_sibling_only_member_is_refused() -> None:
    # Resolving a member's column through the branch's own Table Layout makes a
    # branch that does not physically carry it a loud refusal rather than a
    # silent reference to a column that table has no slot for. Position validity
    # is enforced upstream (`m-inheritance-041`), so this is the compiler's own
    # backstop, and the message names the contributor and the branch table.
    with pytest.raises(SqlGenError, match="has no Column in table 'receipt'"):
        compile_read(
            oa.Comparison(op="greaterThan", attr="Invoice.amountDue", value=1),
            DOCUMENT,
            POSTGRES,
            target(DOCUMENT, "FinancialDocument"),
        )


def test_tph_temporal_slots_follow_every_domain_slot_across_ancestry() -> None:
    # Tier order outranks ancestry: the root declares both `price` (Domain) and
    # the four interval Attributes (Temporal), yet the subtypes' own Domain
    # slots — `coupon` (Bond) and `ticker` (Equity) — still precede every
    # root-owned Temporal slot in the shared Table.
    compiled = compile_read(oa.All(), INSTRUMENT, POSTGRES, target(INSTRUMENT, "Instrument"))
    assert compiled.statement.sql == (
        "select t0.id, t0.kind, t0.price, t0.coupon, t0.ticker, "
        "t0.from_z, t0.thru_z, t0.in_z, t0.out_z from instrument t0"
    )


def test_tpcs_union_uses_one_logical_contributor_order_across_branches() -> None:
    # One Position Layout contributor sequence — `Identity`, then `Domain`
    # (root `amount`, then each concrete's own in alphabetical branch order),
    # then the root-owned `Temporal` slots — is shared by both branches, and a
    # branch that does not own a contributor renders the typed `NULL`
    # placeholder in that contributor's own position rather than reordering.
    compiled = compile_read(oa.All(), RATE, POSTGRES, target(RATE, "Rate"))
    branches = compiled.statement.sql.split(" union all ")
    assert branches[0] == (
        "select t0.id, t0.amount, t0.grade, cast(null as decimal(18, 2)) spread, "
        "t0.from_z, t0.thru_z, t0.in_z, t0.out_z, 'DepositRate' family_variant "
        "from deposit_rate t0"
    )
    assert branches[1] == (
        "select t0.id, t0.amount, cast(null as varchar(8)) grade, t0.spread, "
        "t0.from_z, t0.thru_z, t0.in_z, t0.out_z, 'LoanRate' family_variant "
        "from loan_rate t0"
    )


def test_tpcs_single_concrete_projects_its_own_table_layout_tier_order() -> None:
    # The concrete's own Entity Layout view: ancestry `Identity` and `Domain`
    # slots, its own `Domain` slot, then the inherited `Temporal` slots — no
    # discriminator and no variant literal.
    compiled = compile_read(oa.All(), RATE, POSTGRES, target(RATE, "DepositRate"))
    assert compiled.statement.sql == (
        "select t0.id, t0.amount, t0.grade, t0.from_z, t0.thru_z, t0.in_z, t0.out_z "
        "from deposit_rate t0"
    )


def test_tpcs_union_restarts_aliases_per_branch_and_concatenates_binds() -> None:
    # The state invariant behind the union lane: each `union all` branch gets its
    # OWN lowering context, so a branch's nested correlated subquery restarts at
    # `t1` rather than continuing the previous branch's sequence, and the branch
    # bind lists concatenate in the branches' canonical alphabetical order.
    #
    # No corpus table-per-concrete-subtype family declares a relationship on its
    # abstract root, so no goldened case puts a SUBQUERY inside a union branch —
    # this synthetic family is the general witness. (The corpus case above proves
    # only the `t0` base-alias restart, which cannot distinguish a per-branch
    # context from a per-branch alias reset.)
    from parallax.descriptor._records import (
        Attribute,
        DefiningRelationship,
        Entity,
        Inheritance,
        Metamodel,
        RelationshipJoin,
        RelationshipTarget,
    )

    root = Entity(
        name="Doc",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="title", type="string", column="title", max_length=32),
            Attribute(name="ownerId", type="int64", column="owner_id", nullable=True),
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
    invoice = Entity(
        name="Inv",
        table="inv",
        inheritance=Inheritance(role="concrete-subtype", parent="Doc"),
        attributes=(Attribute(name="due", type="int32", column="due"),),
    )
    receipt = Entity(
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
    meta = formed(Metamodel(entities=(root, invoice, receipt, owner)))

    op = oa.And(
        operands=(
            oa.Comparison(op="eq", attr="Doc.title", value="T"),
            oa.Exists(rel="Doc.owner", op=oa.Comparison(op="eq", attr="Owner.name", value="N")),
        )
    )
    compiled = compile_read(op, meta, POSTGRES, target(meta, "Doc"))
    branches = compiled.statement.sql.split(" union all ")
    assert len(branches) == 2
    # BOTH branches restart the whole sequence: base `t0`, hop alias `t1`.
    hop = "exists (select 1 from owner t1 where t1.id = t0.owner_id and t1.name = ?)"
    assert branches[0] == (
        "select t0.id, t0.title, t0.owner_id, t0.due, cast(null as integer) paid, "
        f"'Inv' family_variant from inv t0 where t0.title = ? and {hop}"
    )
    assert branches[1] == (
        "select t0.id, t0.title, t0.owner_id, cast(null as integer) due, t0.paid, "
        f"'Rec' family_variant from rec t0 where t0.title = ? and {hop}"
    )
    # Per-branch binds, concatenated in alphabetical branch order — never merged,
    # deduplicated, or reordered.
    assert compiled.statement.binds == ("T", "N", "T", "N")


def test_tpcs_string_cast_placeholder_diverges_by_declared_length() -> None:
    # The abstract ROOT read pulls in Memo too, whose `body` needs a bounded
    # varchar(64) placeholder on the other two branches, and Memo's own branch
    # NULL-casts the FinancialDocument-only `currency` (varchar(3)).
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, target(DOCUMENT, "Document"))
    assert "cast(null as varchar(64)) body" in compiled.statement.sql
    assert "cast(null as varchar(3)) currency" in compiled.statement.sql


def test_tpcs_equivalent_narrow_spellings_collapse() -> None:
    by_abstract = compile_read(
        oa.Narrow(entity="Document", to=("FinancialDocument",), operand=oa.All()),
        DOCUMENT,
        POSTGRES,
        target(DOCUMENT, "Document"),
    )
    by_concretes = compile_read(
        oa.Narrow(entity="Document", to=("Receipt", "Invoice"), operand=oa.All()),
        DOCUMENT,
        POSTGRES,
        target(DOCUMENT, "Document"),
    )
    assert by_abstract.statement == by_concretes.statement
    # And matches reading the abstract subtype directly, no narrow at all.
    direct = compile_read(oa.All(), DOCUMENT, POSTGRES, target(DOCUMENT, "FinancialDocument"))
    assert by_abstract.statement == direct.statement


def test_tph_nested_narrow_with_a_trivial_branch_needs_no_grouping() -> None:
    # A nested narrow whose own operand is `all` (no extra predicate) lowers to the
    # bare tag fragment alone — a single term needs no disambiguating parens, unlike
    # its sibling branch here, which does compose a predicate with its tag guard.
    compiled = compile_read(
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
        target(ANIMAL, "Animal"),
    )
    assert compiled.statement.sql.endswith("where t0.kind = ? or (t0.indoor = ? and t0.kind = ?)")
    assert compiled.statement.binds == ("dog", True, "cat")


def test_tph_abstract_instance_form_projects_the_value_object_document_last() -> None:
    # No corpus inheritance family combines with a value object; a synthetic family
    # proves the layout tier order: the `Identity` slot, the raw `Discriminator`
    # slot, the `Domain` slot, THEN the `Document` slot, which rides last among
    # ALL columns however early its owner declares it (m-sql *Read projection*).
    from parallax.descriptor._records import (
        Attribute,
        Entity,
        Inheritance,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    meta = formed(Metamodel(entities=(root, leaf)))
    compiled = compile_read(oa.All(), meta, POSTGRES, target(meta, "Root"), result_form="instance")
    assert compiled.statement.sql == "select t0.id, t0.kind, t0.x, t0.meta from root_tbl t0"


# --------------------------------------------------------------------------- #
# `familyVariant` row materialization (`CompiledRead.transform_row`) and the    #
# TPH/TPCS asymmetry behind it. The transform is built at COMPILE time from the #
# very position that decided the projection, so what a caller materializes can  #
# never disagree with what was actually projected.                              #
# --------------------------------------------------------------------------- #
def test_a_concrete_target_read_transforms_rows_by_identity() -> None:
    # No tag column and no variant literal is projected, so there is nothing to
    # materialize — but the row still comes back as a FRESH dict, so the caller
    # need not care which form it got.
    row = {"id": 1, "amount": "100.00", "card_network": "Visa"}
    for concrete_model, name in ((PAYMENT, "CardPayment"), (DOCUMENT, "Invoice")):
        compiled = compile_read(oa.All(), concrete_model, POSTGRES, target(concrete_model, name))
        transformed = compiled.transform_row(row)
        assert transformed == row
        assert transformed is not row


def test_tph_abstract_read_transforms_rows_through_the_tag_map() -> None:
    # The raw tag column is POPPED (it is framework-owned and never reaches the
    # caller) and its value mapped to the declaring concrete's name.
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, target(PAYMENT, "Payment"))
    assert compiled.transform_row({"id": 1, "amount": "100.00", "kind": "card"}) == {
        "id": 1,
        "amount": "100.00",
        "familyVariant": "CardPayment",
    }
    assert compiled.transform_row({"id": 2, "kind": "cash"})["familyVariant"] == "CashPayment"


def test_tph_tag_transform_holds_regardless_of_narrow_cardinality() -> None:
    # m-inheritance-012's own witness: narrowed down to ONE concrete, but the read's
    # OWN targetEntity (Animal) is abstract, so the tag column is still projected
    # and still transformed. The map is the WHOLE family's, not the narrow's
    # resolved position — `WildBoar` is outside the narrow and still maps.
    compiled = compile_read(
        oa.Narrow(entity="Animal", to=("Dog",), operand=oa.All()),
        ANIMAL,
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    assert compiled.transform_row({"id": 1, "kind": "dog"})["familyVariant"] == "Dog"
    assert compiled.transform_row({"id": 2, "kind": "boar"})["familyVariant"] == "WildBoar"


def test_tph_row_tagged_outside_the_composed_family_is_refused_by_name() -> None:
    # A model may compose a family's concrete leaves PARTIALLY (m-inheritance), and
    # an untouched abstract-root read injects no tag predicate (m-sql), so the shared
    # table can hand back a row tagged for a sibling this model never composed. The
    # tag map is the composed family's, so that row maps to nothing — and the refusal
    # names the family, the tag column, the observed value, and the composed tags,
    # rather than surfacing as a bare mapping miss with no diagnosis in it.
    from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel

    root = Entity(
        name="Beast",
        table="beast",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    wolf = Entity(
        name="Wolf",
        inheritance=Inheritance(role="concrete-subtype", parent="Beast", tag_value="wolf"),
        attributes=(Attribute(name="howl", type="string", column="howl", nullable=True),),
    )
    partial = formed(Metamodel(entities=(root, wolf)))
    compiled = compile_read(oa.All(), partial, POSTGRES, target(partial, "Beast"))

    assert compiled.statement.sql == "select t0.id, t0.kind, t0.howl from beast t0"
    wolf_row = compiled.transform_row({"id": 1, "kind": "wolf", "howl": "aooo"})
    assert wolf_row["familyVariant"] == "Wolf"
    with pytest.raises(SqlGenError, match="names no concrete subtype this model composes"):
        compiled.transform_row({"id": 2, "kind": "bear", "howl": None})


def test_tpcs_union_read_renames_the_projected_literal_column() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, target(DOCUMENT, "Document"))
    transformed = compiled.transform_row({"id": 1, "title": "A", "family_variant": "Invoice"})
    assert transformed == {"id": 1, "title": "A", "familyVariant": "Invoice"}
    assert "family_variant" not in transformed


def test_tpcs_union_preserves_qualified_duplicate_variant_identities() -> None:
    from parallax.core.metamodel import EntityIdentity
    from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel

    root = Entity(
        name="Record",
        namespace="catalog",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    archive = Entity(
        name="SharedVariant",
        namespace="archive",
        table="archive_shared",
        inheritance=Inheritance(role="concrete-subtype", parent="catalog.Record"),
        attributes=(Attribute(name="archiveLabel", type="string", column="shared_label"),),
    )
    catalog = Entity(
        name="SharedVariant",
        namespace="catalog",
        table="catalog_shared",
        inheritance=Inheritance(role="concrete-subtype", parent="catalog.Record"),
        attributes=(Attribute(name="catalogLabel", type="string", column="shared_label"),),
    )
    meta = formed(Metamodel(entities=(root, archive, catalog)))
    root_metadata = meta.entity(EntityIdentity("catalog", "Record"))
    assert root_metadata is not None

    compiled = compile_read(oa.All(), meta, POSTGRES, root_metadata)

    assert compiled.statement.sql == (
        "select t0.id, t0.shared_label parallax_attr_0, cast(null as text) "
        "parallax_attr_1, 'archive.SharedVariant' family_variant from archive_shared t0 "
        "union all select t0.id, cast(null as text) parallax_attr_0, t0.shared_label "
        "parallax_attr_1, 'catalog.SharedVariant' family_variant from catalog_shared t0"
    )
    materialized = compiled.materialize_row(
        {
            "id": 1,
            "parallax_attr_0": "archived",
            "parallax_attr_1": None,
            "family_variant": "archive.SharedVariant",
        }
    )
    assert materialized.resolved_entity == EntityIdentity("archive", "SharedVariant")
    assert materialized.family_variant == "archive.SharedVariant"
    assert materialized.values == {"id": 1, "shared_label": "archived"}


def test_tpcs_narrow_to_a_single_concrete_carries_no_family_variant() -> None:
    # The settled asymmetry with table-per-hierarchy (m-sql, explicit): a single
    # resolved concrete has no shared table to discriminate and no sibling branch
    # to distinguish it from, so it projects — and transforms — nothing.
    compiled = compile_read(
        oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All()),
        DOCUMENT,
        POSTGRES,
        target(DOCUMENT, "Document"),
    )
    assert "family_variant" not in compiled.statement.sql
    assert compiled.transform_row({"id": 1, "title": "A"}) == {"id": 1, "title": "A"}


def test_transform_row_accepts_any_mapping_and_always_returns_a_fresh_dict() -> None:
    from types import MappingProxyType

    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, target(PAYMENT, "Payment"))
    source = MappingProxyType({"id": 1, "kind": "card"})
    transformed = compiled.transform_row(source)
    assert isinstance(transformed, dict)
    assert transformed == {"id": 1, "familyVariant": "CardPayment"}
    # Mutating the result must not reach back into the caller's own row.
    transformed["id"] = 99
    assert source["id"] == 1


# --------------------------------------------------------------------------- #
# `CompiledRead.narrow_to`: the root-level authored-narrow a converted row     #
# resolves its own concrete identity through, where a deep-fetch child level   #
# takes its own `FetchLevel.narrow_to` instead. It reports the AUTHORED `to`,  #
# not the resolved effective set — resolution belongs to materialization,      #
# which knows the row.                                                         #
# --------------------------------------------------------------------------- #
def test_narrow_to_is_none_for_a_bare_read() -> None:
    assert (
        compile_read(oa.All(), DOCUMENT, POSTGRES, target(DOCUMENT, "Document")).narrow_to is None
    )


def test_narrow_to_carries_a_top_level_narrows_authored_subtypes() -> None:
    narrowed = oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All())
    assert compile_read(narrowed, DOCUMENT, POSTGRES, target(DOCUMENT, "Document")).narrow_to == (
        "Invoice",
    )


def test_narrow_to_survives_the_directive_peel() -> None:
    # The narrow sits UNDER the result-shaping directives, so it is found by the
    # same peel the lowering itself performs — never by inspecting the outer node.
    # A table-per-hierarchy family carries the directives here: the
    # table-per-concrete-subtype union lane refuses them outright, so it cannot
    # witness this shape at all.
    narrowed = oa.Narrow(entity="Animal", to=("Cat", "Dog"), operand=oa.All())
    op = oa.Limit(operand=oa.OrderBy(operand=narrowed, keys=()), count=1)
    assert compile_read(op, ANIMAL, POSTGRES, target(ANIMAL, "Animal")).narrow_to == ("Cat", "Dog")


def test_a_mid_predicate_narrow_is_not_the_reads_own_narrow() -> None:
    # Only a TOP-LEVEL narrow sets the read's position; one nested inside
    # and/or/not/group is a local branch guard and must not leak into `narrow_to`.
    op = oa.Or(
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
    )
    assert compile_read(op, ANIMAL, POSTGRES, target(ANIMAL, "Animal")).narrow_to is None


# --------------------------------------------------------------------------- #
# A concrete position that itself has concrete descendants. Every branch table  #
# is that branch's OWN concrete's container, never the queried position's — the #
# two are different facts, and for this shape they disagree.                    #
# --------------------------------------------------------------------------- #
def test_a_concrete_position_with_a_concrete_descendant_unions_both_own_tables() -> None:
    from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel

    root = Entity(
        name="Doc",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    parent = Entity(
        name="Parent",
        table="parent_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Doc"),
        attributes=(Attribute(name="note", type="int32", column="note"),),
    )
    child = Entity(
        name="Child",
        table="child_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Parent"),
        attributes=(Attribute(name="extra", type="int32", column="extra"),),
    )
    meta = formed(Metamodel(entities=(root, parent, child)))

    # Reading Parent spans {Child, Parent}: two branches over two OWN tables,
    # each NULL-casting the columns it does not declare. Parent is in its own
    # effective set, so its columns contribute in the member block (canonical
    # order Child, Parent) rather than in the inherited prefix, which carries
    # only the abstract root's own.
    compiled = compile_read(oa.All(), meta, POSTGRES, target(meta, "Parent"))
    assert compiled.statement.sql == (
        "select t0.id, t0.extra, t0.note, 'Child' family_variant from child_tbl t0 "
        "union all "
        "select t0.id, cast(null as integer) extra, t0.note, 'Parent' family_variant "
        "from parent_tbl t0"
    )
    # Reading the leaf resolves to one concrete and reads that concrete's table.
    leaf = compile_read(oa.All(), meta, POSTGRES, target(meta, "Child"))
    assert leaf.statement.sql == "select t0.id, t0.note, t0.extra from child_tbl t0"


def test_family_attribute_resolution_spans_the_roots_projection_superset() -> None:
    # A predicate resolves an attribute reference against the whole family, which
    # is the family root's projection superset: the ancestry prefix plus every
    # concrete's own block. An abstract position with no concrete descendant
    # contributes to no such block, so its own attributes are unreachable — a
    # position no valid read can name, since narrowing to it resolves to the
    # empty set.
    from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel

    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    barren = Entity(
        name="Barren",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
        attributes=(Attribute(name="y", type="int32", column="y"),),
    )
    meta = formed(Metamodel(entities=(root, leaf, barren)))

    # The root's own and the concrete's own both resolve from the concrete target.
    compiled = compile_read(
        oa.Comparison(op="eq", attr="Root.id", value=1), meta, POSTGRES, target(meta, "Leaf")
    )
    assert compiled.statement.sql.endswith("where t0.id = ? and t0.kind = ?")
    with pytest.raises(SqlGenError, match="names no attribute"):
        compile_read(
            oa.Comparison(op="eq", attr="Barren.y", value=1), meta, POSTGRES, target(meta, "Leaf")
        )
