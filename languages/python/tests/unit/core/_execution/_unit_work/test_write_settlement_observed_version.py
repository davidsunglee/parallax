"""The version an existing-row write of an explicitly versioned row settles
from, which only the observation its source retained supplies."""

from __future__ import annotations

import datetime as dt

import pytest

from parallax.core._execution._unit_work.write_settlement import require_observed_version
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import UnobservedVersionError
from parallax.core.write_plan import PredecessorRow, TemporalObservation, VersionObservation

_ACCOUNT = EntityIdentity("parallax.compatibility", "Account")


def test_an_observed_version_is_the_version_the_write_advances_from() -> None:
    assert require_observed_version(_ACCOUNT, VersionObservation(observed_version=5)) == 5


def test_a_write_that_observed_nothing_is_refused_naming_its_entity() -> None:
    with pytest.raises(UnobservedVersionError, match=r"Account: .*requires the version its source"):
        require_observed_version(_ACCOUNT, None)


def test_a_temporal_observation_supplies_no_version() -> None:
    # It names a predecessor milestone, never a version, so it never licenses a
    # versioned advance either.
    observation = TemporalObservation(
        predecessor=PredecessorRow(
            members={"id": 1, "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC)}
        )
    )
    with pytest.raises(UnobservedVersionError, match="Account"):
        require_observed_version(_ACCOUNT, observation)
