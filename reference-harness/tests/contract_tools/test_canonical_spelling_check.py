"""Docker-free tests for the canonical Entity spelling gate.

Guards the fixed point `canonical_spelling_check` owns: everything the corpus
ships spells an Entity exactly as it resolves, with one per-reference exception
for the bare spelling a `reference-ambiguous-entity-name` case needs in order to
be ambiguous.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from reference_harness.canonical_spelling_check import check, main

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPAT_DIR = _REPO_ROOT / "core" / "compatibility"

_MODEL = """entity:
  name: Grade
  namespace: parallax.compatibility
  table: grade
  attributes:
    - { name: id, type: int64, primaryKey: true }
"""

_SHARED_MODEL = """entities:
  - name: SharedVariant
    namespace: archive
    table: archive_shared
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: archiveLabel, type: string, column: archive_label }
  - name: SharedVariant
    namespace: catalog
    table: catalog_shared
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: catalogLabel, type: string, column: catalog_label }
  - name: Register
    namespace: parallax.compatibility
    table: register
    attributes:
      - { name: id, type: int64, primaryKey: true }
"""

_HEADER = "# What the case proves.\n#\n# Why it holds.\n"


def _corpus(tmp_path: Path, *, cases: dict[str, str], models: dict[str, str]) -> Path:
    root = tmp_path / "compatibility"
    for directory in ("cases", "models", "fixtures", "benchmarks"):
        (root / directory).mkdir(parents=True)
    for name, text in models.items():
        (root / "models" / name).write_text(text, encoding="utf-8")
    for name, text in cases.items():
        (root / "cases" / name).write_text(_HEADER + text, encoding="utf-8")
    return root


def test_the_real_corpus_is_canonical() -> None:
    assert main([str(_COMPAT_DIR)]) == 0


def test_a_canonical_case_passes(tmp_path: Path) -> None:
    root = _corpus(
        tmp_path,
        models={"grade.yaml": _MODEL},
        cases={
            "m-x-001-read.yaml": (
                "model: models/grade.yaml\nshape: read\nwhen:\n"
                "  targetEntity: parallax.compatibility.Grade\n"
                "  operation:\n    eq: { attr: parallax.compatibility.Grade.id, value: 1 }\n"
            )
        },
    )
    assert check(root) == []


def test_a_bare_spelling_is_reported_with_file_path_expectation_and_actual(
    tmp_path: Path,
) -> None:
    root = _corpus(
        tmp_path,
        models={"grade.yaml": _MODEL},
        cases={
            "m-x-001-read.yaml": (
                "model: models/grade.yaml\nshape: read\nwhen:\n"
                "  targetEntity: Grade\n"
                "  operation:\n    eq: { attr: Grade.id, value: 1 }\n"
            )
        },
    )
    findings = check(root)
    case = root / "cases" / "m-x-001-read.yaml"
    assert findings == [
        f"{case}: when.targetEntity: expected 'parallax.compatibility.Grade', found 'Grade'",
        f"{case}: when.operation.eq.attr: "
        "expected 'parallax.compatibility.Grade.id', found 'Grade.id'",
    ]


def test_an_element_relative_path_names_no_entity_and_is_left_alone(tmp_path: Path) -> None:
    root = _corpus(
        tmp_path,
        models={"grade.yaml": _MODEL},
        cases={
            "m-x-001-read.yaml": (
                "model: models/grade.yaml\nshape: read\nwhen:\n"
                "  targetEntity: parallax.compatibility.Grade\n"
                "  operation:\n"
                "    nestedExists:\n"
                "      path: parallax.compatibility.Grade.address.phones\n"
                "      where:\n        nestedEq: { path: type, value: home }\n"
            )
        },
    )
    assert check(root) == []


def test_the_ambiguity_exception_admits_only_the_ambiguous_reference(tmp_path: Path) -> None:
    root = _corpus(
        tmp_path,
        models={"shared.yaml": _SHARED_MODEL},
        cases={
            "m-x-001-rejected-ambiguous.yaml": (
                "model: models/shared.yaml\nshape: rejected\nwhen:\n"
                "  operation:\n"
                "    exists:\n"
                "      rel: Register.variant\n"
                "      op:\n"
                "        eq: { attr: SharedVariant.archiveLabel, value: A-1 }\n"
                "then:\n  rejectedRule: reference-ambiguous-entity-name\n"
            )
        },
    )
    case = root / "cases" / "m-x-001-rejected-ambiguous.yaml"
    assert check(root) == [
        f"{case}: when.operation.exists.rel: "
        "expected 'parallax.compatibility.Register.variant', found 'Register.variant'"
    ]


def test_an_ambiguous_reference_outside_that_rule_is_reported_with_every_candidate(
    tmp_path: Path,
) -> None:
    root = _corpus(
        tmp_path,
        models={"shared.yaml": _SHARED_MODEL},
        cases={
            "m-x-001-read.yaml": (
                "model: models/shared.yaml\nshape: read\nwhen:\n"
                "  targetEntity: SharedVariant\n  operation:\n    all: {}\n"
            )
        },
    )
    case = root / "cases" / "m-x-001-read.yaml"
    assert check(root) == [
        f"{case}: when.targetEntity: expected 'archive.SharedVariant' or "
        "'catalog.SharedVariant', found 'SharedVariant'"
    ]


def test_a_malformed_document_is_a_finding_rather_than_a_crash(tmp_path: Path) -> None:
    root = _corpus(
        tmp_path,
        models={"grade.yaml": _MODEL},
        cases={"m-x-001-read.yaml": "model: [unterminated\n"},
    )
    findings = check(root)
    assert len(findings) == 1
    assert "unreadable document" in findings[0]


def test_a_bare_fixture_key_is_reported(tmp_path: Path) -> None:
    root = _corpus(tmp_path, models={"grade.yaml": _MODEL}, cases={})
    (root / "fixtures" / "grade.yaml").write_text("Grade:\n  - { id: 1 }\n", encoding="utf-8")
    fixture = root / "fixtures" / "grade.yaml"
    assert check(root) == [
        f"{fixture}: <root>: expected 'parallax.compatibility.Grade', found 'Grade'"
    ]


def test_a_bare_inheritance_parent_is_reported_against_the_childs_namespace(
    tmp_path: Path,
) -> None:
    root = _corpus(tmp_path, models={}, cases={})
    (root / "models" / "family.yaml").write_text(
        "entities:\n"
        "  - name: Animal\n    namespace: parallax.compatibility\n"
        "    inheritance: { strategy: table-per-hierarchy, role: root, tag: { column: kind } }\n"
        "    attributes:\n      - { name: id, type: int64, primaryKey: true }\n"
        "  - name: Dog\n    namespace: parallax.compatibility\n"
        "    inheritance: { role: concrete-subtype, parent: Animal, tagValue: dog }\n",
        encoding="utf-8",
    )
    model = root / "models" / "family.yaml"
    assert check(root) == [
        f"{model}: entity[1].inheritance.parent: "
        "expected 'parallax.compatibility.Animal', found 'Animal'"
    ]


def test_a_de_canonicalized_copy_of_the_real_corpus_fails(tmp_path: Path) -> None:
    root = tmp_path / "compatibility"
    shutil.copytree(_COMPAT_DIR, root)
    case = root / "cases" / "m-agg-002-count.yaml"
    case.write_text(
        case.read_text(encoding="utf-8").replace(
            "targetEntity: parallax.compatibility.Order", "targetEntity: Order"
        ),
        encoding="utf-8",
    )
    assert check(root) == [
        f"{case}: when.targetEntity: expected 'parallax.compatibility.Order', found 'Order'"
    ]
    assert main([str(root)]) == 1
