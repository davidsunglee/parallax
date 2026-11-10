"""The production-side oracle for non-Wire observations: the codec arm an actual
selects from accepted Metadata and the refusals a malformed or unowned member
meets.
"""

from __future__ import annotations

import decimal
import uuid

import pytest

from parallax.conformance import models
from parallax.conformance._actual_wire import ActualWireProjection
from parallax.core import inheritance, storage_layout
from parallax.core.base import INFINITY, UsageError
from parallax.core.metamodel import (
    EntityIdentity,
)
from parallax.core.write_plan import ObjectKey
from tests._support.errors import raises_code


def test_run_read_case_wire_renders_managed_row_values() -> None:
    # Production actuals select the codec case from accepted Metadata, never from
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
    with raises_code(UsageError, "wire-encoding-failed"):
        ActualWireProjection(model).scalar(external_id, "123e4567-e89b-12d3-a456-426614174000")


def test_actual_wire_projects_only_the_managed_open_bound_at_an_axis_end() -> None:
    # Production holds the open bound as the managed value; its Wire spelling is
    # this projection's output, never an input it repairs.
    model = models.load_models()["position"]
    (entity,) = model.entities
    valid_end = entity.attribute("validEnd")
    assert valid_end is not None
    projection = ActualWireProjection(model)
    assert projection.scalar(valid_end, INFINITY) == "infinity"
    with raises_code(UsageError, "wire-encoding-failed"):
        projection.scalar(valid_end, "infinity")


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

    with pytest.raises(ValueError, match="no applicable member"):
        projection.entity_values(entity, {"unknown": 1})
    with pytest.raises(ValueError, match="many occurrence requires a sequence"):
        projection.value_object(entries, "not-a-sequence")
    with pytest.raises(ValueError, match="element requires a mapping"):
        projection.value_object(profile, "not-a-document")

    assert projection.value_object(profile, {"amount": decimal.Decimal("12.50")}) == {
        "amount": "12.50"
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
    assert projection.published_value_object(entries, ["corrupt", {"value": "kept"}]) == [
        "corrupt",
        {"value": "kept"},
    ]

    with pytest.raises(ValueError, match="no such Entity"):
        projection.object_key(ObjectKey(EntityIdentity(None, "Missing"), (("id", 1),)))
    with pytest.raises(ValueError, match="no applicable Attribute"):
        projection.object_key(ObjectKey(entity.identity, (("missing", 1),)))


def test_actual_wire_projects_scalar_collections_element_wise_and_keeps_corruption() -> None:
    model = models.load_model(
        models.default_models_dir() / "scalar-collection-layout-twin-columns.yaml"
    )
    projection = ActualWireProjection(model)
    item = EntityIdentity("parallax.compatibility", "CollectionTwinItem")
    entity = model.entity(item)
    assert entity is not None
    amounts = entity.attribute("amounts")
    assert amounts is not None
    parts = entity.value_object("parts")
    assert parts is not None
    detail = entity.value_object("detail")
    assert detail is not None
    view = storage_layout.view(model).entity(item)
    assert view is not None

    assert projection.scalar(amounts, (decimal.Decimal("1.5"),)) == ["1.50"]
    assert projection.published_scalar(amounts, ["1.50", "1.5"]) == ["1.50", "1.5"]
    with pytest.raises(ValueError, match="requires a sequence"):
        projection.scalar(amounts, "1.50")
    row = projection.table_row(view.layout, {"id": 1, "amounts": ["7.00", 7], "tags": "x"})
    assert (row["amounts"], row["tags"], row["flags"]) == (["7.00", 7], "x", None)
    assert projection.value_object(parts, [{"sku": "a", "marks": (2, 2)}]) == [
        {"sku": "a", "marks": [2, 2]}
    ]
    assert projection.published_value_object(detail, {"labels": ["x", 1]}) == {"labels": ["x", 1]}
