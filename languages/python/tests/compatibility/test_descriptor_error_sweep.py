"""Docker-free descriptor-error sweep over the public text doors (m-descriptor
three-phase ingestion).

Every fixture under ``core/compatibility/descriptor-errors/`` pairs one raw
invalid document with one expectation sidecar by stem: the corpus pins the
exact ingestion phase, code, and — for the schema and value phases — the exact
canonically ordered ``(path, rule)`` violation sequence a conforming adapter
must report. Each fixture fails before Model Formation, so the
``domain_model_from_json`` and ``domain_model_from_yaml`` doors report exactly
what ingestion does.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import jsonschema
import pytest
import yaml
from jsonschema.protocols import Validator

from parallax.conformance import case_format
from parallax.descriptor import (
    DescriptorError,
    DescriptorViolation,
    domain_model_from_json,
    domain_model_from_yaml,
)
from tests._support.repo import REPO_ROOT

_CORPUS = REPO_ROOT / "core" / "compatibility" / "descriptor-errors"
_SCHEMA = cast(
    "Mapping[str, object]",
    json.loads((REPO_ROOT / "core" / "schemas" / "metamodel.schema.json").read_text()),
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


def test_the_corpus_exercises_both_concrete_syntax_formats() -> None:
    formats = {fixture.format for fixture in _FIXTURES}
    assert formats == {"json", "yaml"}


def _violation_key(entry: Mapping[str, object]) -> tuple[tuple[object, ...], str]:
    path = cast("Sequence[object]", entry["path"])
    return tuple(path), cast("str", entry["rule"])


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda f: f.stem)
def test_descriptor_error_sweep(fixture: _Fixture) -> None:
    door = domain_model_from_json if fixture.format == "json" else domain_model_from_yaml

    with pytest.raises(DescriptorError) as excinfo:
        door(fixture.text)
    error = excinfo.value

    phase = fixture.expected["phase"]
    assert error.code == fixture.expected["code"]

    if phase == "syntax":
        # A phase-1 failure never reaches phase 2 or phase 3, and it never
        # loses the parser's own diagnostic: this is the only phase whose
        # sidecar carries no `violations` key.
        assert "violations" not in fixture.expected
        assert error.violations == ()
        assert error.format == fixture.format
        assert error.__cause__ is not None
        assert error.line is not None
        assert error.column is not None
        return

    if phase == "schema":
        _assert_violations(error.violations, fixture.expected["violations"])
        return

    if phase == "value":
        _assert_violations(error.violations, fixture.expected["violations"])
        # An earlier phase's own success is a separate, positive fact: assert
        # independently (not just via the raised code) that the document is
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
    actual: Sequence[DescriptorViolation],
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
