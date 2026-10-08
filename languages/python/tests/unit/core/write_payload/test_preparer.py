"""The write payload preparer over real layouts and the real codec.

What a Write Row or an assignment set persists is assembled here and nowhere
else: each member at the slot its Table Layout gives it, the shared Structured
Column composed from a new lineage's members or patched at a successor's executed
assignments alone, and a revising step's document paths as ordered prepared
patches. Its two comparisons are graded against the persisted state they claim
to describe.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from typing import cast

import pytest

from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INFINITY, JSON, FrozenMap, NeutralType
from parallax.core.document_codec import PreparedPatch
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    Table,
    ValueObjectIdentity,
)
from parallax.core.storage_layout import RelationalDocument
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import PredecessorRow, WritePlanningError
from parallax.core.write_plan.payload import PatchedDocument, RowPayload
from parallax.core.write_plan.steps import (
    MAX_PLUS_ONE,
    NEW_LINEAGE,
    CarriedFrom,
    ChangedFrom,
    PlannedAssignments,
    PlannedRow,
    RowOrigin,
    WriteRow,
)
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._document_layout_support import PERSON, columns_model, document_model
from tests.unit._metamodel_support import Declaration, attribute, key, source
from tests.unit._metamodel_support import identity as entity_identity

_EXPEDITIONS: Metamodel = corpus_model("document-layout-restored-member")
_EXPEDITION = EntityIdentity("parallax.compatibility", "Expedition")
_ID, _TITLE, _IN, _OUT = (
    AttributeIdentity(_EXPEDITION, name) for name in ("id", "title", "txStart", "txEnd")
)
_ROUTE = ValueObjectIdentity(_EXPEDITION, ("route",))
_JAN, _JUN = (dt.datetime(2026, month, 1, tzinfo=dt.UTC) for month in (1, 6))

_STORED: Mapping[str, object] = FrozenMap(
    {
        "title": "Coastal Run",
        "charterCode": "NB-118",
        "route": {"name": "Coastal", "sealNumber": "S-4021", "stops": [{"port": "Oslo"}]},
    }
)
"""A stored document holding a key no member declares at its root and another
inside the `route` occurrence."""

_ROUTE_VALUE: Mapping[str, object] = {"name": "Coastal", "stops": ({"port": "Oslo"},)}


def _axis_names() -> tuple[str, str]:
    entity = _EXPEDITIONS.entity(_EXPEDITION)
    assert entity is not None
    (axis,) = entity.declared_as_of_axes
    return axis.start_attribute.name, axis.end_attribute.name


def _predecessor() -> PredecessorRow:
    start, end = _axis_names()
    return PredecessorRow(
        {"id": 7, "title": "Coastal Run", "route": _ROUTE_VALUE, start: _JAN, end: INFINITY},
        document=_STORED,
    )


def _successor(
    origin: RowOrigin,
    executed: Mapping[AttributeIdentity | ValueObjectIdentity, object] = {},
    *,
    title: str = "Coastal Run",
    in_z: dt.datetime = _JUN,
) -> WriteRow:
    attributes: dict[AttributeIdentity, object] = {
        _ID: 7,
        _TITLE: title,
        _IN: in_z,
        _OUT: INFINITY,
    }
    value_objects: dict[ValueObjectIdentity, object] = {_ROUTE: _ROUTE_VALUE}
    for identity, value in executed.items():
        if isinstance(identity, AttributeIdentity):
            attributes[identity] = value
        else:
            value_objects[identity] = value
    row = PlannedRow(attributes=attributes, value_objects=value_objects)
    return WriteRow(row=row, origin=origin, executed=tuple(executed))


def _document(payload: RowPayload) -> Mapping[str, object]:
    (document,) = (
        value
        for contributor, value in zip(payload.contributors, payload.values, strict=True)
        if isinstance(contributor, RelationalDocument)
    )
    return cast("Mapping[str, object]", document)


def test_a_row_stores_each_member_at_its_slot_in_table_layout_order() -> None:
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    write_row = _successor(NEW_LINEAGE)

    payload = preparer.row(_EXPEDITION, write_row)

    assert payload.source is write_row
    assert list(payload.contributors) == [
        _ID,
        _IN,
        _OUT,
        RelationalDocument(_EXPEDITION),
    ]
    assert _document(payload) == {"title": "Coastal Run", "route": _ROUTE_VALUE}


def test_a_changed_row_patches_only_what_it_executes_and_keeps_every_other_key() -> None:
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    changed = _successor(
        ChangedFrom(_predecessor()), {_TITLE: "Coastal Return"}, title="Coastal Return"
    )

    document = _document(preparer.row(_EXPEDITION, changed))

    assert document == {**_STORED, "title": "Coastal Return"}
    assert document["route"] is _STORED["route"]


def test_an_executed_equal_occurrence_replaces_its_stored_subtree() -> None:
    # The route assignment equals the declared members already stored, yet it is
    # executed, so it is written whole and the undeclared key inside the stored
    # subtree is gone, while the root key outside it rides forward.
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    changed = _successor(
        ChangedFrom(_predecessor()),
        {_TITLE: "Coastal Return", _ROUTE: _ROUTE_VALUE},
        title="Coastal Return",
    )

    document = _document(preparer.row(_EXPEDITION, changed))

    assert document == {
        "title": "Coastal Return",
        "charterCode": "NB-118",
        "route": {"name": "Coastal", "stops": [{"port": "Oslo"}]},
    }


def test_a_carried_row_stores_its_predecessors_document_itself() -> None:
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    assert _document(preparer.row(_EXPEDITION, _successor(CarriedFrom(_predecessor())))) is _STORED


def test_a_changed_row_executing_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="a changed Write Row names the members it executes"):
        _successor(ChangedFrom(_predecessor()), title="Changed")


def test_an_assignment_set_patches_only_its_paths_with_prepared_values() -> None:
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    assignments = PlannedAssignments(
        attributes={_TITLE: None}, value_objects={_ROUTE: _ROUTE_VALUE}
    )

    payload = preparer.assignments(_EXPEDITION, assignments)

    assert payload.assignments is assignments
    (contributor,) = payload.contributors
    (patched,) = payload.values
    assert contributor == RelationalDocument(_EXPEDITION)
    assert isinstance(patched, PatchedDocument)
    title, route = patched.patches
    assert title == PreparedPatch(("title",), None, _title_type())
    assert (route.path, route.leaf, route.removes) == (("route",), None, False)
    assert route.value == {"name": "Coastal", "stops": [{"port": "Oslo"}]}


def _title_type() -> NeutralType:
    entity = _EXPEDITIONS.entity(_EXPEDITION)
    assert entity is not None
    attribute = entity.attribute("title")
    assert attribute is not None
    return attribute.type


def test_a_columns_row_encodes_each_occurrence_into_its_own_column() -> None:
    columns = columns_model()
    address = ValueObjectIdentity(PERSON, ("address",))
    tags = ValueObjectIdentity(PERSON, ("tags",))
    write_row = WriteRow(
        row=PlannedRow(
            attributes={AttributeIdentity(PERSON, "id"): 1},
            value_objects={address: {"city": "Oslo", "geo": None}},
        ),
        origin=NEW_LINEAGE,
    )

    payload = LayoutPayloadPreparer(columns).row(PERSON, write_row)

    cells = dict(zip(payload.contributors, payload.values, strict=True))
    assert cells[address] == {"city": "Oslo", "geo": None}
    assert type(cells[address]) is FrozenMap
    assert cells[tags] == ()


def test_the_document_twin_stores_one_shared_document_instead() -> None:
    document = document_model()
    write_row = WriteRow(
        row=PlannedRow(
            attributes={AttributeIdentity(PERSON, "id"): 1},
            value_objects={ValueObjectIdentity(PERSON, ("address",)): {"city": "Oslo"}},
        ),
        origin=NEW_LINEAGE,
    )

    payload = LayoutPayloadPreparer(document).row(PERSON, write_row)

    assert [type(contributor).__name__ for contributor in payload.contributors] == [
        "AttributeIdentity",
        "RelationalDocument",
    ]
    assert payload.values[1] == {"address": {"city": "Oslo"}, "tags": ()}


def test_a_target_with_no_effective_table_is_refused() -> None:
    with pytest.raises(WritePlanningError, match="write target has no effective table"):
        LayoutPayloadPreparer(_EXPEDITIONS).row(
            EntityIdentity("parallax.compatibility", "Nowhere"), _successor(NEW_LINEAGE)
        )


# --------------------------------------------------------------------------- #
# Persisted-state comparison                                                   #
# --------------------------------------------------------------------------- #
def test_rows_persisting_the_same_state_outside_their_interval_are_equal() -> None:
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    left = preparer.row(_EXPEDITION, _successor(NEW_LINEAGE, in_z=_JAN))
    right = preparer.row(_EXPEDITION, _successor(NEW_LINEAGE, in_z=_JUN))

    assert preparer.equal_non_interval(left, right)


def test_unknown_document_content_alone_makes_rows_unequal() -> None:
    # Equal declared members, but the carried row's document still holds the
    # stored keys no member declares: coalescing it with a fresh row would lose
    # them.
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    retained = preparer.row(_EXPEDITION, _successor(CarriedFrom(_predecessor())))
    fresh = preparer.row(_EXPEDITION, _successor(NEW_LINEAGE))

    assert not preparer.equal_non_interval(retained, fresh)
    assert preparer.equal_non_interval(retained, retained)


def test_a_row_of_unknown_complete_state_equals_nothing() -> None:
    positions = corpus_model("position")
    entity = EntityIdentity("parallax.compatibility", "Position")
    preparer = LayoutPayloadPreparer(positions)
    allocated = _position_row(entity, key=MAX_PLUS_ONE)
    incomplete = WriteRow(
        row=PlannedRow(attributes={AttributeIdentity(entity, "id"): 1}), origin=NEW_LINEAGE
    )

    for row in (allocated, incomplete):
        payload = preparer.row(entity, row)
        assert not preparer.equal_non_interval(payload, payload)


def _position_row(
    entity: EntityIdentity,
    *,
    key: object = 1,
    account: object = "A",
    value: object = Decimal("100.00"),
    start: dt.datetime = _JAN,
) -> WriteRow:
    attributes = {
        AttributeIdentity(entity, "id"): key,
        AttributeIdentity(entity, "acctNum"): account,
        AttributeIdentity(entity, "value"): value,
        AttributeIdentity(entity, "validStart"): start,
        AttributeIdentity(entity, "validEnd"): INFINITY,
        AttributeIdentity(entity, "txStart"): _JUN,
        AttributeIdentity(entity, "txEnd"): INFINITY,
    }
    return WriteRow(row=PlannedRow(attributes=attributes), origin=NEW_LINEAGE)


@pytest.mark.parametrize(
    ("changes", "proven"),
    [
        ({"value": Decimal("150.00")}, True),
        ({"account": None}, True),
        ({"value": Decimal("100.0")}, False),
        ({"start": _JUN}, False),
        ({}, False),
    ],
    ids=["value", "null", "equal-spelling", "interval-only", "identical"],
)
def test_cheap_inequality_is_proven_only_by_a_differing_stored_scalar(
    changes: dict[str, object], *, proven: bool
) -> None:
    positions = corpus_model("position")
    entity = EntityIdentity("parallax.compatibility", "Position")
    preparer = LayoutPayloadPreparer(positions)
    left = _position_row(entity)
    right = _position_row(entity, **changes)  # pyright: ignore[reportArgumentType]

    assert preparer.proven_unequal_non_interval(entity, left, right) is proven
    assert preparer.proven_unequal_non_interval(entity, right, left) is proven
    if not proven:
        assert preparer.equal_non_interval(preparer.row(entity, left), preparer.row(entity, right))


def test_cheap_inequality_decides_nothing_about_documents_or_generated_values() -> None:
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    retained = _successor(CarriedFrom(_predecessor()))
    rebuilt = _successor(NEW_LINEAGE, {_ROUTE: {"name": "Elsewhere", "stops": ()}})

    assert not preparer.proven_unequal_non_interval(_EXPEDITION, retained, rebuilt)
    assert not preparer.equal_non_interval(
        preparer.row(_EXPEDITION, retained), preparer.row(_EXPEDITION, rebuilt)
    )
    positions = corpus_model("position")
    entity = EntityIdentity("parallax.compatibility", "Position")
    allocated = _position_row(entity, key=MAX_PLUS_ONE, account="B")
    assert LayoutPayloadPreparer(positions).proven_unequal_non_interval(
        entity, allocated, _position_row(entity)
    )
    assert not LayoutPayloadPreparer(positions).proven_unequal_non_interval(
        entity, _position_row(entity, key=MAX_PLUS_ONE), _position_row(entity)
    )


def test_rows_of_two_entities_or_misaligned_cells_are_never_equal() -> None:
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    payload = preparer.row(_EXPEDITION, _successor(NEW_LINEAGE))
    elsewhere = RowPayload(
        entity=EntityIdentity("parallax.compatibility", "Nowhere"),
        source=payload.source,
        contributors=payload.contributors,
        values=payload.values,
    )
    swapped = RowPayload(
        entity=_EXPEDITION,
        source=payload.source,
        contributors=(payload.contributors[1], payload.contributors[0], *payload.contributors[2:]),
        values=(payload.values[1], payload.values[0], *payload.values[2:]),
    )

    assert not preparer.equal_non_interval(payload, elsewhere)
    assert not preparer.equal_non_interval(payload, swapped)


def test_a_row_executing_only_directly_stored_members_keeps_its_retained_document() -> None:
    # Executed members stored in Columns of their own leave the shared document
    # nothing to patch, so the retained document is stored as it was.
    preparer = LayoutPayloadPreparer(_EXPEDITIONS)
    keyed = _successor(ChangedFrom(_predecessor()), {_ID: 7})

    assert _document(preparer.row(_EXPEDITION, keyed)) is _STORED


def test_a_json_member_compares_as_a_persisted_document() -> None:
    entity = entity_identity("Ledger")
    model = form_metamodel(
        source(
            Declaration(
                identity=entity,
                container=Table("ledger"),
                attributes=(key(entity), attribute(entity, "entries", type=JSON)),
            )
        )
    )
    preparer = LayoutPayloadPreparer(model)
    entries = AttributeIdentity(entity, "entries")

    def row(value: object) -> WriteRow:
        return WriteRow(
            row=PlannedRow(attributes={AttributeIdentity(entity, "id"): 1, entries: value}),
            origin=NEW_LINEAGE,
        )

    same, respelled, other = row({"a": [1]}), row({"a": [1.0]}), row({"a": [True]})
    assert not preparer.proven_unequal_non_interval(entity, same, respelled)
    assert preparer.proven_unequal_non_interval(entity, same, other)
    assert preparer.equal_non_interval(preparer.row(entity, same), preparer.row(entity, respelled))
    assert not preparer.equal_non_interval(preparer.row(entity, same), preparer.row(entity, other))


def test_a_subtypes_rows_store_and_compare_its_discriminator() -> None:
    vehicles = corpus_model("vehicle")
    car = EntityIdentity("parallax.compatibility", "Car")
    vehicle = EntityIdentity("parallax.compatibility", "Vehicle")
    write_row = WriteRow(
        row=PlannedRow(
            attributes={
                AttributeIdentity(vehicle, "id"): 1,
                AttributeIdentity(vehicle, "name"): "Coupe",
                AttributeIdentity(vehicle, "version"): 1,
                AttributeIdentity(car, "doors"): 2,
            }
        ),
        origin=NEW_LINEAGE,
    )
    preparer = LayoutPayloadPreparer(vehicles)

    payload = preparer.row(car, write_row)

    assert "car" in payload.values
    assert len(payload.contributors) == 5
    assert preparer.equal_non_interval(payload, preparer.row(car, write_row))
