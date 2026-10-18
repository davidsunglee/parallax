"""The two Wire keyed sources, asked what they capture and author.

The keyed write ingress owns the order; a source answers facts into it. This
suite asks each Wire adapter what is its own — the change document's shape,
which Entity a node or spelling names, and the row a document authors — and
nothing about the provenance, Pin, evidence, and authority it resolves, which
`test_sources.py` states once for both representations, or about what the order
then does with the answer, which `test_keyed_write_order.py` fixes through the
public verbs.

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
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.instructions import PreparedKeyedWrite
from parallax.core.base import INFINITY, SQL_NULL
from parallax.core.db_port import MappingRow
from parallax.core.metamodel import Metamodel
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan import ObjectKey
from parallax.snapshot import TxnContext, WireEntity
from parallax.snapshot._handle._wire_writes import (
    WireKeyedInsertSource,
    WireKeyedWriteSource,
)
from parallax.snapshot._publication._wire import authoring_of
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests._support.model_capabilities import cataloged_for
from tests.unit._transact_support import (
    ACCOUNT,
    db_for,
)
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
)

_TX_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)

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


def _query(entity: str, key: int) -> dict[str, object]:
    return {
        "target": entity,
        "predicate": {"eq": {"path": f"{entity}.id", "value": key}},
    }


def _published(model: DomainModel, row: MappingRow, query: dict[str, object]) -> WireEntity:
    """One frozen Entity mapping as a standalone Wire read of this store
    publishes it: a stored node carrying no Read Evidence."""
    port = ScriptedAdapter(Read(rows=[dict(row)]))
    return db_for(model, port).wire.find(query).result()


def _projected_account() -> WireEntity:
    port = ScriptedAdapter(Read(rows=[dict(_ACCOUNT_ROW)]))
    snapshot = db_for(ACCOUNT, port).find(mm.Account.where(mm.Account.id == 1))
    return snapshot.wire().result()


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
        source.capture("amend")


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
# Resolve: which Entity a node names.                                         #
# --------------------------------------------------------------------------- #
def test_a_published_node_names_its_own_concrete_entity() -> None:
    # A standalone read publishes a stored node of this source and leaves no
    # Read Evidence on it, so the object the write addresses comes from the row
    # the node's own key authors.
    source = WireKeyedWriteSource(_account_node(), {"balance": "125.00"})
    source.capture("amend")

    resolved = source.resolve(_meta(ACCOUNT), "amend")
    prepared = source.prepare(resolved, valid_from=None, until=None)

    assert resolved.entity.identity == mm.Account.identity
    assert prepared.object_key == ObjectKey(mm.Account.identity, (("id", 1),))


def test_a_projected_node_enters_the_existing_wire_keyed_source() -> None:
    node = _projected_account()
    source = WireKeyedWriteSource(node, {"balance": "125.00"})
    source.capture("amend")

    resolved = source.resolve(_meta(ACCOUNT), "amend")
    prepared = source.prepare(resolved, valid_from=None, until=None)

    assert resolved.entity.identity == mm.Account.identity
    assert prepared.instruction.rows[0] == {"id": 1, "balance": Decimal("125.00")}
    assert prepared.assigned == {"balance"}


def test_the_node_an_insert_answered_names_the_object_its_authority_opened() -> None:
    def fn(tx: TxnContext) -> WireEntity:
        return tx.wire.insert(_ACCOUNT, {"id": 7, "owner": "Newton", "balance": "5.00"})

    opened = db_for(ACCOUNT, ScriptedAdapter(Transact(Write()))).transact(fn)
    source = WireKeyedWriteSource(opened, {"id": 7, "balance": "6.00"})
    source.capture("amend")

    resolved = source.resolve(_meta(ACCOUNT), "amend")
    prepared = source.prepare(resolved, valid_from=None, until=None)

    authority = authoring_of(opened)
    assert authority is not None
    assert resolved.entity.identity == mm.Account.identity
    assert prepared.object_key is authority.object_key
    assert prepared.instruction.rows[0] == {"id": 7, "balance": Decimal("6.00")}
    assert prepared.assigned == {"balance"}


# --------------------------------------------------------------------------- #
# Prepare: the authored row, whose stated keys are its literal assignment set. #
# --------------------------------------------------------------------------- #
def test_prepare_states_every_authored_member_as_its_literal_assignment() -> None:
    source = WireKeyedWriteSource(_account_node(), {"balance": "125.00"})
    source.capture("amend")
    resolved = source.resolve(_meta(ACCOUNT), "amend")

    prepared = source.prepare(resolved, valid_from=None, until=None)

    assert prepared.instruction.rows[0] == {"id": 1, "balance": Decimal("125.00")}
    assert prepared.assigned == {"balance"}
    assert prepared.object_key == ObjectKey(mm.Account.identity, (("id", 1),))


def test_a_member_equal_to_what_the_source_published_is_still_assigned() -> None:
    source = WireKeyedWriteSource(_account_node(), {"balance": "100.00"})
    source.capture("amend")
    resolved = source.resolve(_meta(ACCOUNT), "amend")

    prepared = source.prepare(resolved, valid_from=None, until=None)

    assert prepared.instruction.rows[0] == {"id": 1, "balance": Decimal("100.00")}
    assert prepared.assigned == {"balance"}


def test_a_stated_key_naming_the_published_object_addresses_rather_than_assigns() -> None:
    # A node no writable attempt's read published carries no Object Key of its
    # own, so its published key is what a stated key member is judged against.
    source = WireKeyedWriteSource(_account_node(), {"id": 1, "balance": "125.00"})
    source.capture("amend")
    resolved = source.resolve(_meta(ACCOUNT), "amend")

    prepared = source.prepare(resolved, valid_from=None, until=None)

    assert prepared.instruction.rows[0] == {"id": 1, "balance": Decimal("125.00")}
    assert prepared.assigned == {"balance"}
    assert prepared.object_key == ObjectKey(mm.Account.identity, (("id", 1),))


def test_a_stated_key_naming_another_object_is_refused_while_preparing() -> None:
    source = WireKeyedWriteSource(_account_node(), {"id": 2, "balance": "125.00"})
    source.capture("amend")
    resolved = source.resolve(_meta(ACCOUNT), "amend")

    with pytest.raises(instructions.WriteInstructionError, match="another object"):
        source.prepare(resolved, valid_from=None, until=None)


def test_a_destructive_verb_authors_its_identity_row_and_assigns_nothing() -> None:
    source = WireKeyedWriteSource(_account_node(), None)
    source.capture("delete")
    resolved = source.resolve(_meta(ACCOUNT), "delete")

    prepared = source.prepare(resolved, valid_from=None, until=None)

    assert prepared.instruction.rows[0] == {"id": 1}
    assert prepared.assigned == frozenset()


# --------------------------------------------------------------------------- #
# The insert door's narrower peer.                                            #
# --------------------------------------------------------------------------- #
def test_a_payload_names_the_entity_its_spelling_states() -> None:
    source = WireKeyedInsertSource(_ACCOUNT, {"id": 7, "owner": "Newton", "balance": "5.00"})
    source.capture("insert")

    resolved = source.resolve(_meta(ACCOUNT), "insert")

    assert resolved.entity.identity == mm.Account.identity


def test_an_insert_source_authors_the_whole_create_payload() -> None:
    source = WireKeyedInsertSource(_ACCOUNT, {"id": 7, "owner": "Newton", "balance": "5.00"})
    source.capture("insert")

    prepared = source.prepare(source.resolve(_meta(ACCOUNT), "insert"), valid_from=None, until=None)

    assert isinstance(prepared, PreparedKeyedWrite)
    assert prepared.rows[0] == {"id": 7, "owner": "Newton", "balance": Decimal("5.00")}


def test_an_insert_source_hands_its_raw_window_to_preparation() -> None:
    source = WireKeyedInsertSource(_POSITION, {"id": 9, "acctNum": "A", "value": "1.00"})
    source.capture("insert")
    resolved = source.resolve(_meta(WHERE_POSITION_META), "insert")
    stated = dt.datetime(2024, 1, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))

    prepared = source.prepare(resolved, valid_from=stated, until=None)

    assert prepared.valid_time_window == TimeInterval(_TX_START, INFINITY)
    with pytest.raises(
        instructions.WriteInstructionError, match="a bitemporal 'insert' requires valid_from"
    ):
        source.prepare(resolved, valid_from=None, until=None)


def test_an_insert_source_refuses_a_framework_owned_member_before_it_authors() -> None:
    source = WireKeyedInsertSource(
        _ACCOUNT, {"id": 7, "owner": "Newton", "balance": "5.00", "version": 3}
    )
    source.capture("insert")
    resolved = source.resolve(_meta(ACCOUNT), "insert")

    with pytest.raises(instructions.WriteInstructionError, match="framework-owned"):
        source.prepare(resolved, valid_from=None, until=None)
