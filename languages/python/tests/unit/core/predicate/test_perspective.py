"""m-predicate: temporal perspective values."""

from __future__ import annotations

import datetime as dt

import pytest

from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    EntityIdentity,
    TemporalDimension,
)
from parallax.core.predicate._perspective import (
    AtPerspective,
    AxisPerspective,
    LatestPerspective,
    TemporalPerspective,
)

_ENTITY = EntityIdentity("parallax.test", "Contract")
_OTHER = EntityIdentity("parallax.test", "Amendment")


def _axis(
    dimension: TemporalDimension, start: str, end: str, entity: EntityIdentity = _ENTITY
) -> AsOfAxisMetadata:
    return AsOfAxisMetadata(
        dimension, AttributeIdentity(entity, start), AttributeIdentity(entity, end)
    )


VALID = _axis(TemporalDimension.VALID_TIME, "validFrom", "validThru")
TX = _axis(TemporalDimension.TRANSACTION_TIME, "txIn", "txOut")
MARCH = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
APRIL = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)


def test_an_empty_perspective_is_that_of_a_non_temporal_target() -> None:
    perspective = TemporalPerspective()

    assert list(perspective.ranked_perspectives()) == []
    assert not perspective.is_temporal
    assert not perspective.is_latest_end(TX.end_attribute)


@pytest.mark.parametrize(
    ("valid_time", "transaction_time"),
    [
        (LatestPerspective(TX), LatestPerspective(TX)),
        (None, AtPerspective(VALID, MARCH)),
        (LatestPerspective(VALID), LatestPerspective(VALID)),
    ],
    ids=["transaction-axis-as-valid-time", "valid-axis-as-transaction-time", "both-valid"],
)
def test_a_perspective_in_the_other_dimensions_field_is_rejected(
    valid_time: AxisPerspective | None, transaction_time: AxisPerspective | None
) -> None:
    with pytest.raises(ValueError, match="perspective is over the"):
        TemporalPerspective(valid_time=valid_time, transaction_time=transaction_time)


@pytest.mark.parametrize(
    "valid_time", [LatestPerspective(VALID), AtPerspective(VALID, MARCH)], ids=["latest", "at"]
)
def test_valid_time_without_transaction_time_is_rejected(valid_time: AxisPerspective) -> None:
    with pytest.raises(ValueError, match="requires a Transaction-Time perspective"):
        TemporalPerspective(valid_time=valid_time)


def test_ranked_perspectives_yield_valid_time_before_transaction_time() -> None:
    valid_time = AtPerspective(VALID, MARCH)
    transaction_time = LatestPerspective(TX)

    bitemporal = TemporalPerspective(valid_time=valid_time, transaction_time=transaction_time)
    transaction_time_only = TemporalPerspective(transaction_time=transaction_time)

    assert list(bitemporal.ranked_perspectives()) == [valid_time, transaction_time]
    assert list(transaction_time_only.ranked_perspectives()) == [transaction_time]
    assert bitemporal.is_temporal
    assert transaction_time_only.is_temporal


def test_equality_compares_axes_alternatives_and_instants() -> None:
    perspective = TemporalPerspective(
        valid_time=AtPerspective(VALID, MARCH), transaction_time=LatestPerspective(TX)
    )
    same = TemporalPerspective(
        valid_time=AtPerspective(
            _axis(TemporalDimension.VALID_TIME, "validFrom", "validThru"),
            dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        ),
        transaction_time=LatestPerspective(
            _axis(TemporalDimension.TRANSACTION_TIME, "txIn", "txOut")
        ),
    )
    different = [
        TemporalPerspective(
            valid_time=AtPerspective(VALID, APRIL), transaction_time=LatestPerspective(TX)
        ),
        TemporalPerspective(
            valid_time=LatestPerspective(VALID), transaction_time=LatestPerspective(TX)
        ),
        TemporalPerspective(
            valid_time=AtPerspective(VALID, MARCH), transaction_time=AtPerspective(TX, MARCH)
        ),
        TemporalPerspective(
            valid_time=AtPerspective(
                _axis(TemporalDimension.VALID_TIME, "validFrom", "validThru", _OTHER), MARCH
            ),
            transaction_time=LatestPerspective(TX),
        ),
        TemporalPerspective(transaction_time=LatestPerspective(TX)),
        TemporalPerspective(),
    ]

    assert perspective == same
    assert hash(perspective) == hash(same)
    assert all(perspective != other for other in different)


def test_only_a_latest_axis_end_is_a_latest_end() -> None:
    perspective = TemporalPerspective(
        valid_time=AtPerspective(VALID, MARCH), transaction_time=LatestPerspective(TX)
    )

    assert perspective.is_latest_end(TX.end_attribute)
    assert not perspective.is_latest_end(TX.start_attribute)
    assert not perspective.is_latest_end(VALID.end_attribute)
    assert not perspective.is_latest_end(VALID.start_attribute)
    assert not perspective.is_latest_end(AttributeIdentity(_OTHER, TX.end_attribute.name))


def test_every_latest_axis_contributes_its_end() -> None:
    perspective = TemporalPerspective(
        valid_time=LatestPerspective(VALID), transaction_time=LatestPerspective(TX)
    )

    assert perspective.is_latest_end(VALID.end_attribute)
    assert perspective.is_latest_end(TX.end_attribute)
