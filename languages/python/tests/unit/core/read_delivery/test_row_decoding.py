"""Row decoding over hand-built result contracts.

Each case pairs a contract with a positional row laid out in its result order:
where the decoder reads each carrier and member, what it answers, and what it
refuses. Building the contracts directly also reaches what compilation never
produces: a carrier with no result cell, which the decoder refuses by key at
the row, and a row whose width disagrees with the contract.
"""

from __future__ import annotations

import pytest

from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.db_port import Row
from parallax.core.document_codec import MISSING
from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.read_delivery._row_decoding import (
    publication_keys,
    raw_member,
    row_coordinates,
    row_identity,
)
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._inheritance import (
    ByLiteral,
    ByTag,
    DocumentFanOut,
    FixedIdentity,
    ResultContract,
    RowIdentity,
    SharedDocument,
)

_ROOT = EntityIdentity("decoding", "Root")
_LEAF = EntityIdentity("decoding", "Leaf")
_TAGS = ByTag("kind", _ROOT, (("leaf", _LEAF, "Leaf"),))
_LITERAL = ByLiteral("family_variant", (("Leaf", _LEAF),), (("Leaf", ()),), narrow_to_owned=False)


_NO_MEMBERS = DocumentFanOut(None, ())
_DISPLAY_NAME = DocumentFanOut(None, (("display_name", ("displayName",)),))


def _contract(
    resolve: RowIdentity,
    result_keys: tuple[str, ...],
    *,
    shared: bool = False,
    leaf_document: DocumentFanOut = _NO_MEMBERS,
) -> ResultContract:
    return ResultContract(
        resolve,
        SharedDocument("payload", ((_LEAF, leaf_document),)) if shared else None,
        None,
        (),
        result_keys,
        (),
    )


_FIXED_DOCUMENT = _contract(
    FixedIdentity(_LEAF), ("id", "payload"), shared=True, leaf_document=_DISPLAY_NAME
)


@pytest.mark.parametrize(
    "contract",
    [
        _contract(FixedIdentity(_LEAF), ("id",)),
        _contract(FixedIdentity(_LEAF), ("id", "payload"), shared=True),
        _contract(_TAGS, ("id", "kind")),
        _contract(_LITERAL, ("id", "family_variant")),
    ],
    ids=["fixed", "fixed-document", "tag", "literal"],
)
def test_a_positional_row_of_the_wrong_width_is_refused(contract: ResultContract) -> None:
    with pytest.raises(
        ValueError, match=f"result key count {len(contract.result_keys)} does not match row arity 3"
    ):
        row_identity(contract, (1, 2, 3))


def test_a_coordinate_is_read_only_off_a_row_of_the_contracts_width() -> None:
    contract = ResultContract(
        FixedIdentity(_LEAF), None, None, (), ("id", "parallax_seek_0"), ("parallax_seek_0",)
    )
    assert row_coordinates(contract, ((1, 2),)) == (ContinuationCoordinate((2,)),)
    for row in ((1,), (1, 2, 3)):
        with pytest.raises(ValueError, match="does not match row arity"):
            row_coordinates(contract, (row,))


@pytest.mark.parametrize(
    ("contract", "row", "missing"),
    [
        (_contract(FixedIdentity(_LEAF), ("id",), shared=True), (1,), "payload"),
        (_contract(_TAGS, ("id",)), (1,), "kind"),
        (_contract(_TAGS, ("id", "kind"), shared=True), (1, "leaf"), "payload"),
        (_contract(_LITERAL, ("id",)), (1,), "family_variant"),
        (_contract(_LITERAL, ("id", "family_variant"), shared=True), (1, "Leaf"), "payload"),
    ],
    ids=["fixed-document", "tag", "tag-document", "literal", "literal-document"],
)
def test_a_carrier_without_a_result_cell_is_refused_at_the_row(
    contract: ResultContract, row: tuple[object, ...], missing: str
) -> None:
    with pytest.raises(KeyError, match=missing):
        row_identity(contract, row)


@pytest.mark.parametrize(
    ("contract", "row", "identity"),
    [
        (
            _contract(_TAGS, ("id", "kind", "payload"), shared=True),
            (1, "leaf", SQL_NULL),
            (_LEAF, "Leaf", None, None),
        ),
        (
            _contract(_LITERAL, ("id", "family_variant", "payload"), shared=True),
            (1, "Leaf", PresentDocument({})),
            (_LEAF, "Leaf", None, dict[str, object]()),
        ),
    ],
    ids=["tag", "literal"],
)
def test_a_row_reads_its_carriers_at_their_result_cells(
    contract: ResultContract, row: Row, identity: tuple[object, ...]
) -> None:
    assert row_identity(contract, row) == identity


@pytest.mark.parametrize(
    ("row", "member"),
    [
        ((1, SQL_NULL), SQL_NULL),
        ((1, PresentDocument({})), MISSING),
    ],
    ids=["sql-null-document", "present-empty-document"],
)
def test_a_shared_document_member_keeps_its_carriers_raw_state(row: Row, member: object) -> None:
    # A shared Structured Column's SQL-null carrier and a present document that
    # omits the same member collapse to the same read value, but they are distinct
    # stored structure and must remain distinct before witness comparison.
    assert raw_member(_FIXED_DOCUMENT, row, _LEAF, "display_name") is member


@pytest.mark.parametrize(
    ("resolved", "key"),
    [(_LEAF, "missing"), (_ROOT, "missing")],
    ids=["outside-the-document", "entity-without-a-document-entry"],
)
def test_a_member_the_row_carries_neither_way_is_refused_by_key(
    resolved: EntityIdentity, key: str
) -> None:
    with pytest.raises(KeyError, match=key):
        raw_member(_FIXED_DOCUMENT, (1, PresentDocument({"displayName": "Ada"})), resolved, key)


def test_a_shared_document_member_refuses_a_carrier_the_port_never_folded() -> None:
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        raw_member(_FIXED_DOCUMENT, (1, {"displayName": "Ada"}), _LEAF, "display_name")


def test_row_identity_refuses_a_raw_document_outside_the_database_port_contract() -> None:
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        row_identity(_FIXED_DOCUMENT, (1, {"displayName": "Ada"}))


def test_a_root_outside_the_shared_document_publishes_no_padding() -> None:
    contract = _contract(_TAGS, ("id", "kind", "payload"), shared=True)
    assert publication_keys(contract, _ROOT, None) == ("id",)
