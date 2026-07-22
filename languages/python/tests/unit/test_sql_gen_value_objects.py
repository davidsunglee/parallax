"""Value-object predicate lowering (m-sql / m-value-object).

Flat `nested*` extraction, the to-many array traversal (`nestedExists` /
`nestedNotExists` and the flat any-element form), and every malformed-path
refusal either side of the implemented lowering.

The 8 in-slice corpus cases (`m-value-object-015..-022`, customer.yaml's
`address.phones`) are the byte-exact acceptance surface (`test_compile_sweep` /
`test_run_sweep`); these unit tests isolate seams the corpus alone would not pin
as clearly: the guard fragment's exact shape, alias continuation, the deliberate
absence of a Postgres negation `coalesce`, and paths the in-slice model does not
happen to exercise (an intermediate nested VO before the `many` hop, and a
top-level `many` value object).
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen import SqlGenError, compile_read

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
CUSTOMER = _MODELS["customer"]


def test_nested_null_check_and_membership() -> None:
    is_null = compile_read(
        oa.NestedNullCheck(op="nestedIsNull", path="Customer.address.city"),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    assert "jsonb_extract_path_text(t0.address, ?) is null" in is_null.statement.sql
    membership = compile_read(
        oa.NestedMembership(path="Customer.address.city", values=("Oslo", "Boston")),
        CUSTOMER,
        POSTGRES,
        "Customer",
    )
    assert membership.statement.sql.endswith("in (?, ?)")
    assert membership.statement.binds == ("city", "Oslo", "Boston")


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
                multiplicity="many",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    meta = Metamodel(entities=(doc,))
    compiled = compile_read(
        oa.NestedComparison(op="nestedEq", path="Doc.tags.label", value="x"),
        meta,
        POSTGRES,
        "Doc",
    )
    assert compiled.statement.sql == (
        "select t0.id from doc t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(t0.tags) = ? then t0.tags else cast(? as jsonb) end) "
        "t1 where jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert compiled.statement.binds == ("array", "[]", "label", "x")


# --------------------------------------------------------------------------- #
# To-many value-object array traversal (m-sql "To-many — exists / notExists    #
# and any-element predicates"; COR-3 Phase 7 increment 4).                     #
# --------------------------------------------------------------------------- #
def test_nested_exists_bare_is_a_non_empty_test_no_where() -> None:
    compiled = compile_read(
        oa.NestedExists(path="Customer.address.phones"), CUSTOMER, POSTGRES, "Customer"
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.name from customer t0 where exists (select 1 from "
        "jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1)"
    )
    assert compiled.statement.binds == ("phones", "array", "phones", "[]")


def test_nested_not_exists_bare_negates_with_no_coalesce() -> None:
    # Postgres `EXISTS` is never NULL — unlike MariaDB's containment form (not
    # implemented; this claim is Postgres-only), the negated bare form needs no
    # `coalesce` wrap at all.
    compiled = compile_read(
        oa.NestedNotExists(path="Customer.address.phones"), CUSTOMER, POSTGRES, "Customer"
    )
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.name from customer t0 where not exists ("
    )
    assert "coalesce" not in compiled.statement.sql
    assert compiled.statement.binds == ("phones", "array", "phones", "[]")


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
    compiled = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert compiled.statement.sql.count("jsonb_array_elements(") == 1  # ONE guarded unnest, not two
    assert compiled.statement.sql == (
        "select t0.id, t0.name from customer t0 where exists (select 1 from "
        "jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where "
        "jsonb_extract_path_text(t1.value, ?) = ? and jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert compiled.statement.binds == (
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
    compiled = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.name from customer t0 where not exists ("
    )
    assert "coalesce" not in compiled.statement.sql
    assert compiled.statement.sql.endswith("where jsonb_extract_path_text(t1.value, ?) = ?)")
    assert compiled.statement.binds == ("phones", "array", "phones", "[]", "number", "555-0000")


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
    compiled = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert compiled.statement.sql.endswith(
        "where (jsonb_extract_path_text(t1.value, ?) = ? or "
        "not jsonb_extract_path_text(t1.value, ?) = ?))"
    )
    assert compiled.statement.binds == (
        "phones",
        "array",
        "phones",
        "[]",
        "type",
        "home",
        "type",
        "work",
    )


@pytest.mark.parametrize(
    "node",
    [
        pytest.param(oa.All(), id="all"),
        pytest.param(oa.NoneOp(), id="none"),
        pytest.param(oa.Comparison(op="eq", attr="Customer.name", value="x"), id="comparison"),
        pytest.param(oa.Between(attr="Customer.name", lower="a", upper="b"), id="between"),
        pytest.param(oa.NullCheck(op="isNull", attr="Customer.name"), id="nullCheck"),
        pytest.param(oa.StringMatch(op="like", attr="Customer.name", value="a%"), id="stringMatch"),
        pytest.param(oa.Membership(op="in", attr="Customer.name", values=("a",)), id="membership"),
        pytest.param(oa.NestedExists(path="Customer.address.phones"), id="nestedExists"),
        pytest.param(oa.NestedNotExists(path="Customer.address.phones"), id="nestedNotExists"),
        pytest.param(oa.Narrow(entity="Customer", to=("Customer",), operand=oa.All()), id="narrow"),
        pytest.param(oa.Navigate(rel="Customer.orders"), id="navigate"),
        pytest.param(oa.Exists(rel="Customer.orders"), id="exists"),
        pytest.param(oa.NotExists(rel="Customer.orders"), id="notExists"),
        pytest.param(oa.DeepFetch(operand=oa.All()), id="deepFetch"),
        pytest.param(
            oa.AsOf(operand=oa.All(), dimension="validTime", coordinate="2024-01-01"), id="asOf"
        ),
        pytest.param(oa.Limit(operand=oa.All(), count=1), id="limit"),
        pytest.param(oa.Distinct(operand=oa.All()), id="distinct"),
    ],
)
def test_entity_vocabulary_inside_an_element_where_is_refused_as_one_grammar(
    node: oa.Operation,
) -> None:
    # The element `where` and the entity predicate share ONE dispatcher, so what
    # keeps them different vocabularies is only where the element refusal sits in
    # it — after the shared sub-grammar (`and`/`or`/`not`/`group` and the flat
    # `nested*` family, pinned above), before everything else. Every entity-only
    # node therefore refuses with `elementPredicate`'s single message, NOT with
    # the differentiated deep-fetch / temporal / directive refusals the same node
    # gets at the top level — `m-op-algebra`'s `elementPredicate` is one named
    # production, so what an element `where` gets wrong is always the same thing.
    with pytest.raises(SqlGenError, match=r"is not a legal nestedExists/nestedNotExists element"):
        compile_read(
            oa.NestedExists(path="Customer.address.phones", where=node),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


def test_element_where_refusal_names_the_offending_node_not_its_parent() -> None:
    # Reached through the shared combinators: the refusal reports the INNER node,
    # which is what makes the boundary readable when a `where` is a compound.
    with pytest.raises(SqlGenError, match=r"^Comparison\(op='eq', attr='Customer\.name'"):
        compile_read(
            oa.NestedExists(
                path="Customer.address.phones",
                where=oa.And(
                    operands=(
                        oa.NestedComparison(op="nestedEq", path="type", value="home"),
                        oa.Comparison(op="eq", attr="Customer.name", value="x"),
                    )
                ),
            ),
            CUSTOMER,
            POSTGRES,
            "Customer",
        )


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
    compiled = compile_read(op, CUSTOMER, POSTGRES, "Customer")
    assert compiled.statement.sql.count("jsonb_array_elements(") == 2  # TWO independent unnests
    assert compiled.statement.sql == (
        "select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then "
        "jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where "
        "jsonb_extract_path_text(t1.value, ?) = ?) and exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then "
        "jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t2 where "
        "jsonb_extract_path_text(t2.value, ?) = ?)"
    )
    assert compiled.statement.binds == (
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
    assert guard in flat.statement.sql
    assert guard in bare.statement.sql


def test_nested_exists_over_a_one_multiplicity_value_object_has_no_lowering_yet() -> None:
    # `geo` is `cardinality: one` — nestedExists over it is schema-legal
    # (m-op-algebra: "the value object at `path` is present (`one`)…") but has no
    # goldened Postgres lowering in this corpus, so it refuses loudly rather than
    # guess a shape.
    with pytest.raises(SqlGenError, match=r"one.*multiplicity.*has no goldened lowering yet"):
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
                                multiplicity="many",
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
    assert flat.statement.sql == (
        "select t0.id from store t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.profile, ?, ?)) = ? then "
        "jsonb_extract_path(t0.profile, ?, ?) else cast(? as jsonb) end) t1 where "
        "jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert flat.statement.binds == (
        "shipping",
        "rates",
        "array",
        "shipping",
        "rates",
        "[]",
        "zone",
        "west",
    )

    bare_exists = compile_read(
        oa.NestedExists(path="Store.profile.shipping.rates"), meta, POSTGRES, "Store"
    )
    assert bare_exists.statement.binds == ("shipping", "rates", "array", "shipping", "rates", "[]")
