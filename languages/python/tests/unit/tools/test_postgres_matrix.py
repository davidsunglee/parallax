from __future__ import annotations

import pytest

from postgres_matrix import versions


def test_identical_floor_and_latest_produce_one_database_version() -> None:
    assert versions("18.6") == ["18.6"]


def test_new_minor_keeps_the_floor_and_adds_latest() -> None:
    assert versions("18.12") == ["18.6", "18.12"]


@pytest.mark.parametrize("version", ["18.5", "19.0", "18", "18.6 beta", ""])
def test_unsupported_database_versions_cannot_enter_the_matrix(version: str) -> None:
    with pytest.raises(ValueError, match="outside"):
        versions(version)
