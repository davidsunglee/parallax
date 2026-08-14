"""What composition binds, and what a model still refuses.

Composing an Entity Class into a Domain Model binds nothing, so the same class
participates in as many models as compose it, one model connects to as many
Databases as connect to it, and query authoring reaches no model at all. Those
are the properties this suite pins, together with the two refusals a model does
own: a model that names no Entity Class cannot serve a Snapshot, and a query
target the connected model does not declare is refused before any I/O.

The assignment half is here too. Extracting the judgement is what lets the typed
path state its whole rule without a model, so the parity between it and the
serialized write boundary is the property that must not have moved.
"""

from __future__ import annotations

import datetime as dt

import pytest
from _transact_support import FIXED, NoIoPort, RecordingPort

from parallax.core import (
    Attr,
    DomainModel,
    EditError,
    EditViolation,
    Entity,
    TxTemporal,
    attr,
)
from parallax.core.entity._model import DomainModel as _Fixed
from parallax.core.entity._model import model_of
from parallax.core.inheritance import WriteAssignmentError, validate_write_assignment
from parallax.core.metamodel import UnresolvedEntityDeclaration
from parallax.core.unit_work import FixedClock
from parallax.snapshot import QueryTargetError, SnapshotConnectionError
from parallax.snapshot.handle import Database, Transaction

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


# The SAME `Widget` class object composed into two models: a class names an
# Entity of every model that composed it, so both of these are authoritative.
WIDGETS = DomainModel(Widget)
WIDGETS_AND_GIZMOS = DomainModel(Widget, Gizmo)
GADGETS = DomainModel(Gadget)


class _Source:
    """A minimal Unresolved Metamodel composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (Gizmo,)


def _db(model: DomainModel, port: RecordingPort) -> Database:
    return Database.connect(port, model, clock=FixedClock(FIXED))


# --------------------------------------------------------------------------- #
# One class, several models                                                    #
# --------------------------------------------------------------------------- #
def test_one_entity_class_is_queried_through_every_model_that_composed_it() -> None:
    narrow_port, wide_port = RecordingPort(rows=[]), RecordingPort(rows=[])
    query = Widget.where(Widget.id == 1)

    _db(WIDGETS, narrow_port).find(query)
    _db(WIDGETS_AND_GIZMOS, wide_port).find(query)

    assert [op[0] for op in narrow_port.ops] == ["read"]
    assert narrow_port.ops == wide_port.ops


def test_one_entity_class_is_written_through_every_model_that_composed_it() -> None:
    for model in (WIDGETS, WIDGETS_AND_GIZMOS):
        port = RecordingPort()

        def insert(tx: Transaction) -> None:
            tx.insert(Widget(id=1, label="x"))

        _db(model, port).transact(insert)
        assert [op[0] for op in port.ops] == ["begin", "write", "commit"]


def test_one_domain_model_serves_every_database_connected_to_it() -> None:
    first, second = RecordingPort(rows=[]), RecordingPort(rows=[])
    query = Widget.where(Widget.id == 1)

    _db(WIDGETS, first).find(query)
    _db(WIDGETS, second).find(query)

    assert first.ops == second.ops


def test_a_query_whose_target_the_connected_model_does_not_declare_is_refused() -> None:
    # Authoring reaches no model, so the query builds; the connected model is
    # what answers, and it answers before any adapter activity.
    port = NoIoPort()
    database = Database.connect(port, DomainModel(Gizmo), clock=FixedClock(FIXED))
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
    database = Database.connect(NoIoPort(), descriptor_backed, clock=FixedClock(FIXED))
    with pytest.raises(SnapshotConnectionError) as caught:
        database.find(Gizmo.where(Gizmo.id == 1))
    assert caught.value.code == "snapshot-class-backed-model-required"
    assert database.wire is not None


def test_connect_refuses_a_bare_accepted_metamodel() -> None:
    # The other way the runtime narrowing can fail. `__init__` still admits a
    # bare accepted Metamodel for the neutral write lanes, so `connect` — the
    # developer entry point — must answer it with the same connection refusal
    # rather than by reaching for a class index it does not have.
    with pytest.raises(SnapshotConnectionError) as caught:
        Database.connect(NoIoPort(), model_of(WIDGETS), clock=FixedClock(FIXED))  # pyright: ignore[reportArgumentType] - the runtime narrowing is what this proves
    assert caught.value.code == "snapshot-class-backed-model-required"


def test_a_bare_metamodel_database_refuses_a_read_before_it_resolves_the_target() -> None:
    # The connection refusal precedes preflight on BOTH entry points. A Database
    # that cannot materialize a Snapshot answers that first, so a query this
    # model also does not declare still reports the connection rather than the
    # target.
    port = RecordingPort()
    database = Database(port, model_of(WIDGETS), clock=FixedClock(FIXED))
    with pytest.raises(SnapshotConnectionError) as caught:
        database.find(Gizmo.where(Gizmo.id == 1))
    assert caught.value.code == "snapshot-class-backed-model-required"
    assert port.ops == []


def test_a_bare_metamodel_database_serves_writes_and_refuses_a_modeled_read() -> None:
    # The first-party neutral form the conformance adapter constructs: the write
    # lanes name Entities rather than classes, so they run, while a read that
    # would have to instantiate one is refused before any SQL.
    port = RecordingPort()
    database = Database(port, model_of(WIDGETS), clock=FixedClock(FIXED))
    with pytest.raises(SnapshotConnectionError) as caught:
        database.find(Widget.where(Widget.id == 1))
    assert caught.value.code == "snapshot-class-backed-model-required"
    assert port.ops == []


def test_a_bare_metamodel_transaction_refuses_a_read_before_it_can_force_flush() -> None:
    port = RecordingPort()
    database = Database(port, model_of(WIDGETS), clock=FixedClock(FIXED))

    def body(tx: Transaction) -> None:
        tx.insert(Widget(id=1, label="x"))
        with pytest.raises(SnapshotConnectionError):
            tx.find(Widget.where(Widget.id == 1))
        assert [op[0] for op in port.ops] == ["begin"]

    database.transact(body)


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


def _boundary_verdict(
    model: DomainModel, entity: type[Entity], member: str, value: object
) -> str | None:
    """The same, through the write boundary's own family-effective resolution."""
    try:
        validate_write_assignment(model_of(model), model.meta(entity), member, value)
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
            validate_write_assignment(model_of(WIDGETS), WIDGETS.meta(Widget), member, value)
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
        validate_write_assignment(model_of(WIDGETS), WIDGETS.meta(Widget), "computed", "x")
    assert caught.value.rule == "read-only"
