"""What composition binds, and what a model still refuses.

Composing an Entity Class into a Domain Model binds nothing, so the same class
participates in as many models as compose it, one model connects to as many
Databases as connect to it, and query authoring reaches no model at all. Those
are the properties this suite pins, together with the two refusals a model does
own: a model that names no Entity Class cannot serve a Snapshot, and a query
target the connected model does not declare is refused before any I/O.

A Typed query holds one authored tree and no canonical node, and each operation
resolves that tree against the model it adopted: prepared operands are adopted
only under the exact type they were prepared for, and Python member names
resolve only through the serving model's own Entity Classes.

The assignment half is here too. Extracting the judgement is what lets the typed
path state its whole rule without a model, so the parity between it and the
serialized write boundary is the property that must not have moved.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
from collections.abc import Iterator, Mapping
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import (
    Attr,
    DomainModel,
    EditError,
    EditViolation,
    Entity,
    Float32,
    Predicate,
    QueryDefinitionError,
    TxTemporal,
    attr,
    inheritance,
)
from parallax.core.base import Decimal as NeutralDecimal
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import _expressions
from parallax.core.entity._expressions import (
    AuthoredConstant,
    AuthoredQuery,
    PreparedOperation,
    UnfinishedOperation,
    canonical_predicate,
)
from parallax.core.entity._model import DomainModel as _Fixed
from parallax.core.entity._model import model_of
from parallax.core.execution import QueryTargetError
from parallax.core.execution._preflight import preflight
from parallax.core.metamodel import (
    UnresolvedEntityDeclaration,
    WriteAssignmentError,
    judge_assignment,
)
from parallax.core.object_query._fluent import object_query_node, typed_read_query
from parallax.core.predicate import PredicateNode, validate
from parallax.core.predicate._interpretation import COMPARE, MEMBER_OF, ScalarOperator
from parallax.core.predicate._resolved import ResolvedComparison
from parallax.snapshot import Database, ScopedDatabase, SnapshotConnectionError, Transaction
from tests._support import snapshot_models as sm
from tests._support import value_object_models as vm
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RefusingAdapter,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.query_probes import predicate_node, typed_resolved
from tests._support.root_ownership import own_root
from tests.unit._transact_support import FIXED

_NS = "parallax.compatibility"
_INSTANT = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


class Widget(Entity, table="widget", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)
    computed: Attr[str | None] = attr(max_length=16, read_only=True)


class Gadget(TxTemporal, table="gadget", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class Gizmo(Entity, table="gizmo", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)


class Priced(Entity, table="priced", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=10, scale=2)
    ratio: Attr[float] = attr(type=Float32)
    display: Attr[str] = attr(name="label", max_length=16)


# A second declaration of the SAME Entity Identity, its scalar types differing
# only in Decimal scale and float width.
class Repriced(Entity, table="priced", name="Priced", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=10, scale=3)
    ratio: Attr[float]
    display: Attr[str] = attr(name="label", max_length=16)


# The SAME `Widget` class object composed into two models: a class names an
# Entity of every model that composed it, so both of these are authoritative.
WIDGETS = DomainModel(Widget)
WIDGETS_AND_GIZMOS = DomainModel(Widget, Gizmo)
GADGETS = DomainModel(Gadget)
PRICED = DomainModel(Priced)
REPRICED = DomainModel(Repriced)


class _Source:
    """A minimal Unresolved Metamodel composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (Gizmo,)


# The one Domain Model provenance that composes no Entity Class, and therefore
# the only connection left that cannot materialize a Snapshot.
CLASSLESS = _Fixed._from_unresolved(_Source())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam


def _db(model: DomainModel, adapter: DatabaseAdapter) -> ScopedDatabase:
    return own_root(
        Database.connect(adapter, model, clock=FixedClock(FIXED))
    ).using_database_login()


# --------------------------------------------------------------------------- #
# One class, several models                                                    #
# --------------------------------------------------------------------------- #
def test_one_entity_class_is_queried_through_every_model_that_composed_it() -> None:
    narrow_port, wide_port = ScriptedAdapter(Read(rows=[])), ScriptedAdapter(Read(rows=[]))
    query = Widget.where(Widget.id == 1)

    _db(WIDGETS, narrow_port).find(query)
    _db(WIDGETS_AND_GIZMOS, wide_port).find(query)

    assert [type(op) for op in narrow_port.calls] == [ReadCall]
    assert narrow_port.calls == wide_port.calls


def test_one_entity_class_is_written_through_every_model_that_composed_it() -> None:
    for model in (WIDGETS, WIDGETS_AND_GIZMOS):
        port = ScriptedAdapter(Transact(Write()))

        def insert(tx: Transaction) -> None:
            tx.insert(Widget(id=1, label="x"))

        _db(model, port).transact(insert)
        assert [type(op) for op in port.calls] == [BeginCall, WriteCall, CommitCall]


def test_one_domain_model_serves_every_database_connected_to_it() -> None:
    first, second = ScriptedAdapter(Read(rows=[])), ScriptedAdapter(Read(rows=[]))
    query = Widget.where(Widget.id == 1)

    _db(WIDGETS, first).find(query)
    _db(WIDGETS, second).find(query)

    assert first.calls == second.calls


def test_a_query_whose_target_the_connected_model_does_not_declare_is_refused() -> None:
    # Authoring reaches no model, so the query builds; the connected model is
    # what answers, and it answers before any adapter activity.
    port = RefusingAdapter()
    database = own_root(
        Database.connect(port, DomainModel(Gizmo), clock=FixedClock(FIXED))
    ).using_database_login()
    with pytest.raises(QueryTargetError) as caught:
        database.find(Widget.where(Widget.id == 1))
    assert caught.value.code == "query-target-not-in-model"


# --------------------------------------------------------------------------- #
# What a Database still requires of its model                                  #
# --------------------------------------------------------------------------- #
def test_connect_accepts_a_descriptor_backed_model_and_refuses_typed_reads() -> None:
    # Which Domain Model provenance a caller connected decides capability, not
    # which constructor ran: a descriptor-backed model connects and serves Wire,
    # and only the Typed read it cannot materialize is refused — at the read
    # call, before any I/O, which the raising port proves.
    descriptor_backed = _Fixed._from_unresolved(_Source())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam
    database = own_root(
        Database.connect(RefusingAdapter(), descriptor_backed, clock=FixedClock(FIXED))
    ).using_database_login()
    with pytest.raises(SnapshotConnectionError) as caught:
        database.find(Gizmo.where(Gizmo.id == 1))
    assert caught.value.code == "snapshot-class-backed-model-required"

    # And the Wire read the same connection DOES serve runs end to end: the
    # capability is an executed read rather than a reachable namespace.
    served = own_root(
        Database.connect(
            ScriptedAdapter(Read(rows=[{"id": 1}])), descriptor_backed, clock=FixedClock(FIXED)
        )
    ).using_database_login()
    published = served.wire.find({"target": "Gizmo", "predicate": {"all": {}}}).result()
    assert published == {"id": 1}


def test_both_connection_doors_refuse_a_bare_accepted_metamodel() -> None:
    # A connection reaches its accepted model through a Domain Model and no
    # other way, so a bare accepted Metamodel names no model either door can
    # serve. `connect` — the developer entry point — answers in its own words,
    # and the constructor beneath it refuses the same shape rather than failing
    # on an attribute a Metamodel does not carry.
    with pytest.raises(SnapshotConnectionError) as caught:
        own_root(
            Database.connect(
                RefusingAdapter(),
                model_of(WIDGETS),  # pyright: ignore[reportArgumentType] - the runtime narrowing is what this proves
                clock=FixedClock(FIXED),
            )
        ).using_database_login()
    assert caught.value.code == "snapshot-class-backed-model-required"

    with pytest.raises(SnapshotConnectionError) as constructed:
        own_root(
            Database(
                RefusingAdapter(),
                model_of(WIDGETS),  # pyright: ignore[reportArgumentType] - the runtime narrowing is what this proves
                clock=FixedClock(FIXED),
            )
        ).using_database_login()
    assert constructed.value.code == "snapshot-class-backed-model-required"


def test_a_classless_database_refuses_a_read_before_it_resolves_the_target() -> None:
    # The connection refusal precedes preflight on BOTH entry points. A Database
    # that cannot materialize a Snapshot answers that first, so a query this
    # model also does not declare still reports the connection rather than the
    # target.
    port = ScriptedAdapter()
    database = own_root(
        Database.connect(port, CLASSLESS, clock=FixedClock(FIXED))
    ).using_database_login()
    with pytest.raises(SnapshotConnectionError) as caught:
        database.find(Widget.where(Widget.id == 1))
    assert caught.value.code == "snapshot-class-backed-model-required"
    assert port.calls == []


def test_a_classless_transaction_writes_and_refuses_a_read_before_it_can_force_flush() -> None:
    # The write lanes name Entities rather than classes, so they run against a
    # model that composed none; the read that would have to instantiate one is
    # refused before the force-flush its gate stands in front of, so the write
    # buffered beside it is still only buffered when the refusal lands.
    port = ScriptedAdapter(Transact(Write()))
    database = own_root(
        Database.connect(port, CLASSLESS, clock=FixedClock(FIXED))
    ).using_database_login()

    def body(tx: Transaction) -> None:
        tx.insert(Gizmo(id=1))
        with pytest.raises(SnapshotConnectionError):
            tx.find(Gizmo.where(Gizmo.id == 1))
        assert [type(op) for op in port.calls] == [BeginCall]

    database.transact(body)
    assert [type(op) for op in port.calls] == [BeginCall, WriteCall, CommitCall]


def test_every_typed_read_door_states_one_classless_refusal() -> None:
    # What cannot materialize a Snapshot is the model the read is served under,
    # not the Handle the caller reached it through, so all four Typed doors
    # render ONE message under one stable code rather than a Database spelling
    # beside a Transaction one. Each lands before its own statement: the
    # standalone pair refuses a port that permits nothing at all, and the
    # participating pair leaves an opened transaction with no read on it.
    refusal = (
        "this read is served under a model that composed no Entity Class, so it cannot "
        "materialize a Snapshot (snapshot-class-backed-model-required)"
    )
    query = Gizmo.where(Gizmo.id == 1)
    doors: list[SnapshotConnectionError] = []

    standalone = own_root(
        Database(RefusingAdapter(), CLASSLESS, clock=FixedClock(FIXED))
    ).using_database_login()
    with pytest.raises(SnapshotConnectionError) as eager:
        standalone.find(query)
    doors.append(eager.value)
    with pytest.raises(SnapshotConnectionError) as streamed:
        standalone.stream(query).__enter__()
    doors.append(streamed.value)

    def read_inside(tx: Transaction) -> None:
        with pytest.raises(SnapshotConnectionError) as participating_eager:
            tx.find(query)
        doors.append(participating_eager.value)
        with pytest.raises(SnapshotConnectionError) as participating_stream:
            tx.stream(query).__enter__()
        doors.append(participating_stream.value)

    port = ScriptedAdapter(Transact())
    own_root(
        Database.connect(port, CLASSLESS, clock=FixedClock(FIXED))
    ).using_database_login().transact(read_inside)

    assert [str(door) for door in doors] == [refusal] * 4
    assert [door.code for door in doors] == ["snapshot-class-backed-model-required"] * 4
    assert [type(op) for op in port.calls] == [BeginCall, CommitCall]


# --------------------------------------------------------------------------- #
# One judgement, three callers                                                 #
# --------------------------------------------------------------------------- #
def _typed_violation(entity: type[Entity], member: str, value: object) -> EditViolation | None:
    """What ``.set(...)`` says about ``value``, or absence — the member alone."""
    try:
        getattr(entity, member).set(value)
    except EditError as error:
        return _sole(error)
    return None


def _model_judgement(model: DomainModel, entity: type[Entity], member: str, value: object) -> None:
    """The shared judgement over the model's family-effective member, qualified
    with the addressed Entity as the write boundary qualifies it."""
    metadata = model.meta(entity)
    position = inheritance.view(model_of(model)).entity(metadata.identity)
    assert position is not None
    resolved = position.member_selection.binding(member)
    assert resolved is not None
    try:
        judge_assignment(resolved, value)
    except WriteAssignmentError as error:
        raise WriteAssignmentError(error.rule, f"{metadata.identity.canonical}.{error}") from error


def _boundary_verdict(
    model: DomainModel, entity: type[Entity], member: str, value: object
) -> str | None:
    """The same, through the write boundary's own family-effective resolution."""
    try:
        _model_judgement(model, entity, member, value)
    except WriteAssignmentError as error:
        return str(error)
    return None


def _edit_violation(instance: Entity, member: str, value: object) -> EditViolation | None:
    """The same, through ``edit(**changes)``'s own name resolution."""
    try:
        instance.edit(**{member: value})
    except EditError as error:
        return _sole(error)
    return None


def _sole(error: EditError) -> EditViolation:
    """The one violation a single-target refusal reports."""
    assert len(error.violations) == 1
    return error.violations[0]


@pytest.mark.parametrize(
    ("member", "value"),
    [
        pytest.param("id", 1, id="primary-key"),
        pytest.param("version", 1, id="framework-owned"),
        pytest.param("computed", "x", id="read-only"),
        pytest.param("label", 42, id="value-type-mismatch"),
        pytest.param("label", None, id="required-attribute-cleared"),
        pytest.param("computed", None, id="nullable-member-cleared"),
        pytest.param("label", "x", id="accepted"),
    ],
)
def test_every_assignment_surface_reaches_one_verdict(member: str, value: object) -> None:
    # Only the resolution in front of the judgement differs between the three
    # callers, so all of them reach the same verdict AND render it identically —
    # which is what "one validator" means once the model has disappeared from
    # two of them. `edit(...)` is in this comparison because an edited value
    # becomes a write: a rule it does not apply is a rule the write path is
    # entered around.
    boundary = _boundary_verdict(WIDGETS, Widget, member, value)
    typed = _typed_violation(Widget, member, value)
    edited = _edit_violation(Widget(id=1, label="x"), member, value)
    assert typed == edited
    assert (typed.message if typed is not None else None) == boundary


def test_every_assignment_surface_refuses_a_temporal_endpoint_the_same_way() -> None:
    # The second designated category, which no surface can see from the
    # Attribute's own authored flags: the endpoint carries none, and only the
    # Entity's As-Of Axis says it is framework-owned. The three surfaces still
    # render one verdict, which is what deriving the designation at declaration
    # rather than at acceptance buys.
    boundary = _boundary_verdict(GADGETS, Gadget, "txStart", _INSTANT)
    assert boundary == (
        "parallax.compatibility.Gadget.txStart: framework-owned fields may not be assigned"
    )
    typed = _typed_violation(Gadget, "tx_start", _INSTANT)
    edited = _edit_violation(Gadget(id=1, label="x"), "tx_start", _INSTANT)
    assert typed == edited
    assert typed is not None
    assert typed.message == boundary
    assert typed.code == "edit-framework-owned"


def test_a_rejection_still_says_which_of_the_three_designations_it_is() -> None:
    # Three distinct designations, so the classification distinguishes an
    # Attribute the framework supplies, one the caller supplies once, and the
    # key that addresses the row — none of them collapsed into the others.
    rules: list[str] = []
    for member, value in (("version", 1), ("computed", "x"), ("id", 1)):
        with pytest.raises(WriteAssignmentError) as caught:
            _model_judgement(WIDGETS, Widget, member, value)
        rules.append(caught.value.rule)
    assert rules == ["framework-owned", "read-only", "primary-key"]


def test_every_surface_classifies_a_read_only_member_the_same_way() -> None:
    # The rule the Python specification states and the implementation never
    # applied. It lands in the extracted judgement, so one edit gave it to all
    # three surfaces, including the edited copy that would otherwise carry a
    # changed read-only value into `tx.update`.
    with pytest.raises(EditError, match="read-only fields may not be assigned"):
        Widget.computed.set("x")
    with pytest.raises(EditError, match="read-only fields may not be assigned"):
        Widget(id=1, label="x").edit(computed="x")
    with pytest.raises(WriteAssignmentError) as caught:
        _model_judgement(WIDGETS, Widget, "computed", "x")
    assert caught.value.rule == "read-only"


# --------------------------------------------------------------------------- #
# One authored tree, no canonical backing                                      #
# --------------------------------------------------------------------------- #
def _reachable(value: object) -> Iterator[object]:
    """Every value reachable from ``value`` through dataclass fields, tuples,
    and mappings, ``value`` included."""
    yield value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from _reachable(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            yield from _reachable(item)  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(value, Mapping):
        for item in value.values():  # pyright: ignore[reportUnknownVariableType]
            yield from _reachable(item)  # pyright: ignore[reportUnknownArgumentType]


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(Widget.where(Widget.id == 1), id="where"),
        pytest.param(Widget.where(Widget.all), id="all"),
        pytest.param(
            sm.Animal.where(sm.Animal.narrow(sm.Dog, where=sm.Dog.bark_volume > 5)),
            id="whole-query-narrowing",
        ),
        pytest.param(
            vm.Customer.where(vm.Customer.address.phones.exists(vm.Phone.type == "home")),
            id="value-object-scope",
        ),
        pytest.param(sm.SnapOrder.where(sm.SnapOrder.items.exists()), id="relationship"),
    ],
)
def test_a_typed_query_retains_its_authored_state_and_no_canonical_node(query: Any) -> None:
    reached = list(_reachable(query))
    assert not [value for value in reached if isinstance(value, PredicateNode)]
    assert any(isinstance(value, AuthoredQuery) for value in reached)


def test_where_all_and_whole_query_narrowing_keep_their_authored_meaning() -> None:
    assert typed_read_query(Widget.where(Widget.all)).predicate == AuthoredConstant(truth=True)
    lifted = typed_read_query(
        sm.Animal.where(sm.Animal.narrow(sm.Dog, where=sm.Dog.bark_volume > 5))
    )
    assert lifted.narrow_to == ("parallax.compatibility.Dog",)
    assert isinstance(lifted.predicate, PreparedOperation)


def test_a_prepared_operation_retains_managed_operands_and_their_preparation_type() -> None:
    authored = (Priced.amount == Decimal("1.5")).authored
    assert isinstance(authored, PreparedOperation)
    assert authored.operands == (Decimal("1.50"),)
    assert authored.prepared_type == NeutralDecimal(precision=10, scale=2)


def test_membership_captures_its_entries_in_an_owned_tuple() -> None:
    entries: list[object] = [1, 2]
    predicate = Widget.id.in_(entries)
    entries.append(3)
    entries[0] = 99
    assert predicate_node(predicate) == predicate_node(Widget.id.in_([1, 2]))


def test_authoring_and_typed_binding_neither_encode_nor_decode_operands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object) -> object:
        raise AssertionError("a Typed operand crossed a Wire codec on its way to execution")

    monkeypatch.setattr(_expressions, "encode_wire", refuse)
    monkeypatch.setattr(validate, "decode_wire", refuse)
    query = Priced.where((Priced.amount == Decimal("1.5")) & Priced.id.in_([1, 2]))
    port = ScriptedAdapter(Read(rows=[]))
    _db(PRICED, port).find(query)
    assert [type(call) for call in port.calls] == [ReadCall]


# --------------------------------------------------------------------------- #
# Binding against the adopted model                                            #
# --------------------------------------------------------------------------- #
def test_one_authored_query_is_served_by_class_backed_and_classless_models() -> None:
    # The classless model indexes no Entity Class, and the query names only
    # declared facts, so both models resolve it to the same statement.
    query = Gizmo.where(Gizmo.id == 1)
    backed, classless = ScriptedAdapter(Read(rows=[])), ScriptedAdapter(Read(rows=[]))
    _db(WIDGETS_AND_GIZMOS, backed).wire.find(query)
    _db(CLASSLESS, classless).wire.find(query)
    assert [type(call) for call in backed.calls] == [ReadCall]
    assert backed.calls == classless.calls


@pytest.mark.parametrize(
    "predicate",
    [
        pytest.param(Priced.amount == Decimal("1.25"), id="decimal-scale"),
        pytest.param(Priced.ratio > 0.5, id="float-width"),
    ],
)
def test_a_prepared_operand_is_refused_under_another_declared_type_before_io(
    predicate: Predicate[Priced],
) -> None:
    # Repriced declares the same member under another type; the operand already
    # rounded to Priced's declaration is not re-normalized for it.
    database = _db(REPRICED, RefusingAdapter())
    with pytest.raises(QueryDefinitionError, match="prepared for NeutralType") as caught:
        database.find(Priced.where(predicate))
    assert caught.value.code == "query-expression-invalid"


class _Level(enum.IntEnum):
    ONE = 1


class _Label(enum.StrEnum):
    X = "x"


def _carriers(predicate: object) -> tuple[tuple[type, object], ...]:
    operands: list[object] = [
        getattr(predicate, name) for name in ("value", "lower", "upper") if hasattr(predicate, name)
    ]
    operands.extend(cast("tuple[object, ...]", getattr(predicate, "values", ())))
    return tuple(
        (type(operand), operand.as_tuple() if isinstance(operand, Decimal) else operand)
        for operand in operands
    )


@pytest.mark.parametrize(
    ("query", "model"),
    [
        pytest.param(Priced.where(Priced.amount == 1), PRICED, id="integer-for-decimal"),
        pytest.param(
            Priced.where(Priced.amount.between(Decimal(1), Decimal("2.500"))),
            PRICED,
            id="decimal-exponents",
        ),
        pytest.param(
            Priced.where(Priced.amount.in_([1, Decimal("2.5")])), PRICED, id="decimal-membership"
        ),
        pytest.param(Widget.where(Widget.id == _Level.ONE), WIDGETS, id="integer-enum"),
        pytest.param(Widget.where(Widget.label == _Label.X), WIDGETS, id="string-enum"),
    ],
)
def test_a_prepared_operand_binds_the_carrier_its_canonical_export_decodes_to(
    query: Any, model: DomainModel
) -> None:
    canonical = preflight(object_query_node(query), model=model_of(model), form="graph")
    typed = typed_resolved(query, model)
    assert _carriers(typed.predicate) == _carriers(canonical.predicate)


def test_a_prepared_operand_is_adopted_under_the_identical_declared_type() -> None:
    resolved = typed_resolved(Priced.where(Priced.display == "x"), REPRICED).predicate
    assert isinstance(resolved, ResolvedComparison)
    assert resolved.member is REPRICED.meta(Repriced).attribute("label")
    assert resolved.value == "x"


# --------------------------------------------------------------------------- #
# Unfinished operations                                                        #
# --------------------------------------------------------------------------- #
def _unfinished(
    entity: type[Entity],
    *names: str,
    operands: tuple[object, ...],
    operator: ScalarOperator = COMPARE["eq"],
) -> Predicate[Any]:
    return Predicate(UnfinishedOperation(entity.identity, names, operator, operands))


@pytest.mark.parametrize(
    ("root", "unfinished", "known", "model"),
    [
        pytest.param(
            Priced,
            _unfinished(Priced, "display", operands=("x",)),
            Priced.display == "x",
            PRICED,
            id="renamed",
        ),
        pytest.param(
            sm.Dog,
            _unfinished(sm.Dog, "owner_id", operands=(7,)),
            sm.Dog.owner_id == 7,
            sm.ANIMAL_MODEL,
            id="inherited",
        ),
        pytest.param(
            vm.Customer,
            _unfinished(vm.Customer, "address", "geo", "country", operands=("NO",)),
            vm.Customer.address.geo.country == "NO",
            vm.CUSTOMER_MODEL,
            id="value-object-path",
        ),
        pytest.param(
            Priced,
            _unfinished(Priced, "amount", operator=MEMBER_OF["in"], operands=(Decimal("1.5"), 2)),
            Priced.amount.in_([Decimal("1.5"), 2]),
            PRICED,
            id="native-operands-prepared-once",
        ),
    ],
)
def test_an_unfinished_operation_resolves_through_the_serving_models_classes(
    root: type[Entity], unfinished: Predicate[Any], known: Predicate[Any], model: DomainModel
) -> None:
    assert typed_resolved(root.where(unfinished), model) == typed_resolved(root.where(known), model)


def test_an_unfinished_operation_is_refused_by_a_model_indexing_no_classes() -> None:
    database = _db(CLASSLESS, RefusingAdapter())
    with pytest.raises(QueryDefinitionError, match="through Wire instead") as caught:
        database.wire.find(Gizmo.where(_unfinished(Gizmo, "id", operands=(1,))))
    assert caught.value.code == "query-expression-invalid"


@pytest.mark.parametrize(
    ("names", "operands", "code", "message"),
    [
        pytest.param(("missing",), (1,), "query-path-invalid", "declares no member", id="unknown"),
        pytest.param(
            ("id", "deeper"), (1,), "query-path-invalid", "path continues", id="past-a-scalar"
        ),
        pytest.param(("amount",), (None,), "query-expression-invalid", "None", id="null-operand"),
        pytest.param(
            ("amount",), (object(),), "query-expression-invalid", "input policy", id="carrier"
        ),
    ],
)
def test_an_unfinished_operation_is_refused_at_binding_before_io(
    names: tuple[str, ...], operands: tuple[object, ...], code: str, message: str
) -> None:
    database = _db(PRICED, RefusingAdapter())
    with pytest.raises(QueryDefinitionError, match=message) as caught:
        database.find(Priced.where(_unfinished(Priced, *names, operands=operands)))
    assert caught.value.code == code


def test_an_unfinished_relationship_name_is_not_traversed_by_a_scalar_operation() -> None:
    with pytest.raises(QueryDefinitionError, match="is a relationship") as caught:
        typed_resolved(
            sm.SnapOrder.where(_unfinished(sm.SnapOrder, "items", operands=(1,))),
            sm.SNAP_ORDERS_MODEL,
        )
    assert caught.value.code == "query-path-invalid"


def test_an_unfinished_operation_has_no_canonical_export() -> None:
    with pytest.raises(QueryDefinitionError, match="no canonical form"):
        canonical_predicate(_unfinished(Priced, "amount", operands=(1,)).authored)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            vm.Customer.where(
                vm.Customer.address.phones.exists(
                    ((vm.Phone.type == "home") & (vm.Phone.number == "1")) | ~(vm.Phone.type == "x")
                )
            ),
            id="element-scope",
        ),
        pytest.param(
            vm.Customer.where(
                vm.Customer.address.phones.exists(
                    ((vm.Phone.type == "home") | (vm.Phone.type == "work"))
                    & (vm.Phone.number == "1")
                )
            ),
            id="element-scope-grouping",
        ),
        pytest.param(
            vm.Customer.where(
                ~(vm.Customer.name == "Ada") | ((vm.Customer.id > 1) & (vm.Customer.id < 9))
            ),
            id="entity-position",
        ),
        pytest.param(
            vm.Customer.where(vm.Customer.address.phones.not_exists()),
            id="bare-value-object-scope",
        ),
    ],
)
def test_boolean_structure_binds_as_its_canonical_export_does(query: Any) -> None:
    canonical = preflight(object_query_node(query), model=model_of(vm.CUSTOMER_MODEL), form="graph")
    assert typed_resolved(query, vm.CUSTOMER_MODEL) == canonical


@pytest.mark.parametrize(
    "interior",
    [
        pytest.param(vm.Customer.name == "Ada", id="entity-rooted-attribute"),
        pytest.param(
            _unfinished(vm.Customer, "name", operands=("Ada",)), id="unfinished-operation"
        ),
        pytest.param(vm.Customer.address.phones.exists(), id="nested-scope"),
    ],
)
def test_a_value_object_element_scope_admits_only_element_relative_operations(
    interior: Predicate[Any],
) -> None:
    query = vm.Customer.where(vm.Customer.address.phones.exists(interior))
    with pytest.raises(ValueError, match="not a legal nestedExists/nestedNotExists element"):
        typed_resolved(query, vm.CUSTOMER_MODEL)


@pytest.mark.parametrize(
    "interior",
    [
        pytest.param(vm.Customer.name == "Ada", id="entity-rooted-attribute"),
        pytest.param(~(vm.Customer.name == "Ada"), id="negated-entity-rooted-attribute"),
        pytest.param(vm.Customer.address.phones.exists(), id="nested-scope"),
    ],
)
def test_an_illegal_element_scope_interior_is_described_as_its_canonical_export_is(
    interior: Predicate[Any],
) -> None:
    query = vm.Customer.where(vm.Customer.address.phones.exists(interior))
    with pytest.raises(ValueError, match="not a legal nestedExists") as canonical:
        preflight(object_query_node(query), model=model_of(vm.CUSTOMER_MODEL), form="graph")
    with pytest.raises(ValueError, match="not a legal nestedExists") as typed:
        typed_resolved(query, vm.CUSTOMER_MODEL)
    assert str(typed.value) == str(canonical.value)


@pytest.mark.parametrize(
    "subject",
    [
        pytest.param(Widget.label, id="attribute"),
        pytest.param(vm.Customer.address.city, id="value-object-path"),
        pytest.param(vm.Phone.type, id="value-object-element"),
    ],
)
@pytest.mark.parametrize("method", ["like", "not_like", "starts_with", "ends_with", "contains"])
def test_a_string_operation_refuses_a_none_pattern_at_authoring(subject: Any, method: str) -> None:
    with pytest.raises(QueryDefinitionError, match="None is not a Predicate literal") as caught:
        getattr(subject, method)(None)
    assert caught.value.code == "query-expression-invalid"


@pytest.mark.parametrize(
    ("names", "message"),
    [
        pytest.param(("address", "missing"), "declares no member", id="unknown-in-value-object"),
        pytest.param(("address", "city", "deeper"), "path continues", id="past-a-leaf"),
    ],
)
def test_an_unfinished_value_object_path_is_refused_where_its_names_resolve_nothing(
    names: tuple[str, ...], message: str
) -> None:
    query = vm.Customer.where(_unfinished(vm.Customer, *names, operands=("x",)))
    with pytest.raises(QueryDefinitionError, match=message) as caught:
        typed_resolved(query, vm.CUSTOMER_MODEL)
    assert caught.value.code == "query-path-invalid"


def test_an_unfinished_anchor_the_serving_model_composes_no_class_for_is_refused() -> None:
    query = Widget.where(cast("Predicate[Widget]", _unfinished(Gizmo, "id", operands=(1,))))
    with pytest.raises(QueryDefinitionError, match="composes no Entity Class") as caught:
        typed_resolved(query, WIDGETS)
    assert caught.value.code == "query-expression-invalid"
