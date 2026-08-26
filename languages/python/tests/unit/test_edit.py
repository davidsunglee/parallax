"""``Entity.edit(**changes)``, the refused copy doors, and the Change Record it
stamps (spec §3).

What that record then MEANS to a write — the effective change set, the derived
row, and the refusals of a value carrying none — is the Entity Row Codec's, and
is pinned in ``test_row_codec.py``. Here the record is read straight out of the
private slot the edit surface owns, because what this suite proves is what
``edit`` wrote. The version column's own advance is framework-owned end to end at
the write seam (`m-opt-lock`); see ``test_write_lowering.py`` /
``test_opt_lock.py``.
"""

from __future__ import annotations

import copy as copy_module
import datetime as dt
from decimal import Decimal
from functools import cached_property
from typing import Any, Final, cast

import pytest
from _compact_support import layout_slots
from pydantic import PrivateAttr, ValidationError

from _support import mirrored_models as mm
from _support import snapshot_models as sm
from _support import value_object_models as vm
from parallax.conformance.read_models import Dog
from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Entity,
    TablePerHierarchy,
    attr,
)
from parallax.core.base import INFINITY
from parallax.core.entity import (
    EDIT_CODES,
    UNLOADED,
    EditError,
    EditViolation,
    EntityDefinitionError,
    EntityGraphWriter,
    NodeHandle,
    UnloadedRelationshipError,
    graph_construction_of,
    lifecycle_state_of,
    relationship_value_of,
)
from parallax.core.entity import _instance_state as instance_state
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._declaration import (
    FRAMEWORK_MINT,
    FRAMEWORK_NAME_PREFIX,
    LIFECYCLE_STATE_SLOT,
)
from parallax.core.entity._entity import (
    CHANGE_RECORD_SLOT,
    WireNames,
    lifecycle_state,
    wire_names_of,
)
from parallax.core.entity._instance_state import (
    AUXILIARY_STATE_SLOT,
    CARRIED_LAYOUT_ATTRIBUTE,
    COMPACT_STATE_SLOT,
    OPAQUE_SLOTS_ATTRIBUTE,
    BackedModel,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeLocation,
    Column,
    EntityIdentity,
    EntityLocation,
    RelationshipIdentity,
    RelationshipLocation,
    ValueObjectIdentity,
)


def _account(balance: str = "100.00") -> mm.Account:
    return mm.Account(id=1, owner="Ada", balance=Decimal(balance))


def _fetched_account(balance: str = "100.00", version: int = 1) -> mm.Account:
    """One versioned Account standing in for what a read hands back: the
    framework-owned version is present without a caller having authored it."""
    return mm.Account.model_construct(id=1, owner="Ada", balance=Decimal(balance), version=version)


def _record(value: object) -> dict[str, object] | None:
    """``value``'s Change Record as the edit surface wrote it, read from the one
    private slot that surface owns."""
    return cast("dict[str, object] | None", value.__dict__.get(CHANGE_RECORD_SLOT))


# --------------------------------------------------------------------------- #
# Provenance and the Change Record.                                          #
# --------------------------------------------------------------------------- #
def test_a_fresh_instance_carries_no_change_record() -> None:
    assert CHANGE_RECORD_SLOT not in _account().__dict__


def test_an_edit_records_the_earliest_original_value() -> None:
    original = _account(balance="100.00")
    edited = original.edit(balance=Decimal("175.00"))
    assert edited.balance == Decimal("175.00")
    changes = _record(edited)
    assert changes is not None
    assert changes["balance"] == Decimal("100.00")


def test_copies_of_copies_merge_records_keeping_the_earliest_original() -> None:
    original = _account(balance="100.00")
    once = original.edit(balance=Decimal("150.00"))
    twice = once.edit(balance=Decimal("200.00"))
    changes = _record(twice)
    assert changes is not None
    assert changes["balance"] == Decimal("100.00")  # earliest, not 150.00
    assert twice.balance == Decimal("200.00")


def test_a_net_zero_chain_still_records_the_touch() -> None:
    # The record keeps the touch whatever the values net to; whether that touch
    # reaches a row is the codec's question, not the record's.
    original = _account(balance="100.00")
    round_tripped = original.edit(balance=Decimal("200.00")).edit(balance=Decimal("100.00"))
    changes = _record(round_tripped)
    assert changes is not None
    assert changes["balance"] == Decimal("100.00")


def test_an_edit_with_no_changes_is_legal_and_carries_the_existing_record() -> None:
    # Legal because "nothing to write" already has one representation: an empty
    # effective change set. Nothing was authored, so nothing is validated.
    original = _account(balance="100.00")
    edited = original.edit(balance=Decimal("175.00"))
    plain = edited.edit()
    assert plain is not edited
    assert plain.balance == Decimal("175.00")
    assert plain.model_fields_set == edited.model_fields_set
    assert _record(plain) == _record(edited)


def test_an_edit_with_no_changes_on_a_never_edited_value_records_nothing() -> None:
    assert _record(_account().edit()) == {}


# --------------------------------------------------------------------------- #
# Edit refusals: unknown / primary-key / framework-owned / relationship.      #
# --------------------------------------------------------------------------- #
def test_unknown_field_is_rejected() -> None:
    with pytest.raises(EditError, match="unknown member name"):
        _account().edit(shoe_size=9)


def test_primary_key_field_is_rejected() -> None:
    with pytest.raises(EditError, match="primary-key"):
        _account().edit(id=2)


def test_framework_owned_field_is_rejected() -> None:
    with pytest.raises(EditError, match="framework-owned"):
        _account().edit(version=99)


def test_relationship_field_is_rejected() -> None:
    person = mm.Person(id=1, name="Ada")
    with pytest.raises(EditError, match="relationship"):
        person.edit(passport=None)


def test_an_inherited_relationship_locates_at_the_entity_that_declares_it() -> None:
    # `owner` is declared on `Animal` and reached through `Dog`, so the violation
    # names the declaring member: a Relationship Identity names the source Entity
    # that declares it, and `Dog` declares no `owner` for one to name.
    with pytest.raises(EditError) as caught:
        Dog(id=1, name="Rex").edit(owner=None)
    violation = caught.value.violations[0]
    assert violation.location == RelationshipLocation(
        RelationshipIdentity(EntityIdentity("parallax.compatibility", "Animal"), "owner")
    )
    assert violation.member_name == "owner"


def test_an_invalid_scalar_value_raises_at_edit_time_not_at_the_database() -> None:
    with pytest.raises(EditError, match="does not match the declared type"):
        _account().edit(balance="not-a-decimal")


def test_a_dotted_name_is_refused_as_a_path_rather_than_as_an_unknown_member() -> None:
    # `address` is a declared member and `city` is a declared field of it, so
    # reporting the name as unknown would misdiagnose it. What the caller asked
    # for is the sparse write below an occurrence's boundary that
    # `Customer.address.city.set(...)` is refused for, and a keyword edit is the
    # other spelling of the same request. The remedy is composing edits.
    customer = vm.Customer(id=1, name="Ada", address=vm.Address(street="s", city="Oslo"))
    with pytest.raises(EditError, match="never a nested path") as caught:
        customer.edit(**{"address.city": "Bergen"})
    assert caught.value.codes == {"edit-nested-path"}
    violation = caught.value.violations[0]
    assert violation.member_name == "address.city"
    assert violation.location == EntityLocation(
        EntityIdentity("parallax.compatibility", "Customer")
    )


def test_wire_names_of_rejects_a_class_that_declares_nothing() -> None:
    with pytest.raises(EntityDefinitionError, match="not a Parallax Entity Class"):
        wire_names_of(int)


# --------------------------------------------------------------------------- #
# Framework-owned attributes are omitted at construction, and a caller who     #
# supplies one is refused there — where the mistake is — rather than several   #
# steps later when a row is derived from it.                                  #
# --------------------------------------------------------------------------- #
def test_an_audit_only_instance_constructs_cleanly_without_axis_values() -> None:
    balance = mm.Balance(id=1, acct_num="A", value=Decimal("100.00"))
    assert balance.tx_start is None
    assert balance.tx_end is None


def test_a_bitemporal_instance_constructs_cleanly_without_axis_values() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    assert branch.valid_start is None
    assert branch.valid_end is None
    assert branch.tx_start is None
    assert branch.tx_end is None


def test_a_versioned_instance_constructs_cleanly_without_its_version() -> None:
    # The version column is designated the same way an axis endpoint is, so it
    # behaves the same way: omitted at construction, derived at the write.
    assert _account().version is None


def test_supplying_a_transaction_time_value_at_construction_is_refused() -> None:
    with pytest.raises(ValidationError, match="tx_start"):
        mm.Balance(
            id=1,
            acct_num="A",
            value=Decimal("100.00"),
            tx_start=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )


def test_supplying_a_valid_time_value_at_construction_is_refused() -> None:
    with pytest.raises(ValidationError, match="valid_start"):
        mm.Branch(
            id=1, name="Central", address=None, valid_start=dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
        )


def test_supplying_the_version_at_construction_is_refused() -> None:
    with pytest.raises(ValidationError, match="version"):
        mm.Account(id=1, owner="Ada", balance=Decimal("100.00"), version=1)


def test_a_non_temporal_versioned_class_designates_only_its_version() -> None:
    assert wire_names_of(mm.Account).framework_owned_py == frozenset({"version"})
    assert wire_names_of(mm.Branch).framework_owned_py == frozenset(
        {"valid_start", "valid_end", "tx_start", "tx_end"}
    )


def test_the_declaration_carries_no_default_for_an_axis_attribute() -> None:
    # The Pydantic-level `None` default is a construction affordance ONLY — the
    # declared Attribute Metadata is exactly what the corpus model declares (the
    # no-drift guard is the proof; this pin is the unit-level half of it).
    tx_start = next(a for a in mm.Balance.attributes if a.identity.name == "txStart")
    assert tx_start.storage == Column("in_z")
    assert tx_start.nullable is False


# --------------------------------------------------------------------------- #
# For a temporal write family, a materialized CURRENT milestone's real        #
# `out_z`/`thru_z` value is the framework's own open-interval sentinel        #
# (`TemporalBound.INFINITY` — every real Postgres current row decodes to      #
# exactly this, `parallax.postgres.adapter._InfinityTimestamptzLoader`),      #
# which the WRAP construction that materializes it never validates           #
# (`model_construct`) — so an edit's own untouched-field revalidation must    #
# carry a framework-owned field's CURRENT value forward WITHOUT ever          #
# passing it back through the validating constructor, which refuses an       #
# authored one.                                                              #
# --------------------------------------------------------------------------- #
def test_an_edit_carries_forward_an_untouched_axis_fields_infinity_sentinel() -> None:
    balance = mm.Balance.model_construct(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        tx_start=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        tx_end=INFINITY,
    )
    copy = balance.edit(value=Decimal("150.00"))
    assert copy.value == Decimal("150.00")
    assert copy.tx_end is INFINITY  # carried forward, never re-validated


def test_an_edit_carries_forward_a_hydrated_version_untouched() -> None:
    # The version reaches the same carry-forward for the same reason: an edit
    # never re-authors it, so it never faces the constructor that refuses one.
    copy = _fetched_account(version=7).edit(balance=Decimal("150.00"))
    assert copy.balance == Decimal("150.00")
    assert copy.version == 7


def test_an_edit_refuses_an_explicitly_touched_axis_field() -> None:
    # Not a re-validation of the authored value: the axis endpoint is
    # framework-owned, so naming it at all is the refusal, whatever the value.
    balance = mm.Balance.model_construct(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        tx_start=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        tx_end=INFINITY,
    )
    with pytest.raises(EditError, match="txEnd: framework-owned fields may not be assigned"):
        balance.edit(tx_end=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))


# --------------------------------------------------------------------------- #
# Aggregation: every mistake in one report, canonically ordered.              #
# --------------------------------------------------------------------------- #
class _Reading(Entity, table="reading", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    celsius: Attr[float]
    computed: Attr[str | None] = attr(max_length=8, read_only=True)


def _five_mistakes(person: mm.Person) -> EditError:
    with pytest.raises(EditError) as caught:
        person.edit(
            name=42,
            zip_code="0150",
            passport=None,
            id=2,
            shoe_size=9,
        )
    return caught.value


def test_an_invalid_edit_reports_every_violation_once() -> None:
    # Aggregated, not first-failure: a caller correcting five mistakes learns
    # all five at once, each with a code from the closed set, a structured
    # location, and a non-empty message.
    error = _five_mistakes(mm.Person(id=1, name="Ada"))
    assert [violation.code for violation in error.violations] == [
        "edit-unknown-member",
        "edit-unknown-member",
        "edit-primary-key",
        "edit-value-mismatch",
        "edit-relationship-member",
    ]
    assert error.codes == {
        "edit-unknown-member",
        "edit-primary-key",
        "edit-value-mismatch",
        "edit-relationship-member",
    }
    assert all(violation.code in EDIT_CODES for violation in error.violations)
    assert all(violation.message for violation in error.violations)


def test_the_report_is_ordered_by_location_then_code_then_member_name() -> None:
    # The two unresolved names share one Entity location AND one code, so only
    # the third ordering term separates them — which is why it exists.
    person = mm.Person(id=1, name="Ada")
    entity = EntityIdentity("parallax.compatibility", "Person")
    error = _five_mistakes(person)
    assert [(v.location, v.member_name) for v in error.violations] == [
        (EntityLocation(entity), "shoe_size"),
        (EntityLocation(entity), "zip_code"),
        (AttributeLocation(AttributeIdentity(entity, "id")), "id"),
        (AttributeLocation(AttributeIdentity(entity, "name")), "name"),
        (RelationshipLocation(RelationshipIdentity(entity, "passport")), "passport"),
    ]


def test_the_report_does_not_depend_on_caller_keyword_order() -> None:
    person = mm.Person(id=1, name="Ada")
    with pytest.raises(EditError) as caught:
        person.edit(
            shoe_size=9,
            id=2,
            passport=None,
            zip_code="0150",
            name=42,
        )
    assert caught.value.violations == _five_mistakes(person).violations


def test_an_edit_error_retains_no_cause() -> None:
    # The judgement's own rendered text travels in each violation's message, so
    # chaining the carrier would add nothing and expose an internal class.
    error = _five_mistakes(mm.Person(id=1, name="Ada"))
    assert error.__cause__ is None
    assert error.__context__ is None


def test_a_violation_compares_by_its_position_and_code_rather_than_its_wording() -> None:
    located = AttributeLocation(
        AttributeIdentity(EntityIdentity("parallax.compatibility", "Person"), "id")
    )
    assert EditViolation("edit-primary-key", located, "id", "one wording") == EditViolation(
        "edit-primary-key", located, "id", "another"
    )


def test_an_edit_error_reports_at_least_one_violation() -> None:
    with pytest.raises(ValueError, match="at least one violation"):
        EditError([])


def test_every_edit_code_has_a_reachable_refusal() -> None:
    # The closed set is closed from below as well: each of the eight is what
    # some authored mistake actually raises, on the surface that can express it.
    balance = mm.Balance.model_construct(id=1, acct_num="A", value=Decimal("1.00"))
    observed: set[str] = set()
    refusals = (
        lambda: _account().model_copy(),
        lambda: _account().edit(shoe_size=9),
        lambda: mm.Person(id=1, name="Ada").edit(passport=None),
        lambda: vm.Customer.address.city.set("Oslo"),
        lambda: _account().edit(id=2),
        lambda: _Reading(id=1, celsius=1.0).edit(computed="x"),
        lambda: balance.edit(tx_end=dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        lambda: _account().edit(balance="not-a-decimal"),
    )
    for refusal in refusals:
        with pytest.raises(EditError) as caught:
            refusal()
        observed |= caught.value.codes
    assert observed == EDIT_CODES


# --------------------------------------------------------------------------- #
# `edit` is the only door: every inherited copy path creates nothing.         #
# --------------------------------------------------------------------------- #
def test_every_inherited_copy_path_is_refused() -> None:
    # One reachable copy path would defeat the purpose: `__copy__` and
    # `__deepcopy__` carry the Change Record living in the instance dictionary,
    # and the deprecated v1 shim reaches neither name resolution nor judgement.
    edited = _account().edit(balance=Decimal("175.00"))
    doors = (
        lambda: edited.model_copy(),
        lambda: edited.model_copy(update={"balance": Decimal("1.00")}),
        lambda: edited.model_copy(deep=True),
        lambda: edited.copy(),
        lambda: copy_module.copy(edited),
        lambda: copy_module.deepcopy(edited),
    )
    for door in doors:
        with pytest.raises(EditError) as caught:
            door()
        assert caught.value.codes == {"edit-use-edit"}
        violation = caught.value.violations[0]
        assert violation.member_name is None
        assert violation.location == EntityLocation(
            EntityIdentity("parallax.compatibility", "Account")
        )
        assert "edit(**changes)" in violation.message


def test_a_refused_copy_door_retains_no_cause_while_another_error_is_handled() -> None:
    # A copy door examines nothing, so whatever the caller happened to be
    # handling is not why it refused; displaying that unrelated failure beside
    # the refusal would misattribute it.
    edited = _account().edit(balance=Decimal("175.00"))
    doors = (
        lambda: edited.model_copy(),
        lambda: edited.copy(),
        lambda: copy_module.copy(edited),
        lambda: copy_module.deepcopy(edited),
    )
    for door in doors:
        try:
            raise RuntimeError("an unrelated failure being handled")
        except RuntimeError:
            with pytest.raises(EditError) as caught:
                door()
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__


# --------------------------------------------------------------------------- #
# The carry: an edit replaces declared member state and preserves everything   #
# else. Only Entity Graph Construction produces the state at stake — one slot  #
# per navigable relationship (a loaded value, or the closed-world sentinel for #
# a view the read never fetched) and the lifecycle's own state — and the       #
# authored branch rebuilds through the validating constructor, which knows the #
# declared fields alone. Everything outside them is therefore installed after  #
# construction and BY COMPLEMENT, so a kind of state no test here names        #
# travels too. Driven through construction directly, because that is where     #
# this state comes from; what the carried lifecycle state then MEANS to the    #
# Snapshot lifecycle that installed it is graded in                            #
# `test_snapshot_inspection.py`.                                               #
# --------------------------------------------------------------------------- #
_ORDER = sm.SnapOrder.identity
_ITEM = sm.SnapOrderItem.identity
_STATUS = sm.SnapOrderStatus.identity
_PRIMARY_TAG = ValueObjectIdentity(_STATUS, ("primaryTag",))

# Member rows against each exact Entity's own layout: `SnapOrder` is id, name,
# sku, qty, price, active, orderedOn; `SnapOrderItem` is id, orderId, sku,
# quantity, shippedOn; `SnapOrderStatus` is id, orderId, orderItemId, code, then
# its primaryTag and tags occurrences, and a `Tag` row is label, detail, details.
_ORDER_MEMBERS: tuple[object, ...] = (1, "Ada", None, 1, Decimal("1.00"), True, dt.date(2024, 1, 1))
_ITEM_MEMBERS: tuple[object, ...] = (11, 1, "x", 1, None)
_STATUS_MEMBERS: tuple[object, ...] = (21, 1, None, "SHIPPED", ("urgent", ABSENT, ABSENT), ABSENT)

# The kinds of state an edit is asked to carry are the parameters, not the
# assertions: both branches answer the same, which is the invariant one shared
# partition exists to make unbreakable.
_BRANCHES: dict[str, dict[str, object]] = {"authored": {"name": "renamed"}, "change-free": {}}


def _materialized_order(state: object = "one lifecycle's own state") -> sm.SnapOrder:
    """One `SnapOrder` as a lifecycle materializes it: `items` loaded to a single
    child that points back at it, `statuses` never fetched, and lifecycle state
    attached."""

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        item = writer.allocate(_ITEM)
        writer.populate(order, _ORDER_MEMBERS, ((item,), UNLOADED))
        writer.populate(item, _ITEM_MEMBERS, (order, UNLOADED))
        return (order,)

    (root,) = graph_construction_of(sm.SNAP_ORDERS_MODEL).construct(
        build, state_factory=lambda _view, _handle: state
    )
    return cast("sm.SnapOrder", root)


def _materialized_status() -> sm.SnapOrderStatus:
    """One `SnapOrderStatus` carrying a Value Object occurrence — the declared
    kind `SnapOrder` has none of."""

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        status = writer.allocate(_STATUS)
        writer.populate(status, _STATUS_MEMBERS, ())
        return (status,)

    (root,) = graph_construction_of(sm.SNAP_ORDERS_MODEL).construct(
        build, state_factory=lambda _view, _handle: "one lifecycle's own state"
    )
    return cast("sm.SnapOrderStatus", root)


@pytest.mark.parametrize("changes", list(_BRANCHES.values()), ids=list(_BRANCHES))
def test_an_edit_preserves_a_loaded_relationship_view(changes: dict[str, object]) -> None:
    node = _materialized_order()
    copy = node.edit(**changes)
    # The SAME materialized children, not a re-read and not a lookalike: a
    # relationship keyword is refused, so the copy's views keep describing what
    # this read observed.
    assert copy.items[0] is node.items[0]
    assert copy.items[0].order is node


@pytest.mark.parametrize("changes", list(_BRANCHES.values()), ids=list(_BRANCHES))
def test_an_edit_preserves_the_closed_world_sentinel(changes: dict[str, object]) -> None:
    # The view the read never fetched stays unloaded rather than becoming absent,
    # which is what keeps ordinary access a steered refusal naming the include
    # fix instead of a bare missing-key failure.
    copy = _materialized_order().edit(**changes)
    assert relationship_value_of(copy, RelationshipIdentity(_ORDER, "statuses")) is UNLOADED
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        copy.statuses  # noqa: B018 - the access itself is the assertion


@pytest.mark.parametrize("changes", list(_BRANCHES.values()), ids=list(_BRANCHES))
def test_an_edit_preserves_the_lifecycle_state(changes: dict[str, object]) -> None:
    node = _materialized_order()
    assert lifecycle_state_of(node.edit(**changes)) is lifecycle_state_of(node)


@pytest.mark.parametrize("changes", list(_BRANCHES.values()), ids=list(_BRANCHES))
def test_an_edit_carries_a_slot_no_declaration_and_no_lifecycle_names(
    changes: dict[str, object],
) -> None:
    # The proof that the carry is by COMPLEMENT: this slot belongs to no kind
    # either `edit` or a lifecycle knows, and it travels anyway.
    #
    # Stated over an edited copy rather than over the node it came from, because
    # a published node has no storage for such a name to be in: its whole state
    # is its row, its loaded tails, and its author-owned slot, and the complement
    # is over what the backing NAMES rather than over a dictionary. An edited copy
    # is ordinary, so the complement there is a dictionary again.
    node = _materialized_order().edit()
    marker = object()
    object.__setattr__(node, "__parallax_unnamed__", marker)
    assert node.edit(**changes).__dict__["__parallax_unnamed__"] is marker


class _Marked(Entity, table="marked", namespace="parallax.compatibility"):
    """One private attribute, which Pydantic keeps in a slot of the object layout
    rather than in the instance dictionary an edit rebuilds."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)

    _mark = PrivateAttr(default=3)
    _trail = PrivateAttr(default_factory=list)


_REBUILT_SLOTS: Final = frozenset(
    {"__dict__", "__pydantic_fields_set__", COMPACT_STATE_SLOT, AUXILIARY_STATE_SLOT}
)
"""The four slots of the layout an edit fills from semantic state rather than
carrying.

Two are Pydantic's, and the copy's hold the declared members and populated set
the edit derived. Two are the compact backing's, and the copy holds neither: it
is built ordinary, and the author-owned state a published source keeps in the
auxiliary slot reaches the copy's instance dictionary under its own names.
"""

_COPIED_CONTAINER_SLOTS: Final = frozenset({"__pydantic_extra__", "__pydantic_private__"})
"""The whole carried complement: Pydantic's two name-keyed mappings.

The framework keeps writing into both after the copy exists, so sharing one would
make a write to the copy a write to its source; the copy gets its own outer
mapping of each instead.
"""

_CARRIED_BY_IDENTITY: Final = frozenset({LIFECYCLE_STATE_SLOT})
"""The one slot a copy takes as it stands, rather than deriving or copying.

Its payload is whatever a lifecycle's state factory returned and is opaque to
Entity, so there is nothing to copy shallowly and nothing to rebuild: the copy
either carries the record of the read that published its source or it does not,
and `test_an_edit_preserves_the_lifecycle_state` is where it does.
"""


def test_the_framework_lays_out_exactly_the_slots_the_carry_classifies() -> None:
    # The three buckets account for the layout a concrete class ACTUALLY has,
    # walked across its own MRO — which is the layout the carry itself resolves
    # its complement off, so neither side is a hand-list of the roots this suite
    # happens to know. A slot a Pydantic release or a framework root below the
    # shared backing adds therefore travels by default, and this equality is
    # where the treatment it takes is stated rather than absorbed silently.
    # Checked to BE in that layout rather than assumed, because a name that is
    # not there subtracts nothing and the equality below would still hold with
    # one misspelled or retired. The instance dictionary is the one exception,
    # and pinning it is what keeps the check honest: Pydantic gives it a
    # `getset_descriptor` rather than a slot, so it is in no layout either side
    # walks and is named only to say a copy fills it from semantic state.
    assert _REBUILT_SLOTS - {"__dict__"} <= set(layout_slots(_Marked))
    assert "__dict__" not in layout_slots(_Marked)
    assert set(layout_slots(_Marked)) - _REBUILT_SLOTS == (
        _COPIED_CONTAINER_SLOTS | _CARRIED_BY_IDENTITY
    )
    # The identity bucket is production's own declaration rather than this
    # suite's opinion of it: a root names the slots a copy must take as they
    # stand in its own body, beside the `__slots__` that lays them out.
    assert set(cast("Any", Entity).__dict__[OPAQUE_SLOTS_ATTRIBUTE]) == _CARRIED_BY_IDENTITY


def test_a_declared_class_lays_out_no_slot_of_its_own() -> None:
    # What bounds the walk the carry makes over a value's own class: a
    # declaration may not extend a foreign base and may not declare `__slots__`,
    # so every slot that walk can reach is one a framework root laid out — the
    # shared backing root's, plus the lifecycle slot only an Entity is ever
    # handed state for. Reopening either route puts author-owned state in the
    # layout the carry sweeps, which is the reason both are refused.
    with pytest.raises(EntityDefinitionError) as caught:

        class _Slotted(Entity, table="slotted", namespace="parallax.compatibility"):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            __slots__ = ("token",)

            id: Attr[int] = attr(primary_key=True)

    assert caught.value.code == "entity-reserved-member-name"
    assert set(layout_slots(_Marked)) == set(layout_slots(BackedModel)) | {LIFECYCLE_STATE_SLOT}


@pytest.mark.parametrize("changes", [{"label": "b"}, {}], ids=list(_BRANCHES))
def test_an_edit_carries_every_slot_of_the_layout_it_does_not_rebuild(
    changes: dict[str, object],
) -> None:
    # Completeness graded over the layout THIS CLASS actually has, walked across
    # its whole MRO, rather than over the instance dictionary — one slot of that
    # layout. Every other carry test here reads a name out of that dictionary and
    # so can only see state stored under one; `PrivateAttr` state is not, because
    # Pydantic lays it out beside the dictionary, and a copy assembled from a
    # name-keyed mapping alone resets it with nothing failing. How each carried
    # slot travels is graded too: both are mappings the framework keeps writing
    # into, so the copy's is its own and is shallow.
    marked = _Marked(id=1, label="a")
    cast("Any", marked)._mark = 9
    carried = {
        name: slot
        for name, slot in layout_slots(_Marked).items()
        if name not in _REBUILT_SLOTS | _CARRIED_BY_IDENTITY
    }
    assert set(carried) == _COPIED_CONTAINER_SLOTS
    copied = marked.edit(**changes)
    for slot in carried.values():
        held = slot.__get__(marked)
        assert slot.__get__(copied) == held
        if held is not None:
            assert slot.__get__(copied) is not held
    assert cast("Any", copied)._mark == 9


def test_a_carried_slot_is_the_copy_s_own_state_rather_than_the_source_s() -> None:
    marked = _Marked(id=1, label="a")
    cast("Any", marked)._mark = 9
    copied = cast("Any", marked.edit(label="b"))
    copied._mark = 11
    assert cast("Any", marked)._mark == 9


def test_a_carried_slot_is_shallow_so_what_it_holds_stays_shared() -> None:
    # Shallow exactly as Pydantic's own model copy is, and the contract claims no
    # more than that: the copy's private-attribute mapping is its own, so the
    # rebinding above is private to it, while the object under a key is still the
    # source's and an in-place mutation reaches both.
    marked = _Marked(id=1, label="a")
    cast("Any", marked)._trail.append("a")
    copied = cast("Any", marked.edit(label="b"))
    copied._trail.append("b")
    assert cast("Any", marked)._trail == ["a", "b"]


class _Sidecar(Entity, _mint=FRAMEWORK_MINT):
    """A framework root below the shared backing that lays out a slot of its own.

    The shape the carry has to survive without being taught: nothing in
    production names this slot, no bucket classifies it, and the only reason it
    reaches a copy is that the carry walks the layout the value's own class has.
    """

    __slots__ = ("__parallax_sidecar__",)


class _Riding(_Sidecar, table="riding", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_SIDECAR: Final = cast("Any", _Sidecar).__dict__["__parallax_sidecar__"]


@pytest.mark.parametrize("changes", [{"label": "b"}, {}], ids=list(_BRANCHES))
def test_an_edit_carries_a_framework_slot_below_the_shared_root(
    changes: dict[str, object],
) -> None:
    # The case a complement resolved off the shared backing root could not pass:
    # this slot is laid out beneath that root, so such a complement never saw it
    # and the copy came back without it. It travels here because no code names
    # it — the carry reads the layout `_Riding` actually has — and it travels the
    # default way, as its own shallow copy, because its root asked for nothing
    # else.
    value = _Riding(id=1, label="a")
    held = ["a"]
    _SIDECAR.__set__(value, held)
    copied = value.edit(**changes)
    assert _SIDECAR.__get__(copied) == held
    assert _SIDECAR.__get__(copied) is not held


def test_an_edit_leaves_a_framework_slot_the_source_never_held_unheld() -> None:
    # A slot its owner fills only sometimes — a lifecycle slot before a read
    # attaches anything is the live one — has no value for a copy to take, and
    # the copy is left holding none rather than the edit raising on the read.
    copied = _Riding(id=1, label="a").edit(label="b")
    with pytest.raises(AttributeError):
        _SIDECAR.__get__(copied)


def test_a_root_declaring_a_slot_it_does_not_lay_out_opaque_is_refused() -> None:
    # What a declaration nobody checks costs: the misspelling below leaves
    # `__parallax_cargo__` classified for shallow copying, so a copy would hold a
    # copy of a payload its owner said must travel as it stands, and every test
    # of the CORRECT declaration still passes. Refusing the declaration is what
    # makes the convention gradeable rather than a comment.
    class _Misdeclared(Entity, _mint=FRAMEWORK_MINT):
        __slots__ = ("__parallax_cargo__",)
        __parallax_opaque_slots__ = ("__parallax_cargoe__",)

    class _Hauling(_Misdeclared, table="hauling", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(max_length=16)

    with pytest.raises(ValueError, match="__parallax_cargoe__"):
        _Hauling(id=1, label="a").edit(label="b")


def test_a_root_declaring_a_slot_another_class_lays_out_opaque_is_refused() -> None:
    # The same refusal for a name that IS a slot, but of somebody else's body: a
    # root may speak for the layout it declares and no further, so an ancestor's
    # slot cannot be reclassified from below where the ancestor's own copies
    # would still shallow-copy it.
    class _Reaching(Entity, _mint=FRAMEWORK_MINT):
        __parallax_opaque_slots__ = (LIFECYCLE_STATE_SLOT,)

    class _Reached(_Reaching, table="reached", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(max_length=16)

    with pytest.raises(ValueError, match=LIFECYCLE_STATE_SLOT):
        _Reached(id=1, label="a").edit(label="b")


def test_a_root_declaring_a_rebound_ancestor_slot_opaque_is_refused() -> None:
    # The refusal a bound name cannot decide: this body binds the ANCESTOR's own
    # slot descriptor under the ancestor's own name, so a check asking only
    # whether something slot-shaped answers to the name accepts it. Nothing here
    # lays out storage, and accepting the declaration would reclassify a slot
    # `_Sidecar` still shallow-copies for its own copies into one taken by
    # identity — a payload shared between a value and its edit, with every test
    # of a correct declaration still passing.
    class _Reclaiming(_Sidecar, _mint=FRAMEWORK_MINT):
        __parallax_sidecar__ = _SIDECAR
        __parallax_opaque_slots__ = ("__parallax_sidecar__",)

    class _Reclaimed(_Reclaiming, table="reclaimed", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(max_length=16)

    with pytest.raises(ValueError, match="__parallax_sidecar__"):
        _Reclaimed(id=1, label="a").edit(label="b")


class _Lending(Entity, _mint=FRAMEWORK_MINT):
    """A framework root whose slot a sibling root's body rebinds by name."""

    __slots__ = ("__parallax_lent__",)


class _Borrowing(Entity, _mint=FRAMEWORK_MINT):
    __parallax_lent__ = cast("Any", _Lending).__dict__["__parallax_lent__"]


class _Borrowed(_Borrowing, table="borrowed", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


def test_an_edit_ignores_a_slot_descriptor_a_root_only_rebound() -> None:
    # A descriptor addresses an offset in the layout of the class that laid it
    # out, so applying `_Lending`'s to a `_Borrowed` reads no unset slot — it
    # raises `TypeError` outright. A carry that took every slot-shaped binding it
    # walked past would therefore make EVERY edit of this class raise, on a
    # binding that gives its instances no storage at all. The layout the carry
    # walks is the storage the value really has.
    value = _Borrowed(id=1, label="a")
    copied = value.edit(label="b")
    assert copied.label == "b"
    assert "__parallax_lent__" not in layout_slots(_Borrowed)


class _Rolling(
    Entity,
    table="rolling",
    namespace="parallax.compatibility",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class _Tanker(
    _Rolling, namespace="parallax.compatibility", inheritance=ConcreteSubtype(tag_value="tanker")
):
    capacity: Attr[int | None]


def test_the_carried_layout_is_classified_once_per_class_and_again_per_subclass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The walk costs a whole edit, so classifying once per class is load-bearing
    # for what an edit costs rather than tidiness — and every other test here
    # would pass just as well against an edit that recomputed it every time.
    # Counted rather than timed: two edits of one class classify once, and the
    # subclass classifies again rather than answering with what its ancestor
    # already worked out.
    classified: list[type] = []
    real = instance_state.classify_slots

    def counting(cls: type) -> Any:
        classified.append(cls)
        return real(cls)

    monkeypatch.setattr(instance_state, "classify_slots", counting)
    _Rolling(id=1, label="a").edit(label="b")
    _Rolling(id=2, label="b").edit(label="c")
    _Tanker(id=3, label="c", capacity=4).edit(label="d")
    _Tanker(id=4, label="d", capacity=5).edit(label="e")

    assert classified == [_Rolling, _Tanker]
    assert vars(_Rolling)[CARRIED_LAYOUT_ATTRIBUTE] is not vars(_Tanker)[CARRIED_LAYOUT_ATTRIBUTE]


def test_a_subclass_does_not_borrow_an_ancestor_s_shorter_carried_layout() -> None:
    # Why the memo is read out of `cls.__dict__` rather than through the MRO,
    # graded by planting the shorter answer where an inherited lookup would find
    # it. What is planted is a REAL classification — `Entity`'s own, made above
    # the ballast slot — so borrowing it would return a copy silently missing
    # that state rather than raising. The slot travels because the subclass
    # classifies the layout it actually has.
    class _Ballast(Entity, _mint=FRAMEWORK_MINT):
        __slots__ = ("__parallax_ballast__",)

    class _Barge(_Ballast, table="barge", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(max_length=16)

    slot = cast("Any", _Ballast).__dict__["__parallax_ballast__"]
    setattr(_Ballast, CARRIED_LAYOUT_ATTRIBUTE, instance_state.classify_slots(Entity))
    value = _Barge(id=1, label="a")
    held = ["a"]
    slot.__set__(value, held)

    copied = value.edit(label="b")

    assert slot.__get__(copied) == held
    assert CARRIED_LAYOUT_ATTRIBUTE in vars(_Barge)


class _Tag(Entity, table="tag", namespace="parallax.compatibility"):
    """One derived cache, spelled the way the language spells one: the memoized
    answer is computed from a declared member, so it lives in the instance
    dictionary and an edit that replaces that member contradicts it."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)

    @cached_property
    def shouted(self) -> str:
        return self.label.upper()


@pytest.mark.parametrize("changes", [{"label": "b"}, {}], ids=list(_BRANCHES))
def test_an_edit_never_carries_a_derived_cache(changes: dict[str, object]) -> None:
    # The one named exception to the complement, and the reason the guarantee is
    # "everything the edit neither replaces nor invalidates": the class itself
    # declares this slot derived, so no edit may carry it.
    tag = _Tag(id=1, label="a")
    assert tag.shouted == "A"
    assert "shouted" not in tag.edit(**changes).__dict__


def test_a_derived_cache_recomputes_after_an_edit_replaces_what_it_derives_from() -> None:
    tag = _Tag(id=1, label="a")
    assert tag.shouted == "A"
    assert tag.edit(label="b").shouted == "B"


def test_no_class_may_declare_a_framework_slot_a_derived_cache() -> None:
    # The invalidation rule reads the descriptor off the class, so a class binding
    # a framework slot name would have the edited copy recompute the author's own
    # answer in place of the state the edit dropped — a materialized node's
    # lifecycle state among them, taking snapshot inspection and pin provenance
    # with it. The collision is refused where it is authored instead.
    with pytest.raises(EntityDefinitionError) as caught:

        class _Colliding(Entity, table="colliding", namespace="parallax.compatibility"):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            id: Attr[int] = attr(primary_key=True)

            @cached_property
            def __parallax_lifecycle__(self) -> str:
                return "shadow"

    assert caught.value.code == "entity-reserved-member-name"


def test_every_slot_the_edit_surface_owns_falls_under_the_reserved_prefix() -> None:
    # The reservation above is by prefix, so a framework slot spelled outside it
    # would be bindable — and therefore droppable — again.
    assert LIFECYCLE_STATE_SLOT.startswith(FRAMEWORK_NAME_PREFIX)
    assert CHANGE_RECORD_SLOT.startswith(FRAMEWORK_NAME_PREFIX)


def test_the_freshly_merged_change_record_replaces_the_carried_one() -> None:
    # The source's own record is outside the declared set, so it is carried like
    # any other state — and then overwritten by the merged one as the last step,
    # which is the ordering that keeps a chain's earliest originals intact.
    once = _materialized_order().edit(name="renamed")
    twice = once.edit(qty=2)
    assert _record(twice) == {"name": "Ada", "qty": 1}


def test_an_edit_of_a_plainly_constructed_value_adds_no_lifecycle_state_or_view() -> None:
    # The carry only ever preserves state a value already had, so provenance —
    # not editedness — is what distinguishes an edited node from an edited
    # construction: this value never had a view or a state to keep.
    copy = sm.SnapOrder(
        id=1,
        name="Ada",
        sku=None,
        qty=1,
        price=Decimal("1.00"),
        active=True,
        ordered_on=dt.date(2024, 1, 1),
    ).edit(name="renamed")
    assert lifecycle_state_of(copy) is None
    assert "items" not in copy.__dict__


# The kinds of instance state a materialized node's edited copy carries, named
# by hand rather than read off the code that installs them, so a kind added on
# either side fails here instead of agreeing with itself. A sixth kind lands in
# no bucket, and answering this failure is where its author decides whether an
# edit carries it.
#
# Lifecycle state is the one kind that is not under a name in the copy's
# dictionary: it rides a slot of the Entity root's own layout, which is what lets
# a published node hold it while holding no dictionary at all, so it is counted
# where it lives rather than where the other five do.
_STATE_KINDS = frozenset(
    {
        "declared attribute",
        "declared value object",
        "relationship slot",
        "lifecycle state",
        "change record",
    }
)


def _state_kind(py_name: str, names: WireNames) -> str | None:
    if py_name == "__parallax_changes__":
        return "change record"
    if py_name in names.relationship_identities:
        return "relationship slot"
    if py_name in names.vo_classes:
        return "declared value object"
    if py_name in names.py_to_name:
        return "declared attribute"
    return None


def test_every_kind_of_state_an_edited_node_carries_is_one_of_the_five_named() -> None:
    observed: set[str] = set()
    for node in (_materialized_order().edit(name="renamed"), _materialized_status().edit(code="X")):
        names = wire_names_of(type(node))
        for py_name in node.__dict__:
            kind = _state_kind(py_name, names)
            assert kind is not None, py_name
            observed.add(kind)
        assert lifecycle_state(node) is not None
        observed.add("lifecycle state")
    assert observed == _STATE_KINDS
