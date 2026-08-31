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
import inspect
import pickle
from collections.abc import Callable
from typing import Literal, cast

import pytest
from _corpus_model_support import model, target

from _support import fake_metamodel
from _support.sql import compile_read
from parallax.core import inheritance, relationship, storage_layout
from parallax.core import object_query as oq
from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._compile import (
    AttributeReadContract,
    CompiledPredicate,
    CompiledRead,
)
from parallax.core.sql_gen._compile import compile_read as compile_entity_query

ORDERS = model("orders")
CUSTOMER = model("customer")
ACCOUNT = model("account")
SCALARS = model("scalars")
PAYMENT = model("payment")


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


def test_entity_query_target_must_belong_to_the_model() -> None:
    query = oq.EntityQuery(target=EntityIdentity(None, "Missing"), predicate=oa.All())
    # Authored Entity Queries are not accepted by the private lowering boundary;
    # snapshot preflight and deep-fetch planning must produce the validated token.
    with pytest.raises(AttributeError, match="entity"):
        compile_entity_query(query, ORDERS, POSTGRES)


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
    # `Order.qty` is non-nullable, so placement is observationally irrelevant on it:
    # there are no NULLs to place, both placements denote the same order, and the
    # plain term is emitted under either.
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
    assert not hasattr(sql_gen, "MaterializedReadRow")
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
        ("include_value_objects", inspect.Parameter.KEYWORD_ONLY, True),
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


def test_compiled_read_repr_is_exact_and_stable() -> None:
    # The default generated dataclass repr, pinned exactly. The row transform is
    # a stored FIELD, not a closure, which is why it reprs at all — a stored
    # callable would print an address and make this untestable.
    compiled = compile_read(oa.All(), ORDERS, POSTGRES, target(ORDERS, "Order"))
    assert repr(compiled) == (
        "CompiledRead(statement=LoweredStatement(sql='select t0.id, t0.name, t0.sku, "
        "t0.qty, t0.price, t0.active, t0.ordered_on from orders t0', binds=()), "
        "narrow_to=None, target=EntityIdentity(namespace='parallax.compatibility', name='Order'), "
        "resolved_position=(EntityIdentity(namespace='parallax.compatibility', name='Order'),), "
        "documents=(), projected_documents=(), document_reads=(), "
        "_transform=_IdentityTransform())"
    )


def _unpickle(value: CompiledRead) -> CompiledRead:
    return cast("CompiledRead", pickle.loads(pickle.dumps(value)))


@pytest.mark.parametrize(
    "route",
    [copy.copy, copy.deepcopy, _unpickle],
    ids=["copy", "deepcopy", "pickle"],
)
def test_compiled_read_round_trips_preserving_equality_repr_and_row_behavior(
    route: Callable[[CompiledRead], CompiledRead],
) -> None:
    # Deliberately NOT asserting on pickle BYTES — the ticket excludes them from
    # the contract (private definition paths and `__module__` may move). What
    # must survive a same-version round trip is the VALUE: equality, repr, and
    # the row behavior, which is the only reason the transform is stored as
    # ordinary dataclass state rather than as a bound method or closure.
    compiled = compile_read(oa.All(), PAYMENT, POSTGRES, target(PAYMENT, "Payment"))
    reconstructed = route(compiled)
    assert reconstructed == compiled
    assert repr(reconstructed) == repr(compiled)
    assert reconstructed.transform_row({"id": 1, "kind": "card"}) == {
        "id": 1,
        "familyVariant": "CardPayment",
    }


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
    assert AttributeReadContract(
        identity=payload.identity,
        column="payload",
        result_key="payload_hex",
        type=payload.type,
        nullable=payload.nullable,
        temporal_end=False,
        encoded=True,
    ) in compiled.attribute_reads(entity.identity)
    assert compiled.transform_row({"id": 1, "payload_hex": "00ff"}) == {
        "id": 1,
        "payload_hex": "00ff",
    }
    for invalid in (None, "not-hex"):
        with pytest.raises(SqlGenError, match="invalid stored data"):
            compiled.transform_row({"id": 1, "payload_hex": invalid})


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
        lock="locking",
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.owner, t0.balance, t0.version from account t0 "
        "where t0.id = ? for share of t0"
    )
    assert compiled.statement.binds == (7,)


def test_optimistic_and_default_reads_take_no_lock() -> None:
    for lock in (None, "optimistic"):
        compiled = compile_read(oa.All(), ACCOUNT, POSTGRES, target(ACCOUNT, "Account"), lock=lock)
        assert "for share" not in compiled.statement.sql


# --------------------------------------------------------------------------- #
# The compiler is typed against the metamodel protocols, so an accepted model   #
# that shares no code with the descriptor path compiles identically. The fake   #
# implementation below constructs no descriptor record at all; the facet it     #
# carries is compiled from the same metadata a formed model's would be.         #
# --------------------------------------------------------------------------- #
def _fake_model() -> Metamodel:
    base = fake_metamodel.parity_model()
    inheritance_facet = inheritance.compile_facet(base)
    return fake_metamodel.parity_model(
        {
            inheritance.FACET_KEY: inheritance_facet,
            storage_layout.FACET_KEY: storage_layout.compile_facet(
                base, inheritance_facet, relationship.compile_facet(base)
            ),
            relationship.FACET_KEY: relationship.compile_facet(base),
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
