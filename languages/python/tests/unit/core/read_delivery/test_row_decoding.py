"""Row decoding over hand-built result contracts.

A compiled read always projects every carrier its row identity reads, so the
bind-time readers resolve each carrier to an ordinal. These contracts are built
directly to reach what compilation never produces: a carrier with no result
cell, which the reader refuses by key at the row rather than at bind, and a
positional row whose width disagrees with the contract.
"""

from __future__ import annotations

import pytest

from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.metamodel import EntityIdentity
from parallax.core.read_delivery._row_decoding import publication_keys, row_identity_reader
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
        row_identity_reader(contract)((1, 2, 3))


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
    read = row_identity_reader(contract)
    with pytest.raises(KeyError, match=missing):
        read(row)


def test_a_mapping_row_reads_its_carriers_by_key() -> None:
    read = row_identity_reader(_contract(_TAGS, ("id", "kind", "payload"), shared=True))
    assert read({"id": 1, "kind": "leaf", "payload": SQL_NULL}) == (_LEAF, "Leaf", None, None)
    read = row_identity_reader(
        _contract(_LITERAL, ("id", "family_variant", "payload"), shared=True)
    )
    assert read({"id": 1, "family_variant": "Leaf", "payload": PresentDocument({})}) == (
        _LEAF,
        "Leaf",
        None,
        {},
    )


def test_a_root_outside_the_shared_document_publishes_no_padding() -> None:
    contract = _contract(_TAGS, ("id", "kind", "payload"), shared=True)
    assert publication_keys(contract, _ROOT, None) == ("id",)
