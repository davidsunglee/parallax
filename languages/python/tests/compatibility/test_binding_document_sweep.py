"""Database-free sweep of the shared binding documents (m-database-binding).

Each fixture under ``core/compatibility/bindings/{accepted,rejected}`` pairs one
raw binding document with a sidecar naming the backend reader that judges it.
An accepted sidecar pins the normalized document; a rejected one pins every
definition issue in canonical order. The PostgreSQL text doors grade the
``postgres``-reader fixtures exactly; a document judged by another backend's
reader is refused by them as a foreign backend.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import pytest

from parallax.conformance import case_format
from parallax.core import BindingError
from parallax.postgres import PostgresBinding, PostgresLocation
from tests._support.repo import REPO_ROOT

_BINDINGS = REPO_ROOT / "core" / "compatibility" / "bindings"


@dataclass(frozen=True, slots=True)
class _Fixture:
    stem: str
    outcome: Literal["accepted", "rejected"]
    format: Literal["json", "yaml"]
    text: str
    expected: Mapping[str, object]


def _discover(outcome: Literal["accepted", "rejected"]) -> tuple[_Fixture, ...]:
    directory = _BINDINGS / outcome
    fixtures: list[_Fixture] = []
    for sidecar in sorted(directory.glob("*.expected.yaml")):
        stem = sidecar.name.removesuffix(".expected.yaml")
        candidates = (directory / f"{stem}.json", directory / f"{stem}.yaml")
        present = [path for path in candidates if path.exists()]
        assert len(present) == 1, f"{stem}: exactly one raw .json or .yaml document"
        expected = case_format.safe_load_yaml(sidecar.read_text(encoding="utf-8"))
        assert isinstance(expected, dict)
        document: Path = present[0]
        fixtures.append(
            _Fixture(
                stem=stem,
                outcome=outcome,
                format="json" if document.suffix == ".json" else "yaml",
                text=document.read_text(encoding="utf-8"),
                expected=cast("Mapping[str, object]", expected),
            )
        )
    return tuple(fixtures)


_FIXTURES = _discover("accepted") + _discover("rejected")


def _read(fixture: _Fixture) -> PostgresBinding:
    door = PostgresBinding.from_json if fixture.format == "json" else PostgresBinding.from_yaml
    return door(fixture.text)


def test_the_fixtures_exercise_both_readers_formats_and_outcomes() -> None:
    assert {(f.outcome, f.expected["reader"]) for f in _FIXTURES} == {
        ("accepted", "postgres"),
        ("accepted", "mariadb"),
        ("rejected", "postgres"),
        ("rejected", "mariadb"),
    }
    assert {f.format for f in _FIXTURES} == {"json", "yaml"}


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda f: f"{f.outcome}-{f.stem}")
def test_binding_document_sweep(fixture: _Fixture) -> None:
    if fixture.expected["reader"] != "postgres":
        with pytest.raises(BindingError) as foreign:
            _read(fixture)
        assert [(i.code, i.path) for i in foreign.value.issues] == [
            ("binding-backend-mismatch", ("backend",))
        ]
        return
    if fixture.outcome == "accepted":
        binding = _read(fixture)
        assert binding.to_document() == fixture.expected["normalized"]
        assert PostgresBinding.from_document(binding.to_document()) == binding
        return
    with pytest.raises(BindingError) as raised:
        _read(fixture)
    assert raised.value.code == "binding-definition-rejected"
    expected = cast("Sequence[Mapping[str, object]]", fixture.expected["issues"])
    assert [(issue.code, issue.path) for issue in raised.value.issues] == [
        (entry["code"], tuple(cast("Sequence[str]", entry["path"]))) for entry in expected
    ]


def test_the_corpus_default_binding_places_everything_in_px() -> None:
    document = case_format.safe_load_yaml((_BINDINGS / "default.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    postgres = cast("Mapping[str, object]", document["postgres"])
    assert PostgresBinding.from_document(postgres) == PostgresBinding(
        default=PostgresLocation(schema="px")
    )
