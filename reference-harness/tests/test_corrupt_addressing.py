"""`given.corrupt` addresses a non-temporal Entity, and nothing else.

`m-case-format` *Corrupting stored state* names the row by the model primary key
alone, which addresses one row only where the physical key IS that key. A
temporal Entity's rows are keyed by the model key together with each As-Of Axis's
end instant, so one value there addresses a milestone CHAIN — and an address that
means "every milestone" to one adapter and "no row at all" to another is a case
gradeable by neither. The corpus therefore refuses it statically, before any
executor runs, and the loader refuses it again before any row lands.

These DB-free probes pin both refusals over real corpus models, and pin that they
give one reason in one wording.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from reference_harness.case import corrupt_temporal_entity, load_model
from reference_harness.data_loader import load_model as load_fixture_rows
from reference_harness.schema_validate import _validate_corruptions

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

_POSITION = "parallax.compatibility.Position"
_STREAM_COORDINATE = "parallax.compatibility.StreamCoordinate"


def _entity_defs(model_rel: str) -> list[dict[str, Any]]:
    return load_model(_COMPATIBILITY_ROOT, model_rel).entity_defs


def _corruption(entity: str) -> dict[str, Any]:
    return {"entity": entity, "key": 1, "member": ["val"], "value": "not-a-decimal"}


def _static_errors(model_rel: str, *entries: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _validate_corruptions({"corrupt": list(entries)}, _entity_defs(model_rel), "case probe", errors)
    return errors


def test_the_corpus_refuses_a_corruption_addressing_a_temporal_entity() -> None:
    assert _static_errors("models/position.yaml", _corruption(_POSITION)) == [
        f"case probe: {corrupt_temporal_entity(_POSITION)}"
    ]


def test_the_corpus_admits_a_corruption_addressing_a_non_temporal_entity() -> None:
    assert _static_errors("models/stream-coordinates.yaml", _corruption(_STREAM_COORDINATE)) == []


def test_a_case_declaring_no_corruption_is_judged_at_all() -> None:
    errors: list[str] = []
    _validate_corruptions({"fixtures": True}, _entity_defs("models/position.yaml"), "probe", errors)
    assert errors == []


def test_the_loader_refuses_a_temporal_address_before_any_row_lands() -> None:
    class _RefusingProvider:
        dialect = "postgres"

        def load(self, table: str, columns: Any, rows: Any) -> None:
            raise AssertionError(f"{table} loaded despite a refused corruption")

    model = load_model(_COMPATIBILITY_ROOT, "models/position.yaml")
    with pytest.raises(ValueError, match="a temporal Entity: its model primary key"):
        load_fixture_rows(model, cast("Any", _RefusingProvider()), [_corruption(_POSITION)])
