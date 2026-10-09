"""m-storage-layout: a scalar collection's physical residence under each layout.

Under Columns a top-level collection keeps its Attribute Identity as contributor
and its Direct Column placement, but its slot joins the document tier because it
holds a structured document. Under Document it is one more path in the shared
Structured Column. Its nested collections ride inside their occurrence's
document either way, with no slot or segment of their own.
"""

from __future__ import annotations

from parallax.conformance import models
from parallax.core import storage_layout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.storage_layout import ColumnTier, DirectColumn, DocumentPath

_ITEM = EntityIdentity("parallax.compatibility", "CollectionTwinItem")
_COLUMNS = models.load_model(
    models.default_models_dir() / "scalar-collection-layout-twin-columns.yaml"
)
_DOCUMENT = models.load_model(
    models.default_models_dir() / "scalar-collection-layout-twin-document.yaml"
)


def _layout(model: Metamodel) -> storage_layout.TableLayout:
    view = storage_layout.view(model).entity(_ITEM)
    assert view is not None
    return view.layout


def test_a_columns_collection_owns_a_document_tier_slot_over_its_own_column() -> None:
    layout = _layout(_COLUMNS)
    tags = AttributeIdentity(_ITEM, "tags")

    slot = layout.contribution(tags)
    assert slot is not None
    assert (slot.column.name, slot.tier, slot.effective_nullable) == (
        "tags",
        ColumnTier.DOCUMENT,
        False,
    )
    assert layout.placement(tags) == DirectColumn(slot)
    assert [item.tier for item in layout.columns] == [
        ColumnTier.IDENTITY,
        *[ColumnTier.DOCUMENT] * 14,
    ]


def test_a_document_collection_is_one_path_in_the_shared_structured_column() -> None:
    layout = _layout(_DOCUMENT)
    placement = layout.placement(AttributeIdentity(_ITEM, "tags"))

    assert isinstance(placement, DocumentPath)
    assert placement.path == ("tags",)
    assert [slot.column.name for slot in layout.columns] == ["id", "payload"]


def test_a_nested_collection_rides_inside_its_occurrences_document() -> None:
    parts = ValueObjectIdentity(_ITEM, ("parts",))
    marks = ValueObjectAttributeIdentity(parts, "marks")

    columns = _layout(_COLUMNS).placement(marks)
    document = _layout(_DOCUMENT).placement(marks)

    assert isinstance(columns, DocumentPath)
    assert (columns.slot.column.name, columns.path) == ("parts", ("marks",))
    assert isinstance(document, DocumentPath)
    assert (document.slot.column.name, document.path) == ("payload", ("parts", "marks"))
