"""An Entity value read as a Typed write's source: the members it populated,
the key it names its object by, and what its edit chain touched, each answered
in the resolved Entity's member order, and the two closed ``EntityRowError``
codes.

Whether an authored value changed anything is not asked here: that is the
document codec's one rule, pinned at its own interface and consumed by the keyed
write ingress. The write path's consumption of this source lives in
``test_transaction_writes.py``; what this suite pins is the source itself,
driven with no Unit of Work, no SQL, and no adapter in reach.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Final

import pytest
from pydantic import TypeAdapter

from parallax.conformance import read_models as rm
from parallax.core import Attr, Entity, ValueObject, attr
from parallax.core.entity import DomainModel, EntityDefinitionError
from parallax.core.entity._entity import CHANGE_RECORD_SLOT, ChangeRecord
from parallax.core.entity._errors import ENTITY_ROW_CODES, EntityRowError
from parallax.core.metamodel import UnresolvedEntityDeclaration
from tests._support import mirrored_models as mm
from tests._support import snapshot_models as sm
from tests._support import value_object_models as vm
from tests._support.typed_write_source import TypedWriteSource
from tests.unit._authored_storage_support import (
    answering_for_instance_state,
    forge_into_storage,
    stored_state,
)
from tests.unit.core.entity._compact_support import carries_instance_storage, published
from tests.unit.core.entity._value_object_document_support import inserted_document

_SPEC_CODES = frozenset({"entity-row-member-missing", "entity-row-malformed-provenance"})

_NS = "parallax.rowcodec"


class Widget(Entity, table="widget", namespace=_NS):
    """The narrow declaration of ``parallax.rowcodec.Widget``."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


class WiderWidget(Entity, name="Widget", table="widget", namespace=_NS):
    """A SECOND class declaring the identical Entity Identity with one member
    more — the cross-model value the resolution-not-ownership rule admits, and
    the only way a write meets a member its own model does not declare."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]
    extra: Attr[str | None]


class RekeyedWidget(Entity, name="Widget", table="widget", namespace=_NS):
    """A THIRD class declaring the identical Entity Identity keyed by a member of
    another name — nothing requires two declarations of one Entity to agree on
    the primary key, and this is the value whose class supplies no attribute for
    a member the resolved identity does declare."""

    key: Attr[int] = attr(primary_key=True)
    label: Attr[str]


class Keyed(Entity, table="keyed", namespace=_NS):
    """An `int64` primary key — one of the two types a corpus primary key holds."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


class Labelled(Entity, table="labelled", namespace=_NS):
    """A `string` primary key — the other."""

    code: Attr[str] = attr(primary_key=True, max_length=16)
    label: Attr[str]


class Detail(ValueObject):
    note: Attr[str | None]


class Interleaved(Entity, table="interleaved", namespace=_NS):
    """A declaration interleaving an Attribute and a top-level Value Object,
    which is the only shape a row's category order is visible in."""

    id: Attr[int] = attr(primary_key=True)
    detail: Attr[Detail | None]
    tail: Attr[str]


KEYED_MODEL = DomainModel(Keyed)
LABELLED_MODEL = DomainModel(Labelled)
NARROW_MODEL = DomainModel(Widget)
WIDER_MODEL = DomainModel(WiderWidget)
INTERLEAVED_MODEL = DomainModel(Interleaved)


_FORGED_RECORD: Final = {"label": "never authored"}


class FilteredWidget(Entity, name="Widget", table="widget", namespace=_NS):
    """A declaration whose class body denies the Change Record its storage holds."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]

    __getattribute__ = answering_for_instance_state(CHANGE_RECORD_SLOT)


class InventedWidget(Entity, name="Widget", table="widget", namespace=_NS):
    """A declaration whose class body offers a Change Record no edit ever wrote."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]

    __getattribute__ = answering_for_instance_state(CHANGE_RECORD_SLOT, _FORGED_RECORD)


class ForgeableWidget(Entity, name="Widget", table="widget", namespace=_NS):
    """A declaration whose values a caller forges a Change Record into."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


def _every_construction_door[E: Entity](cls: type[E], state: dict[str, Any]) -> tuple[E, ...]:
    """One ``cls`` value from each door Pydantic builds one through.

    The validating constructor and ``model_construct`` are the two the framework
    itself uses — the second is the door an edit's restatement builds through, and
    materialization enters neither — and ``model_validate`` and a nested
    ``TypeAdapter`` validation are the two it never calls but a caller can: the
    last one builds inside pydantic-core with no framework call site at all.
    """
    nested_type = list[cls]
    return (
        cls(**state),
        cls.model_construct(**state),
        cls.model_validate(dict(state)),
        TypeAdapter[list[E]](nested_type).validate_python([dict(state)])[0],
    )


class _ClasslessSource:
    """A descriptor-frontend formation input: a model composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (Widget,)


def _account(balance: str = "100.00") -> mm.Account:
    return mm.Account(id=1, owner="Ada", balance=Decimal(balance))


def _fetched_account(balance: str = "100.00", version: int = 1) -> mm.Account:
    """One versioned Account standing in for what a read hands back: the
    framework-owned version is present without a caller having authored it."""
    return mm.Account.model_construct(id=1, owner="Ada", balance=Decimal(balance), version=version)


def _accounts() -> TypedWriteSource:
    return TypedWriteSource(mm.ACCOUNT_MODEL)


# --------------------------------------------------------------------------- #
# The members a value populated, in the resolved Entity's own order.          #
# --------------------------------------------------------------------------- #
def test_a_model_composing_no_entity_class_still_derives_rows() -> None:
    # The reading resolves against declared metadata and never consults the
    # class index, so it is total where materialization is not.
    descriptor_backed = DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam
    assert TypedWriteSource(descriptor_backed).row(Widget(id=1, label="a")) == {
        "id": 1,
        "label": "a",
    }


def test_a_row_projects_every_member_the_caller_set() -> None:
    assert _accounts().row(_account("5.00")) == {
        "id": 1,
        "owner": "Ada",
        "balance": Decimal("5.00"),
    }


def test_a_row_omits_a_member_the_caller_never_populated() -> None:
    row = TypedWriteSource(mm.WRITABLE_SCALARS_MODEL).row(mm.WritableScalar(id=1, label="x"))
    assert row == {"id": 1, "label": "x"}


def test_a_row_carries_every_declarable_scalar_type() -> None:
    scalars = mm.WritableScalar(
        id=1,
        f32=1.5,
        f64=2.5,
        payload=b"\x00\x01",
        local_time=dt.time(1, 2, 3),
        external_id=uuid.UUID("00000000-0000-4000-8000-000000000000"),
        amount=Decimal("1.2345"),
        label="x",
    )
    assert TypedWriteSource(mm.WRITABLE_SCALARS_MODEL).row(scalars) == {
        "id": 1,
        "f32": 1.5,
        "f64": 2.5,
        "payload": b"\x00\x01",
        "localTime": dt.time(1, 2, 3),
        "externalId": uuid.UUID("00000000-0000-4000-8000-000000000000"),
        "amount": Decimal("1.2345"),
        "label": "x",
    }


def test_a_row_borrows_a_nullable_value_object_for_shared_preparation() -> None:
    customer = vm.Customer(
        id=1,
        name="Ada",
        address=vm.Address(street="Main St", city="Berlin", geo=None, phones=()),
    )
    row = TypedWriteSource(vm.CUSTOMER_MODEL).row(customer)
    assert row["address"] is customer.address


def test_a_row_borrows_a_many_value_object_collection_for_shared_preparation() -> None:
    status = sm.SnapOrderStatus(
        id=1,
        order_id=1,
        order_item_id=None,
        code="shipped",
        primary_tag=None,
        tags=(sm.Tag(label="a", detail=None, details=()),),
    )
    assert TypedWriteSource(sm.SNAP_ORDERS_MODEL).row(status)["tags"] is status.tags


def test_a_row_borrows_a_value_object_without_rendering_its_containment_tree() -> None:
    sample = mm.Sample(
        id=1,
        label="one",
        profile=mm.SampleProfile(
            flag=True,
            small=1,
            big=2,
            ratio=0.5,
            measure=1.5,
            text="t",
            amount=Decimal("1.25"),
            blob=b"\x02",
            day=dt.date(2026, 1, 1),
            clock=dt.time(4, 5, 6),
            instant=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            token=uuid.UUID("00000000-0000-4000-8000-000000000001"),
            origin=mm.SampleOrigin(city="Oslo", since=dt.date(2020, 1, 1)),
            entries=(mm.SampleEntry(kind="k", active=True, price=Decimal("2.00"), issued=None),),
        ),
    )
    profile = TypedWriteSource(mm.DOCUMENT_CODEC_MODEL).row(sample)["profile"]
    assert sample.profile is not None
    assert profile is sample.profile
    document = inserted_document(mm.DOCUMENT_CODEC_MODEL, sample)
    assert document["day"] == "2026-01-01"


def test_a_row_emits_the_canonical_member_name_and_never_its_column() -> None:
    # `taxID` is authored by `name=` and stored in `tax_id`, whose mechanical
    # default would be `tax_i_d`: physical names are m-storage-layout's, so
    # neither spelling may appear in a row.
    row = TypedWriteSource(mm.TAXPAYER_MODEL).row(mm.Taxpayer(id=1, tax_id="T-1", name="Ada"))
    assert row == {"id": 1, "taxID": "T-1", "name": "Ada"}
    assert "tax_id" not in row
    assert "tax_i_d" not in row


def test_a_row_is_ordered_by_the_models_family_effective_declaration_order() -> None:
    # Base-first, so an inherited member precedes the concrete's own — and the
    # order is the model's, never the order the caller populated members in.
    card = rm.CardPayment(card_network="Visa", amount=Decimal("10.00"), id=1)
    row = TypedWriteSource(mm.PAYMENT_MODEL).row(card)
    assert list(row) == ["id", "amount", "cardNetwork"]


def test_a_row_orders_attributes_before_top_level_value_objects() -> None:
    # The order is a stable CATEGORY pass — Attributes in declaration order, then
    # top-level Value Objects in theirs — so `tail` precedes the earlier-declared
    # `detail`. Ordering by the declaration's own interleaving would make a row's
    # keys depend on the value's class, which a row never does.
    row = TypedWriteSource(INTERLEAVED_MODEL).row(
        Interleaved(id=1, detail=Detail(note="n"), tail="t")
    )
    assert list(row) == ["id", "tail", "detail"]


# --------------------------------------------------------------------------- #
# Framework-owned members are read as unstated, never refused or emitted.    #
# --------------------------------------------------------------------------- #
def test_a_row_omits_a_hydrated_version_rather_than_refusing_it() -> None:
    # Refusing would make a stored row unreadable; emitting would launder stored
    # state into a caller assignment.
    hydrated = _fetched_account(version=7)
    assert "version" in hydrated.model_fields_set
    assert _accounts().row(hydrated) == {
        "id": 1,
        "owner": "Ada",
        "balance": Decimal("100.00"),
    }


def test_a_row_omits_hydrated_temporal_axis_endpoints() -> None:
    hydrated = mm.Balance.model_construct(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        tx_start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        tx_end=dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    )
    assert TypedWriteSource(mm.BALANCE_MODEL).row(hydrated) == {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("100.00"),
    }


def test_a_constructed_instance_needs_no_framework_owned_value_to_derive_a_row() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    assert TypedWriteSource(mm.BRANCH_MODEL).row(branch) == {
        "id": 1,
        "name": "Central",
        "address": None,
    }


# --------------------------------------------------------------------------- #
# An identity row: the declared primary key, read like every other member.   #
# --------------------------------------------------------------------------- #
def test_an_identity_row_projects_only_the_declared_primary_key() -> None:
    assert _accounts().identity(_fetched_account(version=7)) == {"id": 1}


def test_an_identity_row_carries_the_values_the_instance_holds_unchanged() -> None:
    account = _account()
    assert _accounts().identity(account)["id"] is account.id


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Keyed(id=7, label="a"), 7), (Labelled(code="K-1", label="a"), "K-1")],
    ids=["int64", "string"],
)
def test_serialization_is_the_identity_on_every_type_a_primary_key_can_hold(
    value: Entity, expected: object
) -> None:
    # A primary key is structurally restricted to a scalar Attribute and the
    # source borrows scalar values unchanged — which is why reading it moves no
    # emitted bind: the metamodel schema gives `primaryKey` to an Attribute
    # alone, and never to a Value Object occurrence.
    source = TypedWriteSource(KEYED_MODEL if isinstance(value, Keyed) else LABELLED_MODEL)
    (emitted,) = source.identity(value).values()
    assert emitted is expected or emitted == expected


# --------------------------------------------------------------------------- #
# An authored row: the whole selection, with no effectiveness weighed.       #
# --------------------------------------------------------------------------- #
def test_an_authored_row_answers_every_touched_member_beside_the_key() -> None:
    authored = _accounts().authored(_account("100.00").edit(balance=Decimal("175.00")))
    assert authored is not None
    assert authored == {"id": 1, "balance": Decimal("175.00")}


def test_an_authored_row_keeps_a_restored_member() -> None:
    # 100 -> 150 -> 100 still answers the member the chain touched: what a
    # restoration means is the consumer's question.
    chained = _account("100.00").edit(balance=Decimal("150.00")).edit(balance=Decimal("100.00"))
    authored = _accounts().authored(chained)
    assert authored is not None
    assert authored == {"id": 1, "balance": Decimal("100.00")}


def test_an_authored_row_answers_none_only_for_a_chain_that_touched_nothing() -> None:
    assert _accounts().authored(_account()) is None
    assert _accounts().authored(_account().edit()) is None


def test_an_authored_row_reads_a_published_value_s_provenance_without_creating_storage() -> None:
    # A published value keeps its members in a row and no instance storage of its
    # own. The provenance slot is absent either way, but reaching for the storage
    # to learn that would CREATE the dictionary — permanently, per node, on a
    # read every write makes of the value it is handed.
    value = published(mm.Account, id=1, owner="Ada", balance=Decimal("100.00"), version=1)
    assert _accounts().authored(value) is None
    assert _accounts().row(value) == {"id": 1, "owner": "Ada", "balance": Decimal("100.00")}
    assert not carries_instance_storage(value)


def test_an_authored_row_states_a_changed_value_object_beside_a_raw_identity() -> None:
    # The identity is read directly and the occurrence stays in its frontend
    # carrier so shared preparation can traverse it once.
    original = mm.Traveler(
        id=1,
        address=mm.TravelerAddress(city="Oslo", geo=mm.TravelerGeo(country="Norway")),
        tags=(),
    )
    edited = original.edit(address=mm.TravelerAddress(city="Bergen"))
    authored = TypedWriteSource(mm.DOCUMENT_LAYOUT_MODEL).authored(edited)
    assert authored is not None
    assert authored["id"] == 1
    assert authored["address"] is edited.address


def test_an_authored_row_follows_the_models_member_order() -> None:
    # One order, from the model, whatever order the caller edited members in.
    edited = _account("100.00").edit(balance=Decimal("175.00"), owner="Grace")
    authored = _accounts().authored(edited)
    assert authored is not None
    assert list(authored) == ["id", "owner", "balance"]


def test_an_authored_row_borrows_the_occurrence_it_now_holds() -> None:
    original = vm.Address(
        street="Main St", city="Oslo", geo=None, phones=(vm.Phone(number="555-0100"),)
    )
    edited = vm.Customer(id=1, name="Ada", address=original).edit(
        address=vm.Address(street="Main St", city="Bergen", geo=None, phones=())
    )
    authored = TypedWriteSource(vm.CUSTOMER_MODEL).authored(edited)
    assert authored is not None
    assert authored["address"] is edited.address


def test_an_authored_row_refuses_a_selection_a_restoration_would_have_carried() -> None:
    # The selection is judged from both sides before either value is read, so a
    # member the resolved identity does not declare is refused even where the
    # chain restored it and no consumer would have written anything for it.
    restored = WiderWidget(id=1, label="a", extra="x").edit(extra="y").edit(extra="x")
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(NARROW_MODEL).authored(restored)
    assert refusal.value.code == "entity-row-member-missing"


# --------------------------------------------------------------------------- #
# The two refusals.                                                           #
# --------------------------------------------------------------------------- #
def test_a_value_from_another_model_declaring_the_same_identity_derives_a_row() -> None:
    # Input validation resolves; it does not own. The emitted row is a function
    # of the RESOLVED identity's declared members, so a foreign class populating
    # only declared members is ordinary input.
    foreign = WiderWidget(id=1, label="a")
    assert TypedWriteSource(NARROW_MODEL).row(foreign) == {"id": 1, "label": "a"}


def test_a_row_refuses_a_populated_member_the_resolved_identity_does_not_declare() -> None:
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(NARROW_MODEL).row(WiderWidget(id=1, label="a", extra="x"))
    assert refusal.value.code == "entity-row-member-missing"
    assert "'extra'" in refusal.value.message


def test_the_same_value_emits_an_identity_row_and_an_untouched_authored_row() -> None:
    # Refusal follows SELECTION: `identity_row` drops every non-key member and
    # `authored_row` every member its Change Record does not name, so neither
    # loses anything by dropping one more.
    wider = WiderWidget(id=1, label="a", extra="x")
    source = TypedWriteSource(NARROW_MODEL)
    assert source.identity(wider) == {"id": 1}
    authored = source.authored(wider.edit(label="b"))
    assert authored is not None
    assert authored == {"id": 1, "label": "b"}


def test_an_authored_row_refuses_a_recorded_name_the_resolved_identity_does_not_declare() -> None:
    edited = WiderWidget(id=1, label="a", extra="x").edit(extra="y")
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(NARROW_MODEL).authored(edited)
    assert refusal.value.code == "entity-row-member-missing"


def test_a_cross_model_value_keyed_by_another_member_derives_no_identity_row() -> None:
    # The resolved identity declares `id`; this value's class keys the same
    # Entity by `key` and carries no attribute to read `id` from. Dropping it
    # would hand a keyed write an unkeyed `{}` outside the closed vocabulary.
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(NARROW_MODEL).identity(RekeyedWidget(key=1, label="a"))
    assert refusal.value.code == "entity-row-member-missing"
    assert "'id'" in refusal.value.message
    assert refusal.value.identity == Widget.identity


def test_a_cross_model_value_keyed_by_another_member_derives_no_authored_row() -> None:
    # `authored_row` selects the primary key too, so the identity half is judged
    # by the same rule rather than emitted short.
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(NARROW_MODEL).authored(RekeyedWidget(key=1, label="a").edit(label="b"))
    assert refusal.value.code == "entity-row-member-missing"
    assert "'id'" in refusal.value.message


@pytest.mark.parametrize(
    "net_zero",
    [
        RekeyedWidget(key=1, label="a").edit(),
        RekeyedWidget(key=1, label="a").edit(label="b").edit(label="a"),
    ],
    ids=["no-changes", "restored-chain"],
)
def test_a_net_zero_edit_of_a_rekeyed_value_is_refused_rather_than_answering_none(
    net_zero: RekeyedWidget,
) -> None:
    # An empty touched set never narrows the selection, and the primary key is
    # half of it: "nothing to compare" cannot excuse a key member the value's
    # class supplies no attribute for, or `None` would answer for a value no
    # write could have keyed.
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(NARROW_MODEL).authored(net_zero)
    assert refusal.value.code == "entity-row-member-missing"
    assert "'id'" in refusal.value.message


def test_a_recorded_name_the_value_supplies_no_attribute_for_is_refused() -> None:
    # The other side of the pairing, reached through the RECORDED half of
    # `authored_row`'s selection rather than the key half: `extra` is declared by
    # the resolved identity and named by the record, and this narrower class
    # carries no attribute to emit its current value from. Suppliedness is judged
    # before anything is read, because reading it would escape the closed code
    # set with an `AttributeError`.
    narrow = Widget(id=1, label="a")
    object.__setattr__(narrow, CHANGE_RECORD_SLOT, ChangeRecord({"extra": "x"}))
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(WIDER_MODEL).authored(narrow)
    assert refusal.value.code == "entity-row-member-missing"
    assert "'extra'" in refusal.value.message
    assert refusal.value.identity == Widget.identity


def test_a_never_edited_value_derives_no_authored_row() -> None:
    # An absent record and an empty one name the same empty selection, so the
    # ordinary never-edited value answers `None` rather than a keyed row with
    # nothing beside the key.
    assert _accounts().authored(_account()) is None


@pytest.mark.parametrize(
    "carrier",
    [["balance"], "balance", {1: "not-a-member-name"}, {"balance": Decimal("1.00")}],
    ids=["list", "str", "int-keyed", "well-shaped"],
)
def test_a_change_record_no_edit_wrote_reports_corruption_rather_than_absence(
    carrier: object,
) -> None:
    # Told apart by the SLOT rather than by its contents: collapsing a carrier
    # the framework never wrote into "never edited" would name the wrong defect.
    # A well-shaped mapping is one of these, because what makes a mapping a
    # Change Record is that `edit(...)` made it, not what it looks like.
    account = _account()
    object.__setattr__(account, CHANGE_RECORD_SLOT, carrier)
    with pytest.raises(EntityRowError) as refusal:
        _accounts().authored(account)
    assert refusal.value.code == "entity-row-malformed-provenance"


def test_a_class_body_denying_the_change_record_still_writes_the_edit() -> None:
    # No class body may bind `__dict__`, but `__getattribute__` is authorable and
    # answers every read of that name. The Change Record is private first-party
    # state only `edit(...)` writes, so the source reads the value's own storage:
    # an edit that touched a member lowers to the sparse row it authored even
    # when the class denies the slot the storage holds.
    edited = FilteredWidget(id=1, label="a").edit(label="b")
    assert CHANGE_RECORD_SLOT not in edited.__dict__

    authored = TypedWriteSource(NARROW_MODEL).authored(edited)
    assert authored is not None
    assert authored == {"id": 1, "label": "b"}


def test_a_class_body_inventing_a_change_record_earns_no_row() -> None:
    # The same fact from the other side: a class answering with a record the
    # storage never held names no edit, so the value a caller never edited stays
    # the one proposition `None` makes rather than emitting an unearned write.
    plain = InventedWidget(id=1, label="a")
    assert plain.__dict__[CHANGE_RECORD_SLOT] == _FORGED_RECORD

    assert TypedWriteSource(NARROW_MODEL).authored(plain) is None


def test_a_change_record_forged_into_a_value_s_own_storage_earns_no_row() -> None:
    # Denial and invention are answers the source reads past. This is the storage
    # itself, doctored by a caller holding the value — the residual no in-process
    # design closes, and the one the carrier answers. What can be put there is a
    # well-shaped mapping, and a Change Record is not a shape: only `edit(...)`
    # constructs the carrier both readers accept, so private state the framework
    # never wrote is corruption rather than provenance — through every door a
    # value is built by.
    for plain in _every_construction_door(ForgeableWidget, {"id": 1, "label": "a"}):
        forge_into_storage(plain, CHANGE_RECORD_SLOT, dict(_FORGED_RECORD))
        assert stored_state(plain)[CHANGE_RECORD_SLOT] == _FORGED_RECORD
        with pytest.raises(EntityRowError) as refusal:
            TypedWriteSource(NARROW_MODEL).authored(plain)
        assert refusal.value.code == "entity-row-malformed-provenance"


def test_no_class_body_may_answer_for_the_slot_the_record_lives_beside() -> None:
    # The route the two doctored declarations above do NOT take, because it is
    # closed at class creation: `__dict__` is the name the framework presents a
    # published value's state under, so a body binding it would decide what every
    # reader of every instance is told rather than doctoring one slot.
    with pytest.raises(EntityDefinitionError) as refusal:

        class Bound(Entity, name="Widget", table="widget", namespace=_NS):  # pyright: ignore[reportUnusedClass] - the declaration is refused, so nothing uses it
            id: Attr[int] = attr(primary_key=True)

            __dict__ = {}  # pyright: ignore[reportGeneralTypeIssues, reportAssignmentType] - the point of the probe

    assert refusal.value.code == "entity-reserved-member-name"


def test_an_edit_of_such_a_value_still_records_the_original_it_touched() -> None:
    # Refusing the forgery costs an edit nothing: the copy carries the carrier
    # `edit(...)` wrote over whatever the original held, so the row names the
    # member the caller touched and the original the value really held.
    original = ForgeableWidget(id=1, label="a")
    forge_into_storage(original, CHANGE_RECORD_SLOT, dict(_FORGED_RECORD))
    edited = original.edit(label="b")

    authored = TypedWriteSource(NARROW_MODEL).authored(edited)
    assert authored is not None
    assert authored == {"id": 1, "label": "b"}


# --------------------------------------------------------------------------- #
# Refusal order: one input, one code.                                         #
# --------------------------------------------------------------------------- #
def test_a_never_edited_value_still_judges_the_primary_key_selection() -> None:
    # A never-edited value and a chain that touched nothing answer `None`
    # through the SAME path, so both judge the identity selection first: a value
    # whose class carries no attribute for a key member the resolved identity
    # declares is refused rather than answered.
    with pytest.raises(EntityRowError) as refusal:
        TypedWriteSource(NARROW_MODEL).authored(RekeyedWidget(key=1, label="a"))
    assert refusal.value.code == "entity-row-member-missing"
    assert "'id'" in refusal.value.message


# --------------------------------------------------------------------------- #
# The closed code set.                                                        #
# --------------------------------------------------------------------------- #
def test_the_code_set_is_closed_against_an_unlisted_code() -> None:
    assert ENTITY_ROW_CODES == _SPEC_CODES
    with pytest.raises(ValueError, match="not an entity row code"):
        EntityRowError(code="entity-row-nosuch", message="invented")
