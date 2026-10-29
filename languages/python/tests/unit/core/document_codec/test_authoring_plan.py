"""The compiled authoring plan: one member-order pass from authored values to
owned positional cells, shared per shape and per Neutral Type."""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Mapping
from typing import Final, cast

import pytest

from parallax.core.base import (
    INT64,
    STRING,
    TIMESTAMP,
    Decimal,
    FrozenMap,
    NeutralType,
    NeutralTypeMismatch,
    ScalarConverter,
    typed_converter,
)
from parallax.core.document_codec._plan import (
    BORROWED_DOCUMENTS,
    MAPPING_DOCUMENTS,
    AuthoringCatalog,
    AuthoringLane,
    AuthoringPlan,
    AuthoringRefusal,
    PreparedAuthoringRow,
    RootPolicy,
)
from parallax.core.metamodel import (
    AuthoringViolation,
    MemberShape,
    Multiplicity,
    OccurrenceDefinition,
    ScalarDefinition,
)
from parallax.core.wire import WireDecodingError
from parallax.core.wire._codec import wire_converter

_ABSENT: Final = object()
_GEO = MemberShape(
    (
        ScalarDefinition("lat", Decimal(8, 5), False),
        ScalarDefinition("note", STRING, True),
    )
)
_ADDRESS = MemberShape(
    (
        ScalarDefinition("city", STRING, False),
        ScalarDefinition("lines", STRING, False, Multiplicity.MANY),
        OccurrenceDefinition("geo", Multiplicity.ONE, True, _GEO),
    )
)
_ROW = MemberShape(
    (
        ScalarDefinition("id", INT64, False),
        ScalarDefinition("name", STRING, True),
        ScalarDefinition("at", TIMESTAMP, True),
        ScalarDefinition("tags", STRING, False, Multiplicity.MANY),
        OccurrenceDefinition("home", Multiplicity.ONE, True, _ADDRESS),
        OccurrenceDefinition("past", Multiplicity.MANY, False, _ADDRESS),
    )
)
_REQUIRED: Final = 0b1


_TYPED: Final = 0
_WIRE: Final = 1
_LANES: Final = (
    AuthoringLane(typed_converter, BORROWED_DOCUMENTS),
    AuthoringLane(wire_converter, MAPPING_DOCUMENTS),
)


def _plan(shape: MemberShape = _ROW) -> AuthoringPlan:
    return AuthoringCatalog(_LANES, absent=_ABSENT).plan(shape)


def _row(
    lane: int, raws: tuple[object, ...], *, omitted: int = 0, root: RootPolicy | None = None
) -> PreparedAuthoringRow:
    return _plan().complete_row(raws, lane=lane, required=_REQUIRED, omitted=omitted, root=root)


def _refusal(lane: int, raws: tuple[object, ...]) -> AuthoringRefusal:
    with pytest.raises(AuthoringRefusal) as refused:
        _row(lane, raws)
    return refused.value


def test_a_complete_row_packs_its_stated_cells_in_member_order() -> None:
    at = dt.datetime(2026, 1, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))

    row = _row(_TYPED, (7, None, at, _ABSENT, _ABSENT, _ABSENT))

    assert row.cells == (7, None, dt.datetime(2026, 1, 1, tzinfo=dt.UTC), (), ())
    assert row.presence == 0b101111


def test_an_omitted_member_is_unstated_whatever_its_value() -> None:
    row = _row(_TYPED, (7, "Ada", _ABSENT, ("a",), _ABSENT, ()), omitted=0b10)

    assert row.cells == (7, ("a",), ())
    assert row.presence == 0b101001


def test_a_nested_occurrence_keeps_the_full_width_read_form() -> None:
    home = {"city": "Paris", "geo": {"lat": "48.85661"}}

    row = _row(_WIRE, (7, _ABSENT, _ABSENT, _ABSENT, home, [home]))

    nested = ("Paris", (), (decimal.Decimal("48.85661"), _ABSENT))
    assert row.cells == (7, (), nested, (nested,))
    assert row.presence == 0b111001


def test_both_lanes_author_the_same_cells_from_their_own_carriers() -> None:
    typed = _row(_TYPED, (7, "Ada", _ABSENT, ("a", "b"), {"city": "Oslo", "lines": ("x",)}, ()))
    wire = _row(_WIRE, (7, "Ada", _ABSENT, ["a", "b"], {"city": "Oslo", "lines": ["x"]}, []))

    assert typed == wire


def test_an_unchanged_nested_document_is_its_reader_tuple() -> None:
    plan = _plan(_ADDRESS)
    values = ("Oslo", ("x",), None)

    class _Reader:
        def document(
            self, source: object, shape: MemberShape, absent: object, /
        ) -> tuple[object, ...] | None:
            return values

        def elements(self, source: object, /) -> None:
            return None

        def scalar_elements(self, source: object, /) -> tuple[object, ...]:
            return ("x",)

    reading = AuthoringCatalog((AuthoringLane(typed_converter, _Reader()),), absent=_ABSENT).plan(
        _ADDRESS
    )

    assert plan.document({"city": "Oslo", "lines": ("x",), "geo": None}, _WIRE) == values
    assert reading.document(object(), _TYPED) == values


@pytest.mark.parametrize(
    ("raws", "position", "violation"),
    [
        (
            (_ABSENT, 2**70, _ABSENT, _ABSENT, _ABSENT, _ABSENT),
            0,
            AuthoringViolation("", "attribute-missing"),
        ),
        (
            (2**70, None, _ABSENT, _ABSENT, _ABSENT, _ABSENT),
            0,
            AuthoringViolation("", "type-mismatch", 2**70, INT64),
        ),
        (
            (7, None, _ABSENT, None, _ABSENT, _ABSENT),
            3,
            AuthoringViolation("", "attribute-missing"),
        ),
        (
            (7, 3, _ABSENT, ("a", None), _ABSENT, _ABSENT),
            1,
            AuthoringViolation("", "type-mismatch", 3, STRING),
        ),
        (
            (7, None, _ABSENT, ("a", None), _ABSENT, _ABSENT),
            3,
            AuthoringViolation("[1]", "type-mismatch", None, STRING),
        ),
        (
            (7, None, _ABSENT, ["a"], _ABSENT, _ABSENT),
            3,
            AuthoringViolation("", "not-a-list", ["a"]),
        ),
        (
            (7, None, _ABSENT, _ABSENT, {"lines": ("x",)}, _ABSENT),
            4,
            AuthoringViolation("city", "attribute-missing"),
        ),
        (
            (7, None, _ABSENT, _ABSENT, _ABSENT, ({"city": "x", "geo": {"note": None}},)),
            5,
            AuthoringViolation("[0].geo.lat", "attribute-missing"),
        ),
        (
            (7, None, _ABSENT, _ABSENT, 5, _ABSENT),
            4,
            AuthoringViolation("", "not-a-document", 5),
        ),
    ],
)
def test_the_first_refused_member_in_member_order_is_reported(
    raws: tuple[object, ...], position: int, violation: AuthoringViolation
) -> None:
    refused = _refusal(_TYPED, raws)

    assert (refused.position, refused.violation) == (position, violation)


def test_a_typed_mismatch_reports_the_converted_value() -> None:
    refused = _refusal(
        _TYPED,
        (7, None, _ABSENT, _ABSENT, {"city": "x", "geo": {"lat": decimal.Decimal(1) / 3}}, ()),
    )

    assert refused.violation.path == "geo.lat"
    assert isinstance(refused.cause, NeutralTypeMismatch)


def test_a_wire_mismatch_carries_its_decoding_failure() -> None:
    refused = _refusal(_WIRE, (7, None, _ABSENT, ["a", 3], _ABSENT, _ABSENT))

    assert refused.violation == AuthoringViolation("[1]", "type-mismatch", 3, STRING)
    assert isinstance(refused.cause, WireDecodingError)


def test_a_root_policy_authors_only_a_top_level_scalar_marker() -> None:
    marked: list[tuple[int, Mapping[str, object]]] = []

    def root(position: int, marker: Mapping[str, object]) -> object:
        marked.append((position, marker))
        return "planned"

    row = _row(
        _WIRE, ({"computed": "maxPlusOne"}, _ABSENT, _ABSENT, _ABSENT, _ABSENT, _ABSENT), root=root
    )

    assert row.cells == ("planned", (), ())
    assert marked == [(0, {"computed": "maxPlusOne"})]
    with pytest.raises(AuthoringRefusal):
        _row(
            _WIRE, (7, _ABSENT, _ABSENT, [{"computed": "maxPlusOne"}], _ABSENT, _ABSENT), root=root
        )


def test_a_row_short_of_its_shape_is_refused() -> None:
    with pytest.raises(ValueError, match="one value per member"):
        _row(_TYPED, (7,))


def test_a_catalog_compiles_one_plan_per_shape_and_one_converter_per_type() -> None:
    compiled: list[NeutralType] = []

    def counted(declared: NeutralType) -> ScalarConverter:
        compiled.append(declared)
        return typed_converter(declared)

    catalog = AuthoringCatalog((AuthoringLane(counted, BORROWED_DOCUMENTS),), absent=_ABSENT)
    plan = catalog.plan(_ROW)

    assert catalog.plan(_ROW) is plan
    assert catalog.plan(_ADDRESS) is catalog.plan(_ADDRESS)
    assert sorted(map(repr, compiled)) == sorted(
        map(repr, (INT64, STRING, TIMESTAMP, Decimal(8, 5)))
    )


def test_owned_json_content_is_frozen_once() -> None:
    from parallax.core.base import JSON

    shape = MemberShape((ScalarDefinition("doc", JSON, False),))
    (cell,) = _plan(shape).complete_row(({"a": [1]},), lane=_WIRE, required=0b1).cells

    assert cell == FrozenMap({"a": (1,)})
    assert type(cell) is FrozenMap


def test_authored_values_read_a_payload_in_member_order() -> None:
    assert _plan().authored_values({"name": "Ada", "id": 7}) == (
        7,
        "Ada",
        _ABSENT,
        _ABSENT,
        _ABSENT,
        _ABSENT,
    )


@pytest.mark.parametrize(
    ("raws", "position", "violation"),
    [
        ((7, None, _ABSENT, _ABSENT, "not a document", _ABSENT), 4, "not-a-document"),
        ((7, None, _ABSENT, _ABSENT, _ABSENT, "not a list"), 5, "not-a-list"),
        ((7, None, _ABSENT, _ABSENT, {"city": "x", "lines": [None]}, _ABSENT), 4, "type-mismatch"),
    ],
)
def test_a_wire_document_or_collection_of_the_wrong_carrier_is_refused(
    raws: tuple[object, ...], position: int, violation: str
) -> None:
    refused = _refusal(_WIRE, raws)

    assert (refused.position, refused.violation.reason) == (position, violation)


def test_a_nested_collection_element_path_joins_its_member() -> None:
    refused = _refusal(_WIRE, (7, None, _ABSENT, _ABSENT, {"city": "x", "lines": [3]}, _ABSENT))

    assert refused.violation.path == "lines[0]"


def test_a_borrowed_value_object_authors_through_its_hooks() -> None:
    class _Borrowed:
        def __parallax_authoring_names__(self) -> tuple[str, ...]:
            return ("city", "geo")

        def __parallax_authoring_member__(self, name: str) -> object:
            return {"city": "Oslo", "geo": None}[name]

    row = _row(_TYPED, (7, _ABSENT, _ABSENT, _ABSENT, _Borrowed(), ()))

    assert row.cells == (7, (), ("Oslo", (), None), ())


def test_a_nested_required_member_stated_null_is_missing() -> None:
    refused = _refusal(_WIRE, (7, None, _ABSENT, _ABSENT, {"city": None}, _ABSENT))

    assert refused.violation == AuthoringViolation("city", "attribute-missing")


def test_a_partial_row_judges_in_its_stated_order_and_packs_in_member_order() -> None:
    judged: list[int] = []

    row = _plan().partial_row(
        ((3, ["a"]), (0, 7), (1, None)),
        lane=_WIRE,
        check=lambda position, _raw: judged.append(position),
    )

    assert judged == [3, 0, 1]
    assert row.cells == (7, None, ("a",))
    assert row.presence == 0b1011


def test_a_partial_row_refuses_its_first_refused_member_in_stated_order() -> None:
    with pytest.raises(AuthoringRefusal) as refused:
        _plan().partial_row(((2, "not-an-instant"), (0, "seven")), lane=_TYPED)

    assert refused.value.position == 2


def test_a_partial_row_states_no_member_it_omits_and_never_a_null_collection() -> None:
    assert _plan().partial_row((), lane=_TYPED) == PreparedAuthoringRow((), 0)
    with pytest.raises(AuthoringRefusal) as refused:
        _plan().partial_row(((3, None),), lane=_TYPED)

    assert refused.value.violation == AuthoringViolation("", "attribute-missing")


def test_an_addressing_position_spells_its_marker_as_an_ordinary_value() -> None:
    marker = {"computed": "maxPlusOne"}

    planned = _plan().partial_row(((1, marker),), lane=_WIRE, root=lambda _p, _m: "planned")
    with pytest.raises(AuthoringRefusal) as refused:
        _plan().partial_row(
            ((0, marker),), lane=_WIRE, root=lambda _p, _m: "planned", addressing=0b1
        )

    assert planned.cells == ("planned",)
    assert isinstance(refused.value.cause, WireDecodingError)


def test_a_complete_row_states_an_unstated_nulled_member_as_null() -> None:
    row = _plan().complete_row(
        (7, _ABSENT, _ABSENT, _ABSENT, _ABSENT, _ABSENT), lane=_TYPED, required=0, nulled=0b10110
    )

    assert row.cells == (7, None, None, (), None, ())
    assert row.presence == 0b111111


def test_a_complete_row_leaves_an_unstated_excluded_member_unstated() -> None:
    row = _plan().complete_row(
        (7, _ABSENT, _ABSENT, _ABSENT, _ABSENT, _ABSENT),
        lane=_TYPED,
        required=0,
        nulled=0b10,
        excluded=0b1010,
    )

    assert row.cells == (7, ())
    assert row.presence == 0b100001


def test_a_complete_row_judges_a_stated_member_by_its_check_before_its_value() -> None:
    def refuse_name(position: int, _raw: object) -> None:
        if position == 1:
            raise LookupError(position)

    with pytest.raises(LookupError):
        _plan().complete_row(
            (7, "Ada", "not-an-instant", _ABSENT, _ABSENT, _ABSENT),
            lane=_TYPED,
            required=0,
            check=refuse_name,
        )


def test_validation_only_mode_reports_the_first_violation_and_builds_nothing() -> None:
    catalog = AuthoringCatalog(_LANES, absent=_ABSENT)
    home = cast("OccurrenceDefinition", _ROW.members[4])
    tags = cast("ScalarDefinition", _ROW.members[3])

    assert catalog.violation(home, {"city": "Paris"}, lane=_WIRE) is None
    assert catalog.plan(home.shape).document({"city": "Paris"}, _WIRE, produce=False) is None
    assert catalog.violation(home, {"lines": ["a"]}, lane=_WIRE) == AuthoringViolation(
        "city", "attribute-missing"
    )
    assert catalog.violation(tags, ("a", 2), lane=_TYPED) == AuthoringViolation(
        "[1]", "type-mismatch", 2, STRING
    )
    assert catalog.violation(_ROW.members[0], True, lane=_TYPED) == AuthoringViolation(
        "", "type-mismatch", True, INT64
    )


def test_a_lane_converts_one_exact_definition_apart_from_its_neutral_type() -> None:
    twin = MemberShape((ScalarDefinition("label", STRING, True),))
    shape = MemberShape(
        (
            ScalarDefinition("label", STRING, True),
            OccurrenceDefinition("twin", Multiplicity.ONE, True, twin),
        )
    )
    top = shape.members[0]
    assert top == twin.members[0]

    plan = AuthoringPlan.compile(
        shape,
        wire_converter,
        absent=_ABSENT,
        definition_converter=lambda member: (lambda _v: "own") if member is top else None,
    )
    row = plan.complete_row(("a", {"label": "b"}), lane=0, required=0)

    assert row.cells == ("own", ("b",))
