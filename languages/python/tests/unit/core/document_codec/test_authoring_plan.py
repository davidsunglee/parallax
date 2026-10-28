"""The compiled authoring plan: one member-order pass from authored values to
owned positional cells, shared per shape and per Neutral Type."""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Mapping
from typing import Final

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
    AuthoringPlan,
    AuthoringRefusal,
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


def _typed() -> AuthoringPlan:
    return AuthoringCatalog(typed_converter, BORROWED_DOCUMENTS, absent=_ABSENT).plan(_ROW)


def _wire() -> AuthoringPlan:
    return AuthoringCatalog(wire_converter, MAPPING_DOCUMENTS, absent=_ABSENT).plan(_ROW)


def _refusal(plan: AuthoringPlan, raws: tuple[object, ...]) -> AuthoringRefusal:
    with pytest.raises(AuthoringRefusal) as refused:
        plan.complete_row(raws, required=_REQUIRED)
    return refused.value


def test_a_complete_row_packs_its_stated_cells_in_member_order() -> None:
    at = dt.datetime(2026, 1, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))

    row = _typed().complete_row((7, None, at, _ABSENT, _ABSENT, _ABSENT), required=_REQUIRED)

    assert row.cells == (7, None, dt.datetime(2026, 1, 1, tzinfo=dt.UTC), (), ())
    assert row.presence == 0b101111


def test_an_omitted_member_is_unstated_whatever_its_value() -> None:
    row = _typed().complete_row(
        (7, "Ada", _ABSENT, ("a",), _ABSENT, ()), required=_REQUIRED, omitted=0b10
    )

    assert row.cells == (7, ("a",), ())
    assert row.presence == 0b101001


def test_a_nested_occurrence_keeps_the_full_width_read_form() -> None:
    home = {"city": "Paris", "geo": {"lat": "48.85661"}}

    row = _wire().complete_row((7, _ABSENT, _ABSENT, _ABSENT, home, [home]), required=_REQUIRED)

    nested = ("Paris", (), (decimal.Decimal("48.85661"), _ABSENT))
    assert row.cells == (7, (), nested, (nested,))
    assert row.presence == 0b111001


def test_both_lanes_author_the_same_cells_from_their_own_carriers() -> None:
    typed = _typed().complete_row(
        (7, "Ada", _ABSENT, ("a", "b"), {"city": "Oslo", "lines": ("x",)}, ()),
        required=_REQUIRED,
    )
    wire = _wire().complete_row(
        (7, "Ada", _ABSENT, ["a", "b"], {"city": "Oslo", "lines": ["x"]}, []),
        required=_REQUIRED,
    )

    assert typed == wire


def test_an_unchanged_nested_document_is_its_reader_tuple() -> None:
    plan = AuthoringCatalog(typed_converter, MAPPING_DOCUMENTS, absent=_ABSENT).plan(_ADDRESS)
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

    reading = AuthoringCatalog(typed_converter, _Reader(), absent=_ABSENT).plan(_ADDRESS)

    assert plan.document({"city": "Oslo", "lines": ("x",), "geo": None}) == values
    assert reading.document(object()) == values


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
    refused = _refusal(_typed(), raws)

    assert (refused.position, refused.violation) == (position, violation)


def test_a_typed_mismatch_reports_the_converted_value() -> None:
    refused = _refusal(
        _typed(),
        (7, None, _ABSENT, _ABSENT, {"city": "x", "geo": {"lat": decimal.Decimal(1) / 3}}, ()),
    )

    assert refused.violation.path == "geo.lat"
    assert isinstance(refused.cause, NeutralTypeMismatch)


def test_a_wire_mismatch_carries_its_decoding_failure() -> None:
    refused = _refusal(_wire(), (7, None, _ABSENT, ["a", 3], _ABSENT, _ABSENT))

    assert refused.violation == AuthoringViolation("[1]", "type-mismatch", 3, STRING)
    assert isinstance(refused.cause, WireDecodingError)


def test_a_root_policy_authors_only_a_top_level_scalar_marker() -> None:
    marked: list[tuple[int, Mapping[str, object]]] = []

    def root(position: int, marker: Mapping[str, object]) -> object:
        marked.append((position, marker))
        return "planned"

    row = _wire().complete_row(
        ({"computed": "maxPlusOne"}, _ABSENT, _ABSENT, _ABSENT, _ABSENT, _ABSENT),
        required=_REQUIRED,
        root=root,
    )

    assert row.cells == ("planned", (), ())
    assert marked == [(0, {"computed": "maxPlusOne"})]
    with pytest.raises(AuthoringRefusal):
        _wire().complete_row(
            (7, _ABSENT, _ABSENT, [{"computed": "maxPlusOne"}], _ABSENT, _ABSENT),
            required=_REQUIRED,
            root=root,
        )


def test_a_row_short_of_its_shape_is_refused() -> None:
    with pytest.raises(ValueError, match="one value per member"):
        _typed().complete_row((7,), required=_REQUIRED)


def test_a_catalog_compiles_one_plan_per_shape_and_one_converter_per_type() -> None:
    compiled: list[NeutralType] = []

    def counted(declared: NeutralType) -> ScalarConverter:
        compiled.append(declared)
        return typed_converter(declared)

    catalog = AuthoringCatalog(counted, BORROWED_DOCUMENTS, absent=_ABSENT)
    plan = catalog.plan(_ROW)

    assert catalog.plan(_ROW) is plan
    assert catalog.plan(_ADDRESS) is catalog.plan(_ADDRESS)
    assert sorted(map(repr, compiled)) == sorted(
        map(repr, (INT64, STRING, TIMESTAMP, Decimal(8, 5)))
    )


def test_owned_json_content_is_frozen_once() -> None:
    from parallax.core.base import JSON

    shape = MemberShape((ScalarDefinition("doc", JSON, False),))
    plan = AuthoringCatalog(wire_converter, MAPPING_DOCUMENTS, absent=_ABSENT).plan(shape)

    (cell,) = plan.complete_row(({"a": [1]},), required=0b1).cells

    assert cell == FrozenMap({"a": (1,)})
    assert type(cell) is FrozenMap


def test_authored_values_read_a_payload_in_member_order() -> None:
    assert _wire().authored_values({"name": "Ada", "id": 7}) == (
        7,
        "Ada",
        _ABSENT,
        _ABSENT,
        _ABSENT,
        _ABSENT,
    )
