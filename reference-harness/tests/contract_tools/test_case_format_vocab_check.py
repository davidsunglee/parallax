"""Docker-free tests for the case-format prose <-> schema vocabulary check.

Guards the normative property `case_format_vocab_check` exists to prove: each
closed vocabulary `core/spec/m-case-format.md` documents in prose — the
`rejectedRule` rule set and a scenario step's `expectError` code set — is
EXACTLY the `enum` `core/schemas/compatibility-case.schema.json` declares for
it, and neither side may drift from the other. The drift is silent and
safety-critical: a schema `enum` missing a value the prose documents makes a
case pinning that value fail schema validation regardless of whether every
implementation classifies it correctly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from reference_harness.case_format_vocab_check import (
    VocabMismatch,
    check,
    main,
    prose_expect_errors,
    prose_rejected_rules,
    schema_expect_errors,
    schema_rejected_rules,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"


def _real_markdown() -> str:
    return (_SPEC_DIR / "m-case-format.md").read_text(encoding="utf-8")


def _real_schema() -> dict[str, object]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_real_prose_and_schema_vocabularies_match() -> None:
    assert check(_real_markdown(), _real_schema()) == []


def test_real_prose_vocabulary_is_the_full_forty_nine_rule_set() -> None:
    # A sanity floor: the parser found every bulleted group PLUS the
    # comma-separated Model-rules paragraph, not an accidentally-truncated
    # subset (a parsing-anchor regression would silently shrink this).
    prose = prose_rejected_rules(_real_markdown())
    assert len(prose) == 49
    assert "metamodel-index-identity-duplicate" in prose  # the foundational resolver rule
    assert "inheritance-temporality-not-root-owned" in prose  # a root-owned family rule
    assert "inheritance-optimistic-locking-not-root-owned" in prose  # the D-25 rule
    assert "nested-path-first-segment-not-value-object" in prose  # a Predicate-rule bullet
    assert "between-bounds-inverted" in prose  # the bound-ordering Predicate rule
    assert "nested-string-predicate-non-string-member" in prose  # the non-string-member rule
    assert "subtype-write-sibling-attribute" in prose  # a Subtype-write-rule bullet
    assert "temporal-keyed-write-multi-row" in prose  # the Instruction-rule bullet
    assert "inheritance-missing-root" in prose  # a Model-rules paragraph entry
    assert "inheritance-missing-concrete-subtype" in prose  # the family-membership rule
    assert "attribute-outside-active-position" in prose  # the non-family positional rule
    assert "reference-ambiguous-entity-name" in prose  # the reference-resolution rule
    assert "subtype-selection-duplicate-alternative" in prose
    assert "subtype-selection-overlapping-alternatives" in prose
    assert "storage-layout-table-mapping-collision" in prose
    assert "storage-layout-column-collision" in prose
    assert "storage-layout-table-boundary-collision" not in prose
    assert "inheritance-physical-column-collision" not in prose
    assert "inheritance-materialization-key-collision" in prose
    assert "inheritance-layout-not-root-owned" in prose  # the root-owned Storage Layout rule
    assert "storage-layout-document-member-column-override" in prose
    assert "storage-layout-index-over-document-member" in prose


def test_real_schema_enum_is_the_full_forty_nine_rule_set() -> None:
    rules = schema_rejected_rules(_real_schema())
    assert len(rules) == 49
    assert "metamodel-index-identity-duplicate" in rules
    assert "between-bounds-inverted" in rules
    assert "nested-string-predicate-non-string-member" in rules
    assert "storage-layout-table-mapping-collision" in rules
    assert "storage-layout-column-collision" in rules
    assert "attribute-outside-active-position" in rules
    assert "reference-ambiguous-entity-name" in rules
    assert "subtype-selection-duplicate-alternative" in rules
    assert "subtype-selection-overlapping-alternatives" in rules
    assert "temporal-keyed-write-multi-row" in rules
    assert "inheritance-missing-concrete-subtype" in rules
    assert "inheritance-layout-not-root-owned" in rules
    assert "storage-layout-document-member-column-override" in rules
    assert "storage-layout-index-over-document-member" in rules
    assert "storage-layout-table-boundary-collision" not in rules
    assert "inheritance-physical-column-collision" not in rules


_EXPECT_ERRORS = {
    "detached-relationship-load",
    "transaction-time-pin-read-only",
    "write-value-not-stored",
    "write-value-already-stored",
    "write-value-foreign-lifecycle",
}

_FOREIGN_LIFECYCLE_BULLET = (
    "  - `write-value-foreign-lifecycle` — a write verb handed a value produced by a\n"
    "    read through some other framework-managed source than the one it writes\n"
    "    through, the same store or not (`m-unit-work`).\n"
)


def _schema_expect_error_enum(schema: dict[str, object]) -> list[str]:
    """The live per-step `expectError` enum list, for in-place mutation."""
    node = cast("dict[str, Any]", schema)
    for key in ("properties", "when", "properties", "scenario", "items", "properties"):
        node = node[key]
    return cast("list[str]", node["expectError"]["enum"])


def test_real_prose_expect_error_vocabulary_is_the_full_five_code_set() -> None:
    # A sanity floor: the parser read the whole nested bullet list under the
    # `expectError` bullet, not a subset a drifted anchor truncated.
    assert prose_expect_errors(_real_markdown()) == _EXPECT_ERRORS


def test_real_schema_expect_error_enum_is_the_full_five_code_set() -> None:
    assert schema_expect_errors(_real_schema()) == _EXPECT_ERRORS


def test_missing_schema_entry_is_reported() -> None:
    # The exact historical regression: the schema `enum` drops a rule the
    # prose still documents.
    schema = _real_schema()
    enum = schema["properties"]["then"]["properties"]["rejectedRule"]["enum"]  # type: ignore[index]
    enum.remove("inheritance-temporality-not-root-owned")
    errors = check(_real_markdown(), schema)
    assert len(errors) == 1
    assert "inheritance-temporality-not-root-owned" in errors[0]
    assert "absent from the schema enum" in errors[0]


def test_missing_schema_expect_error_entry_is_reported() -> None:
    # The same drift on the second vocabulary: the per-step `expectError` enum
    # drops a code the prose still documents.
    schema = _real_schema()
    _schema_expect_error_enum(schema).remove("write-value-foreign-lifecycle")
    errors = check(_real_markdown(), schema)
    assert len(errors) == 1
    assert "expectError" in errors[0]
    assert "write-value-foreign-lifecycle" in errors[0]
    assert "absent from the schema enum" in errors[0]


def test_missing_prose_expect_error_entry_is_reported() -> None:
    # The reverse drift: the schema declares a code the prose no longer names.
    markdown = _real_markdown().replace(_FOREIGN_LIFECYCLE_BULLET, "")
    assert "write-value-foreign-lifecycle" not in prose_expect_errors(markdown)
    errors = check(markdown, _real_schema())
    assert len(errors) == 1
    assert "expectError" in errors[0]
    assert "write-value-foreign-lifecycle" in errors[0]
    assert "undocumented in m-case-format.md" in errors[0]


def test_expect_error_bullet_moved_out_of_its_owning_section_is_rejected() -> None:
    # The whole bullet list relocates under another heading: the extractor must
    # fail loudly rather than silently report an empty vocabulary.
    markdown = _real_markdown().replace("- **`expectError`** —", "- **`expectErrorMoved`** —", 1)
    with pytest.raises(VocabMismatch, match="expectError"):
        prose_expect_errors(markdown)


def test_schema_expect_error_extractor_rejects_a_malformed_step_shape() -> None:
    # An intermediate node of an unexpected type collapses to the missing-enum
    # mismatch instead of escaping as a KeyError or TypeError.
    malformed: tuple[dict[str, object], ...] = (
        {},
        {"properties": {"when": []}},
        {"properties": {"when": {"properties": {"scenario": {"items": {"properties": {}}}}}}},
    )
    for schema in malformed:
        with pytest.raises(VocabMismatch, match="no expectError enum"):
            schema_expect_errors(schema)


def test_missing_prose_entry_is_reported() -> None:
    # The reverse drift: the schema documents a rule the prose no longer names.
    markdown = _real_markdown().replace(
        "- `abstract-write-target` — a create / update / delete / terminate handle aimed at\n"
        "  an **abstract** root or abstract subtype. Writes are concrete-subtype only.\n",
        "",
    )
    assert "abstract-write-target" not in prose_rejected_rules(markdown)
    errors = check(markdown, _real_schema())
    assert len(errors) == 1
    assert "abstract-write-target" in errors[0]
    assert "undocumented in m-case-format.md" in errors[0]


def test_main_reports_success_on_the_real_corpus() -> None:
    assert main([str(_SPEC_DIR)]) == 0


def test_main_rejects_a_missing_spec_dir_argument() -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2


def test_main_rejects_a_nonexistent_case_format_file(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2
