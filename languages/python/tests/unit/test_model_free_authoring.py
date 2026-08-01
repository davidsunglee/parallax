"""What lifting the one-model-per-class rule buys, and what still refuses.

Composing an Entity Class into a Domain Model binds nothing, so the same class
participates in as many models as compose it, one model connects to as many
Databases as connect to it, and query authoring reaches no model at all. Those
are the properties this suite pins, together with the two refusals that replace
the ones the claim rule was providing: a model that names no Entity Class cannot
serve a Snapshot, and a query target the connected model does not declare is
refused before any I/O.

The assignment half is here too. Extracting the judgement is what lets the typed
path state its whole rule without a model, so the parity between it and the
serialized write boundary is the property that must not have moved.
"""

from __future__ import annotations

import pytest
from _transact_support import FIXED, NoIoPort, RecordingPort

from parallax.core import (
    Attr,
    DomainModel,
    Entity,
    ModelCopyError,
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


class Widget(Entity, table="widget", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)
    computed: Attr[str | None] = attr(max_length=16, read_only=True)


class Gizmo(Entity, table="gizmo", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)


# The SAME `Widget` class object composed into two models, which is what the
# claim rule made unconstructible.
WIDGETS = DomainModel(Widget)
WIDGETS_AND_GIZMOS = DomainModel(Widget, Gizmo)


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
            tx.insert(Widget(id=1, label="x", version=1))

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
def test_connect_refuses_a_model_that_composed_no_entity_class() -> None:
    # A Snapshot instantiates Entity Class instances, so a descriptor-backed
    # model is refused at the connection rather than after a round trip. The
    # raising port proves nothing was inspected.
    descriptor_backed = _Fixed._from_unresolved(_Source())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam
    with pytest.raises(SnapshotConnectionError) as caught:
        Database.connect(NoIoPort(), descriptor_backed, clock=FixedClock(FIXED))
    assert caught.value.code == "snapshot-class-backed-model-required"


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
        tx.insert(Widget(id=1, label="x", version=1))
        with pytest.raises(SnapshotConnectionError):
            tx.find(Widget.where(Widget.id == 1))
        assert [op[0] for op in port.ops] == ["begin"]

    database.transact(body)


# --------------------------------------------------------------------------- #
# One judgement, two callers                                                   #
# --------------------------------------------------------------------------- #
def _typed_verdict(member: str, value: object) -> str | None:
    """What ``.set(...)`` says about ``value``, or absence — the member alone."""
    try:
        getattr(Widget, member).set(value)
    except ModelCopyError as error:
        return str(error)
    return None


def _boundary_verdict(member: str, value: object) -> str | None:
    """The same, through the write boundary's own family-effective resolution."""
    try:
        validate_write_assignment(model_of(WIDGETS), WIDGETS.meta(Widget), member, value)
    except WriteAssignmentError as error:
        return str(error)
    return None


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
def test_the_typed_path_and_the_write_boundary_reach_one_verdict(
    member: str, value: object
) -> None:
    # Only the resolution in front of the judgement differs between the two
    # callers, so both reach the same verdict AND render it identically — which
    # is what "one validator, two callers" means once the model has disappeared
    # from one of them.
    assert _typed_verdict(member, value) == _boundary_verdict(member, value)


def test_both_callers_classify_a_read_only_member_the_same_way() -> None:
    # The rule the Python specification states and the implementation never
    # applied. It lands in the extracted judgement, so one edit gave it to both.
    with pytest.raises(ModelCopyError, match="read-only fields may not be assigned"):
        Widget.computed.set("x")
    with pytest.raises(WriteAssignmentError) as caught:
        validate_write_assignment(model_of(WIDGETS), WIDGETS.meta(Widget), "computed", "x")
    assert caught.value.rule == "read-only"
