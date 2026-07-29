"""Independent harness conformance to m-descriptor's naming vectors."""

from __future__ import annotations

import pytest

from reference_harness.naming import default_column_name


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
