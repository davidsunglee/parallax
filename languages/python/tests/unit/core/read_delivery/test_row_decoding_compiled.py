"""Row decoding over compiled result contracts.

Compilation supplies each contract; what is graded is how the decoder reads,
classifies, and refuses a row against it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

import pytest

from parallax.core import predicate as oa
from parallax.core.base import SQL_NULL, DocumentValue, PresentDocument
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import MemberShape
from parallax.core.read_delivery._row_decoding import (
    member_classifier,
    raw_member,
    row_identity_reader,
)
from parallax.core.sql_gen import SqlGenError
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import formed, model, target
from tests.unit._document_layout_support import columns_model, document_model, entity

ORDERS = model("orders")
DOCUMENT = document_model()
COLUMNS = columns_model()

# One person, spelled the two ways the two layouts store it. Every leaf inside
# the document carries the codec's own portable spelling, which is what a
# document-resident member reads back as before it is decoded.
_DOCUMENT_VALUE: DocumentValue = {
    "displayName": "Ada",
    "score": 7,
    "joinedOn": "2026-01-15",
    "address": {"city": "Oslo", "geo": {"country": "NO"}},
    "tags": [{"label": "founder"}],
}
_DOCUMENT_ROW = {
    "id": 1,
    "payload": PresentDocument(_DOCUMENT_VALUE),
}
_COLUMNS_ROW = {
    "id": 1,
    "display_name": "Ada",
    "score": 7,
    "joined_on": dt.date(2026, 1, 15),
    "address": PresentDocument({"city": "Oslo", "geo": {"country": "NO"}}),
    "tags": PresentDocument([{"label": "founder"}]),
}


def test_a_positional_row_is_refused_at_the_wrong_arity_and_an_unknown_member() -> None:
    compiled = compile_read(oa.TrueNode(), ORDERS, POSTGRES, target(ORDERS, "Order"))

    with pytest.raises(ValueError, match="does not match row arity"):
        row_identity_reader(compiled.result_contract)(())
    with pytest.raises(KeyError, match="missing"):
        raw_member(compiled.result_contract, (), compiled.target, "missing")


def test_raw_document_access_validates_the_resolved_member_and_folded_carrier() -> None:
    person = entity(DOCUMENT, "Person").identity
    marker = entity(DOCUMENT, "Marker").identity
    document = compile_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )

    assert (
        raw_member(document.result_contract, {"payload": SQL_NULL}, person, "display_name")
        is SQL_NULL
    )
    display_name = member_classifier(document.result_contract, person, "display_name")
    assert display_name(
        raw_member(document.result_contract, _DOCUMENT_ROW, person, "display_name")
    ) == (
        "Ada",
        (),
    )
    address = member_classifier(document.result_contract, person, "address")
    address_value, address_findings = address(
        raw_member(document.result_contract, _DOCUMENT_ROW, person, "address")
    )
    assert address_value == {"city": "Oslo", "geo": {"country": "NO"}}
    assert address_findings == ()

    def object_output(_shape: MemberShape, values: Iterable[object]) -> tuple[object, ...]:
        return tuple(values)

    with pytest.raises(ValueError, match="must be supplied together"):
        member_classifier(document.result_contract, person, "address", build_object=object_output)
    with pytest.raises(KeyError, match="missing"):
        member_classifier(document.result_contract, marker, "missing")
    with pytest.raises(KeyError, match="missing"):
        member_classifier(document.result_contract, person, "missing")
    with pytest.raises(KeyError, match="missing"):
        raw_member(document.result_contract, _DOCUMENT_ROW, person, "missing")
    with pytest.raises(KeyError, match="missing"):
        raw_member(document.result_contract, _DOCUMENT_ROW, marker, "missing")
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        raw_member(document.result_contract, {"payload": _DOCUMENT_VALUE}, person, "display_name")

    columns = compile_read(
        oa.TrueNode(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
    )
    classify_address = member_classifier(columns.result_contract, person, "address")
    assert classify_address(_COLUMNS_ROW["address"])[0] == {
        "city": "Oslo",
        "geo": {"country": "NO"},
    }
    incomplete_classifier = member_classifier(
        columns.result_contract, person, "address", build_object=object_output
    )
    with pytest.raises(ValueError, match="must be supplied together"):
        incomplete_classifier(_COLUMNS_ROW["address"])
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        classify_address({"city": "Oslo"})
    with pytest.raises(KeyError, match="missing"):
        member_classifier(columns.result_contract, person, "missing")


def test_row_identity_refuses_a_raw_document_outside_the_database_port_contract() -> None:
    compiled = compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"))
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        row_identity_reader(compiled.result_contract)({"id": 1, "payload": _DOCUMENT_VALUE})


def test_an_occurrence_only_entity_document_still_requires_a_folded_carrier() -> None:
    from parallax.descriptor._records import (
        Attribute,
        DocumentLayout,
        Entity,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    holder = Entity(
        name="Holder",
        table="holder",
        layout=DocumentLayout(column="payload"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="profile",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    holder_model = formed(Metamodel(entities=(holder,)))
    compiled = compile_read(
        oa.TrueNode(),
        holder_model,
        POSTGRES,
        entity(holder_model, "Holder"),
        result_form="instance",
    )
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        raw_member(
            compiled.result_contract,
            {"id": 1, "payload": {"profile": {"label": "x"}}},
            compiled.target,
            "profile",
        )


def test_predecessor_document_retention_requires_a_folded_carrier() -> None:
    compiled = compile_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Marker"), result_form="instance"
    )
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        row_identity_reader(compiled.result_contract)({"id": 1, "payload": {}})
