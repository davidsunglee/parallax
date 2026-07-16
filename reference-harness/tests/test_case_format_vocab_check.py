"""Docker-free tests for the `rejectedRule` prose <-> schema vocabulary check.

Guards the normative property `case_format_vocab_check` exists to prove: the
`rejectedRule` vocabulary `core/spec/m-case-format.md` documents in prose is
EXACTLY the `enum` `core/schemas/compatibility-case.schema.json` declares —
neither side may drift from the other (the residual-round finding: the schema
`enum` was once missing `inheritance-temporal-axes-not-root-owned` while the
prose was already correct, a safety-critical gap since a case pinning that
rule would fail schema validation regardless of implementation correctness).
"""

from __future__ import annotations

import json
from pathlib import Path

from reference_harness.case_format_vocab_check import (
    check,
    main,
    prose_rejected_rules,
    schema_rejected_rules,
)

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"


def _real_markdown() -> str:
    return (_SPEC_DIR / "m-case-format.md").read_text(encoding="utf-8")


def _real_schema() -> dict[str, object]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_real_prose_and_schema_vocabularies_match() -> None:
    assert check(_real_markdown(), _real_schema()) == []


def test_real_prose_vocabulary_is_the_full_thirty_rule_set() -> None:
    # A sanity floor: the parser found every bulleted group PLUS the
    # comma-separated Model-rules paragraph, not an accidentally-truncated
    # subset (a parsing-anchor regression would silently shrink this).
    prose = prose_rejected_rules(_real_markdown())
    assert len(prose) == 30
    assert "inheritance-temporal-axes-not-root-owned" in prose  # the residual-round rule
    assert "nested-path-first-segment-not-value-object" in prose  # an Operation-rule bullet
    assert "subtype-write-sibling-attribute" in prose  # a Subtype-write-rule bullet
    assert "inheritance-missing-root" in prose  # a Model-rules paragraph entry


def test_real_schema_enum_is_the_full_thirty_rule_set() -> None:
    assert len(schema_rejected_rules(_real_schema())) == 30


def test_missing_schema_entry_is_reported() -> None:
    # The exact historical regression: the schema `enum` drops a rule the
    # prose still documents.
    schema = _real_schema()
    enum = schema["properties"]["then"]["properties"]["rejectedRule"]["enum"]  # type: ignore[index]
    enum.remove("inheritance-temporal-axes-not-root-owned")
    errors = check(_real_markdown(), schema)
    assert len(errors) == 1
    assert "inheritance-temporal-axes-not-root-owned" in errors[0]
    assert "absent from the schema enum" in errors[0]


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
