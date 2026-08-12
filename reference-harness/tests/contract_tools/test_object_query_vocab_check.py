"""Docker-free tests for the Object Query prose <-> schema vocabulary check.

Guards the normative property `object_query_vocab_check` exists to prove: each
closed vocabulary `core/spec/m-object-query.md` documents in prose — the
Temporal Selection variants and a Sort Key's Null Placement values — is EXACTLY
what `core/schemas/object-query.schema.json` admits, and neither side may drift
from the other. Both vocabularies arrived with the Object Query, and adding a
`$def` is otherwise checked only for meta-schema validity, so without this
check a variant present in one home and absent from the other passes every
gate in the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from reference_harness.object_query_vocab_check import (
    ObjectQueryVocabMismatch,
    check,
    main,
    prose_null_placements,
    prose_temporal_selection_variants,
    schema_null_placements,
    schema_temporal_selection_variants,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "object-query.schema.json"

_TEMPORAL_VARIANTS = {"asOf", "asOfRange", "history"}
_NULL_PLACEMENTS = {"first", "last"}

_HISTORY_TABLE_ROW = (
    '| `history` | `{ "history": {} }` | return the full milestone set on that '
    "dimension; no as-of predicate is injected for it |\n"
)


def _real_markdown() -> str:
    return (_SPEC_DIR / "m-object-query.md").read_text(encoding="utf-8")


def _real_schema() -> dict[str, object]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _temporal_union(schema: dict[str, object]) -> list[dict[str, str]]:
    """The live `temporalSelection` oneOf branch list, for in-place mutation."""
    defs = cast("dict[str, Any]", schema["$defs"])
    return cast("list[dict[str, str]]", defs["temporalSelection"]["oneOf"])


def test_real_prose_and_schema_vocabularies_match() -> None:
    assert check(_real_markdown(), _real_schema()) == []


def test_real_prose_documents_the_three_temporal_selection_variants() -> None:
    assert prose_temporal_selection_variants(_real_markdown()) == _TEMPORAL_VARIANTS


def test_real_schema_admits_the_three_temporal_selection_variants() -> None:
    assert schema_temporal_selection_variants(_real_schema()) == _TEMPORAL_VARIANTS


def test_real_prose_documents_both_null_placements() -> None:
    assert prose_null_placements(_real_markdown()) == _NULL_PLACEMENTS


def test_real_schema_admits_both_null_placements() -> None:
    assert schema_null_placements(_real_schema()) == _NULL_PLACEMENTS


def test_a_temporal_variant_the_schema_drops_is_reported() -> None:
    # The safety-critical direction: the prose still documents `history`, so a
    # query spelling it would fail schema validation.
    schema = _real_schema()
    union = _temporal_union(schema)
    union.remove({"$ref": "#/$defs/temporalHistory"})
    errors = check(_real_markdown(), schema)
    assert len(errors) == 1
    assert "Temporal Selection variants" in errors[0]
    assert "history" in errors[0]
    assert "absent from object-query.schema.json" in errors[0]


def test_a_temporal_variant_the_prose_drops_is_reported() -> None:
    markdown = _real_markdown().replace(_HISTORY_TABLE_ROW, "")
    assert "history" not in prose_temporal_selection_variants(markdown)
    errors = check(markdown, _real_schema())
    assert len(errors) == 1
    assert "Temporal Selection variants" in errors[0]
    assert "undocumented in m-object-query.md" in errors[0]


def test_an_undocumented_new_temporal_variant_is_reported() -> None:
    # The gate's reason to exist: a genuinely new closed-vocabulary branch is
    # meta-schema-valid and otherwise reaches no check at all.
    schema = _real_schema()
    defs = cast("dict[str, Any]", schema["$defs"])
    defs["temporalNow"] = {"type": "object", "required": ["now"], "properties": {"now": {}}}
    _temporal_union(schema).append({"$ref": "#/$defs/temporalNow"})
    errors = check(_real_markdown(), schema)
    assert len(errors) == 1
    assert "now" in errors[0]
    assert "undocumented in m-object-query.md" in errors[0]


def test_a_null_placement_the_schema_drops_is_reported() -> None:
    schema = _real_schema()
    defs = cast("dict[str, Any]", schema["$defs"])
    defs["sortKey"]["properties"]["nulls"]["enum"] = ["last"]
    errors = check(_real_markdown(), schema)
    assert len(errors) == 1
    assert "Null Placement values" in errors[0]
    assert "first" in errors[0]
    assert "absent from object-query.schema.json" in errors[0]


def test_a_null_placement_the_prose_drops_is_reported() -> None:
    markdown = _real_markdown().replace(
        "a Null Placement `nulls` (`first` / `last`, default\n`last`)",
        "a Null Placement `nulls` (`last` only, default\n`last`)",
        1,
    )
    assert prose_null_placements(markdown) == {"last"}
    errors = check(markdown, _real_schema())
    assert len(errors) == 1
    assert "Null Placement values" in errors[0]
    assert "first" in errors[0]
    assert "undocumented in m-object-query.md" in errors[0]


def test_a_relocated_temporal_table_is_rejected_rather_than_read_as_empty() -> None:
    markdown = _real_markdown().replace("Temporal Selection per dimension", "Temporal wrappers", 1)
    with pytest.raises(ObjectQueryVocabMismatch, match="Temporal Selection per dimension"):
        prose_temporal_selection_variants(markdown)


def test_an_emptied_temporal_section_is_rejected_rather_than_read_as_empty() -> None:
    markdown = _real_markdown()
    start = markdown.index("| Selection | Encoding | Meaning |")
    end = markdown.index("The keys are `valid-time`")
    with pytest.raises(ObjectQueryVocabMismatch, match="no Temporal Selection table"):
        prose_temporal_selection_variants(markdown[:start] + markdown[end:])


def test_a_relocated_null_placement_sentence_is_rejected() -> None:
    markdown = _real_markdown().replace("Null Placement `nulls`", "NULL ordering `nulls`", 1)
    with pytest.raises(ObjectQueryVocabMismatch, match="Null Placement"):
        prose_null_placements(markdown)


def test_a_null_placement_sentence_without_a_value_list_is_rejected() -> None:
    markdown = _real_markdown().replace(
        "a Null Placement `nulls` (`first` / `last`, default\n`last`)",
        "a Null Placement `nulls`.",
        1,
    )
    with pytest.raises(ObjectQueryVocabMismatch, match="parenthesized value list"):
        prose_null_placements(markdown)


def test_schema_extractors_reject_malformed_shapes() -> None:
    # A malformed home fails loudly rather than escaping as a KeyError or
    # collapsing to an empty vocabulary that would silently match nothing.
    with pytest.raises(ObjectQueryVocabMismatch, match=r"no \$defs"):
        schema_temporal_selection_variants({})
    with pytest.raises(ObjectQueryVocabMismatch, match="oneOf union"):
        schema_temporal_selection_variants({"$defs": {"temporalSelection": {}}})
    with pytest.raises(ObjectQueryVocabMismatch, match="not a local"):
        schema_temporal_selection_variants(
            {"$defs": {"temporalSelection": {"oneOf": [{"$ref": "other.schema.json#/$defs/x"}]}}}
        )
    with pytest.raises(ObjectQueryVocabMismatch, match="exactly one member"):
        schema_temporal_selection_variants(
            {
                "$defs": {
                    "temporalSelection": {"oneOf": [{"$ref": "#/$defs/branch"}]},
                    "branch": {"required": ["a", "b"]},
                }
            }
        )
    with pytest.raises(ObjectQueryVocabMismatch, match="nulls enum"):
        schema_null_placements({"$defs": {"sortKey": {"properties": {}}}})


def test_main_reports_success_on_the_real_spec() -> None:
    assert main([str(_SPEC_DIR)]) == 0


def test_main_rejects_a_missing_spec_dir_argument() -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2


def test_main_rejects_a_nonexistent_object_query_file(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2
