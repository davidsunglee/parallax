"""Predicate-selected (`*_where`) write unit tests for `parallax.snapshot._handle`.

The set-based verb family covers the mutation-compatibility guard, Assignment
composition, the replaced state, inheritance rejection, the readless statement an unversioned
non-temporal target executes, and the refusal of every target that needs an
observation (`m-batch-write`).

The codec's effective-change comparison is driven directly off positional rows
over these models' own shapes, under `Columns` layout and Relational Document
Layout alike.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, cast
from uuid import UUID

import pytest

from parallax.conformance import engine
from parallax.conformance._lanes import scenario
from parallax.conformance.class_models import MODELS
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.read_models import Balance
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.story_models import Account, Order, OrderItem
from parallax.core import (
    TX_TIME,
    Attr,
    Document,
    DomainModel,
    Entity,
    Int32,
    Predicate,
    QueryDefinitionError,
    TxTemporal,
    ValueObject,
    attr,
    inheritance,
)
from parallax.core._execution._family import comparison_shape
from parallax.core._execution._publication import write_projection
from parallax.core._execution._unit_work import instructions
from parallax.core.base import (
    INFINITY,
    FrozenMap,
)
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import (
    MemberShape,
    prepare_effective_change,
)
from parallax.core.entity._authored_resolver import typed_interpretation
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._expressions import AuthoredPath, UnfinishedOperation
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import DomainModel as _Fixed
from parallax.core.entity._model import class_index, model_of
from parallax.core.execution import QueryTargetError, ServingModel, prepare_model
from parallax.core.metamodel import UnresolvedEntityDeclaration
from parallax.core.predicate import ModelRejectedError
from parallax.core.predicate._interpretation import COMPARE
from parallax.core.unit_work import (
    PredicateWriteInstruction,
)
from parallax.snapshot import (
    Database,
    TxnContext,
)
from parallax.snapshot._handle import _typed_writes as typed_writes
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.case_corpus import case as corpus_case
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.root_ownership import own_root
from tests.unit._document_layout_support import document_model
from tests.unit._document_layout_support import entity as document_layout_entity
from tests.unit._positional_row_support import positional_row
from tests.unit._transact_support import (
    ACCOUNT,
    FIXED,
    ORDERS,
    PAYMENT,
    PERSON,
    RATE,
)


class WhereManagedOccurrence(ValueObject):
    amount: Attr[Decimal] = attr(precision=18, scale=2)
    payload: Attr[bytes]
    day: Attr[dt.date]
    time: Attr[dt.time]
    instant: Attr[dt.datetime]
    token: Attr[UUID]


class WhereManagedSubscriber(
    Entity, table="where_managed_subscriber", namespace="parallax.compatibility"
):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)
    day: Attr[dt.date]
    payload: Attr[bytes]
    details: Attr[WhereManagedOccurrence]
    entries: Attr[tuple[WhereManagedOccurrence, ...]]


_WHERE_MANAGED_SUBSCRIBER_META = DomainModel(WhereManagedSubscriber)


# A local Transaction-Time-Only entity under Relational Document Layout: the two
# axis bounds keep Columns of their own and every domain member lives in the
# shared Structured Column.
class WhereVoyageManifest(ValueObject):
    cargo: Attr[str | None]


class WhereVoyage(
    TxTemporal, table="where_voyage", namespace="parallax.compatibility", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str | None] = attr(max_length=64)
    manifest: Attr[WhereVoyageManifest | None]


_WHERE_VOYAGE_META = DomainModel(WhereVoyage)


class NestedReadlessStop(ValueObject):
    port: Attr[str]


class NestedReadlessSegment(ValueObject):
    stops: Attr[tuple[NestedReadlessStop, ...]]


class NestedReadlessRoute(ValueObject):
    name: Attr[str]
    segment: Attr[NestedReadlessSegment]


class NestedReadlessVoyage(
    Entity, table="nested_readless_voyage", namespace="parallax.compatibility", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str | None]
    route: Attr[NestedReadlessRoute]


_NESTED_READLESS_META = DomainModel(NestedReadlessVoyage)


# --------------------------------------------------------------------------- #
# Predicate-selected `_where` verb family over a readless target: one        #
# statement, executed at the call, with no read.                               #
# --------------------------------------------------------------------------- #
def test_readless_update_where_executes_one_statement_no_read() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_where(mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"))

    own_root(
        Database.connect(port, PERSON, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert port.calls == [
        BeginCall(),
        WriteCall(POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Ada", 1)),
        CommitCall(),
    ]


def test_readless_document_many_assignment_replaces_the_array_at_its_path() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_where(
            mm.Traveler.where(mm.Traveler.id == 1),
            mm.Traveler.tags.set((mm.TravelerTag(label="founder"),)),
        )

    own_root(
        Database.connect(port, mm.DOCUMENT_LAYOUT_MODEL, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert port.calls == [
        BeginCall(),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update traveler set payload = jsonb_set(payload, ?, cast(? as jsonb)) where id = ?"
            ),
            ("{tags}", JsonDocument((FrozenMap({"label": "founder"}),)), 1),
        ),
        CommitCall(),
    ]


@pytest.mark.parametrize(
    ("model", "entity", "sql", "binds"),
    [
        (
            mm.SCALAR_COLLECTION_COLUMNS_MODEL,
            mm.ColumnsCollectionTwinItem,
            "update collection_twin set counts = ?, tags = ? where id < ?",
            (JsonDocument((5, 5)), JsonDocument(("b",)), 3),
        ),
        (
            mm.SCALAR_COLLECTION_DOCUMENT_MODEL,
            mm.DocumentCollectionTwinItem,
            "update collection_twin set payload = jsonb_set(jsonb_set(payload, ?, "
            "cast(? as jsonb)), ?, cast(? as jsonb)) where id < ?",
            ("{counts}", JsonDocument((5, 5)), "{tags}", JsonDocument(("b",)), 3),
        ),
    ],
    ids=["columns", "document"],
)
def test_a_readless_collection_assignment_binds_whole_arrays_in_layout_order(
    model: DomainModel, entity: Any, sql: str, binds: tuple[object, ...]
) -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_where(
            entity.where(entity.id < 3), entity.tags.set(("b",)), entity.counts.set((5, 5))
        )

    own_root(
        Database.connect(port, model, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert port.calls == [
        BeginCall(),
        WriteCall(POSTGRES.to_driver_sql(sql), binds),
        CommitCall(),
    ]


def test_readless_nested_document_many_assignment_replaces_the_whole_occurrence() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_where(
            NestedReadlessVoyage.where(NestedReadlessVoyage.id == 1),
            NestedReadlessVoyage.route.set(
                NestedReadlessRoute(
                    name="Coastal",
                    segment=NestedReadlessSegment(stops=(NestedReadlessStop(port="Oslo"),)),
                )
            ),
        )

    own_root(
        Database.connect(port, _NESTED_READLESS_META, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    route = FrozenMap(
        {"name": "Coastal", "segment": FrozenMap({"stops": (FrozenMap({"port": "Oslo"}),)})}
    )
    assert port.calls == [
        BeginCall(),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update nested_readless_voyage set payload = "
                "jsonb_set(payload, ?, cast(? as jsonb)) where id = ?"
            ),
            ("{route}", JsonDocument(route), 1),
        ),
        CommitCall(),
    ]


def test_readless_document_scalar_assignment_still_reaches_planning() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_where(
            NestedReadlessVoyage.where(NestedReadlessVoyage.id == 1),
            NestedReadlessVoyage.title.set("Coastal"),
        )

    own_root(
        Database.connect(port, _NESTED_READLESS_META, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert [type(op) for op in port.calls] == [BeginCall, WriteCall, CommitCall]


def test_readless_delete_where_executes_one_statement_no_read() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1))

    own_root(
        Database.connect(port, PERSON, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert port.calls == [
        BeginCall(),
        WriteCall(POSTGRES.to_driver_sql("delete from person where id = ?"), (1,)),
        CommitCall(),
    ]


def test_readless_replace_where_writes_the_instances_whole_state_but_never_its_key() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.replace_where(mm.Person.where(mm.Person.id == 1), mm.Person(id=9, name="Grace"))

    own_root(
        Database.connect(port, PERSON, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert port.calls == [
        BeginCall(),
        WriteCall(POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Grace", 1)),
        CommitCall(),
    ]


def test_readless_replace_where_completes_each_omitted_member_at_its_document_path() -> None:
    # An omitted nullable member is JSON null at its own path and an omitted
    # `many` the empty array, each patched in canonical placement order, so no
    # key the replacement does not write is touched.
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.replace_where(mm.Traveler.where(mm.Traveler.id == 1), mm.Traveler(id=1, note="east"))

    own_root(
        Database.connect(port, mm.DOCUMENT_LAYOUT_MODEL, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    patch = "payload"
    for _ in range(6):
        patch = f"jsonb_set({patch}, ?, cast(? as jsonb))"
    assert port.calls == [
        BeginCall(),
        WriteCall(
            POSTGRES.to_driver_sql(f"update traveler set payload = {patch} where id = ?"),
            (
                "{displayName}",
                "null",
                "{score}",
                "null",
                "{joinedOn}",
                "null",
                "{note}",
                '"east"',
                "{address}",
                "null",
                "{tags}",
                JsonDocument(()),
                1,
            ),
        ),
        CommitCall(),
    ]


def test_a_replacement_of_an_entity_writing_nothing_but_its_key_is_dropped() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.replace_where(mm.Beacon.where(mm.Beacon.id == 1), mm.Beacon(id=1))

    own_root(
        Database.connect(port, mm.DOCUMENT_LAYOUT_MODEL, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert port.calls == [BeginCall(), CommitCall()]


def test_replace_where_refuses_a_payload_of_another_entity() -> None:
    # The type checker refuses it; preparation's caller is the runtime, which
    # can be handed anything.
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.replace_where(
            mm.Person.where(mm.Person.id == 1),
            mm.Passport(id=1, person_id=1, number="X"),  # pyright: ignore[reportArgumentType]
        )

    with raises_contextualized(
        instructions.WriteInstructionError,
        match=r"`replace_where` over parallax\.compatibility\.Person states a whole state of "
        r"that Entity, and this payload is a parallax\.compatibility\.Passport",
    ):
        own_root(
            Database.connect(port, PERSON, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert not any(isinstance(op, (ReadCall, WriteCall)) for op in port.calls)


def test_readless_update_where_through_a_shared_join_executes_one_statement_no_read() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_where(OrderItem.where(OrderItem.order.name == "Ada"), OrderItem.sku.set("Z"))

    own_root(
        Database.connect(port, ORDERS, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    assert port.calls == [
        BeginCall(),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update order_item set sku = ? where id in (select t0.id from order_item t0 "
                "left join orders t1 on t1.id = t0.order_id where t1.name = ?)"
            ),
            ("Z", "Ada"),
        ),
        CommitCall(),
    ]


def test_readless_update_where_reorders_assignments_to_layout_slot_order() -> None:
    # The SET clause orders by the target's Table Layout slots
    # (the settled step's own slot-ordered assignment cells), never the
    # AUTHORED assignment order -- reversing the two `.set(...)` calls below
    # (price before name, the opposite of Order's own slot order) emits
    # BYTE-IDENTICAL SQL to the natural order (mirrors `test_full_row_insert_
    # emits_the_entity_layout_slot_selection`'s own insert-side proof).
    # Eligibility is untouched: the target is still unversioned and
    # non-temporal, so the write stays readless.
    forward_port = ScriptedAdapter(Transact(Write()))

    def forward(tx: TxnContext) -> None:
        tx.amend_where(
            Order.where(Order.id == 100),
            Order.name.set("Hopper"),
            Order.price.set(Decimal("9.99")),
        )

    own_root(
        Database.connect(forward_port, ORDERS, clock=FixedClock(FIXED))
    ).using_database_login().transact(forward)

    reordered_port = ScriptedAdapter(Transact(Write()))

    def reordered(tx: TxnContext) -> None:
        tx.amend_where(
            Order.where(Order.id == 100),
            Order.price.set(Decimal("9.99")),
            Order.name.set("Hopper"),
        )

    own_root(
        Database.connect(reordered_port, ORDERS, clock=FixedClock(FIXED))
    ).using_database_login().transact(reordered)

    assert forward_port.calls == reordered_port.calls
    assert forward_port.calls == [
        BeginCall(),
        WriteCall(
            POSTGRES.to_driver_sql("update orders set name = ?, price = ? where id = ?"),
            ("Hopper", Decimal("9.99"), 100),
        ),
        CommitCall(),
    ]


def test_where_verb_rejects_a_query_that_is_not_mutation_compatible() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1).limit(1))

    with raises_contextualized(QueryDefinitionError) as caught:
        own_root(
            Database.connect(port, PERSON, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_where_verb_rejects_an_assignment_addressing_another_entity() -> None:
    # A set-based write assigns members of its exact target; an Assignment built
    # through another Entity of the same model names none.
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.amend_where(
            mm.Ticket.where(mm.Ticket.id == 1),
            mm.Badge.holder.set("Ada"),  # pyright: ignore[reportArgumentType]
        )

    with raises_contextualized(
        instructions.WriteInstructionError,
        match=r"'parallax\.compatibility\.Badge\.holder' does not name a declared member of "
        r"parallax\.compatibility\.Ticket",
    ):
        own_root(
            Database.connect(port, mm.PK_SEQUENCE_MODEL, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert not any(isinstance(op, (ReadCall, WriteCall)) for op in port.calls)


def test_one_member_is_assigned_once_in_a_predicate_selected_write() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.amend_where(
            mm.Person.where(mm.Person.id == 1),
            mm.Person.name.set("Ada"),
            mm.Person.name.set("Grace"),
        )

    with raises_contextualized(instructions.WriteInstructionError, match="is duplicated"):
        own_root(
            Database.connect(port, PERSON, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert not any(isinstance(op, (ReadCall, WriteCall)) for op in port.calls)


@dataclass(frozen=True, slots=True)
class _ClassSource:
    entities: tuple[UnresolvedEntityDeclaration, ...]


def _classless(model: DomainModel) -> DomainModel:
    """``model``'s Entities formed again with no Entity Class index, as a
    descriptor-backed model forms them."""
    classes = class_index(model)
    assert classes is not None
    return _Fixed._from_unresolved(  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam
        _ClassSource(tuple(cast("UnresolvedEntityDeclaration", cls) for cls in classes.by_class))
    )


def _unfinished(entity: type[Entity], *names: str, operands: tuple[object, ...]) -> Predicate[Any]:
    path = AuthoredPath(entity.identity, names, unfinished=True)
    return Predicate(UnfinishedOperation(path, COMPARE["eq"], operands))


def _amended(model: DomainModel | ServingModel, predicate: Predicate[Any]) -> ScriptedAdapter:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_where(mm.Person.where(predicate), mm.Person.name.set("Ada"))

    own_root(
        Database.connect(port, model, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    return port


def test_a_typed_predicate_write_binds_known_references_with_no_class_index() -> None:
    assert _amended(_classless(PERSON), mm.Person.id == 1).calls == (
        _amended(PERSON, mm.Person.id == 1).calls
    )


def test_a_typed_predicate_write_resolves_python_names_through_the_attempts_classes() -> None:
    assert _amended(PERSON, _unfinished(mm.Person, "id", operands=(1,))).calls == (
        _amended(PERSON, mm.Person.id == 1).calls
    )


def test_a_typed_predicate_write_binds_against_the_adopted_write_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A selection published after the attempt adopted its own does not serve the
    # attempt's predicate binding: the write borrows the attempt's write
    # projection, never the serving model's current one or a read projection.
    adopted = prepare_model(PERSON, edition="adopted")
    later = prepare_model(DomainModel(*cast("Any", class_index(PERSON)).by_class), edition="later")
    serving = ServingModel(adopted)
    bound: list[tuple[object, object]] = []
    bind = typed_interpretation

    def recording(predicate: Any, model: Any, classes: Any) -> Any:
        bound.append((model, classes))
        return bind(predicate, model, classes)

    monkeypatch.setattr(typed_writes, "typed_interpretation", recording)
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        serving.publish(later, expected=adopted)
        tx.amend_where(
            mm.Person.where(_unfinished(mm.Person, "id", operands=(1,))),
            mm.Person.name.set("Ada"),
        )

    own_root(
        Database.connect(port, serving, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    adopted_write = write_projection(adopted)
    assert bound == [(adopted_write.model.meta, adopted_write.classes)]
    assert adopted_write.classes is not write_projection(later).classes


def test_a_typed_predicate_write_over_python_names_is_refused_by_a_classless_model() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.amend_where(
            mm.Person.where(_unfinished(mm.Person, "id", operands=(1,))),
            mm.Person.name.set("Ada"),
        )

    with raises_contextualized(QueryDefinitionError, match="through Wire instead"):
        own_root(
            Database.connect(port, _classless(PERSON), clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert not any(isinstance(op, (ReadCall, WriteCall)) for op in port.calls)


# --------------------------------------------------------------------------- #
# The codec's effective-change comparison weighs each assigned member as the  #
# value the row would hold.                                                    #
# --------------------------------------------------------------------------- #


def _managed_subscriber_shape() -> MemberShape:
    meta = model_of(_WHERE_MANAGED_SUBSCRIBER_META)
    entity = next(
        entity
        for entity in _WHERE_MANAGED_SUBSCRIBER_META.entities
        if entity.identity.name == "WhereManagedSubscriber"
    )
    return comparison_shape(meta, entity)


def _no_op(shape: MemberShape, assigned: Mapping[str, object], row: tuple[object, ...]) -> bool:
    return not prepare_effective_change(shape, assigned, absent=ABSENT).any_effective(row)


def test_managed_scalar_operands_are_compared_as_the_host_values_the_row_holds() -> None:
    # A resolved row's scalars arrive from the shared Entity State in their declared
    # Neutral Type's managed carrier, and an assignment already carries one, so
    # preparation leaves both sides alone and the comparison weighs two host
    # values without an encode/decode round trip between them. Nothing on either
    # side is judged, so a stored value a current authoring constraint would reject
    # — a Decimal carrying more fractional digits than the declared scale — is
    # compared rather than refused, and the assignment correcting it is a change.
    shape = _managed_subscriber_shape()
    stored = {"amount": Decimal("19.95"), "day": dt.date(2026, 8, 13), "payload": b"\x0a\x1b"}
    row = positional_row(shape, stored, absent=ABSENT)

    assert _no_op(shape, stored, row)
    assert not _no_op(shape, {"payload": b"\x0a\x1c"}, row)
    assert not _no_op(shape, {"day": dt.date(2026, 8, 14)}, row)

    out_of_scale = positional_row(shape, {"amount": Decimal("19.9501")}, absent=ABSENT)
    assert not _no_op(shape, {"amount": Decimal("19.95")}, out_of_scale)


def test_a_no_op_occurrence_is_the_one_the_write_would_store_unchanged() -> None:
    # The operand the comparison weighs is the document the assignment would STORE:
    # preparation answers the whole subtree, because the write replaces it whole.
    # Naming only `city` is therefore a CHANGE against a row holding `geo` — issuing
    # it removes `geo`, so eliminating it would leave stored state the assignment
    # says is gone. The target declares Relational Document Layout, so both sides of
    # every comparison are document-resident.
    model = document_model()
    person = document_layout_entity(model, "Person")
    shape = comparison_shape(model, person)
    row = positional_row(
        shape,
        {
            "address": {"city": "Bergen", "geo": {"country": "NO"}},
            "tags": [{"label": "founder"}],
        },
        absent=ABSENT,
    )

    assert _no_op(
        shape,
        {"address": {"city": "Bergen", "geo": {"country": "NO"}}, "tags": [{"label": "founder"}]},
        row,
    )
    assert not _no_op(shape, {"address": {"city": "Bergen"}}, row)
    assert not _no_op(shape, {"address": {"city": "Oslo"}}, row)
    assert not _no_op(shape, {"tags": []}, row)


# --------------------------------------------------------------------------- #
# The behavioral mutation-compatibility rejection is covered end to end.        #
# `mutation_selection` refusing a clause-bearing query in `test_where_verbs.py` #
# is necessary but an actual `tx.update_where` or `tx.delete_where` call handed #
# one must itself raise the rejection, never merely be provable                 #
# through the seam alone. A port that raises on any I/O proves the guard runs   #
# BEFORE the connection is ever touched.                                        #
# --------------------------------------------------------------------------- #
def test_update_where_rejects_an_ordered_query_end_to_end() -> None:
    query = mm.Person.where(mm.Person.id == 1).order_by(mm.Person.id.asc())

    def fn(tx: TxnContext) -> None:
        tx.amend_where(query, mm.Person.name.set("Ada"))

    with raises_contextualized(QueryDefinitionError) as caught:
        own_root(
            Database.connect(ScriptedAdapter(Transact()), PERSON, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"


def test_delete_where_rejects_an_ordered_query_end_to_end() -> None:
    query = mm.Person.where(mm.Person.id == 1).order_by(mm.Person.id.asc())

    def fn(tx: TxnContext) -> None:
        tx.delete_where(query)

    with raises_contextualized(QueryDefinitionError) as caught:
        own_root(
            Database.connect(ScriptedAdapter(Transact()), PERSON, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"


def test_a_where_verb_never_classifies_deferred_execution_features() -> None:
    # Deferred Execution Feature classification belongs to modeled READ
    # execution. A predicate-selected write requires a mutation-compatible query
    # first, so the read-shaped clauses a deferral is recognized from are what
    # refuses this one — `query-not-mutation-compatible`, never
    # `execution-feature-deferred`, whichever the query would also have matched.
    query = Policy.where(Policy.all).history(TX_TIME).include(Policy.coverages)

    def fn(tx: TxnContext) -> None:
        tx.delete_where(query)

    with raises_contextualized(QueryDefinitionError) as caught:
        own_root(
            Database.connect(ScriptedAdapter(Transact()), POLICY_MODEL, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"


def test_update_where_refuses_a_target_the_connected_model_does_not_declare() -> None:
    # A write target is resolved by write preparation, the one boundary every
    # write crosses, so it is refused as the write it is: naming the authored
    # Entity and the connected model that declares none. It precedes buffering
    # and every adapter touch.
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.amend_where(mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"))

    with raises_contextualized(
        instructions.WriteInstructionError,
        match=r"^the connected model declares no entity 'parallax\.compatibility\.Person' "
        "for this write$",
    ):
        own_root(
            Database.connect(port, ACCOUNT, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert not any(isinstance(op, (ReadCall, WriteCall)) for op in port.calls)


def test_a_read_of_a_target_the_connected_model_does_not_declare_keeps_its_refusal() -> None:
    def fn(tx: TxnContext) -> None:
        tx.find(mm.Person.where(mm.Person.id == 1))

    with raises_contextualized(QueryTargetError) as caught:
        own_root(
            Database.connect(ScriptedAdapter(Transact()), ACCOUNT, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert caught.value.code == "query-target-not-in-model"


# --------------------------------------------------------------------------- #
# The selecting predicate is a canonical Predicate node and carries the WHOLE  #
# model-aware validation vocabulary, not just the rules the write instruction  #
# itself states. Authoring reaches no model, so a `_where` verb is the only    #
# place these can be enforced on a predicate-selected write; the two rules     #
# below come from different families so the pin covers the vocabulary rather   #
# than one rule.                                                               #
# --------------------------------------------------------------------------- #
def test_update_where_refuses_an_inverted_between_window_before_any_sql() -> None:
    def fn(tx: TxnContext) -> None:
        tx.amend_where(mm.Person.where(mm.Person.id.between(10, 1)), mm.Person.name.set("Ada"))

    with raises_contextualized(ModelRejectedError) as caught:
        own_root(
            Database.connect(ScriptedAdapter(Transact()), PERSON, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert caught.value.rule == "between-bounds-inverted"


def test_delete_where_refuses_an_attribute_outside_the_written_position() -> None:
    # A second rule family — the positional reference check — over the same
    # connected model, which declares both Entities and relates them.
    def fn(tx: TxnContext) -> None:
        tx.delete_where(mm.Person.where(mm.Passport.number == "X"))  # pyright: ignore[reportArgumentType]

    with raises_contextualized(ModelRejectedError) as caught:
        own_root(
            Database.connect(ScriptedAdapter(Transact()), PERSON, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert caught.value.rule == "attribute-outside-active-position"


# --------------------------------------------------------------------------- #
# A target that needs an observation — versioned, Transaction-Time-Only, or    #
# Bitemporal — is refused at the call, in both representations, before the    #
# port is touched (`m-batch-write`). The exact advice for every verb and kind  #
# is `test_predicate_write_order.py`'s subject.                                #
# --------------------------------------------------------------------------- #
_OBSERVED_TARGETS: Final[list[tuple[str, DomainModel, Callable[[TxnContext], object]]]] = [
    (
        "versioned",
        MODELS["account"],
        lambda tx: tx.amend_where(
            Account.where(Account.balance < Decimal("200.00")),
            Account.balance.set(Decimal("0.00")),
        ),
    ),
    (
        "transaction-time",
        MODELS["balance"],
        lambda tx: tx.delete_where(Balance.where(Balance.acct_num == "A-1")),
    ),
    (
        "bitemporal",
        MODELS["position"],
        lambda tx: tx.wire.delete_where(
            {
                "entity": "Position",
                "predicate": {"eq": {"path": "Position.acctNum", "value": "A-1"}},
            }
        ),
    ),
]


@pytest.mark.parametrize(
    ("model", "write"),
    [(model, write) for _kind, model, write in _OBSERVED_TARGETS],
    ids=[kind for kind, _model, _write in _OBSERVED_TARGETS],
)
def test_a_predicate_write_needing_an_observation_is_refused_at_the_call(
    model: DomainModel, write: Callable[[TxnContext], None]
) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(instructions.InstructionRejectedError) as refused:
            write(tx)
        assert refused.value.rule == instructions.SET_BASED_WRITE_TARGET_UNSUPPORTED
        assert port.calls == [BeginCall()]
        raise _Abandon

    with raises_contextualized(_Abandon):
        own_root(
            Database.connect(port, model, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)


# --------------------------------------------------------------------------- #
# The conformance engine's OWN ingress, driven as the engine drives it: the     #
# readless entry point (`_run_readless_predicate_write`, which opens the        #
# transaction itself and states its write through `tx.wire.*_where`) prepares   #
# the case's own instruction first, so a lane that stopped judging its own      #
# target fails these cases. Driving preparation from the test instead would     #
# leave that regression unpinned: the refusal would then come from the test,    #
# not from the engine.                                                          #
#                                                                               #
# The model is the corpus's own `models/wallet.yaml` (m-batch-write-005). The   #
# predicates cover both refusal families a write target carries: the            #
# model-aware `between-bounds-inverted` rejection, and a node the Predicate     #
# grammar does not admit at all — every query-wide clause is an Object Query    #
# clause now, so a write target carrying one is a malformed document rather    #
# than a rule a validator applies.                                              #
# --------------------------------------------------------------------------- #
_READLESS_ENGINE_META = engine.load_case_metamodel(corpus_case("m-batch-write-005"))


def _refused_predicates(entity: str) -> list[tuple[str, str, dict[str, object]]]:
    return [
        ("between", "upper bound", {"between": {"path": f"{entity}.id", "lower": 10, "upper": 1}}),
        (
            "unknown-node",
            "unknown predicate node 'limit'",
            {"limit": {"operand": {"true": {}}, "count": 1}},
        ),
    ]


_READLESS_REFUSALS = _refused_predicates("Wallet")


@pytest.mark.parametrize(
    ("message", "predicate"),
    [(message, predicate) for _id, message, predicate in _READLESS_REFUSALS],
    ids=[case_id for case_id, _message, _predicate in _READLESS_REFUSALS],
)
def test_the_engines_readless_case_adapter_refuses_before_execution(
    message: str, predicate: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        scenario._prepared_case_predicate_write(  # pyright: ignore[reportPrivateUsage] - the scenario lane's case-format preparation ingress
            {"mutation": "delete", "target": {"entity": "Wallet", "predicate": predicate}},
            _READLESS_ENGINE_META,
        )


# The WIRE predicate ingress's OWN validation, driven the way the conformance
# engine drives it — a canonical target NOTHING pre-validated, straight into
# `tx.wire.delete_where`. That ingress lowers to the same
# `PredicateWriteInstruction` the Typed verbs build and validates it exactly as
# they do, so deleting its prepared-write call fails this case.
#
# The refusal is asserted at the verb CALL, inside the transaction body, which
# is what makes it discriminating: unvalidated, the family instruction is merely
# buffered and the call returns — the planner's flush-time refusal would come
# later, and never at all on the abandoned transaction here.
def test_the_wire_predicate_ingress_refuses_an_unvalidated_inheritance_family_target() -> None:
    target: dict[str, object] = {
        "entity": "CardPayment",
        "predicate": {"eq": {"path": "CardPayment.id", "value": 1}},
    }
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(
            inheritance.InheritanceError, match="subtype-write-set-based-unsupported"
        ):
            tx.wire.delete_where(target)
        assert port.calls == [BeginCall()]
        raise _Abandon

    with raises_contextualized(_Abandon):
        own_root(
            Database.connect(port, PAYMENT, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)


# A family instruction never reaches the buffering seam: the one producer of
# prepared writes refuses it, so no seam re-judges the family. A family that
# needs an observation hears that refusal first.
@pytest.mark.parametrize(
    ("model", "entity", "rule"),
    [
        (PAYMENT, "CardPayment", "subtype-write-set-based-unsupported"),
        (RATE, "DepositRate", instructions.SET_BASED_WRITE_TARGET_UNSUPPORTED),
    ],
    ids=["unversioned-family", "bitemporal-family"],
)
def test_preparation_refuses_an_inheritance_family_predicate_instruction(
    model: DomainModel, entity: str, rule: str
) -> None:
    instruction = instructions.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": entity,
                "predicate": {"eq": {"path": f"{entity}.id", "value": 1}},
            },
        }
    )
    assert isinstance(instruction, PredicateWriteInstruction)
    with pytest.raises(
        (inheritance.InheritanceError, instructions.InstructionRejectedError)
    ) as refused:
        instructions.prepare_wire_write(instruction, model_of(model))
    assert refused.value.rule == rule


class _Abandon(Exception):
    """Abandons the transaction once the refusal at the verb is proven, so
    nothing the transaction holds has to become a valid committed write."""


def test_a_positional_rows_absent_marker_is_compared_as_itself_never_as_the_observed_null() -> None:
    # A member the row holds as null is the observed null, and a null assignment
    # restores it. A position the read left ABSENT is not: the marker is a
    # present value the comparison weighs as itself, so a null assignment against
    # it is a change rather than a no-op.
    meta = model_of(_WHERE_VOYAGE_META)
    entity = next(entity for entity in meta.entities if entity.identity.name == "WhereVoyage")
    shape = comparison_shape(meta, entity)
    layout = LayoutCatalog(meta).entity(entity.identity)
    assert layout.member_selection.shape is shape
    tx_start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)

    def positional(title: object) -> tuple[object, ...]:
        return (1, title, tx_start, INFINITY, ("grain",))

    assert _no_op(shape, {"title": None}, positional(None))
    assert not _no_op(shape, {"title": None}, positional(ABSENT))
    assert not _no_op(shape, {"title": None}, positional("Coastal Run"))
    assert _no_op(shape, {"manifest": {"cargo": "grain"}}, positional(None))
