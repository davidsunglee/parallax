"""Portable member-storage naming through the supported metamodel API."""

from __future__ import annotations

import pytest

from parallax.core.metamodel import default_column_name


@pytest.mark.parametrize(
    ("name", "column"),
    [
        ("id", "id"),
        ("personId", "person_id"),
        ("taxID", "tax_i_d"),
        ("line2Item", "line2_item"),
        ("already_snake", "already_snake"),
        ("legacy_ID", "legacy__i_d"),
    ],
)
def test_default_column_name_matches_the_authoritative_vectors(name: str, column: str) -> None:
    assert default_column_name(name) == column
