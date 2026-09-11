"""The production-side oracle for non-Wire observations: the codec arm an actual
selects from accepted Metadata, the row variant a reused column is projected
under, and the refusals a malformed or unowned member meets.
"""

from __future__ import annotations

import dataclasses
import decimal
import functools
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pytest

from parallax.conformance import case_format, models, sweep
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.core import inheritance, storage_layout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    ValueObjectIdentity,
)
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.unit_work import (
    ObjectKey,
)
from parallax.core.wire import WireEncodingError


@functools.cache
def _corpus() -> tuple[case_format.Case, ...]:
    return tuple(case_format.load_cases())


def _by_id(cases: Sequence[case_format.Case]) -> Mapping[str, case_format.Case]:
    # A case id is unique within its module, so a collision here means two case
    # files claim one id; keying them into a dict would silently resolve every
    # lookup to whichever file sorts last.
    index: dict[str, case_format.Case] = {}
    for case in cases:
        claimed = index.setdefault(case.case_id, case)
        if claimed is not case:
            raise ValueError(
                f"case id {case.case_id!r} is claimed by both "
                f"{claimed.path.name} and {case.path.name}"
            )
    return index


@functools.cache
def _reachable_by_id() -> Mapping[str, case_format.Case]:
    return _by_id(sweep.reachable_cases(cases=list(_corpus())))


def _case(case_id: str) -> case_format.Case:
    return _reachable_by_id()[case_id]


def test_run_read_case_wire_renders_managed_row_values() -> None:
    # Production actuals select the codec arm from accepted Metadata, never from
    # the UUID carrier itself.
    model = models.load_models()["scalars"]
    entity = model.entities[0]
    external_id = entity.attribute("externalId")
    assert external_id is not None
    projected = ActualWireProjection(model).scalar(
        external_id, uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
    )
    assert projected == "123e4567-e89b-12d3-a456-426614174000"


def test_run_read_case_wire_refuses_a_wire_shaped_non_member_carrier() -> None:
    model = models.load_models()["scalars"]
    entity = model.entities[0]
    external_id = entity.attribute("externalId")
    assert external_id is not None
    with pytest.raises(WireEncodingError):
        ActualWireProjection(model).scalar(external_id, "123e4567-e89b-12d3-a456-426614174000")


def test_read_row_projects_reused_tph_columns_from_each_row_variant() -> None:
    case = _case("m-inheritance-124")
    model = models.load_models()["document-layout"]
    when = cast("Mapping[str, object]", case.document["when"])
    query = deserialize_query(when["objectQuery"])
    projection = ActualWireProjection(model)

    card = projection.published_row(
        query,
        {
            "id": 1,
            "detail": "visa-4242",
            "authorization_code": "AUTH-7",
            "familyVariant": "CardPayment",
        },
    )
    cash = projection.published_row(
        query,
        {
            "id": 2,
            "detail": decimal.Decimal("12.50"),
            "authorization_code": None,
            "familyVariant": "CashPayment",
        },
    )

    assert card["detail"] == "visa-4242"
    assert cash["detail"] == "12.50"


def test_read_row_requires_variant_provenance_for_reused_columns() -> None:
    case = _case("m-inheritance-124")
    model = models.load_models()["document-layout"]
    when = cast("Mapping[str, object]", case.document["when"])
    query = deserialize_query(when["objectQuery"])

    with pytest.raises(ValueError, match="requires familyVariant"):
        ActualWireProjection(model).published_row(query, {"id": 1, "detail": "ambiguous"})


def test_actual_wire_projection_rejects_unowned_members_and_malformed_value_objects() -> None:
    model = models.load_models()["document-codec"]
    entity = model.entities[0]
    position = inheritance.view(model).entity(entity.identity)
    assert position is not None
    profile = position.applicable_value_object("profile")
    assert profile is not None
    entries = profile.value_object("entries")
    assert entries is not None
    projection = ActualWireProjection(model)
    query = deserialize_query({"target": entity.identity.canonical, "predicate": {"all": {}}})

    with pytest.raises(ValueError, match="no projected member owns"):
        projection.published_row(query, {"unknown": 1})
    with pytest.raises(ValueError, match="no applicable member"):
        projection.entity_values(entity, {"unknown": 1})
    with pytest.raises(ValueError, match="many occurrence requires a sequence"):
        projection.value_object(entries, "not-a-sequence")
    with pytest.raises(ValueError, match="element requires a mapping"):
        projection.value_object(profile, "not-a-document")

    assert projection.published_row(query, {"profile": {"amount": decimal.Decimal("12.50")}}) == {
        "profile": {"amount": "12.50"}
    }
    assert projection.value_object(profile, None) is None
    label = entity.attribute("label")
    assert label is not None
    assert projection.published_scalar(label, None) is None
    assert projection.value_object(profile, {"future": {"opaque": True}}) == {
        "future": {"opaque": True},
    }
    assert projection.value_object(profile, {"entries": [{"value": "nested"}]}) == {
        "entries": [{"value": "nested"}]
    }
    assert projection.published_value_object(entries, "corrupt") == "corrupt"
    assert projection.published_value_object(profile, "corrupt") == "corrupt"
    with pytest.raises(ValueError, match="element requires a mapping"):
        projection.published_value_object(entries, ["corrupt"])

    unknown_query = deserialize_query(
        {"target": "parallax.compatibility.Missing", "predicate": {"all": {}}}
    )
    with pytest.raises(ValueError, match="no such Entity"):
        projection.published_row(unknown_query, {})
    with pytest.raises(ValueError, match="no such Entity"):
        projection.object_key(ObjectKey(EntityIdentity(None, "Missing"), (("id", 1),)))
    with pytest.raises(ValueError, match="no applicable Attribute"):
        projection.object_key(ObjectKey(entity.identity, (("missing", 1),)))

    narrowed_query = deserialize_query(
        {
            "target": entity.identity.canonical,
            "predicate": {"all": {}},
            "narrowTo": [entity.identity.canonical],
        }
    )
    assert projection.published_row(narrowed_query, {}) == {}

    orders = models.load_models()["orders"]
    order = next(item for item in orders.entities if item.identity.name == "Order")
    order_item = next(item for item in orders.entities if item.identity.name == "OrderItem")
    invalid_narrow = deserialize_query(
        {
            "target": order.identity.canonical,
            "predicate": {"all": {}},
            "narrowTo": [order_item.identity.canonical],
        }
    )
    assert ActualWireProjection(orders).published_row(invalid_narrow, {}) == {}


def test_actual_wire_projection_rejects_unresolved_physical_contributors() -> None:
    model = models.load_models()["document-codec"]
    layout = storage_layout.view(model).tables[0]
    slot = layout.columns[0]

    missing_attribute = cast(
        "storage_layout.TableLayout",
        dataclasses.replace(
            cast("Any", layout),
            columns=(
                dataclasses.replace(
                    slot,
                    contributor=AttributeIdentity(EntityIdentity(None, "Missing"), "id"),
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="no such Entity"):
        ActualWireProjection(model).table_row(missing_attribute, {slot.column.name: 1})

    missing_value_object = cast(
        "storage_layout.TableLayout",
        dataclasses.replace(
            cast("Any", layout),
            columns=(
                dataclasses.replace(
                    slot,
                    contributor=ValueObjectIdentity(EntityIdentity(None, "Missing"), ("payload",)),
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="no such Entity"):
        ActualWireProjection(model).table_row(missing_value_object, {slot.column.name: {}})

    entity = model.entities[0]
    missing_attribute = cast(
        "storage_layout.TableLayout",
        dataclasses.replace(
            cast("Any", layout),
            columns=(
                dataclasses.replace(
                    slot,
                    contributor=AttributeIdentity(entity.identity, "missing"),
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="no Attribute"):
        ActualWireProjection(model).table_row(missing_attribute, {slot.column.name: 1})

    missing_value_object = cast(
        "storage_layout.TableLayout",
        dataclasses.replace(
            cast("Any", layout),
            columns=(
                dataclasses.replace(
                    slot,
                    contributor=ValueObjectIdentity(entity.identity, ("missing",)),
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="no Value Object"):
        ActualWireProjection(model).table_row(missing_value_object, {slot.column.name: {}})

    assert ActualWireProjection(model)._table_row_entity(layout, {}) is entity  # pyright: ignore[reportPrivateUsage]


def test_actual_wire_projection_rejects_a_narrowing_product_with_no_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = models.load_models()["document-codec"]
    entity = model.entities[0]
    real = inheritance.view(model).entity(entity.identity)
    assert real is not None

    class MissingNarrow:
        @staticmethod
        def entity(_identity: object) -> object:
            return real

        @staticmethod
        def position(_identities: object) -> None:
            return None

    def missing_view(_model: object) -> MissingNarrow:
        return MissingNarrow()

    monkeypatch.setattr(inheritance, "view", missing_view)
    query = deserialize_query(
        {
            "target": entity.identity.canonical,
            "predicate": {"all": {}},
            "narrowTo": [entity.identity.canonical],
        }
    )

    with pytest.raises(ValueError, match="narrowing resolves no position"):
        ActualWireProjection(model).published_row(query, {})
