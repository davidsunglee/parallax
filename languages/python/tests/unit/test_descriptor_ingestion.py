"""Three-phase descriptor ingestion over the canonical descriptor-errors corpus.

Every fixture under ``core/compatibility/descriptor-errors/`` pairs one raw
invalid document with one expectation sidecar by stem: the corpus pins the
exact ingestion phase, code, and — for the schema and value phases — the exact
canonically ordered ``(path, rule)`` violation sequence a conforming adapter
must report.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import jsonschema
import pytest
import yaml
from jsonschema.protocols import Validator

from parallax.conformance import case_format
from parallax.core.descriptor import (
    DescriptorError,
    DescriptorSchemaError,
    DescriptorSchemaViolation,
    DescriptorSyntaxError,
    DescriptorValueError,
    DescriptorValueViolation,
    parse_json,
    parse_yaml,
)
from parallax.core.descriptor import ingest as _ingest

pytestmark = pytest.mark.unit

_REPO = case_format.find_repo_root()
_CORPUS = _REPO / "core" / "compatibility" / "descriptor-errors"
_SCHEMA = cast(
    "Mapping[str, object]",
    json.loads((_REPO / "core" / "schemas" / "metamodel.schema.json").read_text()),
)


@dataclass(frozen=True, slots=True)
class _Fixture:
    """One raw-document/expectation-sidecar pair, by stem."""

    stem: str
    format: Literal["json", "yaml"]
    text: str
    expected: Mapping[str, object]


def _discover() -> tuple[_Fixture, ...]:
    fixtures: list[_Fixture] = []
    for expected_path in sorted(_CORPUS.glob("*.expected.yaml")):
        stem = expected_path.name.removesuffix(".expected.yaml")
        expected = case_format.safe_load_yaml(expected_path.read_text(encoding="utf-8"))
        assert isinstance(expected, dict)
        json_path = _CORPUS / f"{stem}.json"
        yaml_path = _CORPUS / f"{stem}.yaml"
        assert json_path.exists() != yaml_path.exists(), (
            f"{stem}: exactly one of a raw .json or .yaml document must exist"
        )
        doc_path, doc_format = (json_path, "json") if json_path.exists() else (yaml_path, "yaml")
        fixtures.append(
            _Fixture(
                stem=stem,
                format=doc_format,
                text=doc_path.read_text(encoding="utf-8"),
                expected=cast("Mapping[str, object]", expected),
            )
        )
    return tuple(fixtures)


_FIXTURES = _discover()


def test_the_corpus_has_the_documented_stem_count() -> None:
    # Pinned to the corpus's exact stem count so an added or removed fixture
    # must update this assertion explicitly, rather than silently shrinking
    # or growing the parametrization unnoticed.
    assert len(_FIXTURES) == 26


def test_the_corpus_exercises_both_concrete_syntax_formats() -> None:
    formats = {fixture.format for fixture in _FIXTURES}
    assert formats == {"json", "yaml"}


def _violation_key(entry: Mapping[str, object]) -> tuple[tuple[object, ...], str]:
    path = cast("Sequence[object]", entry["path"])
    return tuple(path), cast("str", entry["rule"])


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda f: f.stem)
def test_descriptor_ingestion_matches_the_corpus_expectation(fixture: _Fixture) -> None:
    parse = parse_json if fixture.format == "json" else parse_yaml

    with pytest.raises(DescriptorError) as excinfo:
        parse(fixture.text)
    error = excinfo.value

    phase = fixture.expected["phase"]
    assert error.code == fixture.expected["code"]

    if phase == "syntax":
        # A phase-1 failure never reaches phase 2 or phase 3, and it never
        # loses the parser's own diagnostic: this is the only phase whose
        # sidecar carries no `violations` key.
        assert "violations" not in fixture.expected
        assert isinstance(error, DescriptorSyntaxError)
        assert not isinstance(error, (DescriptorSchemaError, DescriptorValueError))
        assert error.format == fixture.format
        assert error.cause is not None
        assert error.line is not None
        assert error.column is not None
        return

    if phase == "schema":
        assert isinstance(error, DescriptorSchemaError)
        _assert_violations(error.violations, fixture.expected["violations"])
        return

    if phase == "value":
        assert isinstance(error, DescriptorValueError)
        _assert_violations(error.violations, fixture.expected["violations"])
        # An earlier phase's own success is a separate, positive fact: assert
        # independently (not just via the raised type) that the document is
        # schema-valid, so a value-phase fixture can never be silently masking
        # a schema violation the adapter mis-happening to shove into phase 3.
        document = (
            json.loads(fixture.text) if fixture.format == "json" else yaml.safe_load(fixture.text)
        )
        validator = cast(Validator, jsonschema.Draft202012Validator(_SCHEMA))
        assert not list(validator.iter_errors(document))
        return

    raise AssertionError(f"{fixture.stem}: unknown phase {phase!r}")


def _assert_violations(
    actual: Sequence[DescriptorSchemaViolation] | Sequence[DescriptorValueViolation],
    expected: object,
) -> None:
    assert isinstance(expected, Sequence)
    expected_entries = cast("Sequence[Mapping[str, object]]", expected)
    assert expected_entries, "a schema/value sidecar's `violations` is nonempty"
    actual_keys = [(tuple(v.path), v.rule) for v in actual]
    expected_keys = [_violation_key(entry) for entry in expected_entries]
    # Canonical (path, rule) order and duplicate-freedom, message excluded.
    assert actual_keys == expected_keys
    assert len(set(actual_keys)) == len(actual_keys)


def test_a_schema_error_naming_no_violation_is_not_a_report() -> None:
    with pytest.raises(ValueError, match="at least one violation"):
        DescriptorSchemaError([])


def test_a_value_error_naming_no_violation_is_not_a_report() -> None:
    with pytest.raises(ValueError, match="at least one violation"):
        DescriptorValueError([])


def test_the_schema_phase_reports_a_missing_schema_file_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # `_schema_path` walks up from its OWN source location; relocating that
    # location to a bare temp directory (no `core/schemas` above it) exercises
    # the not-a-checkout diagnostic directly.
    monkeypatch.setattr(_ingest, "__file__", str(tmp_path / "ingest.py"))
    with pytest.raises(FileNotFoundError, match=r"metamodel\.schema\.json"):
        _ingest._schema_path()  # pyright: ignore[reportPrivateUsage]


def test_a_missing_jsonschema_dependency_raises_a_clear_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    _ingest._validator.cache_clear()  # pyright: ignore[reportPrivateUsage]
    try:
        with pytest.raises(RuntimeError, match="jsonschema"):
            _ingest._validator()  # pyright: ignore[reportPrivateUsage]
    finally:
        _ingest._validator.cache_clear()  # pyright: ignore[reportPrivateUsage]
