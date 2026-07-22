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

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import SqlGenError, compile_read

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
PAYMENT = _MODELS["payment"]
ANIMAL = _MODELS["animal"]
DOCUMENT = _MODELS["document"]


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


def test_tph_tag_predicate_whole_family_root_injects_none() -> None:
    # Reading the abstract root untouched (no narrow) spans the whole shared
    # table: the absence of a tag predicate IS the contract (m-sql).
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, "Payment")
    assert "where" not in compiled.statement.sql
    assert compiled.statement.binds == ()


def test_tph_tag_predicate_one_concrete_injects_eq() -> None:
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, "CardPayment")
    assert compiled.statement.sql.endswith("where t0.kind = ?")
    assert compiled.statement.binds == ("card",)


def test_tph_tag_predicate_several_concretes_injects_in_alphabetical_order() -> None:
    # Pet (abstract subtype) resolves to {Cat, Dog} — a PROPER SUBSET of the whole
    # animal table — so it injects `in (...)`, never the whole-family "no tag" form,
    # even though it is reached with no narrow at all.
    compiled = compile_read(oa.All(), ANIMAL, POSTGRES, "Pet")
    assert compiled.statement.sql.endswith("where t0.kind in (?, ?)")
    assert compiled.statement.binds == ("cat", "dog")


def test_tph_user_predicate_then_tag_binds_user_first() -> None:
    # The injected tag composes via `and` AFTER the user predicate — binds read
    # user-first, then tag (m-sql).
    compiled = compile_read(
        oa.Comparison(op="greaterThan", attr="CardPayment.amount", value=60),
        PAYMENT,
        POSTGRES,
        "CardPayment",
    )
    assert compiled.statement.sql.endswith("where t0.amount > ? and t0.kind = ?")
    assert compiled.statement.binds == (60, "card")


def test_tph_narrow_to_one_concrete_from_an_abstract_target_still_carries_the_tag() -> None:
    # m-inheritance-012: narrowing the abstract root to ONE concrete still projects
    # the raw tag column (slot 2 is keyed to `targetEntity` being abstract, never to
    # the narrow's resolved cardinality) and still injects `=` (cardinality-keyed).
    compiled = compile_read(
        oa.Narrow(
            entity="Animal",
            to=("Dog",),
            operand=oa.Comparison(op="greaterThan", attr="Dog.barkVolume", value=3),
        ),
        ANIMAL,
        POSTGRES,
        "Animal",
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.bark_volume, t0.kind "
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
        "Animal",
    )
    assert compiled.statement.sql.endswith(
        "where (t0.bark_volume > ? and t0.kind = ?) or (t0.indoor = ? and t0.kind = ?)"
    )
    assert compiled.statement.binds == (5, "dog", True, "cat")


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
        "Person",
    )
    assert compiled.statement.sql.endswith(
        "where exists (select 1 from animal t1 "
        "where t1.owner_id = t0.id and t1.bark_volume = ? and t1.kind = ?)"
    )
    assert compiled.statement.binds == (5, "dog")


def test_tph_abstract_superset_projection_ordering() -> None:
    # Ancestry prefix (Animal's own, then Pet's own) first, never alphabetized
    # across the chain, THEN each concrete's own block in alphabetical subtype
    # order (Cat before Dog before WildBoar), THEN the raw tag column last.
    compiled = compile_read(oa.All(), ANIMAL, POSTGRES, "Animal")
    assert compiled.statement.sql == (
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
    # The LOWERING is what must collapse. `narrow_to` deliberately does not: it
    # reports the narrow the caller AUTHORED, which materialization resolves for
    # itself — so the two compiled reads are compared statement to statement.
    assert by_abstract.statement == by_concretes.statement


def test_tph_narrow_canonical_alphabetical_order_independent_of_authored_order() -> None:
    # The `to` list's authored order never leaks into the lowered `in (...)` list —
    # it is always the family's canonical alphabetical order.
    compiled = compile_read(
        oa.Narrow(entity="Animal", to=("Dog", "Cat"), operand=oa.All()), ANIMAL, POSTGRES, "Animal"
    )
    assert compiled.statement.sql.endswith("where t0.kind in (?, ?)")
    assert compiled.statement.binds == ("cat", "dog")


def test_tpcs_single_concrete_is_an_ordinary_read_no_tag_no_union() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, "Invoice")
    assert compiled.statement.sql == (
        "select t0.id, t0.title, t0.folder_id, t0.currency, t0.amount_due from invoice t0"
    )
    assert "union" not in compiled.statement.sql
    assert "family_variant" not in compiled.statement.sql


def test_tpcs_union_all_branch_order_alias_restart_casts_and_literal() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, "FinancialDocument")
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
    from parallax.core.descriptor import (
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
    meta = Metamodel(entities=(root, invoice, receipt, owner))

    op = oa.And(
        operands=(
            oa.Comparison(op="eq", attr="Doc.title", value="T"),
            oa.Exists(rel="Doc.owner", op=oa.Comparison(op="eq", attr="Owner.name", value="N")),
        )
    )
    compiled = compile_read(op, meta, POSTGRES, "Doc")
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
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, "Document")
    assert "cast(null as varchar(64)) body" in compiled.statement.sql
    assert "cast(null as varchar(3)) currency" in compiled.statement.sql


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
    assert by_abstract.statement == by_concretes.statement
    # And matches reading the abstract subtype directly, no narrow at all.
    direct = compile_read(oa.All(), DOCUMENT, POSTGRES, "FinancialDocument")
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
        "Animal",
    )
    assert compiled.statement.sql.endswith("where t0.kind = ? or (t0.indoor = ? and t0.kind = ?)")
    assert compiled.statement.binds == ("dog", True, "cat")


def test_tph_abstract_instance_form_projects_the_value_object_document_last() -> None:
    # No corpus inheritance family combines with a value object; a synthetic family
    # proves the slot ordering: tag column (m-sql resolved Q6), THEN the value-object
    # document (m-sql *Read projection*: it rides last among ALL columns).
    from parallax.core.descriptor import Attribute, Entity, Inheritance, Metamodel, ValueObject

    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(ValueObject(name="meta", column="meta"),),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    meta = Metamodel(entities=(root, leaf))
    compiled = compile_read(oa.All(), meta, POSTGRES, "Root", result_form="instance")
    assert compiled.statement.sql == "select t0.id, t0.x, t0.kind, t0.meta from root_tbl t0"


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
    for meta, target in ((PAYMENT, "CardPayment"), (DOCUMENT, "Invoice")):
        compiled = compile_read(oa.All(), meta, POSTGRES, target)
        transformed = compiled.transform_row(row)
        assert transformed == row
        assert transformed is not row


def test_tph_abstract_read_transforms_rows_through_the_tag_map() -> None:
    # The raw tag column is POPPED (it is framework-owned and never reaches the
    # caller) and its value mapped to the declaring concrete's name.
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, "Payment")
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
        oa.Narrow(entity="Animal", to=("Dog",), operand=oa.All()), ANIMAL, POSTGRES, "Animal"
    )
    assert compiled.transform_row({"id": 1, "kind": "dog"})["familyVariant"] == "Dog"
    assert compiled.transform_row({"id": 2, "kind": "boar"})["familyVariant"] == "WildBoar"


def test_tpcs_union_read_renames_the_projected_literal_column() -> None:
    compiled = compile_read(oa.All(), DOCUMENT, POSTGRES, "Document")
    transformed = compiled.transform_row({"id": 1, "title": "A", "family_variant": "Invoice"})
    assert transformed == {"id": 1, "title": "A", "familyVariant": "Invoice"}
    assert "family_variant" not in transformed


def test_tpcs_narrow_to_a_single_concrete_carries_no_family_variant() -> None:
    # The settled asymmetry with table-per-hierarchy (m-sql, explicit): a single
    # resolved concrete has no shared table to discriminate and no sibling branch
    # to distinguish it from, so it projects — and transforms — nothing.
    compiled = compile_read(
        oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All()),
        DOCUMENT,
        POSTGRES,
        "Document",
    )
    assert "family_variant" not in compiled.statement.sql
    assert compiled.transform_row({"id": 1, "title": "A"}) == {"id": 1, "title": "A"}


def test_transform_row_accepts_any_mapping_and_always_returns_a_fresh_dict() -> None:
    from types import MappingProxyType

    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, "Payment")
    source = MappingProxyType({"id": 1, "kind": "card"})
    transformed = compiled.transform_row(source)
    assert isinstance(transformed, dict)
    assert transformed == {"id": 1, "familyVariant": "CardPayment"}
    # Mutating the result must not reach back into the caller's own row.
    transformed["id"] = 99
    assert source["id"] == 1


# --------------------------------------------------------------------------- #
# `CompiledRead.narrow_to` (S3, COR-3 Phase 7 increment 7 round-2): the        #
# root-level authored-narrow a find executor threads into                     #
# `Assembler.materialize_root` the same way a deep-fetch child level's own    #
# `FetchLevel.narrow_to` already threads through `attach_level`. It reports   #
# the AUTHORED `to`, not the resolved effective set — resolution belongs to   #
# materialization, which knows the row.                                       #
# --------------------------------------------------------------------------- #
def test_narrow_to_is_none_for_a_bare_read() -> None:
    assert compile_read(oa.All(), DOCUMENT, POSTGRES, "Document").narrow_to is None


def test_narrow_to_carries_a_top_level_narrows_authored_subtypes() -> None:
    narrowed = oa.Narrow(entity="Document", to=("Invoice",), operand=oa.All())
    assert compile_read(narrowed, DOCUMENT, POSTGRES, "Document").narrow_to == ("Invoice",)


def test_narrow_to_survives_the_directive_peel() -> None:
    # The narrow sits UNDER the result-shaping directives, so it is found by the
    # same peel the lowering itself performs — never by inspecting the outer node.
    # A table-per-hierarchy family carries the directives here: the
    # table-per-concrete-subtype union lane refuses them outright, so it cannot
    # witness this shape at all.
    narrowed = oa.Narrow(entity="Animal", to=("Cat", "Dog"), operand=oa.All())
    op = oa.Limit(operand=oa.OrderBy(operand=narrowed, keys=()), count=1)
    assert compile_read(op, ANIMAL, POSTGRES, "Animal").narrow_to == ("Cat", "Dog")


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
    assert compile_read(op, ANIMAL, POSTGRES, "Animal").narrow_to is None
