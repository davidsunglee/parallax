"""Where the decoder reads a row's carriers and shared-document members.

Every contract is a compiled read's own, and every row is laid out
positionally as its statement selects it: where the row identity, the shared
document, and each Continuation Order coordinate are read, what a
document-resident member reads before classification, and the width a row
must have.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from parallax.core import continuation, deep_fetch
from parallax.core import predicate as oa
from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import MISSING
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.object_query import object_query, validate_object_query
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.read_delivery._page import ROOT_LEVEL, PageBuilder, ViewSchema
from parallax.core.read_delivery._row_converter import bind
from parallax.core.read_delivery._row_decoding import row_coordinates, row_identity
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.sql_gen._compile import compile_read as compile_entity_query
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model, target
from tests.unit._document_layout_support import document_model, entity
from tests.unit._prepared_read_support import result_row
from tests.unit.core.sql_gen._delivery_support import deliver

ORDERS = model("orders")
DOCUMENT = document_model()
DOCUMENT_LAYOUT = model("document-layout")
PAYMENT = model("payment")


def _read(meta: Metamodel, name: str) -> CompiledRead:
    return compile_read(oa.TrueNode(), meta, POSTGRES, target(meta, name), result_form="instance")


@pytest.mark.parametrize(
    ("meta", "name"),
    [
        (ORDERS, "Order"),
        (DOCUMENT_LAYOUT, "CardPayment"),
        (PAYMENT, "Payment"),
        (DOCUMENT_LAYOUT, "Publication"),
    ],
    ids=["fixed", "fixed-document", "tag", "literal"],
)
def test_a_positional_row_of_the_wrong_width_is_refused(meta: Metamodel, name: str) -> None:
    contract = _read(meta, name).result_contract
    with pytest.raises(
        ValueError, match=f"result cell count {len(contract.slots)} does not match row arity 9"
    ):
        row_identity(contract, tuple(range(9)))


def test_a_coordinate_is_read_only_off_a_row_of_the_contracts_width() -> None:
    entity_metadata = target(ORDERS, "Order")
    plan = continuation.plan(
        validate_object_query(
            entity_metadata, object_query(entity_metadata.identity, oa.TrueNode()), ORDERS
        ),
        ORDERS,
    )
    compiled = compile_entity_query(
        deep_fetch.plan(
            plan.first(limit=2),
            ORDERS,
            projection=deep_fetch.ReadProjectionRequest("none", False),
        ).root,
        ORDERS,
        POSTGRES,
    )
    contract = compiled.result_contract
    width = len(contract.slots)
    assert row_coordinates(contract, (tuple(range(width)),)) == (
        ContinuationCoordinate((width - 1,)),
    )
    for row in (tuple(range(width - 1)), tuple(range(width + 1))):
        with pytest.raises(ValueError, match="does not match row arity"):
            row_coordinates(contract, (row,))


@pytest.mark.parametrize(
    ("name", "cells", "identity"),
    [
        (
            "Payment",
            {"id": 1, "kind": "card", "payload": SQL_NULL},
            ("CardPayment", "CardPayment", None, None),
        ),
        (
            "Publication",
            {"id": 1, "payload": PresentDocument({}), "family_variant": "Film"},
            ("Film", "Film", None, dict[str, object]()),
        ),
    ],
    ids=["tag", "literal"],
)
def test_a_row_reads_its_carriers_at_their_result_cells(
    name: str, cells: Mapping[str, object], identity: tuple[object, ...]
) -> None:
    compiled = _read(DOCUMENT_LAYOUT, name)
    resolved, variant, unknown, document = row_identity(
        compiled.result_contract, result_row(compiled, cells)
    )
    assert (resolved.name, variant, unknown, document) == identity


@pytest.mark.parametrize(
    ("payload", "member"),
    [(SQL_NULL, SQL_NULL), (PresentDocument({}), MISSING)],
    ids=["sql-null-document", "present-empty-document"],
)
def test_a_shared_document_member_keeps_its_carriers_raw_state(
    payload: object, member: object
) -> None:
    # A shared Structured Column's SQL-null carrier and a present document that
    # omits the same member collapse to the same read value, but they are distinct
    # stored structure and must remain distinct before witness comparison.
    compiled = _read(DOCUMENT, "Person")
    builder = PageBuilder(ViewSchema.of())
    converter = bind(CatalogedModel(DOCUMENT), compiled.result_contract, compiled.projection)
    index, *_ = converter.convert_row(
        result_row(compiled, {"id": 1, "payload": payload}), builder, source=ROOT_LEVEL
    )
    person = entity(DOCUMENT, "Person").identity
    assert builder.member_value(index, AttributeIdentity(person, "displayName")) is member


def test_a_root_outside_the_shared_document_publishes_no_padding() -> None:
    # A flat row resolving to a concrete pads its siblings' document members, while
    # a row an unrecognized tag resolved to the family root carries no document of
    # the position's and so pads nothing.
    compiled = compile_read(
        oa.TrueNode(), DOCUMENT_LAYOUT, POSTGRES, target(DOCUMENT_LAYOUT, "Payment")
    )
    card, unknown = deliver(
        DOCUMENT_LAYOUT,
        compiled,
        [
            {"id": 1, "kind": "card", "payload": {"detail": "visa", "authorizationCode": "A"}},
            {"id": 3, "kind": "wire", "payload": {"detail": "x"}},
        ],
    )
    assert card.published == (
        ("id", 1),
        ("detail", "visa"),
        ("authorization_code", "A"),
        ("familyVariant", "CardPayment"),
    )
    assert unknown.published == (("id", 3),)
