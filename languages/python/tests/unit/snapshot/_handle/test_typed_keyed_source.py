"""The Typed Keyed Write Source and Keyed Insert Source, asked what they author.

The keyed write ingress owns the order; a source answers facts into it. This
suite asks each Typed adapter what is its own — which Entity its value's class
names, and the row its value and Change Record author — and nothing about the
provenance, Pin, evidence, and authority it resolves, which
`test_sources.py` states once for both representations, or about what the order
then does with the answer, which `test_keyed_write_order.py` fixes through the
public verbs.

Every case constructs the adapter directly, which is also how the two claims a
verb cannot show are shown: that construction is inert, so nothing an adapter
could refuse can run before the ingress refuses re-entry, and that ``capture``
judges nothing at all, because a Typed value's shape is fixed by its class.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Final, cast

import pytest

from parallax.conformance.vo_models import (
    CONTACT_MODEL,
    Contact,
    ContactAddress,
    ContactGeo,
    ContactPoint,
)
from parallax.core import Attr, DomainModel, attr
from parallax.core.base import INFINITY, DocumentValue, PresentDocument
from parallax.core.db_port import MappingRow
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import EntityRowCodec
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery import InvalidData
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import WriteInstructionError
from parallax.snapshot._handle._typed_writes import (
    TypedKeyedInsertSource,
    TypedKeyedWriteSource,
)
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter
from tests._support.model_capabilities import cataloged_for, row_codec_for
from tests.unit._transact_support import (
    ACCOUNT,
    db_for,
    new_account,
)
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
    WherePosition,
)

_TX_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_ACCOUNT_ROW: Final[MappingRow] = {
    "id": 1,
    "owner": "Ada",
    "balance": Decimal("100.00"),
    "version": 4,
}


# One Entity Identity declared twice, keyed by a different member each time: an
# instance of the second states no value for the member the first keys by, which
# is the whole of what "names no object" is.
class _Twin(EntityBase, table="twin", name="Twin", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    only: Attr[str] = attr(max_length=8)


class _RekeyedTwin(EntityBase, table="twin", name="Twin", namespace="parallax.compatibility"):
    id_elsewhere: Attr[int] = attr(primary_key=True)
    only: Attr[str] = attr(max_length=8)


_TWIN: Final = DomainModel(_Twin)


def _accounts() -> tuple[Metamodel, EntityRowCodec]:
    return cataloged_for(ACCOUNT).meta, row_codec_for(ACCOUNT)


def _twins() -> tuple[Metamodel, EntityRowCodec]:
    return cataloged_for(_TWIN).meta, row_codec_for(_TWIN)


def _published_account() -> mm.Account:
    """One `Account` as a standalone read of this store hands it back."""
    port = ScriptedAdapter(Read(rows=[dict(_ACCOUNT_ROW)]))
    return db_for(ACCOUNT, port).find(mm.Account.where(mm.Account.id == 1)).result()


_STORED_ADDRESS: Final[dict[str, DocumentValue]] = {
    "street": "Main",
    "geo": {"country": "DE", "point": {"lat": 1.0, "lon": 2.0}},
    "phones": [],
}
_COMPLETE_ADDRESS: Final = ContactAddress(
    street="Main",
    city="Berlin",
    geo=ContactGeo(country="DE", point=ContactPoint(lat=1.0, lon=2.0)),
    phones=(),
)


def _published_contact() -> Contact:
    """One `Contact` whose stored address states no `city`, as the read that
    classifies it still hands the hydrated root back."""
    port = ScriptedAdapter(
        Read(rows=[{"id": 1, "name": "Ada", "address": PresentDocument(dict(_STORED_ADDRESS))}])
    )
    published = db_for(CONTACT_MODEL, port).find(Contact.where(Contact.id == 1)).checked().result()
    assert isinstance(published, InvalidData)
    return cast("Contact", published.data)


# --------------------------------------------------------------------------- #
# Which Entity a value names.                                                 #
# --------------------------------------------------------------------------- #
def test_a_value_names_the_entity_its_class_declares_in_the_connected_model() -> None:
    meta, codec = _accounts()

    resolved = TypedKeyedWriteSource(_published_account(), codec).resolve(meta, "amend")

    assert resolved.entity.identity == mm.Account.identity


def test_a_class_the_connected_model_does_not_declare_is_refused_while_resolving() -> None:
    meta, _ = _accounts()

    with pytest.raises(TypeError, match="is not an Entity Class of this model"):
        TypedKeyedWriteSource(_Twin(id=1, only="x"), row_codec_for(_TWIN)).resolve(meta, "amend")


# --------------------------------------------------------------------------- #
# What a value authors, once the window has been judged.                      #
# --------------------------------------------------------------------------- #
def test_prepare_states_every_touched_member_as_its_literal_assignment() -> None:
    meta, codec = _accounts()
    edited = _published_account().edit(balance=Decimal("125.00"))
    source = TypedKeyedWriteSource(edited, codec)
    resolved = source.resolve(meta, "amend")

    prepared = source.prepare(meta, "amend", resolved, valid_from=None, until=None)

    assert prepared.instruction.rows[0] == {"id": 1, "balance": Decimal("125.00")}
    assert prepared.assigned == {"balance"}


def test_a_wholly_restoring_chain_still_assigns_the_member_it_took_back() -> None:
    # The chain touched the member, so the adapter states it at the value the
    # chain ended on, whatever that equals: the assignment is literal.
    meta, codec = _accounts()
    restored = _published_account().edit(balance=Decimal("125.00")).edit(balance=Decimal("100.00"))
    source = TypedKeyedWriteSource(restored, codec)

    prepared = source.prepare(
        meta, "amend", source.resolve(meta, "amend"), valid_from=None, until=None
    )

    assert prepared.instruction.rows[0] == {"id": 1, "balance": Decimal("100.00")}
    assert prepared.assigned == {"balance"}


def test_a_correction_states_what_current_authoring_admits_over_any_stored_original() -> None:
    # `Contact` requires every member inside its address, and the stored document
    # states no `city`: readable state a read publishes as a hydratable
    # classified record, which authoring refuses — assigning that same document
    # is `Contact.address.city: required attribute is absent (or null)`. The
    # write repairing it is a correction, judged on the authored side alone, so
    # the state it revises never refuses it.
    meta = cataloged_for(CONTACT_MODEL).meta
    source = TypedKeyedWriteSource(
        _published_contact().edit(address=_COMPLETE_ADDRESS), row_codec_for(CONTACT_MODEL)
    )

    prepared = source.prepare(
        meta, "amend", source.resolve(meta, "amend"), valid_from=None, until=None
    )

    assert prepared.instruction.rows[0]["address"] == {
        "street": "Main",
        "city": "Berlin",
        "geo": {"country": "DE", "point": {"lat": 1.0, "lon": 2.0}},
        "phones": (),
    }
    assert prepared.assigned == {"address"}


def test_an_untouched_copy_authors_its_identity_row_alone() -> None:
    meta, codec = _accounts()
    source = TypedKeyedWriteSource(_published_account(), codec)

    prepared = source.prepare(
        meta, "amend", source.resolve(meta, "amend"), valid_from=None, until=None
    )

    assert prepared.instruction.rows[0] == {"id": 1}
    assert prepared.assigned == frozenset()


def test_a_destructive_verb_authors_its_identity_row_and_assigns_nothing() -> None:
    meta, codec = _accounts()
    source = TypedKeyedWriteSource(_published_account(), codec)

    prepared = source.prepare(
        meta, "delete", source.resolve(meta, "delete"), valid_from=None, until=None
    )

    assert prepared.instruction.rows[0] == {"id": 1}
    assert prepared.assigned == frozenset()


# --------------------------------------------------------------------------- #
# The insert door's narrower peer.                                            #
# --------------------------------------------------------------------------- #
def test_an_insert_source_answers_the_entity_the_value_is_of() -> None:
    meta, codec = _accounts()

    resolved = TypedKeyedInsertSource(new_account(), codec).resolve(meta, "insert")

    assert resolved.entity.identity == mm.Account.identity


def test_an_insert_source_authors_the_whole_create_payload() -> None:
    meta, codec = _accounts()
    source = TypedKeyedInsertSource(new_account(), codec)

    prepared = source.prepare(
        meta, "insert", source.resolve(meta, "insert"), valid_from=None, until=None
    )

    assert prepared.rows[0] == {"id": 7, "owner": "Newton", "balance": Decimal("5.00")}


def test_an_insert_source_hands_its_raw_window_to_preparation() -> None:
    # The source states the caller's bounds as they were passed; preparation
    # judges them against the target and normalizes what it admits.
    meta, codec = cataloged_for(WHERE_POSITION_META).meta, row_codec_for(WHERE_POSITION_META)
    position = WherePosition(id=9, acct_num="A", value=Decimal("1.00"))
    source = TypedKeyedInsertSource(position, codec)
    resolved = source.resolve(meta, "insert")
    stated = dt.datetime(2024, 1, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))

    prepared = source.prepare(meta, "insert", resolved, valid_from=stated, until=None)

    assert prepared.valid_time_window == TimeInterval(_TX_START, INFINITY)
    with pytest.raises(WriteInstructionError, match="a bitemporal 'insert' requires valid_from"):
        source.prepare(meta, "insert", resolved, valid_from=None, until=None)


# --------------------------------------------------------------------------- #
# What construction and capture do, which is nothing.                         #
# --------------------------------------------------------------------------- #
def test_construction_and_capture_refuse_nothing_a_verb_would() -> None:
    # A value every one of the three refusals is waiting for: it names no object,
    # no read produced it, and its class keys the Entity elsewhere. Constructing
    # a source over it and capturing must still be silent, because the ingress
    # refuses re-entry before either runs.
    _, codec = _twins()
    rekeyed = _RekeyedTwin(id_elsewhere=1, only="x")
    assert TypedKeyedWriteSource(rekeyed, codec).capture("amend") is None
    assert TypedKeyedInsertSource(rekeyed, codec).capture("insert") is None
