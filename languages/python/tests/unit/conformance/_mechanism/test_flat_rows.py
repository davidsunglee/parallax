"""The shared flat renderer: published Wire nodes as the physically keyed rows a case
states, with every expectation written out by hand.

Docker-free.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import pytest

from parallax.conformance import case_format, models
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._lanes import scenario
from parallax.conformance._mechanism import flat_rows as flat_rows_module
from parallax.conformance._mechanism import model_facts
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance._mechanism.flat_rows import flat_rows, omitted_value_objects
from parallax.core.db_port import MappingRow
from parallax.core.metamodel import (
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.wire import WireDecodingError
from tests._support.case_corpus import case as corpus_case


def _query(target: str, *narrow_to: str) -> ObjectQueryNode:
    clauses = {"narrowTo": list(narrow_to)} if narrow_to else {}
    return deserialize_query({"target": target, "predicate": {"true": {}}, **clauses})


def _rendered(
    model_name: str,
    target: str,
    roots: Sequence[Mapping[str, object]],
    *,
    value_objects: bool = False,
) -> list[MappingRow]:
    return flat_rows(
        models.load_models()[model_name], _query(target), roots, value_objects=value_objects
    )


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id, reachable=True)


def _abstract_step_query(case_id: str) -> ObjectQueryNode:
    """The first scenario step's query of ``case_id`` — an abstract-position read."""
    case = _case(case_id)
    steps = cast("list[dict[str, Any]]", cast("dict[str, Any]", case.document)["when"])
    return scenario.step_query(
        cast("list[dict[str, Any]]", cast("dict[str, Any]", steps)["scenario"])[0],
        model_facts.load_case_metamodel(case),
    )


# `m-inheritance-130`'s step 0 reads the abstract root `Vehicle` and is handed the
# concrete `Car` that row resolves to: id 1, `Sedan`, version 5, four doors, and no
# `axles` key at all, a materialized node carrying only its own branch's members.
_PUBLISHED_CAR: MappingRow = {
    "id": 1,
    "name": "Sedan",
    "version": 5,
    "doors": 4,
    "_type": "parallax.compatibility.Car",
}

_THING = "parallax.compatibility.ScalarThing"
_ALPHA = "snapshot.materialization.Alpha"
_COLLECTION_ITEM = "parallax.compatibility.CollectionTwinItem"
_POSITION = "parallax.compatibility.Position"
_CUSTOMER = "parallax.compatibility.Customer"


def test_a_column_resident_bytes_scalar_takes_its_result_spelling() -> None:
    (row,) = _rendered("scalars", _THING, [{"id": 1, "payload": "01020304"}])

    assert row == {"id": 1, "payload_hex": "01020304"}


def test_a_document_resident_bytes_scalar_keeps_its_storage_key() -> None:
    (row,) = _rendered("materialization-stress-document", _ALPHA, [{"id": 1, "blob": "0aff"}])

    assert row == {"id": 1, "blob": "0aff"}


def test_a_columns_twin_of_that_scalar_takes_the_result_spelling() -> None:
    (row,) = _rendered("materialization-stress-columns", _ALPHA, [{"id": 1, "blob": "0aff"}])

    assert row == {"id": 1, "blob_hex": "0aff"}


@pytest.mark.parametrize(
    "model", ["scalar-collection-layout-twin-columns", "scalar-collection-layout-twin-document"]
)
def test_a_bytes_collection_keeps_its_storage_key_under_either_layout(model: str) -> None:
    (row,) = _rendered(model, _COLLECTION_ITEM, [{"id": 1, "blobs": ["0aff", ""]}])

    assert row == {"id": 1, "blobs": ["0aff", ""]}


def test_a_scalar_collection_is_stated_element_by_element() -> None:
    (row,) = _rendered(
        "scalar-collection-layout-twin-columns",
        _COLLECTION_ITEM,
        [{"id": 1, "amounts": ["1.50", "2.00"], "tags": []}],
    )

    assert row == {"id": 1, "amounts": ["1.50", "2.00"], "tags": []}


def test_a_null_stays_null_under_its_result_spelling() -> None:
    (row,) = _rendered("scalars", _THING, [{"id": 1, "payload": None, "f64": None}])

    assert row == {"id": 1, "payload_hex": None, "f64": None}


def test_a_temporal_row_keeps_its_instants_and_open_ends() -> None:
    (row,) = _rendered(
        "position",
        _POSITION,
        [
            {
                "id": 1,
                "validStart": "2024-01-01T00:00:00.000000Z",
                "validEnd": "infinity",
                "txStart": "2024-04-01T00:00:00.000000Z",
                "txEnd": "infinity",
            }
        ],
    )

    assert row == {
        "pos_id": 1,
        "from_z": "2024-01-01T00:00:00.000000Z",
        "thru_z": "infinity",
        "in_z": "2024-04-01T00:00:00.000000Z",
        "out_z": "infinity",
    }


def test_an_open_end_is_a_member_only_of_a_temporal_end() -> None:
    with pytest.raises(WireDecodingError):
        _rendered("position", _POSITION, [{"id": 1, "validStart": "infinity"}])


def test_a_value_object_is_stated_only_where_the_row_asks_for_it() -> None:
    node = {"id": 1, "name": "Ada", "address": {"city": "Oslo"}}

    assert _rendered("customer", _CUSTOMER, [node]) == [{"id": 1, "name": "Ada"}]
    assert _rendered("customer", _CUSTOMER, [node], value_objects=True) == [
        {"id": 1, "name": "Ada", "address": {"city": "Oslo"}}
    ]


def test_the_omitted_value_objects_are_every_top_level_occurrence_of_a_concrete_read() -> None:
    traveler = EntityIdentity("parallax.compatibility", "Traveler")
    assert omitted_value_objects(
        models.load_models()["document-layout"], _query("parallax.compatibility.Traveler")
    ) == {
        ValueObjectIdentity(traveler, ("address",)),
        ValueObjectIdentity(traveler, ("tags",)),
    }


def test_the_omitted_value_objects_keep_an_inherited_occurrences_declaring_identity() -> None:
    assert omitted_value_objects(
        models.load_models()["storage-layout"],
        _query("parallax.compatibility.LayoutMeterReading"),
    ) == {
        ValueObjectIdentity(EntityIdentity("parallax.compatibility", "LayoutReading"), ("probe",))
    }


def test_the_omitted_value_objects_of_an_abstract_position_follow_its_narrowing() -> None:
    model = models.load_models()["document"]
    target = "parallax.compatibility.Document"
    memo = EntityIdentity("parallax.compatibility", "Memo")
    assert omitted_value_objects(model, _query(target)) == {
        ValueObjectIdentity(memo, ("annotation",))
    }
    narrowed = _query(target, "parallax.compatibility.FinancialDocument")
    assert omitted_value_objects(model, narrowed) == frozenset()


def test_an_abstract_position_pads_its_superset_and_states_the_variant() -> None:
    # What an abstract step's `expectRows` state is the projection the published
    # node OCCUPIES (m-case-format "Read targeting"): every column the position's
    # superset places, `null` where the row's own branch contributes none, and the
    # `_type` the node carries. Rendering the ADDRESSED position's
    # applicable members instead drops `doors` — a value the read published — and
    # reports no variant, which is a node no case could state.
    case = _case("m-inheritance-130")

    rows = flat_rows(
        model_facts.load_case_metamodel(case),
        _abstract_step_query("m-inheritance-130"),
        [dict(_PUBLISHED_CAR)],
        value_objects=True,
    )

    assert rows == [
        {
            "id": 1,
            "name": "Sedan",
            "version": 5,
            "doors": 4,
            "axles": None,
            "_type": "parallax.compatibility.Car",
        }
    ]


def test_a_narrowed_abstract_position_pads_only_what_it_selects() -> None:
    # Narrowing shrinks the superset the position projects without making the read
    # concrete: over `[Car]` alone the sibling `axles` is no column of the
    # projection at all, and the node still states the variant it resolved to.
    case = _case("m-inheritance-130")
    query = _query(
        _abstract_step_query("m-inheritance-130").target.canonical, "parallax.compatibility.Car"
    )

    rows = flat_rows(
        model_facts.load_case_metamodel(case), query, [dict(_PUBLISHED_CAR)], value_objects=False
    )

    assert rows == [
        {"id": 1, "name": "Sedan", "version": 5, "doors": 4, "_type": "parallax.compatibility.Car"}
    ]


def test_a_concrete_target_of_a_family_states_its_variant_and_no_sibling() -> None:
    rows = _rendered(
        "vehicle",
        "parallax.compatibility.Car",
        [
            {
                "id": 1,
                "name": "Sedan",
                "version": 5,
                "doors": 4,
                "_type": "parallax.compatibility.Car",
            }
        ],
    )

    assert rows == [
        {"id": 1, "name": "Sedan", "version": 5, "doors": 4, "_type": "parallax.compatibility.Car"}
    ]


def test_a_reused_member_name_resolves_at_each_published_variant() -> None:
    case = _case("m-inheritance-124")
    when = cast("Mapping[str, object]", case.document["when"])

    rows = flat_rows(
        model_facts.load_case_metamodel(case),
        deserialize_query(when["objectQuery"]),
        [
            {
                "id": 1,
                "detail": "visa-4242",
                "authorizationCode": "AUTH-7",
                "_type": "parallax.compatibility.CardPayment",
            },
            {"id": 2, "detail": "12.50", "_type": "parallax.compatibility.CashPayment"},
        ],
        value_objects=True,
    )

    assert rows == [
        {
            "id": 1,
            "detail": "visa-4242",
            "authorization_code": "AUTH-7",
            "_type": "parallax.compatibility.CardPayment",
        },
        {
            "id": 2,
            "detail": "12.50",
            "authorization_code": None,
            "_type": "parallax.compatibility.CashPayment",
        },
    ]


def test_an_abstract_position_refuses_a_node_publishing_no_variant() -> None:
    # An abstract position publishes concrete nodes, so a node arriving without the
    # variant is a lane that resolved nothing rather than a row to render: which
    # branch its columns belong to would have to be guessed.
    case = _case("m-inheritance-130")
    node = {key: value for key, value in _PUBLISHED_CAR.items() if key != "_type"}

    with pytest.raises(EngineError, match="_type"):
        flat_rows(
            model_facts.load_case_metamodel(case),
            _abstract_step_query("m-inheritance-130"),
            [node],
            value_objects=False,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf")], ids=["nan", "infinity"])
def test_a_non_member_scalar_is_refused_rather_than_repaired(value: float) -> None:
    with pytest.raises(WireDecodingError):
        _rendered("scalars", _THING, [{"id": 1, "f64": value}])


def test_a_non_canonical_spelling_is_refused_rather_than_repaired() -> None:
    with pytest.raises(WireDecodingError):
        _rendered("scalars", _THING, [{"id": 1, "payload": "0AFF"}])


def test_a_projected_row_refuses_an_ambiguous_member() -> None:
    model: Metamodel = models.load_models()["document-codec"]
    entity = model.entities[0]
    first, second = entity.declared_attributes[:2]
    columns = {"ambiguous": (("first", first), ("second", second))}

    with pytest.raises(EngineError, match="does not select one declaration"):
        flat_rows_module._projected_row(  # pyright: ignore[reportPrivateUsage] - no accepted model reaches this
            model,
            ActualWireProjection(model),
            columns,
            None,
            {"ambiguous": 1},
        )
