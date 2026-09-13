"""The three Wire keyed sources, asked what they answer.

The keyed write ingress owns the order; a source answers facts into it. This
suite asks each Wire adapter the one question that is its own — given this
published node, this change document, or this already-prepared product, what did
you answer — and nothing about what the order then does with the answer, which
`test_keyed_write_order.py` fixes through the public verbs.

Every case constructs the adapter directly, which is how the claims a verb cannot
show are shown: that construction is inert, so nothing an adapter could refuse
runs before the ingress refuses re-entry, and that ``capture`` judges the
document's own shape before ``resolve`` is asked for a source at all.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Final, cast

import pytest

from parallax.core import DomainModel
from parallax.core.base import SQL_NULL
from parallax.core.db_port import MappingRow
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import ObjectKey, instructions
from parallax.core.unit_work.instructions import PreparedKeyedWrite, PreparedTemporalBounds
from parallax.snapshot.handle._wire_writes import (
    PreparedWireKeyedWriteSource,
    WireKeyedInsertSource,
    WireKeyedWriteSource,
)
from parallax.snapshot.materialize import WireEntity
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter
from tests._support.model_capabilities import cataloged_for
from tests.unit._transact_support import (
    ACCOUNT,
    CONTACT,
    INFINITY_INSTANT,
    WHERE_POSITION_META,
    db_for,
)

_TX_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_TX_PIN: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_TX_PIN_WIRE: Final = "2024-03-01T00:00:00.000000Z"
_UNBOUNDED: Final = PreparedTemporalBounds(None, None)

_ACCOUNT = "parallax.compatibility.Account"
_CONTACT = "parallax.compatibility.Contact"
_POSITION = "parallax.compatibility.WherePosition"

_ACCOUNT_ROW: Final[MappingRow] = {
    "id": 1,
    "owner": "Ada",
    "balance": Decimal("100.00"),
    "version": 4,
}
_BLANK_CONTACT_ROW: Final[MappingRow] = {"id": 2, "name": "Ada", "address": SQL_NULL}
_POSITION_ROW: Final[MappingRow] = {
    "id": 1,
    "acct_num": "A",
    "value": Decimal("100.00"),
    "from_z": _TX_START,
    "thru_z": INFINITY_INSTANT,
    "in_z": _TX_START,
    "out_z": INFINITY_INSTANT,
}


def _query(entity: str, key: int, temporal: dict[str, object] | None = None) -> dict[str, object]:
    query: dict[str, object] = {
        "target": entity,
        "predicate": {"eq": {"attr": f"{entity}.id", "value": key}},
    }
    if temporal is not None:
        query["temporal"] = temporal
    return query


def _published(model: DomainModel, row: MappingRow, query: dict[str, object]) -> WireEntity:
    """One frozen Entity mapping as a standalone Wire read of this store
    publishes it, Source Hint and all."""
    port = ScriptedAdapter(Read(rows=[dict(row)]))
    return db_for(model, port).wire.find(query).result()


def _account_node() -> WireEntity:
    return _published(ACCOUNT, _ACCOUNT_ROW, _query(_ACCOUNT, 1))


def _meta(model: DomainModel) -> Metamodel:
    return cataloged_for(model).meta


# --------------------------------------------------------------------------- #
# Capture: the change document's own shape, before a source is required.      #
# --------------------------------------------------------------------------- #
def test_capture_judges_the_document_before_resolve_is_asked_for_a_source() -> None:
    # Both arguments are wrong, and the one answered is the one no other input
    # is needed to judge: whether a document was stated at all needs neither the
    # source's provenance nor the Entity that source names.
    source = WireKeyedWriteSource(cast("object", {}), cast("dict[str, object]", []))

    with pytest.raises(instructions.WriteInstructionError, match="document of names"):
        source.capture("update")


def test_construction_refuses_nothing_either_phase_would() -> None:
    # A hintless source and a document that is no document, held together: the
    # ingress refuses re-entry before either phase runs, so constructing over
    # both has to be silent.
    WireKeyedWriteSource(cast("object", {}), cast("dict[str, object]", []))
    WireKeyedInsertSource("parallax.compatibility.Nope", cast("dict[str, object]", []))


def test_an_insert_payload_that_is_no_document_is_judged_at_capture() -> None:
    source = WireKeyedInsertSource(_ACCOUNT, cast("dict[str, object]", []))

    with pytest.raises(instructions.WriteInstructionError, match="payload must be a document"):
        source.capture("insert")


# --------------------------------------------------------------------------- #
# Resolve: what a published node states about the state a write revises.      #
# --------------------------------------------------------------------------- #
def test_a_published_node_answers_the_facts_its_own_read_filed() -> None:
    source = WireKeyedWriteSource(_account_node(), {"balance": "125.00"})
    source.capture("update")

    resolved = source.resolve(_meta(ACCOUNT), "update")

    assert resolved.entity.identity == mm.Account.identity
    assert resolved.provenance == "this"
    assert resolved.representation == "wire"
    assert resolved.identity_row == {"id": 1}
    assert resolved.hint is not None
    assert resolved.hint.object_key == ObjectKey(mm.Account.identity, (("id", 1),))
    assert resolved.pin is None


def test_a_node_a_pinned_read_published_answers_the_instant_it_stands_at() -> None:
    node = _published(
        WHERE_POSITION_META,
        _POSITION_ROW,
        _query(
            _POSITION,
            1,
            {"transaction-time": {"asOf": _TX_PIN_WIRE}, "valid-time": {"asOf": "latest"}},
        ),
    )
    source = WireKeyedWriteSource(node, {"value": "300.00"})
    source.capture("update")

    resolved = source.resolve(_meta(WHERE_POSITION_META), "update")

    assert resolved.pin is not None
    assert resolved.pin.tx_time == _TX_PIN


def test_an_argument_carrying_no_hint_is_refused_as_no_source_at_all() -> None:
    # Provenance is never asked of a Wire keyed source, because a source that
    # could answer anything but "this" is refused here first.
    source = WireKeyedWriteSource(cast("object", dict(_account_node())), {})
    source.capture("update")

    with pytest.raises(instructions.WriteInstructionError, match="carries no such provenance"):
        source.resolve(_meta(ACCOUNT), "update")


# --------------------------------------------------------------------------- #
# Prepare: the authored row and the source's own originals, through one       #
# producer.                                                                   #
# --------------------------------------------------------------------------- #
def test_prepare_states_every_authored_member_beside_what_the_source_published() -> None:
    source = WireKeyedWriteSource(_account_node(), {"balance": "125.00"})
    source.capture("update")
    resolved = source.resolve(_meta(ACCOUNT), "update")

    prepared = source.prepare(resolved, _UNBOUNDED)

    assert prepared.instruction.rows[0] == {"id": 1, "balance": Decimal("125.00")}
    assert prepared.originals == {"balance": Decimal("100.00")}
    assert prepared.object_key == ObjectKey(mm.Account.identity, (("id", 1),))


def test_a_member_the_source_published_nothing_for_is_measured_against_a_null() -> None:
    # The published row states no address at all. The originals row must still
    # NAME the member, because the comparison is over the two prepared rows and a
    # name missing from one of them is no comparison; the null is what the source
    # would state back.
    node = _published(CONTACT, _BLANK_CONTACT_ROW, _query(_CONTACT, 2))
    authored: dict[str, object] = {
        "street": "1 Park",
        "city": "Oslo",
        "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
        "phones": [],
    }
    source = WireKeyedWriteSource(node, {"address": authored})
    source.capture("update")
    resolved = source.resolve(_meta(CONTACT), "update")

    prepared = source.prepare(resolved, _UNBOUNDED)

    assert set(prepared.originals) == {"address"}
    assert prepared.originals["address"] is None


def test_a_destructive_verb_authors_its_identity_row_and_no_originals() -> None:
    source = WireKeyedWriteSource(_account_node(), None)
    source.capture("delete")
    resolved = source.resolve(_meta(ACCOUNT), "delete")

    prepared = source.prepare(resolved, _UNBOUNDED)

    assert prepared.instruction.rows[0] == {"id": 1}
    assert prepared.originals == {}


# --------------------------------------------------------------------------- #
# The conformance bridge's source: preparation as an input capability.        #
# --------------------------------------------------------------------------- #
def test_a_prepared_product_is_answered_back_with_the_originals_beside_it() -> None:
    node = _account_node()
    authoring = WireKeyedWriteSource(node, {"balance": "125.00"})
    authoring.capture("update")
    product = authoring.prepare(authoring.resolve(_meta(ACCOUNT), "update"), _UNBOUNDED).instruction

    bridged = PreparedWireKeyedWriteSource(node, product, frozenset({"balance"}))
    assert bridged.capture("update") is None
    prepared = bridged.prepare(bridged.resolve(_meta(ACCOUNT), "update"), _UNBOUNDED)

    assert prepared.instruction is product
    assert prepared.originals == {"balance": Decimal("100.00")}
    assert prepared.object_key == ObjectKey(mm.Account.identity, (("id", 1),))


# --------------------------------------------------------------------------- #
# The insert door's narrower peer.                                            #
# --------------------------------------------------------------------------- #
def test_a_fresh_payload_answers_that_no_read_produced_it() -> None:
    source = WireKeyedInsertSource(_ACCOUNT, {"id": 7, "owner": "Newton", "balance": "5.00"})
    source.capture("insert")

    resolved = source.resolve(_meta(ACCOUNT), "insert")

    assert resolved.entity.identity == mm.Account.identity
    assert resolved.provenance == "none"
    assert resolved.representation == "wire"
    assert resolved.pin is None


def test_a_payload_that_is_itself_a_published_node_answers_its_view_and_its_source() -> None:
    # The one payload that carries a view is the one this door refuses for its
    # provenance, and it answers BOTH facts: the pin is the more specific
    # complaint and the order asks for it first, exactly as the Typed door does.
    node = _published(
        WHERE_POSITION_META,
        _POSITION_ROW,
        _query(
            _POSITION,
            1,
            {"transaction-time": {"asOf": _TX_PIN_WIRE}, "valid-time": {"asOf": "latest"}},
        ),
    )
    source = WireKeyedInsertSource(_POSITION, node)
    source.capture("insert")

    resolved = source.resolve(_meta(WHERE_POSITION_META), "insert")

    assert resolved.provenance == "this"
    assert resolved.pin is not None
    assert resolved.pin.tx_time == _TX_PIN


def test_an_insert_source_authors_the_whole_create_payload() -> None:
    source = WireKeyedInsertSource(_ACCOUNT, {"id": 7, "owner": "Newton", "balance": "5.00"})
    source.capture("insert")

    prepared = source.prepare(source.resolve(_meta(ACCOUNT), "insert"), _UNBOUNDED)

    assert isinstance(prepared, PreparedKeyedWrite)
    assert prepared.rows[0] == {"id": 7, "owner": "Newton", "balance": Decimal("5.00")}


def test_an_insert_source_refuses_a_framework_owned_member_before_it_authors() -> None:
    source = WireKeyedInsertSource(
        _ACCOUNT, {"id": 7, "owner": "Newton", "balance": "5.00", "version": 3}
    )
    source.capture("insert")
    resolved = source.resolve(_meta(ACCOUNT), "insert")

    with pytest.raises(instructions.WriteInstructionError, match="framework-owned"):
        source.prepare(resolved, _UNBOUNDED)
