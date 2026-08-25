"""Source-owned write evidence: identity, lifetime, and claim transfer.

The Python-interface half of the observed-state contract, driven through the real
handles over a fake port. Evidence belongs to the VALUE a read produced, so what
these tests measure is what a value carries, how long it lives, what survives an
edit or a copy, and what a conversion strips.

The seam's own mechanics — which rows retain what, and under which state key —
live in `test_write_inputs.py`; what lives here is the choreography a caller
actually performs.
"""

from __future__ import annotations

import datetime as dt
import gc
import io
import pickle
from decimal import Decimal
from typing import Any, ClassVar, Final, cast

import pytest
from _authored_storage_support import AuthoredInstanceDict, stored_state
from _transact_support import (
    BALANCE,
    PERSON,
    RecordingPort,
    account_db,
    balance_row,
    db_for,
    new_account,
)
from pydantic import BaseModel

from _support import mirrored_models as mm
from parallax.conformance import vo_models as vo
from parallax.conformance.read_models import Person
from parallax.core import Attr, Entity, attr
from parallax.core.entity import (
    EntityAttributeInput,
    EntityGraphWriter,
    NodeHandle,
    graph_construction_of,
)
from parallax.core.entity._declaration import LIFECYCLE_STATE_SLOT
from parallax.core.entity._model import DomainModel
from parallax.core.metamodel import AttributeIdentity
from parallax.core.unit_work import (
    OptimisticLockConflictError,
    VersionedStateKey,
    VersionObservation,
)
from parallax.snapshot import InvalidData, WireEntity, connect
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle import KeyedWriteValueError, Transaction, WriteEvidenceError
from parallax.snapshot.materialize import source_hint_of

_ACCOUNT_ROW: dict[str, object] = {
    "id": 1,
    "owner": "Ada",
    "balance": Decimal("100.00"),
    "version": 4,
}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _typed_hint(node: object) -> object:
    state = snapshot_state_of(node)
    assert state is not None
    return state.source


def _account_port(rows: list[dict[str, object]] | None = None) -> RecordingPort:
    return RecordingPort(rows=[dict(row) for row in (rows or [_ACCOUNT_ROW])])


# --------------------------------------------------------------------------- #
# What a source value carries.                                                #
# --------------------------------------------------------------------------- #
def test_a_typed_node_carries_the_state_its_row_observed() -> None:
    node = account_db(_account_port()).find(mm.Account.where(mm.Account.id == 1)).result()
    hint = _typed_hint(node)
    assert hint is not None
    assert cast("Any", hint).observation.key == VersionedStateKey(cast("Any", hint).object_key, 4)


def test_a_wire_node_and_a_typed_node_of_one_row_carry_the_identical_evidence() -> None:
    # The two representations of one observed state share ONE retained
    # observation object, not equal copies of one: consumption is the mutable
    # fact living on that object, so a second copy would keep licensing writes
    # after the flush that spent the first. Both reads participate and the typed
    # source stays live across the second, which is what makes them one state.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [dict(_ACCOUNT_ROW)]))

    def fn(tx: Transaction) -> tuple[object, object]:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        wire = tx.wire.find(mm.Account.where(mm.Account.id == 1)).result()
        assert isinstance(wire, WireEntity)
        return _typed_hint(typed), source_hint_of(wire)

    typed_hint, wire_hint = (cast("Any", hint) for hint in account_db(port).transact(fn))
    assert wire_hint is not None
    assert wire_hint.object_key == typed_hint.object_key
    assert wire_hint.observation is typed_hint.observation


# --------------------------------------------------------------------------- #
# Claim transfer and stripping.                                               #
# --------------------------------------------------------------------------- #
def test_entity_edit_transfers_the_sources_claim_to_the_derived_value() -> None:
    node = account_db(_account_port()).find(mm.Account.where(mm.Account.id == 1)).result()
    edited = node.edit(balance=Decimal("125.00"))
    assert _typed_hint(edited) is _typed_hint(node)


def test_wire_copy_answers_the_same_value_and_therefore_the_same_claim() -> None:
    import copy as copy_module

    node = account_db(_account_port()).wire.find(mm.Account.where(mm.Account.id == 1)).result()
    assert isinstance(node, WireEntity)
    for copied in (cast("Any", node).copy(), copy_module.copy(node), copy_module.deepcopy(node)):
        assert copied is node
        assert source_hint_of(cast("WireEntity", copied)) is source_hint_of(node)


def test_plain_dict_conversion_strips_a_wire_nodes_keyed_source_status() -> None:
    # The hint rides a slot rather than a mapping entry, so a plain conversion
    # carries none of it: what comes out is ordinary domain data, which is
    # exactly what it is.
    node = account_db(_account_port()).wire.find(mm.Account.where(mm.Account.id == 1)).result()
    assert isinstance(node, WireEntity)
    converted = dict(node)
    assert converted == dict(node.items())
    assert type(converted) is dict
    assert not isinstance(converted, WireEntity)
    assert not hasattr(converted, "_source")


# --------------------------------------------------------------------------- #
# Pickle: the lifecycle refusal, and everything it leaves alone.              #
# --------------------------------------------------------------------------- #
def _rebuilt_by_hand(identifier: int) -> tuple[str, int]:
    """What ``_AuthoredReduce``'s hook reconstructs, chosen so the restored value
    is itself the evidence that the authored hook ran."""
    return ("rebuilt by hand", identifier)


class _AuthoredReduce(Entity, table="authored_reduce", namespace="parallax.compatibility"):
    """An ordinary Entity authoring the hook ``object.__reduce_ex__`` consults."""

    id: Attr[int] = attr(primary_key=True)

    def __reduce__(self) -> tuple[Any, ...]:
        return (_rebuilt_by_hand, (self.id,))


class _AuthoredGetState(Entity, table="authored_getstate", namespace="parallax.compatibility"):
    """The other authorable hook, marking the state it hands back."""

    id: Attr[int] = attr(primary_key=True)

    def __getstate__(self) -> dict[Any, Any]:
        state = super().__getstate__()
        instance = cast("dict[str, Any]", state["__dict__"])
        return {**state, "__dict__": {**instance, "_authored_by_getstate": True}}


class _DerivingAttributes(Entity, table="deriving_attributes", namespace="parallax.compatibility"):
    """An Entity whose class body answers every name the instance does not carry.

    The lifecycle slot's name is one of those, so a predicate that asked the
    value for it would read a materialized node out of an ordinary one.
    """

    id: Attr[int] = attr(primary_key=True)

    def __getattr__(self, name: str) -> Any:
        return f"<derived {name}>"


class _HidingAttributes(Entity, table="hiding_attributes", namespace="parallax.compatibility"):
    """An Entity whose class body denies the lifecycle slot it carries."""

    id: Attr[int] = attr(primary_key=True)

    def __getattribute__(self, name: str) -> Any:
        if name == LIFECYCLE_STATE_SLOT:
            raise AttributeError(name)
        return object.__getattribute__(self, name)


_INVENTED_STATE: Final = object()


class _FilteredDict(Entity, table="filtered_dict", namespace="parallax.compatibility"):
    """An Entity whose class body denies the lifecycle slot its storage holds."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)

    __dict__ = AuthoredInstanceDict.denying(LIFECYCLE_STATE_SLOT)  # pyright: ignore[reportGeneralTypeIssues, reportAssignmentType] - a type checker forbids the binding the interpreter allows, and the interpreter is what the refusal answers to


class _InventedDict(Entity, table="invented_dict", namespace="parallax.compatibility"):
    """An Entity whose class body offers a lifecycle slot its storage never held."""

    id: Attr[int] = attr(primary_key=True)

    __dict__ = AuthoredInstanceDict.inventing(LIFECYCLE_STATE_SLOT, _INVENTED_STATE)  # pyright: ignore[reportGeneralTypeIssues, reportAssignmentType] - as above


_DIVERTED_TO: Final = "_diverted_lifecycle"


class _DivertedSlot:
    """A data descriptor at the lifecycle slot's own name.

    ``object.__setattr__`` honors a data descriptor, so a class carrying one here
    takes whatever is assigned under that name and holds it wherever it likes —
    here, under a name of its own in the same storage.
    """

    def __get__(self, instance: BaseModel | None, owner: type[object] | None = None) -> object:
        if instance is None:
            return self
        return stored_state(instance).get(_DIVERTED_TO)

    def __set__(self, instance: BaseModel, value: object) -> None:
        stored_state(instance)[_DIVERTED_TO] = value


class _InstallsDivertedSlot:
    """A class-body binding that installs that descriptor once the class exists.

    ``__set_name__`` runs after the class body has been judged, which is what puts
    a name no body may bind within a class's reach at all.
    """

    def __set_name__(self, owner: type[object], name: str) -> None:
        del name
        setattr(owner, LIFECYCLE_STATE_SLOT, _DivertedSlot())


class _DivertedSlotNode(
    Entity, table="diverted_slot", name="DivertedSlotNode", namespace="parallax.compatibility"
):
    """An Entity whose class installs a descriptor at the lifecycle slot's name."""

    id: Attr[int] = attr(primary_key=True)

    installer: ClassVar[_InstallsDivertedSlot] = _InstallsDivertedSlot()


_DIVERTED_MODEL: Final = DomainModel(_DivertedSlotNode)


_HISTORICAL_PROTOCOL: Final = pickle.HIGHEST_PROTOCOL


class _StrippingPickler(pickle.Pickler):
    """Writes an Entity the way the implementation before the refusal wrote one.

    ``object.__reduce_ex__`` reached directly is exactly that implementation: with
    no authored ``__reduce__`` or ``__getstate__`` standing in front of it on
    these models, ``Entity.__getstate__``'s lifecycle strip runs and no
    entry-point guard does,
    so what lands in the buffer is a historical pickle rather than an
    approximation of one. Supplying the reducer is what makes that reachable — a
    caller who answers for the entry point never enters the refusal (spec §3) —
    so this is the writer of the historical bytes and never a way to obtain them
    from the refusal.
    """

    def reducer_override(self, obj: Any) -> Any:
        if isinstance(obj, Entity):
            return object.__reduce_ex__(obj, _HISTORICAL_PROTOCOL)
        return NotImplemented


def _stripped_pickle(node: Entity) -> bytes:
    buffer = io.BytesIO()
    _StrippingPickler(buffer, _HISTORICAL_PROTOCOL).dump(node)
    return buffer.getvalue()


def test_pickling_a_typed_node_is_refused_while_it_carries_lifecycle_state() -> None:
    # A pickled value crosses a boundary the lifecycle state cannot: the hint and
    # the claim behind it describe a live read, and neither answer is truthful.
    # Carrying the state would rebuild the claim as a fresh object whose consumed
    # state is whatever the bytes happened to capture; dropping it silently would
    # answer a request to preserve a value with one that quietly lost what the
    # caller never learned it had. So the door refuses, and it refuses with the
    # language's own pickling error rather than a Parallax one — a caller
    # pickling a graph is inside `pickle`, not inside this framework.
    node = account_db(_account_port()).find(mm.Account.where(mm.Account.id == 1)).result()

    with pytest.raises(pickle.PicklingError) as refusal:
        pickle.dumps(node)
    assert type(refusal.value) is pickle.PicklingError
    message = str(refusal.value)
    assert "Account" in message
    assert "model_dump()" in message


def test_a_materialized_node_nested_in_what_is_pickled_is_refused_too() -> None:
    # Being the pickle's root is not what the refusal is about: `pickle`'s own
    # dispatch asks every object it writes for the same entry point, so a node
    # buried in a container refuses the whole dump.
    node = account_db(_account_port()).find(mm.Account.where(mm.Account.id == 1)).result()

    with pytest.raises(pickle.PicklingError):
        pickle.dumps({"accounts": [node]})


def test_pickling_an_edited_copy_that_kept_the_claim_is_refused_too() -> None:
    # An edit transfers the claim, so the derived value is a materialized node's
    # equal in everything the refusal is about.
    node = account_db(_account_port()).find(mm.Account.where(mm.Account.id == 1)).result()
    edited = node.edit(balance=Decimal("125.00"))
    assert _typed_hint(edited) is _typed_hint(node)

    with pytest.raises(pickle.PicklingError):
        pickle.dumps(edited)


def test_pickling_a_plainly_constructed_value_has_nothing_to_refuse() -> None:
    # The other half of the same boundary: a value no read produced carries no
    # lifecycle state, so its round trip is the ordinary one and the result is
    # the value it always was.
    fresh = new_account()
    restored = cast("mm.Account", pickle.loads(pickle.dumps(fresh)))
    assert restored == fresh
    assert snapshot_state_of(restored) is None


def test_a_value_object_of_a_materialized_graph_round_trips() -> None:
    # Only an Entity node can carry lifecycle state, so the refusal reaches no
    # Value Object — including one a read published, which is ordinary domain
    # data the moment it is held on its own.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada", "address": {"street": "Main"}}])
    customer = (
        connect(port, vo.CUSTOMER_MODEL).find(vo.Customer.where(vo.Customer.id == 1)).result()
    )
    assert isinstance(customer, vo.Customer)

    restored = cast("vo.CustomerAddress", pickle.loads(pickle.dumps(customer.address)))
    assert restored == customer.address
    assert restored is not customer.address


def test_an_authored_reduce_hook_still_runs_on_a_lifecycle_free_value() -> None:
    # The guard is on the entry point precisely so the hooks below it stay
    # authorable: `object.__reduce_ex__` consults `__reduce__` only after the
    # guard has passed, so an ordinary Entity's own pickle behavior is untouched.
    assert pickle.loads(pickle.dumps(_AuthoredReduce(id=7))) == ("rebuilt by hand", 7)


def test_an_authored_getstate_hook_still_runs_on_a_lifecycle_free_value() -> None:
    value = _AuthoredGetState(id=7)
    restored = cast("_AuthoredGetState", pickle.loads(pickle.dumps(value)))
    assert restored == value
    assert restored.__dict__["_authored_by_getstate"] is True


def test_a_class_body_answering_every_name_leaves_an_ordinary_value_pickleable() -> None:
    # What the refusal asks is whether the state is attached, which is a fact
    # about the instance dictionary rather than about what the value answers: a
    # class body deriving the slot's name does not make a value a read never
    # produced into a materialized node.
    value = _DerivingAttributes(id=7)
    assert getattr(value, LIFECYCLE_STATE_SLOT, None) is not None

    restored = cast("_DerivingAttributes", pickle.loads(pickle.dumps(value)))
    assert restored == value


def test_a_class_body_hiding_the_lifecycle_slot_is_refused_all_the_same() -> None:
    # The same fact read from the other side. The state is attached exactly as
    # Entity Graph Construction attaches it, and a class body that denies the
    # slot exists does not buy a pickle of a materialized node.
    value = _HidingAttributes(id=7)
    object.__setattr__(value, LIFECYCLE_STATE_SLOT, object())
    assert getattr(value, LIFECYCLE_STATE_SLOT, None) is None

    with pytest.raises(pickle.PicklingError):
        pickle.dumps(value)


def test_a_class_body_filtering_its_instance_dictionary_is_refused_all_the_same() -> None:
    # `__dict__` is a name a class body can bind like any other, and binding it
    # decides what every reader of that name — `getattr` and
    # `object.__getattribute__` alike — is told. The refusal reads the storage
    # itself, so a value whose dictionary denies the state it carries pickles no
    # more than a plainly materialized node does.
    value = _FilteredDict(id=7, name="Ada")
    object.__setattr__(value, LIFECYCLE_STATE_SLOT, object())
    assert LIFECYCLE_STATE_SLOT not in value.__dict__

    with pytest.raises(pickle.PicklingError):
        pickle.dumps(value)


def test_a_class_body_inventing_the_slot_leaves_an_ordinary_value_pickleable() -> None:
    # The same fact from the other side: a dictionary answering with a slot the
    # storage never held does not make a value a read never produced into a
    # materialized node.
    value = _InventedDict(id=7)
    assert value.__dict__[LIFECYCLE_STATE_SLOT] is _INVENTED_STATE

    restored = cast("_InventedDict", pickle.loads(pickle.dumps(value)))
    assert restored.id == 7
    assert snapshot_state_of(restored) is None


def test_an_edited_copy_of_a_value_whose_dictionary_denies_the_slot_is_refused_too() -> None:
    # An edit carries every kind of instance state outside the declared members
    # forward, so a class that filters `__dict__` could otherwise launder a
    # materialized node one call deeper than the refusal: derive a copy, and the
    # state the original's storage holds is dropped on the way. The edit surface
    # reads and writes that storage itself, so the copy carries the claim the
    # original transferred to it — through the no-change branch that restates a
    # value whole and through the branch that rebuilds it around changes alike —
    # and pickles no more than the node it came from.
    value = _FilteredDict(id=7, name="Ada")
    object.__setattr__(value, LIFECYCLE_STATE_SLOT, object())

    for derived in (value.edit(), value.edit(name="Grace")):
        with pytest.raises(pickle.PicklingError):
            pickle.dumps(derived)


def test_a_class_diverting_the_lifecycle_slot_is_refused_all_the_same() -> None:
    # No class body may bind the lifecycle slot's name, but `__set_name__` runs
    # after that judgement and can install a data descriptor there — one
    # `object.__setattr__` would honor, taking the state a read attaches and
    # holding it somewhere of the class's own choosing. Entity Graph Construction
    # writes that state into the node's own storage instead, so a class can blind
    # its own readers of the slot without making a materialized node answer as a
    # value no read produced: the refusal reads what the lifecycle attached.
    state = object()
    identity = _DivertedSlotNode.identity

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        node = writer.allocate(identity)
        writer.populate(node, (EntityAttributeInput(AttributeIdentity(identity, "id"), 7),), (), ())
        return (node,)

    (root,) = graph_construction_of(_DIVERTED_MODEL).construct(
        build, state_factory=lambda _view, _handle: state
    )
    assert stored_state(cast("_DivertedSlotNode", root))[LIFECYCLE_STATE_SLOT] is state

    with pytest.raises(pickle.PicklingError):
        pickle.dumps(root)


def test_a_pickle_written_before_the_refusal_existed_still_loads() -> None:
    # The refusal is on what may be written, never on what may be read: bytes
    # whose lifecycle state was stripped at dump time load into exactly the
    # ordinary domain data they always described — a value the write verbs then
    # refuse for having lost its provenance, which is the same answer they gave
    # such a value before.
    port = _account_port()
    db = account_db(port)
    node = db.find(mm.Account.where(mm.Account.id == 1)).result()

    restored = cast("mm.Account", pickle.loads(_stripped_pickle(node)))
    assert restored == node
    assert snapshot_state_of(restored) is None

    with pytest.raises(KeyedWriteValueError) as refusal:
        db.transact(lambda tx: tx.update(restored.edit(balance=Decimal("125.00"))))
    assert refusal.value.code == "write-value-not-stored"
    assert not any(op[0] == "write" for op in port.ops)


# --------------------------------------------------------------------------- #
# Lifetime: liveness is strong reachability.                                  #
# --------------------------------------------------------------------------- #
def test_a_retained_included_child_outlives_its_released_root_and_snapshot() -> None:
    # Retaining a root naturally retains its children; extracting and retaining a
    # CHILD keeps that child's own evidence after the root and the Snapshot are
    # released, because the claim belongs to the entity node rather than to the
    # result it arrived in.
    from parallax.conformance.graph_models import POLICY_MODEL, Policy
    from parallax.core import LATEST

    policy_row: dict[str, object] = {
        "id": 1,
        "name": "P-1",
        "from_z": _TX_START,
        "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        "in_z": _TX_START,
        "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    }
    coverage_row: dict[str, object] = {
        "id": 10,
        "policy_id": 1,
        "amount": Decimal("250.00"),
        "from_z": _TX_START,
        "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        "in_z": _TX_START,
        "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    }
    port = RecordingPort(row_queue=([policy_row], [coverage_row]))
    snapshot = db_for(POLICY_MODEL, port).find(
        Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
    )
    child = snapshot.result().coverages[0]
    del snapshot
    gc.collect()
    hint = cast("Any", _typed_hint(child))
    assert hint.observation is not None
    assert hint.object_key.primary_key == (("id", 10),)


def test_releasing_every_source_makes_the_transactions_index_forget_the_state() -> None:
    # Liveness IS the reference graph: the unit of work holds a WEAK index, so an
    # observed state no source value and no buffered write reaches disappears
    # from it on the runtime's own collection schedule, with no claim counting
    # and no scope-bound bookkeeping.
    port = _account_port()

    def fn(tx: Transaction) -> tuple[object, object]:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        hint = cast("Any", _typed_hint(node))
        state = hint.observation.key
        held = tx._uow.retained_for(state)  # pyright: ignore[reportPrivateUsage] - the index is first-party state
        assert held is hint.observation
        del node, hint, held
        gc.collect()
        return state, tx._uow.retained_for(state)  # pyright: ignore[reportPrivateUsage] - the index is first-party state

    state, after_release = account_db(port).transact(fn)
    assert state is not None
    assert after_release is None


# --------------------------------------------------------------------------- #
# Consumption: what a successful flush spends.                                #
# --------------------------------------------------------------------------- #
def test_a_successful_flush_consumes_the_evidence_its_write_used() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> object:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        return _typed_hint(node)

    hint = cast("Any", account_db(port).transact(fn))
    assert hint.observation.consumed is True


def test_reusing_a_consumed_source_after_the_flush_is_refused() -> None:
    # A consumed source stays an ordinary readable value; what it no longer
    # carries is authority, because the state it observed is not the stored state
    # any more. The refusal is at the second verb, before any DML of its own.
    port = _account_port()
    db = account_db(port)

    def fn(tx: Transaction) -> mm.Account:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        return node

    stale = db.transact(fn)

    def second(tx: Transaction) -> None:
        tx.update(stale.edit(balance=Decimal("150.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        db.transact(second)
    assert refusal.value.code == "write-evidence-consumed"
    assert [op[0] for op in port.ops].count("write") == 1


def test_a_locking_source_consumed_by_a_flush_cannot_drive_a_second_write() -> None:
    # Consumption is strategy-independent. The shared row lock licenses a write
    # against the state the locked read saw; it says nothing about a state this
    # unit of work has itself already written past, so the participating source
    # that drove the surviving write carries no authority for a second one. The
    # dependent read in the middle is what forces that first write out.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [dict(_ACCOUNT_ROW)]))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        tx.find(mm.Account.where(mm.Account.id == 1))
        tx.update(node.edit(balance=Decimal("150.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        account_db(port).transact(fn, concurrency="locking")
    assert refusal.value.code == "write-evidence-consumed"
    assert [op[0] for op in port.ops].count("write") == 1


def test_an_intent_eliminated_before_dml_consumes_nothing() -> None:
    # An edited copy whose effective change set is empty buffers nothing and
    # issues no statement, so the evidence its source carries is still about the
    # stored state and still licenses a later write.
    port = _account_port()
    db = account_db(port)

    def fn(tx: Transaction) -> mm.Account:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("100.00")))
        return node

    unchanged = db.transact(fn)
    assert cast("Any", _typed_hint(unchanged)).observation.consumed is False
    assert not any(op[0] == "write" for op in port.ops)


def test_an_aborted_flush_spends_no_evidence() -> None:
    # A failed flush aborts the transaction, so nothing it wrote survives and the
    # evidence a live value carries is still about stored state — which is why
    # abort needs no restoration.
    port = _account_port()
    db = account_db(port)
    escaped: list[mm.Account] = []

    def doomed(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        escaped.append(node)
        tx.update(node.edit(balance=Decimal("125.00")))
        raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        db.transact(doomed)
    assert cast("Any", _typed_hint(escaped[0])).observation.consumed is False


# --------------------------------------------------------------------------- #
# Several observed states of one object.                                      #
# --------------------------------------------------------------------------- #
def test_two_observed_versions_of_one_object_coexist_and_resolve_independently() -> None:
    # A reread that sees a NEW version is evidence about a different state, so
    # the older live value is not upgraded: it keeps the version it observed, and
    # a write from it gates on that version rather than on the fresher one.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [{**_ACCOUNT_ROW, "version": 7}]))
    db = account_db(port)

    def fn(tx: Transaction) -> tuple[object, object]:
        first = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        second = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        return _typed_hint(first), _typed_hint(second)

    earlier, later = db.transact(fn)
    assert cast("Any", earlier).observation is not cast("Any", later).observation
    assert cast("Any", earlier).observation.evidence == VersionObservation(observed_version=4)
    assert cast("Any", later).observation.evidence == VersionObservation(observed_version=7)


def test_a_reread_of_one_state_answers_the_evidence_the_first_read_retained() -> None:
    # Two reads that resolve to ONE observed state share one claim, exactly as
    # two graph positions reaching one node do — so a flush that spends the state
    # spends it for both rather than leaving a second live value able to rewrite
    # what was just written.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [dict(_ACCOUNT_ROW)]))

    def fn(tx: Transaction) -> tuple[object, object]:
        first = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        second = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        return _typed_hint(first), _typed_hint(second)

    earlier, later = account_db(port).transact(fn)
    assert cast("Any", earlier).observation is cast("Any", later).observation


# --------------------------------------------------------------------------- #
# The standalone optimistic source.                                           #
# --------------------------------------------------------------------------- #
def test_a_standalone_versioned_source_gates_a_later_transactions_write() -> None:
    # The default preference resolves `Account` to Optimistic, where the database
    # gate is the authority — so a value a plain `db.find` produced carries the
    # version it observed into a later transaction and no reread is issued.
    port = _account_port()
    db = account_db(port)
    node = db.find(mm.Account.where(mm.Account.id == 1)).result()

    db.transact(lambda tx: tx.update(node.edit(balance=Decimal("125.00"))))
    assert [op[0] for op in port.ops] == ["read", "begin", "write", "commit"]
    update = port.ops[2]
    assert cast("tuple[object, ...]", update[2])[-1] == 4


def test_a_standalone_versioned_source_meeting_an_intervening_writer_conflicts() -> None:
    # The gate is the concurrency authority, so a stale standalone source is not
    # refused at the verb — it is admitted, and its zero-row gated UPDATE raises
    # the ordinary optimistic conflict the database discovered.
    port = _account_port()
    db = account_db(port)
    node = db.find(mm.Account.where(mm.Account.id == 1)).result()
    port.write_affected = 0

    with pytest.raises(OptimisticLockConflictError):
        db.transact(lambda tx: tx.update(node.edit(balance=Decimal("125.00"))))


def test_a_standalone_temporal_source_carries_its_milestone_into_a_transaction() -> None:
    port = RecordingPort(rows=[balance_row(in_z=_TX_START)])
    db = db_for(BALANCE, port)
    node = db.find(mm.Balance.where(mm.Balance.id == 1)).result()

    db.transact(lambda tx: tx.update(node.edit(value=Decimal("9.00"))))
    assert [op[0] for op in port.ops] == ["read", "begin", "write", "write", "commit"]


def test_a_standalone_versioned_source_is_refused_under_an_explicit_locking_preference() -> None:
    # `locking` forces the Locking strategy onto every Entity, and its license is
    # the shared row lock a read of the writing transaction holds. A standalone
    # `db.find` acquired none, so its retained version buys nothing here: the
    # verb refuses before buffering and before any statement is emitted.
    port = _account_port()
    db = account_db(port)
    node = db.find(mm.Account.where(mm.Account.id == 1)).result()

    with pytest.raises(WriteEvidenceError) as refusal:
        db.transact(
            lambda tx: tx.update(node.edit(balance=Decimal("125.00"))), concurrency="locking"
        )
    assert refusal.value.code == "write-evidence-unavailable"
    assert not any(op[0] == "write" for op in port.ops)


def test_a_standalone_unversioned_source_is_refused_under_the_default_preference() -> None:
    # An unversioned Non-Temporal Entity has no optimistic gate, so the default
    # `optimistic` preference resolves it to the Locking fallback and the shared
    # row lock is the whole of its evidence. A standalone `db.find` holds none,
    # and there is no version for the database to settle the write against, so
    # the refusal is the only honest answer.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada"}])
    db = db_for(PERSON, port)
    node = db.find(Person.where(Person.id == 1)).result()

    with pytest.raises(WriteEvidenceError) as refusal:
        db.transact(lambda tx: tx.update(node.edit(name="Grace")))
    assert refusal.value.code == "write-evidence-unavailable"
    assert not any(op[0] == "write" for op in port.ops)


def test_an_unconditional_delete_is_spelled_through_the_predicate_verb() -> None:
    # What replaces a keyed verb against a constructed instance: `delete_where`
    # says the unconditional intent outright rather than reaching it by building
    # a throwaway value, and an unversioned Non-Temporal target lowers it
    # readlessly to one predicate-shaped statement.
    port = RecordingPort()
    db_for(PERSON, port).transact(lambda tx: tx.delete_where(Person.where(Person.id == 1)))

    assert [op[0] for op in port.ops] == ["begin", "write", "commit"]
    assert port.ops[1][2] == (1,)


# --------------------------------------------------------------------------- #
# Classified sources.                                                         #
# --------------------------------------------------------------------------- #
def test_a_hydratable_invalid_root_carries_its_ordinary_claim() -> None:
    # A hydratable violation's collapse produced legal member values, so the row
    # behind it is an ordinary stored row: the node in `data` carries the same
    # evidence any conforming node of that read would, and stays an ordinary
    # write source. Only a non-hydrating position, which has no conforming value
    # at all, carries none.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada", "address": {"city": "Berlin"}}])
    record = (
        connect(port, vo.CUSTOMER_MODEL)
        .find(vo.Customer.where(vo.Customer.id == 1))
        .checked()
        .result()
    )
    assert isinstance(record, InvalidData)
    hint = cast("Any", _typed_hint(record.data))
    assert hint is not None
    assert hint.object_key.primary_key == (("id", 1),)
