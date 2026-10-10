"""Value-object predicate lowering (m-sql / m-value-object).

Dotted value-object field extraction, the to-many array traversal a
quantifier opens, single value-object presence, and every malformed-path
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

from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.object_query import History
from parallax.core.predicate import ModelRejectedError
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import formed, model, target

CUSTOMER = model("customer")


def test_dotted_null_check_and_membership() -> None:
    is_null = compile_read(
        oa.NullCheck(op="isNull", subject=oa.FieldSubject("Customer.address.city")),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert "jsonb_extract_path_text(t0.address, ?) is null" in is_null.statement.sql
    membership = compile_read(
        oa.Membership(
            op="in", subject=oa.FieldSubject("Customer.address.city"), values=("Oslo", "Boston")
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert membership.statement.sql.endswith("in (?, ?)")
    assert membership.statement.binds == ("city", "Oslo", "Boston")


def test_a_dotted_range_lowers_to_one_between_with_the_typed_cast() -> None:
    # ONE `between` with the leaf's cast applied once, binding the path then `lower`
    # then `upper` — never two comparisons, which through a `many` member would be a
    # different predicate (m-predicate).
    compiled = compile_read(
        oa.Range(subject=oa.FieldSubject("Customer.address.geo.elevation"), lower=5, upper=12),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.name from customer t0 where "
        "cast(jsonb_extract_path_text(t0.address, ?, ?) as double precision) between ? and ?"
    )
    assert compiled.statement.binds == ("geo", "elevation", 5, 12)


def test_dotted_negated_membership_lowers_to_a_leading_not_with_no_extra_bind() -> None:
    # The corpus negation form: a LEADING `not` over the identical `in (…)` fragment
    # the positive tag emits, with the same bind list (m-sql).
    positive = compile_read(
        oa.Membership(op="in", subject=oa.FieldSubject("Customer.address.city"), values=("Oslo",)),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    negated = compile_read(
        oa.Membership(
            op="notIn", subject=oa.FieldSubject("Customer.address.city"), values=("Oslo",)
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    where = "where jsonb_extract_path_text(t0.address, ?) in (?)"
    assert positive.statement.sql.endswith(where)
    assert negated.statement.sql.endswith(f"where not {where.removeprefix('where ')}")
    assert negated.statement.binds == positive.statement.binds == ("city", "Oslo")


def test_a_range_inside_a_quantifier_binds_one_element() -> None:
    # The WHOLE range rides one element predicate on one alias, so a single
    # element must satisfy both bounds.
    compiled = compile_read(
        oa.Quantifier(
            "any",
            "Customer.address.phones",
            oa.Range(subject=oa.FieldSubject("number"), lower="555-0000", upper="555-1234"),
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert compiled.statement.sql.count("jsonb_array_elements(") == 1
    assert compiled.statement.sql.endswith(
        "where jsonb_extract_path_text(t1.value, ?) between ? and ?)"
    )
    assert compiled.statement.binds == (
        "phones",
        "array",
        "phones",
        "[]",
        "number",
        "555-0000",
        "555-1234",
    )


def test_range_and_negated_membership_lower_inside_a_quantifier() -> None:
    # The element scope reaches the same two arms through the ONE dispatcher: the
    # element-relative path resolves against the unnested alias, and both new nodes
    # join the equality conjunct on that same alias (same-element).
    op = oa.Quantifier(
        "any",
        path="Customer.address.phones",
        where=oa.And(
            operands=(
                oa.Range(subject=oa.FieldSubject("number"), lower="555-9000", upper="555-9999"),
                oa.Membership(op="notIn", subject=oa.FieldSubject("type"), values=("work",)),
            )
        ),
    )
    compiled = compile_read(op, CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))
    assert compiled.statement.sql.count("jsonb_array_elements(") == 1
    assert compiled.statement.sql.endswith(
        "where jsonb_extract_path_text(t1.value, ?) between ? and ? "
        "and not jsonb_extract_path_text(t1.value, ?) in (?))"
    )
    assert compiled.statement.binds == (
        "phones",
        "array",
        "phones",
        "[]",
        "number",
        "555-9000",
        "555-9999",
        "type",
        "work",
    )


@pytest.mark.parametrize(
    ("tag", "value", "expected_fragment", "expected_pattern"),
    [
        ("like", "Os%", "like ?", "Os%"),
        ("notLike", "Os%", "not like ?", "Os%"),
        ("startsWith", "Os", "like ?", "Os%"),
        ("endsWith", "lo", "like ?", "%lo"),
        ("contains", "sl", "like ?", "%sl%"),
    ],
)
def test_dotted_string_predicates_reuse_the_scalar_pattern_rules(
    tag: oa.StringOp, value: str, expected_fragment: str, expected_pattern: str
) -> None:
    # `like`/`notLike` bind the pattern verbatim while the affix forms
    # derive it; the negation is INFIX (the normalizer's fixed point for `like`),
    # unlike the leading `not` membership and presence tests take. No cast is applied
    # — the leaf is a String member by the non-string-member rule.
    compiled = compile_read(
        oa.StringMatch(op=tag, subject=oa.FieldSubject("Customer.address.city"), value=value),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert compiled.statement.sql.endswith(
        f"where jsonb_extract_path_text(t0.address, ?) {expected_fragment}"
    )
    assert compiled.statement.binds == ("city", expected_pattern)


def test_a_dotted_affix_pattern_escapes_only_when_the_literal_carries_a_wildcard() -> None:
    # The `escape ?` clause and its second bind ride the escaping, not the affix form:
    # a literal whose wildcards needed no escaping emits neither.
    escaped = compile_read(
        oa.StringMatch(
            op="contains", subject=oa.FieldSubject("Customer.address.street"), value="50%"
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert escaped.statement.sql.endswith("like ? escape ?")
    assert escaped.statement.binds == ("street", "%50\\%%", "\\")
    plain = compile_read(
        oa.StringMatch(
            op="contains", subject=oa.FieldSubject("Customer.address.street"), value="50"
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert plain.statement.sql.endswith("like ?")
    assert plain.statement.binds == ("street", "%50%")


def test_a_case_insensitive_dotted_string_predicate_folds_both_sides() -> None:
    compiled = compile_read(
        oa.StringMatch(
            op="like",
            subject=oa.FieldSubject("Customer.address.city"),
            value="OSLO",
            case_insensitive=True,
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert compiled.statement.sql.endswith(
        "where lower(jsonb_extract_path_text(t0.address, ?)) like lower(?)"
    )
    assert compiled.statement.binds == ("city", "OSLO")


def test_string_predicates_lower_inside_a_quantifier() -> None:
    # Alone, the pattern rides the element alias; beside an equality it joins it
    # on the SAME alias.
    any_element = compile_read(
        oa.Quantifier(
            "any",
            "Customer.address.phones",
            oa.StringMatch(op="startsWith", subject=oa.FieldSubject("number"), value="555-1"),
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert any_element.statement.sql.endswith("where jsonb_extract_path_text(t1.value, ?) like ?)")
    assert any_element.statement.binds == ("phones", "array", "phones", "[]", "number", "555-1%")
    scoped = compile_read(
        oa.Quantifier(
            "any",
            path="Customer.address.phones",
            where=oa.And(
                operands=(
                    oa.Comparison(op="eq", subject=oa.FieldSubject("type"), value="home"),
                    oa.StringMatch(op="endsWith", subject=oa.FieldSubject("number"), value="9999"),
                )
            ),
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert scoped.statement.sql.count("jsonb_array_elements(") == 1
    assert scoped.statement.sql.endswith(
        "where jsonb_extract_path_text(t1.value, ?) = ? "
        "and jsonb_extract_path_text(t1.value, ?) like ?)"
    )
    assert scoped.statement.binds == (
        "phones",
        "array",
        "phones",
        "[]",
        "type",
        "home",
        "number",
        "%9999",
    )


def test_malformed_value_object_paths() -> None:
    with pytest.raises(ModelRejectedError):
        compile_read(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Customer.address"), value="x"),
            CUSTOMER,
            POSTGRES,
            target(CUSTOMER, "Customer"),
        )
    with pytest.raises(ModelRejectedError):
        compile_read(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Customer.mystery.city"), value="x"),
            CUSTOMER,
            POSTGRES,
            target(CUSTOMER, "Customer"),
        )
    with pytest.raises(ModelRejectedError):
        compile_read(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Customer.address.mystery"), value="x"),
            CUSTOMER,
            POSTGRES,
            target(CUSTOMER, "Customer"),
        )


def test_a_path_continuing_past_a_scalar_is_refused() -> None:
    with pytest.raises(ModelRejectedError):
        compile_read(
            oa.Comparison(
                op="eq", subject=oa.FieldSubject("Customer.address.city.extra"), value="x"
            ),
            CUSTOMER,
            POSTGRES,
            target(CUSTOMER, "Customer"),
        )


def test_a_path_ending_on_a_value_object_is_refused() -> None:
    with pytest.raises(ModelRejectedError):
        compile_read(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Customer.address.geo"), value="x"),
            CUSTOMER,
            POSTGRES,
            target(CUSTOMER, "Customer"),
        )


def test_document_slots_stay_atomic_and_follow_every_scalar_tier() -> None:
    # A top-level Value Object occupies ONE `Document` slot however early its
    # owner declares it: the layout's `Document` tier follows every scalar tier,
    # so an instance-form read projects `t0.address` whole after the Temporal
    # slots even though `address` is declared before them, and its nested fields
    # contribute no column of their own.
    from parallax.descriptor._records import (
        AsOfAxisMetadata,
        Attribute,
        Entity,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    site = Entity(
        name="Site",
        table="site",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="txStart", type="timestamp", column="in_z"),
            Attribute(name="txEnd", type="timestamp", column="out_z"),
            Attribute(name="label", type="string", column="label"),
        ),
        value_objects=(
            ValueObject(
                name="address",
                column="address",
                attributes=(ValueObjectAttribute(name="city", type="string"),),
            ),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="txStart", end_attribute="txEnd"
            ),
        ),
    )
    meta = formed(Metamodel(entities=(site,)))
    instance = compile_read(
        oa.TrueNode(),
        meta,
        POSTGRES,
        target(meta, "Site"),
        temporal={"transaction-time": History()},
        result_form="instance",
    )
    assert instance.statement.sql == (
        "select t0.id, t0.label, t0.in_z, t0.out_z, not t0.address is null, t0.address from site t0"
    )
    row_form = compile_read(
        oa.TrueNode(),
        meta,
        POSTGRES,
        target(meta, "Site"),
        temporal={"transaction-time": History()},
    )
    assert row_form.statement.sql == "select t0.id, t0.label, t0.in_z, t0.out_z from site t0"


def test_a_top_level_many_value_object_quantifier_needs_no_path_descent() -> None:
    # A `many` value object declared AT THE TOP LEVEL (the array IS the whole
    # document, not a nested member reached by descending through a `one` VO) is
    # not corpus-covered — customer.yaml's `phones` nests one level under `address`
    # — so this proves the degenerate zero-pre-segment guard: `array_guard` probes
    # the plain column reference directly, no `jsonb_extract_path` call at all.
    from parallax.descriptor._records import (
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
    meta = formed(Metamodel(entities=(doc,)))
    compiled = compile_read(
        oa.Quantifier(
            "any", "Doc.tags", oa.Comparison(op="eq", subject=oa.FieldSubject("label"), value="x")
        ),
        meta,
        POSTGRES,
        target(meta, "Doc"),
    )
    assert compiled.statement.sql == (
        "select t0.id from doc t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(t0.tags) = ? then t0.tags else cast(? as jsonb) end) "
        "t1 where jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert compiled.statement.binds == ("array", "[]", "label", "x")


# --------------------------------------------------------------------------- #
# To-many value-object array traversal (m-sql quantifier lowering).           #
# --------------------------------------------------------------------------- #
def test_a_bare_any_is_a_non_empty_test_no_where() -> None:
    compiled = compile_read(
        oa.Quantifier("any", path="Customer.address.phones"),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.name from customer t0 where exists (select 1 from "
        "jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1)"
    )
    assert compiled.statement.binds == ("phones", "array", "phones", "[]")


def test_a_bare_none_negates_with_no_coalesce() -> None:
    # Postgres `EXISTS` is never NULL — unlike MariaDB's containment form (not
    # implemented; this claim is Postgres-only), the negated bare form needs no
    # `coalesce` wrap at all.
    compiled = compile_read(
        oa.Quantifier("none", path="Customer.address.phones"),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.name from customer t0 where not exists ("
    )
    assert "coalesce" not in compiled.statement.sql
    assert compiled.statement.binds == ("phones", "array", "phones", "[]")


def test_one_quantifier_where_reuses_one_alias_for_every_conjunct() -> None:
    # Same-element semantics (m-value-object): every element predicate in the
    # quantifier's `where` binds the SAME unnested alias — one guard, one FROM
    # clause — never one subquery per conjunct (two quantifiers' shape, below).
    op = oa.Quantifier(
        "any",
        path="Customer.address.phones",
        where=oa.And(
            operands=(
                oa.Comparison(op="eq", subject=oa.FieldSubject("type"), value="home"),
                oa.Comparison(op="eq", subject=oa.FieldSubject("number"), value="555-9999"),
            )
        ),
    )
    compiled = compile_read(op, CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))
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


def test_none_where_negates_the_same_element_check() -> None:
    op = oa.Quantifier(
        "none",
        path="Customer.address.phones",
        where=oa.Comparison(op="eq", subject=oa.FieldSubject("number"), value="555-0000"),
    )
    compiled = compile_read(op, CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))
    assert compiled.statement.sql.startswith(
        "select t0.id, t0.name from customer t0 where not exists ("
    )
    assert "coalesce" not in compiled.statement.sql
    assert compiled.statement.sql.endswith("where jsonb_extract_path_text(t1.value, ?) = ?)")
    assert compiled.statement.binds == ("phones", "array", "phones", "[]", "number", "555-0000")


def test_a_quantifier_where_composes_or_not_and_group() -> None:
    # Not corpus-covered (the 8 in-slice cases only exercise a bare `and`/single
    # leaf inside `where`) — the scoped `elementPredicate` grammar also admits
    # `or`/`not`/`group`, element-relative and same-element exactly like `and`.
    op = oa.Quantifier(
        "any",
        path="Customer.address.phones",
        where=oa.Group(
            operand=oa.Or(
                operands=(
                    oa.Comparison(op="eq", subject=oa.FieldSubject("type"), value="home"),
                    oa.Not(
                        operand=oa.Comparison(
                            op="eq", subject=oa.FieldSubject("type"), value="work"
                        )
                    ),
                )
            )
        ),
    )
    compiled = compile_read(op, CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))
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
        pytest.param(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Customer.name"), value="x"),
            id="comparison",
        ),
        pytest.param(
            oa.NullCheck(op="isNull", subject=oa.FieldSubject("Customer.name")), id="nullCheck"
        ),
        pytest.param(oa.Quantifier("any", path="Customer.address.phones"), id="quantifier"),
        pytest.param(oa.Presence("exists", "Customer.address.geo"), id="presence"),
        pytest.param(oa.Narrow(to=("Customer",), operand=oa.TrueNode()), id="narrow"),
        pytest.param(
            oa.Comparison(op="eq", subject=oa.CURRENT_SCALAR_ELEMENT, value="x"), id="element"
        ),
    ],
)
def test_an_element_where_reads_only_the_element_it_binds(node: oa.PredicateNode) -> None:
    # Inside a value-object quantifier a path is relative to the bound element,
    # so an Entity-qualified subject, a narrowing, and a scalar element all name
    # something outside the scope.
    with pytest.raises(ModelRejectedError) as caught:
        compile_read(
            oa.Quantifier("any", path="Customer.address.phones", where=node),
            CUSTOMER,
            POSTGRES,
            target(CUSTOMER, "Customer"),
        )
    assert caught.value.rule == "predicate-subject-outside-scope"


def test_constants_lower_inside_an_element_where() -> None:
    compiled = compile_read(
        oa.Quantifier("all", path="Customer.address.phones", where=oa.FalseNode()),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert compiled.statement.sql.endswith("t1 where not (1 = 0) is true)")


def test_two_quantifiers_bind_independent_elements() -> None:
    # m-value-object-018's discriminating witness: two ANDed quantifiers over the
    # same `many` member open TWO independent subqueries (t1, t2), each
    # self-guarding — the contrast with one quantifier's `where`, which shares ONE
    # alias across every conjunct.
    op = oa.And(
        operands=(
            oa.Quantifier(
                "any",
                "Customer.address.phones",
                oa.Comparison(op="eq", subject=oa.FieldSubject("type"), value="home"),
            ),
            oa.Quantifier(
                "any",
                "Customer.address.phones",
                oa.Comparison(op="eq", subject=oa.FieldSubject("number"), value="555-9999"),
            ),
        )
    )
    compiled = compile_read(op, CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))
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


def test_every_quantifier_uses_the_same_guard_fragment() -> None:
    # The guard fragment is identical regardless of context (bare or scoped) —
    # one canonical `<arr>` spelling keyed only to the path, never re-derived per
    # call site.
    guard = (
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end"
    )
    scoped_element = compile_read(
        oa.Quantifier(
            "any",
            "Customer.address.phones",
            oa.Comparison(op="eq", subject=oa.FieldSubject("number"), value="555-0000"),
        ),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    bare = compile_read(
        oa.Quantifier("any", path="Customer.address.phones"),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert guard in scoped_element.statement.sql
    assert guard in bare.statement.sql


def test_presence_of_a_single_value_object_tests_for_an_object() -> None:
    # A JSON null, a missing member, and a non-object all fail presence; the
    # comparison's unknown folds to false so a negation stays two-valued.
    present = compile_read(
        oa.Presence("exists", "Customer.address.geo"),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert present.statement.sql.endswith(
        "where coalesce(jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ?, false)"
    )
    assert present.statement.binds == ("geo", "object")
    absent = compile_read(
        oa.Presence("notExists", "Customer.address.geo"),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Customer"),
    )
    assert absent.statement.sql.endswith(
        "where not coalesce(jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ?, false)"
    )


@pytest.mark.parametrize(
    "op",
    [
        pytest.param(oa.Quantifier("any", path="Customer.address.geo"), id="quantified-single"),
        pytest.param(oa.Presence("exists", "Customer.address.phones"), id="present-many"),
        pytest.param(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Customer.address.phones"), value="x"),
            id="compared-array",
        ),
        pytest.param(oa.Quantifier("any", path="Customer.address.city"), id="quantified-scalar"),
    ],
)
def test_an_operation_over_the_wrong_terminal_kind_is_refused(op: oa.PredicateNode) -> None:
    with pytest.raises(ModelRejectedError) as caught:
        compile_read(op, CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))
    assert caught.value.rule == "path-target-kind-mismatch"


def test_a_dotted_path_through_a_many_value_object_is_refused() -> None:
    with pytest.raises(ModelRejectedError) as caught:
        compile_read(
            oa.Comparison(
                op="eq", subject=oa.FieldSubject("Customer.address.phones.number"), value="x"
            ),
            CUSTOMER,
            POSTGRES,
            target(CUSTOMER, "Customer"),
        )
    assert caught.value.rule == "path-crosses-many"


def test_an_unknown_element_member_is_refused() -> None:
    op = oa.Quantifier(
        "any",
        path="Customer.address.phones",
        where=oa.Comparison(op="eq", subject=oa.FieldSubject("mystery"), value="x"),
    )
    with pytest.raises(ModelRejectedError):
        compile_read(op, CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))


def test_many_member_nested_two_levels_deep_binds_every_path_segment_twice() -> None:
    # customer.yaml's `phones` nests directly under the top-level `address` (one
    # segment before the `many` hop); this synthetic model proves the general
    # case — a `many` member reached through an INTERMEDIATE nested `one` value
    # object — composes correctly with the existing extraction machinery: every
    # segment on the path from the document column to the array binds TWICE in
    # the guard, and the field-within-the-element binds once more, after.
    from parallax.descriptor._records import (
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
    meta = formed(Metamodel(entities=(store,)))

    scoped_element = compile_read(
        oa.Quantifier(
            "any",
            "Store.profile.shipping.rates",
            oa.Comparison(op="eq", subject=oa.FieldSubject("zone"), value="west"),
        ),
        meta,
        POSTGRES,
        target(meta, "Store"),
    )
    assert scoped_element.statement.sql == (
        "select t0.id from store t0 where exists (select 1 from jsonb_array_elements("
        "case when jsonb_typeof(jsonb_extract_path(t0.profile, ?, ?)) = ? then "
        "jsonb_extract_path(t0.profile, ?, ?) else cast(? as jsonb) end) t1 where "
        "jsonb_extract_path_text(t1.value, ?) = ?)"
    )
    assert scoped_element.statement.binds == (
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
        oa.Quantifier("any", path="Store.profile.shipping.rates"),
        meta,
        POSTGRES,
        target(meta, "Store"),
    )
    assert bare_exists.statement.binds == ("shipping", "rates", "array", "shipping", "rates", "[]")


def test_presence_of_a_top_level_value_object_probes_its_column() -> None:
    compiled = compile_read(
        oa.Presence("exists", "Customer.address"), CUSTOMER, POSTGRES, target(CUSTOMER, "Customer")
    )
    assert compiled.statement.sql.endswith("where coalesce(jsonb_typeof(t0.address) = ?, false)")
    assert compiled.statement.binds == ("object",)


def test_presence_of_a_value_object_past_a_to_one_hop_reads_the_related_document() -> None:
    compiled = compile_read(
        oa.Presence("exists", "Location.customer.address"),
        CUSTOMER,
        POSTGRES,
        target(CUSTOMER, "Location"),
    )
    assert compiled.statement.sql.endswith(
        "where coalesce((select coalesce(jsonb_typeof(t1.address) = ?, false) "
        "from customer t1 where t1.id = t0.customer_id), false)"
    )
