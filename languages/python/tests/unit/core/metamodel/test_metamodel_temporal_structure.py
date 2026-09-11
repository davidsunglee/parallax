"""The frontend-neutral Temporality Profile derivation and its inverse."""

from __future__ import annotations

import pytest

from parallax.core.metamodel import (
    TemporalDimension,
    derive_temporal_structure,
    temporality_profile,
)


@pytest.mark.parametrize(
    ("temporality", "expected"),
    [
        (None, ()),
        ("nontemporal", ()),
        ("transaction-time", (("txStart", "in_z"), ("txEnd", "out_z"))),
        (
            "bitemporal",
            (
                ("validStart", "from_z"),
                ("validEnd", "thru_z"),
                ("txStart", "in_z"),
                ("txEnd", "out_z"),
            ),
        ),
    ],
)
def test_a_profile_derives_its_endpoints_over_framework_fixed_columns(
    temporality: str | None, expected: tuple[tuple[str, str], ...]
) -> None:
    axes = derive_temporal_structure(temporality)
    assert (
        tuple(
            (endpoint.name, endpoint.column) for axis in axes for endpoint in (axis.start, axis.end)
        )
        == expected
    )


def test_an_unknown_profile_is_refused() -> None:
    with pytest.raises(ValueError, match="not a temporality profile"):
        derive_temporal_structure("valid-time")


@pytest.mark.parametrize(
    ("dimensions", "expected"),
    [
        ((), "nontemporal"),
        ((TemporalDimension.TRANSACTION_TIME,), "transaction-time"),
        ((TemporalDimension.VALID_TIME, TemporalDimension.TRANSACTION_TIME), "bitemporal"),
    ],
)
def test_the_profile_of_a_derived_axis_set_round_trips(
    dimensions: tuple[TemporalDimension, ...], expected: str
) -> None:
    profile = temporality_profile(dimensions)
    assert profile == expected
    assert tuple(axis.dimension for axis in derive_temporal_structure(profile)) == dimensions


def test_a_dimension_set_no_profile_derives_has_no_spelling() -> None:
    with pytest.raises(ValueError, match="no temporality profile derives"):
        temporality_profile((TemporalDimension.VALID_TIME,))
