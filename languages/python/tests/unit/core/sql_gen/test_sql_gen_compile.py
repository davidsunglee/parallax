"""Ordinary read assembly (m-sql lowering): projection, directives, clause tail.

The non-family, non-navigation, non-value-object lane of the read compiler: the
public statement/error interface and private compiler-product value semantics,
the `LoweredStatement` value itself, ordinary scalar/row projection,
result-shaping directive composition and
its refusals, the read-lock suffix, the
deferred-node refusals, and the bind-ORDER invariants the whole compiler rests
on (projection binds before predicate binds, limit bind last). Inheritance
families, navigation hops, value-object traversal, and write predicates each
have their own suite.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import pickle
from collections.abc import Callable, Mapping
from typing import Any, Literal, cast

import pytest

from parallax.core import deep_fetch, inheritance, relationship, storage_layout, temporal_read
from parallax.core import object_query as oq
from parallax.core import predicate as oa
from parallax.core.base import ManagedValue
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.inheritance import _compile as inheritance_compile
from parallax.core.metamodel import (
    Metamodel,
    NestedValueObjectMetadata,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeMetadata,
    ValueObjectIdentity,
)
from parallax.core.object_query import TemporalSelection
from parallax.core.object_query._nodes import TemporalDimension
from parallax.core.predicate._validated import (
    ValidatedOperands,
    ValidatedPredicate,
    conjunction,
    deferred_membership,
    managed_comparison,
)
from parallax.core.relationship import _compile as relationship_compile
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen import _compile as sql_compile
from parallax.core.sql_gen._compile import (
    AttributeReadContract,
    CompiledPredicate,
    CompiledRead,
)
from parallax.core.sql_gen._compile import compile_read as compile_entity_query
from parallax.core.storage_layout import _compile as storage_layout_compile
from parallax.core.temporal_read import _compile as temporal_read_compile
from tests._support import fake_metamodel
from tests._support.binary32 import narrowed
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model, target

ORDERS = model("orders")
CUSTOMER = model("customer")
ACCOUNT = model("account")
SCALARS = model("scalars")
PAYMENT = model("payment")
DOCUMENT_LAYOUT = model("document-layout")


def _compile_validated_product(
    product: ValidatedPredicate, meta: Metamodel = ACCOUNT
) -> CompiledRead:
    entity = target(meta, "Account") if meta is ACCOUNT else target(meta, "Customer")
    query = deep_fetch.ValidatedEntityQuery(
        target=entity.identity,
        entity=entity,
        validated_predicate=product,
        projection=deep_fetch.ResolvedReadProjection((), False),
    )
    return compile_entity_query(query, meta, POSTGRES)


def test_sql_lowering_rejects_incomplete_validated_scalar_products() -> None:
    balance = target(ACCOUNT, "Account").attribute("balance")
    assert balance is not None

    with pytest.raises(SqlGenError, match="carries no resolved Attribute"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.Comparison(op="eq", attr="Account.balance", value="1.00"),
                operands=ValidatedOperands((1,), balance.type),
            )
        )
    with pytest.raises(SqlGenError, match="carries no validated operands"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.Comparison(op="eq", attr="Account.balance", value="1.00"),
                member=balance,
            )
        )
    with pytest.raises(SqlGenError, match="carries no validated operands"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.Membership(op="in", attr="Account.balance", values=("1.00",)),
                member=balance,
            )
        )
    with pytest.raises(SqlGenError, match="has no declared neutral type"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.Comparison(op="eq", attr="Account.balance", value="1.00"),
                operands=ValidatedOperands((1,), None),
                member=balance,
            )
        )


def test_sql_lowering_rejects_incomplete_validated_structural_products() -> None:
    with pytest.raises(SqlGenError, match="no resolved effective position"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.Narrow(to=("Account",), operand=oa.All()),
                children=(ValidatedPredicate(oa.All()),),
            )
        )
    with pytest.raises(SqlGenError, match="no resolved relationship join"):
        _compile_validated_product(ValidatedPredicate(oa.Exists(rel="Account.missing")))
    with pytest.raises(SqlGenError, match="no resolved nested leaf"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.NestedComparison(op="nestedEq", path="Customer.address.city", value="Berlin")
            ),
            CUSTOMER,
        )
    with pytest.raises(SqlGenError, match="no resolved container"):
        _compile_validated_product(
            ValidatedPredicate(oa.NestedExists(path="Customer.address.phones")), CUSTOMER
        )


def test_inheritance_plan_may_select_but_never_replace_a_validated_occurrence() -> None:
    operand = oa.All()
    product = ValidatedPredicate(
        oa.Narrow(to=("Account",), operand=operand),
        children=(ValidatedPredicate(operand),),
    )

    assert sql_compile._planned_inner(product, operand) is product.children[0]  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(SqlGenError, match="replaced rather than selected"):
        sql_compile._planned_inner(product, object())  # pyright: ignore[reportPrivateUsage]


def test_sql_lowering_rejects_inconsistent_validated_value_object_products() -> None:
    customer = target(CUSTOMER, "Customer")
    position = inheritance.view(CUSTOMER).entity(customer.identity)
    assert position is not None
    address = position.applicable_value_object("address")
    assert address is not None
    city = address.attribute("city")
    phones = address.value_object("phones")
    assert city is not None
    assert phones is not None

    outside_leaf = cast(
        "ValueObjectAttributeMetadata",
        dataclasses.replace(
            cast("Any", city),
            identity=ValueObjectAttributeIdentity(
                ValueObjectIdentity(customer.identity, ("address", "other")), "city"
            ),
        ),
    )
    child = ValidatedPredicate(
        oa.NestedComparison(op="nestedEq", path="other.city", value="Berlin"),
        operands=ValidatedOperands(("Berlin",), city.type),
        member=outside_leaf,
    )
    with pytest.raises(SqlGenError, match="outside its resolved container"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.NestedExists(path="Customer.address.phones", where=child.authored),
                children=(child,),
                container=phones,
            ),
            CUSTOMER,
        )

    absent_leaf = cast(
        "ValueObjectAttributeMetadata",
        dataclasses.replace(
            cast("Any", city),
            identity=ValueObjectAttributeIdentity(
                ValueObjectIdentity(customer.identity, ("missing",)), "city"
            ),
        ),
    )
    with pytest.raises(SqlGenError, match="is absent from the active position"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.NestedComparison(op="nestedEq", path="Customer.missing.city", value="Berlin"),
                operands=ValidatedOperands(("Berlin",), city.type),
                member=absent_leaf,
            ),
            CUSTOMER,
        )

    array_leaf = cast(
        "ValueObjectAttributeMetadata",
        dataclasses.replace(
            cast("Any", city),
            identity=ValueObjectAttributeIdentity(
                ValueObjectIdentity(customer.identity, ("address",)), "phones"
            ),
        ),
    )
    with pytest.raises(SqlGenError, match="ends on the `many` array itself"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.NestedComparison(op="nestedEq", path="Customer.address.phones", value="Berlin"),
                operands=ValidatedOperands(("Berlin",), city.type),
                member=array_leaf,
            ),
            CUSTOMER,
        )

    absent_container = cast(
        "NestedValueObjectMetadata",
        dataclasses.replace(
            cast("Any", phones),
            identity=ValueObjectIdentity(customer.identity, ("missing", "phones")),
        ),
    )
    with pytest.raises(SqlGenError, match="is absent from the active position"):
        _compile_validated_product(
            ValidatedPredicate(
                oa.NestedExists(path="Customer.missing.phones"),
                container=absent_container,
            ),
            CUSTOMER,
        )


def test_all_projects_scalar_columns() -> None:
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql == (
        "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0"
    )
    assert compiled.statement.binds == ()


def test_none_lowers_to_unsatisfiable() -> None:
    compiled = compile_read(oa.NoneOp(), ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert compiled.statement.sql.endswith("where 1 = 0")


def test_instance_form_projects_value_object_document_last() -> None:
    # Instance-form (the object lane, m-sql *Read projection* slot 4): the value
    # object's document column rides the owner's SELECT, last among all columns.
    instance = compile_read(
        oa.All(), CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"), result_form="instance"
    )
    assert instance.statement.sql == (
        "select t0.id, t0.name, not t0.address is null, t0.address from customer t0"
    )
    assert instance.document_reads == ((2, 3),)
    assert instance.result_keys == ("id", "name", "address")
    # Row-form (the default values lane) omits slot 4 — the scalars alone.
    row = compile_read(oa.All(), CUSTOMER, POSTGRES, target(CUSTOMER, "Customer"))
    assert row.statement.sql == "select t0.id, t0.name from customer t0"


def test_unbound_attribute_is_refused() -> None:
    with pytest.raises(ValueError, match="names no declared attribute"):
        compile_read(
            oa.Comparison(op="eq", attr="Order.mystery", value=1),
            ORDERS,
            POSTGRES,
            target(ORDERS, "Order"),
        )


def test_entity_query_carries_one_limit_without_a_wrapper_tree() -> None:
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"), limit=5)
    assert compiled.statement.sql.endswith("limit ?")
    assert compiled.statement.binds == (5,)


def test_order_and_limit_directives_still_compose() -> None:
    # One of each directive (orderBy/limit) is the canonical stack and
    # lowers to the ordered clauses, unaffected by the duplicate-directive guard.
    compiled = compile_read(
        oa.All(),
        ORDERS,
        POSTGRES,
        target(ORDERS, "Order"),
        order_by=(oq.OrderKey(attr="Order.id", direction="asc"),),
        limit=5,
    )
    assert compiled.statement.sql.endswith("order by t0.id asc limit ?")


@pytest.mark.parametrize(
    ("direction", "placement", "term"),
    [
        ("asc", None, "t0.sku asc"),
        ("asc", "last", "t0.sku asc"),
        ("desc", "last", "t0.sku desc nulls last"),
        ("asc", "first", "t0.sku asc nulls first"),
        ("desc", "first", "t0.sku desc"),
        ("desc", None, "t0.sku desc nulls last"),
    ],
)
def test_nullable_order_key_lowers_through_the_placement_seam(
    direction: str, placement: str | None, term: str
) -> None:
    # `Order.sku` is nullable, so every placement — including the omitted one, which
    # defaults to `last` — renders through the m-dialect seam.
    keys = (
        oq.OrderKey(
            attr="Order.sku",
            direction=cast('Literal["asc", "desc"]', direction),
            nulls=cast('Literal["first", "last"] | None', placement),
        ),
    )
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"), order_by=keys)
    assert compiled.statement.sql.endswith(f"order by {term}")


@pytest.mark.parametrize("placement", [None, "first", "last"])
def test_non_nullable_order_key_ignores_placement(placement: str | None) -> None:
    # `Order.qty` is non-nullable, so placement is observationally irrelevant on it
    # under conforming storage: there is no NULL to place, both placements denote the
    # same order, and the plain term is emitted under either — leaving the dialect's
    # own convention to rank a NULL a dropped `NOT NULL` constraint left behind.
    keys = (
        oq.OrderKey(
            attr="Order.qty",
            direction="desc",
            nulls=cast('Literal["first", "last"] | None', placement),
        ),
    )
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"), order_by=keys)
    assert compiled.statement.sql.endswith("order by t0.qty desc")


def test_statement_is_frozen_value() -> None:
    statement = LoweredStatement("select 1", (1,))
    assert statement.sql == "select 1"
    assert statement.binds == (1,)


# --------------------------------------------------------------------------- #
# The supported interface itself. `parallax.core.sql_gen` exports exactly two   #
# names; every compiler operation and compiler product is private implementation. #
# The result objects are ordinary frozen dataclasses, so equality, `repr`,      #
# hashing, copying, and same-version pickling are all structural — no           #
# `__reduce__`, no stored callable, nothing to keep in sync by hand.            #
# --------------------------------------------------------------------------- #
def test_the_package_exports_only_statement_and_error_values() -> None:
    # An EXACT set, not a superset: re-exporting a private helper is precisely the
    # regression this guards, and a superset assertion would not see it. Canonical
    # column order is `m-inheritance`'s export, so its absence here is the point.
    import parallax.core.sql_gen as sql_gen

    assert set(sql_gen.__all__) == {"LoweredStatement", "SqlGenError"}
    assert sql_gen.SqlGenError is SqlGenError
    assert sql_gen.LoweredStatement is LoweredStatement
    assert not hasattr(sql_gen, "AttributeReadContract")
    assert not hasattr(sql_gen, "CompiledPredicate")
    assert not hasattr(sql_gen, "CompiledRead")
    assert not hasattr(sql_gen, "PreparedRow")
    assert not hasattr(sql_gen, "compile_read")
    assert not hasattr(sql_gen, "compile_write_predicate")


def test_compile_read_accepts_exactly_the_supported_call_shape() -> None:
    # The export assertion above pins NAMES; a supported entry point's call shape
    # is a second contract nothing else covers, so adding, renaming, or removing a
    # parameter — or turning a keyword-only one positional — is caught here rather
    # than at a caller.
    parameters = inspect.signature(compile_entity_query).parameters
    assert [
        (name, parameter.kind, parameter.default is not inspect.Parameter.empty)
        for name, parameter in parameters.items()
    ] == [
        ("query", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
        ("model", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
        ("dialect", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
        ("result_form", inspect.Parameter.KEYWORD_ONLY, True),
        ("lock", inspect.Parameter.KEYWORD_ONLY, True),
    ]


def test_compiled_read_is_an_equatable_hashable_value() -> None:
    # Two compiles of the same read are indistinguishable values — which is what
    # lets a caller cache, compare, or key on one.
    first = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"))
    second = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert first == second
    assert hash(first) == hash(second)
    # And a DIFFERENT read is not equal, member by member: the statement,
    # the narrow, and the transform all participate.
    assert first != compile_read(oa.NoneOp(), ORDERS, POSTGRES, target(ORDERS, "Order"))


def test_compiled_row_validation_rejects_duplicate_keys_and_wrong_tuple_arity() -> None:
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"))

    with pytest.raises(ValueError, match="duplicate result key 'id'"):
        dataclasses.replace(compiled, result_keys=("id", "id"))
    with pytest.raises(ValueError, match="does not match row arity"):
        compiled.row_identity(())
    with pytest.raises(KeyError, match="missing"):
        compiled.raw_member_of((), compiled.target, "missing")


def test_a_read_paging_through_nothing_reads_no_coordinate_off_any_row() -> None:
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"))

    assert compiled.coordinate_reads == ()
    assert compiled.row_coordinates(((), ())) == (None, None)


def test_compiled_read_repr_is_exact_and_stable() -> None:
    # The default generated dataclass repr, pinned exactly. The row stages are a
    # stored FIELD, not a closure, which is why they repr at all — a stored
    # callable would print an address and make this untestable. A plain record
    # still names what its rows resolve to: an identity fixed at compile time,
    # which is all its rows can name.
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"))
    order = "EntityIdentity(namespace='parallax.compatibility', name='Order')"
    assert repr(compiled) == (
        "CompiledRead(statement=LoweredStatement(sql='select t0.id, t0.name, t0.sku, "
        "t0.qty, t0.price, t0.active, t0.ordered_on from orders t0', binds=()), "
        f"narrow_to=None, target={order}, "
        f"resolved_position=({order},), "
        "documents=(), projected_documents=(), document_reads=(), "
        "result_keys=('id', 'name', 'sku', 'qty', 'price', 'active', 'ordered_on'), "
        "coordinate_reads=(), "
        f"_stages=RowStages(resolve=FixedIdentity(entity={order}), "
        "shared_document=None, direct_documents=None))"
    )


def _unpickle(value: CompiledRead) -> CompiledRead:
    return cast("CompiledRead", pickle.loads(pickle.dumps(value)))


@pytest.mark.parametrize(
    "route",
    [copy.copy, copy.deepcopy, _unpickle],
    ids=["copy", "deepcopy", "pickle"],
)
def test_compiled_read_round_trips_preserving_equality_and_repr(
    route: Callable[[CompiledRead], CompiledRead],
) -> None:
    # Deliberately NOT asserting on pickle BYTES — the ticket excludes them from
    # the contract (private definition paths and `__module__` may move). What
    # must survive a same-version round trip is the VALUE: equality and repr.
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, target(PAYMENT, "Payment"))
    reconstructed = route(compiled)
    assert reconstructed == compiled
    assert repr(reconstructed) == repr(compiled)


def test_compiled_predicate_is_a_frozen_value() -> None:
    predicate = CompiledPredicate("balance < ?", (100,))
    assert predicate.sql == "balance < ?"
    assert predicate.binds == (100,)
    assert predicate == CompiledPredicate("balance < ?", (100,))
    # `binds` defaults to the empty tuple, exactly as `LoweredStatement`'s does.
    assert CompiledPredicate("1 = 0") == CompiledPredicate("1 = 0", ())


# --------------------------------------------------------------------------- #
# Bind ORDER across the four phases (m-sql; the state invariants the private   #
# split must preserve). Bind order is produced STRUCTURALLY by call ordering   #
# — projection, then the user predicate, then any framework guard, then the    #
# limit — never by a sorting pass, so these pins are what catch a reordered    #
# lowering that still emits byte-identical SQL text.                           #
#                                                                              #
# `ScalarThing` is the only corpus model with a bind-EMITTING projection: a    #
# `bytes` column projects `encode(t0.payload, ?) payload_hex` with the bind    #
# `hex` (m-dialect). Combining it with a bind-emitting predicate and a         #
# trailing limit is a shape no Docker-free corpus case reaches — the one that  #
# does (`m-navigate-024`) is `compileEligibility: run-only` — so the pins are  #
# built from the corpus-loaded model directly.                                 #
# --------------------------------------------------------------------------- #
def test_projection_binds_precede_predicate_binds() -> None:
    # The projection's own dialect bind (`hex`) is spliced into the context BEFORE
    # the predicate lowers, so it leads the tuple however many predicate binds
    # follow. Placeholder order in the SQL and bind order must agree.
    compiled = compile_read(
        oa.Comparison(op="greaterThan", attr="ScalarThing.f64", value=1.5),
        SCALARS,
        POSTGRES,
        target(SCALARS, "ScalarThing"),
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.f32, t0.f64, encode(t0.payload, ?) payload_hex, t0.local_time, "
        "t0.external_id from scalar_thing t0 where t0.f64 > ?"
    )
    assert compiled.statement.binds == ("hex", 1.5)


def test_encoded_projection_result_key_carries_its_logical_scalar_contract() -> None:
    entity = target(SCALARS, "ScalarThing")
    compiled = compile_read(oa.All(), SCALARS, POSTGRES, entity)
    payload = entity.attribute("payload")
    assert payload is not None
    assert compiled.result_keys == (
        "id",
        "f32",
        "f64",
        "payload_hex",
        "local_time",
        "external_id",
    )
    assert AttributeReadContract(
        attribute=payload,
        result_key="payload_hex",
        temporal_end=False,
        encoded=True,
    ) in compiled.attribute_reads(entity.identity)


_MARIADB = dataclasses.replace(POSTGRES, name="mariadb")


def _child_template(
    dialect: Dialect, meta: Metamodel = ORDERS, name: str = "OrderItem", attr: str = "orderId"
) -> sql_compile.CompiledTemplate:
    entity = target(meta, name)
    member = entity.attribute(attr)
    assert member is not None
    query = deep_fetch.ValidatedEntityQuery(
        target=entity.identity,
        entity=entity,
        validated_predicate=deferred_membership(
            attr=f"{name}.{attr}",
            member=member,
        ),
        projection=deep_fetch.ResolvedReadProjection((), False),
    )
    return sql_compile.compile_template(query, meta, dialect)


def test_postgres_child_template_keeps_one_array_bind_for_every_key_count() -> None:
    template = _child_template(POSTGRES)
    first = template.render([1])
    several = template.render([1, 42])

    assert first.statement.sql == several.statement.sql
    assert first.statement.sql.endswith("where t0.order_id = any(?)")
    assert first.statement.binds == ([1],)
    assert several.statement.binds == ([1, 42],)
    assert several.statement.wire_binds() == ([1, 42],)


def test_postgres_child_template_binds_the_gathered_list_under_the_template_metadata() -> None:
    template = _child_template(POSTGRES)
    keys: list[ManagedValue] = [1, 42]

    rendered = template.render(keys).statement

    assert rendered.binds[0] is keys
    assert rendered.typed_bind_spans is template.compiled.statement.typed_bind_spans
    assert rendered.wire_bind_overrides is template.compiled.statement.wire_bind_overrides


def test_mariadb_child_template_expands_only_the_deferred_key_bind() -> None:
    rendered = _child_template(_MARIADB).render([1, 42])

    assert rendered.statement.sql.endswith("where t0.order_id in (?, ?)")
    assert rendered.statement.binds == (1, 42)
    assert rendered.statement.wire_binds() == (1, 42)


@pytest.mark.parametrize(
    ("dialect", "projected"),
    [(POSTGRES, ([1.2, 0.1],)), (_MARIADB, (1.2, 0.1))],
    ids=["postgres", "mariadb"],
)
def test_child_template_projects_each_float32_key_to_its_canonical_wire_value(
    dialect: Dialect, projected: tuple[object, ...]
) -> None:
    template = _child_template(dialect, SCALARS, "ScalarThing", "f32")

    rendered = template.render([narrowed(1.2), narrowed(0.1)])

    assert rendered.statement.wire_binds()[-len(projected) :] == projected


@pytest.mark.parametrize("dialect", [POSTGRES, _MARIADB], ids=["postgres", "mariadb"])
def test_an_unrendered_child_template_has_no_wire_projection(dialect: Dialect) -> None:
    with pytest.raises(SqlGenError, match="until its keys are rendered"):
        _child_template(dialect).compiled.statement.wire_binds()


def test_child_template_refuses_an_empty_set_that_should_issue_no_statement() -> None:
    with pytest.raises(SqlGenError, match="at least one gathered key"):
        _child_template(POSTGRES).render([])


@pytest.mark.parametrize("dialect", [POSTGRES, _MARIADB], ids=["postgres", "mariadb"])
def test_child_template_refuses_a_query_without_one_deferred_key_set(dialect: Dialect) -> None:
    entity = target(ACCOUNT, "Account")
    query = deep_fetch.ValidatedEntityQuery(
        target=entity.identity,
        entity=entity,
        validated_predicate=ValidatedPredicate(oa.All()),
        projection=deep_fetch.ResolvedReadProjection((), False),
    )

    with pytest.raises(SqlGenError, match="exactly one deferred key set"):
        sql_compile.compile_template(query, ACCOUNT, dialect)


@pytest.mark.parametrize("dialect", [POSTGRES, _MARIADB], ids=["postgres", "mariadb"])
def test_child_template_refuses_distinct_markers_even_when_their_types_match(
    dialect: Dialect,
) -> None:
    entity = target(ORDERS, "OrderItem")
    member = entity.attribute("orderId")
    assert member is not None
    query = deep_fetch.ValidatedEntityQuery(
        target=entity.identity,
        entity=entity,
        validated_predicate=conjunction(
            deferred_membership(attr="OrderItem.orderId", member=member),
            deferred_membership(attr="OrderItem.orderId", member=member),
        ),
        projection=deep_fetch.ResolvedReadProjection((), False),
    )
    with pytest.raises(SqlGenError, match="exactly one deferred key set"):
        sql_compile.compile_template(query, ORDERS, dialect)


@pytest.mark.parametrize("dialect", [POSTGRES, _MARIADB], ids=["postgres", "mariadb"])
@pytest.mark.parametrize("narrow", [False, True], ids=["three-branches", "single-branch"])
def test_tpcs_child_template_renders_each_occurrence_without_recompilation(
    dialect: Dialect, narrow: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = model("document")
    entity = target(meta, "Document")
    member = entity.attribute("folderId")
    title = entity.attribute("title")
    assert member is not None and title is not None
    query = deep_fetch.ValidatedEntityQuery(
        target=entity.identity,
        entity=entity,
        validated_predicate=conjunction(
            managed_comparison(op="eq", attr="Document.title", member=title, value="before"),
            deferred_membership(attr="Document.folderId", member=member),
            managed_comparison(op="notEq", attr="Document.title", member=title, value="after"),
        ),
        narrow_to=(target(meta, "Invoice").identity,) if narrow else None,
        limit=7,
        projection=deep_fetch.ResolvedReadProjection((), False),
    )
    template = sql_compile.compile_template(query, meta, dialect, result_form="instance")
    original = template.compiled.statement

    def forbidden(*args: object, **kwargs: object) -> Any:
        raise AssertionError("render must reuse prepared access and assemble only once")

    monkeypatch.setattr(sql_compile, "compile_read", forbidden)
    monkeypatch.setattr(LoweredStatement, "deferred_key_markers", forbidden)
    for keys in ([10], [10, 20, 30], [40, 50]):
        original_keys = tuple(keys)
        gathered = cast("list[ManagedValue]", keys)
        rendered = template.render(gathered)
        branches = 1 if narrow else 3
        key_binds: tuple[object, ...] = (keys,) if dialect.name == "postgres" else tuple(keys)
        assert rendered.statement.binds == ("before", *key_binds, "after") * branches + (7,)
        assert rendered.statement.wire_binds() == rendered.statement.binds
        membership = (
            "t0.folder_id = any(?)"
            if dialect.name == "postgres"
            else f"t0.folder_id in ({', '.join('?' for _ in keys)})"
        )
        assert rendered.statement.sql.count(membership) == branches
        assert rendered.statement.sql.count("union all") == branches - 1
        assert "__parallax_deferred_keys__" not in rendered.statement.sql
        assert rendered.statement.is_compiler_proven
        assert rendered.result_keys == template.compiled.result_keys
        assert rendered.document_reads == template.compiled.document_reads
        assert rendered.resolved_position == template.compiled.resolved_position
        assert rendered.statement.sql.endswith("limit ?")
        if dialect.name == "postgres":
            assert all(rendered.statement.binds[1 + 3 * index] is keys for index in range(branches))
            assert rendered.statement.typed_bind_spans is original.typed_bind_spans
        assert tuple(keys) == original_keys
    assert template.compiled.statement is original


@pytest.mark.parametrize(
    ("meta", "name", "temporal"),
    [
        (ORDERS, "Order", None),
        (SCALARS, "ScalarThing", None),
        (CUSTOMER, "Customer", None),
        (PAYMENT, "Payment", None),
        (DOCUMENT_LAYOUT, "Publication", None),
        (
            DOCUMENT_LAYOUT,
            "Charter",
            {"valid-time": oq.AsOf("latest"), "transaction-time": oq.AsOf("latest")},
        ),
    ],
    ids=["plain", "encoded", "documents", "family", "document-layout", "temporal"],
)
def test_attribute_contracts_align_by_position_with_each_resolvable_layout(
    meta: Metamodel,
    name: str,
    temporal: Mapping[TemporalDimension, TemporalSelection] | None,
) -> None:
    # The compiled contracts and the model's exact member layout are two readings
    # of ONE position view, so contract `i` describes layout Attribute `i` — the
    # same metadata object, not an equal copy. That is what lets a consumer read
    # the two together by position instead of indexing one by identity per row.
    # The interval-closing Attributes agree for the same reason, both being the
    # family root's declared axes, so a consumer admitting a stored scalar reads
    # the flag off the contract rather than re-testing the layout's own set.
    # An Entity this read projected no columns for — a family root only an
    # unrecognized tag names — answers nothing, and its rows read storage keys.
    cataloged = CatalogedModel(meta)
    compiled = compile_read(oa.All(), meta, POSTGRES, target(meta, name), temporal=temporal)
    assert compiled.resolvable
    for identity in compiled.resolvable:
        reads = compiled.attribute_reads(identity)
        if identity not in compiled.resolved_position:
            assert reads == ()
            continue
        layout = cataloged.layouts.entity(identity)
        assert reads
        for contract, attribute in zip(reads, layout.attributes, strict=True):
            assert contract.attribute is attribute
            assert contract.temporal_end == (attribute.identity in layout.temporal_ends)
        assert any(contract.temporal_end for contract in reads) == bool(layout.temporal_ends)


def test_limit_bind_lands_after_predicate_binds() -> None:
    # The limit clause is appended by the shared clause tail AFTER the `where`
    # clause is already assembled, so its bind is last — behind both the
    # projection bind and every user-predicate bind.
    compiled = compile_read(
        oa.Comparison(op="greaterThan", attr="ScalarThing.f64", value=1.5),
        SCALARS,
        POSTGRES,
        target(SCALARS, "ScalarThing"),
        limit=3,
    )
    assert compiled.statement.sql.endswith("from scalar_thing t0 where t0.f64 > ? limit ?")
    assert compiled.statement.binds == ("hex", 1.5, 3)


# --------------------------------------------------------------------------- #
# Read-lock suffix (m-sql *Read-lock suffix*, via the m-dialect seam).         #
# --------------------------------------------------------------------------- #
def test_locking_object_find_matches_the_scenario_find_golden() -> None:
    # The m-read-lock-001 golden's shape: an in-transaction object find whose
    # target resolved to the Locking strategy carries the shared-row-lock
    # suffix, last in the statement.
    compiled = compile_read(
        oa.Comparison(op="eq", attr="Account.id", value=7),
        ACCOUNT,
        POSTGRES,
        target(ACCOUNT, "Account"),
        preference="locking",
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.owner, t0.balance, t0.version from account t0 "
        "where t0.id = ? for share of t0"
    )
    assert compiled.statement.binds == (7,)


def test_optimistic_and_default_reads_take_no_lock() -> None:
    for preference in (None, "optimistic"):
        compiled = compile_read(
            oa.All(), ACCOUNT, POSTGRES, target(ACCOUNT, "Account"), preference=preference
        )
        assert "for share" not in compiled.statement.sql


# --------------------------------------------------------------------------- #
# The compiler is typed against the metamodel protocols, so an accepted model   #
# that shares no code with the descriptor path compiles identically. The fake   #
# implementation below constructs no descriptor record at all; the facet it     #
# carries is compiled from the same metadata a formed model's would be.         #
# --------------------------------------------------------------------------- #
def _fake_model() -> Metamodel:
    base = fake_metamodel.parity_model()
    inheritance_facet = inheritance_compile.compile_facet(base)
    return fake_metamodel.parity_model(
        {
            inheritance.FACET_KEY: inheritance_facet,
            storage_layout.FACET_KEY: storage_layout_compile.compile_facet(
                base, inheritance_facet, relationship_compile.compile_facet(base)
            ),
            relationship.FACET_KEY: relationship_compile.compile_facet(base),
            temporal_read.FACET_KEY: temporal_read_compile.compile_facet(base, inheritance_facet),
        }
    )


def test_a_record_free_model_compiles_the_same_reads() -> None:
    model = _fake_model()
    account = model.entity(fake_metamodel.ACCOUNT)
    assert account is not None

    scalars = compile_read(oa.All(), model, POSTGRES, account)
    assert scalars.statement.sql == (
        "select t0.id, t0.ledger_label, t0.balance, t0.opened_on from account t0"
    )
    # Instance form adds the `Document` tier slot after every scalar tier.
    instance = compile_read(oa.All(), model, POSTGRES, account, result_form="instance")
    assert instance.statement.sql.endswith(
        "t0.opened_on, not t0.contact_doc is null, t0.contact_doc from account t0"
    )


def test_a_record_free_model_lowers_navigation_and_value_object_paths() -> None:
    model = _fake_model()
    account = model.entity(fake_metamodel.ACCOUNT)
    entry = model.entity(fake_metamodel.ENTRY)
    assert account is not None
    assert entry is not None

    # A defining declaration's own join, and the reverse declaration's swap of it.
    forward = compile_read(oa.Exists(rel="Account.entries"), model, POSTGRES, account)
    assert forward.statement.sql.endswith(
        "where exists (select 1 from entry t1 where t1.account_id = t0.id)"
    )
    reverse = compile_read(oa.Exists(rel="Entry.account"), model, POSTGRES, entry)
    assert reverse.statement.sql.endswith(
        "where exists (select 1 from account t1 where t1.id = t0.account_id)"
    )

    nested = compile_read(
        oa.NestedComparison(op="nestedEq", path="Account.contact.address.city", value="Oslo"),
        model,
        POSTGRES,
        account,
    )
    assert nested.statement.sql.endswith("where jsonb_extract_path_text(t0.contact_doc, ?, ?) = ?")
    assert nested.statement.binds == ("address", "city", "Oslo")
