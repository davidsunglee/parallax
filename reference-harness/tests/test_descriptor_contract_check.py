"""Docker-free tests for the m-descriptor ingestion/export contract gate.

Guards the normative properties `descriptor_contract_check` exists to prove:
every canonical invalid-descriptor fixture under
``core/compatibility/descriptor-errors/`` fails in its expected phase with its
expected canonically ordered violations, the canonical violation ordering and
collapse laws (equality/order ``(path, rule)``, branching-keyword collapse,
duplicate-free sequences) hold, every corpus model export is
byte-deterministic, and a malformed fixture set or corpus fails loudly rather
than passing vacuously. The real artifacts pass; injected mutations each fail
with their named error.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from reference_harness.descriptor_contract_check import (
    Violation,
    canonical_violations,
    export_determinism_errors,
    fixture_errors,
    main,
    violation_sort_key,
)

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_FIXTURE_DIR = _COMPATIBILITY_ROOT / "descriptor-errors"
_MODELS_DIR = _COMPATIBILITY_ROOT / "models"
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "metamodel.schema.json"


def _schema() -> dict[str, object]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _copied_fixtures(tmp_path: Path) -> Path:
    """A mutable copy of the real fixture set."""
    copy = tmp_path / "descriptor-errors"
    shutil.copytree(_FIXTURE_DIR, copy)
    return copy


def _tree_with_schema(tmp_path: Path, schema_text: str) -> Path:
    """A compatibility tree over the real fixture set whose ``core/schemas``
    metamodel schema is replaced by *schema_text*; returns the compatibility
    root to pass to ``main``."""
    core = tmp_path / "core"
    (core / "schemas").mkdir(parents=True)
    (core / "schemas" / "metamodel.schema.json").write_text(schema_text, encoding="utf-8")
    compatibility = core / "compatibility"
    compatibility.mkdir()
    shutil.copytree(_FIXTURE_DIR, compatibility / "descriptor-errors")
    (compatibility / "models").mkdir()
    return compatibility


# --- the real artifacts pass ---------------------------------------------------


def test_real_fixture_set_passes() -> None:
    assert fixture_errors(_FIXTURE_DIR, _schema()) == []


def test_real_fixture_set_covers_both_failing_phases() -> None:
    # A sanity floor: the canonical set carries the phase-1 minimal pair (one
    # malformed JSON, one malformed YAML) and at least one schema fixture.
    expectations = sorted(_FIXTURE_DIR.glob("*.expected.yaml"))
    phases = [yaml.safe_load(path.read_text(encoding="utf-8"))["phase"] for path in expectations]
    syntax_documents = {
        path.suffix
        for path in _FIXTURE_DIR.iterdir()
        if path.name.startswith("syntax-") and not path.name.endswith(".expected.yaml")
    }
    assert phases.count("syntax") == 2
    assert syntax_documents == {".json", ".yaml"}
    assert phases.count("schema") >= 1


def test_real_corpus_export_is_deterministic() -> None:
    assert export_determinism_errors(_MODELS_DIR) == []


def test_main_reports_success_on_the_real_corpus() -> None:
    assert main([str(_COMPATIBILITY_ROOT)]) == 0


# --- the canonical ordering and collapse laws ----------------------------------


def test_prefix_path_orders_before_its_extensions() -> None:
    prefix = Violation(("entity", "attributes"), "required")
    extension = Violation(("entity", "attributes", 0), "required")
    assert sorted([extension, prefix], key=violation_sort_key) == [prefix, extension]


def test_array_indices_order_numerically() -> None:
    # Codepoint comparison of the decimal spellings would put 10 before 2.
    second = Violation(("entities", 2), "required")
    tenth = Violation(("entities", 10), "required")
    assert sorted([tenth, second], key=violation_sort_key) == [second, tenth]


def test_member_names_order_by_codepoint() -> None:
    attributes = Violation(("entities", 0, "attributes"), "type")
    persistence = Violation(("entities", 0, "persistence"), "enum")
    assert sorted([persistence, attributes], key=violation_sort_key) == [attributes, persistence]


def test_equal_paths_order_by_rule() -> None:
    one_of = Violation((), "oneOf")
    type_rule = Violation((), "type")
    assert sorted([type_rule, one_of], key=violation_sort_key) == [one_of, type_rule]


def test_equal_identities_collapse_to_one_violation() -> None:
    # An empty entity misses `name`, `table`, and `attributes` — three
    # `required` failures sharing one (path, rule) identity.
    assert canonical_violations({"entity": {}}, _schema()) == [Violation(("entity",), "required")]


def test_branching_keyword_collapses_to_the_branching_path() -> None:
    # The mixed defining/reverse fixture fails the relationship oneOf: exactly
    # one violation at the branching path, no per-branch sub-errors.
    document = json.loads(
        (_FIXTURE_DIR / "schema-relationship-mixed-forms.json").read_text(encoding="utf-8")
    )
    assert canonical_violations(document, _schema()) == [
        Violation(("entities", 0, "relationships", 0), "oneOf")
    ]


# --- injected fixture mutations fail with named errors -------------------------


def test_wrong_expected_rule_fails_with_a_violation_mismatch(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    sidecar = fixtures / "schema-persistence-vocabulary.expected.yaml"
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace("rule: enum", "rule: pattern"),
        encoding="utf-8",
    )
    errors = fixture_errors(fixtures, _schema())
    assert any(
        "schema-persistence-vocabulary.yaml" in e and "differ from the canonical violations" in e
        for e in errors
    )


def test_misordered_expected_violations_fail_the_canonical_order(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    sidecar = fixtures / "schema-canonical-violation-order.expected.yaml"
    expectation = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    expectation["violations"].reverse()
    sidecar.write_text(yaml.safe_dump(expectation), encoding="utf-8")
    errors = fixture_errors(fixtures, _schema())
    # The identity set still matches, so the one failure is the ordering law.
    assert errors == [e for e in errors if "not in canonical order" in e]
    assert len(errors) == 1


def test_schema_valid_document_fixture_is_reported(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    (fixtures / "schema-empty-document.yaml").write_text(
        "entity:\n"
        "  name: Order\n"
        "  table: orders\n"
        "  attributes:\n"
        "    - name: id\n"
        "      type: int64\n"
        "      primaryKey: true\n",
        encoding="utf-8",
    )
    errors = fixture_errors(fixtures, _schema())
    assert any("schema-empty-document.yaml" in e and "schema-valid" in e for e in errors)


def test_syntax_fixture_that_parses_is_reported(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    (fixtures / "syntax-truncated-json.json").write_text('{"entity": {}}\n', encoding="utf-8")
    errors = fixture_errors(fixtures, _schema())
    assert any(
        "syntax-truncated-json.json" in e and "json text parses cleanly" in e for e in errors
    )


def test_schema_fixture_that_does_not_parse_is_reported(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    (fixtures / "schema-empty-document.yaml").write_text("attributes: [\n", encoding="utf-8")
    errors = fixture_errors(fixtures, _schema())
    assert any("schema-empty-document.yaml" in e and "does not parse" in e for e in errors)


def test_unpaired_files_are_reported(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    (fixtures / "schema-persistence-vocabulary.expected.yaml").unlink()
    (fixtures / "schema-orphaned.expected.yaml").write_text(
        "phase: syntax\ncode: descriptor-invalid-syntax\n", encoding="utf-8"
    )
    errors = fixture_errors(fixtures, _schema())
    assert any(
        "schema-persistence-vocabulary.yaml" in e and "has no" in e and "sidecar" in e
        for e in errors
    )
    assert any("schema-orphaned.expected.yaml" in e and "has no" in e for e in errors)


def test_duplicate_document_stems_are_reported(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    (fixtures / "schema-empty-document.json").write_text("{}\n", encoding="utf-8")
    errors = fixture_errors(fixtures, _schema())
    assert any("'schema-empty-document'" in e and "two documents" in e for e in errors)


def test_unexpected_files_are_reported(tmp_path: Path) -> None:
    fixtures = _copied_fixtures(tmp_path)
    (fixtures / "notes.txt").write_text("stray\n", encoding="utf-8")
    errors = fixture_errors(fixtures, _schema())
    assert any("unexpected file notes.txt" in e for e in errors)


def test_malformed_expectation_sidecars_are_reported(tmp_path: Path) -> None:
    mutations = [
        ("phase: schema", "phase: semantics", "`phase` must be one of"),
        (
            "code: descriptor-schema-invalid",
            "code: descriptor-invalid-syntax",
            "requires `code: descriptor-schema-invalid`",
        ),
        ("phase: schema\n", "phase: schema\nseverity: fatal\n", "keys must be exactly"),
        (
            "violations:\n  - path: [entity, persistence]\n    rule: enum\n",
            "violations: []\n",
            "must be a nonempty list",
        ),
        ("path: [entity, persistence]", "path: [entity, true]", "member names and array indices"),
        ("    rule: enum", "    rule: enum\n    severity: fatal", "exactly `path` and `rule`"),
    ]
    original = (_FIXTURE_DIR / "schema-persistence-vocabulary.expected.yaml").read_text(
        encoding="utf-8"
    )
    for position, (old, new, expected_error) in enumerate(mutations):
        fixtures = _copied_fixtures(tmp_path / f"mutation-{position}")
        mutated = original.replace(old, new)
        assert mutated != original, old
        (fixtures / "schema-persistence-vocabulary.expected.yaml").write_text(
            mutated, encoding="utf-8"
        )
        errors = fixture_errors(fixtures, _schema())
        assert any(
            "schema-persistence-vocabulary.expected.yaml" in e and expected_error in e
            for e in errors
        ), (expected_error, errors)


def test_syntax_sidecar_carrying_violations_is_reported(tmp_path: Path) -> None:
    # `violations` is a schema-phase key; a syntax sidecar that adds it must
    # fail the exact-key rule, not be silently tolerated.
    fixtures = _copied_fixtures(tmp_path)
    sidecar = fixtures / "syntax-truncated-json.expected.yaml"
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8") + "violations:\n  - path: []\n    rule: type\n",
        encoding="utf-8",
    )
    errors = fixture_errors(fixtures, _schema())
    assert any(
        "syntax-truncated-json.expected.yaml" in e and "keys must be exactly" in e for e in errors
    )


def test_empty_fixture_directory_is_reported(tmp_path: Path) -> None:
    empty = tmp_path / "descriptor-errors"
    empty.mkdir()
    errors = fixture_errors(empty, _schema())
    assert any("no descriptor-error fixtures found" in e for e in errors)


# --- export-determinism mutations ----------------------------------------------


def test_unserializable_model_is_reported(tmp_path: Path) -> None:
    # An unquoted YAML date decodes to a non-JSON scalar the canonical JSON
    # writer cannot serialize: reported, never raised.
    models = tmp_path / "models"
    models.mkdir()
    (models / "dated.yaml").write_text(
        "entity:\n"
        "  name: Reading\n"
        "  table: reading\n"
        "  attributes:\n"
        "    - name: id\n"
        "      type: date\n"
        "      primaryKey: true\n"
        "      default: 2024-01-01\n",
        encoding="utf-8",
    )
    errors = export_determinism_errors(models)
    assert any("dated.yaml" in e and "canonical json export failed" in e for e in errors)


def test_type_changing_round_trip_is_reported(tmp_path: Path) -> None:
    # An integer object key survives YAML but becomes a string through the
    # JSON cycle: byte-stable, yet the value changed — reported.
    models = tmp_path / "models"
    models.mkdir()
    (models / "keyed.yaml").write_text("entity:\n  1: tag\n", encoding="utf-8")
    errors = export_determinism_errors(models)
    assert any("keyed.yaml" in e and "changed the document" in e for e in errors)


def test_empty_models_directory_is_reported(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    assert export_determinism_errors(models) == [f"no corpus models found under {models}"]


# --- the CLI entry point ---------------------------------------------------------


def test_main_rejects_bad_argument_counts() -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2


def test_main_rejects_a_compatibility_root_missing_the_fixture_set(tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    assert main([str(tmp_path)]) == 2


def test_main_reports_a_meta_schema_invalid_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `{"type": 7}` parses as JSON with an object root but is not a Draft
    # 2020-12 schema; unvetted it reaches `iter_errors` and raises. The CLI
    # must report it on stderr and exit 1, never surface a traceback.
    compatibility = _tree_with_schema(tmp_path, '{"type": 7}\n')
    assert main([str(compatibility)]) == 1
    stderr = capsys.readouterr().err
    assert "malformed Draft 2020-12 schema" in stderr
    assert "metamodel.schema.json" in stderr


def test_main_reports_an_unresolvable_schema_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A dangling `$ref` passes the meta-schema, so it escapes `check_schema`
    # and surfaces only when fixture validation resolves it — still reported,
    # never raised.
    compatibility = _tree_with_schema(tmp_path, '{"$ref": "#/$defs/nope"}\n')
    assert main([str(compatibility)]) == 1
    stderr = capsys.readouterr().err
    assert "malformed Draft 2020-12 schema" in stderr
    assert "unresolvable schema reference" in stderr
