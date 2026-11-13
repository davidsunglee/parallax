"""DB-free grading of the shared binding documents (m-database-binding).

Each fixture under ``core/compatibility/bindings/{accepted,rejected}`` is one raw
document plus a sidecar naming the backend ``reader`` that judges it and either
the ``normalized`` document or the canonically ordered definition ``issues``.
The independent reader must reproduce each sidecar exactly, and the canonical
schema must agree: an accepted document is schema-valid, and a document refused
for anything but a foreign backend is schema-invalid.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reference_harness.corpus_yaml import read_corpus_yaml
from reference_harness.database_binding import (
    LOCATION_KEYS,
    BindingIssue,
    BindingRejection,
    normalize_binding,
    parse_binding_text,
)
from reference_harness.providers import DIALECT_CATALOG
from reference_harness.schemas import load_schemas

_CORE = Path(__file__).resolve().parents[2] / "core"
_BINDINGS = _CORE / "compatibility" / "bindings"
_SCHEMAS = load_schemas(_CORE)
_SCHEMA = _SCHEMAS["database-binding.schema.json"]
_VALIDATOR = Draft202012Validator(_SCHEMA)


@dataclass(frozen=True)
class _Fixture:
    outcome: str
    stem: str
    fmt: str
    text: str
    expected: dict[str, Any]


def _fixtures() -> list[_Fixture]:
    found: list[_Fixture] = []
    for outcome in ("accepted", "rejected"):
        directory = _BINDINGS / outcome
        documents = {
            path.stem: path
            for path in directory.iterdir()
            if path.suffix in (".json", ".yaml") and not path.name.endswith(".expected.yaml")
        }
        sidecars = {
            path.name.removesuffix(".expected.yaml"): path
            for path in directory.glob("*.expected.yaml")
        }
        assert set(documents) == set(sidecars), f"{outcome}: every document has one sidecar"
        for stem in sorted(documents):
            expected = read_corpus_yaml(sidecars[stem])
            outcome_key = "normalized" if outcome == "accepted" else "issues"
            assert set(expected) == {"reader", outcome_key}, f"{outcome}/{stem}: sidecar keys"
            assert expected["reader"] in LOCATION_KEYS, f"{outcome}/{stem}: reader"
            found.append(
                _Fixture(
                    outcome,
                    stem,
                    documents[stem].suffix.removeprefix("."),
                    documents[stem].read_text(encoding="utf-8"),
                    expected,
                )
            )
    return found


_FIXTURES = _fixtures()


def _schema_valid(document: Any) -> bool:
    return not list(_VALIDATOR.iter_errors(document))


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda f: f"{f.outcome}-{f.stem}")
def test_the_reader_reproduces_every_sidecar(fixture: _Fixture) -> None:
    reader = fixture.expected["reader"]
    if fixture.outcome == "accepted":
        document = parse_binding_text(fixture.text, fixture.fmt)
        normalized = normalize_binding(document, reader)
        assert normalized == fixture.expected["normalized"]
        assert normalize_binding(normalized, reader) == normalized
        assert _schema_valid(document)
        assert _schema_valid(normalized)
        return
    expected = tuple(
        BindingIssue(tuple(entry["path"]), entry["code"]) for entry in fixture.expected["issues"]
    )
    assert list(expected) == sorted(expected), "sidecar issues are in canonical order"
    with pytest.raises(BindingRejection) as raised:
        normalize_binding(parse_binding_text(fixture.text, fixture.fmt), reader)
    assert raised.value.issues == expected
    codes = {issue.code for issue in expected}
    if codes - {"binding-backend-mismatch", "binding-syntax-invalid"}:
        assert not _schema_valid(parse_binding_text(fixture.text, fixture.fmt))


def test_the_fixtures_cover_both_readers_and_both_outcomes() -> None:
    assert {(f.outcome, f.expected["reader"]) for f in _FIXTURES} == {
        (outcome, reader) for outcome in ("accepted", "rejected") for reader in LOCATION_KEYS
    }


def test_the_default_binding_places_every_dialect_in_px() -> None:
    default = read_corpus_yaml(_BINDINGS / "default.yaml")
    assert set(default) == set(DIALECT_CATALOG)
    for dialect, document in default.items():
        assert _schema_valid(document)
        assert normalize_binding(document, dialect)["default"] == {LOCATION_KEYS[dialect]: "px"}


def test_the_schema_copies_only_the_shared_identity_grammars() -> None:
    identity = _SCHEMAS["identity.schema.json"]["$defs"]
    defs = _SCHEMA["$defs"]
    assert defs["namespace"]["pattern"] == identity["namespaceSegment"]["pattern"]
    assert defs["canonicalEntity"]["pattern"] == identity["entityName"]["pattern"]
