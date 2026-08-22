"""The Entity Row Codec: ``full_row`` / ``identity_row`` / ``edited_row``, the
``row_codec_of`` seam, and the five closed ``EntityRowError`` codes (spec §5).

The write path's consumption of the codec lives in ``test_transaction_writes.py``
and ``tests/api/test_edited_row_no_drift.py``; what this suite pins is the codec
itself, driven with no Unit of Work, no SQL, and no adapter in reach.
"""

from __future__ import annotations

import ast
import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from _snapshot_graph_support import GraphFixture

from _support import mirrored_models as mm
from _support import snapshot_models as sm
from _support import value_object_models as vm
from parallax.conformance import read_models as rm
from parallax.core import Attr, Entity, ValueObject, attr
from parallax.core.entity import (
    ENTITY_ROW_CODES,
    DomainModel,
    EntityRowCodec,
    EntityRowError,
    graph_construction_of,
    row_codec_of,
)
from parallax.core.entity._entity import CHANGE_RECORD_SLOT
from parallax.core.entity._model import model_of
from parallax.core.entity._row_codec import (
    _assignment_matches_original,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.metamodel import UnresolvedEntityDeclaration

_SPEC_CODES = frozenset(
    {
        "entity-row-not-an-entity",
        "entity-row-target-not-in-model",
        "entity-row-member-missing",
        "entity-row-malformed-provenance",
    }
)

_NS = "parallax.rowcodec"


class Widget(Entity, table="widget", namespace=_NS):
    """The narrow declaration of ``parallax.rowcodec.Widget``."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


class WiderWidget(Entity, name="Widget", table="widget", namespace=_NS):
    """A SECOND class declaring the identical Entity Identity with one member
    more — the cross-model value the resolution-not-ownership rule admits, and
    the only way a codec meets a member its own model does not declare."""

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


class _ClasslessSource:
    """A descriptor-frontend formation input: a model composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (Widget,)


def _account(balance: str = "100.00") -> mm.Account:
    return mm.Account(id=1, owner="Ada", balance=Decimal(balance))


def _fetched_account(balance: str = "100.00", version: int = 1) -> mm.Account:
    """One versioned Account as a read hands it back: the framework-owned version
    arrives through the validation-free path a caller cannot author through."""
    return mm.Account.model_construct(id=1, owner="Ada", balance=Decimal(balance), version=version)


def _accounts() -> EntityRowCodec:
    return row_codec_of(mm.ACCOUNT_MODEL)


# --------------------------------------------------------------------------- #
# The seam: one codec per model, retained, and independent of its sibling.    #
# --------------------------------------------------------------------------- #
def test_a_model_reaches_one_retained_codec() -> None:
    assert row_codec_of(mm.ACCOUNT_MODEL) is row_codec_of(mm.ACCOUNT_MODEL)
    assert row_codec_of(mm.ACCOUNT_MODEL) is not row_codec_of(mm.BALANCE_MODEL)


def test_the_two_capability_seams_answer_independently() -> None:
    # Each seam owns its own slot; neither is a projection of a composite value,
    # and reaching one never builds the other.
    model = DomainModel(Widget)
    codec = row_codec_of(model)
    assert graph_construction_of(model) is not codec
    assert row_codec_of(model) is codec


def test_a_model_composing_no_entity_class_still_derives_rows() -> None:
    # The codec resolves an Entity Identity against declared metadata and never
    # consults the class index, so the seam is total where materialization is not.
    descriptor_backed = DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam
    assert row_codec_of(descriptor_backed).full_row(Widget(id=1, label="a")) == {
        "id": 1,
        "label": "a",
    }


# --------------------------------------------------------------------------- #
# full_row: the populated selection, canonically keyed and serialized.        #
# --------------------------------------------------------------------------- #
def test_full_row_projects_every_member_the_caller_set() -> None:
    assert _accounts().full_row(_account("5.00")) == {
        "id": 1,
        "owner": "Ada",
        "balance": Decimal("5.00"),
    }


def test_full_row_omits_a_member_the_caller_never_populated() -> None:
    row = row_codec_of(mm.WRITABLE_SCALARS_MODEL).full_row(mm.WritableScalar(id=1, label="x"))
    assert row == {"id": 1, "label": "x"}


def test_full_row_carries_every_declarable_scalar_type() -> None:
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
    assert row_codec_of(mm.WRITABLE_SCALARS_MODEL).full_row(scalars) == {
        "id": 1,
        "f32": 1.5,
        "f64": 2.5,
        "payload": b"\x00\x01",
        "localTime": dt.time(1, 2, 3),
        "externalId": uuid.UUID("00000000-0000-4000-8000-000000000000"),
        "amount": Decimal("1.2345"),
        "label": "x",
    }


def test_full_row_serializes_a_nullable_value_object_to_its_canonical_document() -> None:
    customer = vm.Customer(
        id=1,
        name="Ada",
        address=vm.Address(street="Main St", city="Berlin", geo=None, phones=()),
    )
    row = row_codec_of(vm.CUSTOMER_MODEL).full_row(customer)
    assert row["address"] == {"street": "Main St", "city": "Berlin", "geo": None, "phones": []}


def test_full_row_serializes_a_many_value_object_to_a_list_of_documents() -> None:
    status = sm.SnapOrderStatus(
        id=1,
        order_id=1,
        order_item_id=None,
        code="shipped",
        primary_tag=None,
        tags=(sm.Tag(label="a", detail=None, details=()),),
    )
    assert row_codec_of(sm.SNAP_ORDERS_MODEL).full_row(status)["tags"] == [
        {"label": "a", "detail": None, "details": []}
    ]


def test_full_row_serializes_a_value_object_to_its_full_containment_depth() -> None:
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
    profile = row_codec_of(mm.DOCUMENT_CODEC_MODEL).full_row(sample)["profile"]
    assert isinstance(profile, dict)
    # A document's leaves are canonically ENCODED at every depth, where an
    # Entity Attribute of the same declared type stays Python-typed above them:
    # a document is one value, and the codec emits it whole.
    assert profile["day"] == "2026-01-01"
    assert profile["origin"] == {"city": "Oslo", "since": "2020-01-01"}
    assert profile["entries"] == [{"kind": "k", "active": True, "price": "2.00", "issued": None}]


def test_a_row_emits_the_canonical_member_name_and_never_its_column() -> None:
    # `taxID` is authored by `name=` and stored in `tax_id`, whose mechanical
    # default would be `tax_i_d`: physical names are m-storage-layout's, so
    # neither spelling may appear in a row.
    row = row_codec_of(mm.TAXPAYER_MODEL).full_row(mm.Taxpayer(id=1, tax_id="T-1", name="Ada"))
    assert row == {"id": 1, "taxID": "T-1", "name": "Ada"}
    assert "tax_id" not in row
    assert "tax_i_d" not in row


def test_a_row_is_ordered_by_the_models_family_effective_declaration_order() -> None:
    # Base-first, so an inherited member precedes the concrete's own — and the
    # order is the model's, never the order the caller populated members in.
    card = rm.CardPayment(card_network="Visa", amount=Decimal("10.00"), id=1)
    row = row_codec_of(mm.PAYMENT_MODEL).full_row(card)
    assert list(row) == ["id", "amount", "cardNetwork"]


def test_a_row_orders_attributes_before_top_level_value_objects() -> None:
    # The order is a stable CATEGORY pass — Attributes in declaration order, then
    # top-level Value Objects in theirs — so `tail` precedes the earlier-declared
    # `detail`. Ordering by the declaration's own interleaving would make a row's
    # keys depend on the value's class, which a row never does.
    row = row_codec_of(INTERLEAVED_MODEL).full_row(
        Interleaved(id=1, detail=Detail(note="n"), tail="t")
    )
    assert list(row) == ["id", "tail", "detail"]


def test_a_row_is_a_fresh_plain_caller_owned_dict() -> None:
    codec = _accounts()
    account = _account()
    row = codec.full_row(account)
    assert type(row) is dict
    row["balance"] = Decimal("0.00")
    assert codec.full_row(account)["balance"] == Decimal("100.00")


# --------------------------------------------------------------------------- #
# Framework-owned members are omitted, never refused and never emitted.       #
# --------------------------------------------------------------------------- #
def test_full_row_omits_a_hydrated_version_rather_than_refusing_it() -> None:
    # Refusing would make a stored row unreadable; emitting would launder stored
    # state into a caller assignment.
    hydrated = _fetched_account(version=7)
    assert "version" in hydrated.model_fields_set
    assert _accounts().full_row(hydrated) == {
        "id": 1,
        "owner": "Ada",
        "balance": Decimal("100.00"),
    }


def test_full_row_omits_hydrated_temporal_axis_endpoints() -> None:
    hydrated = mm.Balance.model_construct(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        tx_start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        tx_end=dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    )
    assert row_codec_of(mm.BALANCE_MODEL).full_row(hydrated) == {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("100.00"),
    }


def test_a_constructed_instance_needs_no_framework_owned_value_to_derive_a_row() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    assert row_codec_of(mm.BRANCH_MODEL).full_row(branch) == {
        "id": 1,
        "name": "Central",
        "address": None,
    }


# --------------------------------------------------------------------------- #
# identity_row: the declared primary key, serialized like every other row.    #
# --------------------------------------------------------------------------- #
def test_identity_row_projects_only_the_declared_primary_key() -> None:
    assert _accounts().identity_row(_fetched_account(version=7)) == {"id": 1}


def test_identity_row_carries_the_values_the_instance_holds_unchanged() -> None:
    account = _account()
    assert _accounts().identity_row(account)["id"] is account.id


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Keyed(id=7, label="a"), 7), (Labelled(code="K-1", label="a"), "K-1")],
    ids=["int64", "string"],
)
def test_serialization_is_the_identity_on_every_type_a_primary_key_can_hold(
    value: object, expected: object
) -> None:
    # All three operations serialize, and a primary key is structurally
    # restricted to a scalar Attribute type `serialize_member` passes through by
    # identity — which is why uniform serialization moves no emitted bind: the
    # metamodel schema gives `primaryKey` to an Attribute alone, and never to a
    # Value Object occurrence.
    codec = row_codec_of(KEYED_MODEL if isinstance(value, Keyed) else LABELLED_MODEL)
    (emitted,) = codec.identity_row(value).values()
    assert emitted is expected or emitted == expected


# --------------------------------------------------------------------------- #
# edited_row: identity plus the effective caller-authored changes.            #
# --------------------------------------------------------------------------- #
def test_edited_row_merges_the_identity_with_the_effective_changes() -> None:
    edited = _account().edit(balance=Decimal("175.00"))
    assert _accounts().edited_row(edited) == {"id": 1, "balance": Decimal("175.00")}


def test_edited_row_omits_a_touched_member_whose_value_is_unchanged() -> None:
    edited = _account("100.00").edit(balance=Decimal("100.00"), owner="Grace")
    assert _accounts().edited_row(edited) == {"id": 1, "owner": "Grace"}


def test_edited_row_answers_none_for_a_net_zero_edit() -> None:
    assert _accounts().edited_row(_account("100.00").edit(balance=Decimal("100.00"))) is None


def test_edited_row_answers_none_for_a_net_zero_chain() -> None:
    round_tripped = _account("100.00").edit(balance=Decimal("200.00"))
    assert _accounts().edited_row(round_tripped.edit(balance=Decimal("100.00"))) is None


def test_edited_row_preserves_the_first_touched_original_across_a_chain() -> None:
    # 100 -> 150 -> 100 nets to zero against the EARLIEST original, not against
    # the immediate parent's 150.
    chained = _account("100.00").edit(balance=Decimal("150.00")).edit(balance=Decimal("100.00"))
    assert chained.balance == Decimal("100.00")
    assert _accounts().edited_row(chained) is None


def test_edited_row_answers_none_for_an_edit_that_authored_nothing() -> None:
    assert _accounts().edited_row(_account().edit()) is None


def test_edited_row_serializes_a_changed_value_object_beside_a_raw_identity() -> None:
    # The two halves keep their own value conventions: the identity is what the
    # instance holds, the change is its canonical document.
    original = mm.Traveler(
        id=1,
        address=mm.TravelerAddress(city="Oslo", geo=mm.TravelerGeo(country="Norway")),
        tags=(),
    )
    edited = original.edit(address=mm.TravelerAddress(city="Bergen"))
    row = row_codec_of(mm.DOCUMENT_LAYOUT_MODEL).edited_row(edited)
    assert row is not None
    assert row["id"] == 1
    # The authored occurrence names `city` alone, and a document omits what the
    # caller never populated rather than spelling it as an explicit null.
    assert row["address"] == {"city": "Bergen"}


def test_edited_row_compares_a_one_occurrence_as_a_whole() -> None:
    # The authored occurrence names `city` alone, so the omitted `geo` is a
    # member the write REMOVES — an assignment replaces its subtree whole under
    # every Storage Layout — and the edit is effective even though every key it
    # does name is unchanged. Comparing only those keys would eliminate a write
    # that changes what storage holds.
    original = mm.Traveler(
        id=1,
        address=mm.TravelerAddress(city="Oslo", geo=mm.TravelerGeo(country="Norway")),
        tags=(),
    )
    edited = original.edit(address=mm.TravelerAddress(city="Oslo"))
    assert row_codec_of(mm.DOCUMENT_LAYOUT_MODEL).edited_row(edited) == {
        "id": 1,
        "address": {"city": "Oslo"},
    }


def test_edited_row_answers_none_for_an_occurrence_restated_unchanged() -> None:
    # The other side of the same rule: an occurrence restated with the members
    # its original holds, at the values it holds them, stores exactly what is
    # there and nets to zero.
    original = mm.Traveler(
        id=1,
        address=mm.TravelerAddress(city="Oslo", geo=mm.TravelerGeo(country="Norway")),
        tags=(),
    )
    edited = original.edit(
        address=mm.TravelerAddress(city="Oslo", geo=mm.TravelerGeo(country="Norway"))
    )
    codec = row_codec_of(mm.DOCUMENT_LAYOUT_MODEL)
    assert codec.edited_row(edited) is None
    assert codec.restored_members(edited) == frozenset({"address"})


def test_edited_row_compares_a_many_occurrence_as_a_whole() -> None:
    # Elements have no identity, so any element difference is a change rather
    # than a per-key mask.
    original = mm.Traveler(id=1, address=None, tags=(mm.TravelerTag(label="a"),))
    edited = original.edit(tags=(mm.TravelerTag(label="b"),))
    row = row_codec_of(mm.DOCUMENT_LAYOUT_MODEL).edited_row(edited)
    assert row is not None
    assert row["tags"] == [{"label": "b"}]


def test_edited_row_writes_an_authored_null_a_materialized_read_never_set() -> None:
    # Storage holds a `Customer.address` document that never wrote `geo` at all,
    # so the materialized read's own `address` names `geo` ABSENT rather than
    # null (`model_fields_set` omits it) — presence at materialization is what
    # `test_snapshot_merge.py`'s
    # `test_a_materialized_value_object_names_exactly_what_storage_held` pins.
    # Authoring `geo=None` on the edit is then a REAL difference from what was
    # read, not a repeat of a fabricated original, and `edited_row` must carry
    # it through as an explicit null rather than let it cancel out.
    fixture = GraphFixture(vm.CUSTOMER_MODEL)
    node = fixture.node(
        "Customer",
        {
            "id": 1,
            "name": "Ada",
            "address": {"street": "Main St", "city": "Oslo", "phones": [{"number": "555-0100"}]},
        },
    )
    (root,) = fixture.materialize(node)
    customer = cast("vm.Customer", root)
    address = customer.address
    assert address is not None
    assert address.model_fields_set == {"street", "city", "phones"}

    edited = customer.edit(
        address=vm.Address(
            street=address.street, city=address.city, geo=None, phones=address.phones
        )
    )
    row = row_codec_of(vm.CUSTOMER_MODEL).edited_row(edited)
    assert row is not None
    assert row["address"] == {
        "street": "Main St",
        "city": "Oslo",
        "geo": None,
        "phones": [{"number": "555-0100"}],
    }


def test_whole_comparison_covers_the_nested_and_many_boundaries() -> None:
    assert _assignment_matches_original({"city": "Oslo"}, {"city": "Oslo"})
    assert not _assignment_matches_original({}, {"future": 1})
    assert not _assignment_matches_original({"city": "Oslo"}, {"city": "Oslo", "geo": None})
    assert not _assignment_matches_original({"city": "Oslo"}, None)
    assert not _assignment_matches_original({"city": "Oslo"}, {"city": "Bergen"})
    assert not _assignment_matches_original([{"city": "Oslo"}], [{"city": "Oslo", "future": 1}])
    assert not _assignment_matches_original([{"city": "Oslo"}], [])
    assert not _assignment_matches_original([{"city": "Oslo"}], {"city": "Oslo"})
    assert not _assignment_matches_original("Oslo", "Bergen")


# --------------------------------------------------------------------------- #
# The five refusals.                                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [object(), "Account", mm.TravelerGeo(country="Norway")])
def test_a_value_that_is_no_entity_derives_no_row(value: object) -> None:
    with pytest.raises(EntityRowError) as refusal:
        _accounts().full_row(value)
    assert refusal.value.code == "entity-row-not-an-entity"


def test_an_identity_this_model_does_not_declare_is_refused_by_every_operation() -> None:
    account = _account()
    for operation in (
        row_codec_of(NARROW_MODEL).full_row,
        row_codec_of(NARROW_MODEL).identity_row,
        row_codec_of(NARROW_MODEL).edited_row,
    ):
        with pytest.raises(EntityRowError) as refusal:
            operation(account)
        assert refusal.value.code == "entity-row-target-not-in-model"
        assert refusal.value.identity == mm.Account.identity


def test_a_value_from_another_model_declaring_the_same_identity_derives_a_row() -> None:
    # Input validation resolves; it does not own. The emitted row is a function
    # of the RESOLVED identity's declared members, so a foreign class populating
    # only declared members is ordinary input.
    foreign = WiderWidget(id=1, label="a")
    assert row_codec_of(NARROW_MODEL).full_row(foreign) == {"id": 1, "label": "a"}


def test_full_row_refuses_a_populated_member_the_resolved_identity_does_not_declare() -> None:
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).full_row(WiderWidget(id=1, label="a", extra="x"))
    assert refusal.value.code == "entity-row-member-missing"
    assert "'extra'" in refusal.value.message


def test_the_same_value_emits_an_identity_row_and_an_untouched_edited_row() -> None:
    # Refusal follows SELECTION: `identity_row` drops every non-key member and
    # `edited_row` every member its Change Record does not name, so neither
    # loses anything by dropping one more.
    wider = WiderWidget(id=1, label="a", extra="x")
    codec = row_codec_of(NARROW_MODEL)
    assert codec.identity_row(wider) == {"id": 1}
    assert codec.edited_row(wider.edit(label="b")) == {"id": 1, "label": "b"}


def test_edited_row_refuses_a_recorded_name_the_resolved_identity_does_not_declare() -> None:
    edited = WiderWidget(id=1, label="a", extra="x").edit(extra="y")
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).edited_row(edited)
    assert refusal.value.code == "entity-row-member-missing"


def test_a_restored_undeclared_member_is_still_refused_by_edited_row() -> None:
    # Effectiveness is weighed AFTER the selection is judged and never narrows
    # it: the row would have carried nothing for `extra`, and it still raises.
    restored = WiderWidget(id=1, label="a", extra="x").edit(extra="y").edit(extra="x")
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).edited_row(restored)
    assert refusal.value.code == "entity-row-member-missing"


def test_a_cross_model_value_keyed_by_another_member_derives_no_identity_row() -> None:
    # The resolved identity declares `id`; this value's class keys the same
    # Entity by `key` and carries no attribute to read `id` from. Dropping it
    # would hand a keyed write an unkeyed `{}` outside the closed vocabulary.
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).identity_row(RekeyedWidget(key=1, label="a"))
    assert refusal.value.code == "entity-row-member-missing"
    assert "'id'" in refusal.value.message
    assert refusal.value.identity == Widget.identity


def test_a_cross_model_value_keyed_by_another_member_derives_no_edited_row() -> None:
    # `edited_row` selects the primary key too, so the identity half is judged by
    # the same rule rather than emitted short.
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).edited_row(RekeyedWidget(key=1, label="a").edit(label="b"))
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
    # Effectiveness never narrows the selection, and the primary key is half of
    # it: an empty effective set cannot excuse a key member the value's class
    # supplies no attribute for, or "nothing to write" would answer for a value
    # no write could have keyed.
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).edited_row(net_zero)
    assert refusal.value.code == "entity-row-member-missing"
    assert "'id'" in refusal.value.message


def test_a_recorded_name_the_value_supplies_no_attribute_for_is_refused() -> None:
    # The other side of the pairing, reached through the RECORDED half of
    # `edited_row`'s selection rather than the key half: `extra` is declared by
    # the resolved identity and named by the record, and this narrower class
    # carries no attribute to compare it against its original. Suppliedness is
    # judged before effectiveness because weighing effectiveness would itself
    # read that attribute, escaping the closed code set with an `AttributeError`.
    narrow = Widget(id=1, label="a")
    object.__setattr__(narrow, CHANGE_RECORD_SLOT, {"extra": "x"})
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(WIDER_MODEL).edited_row(narrow)
    assert refusal.value.code == "entity-row-member-missing"
    assert "'extra'" in refusal.value.message
    assert refusal.value.identity == Widget.identity


def test_a_never_edited_value_derives_no_edited_row() -> None:
    # `None` is one proposition — this value names no change to write — so a
    # value no edit ever touched answers it exactly as a net-zero chain does.
    assert _accounts().edited_row(_account()) is None


@pytest.mark.parametrize(
    "carrier", [["balance"], "balance", {1: "not-a-member-name"}], ids=["list", "str", "int-keyed"]
)
def test_an_unreadable_change_record_reports_corruption_rather_than_absence(
    carrier: object,
) -> None:
    # Told apart by the SLOT rather than by its contents: collapsing an
    # unreadable carrier into "never edited" would name the wrong defect.
    account = _account()
    object.__setattr__(account, CHANGE_RECORD_SLOT, carrier)
    with pytest.raises(EntityRowError) as refusal:
        _accounts().edited_row(account)
    assert refusal.value.code == "entity-row-malformed-provenance"


# --------------------------------------------------------------------------- #
# Refusal order: one input, one code.                                         #
# --------------------------------------------------------------------------- #
def test_an_unresolved_identity_outranks_every_later_refusal() -> None:
    # A plain value of an Entity this model does not declare reports the
    # identity rather than answering the no-change `None`.
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).edited_row(_account())
    assert refusal.value.code == "entity-row-target-not-in-model"


def test_a_never_edited_value_still_judges_the_primary_key_selection() -> None:
    # A never-edited value and a net-zero chain answer `None` through the SAME
    # path, so both judge the identity selection first: a value whose class
    # carries no attribute for a key member the resolved identity declares is
    # refused rather than answered.
    with pytest.raises(EntityRowError) as refusal:
        row_codec_of(NARROW_MODEL).edited_row(RekeyedWidget(key=1, label="a"))
    assert refusal.value.code == "entity-row-member-missing"
    assert "'id'" in refusal.value.message


# --------------------------------------------------------------------------- #
# The closed code set, and the module's own dependencies.                     #
# --------------------------------------------------------------------------- #
def test_the_code_set_is_closed_against_an_unlisted_code() -> None:
    assert ENTITY_ROW_CODES == _SPEC_CODES
    with pytest.raises(ValueError, match="not an entity row code"):
        EntityRowError(code="entity-row-nosuch", message="invented")


def _codec_imports() -> set[str]:
    """Every module ``_row_codec`` imports, as its own source states them."""
    from parallax.core.entity import _row_codec

    source = ast.parse(Path(str(_row_codec.__file__)).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(source):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return imported


def test_the_codec_depends_on_accepted_metadata_and_its_own_frontend_alone() -> None:
    # The audit-neutrality proof, stated as the module's own import list: no
    # Principal, Subject Identity, Session, Clock Strategy, Transaction Instant,
    # Audit Metadata, temporal planning, Write Planner, SQL, or Storage Layout is
    # reachable from here. §7's generated contracts enforce the scope-level half.
    assert _codec_imports() == {
        "__future__",
        "collections.abc",
        "dataclasses",
        "types",
        "typing",
        "parallax.core.entity._declaration",
        "parallax.core.entity._entity",
        "parallax.core.entity._errors",
        "parallax.core.entity._expressions",
        "parallax.core.entity._model",
        "parallax.core.inheritance",
        "parallax.core.metamodel",
    }


@pytest.mark.parametrize(
    "forbidden",
    [
        "principal",
        "session",
        "clock",
        "audit",
        "write_planner",
        "unit_work",
        "sql_gen",
        "storage_layout",
        "db_port",
        "dialect",
        "opt_lock",
        "batch_write",
        "temporal",
    ],
)
def test_the_codec_names_no_audit_planning_or_physical_dependency(forbidden: str) -> None:
    assert not [module for module in _codec_imports() if forbidden in module]


def test_a_codec_states_itself_over_the_accepted_metamodel_alone() -> None:
    # What `row_codec_of` retains is derivable from the accepted model with no
    # Domain Model in reach, which is what makes the bare-Metamodel connection
    # the conformance adapter builds a fully functional write path.
    standalone: Any = EntityRowCodec(model_of(mm.ACCOUNT_MODEL))
    assert standalone.full_row(_account()) == _accounts().full_row(_account())
