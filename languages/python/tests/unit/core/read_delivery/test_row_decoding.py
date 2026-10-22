"""Row decoding over hand-built result contracts.

A compiled read always projects every carrier its row identity reads. These
contracts are built directly to reach what compilation never produces: a carrier
with no result cell, which the decoder refuses by key at the row, and a
positional row whose width disagrees with the contract.
"""

from __future__ import annotations

import pytest

from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.read_delivery._row_decoding import (
    publication_keys,
    row_coordinates,
    row_identity,
)
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


def _contract(
    resolve: RowIdentity, result_keys: tuple[str, ...], *, shared: bool = False
) -> ResultContract:
    return ResultContract(
        resolve,
        SharedDocument("payload", ((_LEAF, DocumentFanOut(None, ())),)) if shared else None,
        None,
        (),
        result_keys,
        (),
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


def test_a_mapping_row_reads_its_carriers_by_key() -> None:
    tags = _contract(_TAGS, ("id", "kind", "payload"), shared=True)
    assert row_identity(tags, {"id": 1, "kind": "leaf", "payload": SQL_NULL}) == (
        _LEAF,
        "Leaf",
        None,
        None,
    )
    literal = _contract(_LITERAL, ("id", "family_variant", "payload"), shared=True)
    assert row_identity(
        literal, {"id": 1, "family_variant": "Leaf", "payload": PresentDocument({})}
    ) == (
        _LEAF,
        "Leaf",
        None,
        {},
    )


def test_a_root_outside_the_shared_document_publishes_no_padding() -> None:
    contract = _contract(_TAGS, ("id", "kind", "payload"), shared=True)
    assert publication_keys(contract, _ROOT, None) == ("id",)
