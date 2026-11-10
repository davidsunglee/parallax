from __future__ import annotations

from api_reference import REFERENCE, render


def test_api_reference_matches_the_snapshot_and_docstrings() -> None:
    assert REFERENCE.read_text() == render(), (
        "docs/api-reference.md is stale; run `uv run python tools/api_reference.py`"
    )
