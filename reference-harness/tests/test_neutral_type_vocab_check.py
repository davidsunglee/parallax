"""Docker-free tests for the neutral-type three-home vocabulary check.

Guards the normative property `neutral_type_vocab_check` exists to prove: the
`NeutralType` variant set is spelled in three places nothing else forces to
agree — the `core/spec/m-core.md` algebra block, the `core/spec/m-descriptor.md`
"Type spellings" table, and the `core/schemas/metamodel.schema.json`
`neutralType` pattern — and a variant added, removed, or renamed in one home
but not the others must fail loudly rather than let the algebra, wire grammar,
and schema silently diverge.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

from reference_harness.neutral_type_vocab_check import (
    VocabMismatch,
    check,
    core_algebra_variants,
    descriptor_spelling_variants,
    main,
    schema_pattern_variants,
)

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "metamodel.schema.json"

_EXPECTED_VARIANTS = {
    "boolean",
    "int32",
    "int64",
    "float32",
    "float64",
    "decimal",
    "string",
    "bytes",
    "date",
    "time",
    "timestamp",
    "uuid",
    "json",
}


def _core_markdown() -> str:
    return (_SPEC_DIR / "m-core.md").read_text(encoding="utf-8")


def _descriptor_markdown() -> str:
    return (_SPEC_DIR / "m-descriptor.md").read_text(encoding="utf-8")


def _schema() -> dict[str, object]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_real_homes_agree() -> None:
    assert check(_core_markdown(), _descriptor_markdown(), _schema()) == []


def test_core_algebra_is_the_full_thirteen_variant_set() -> None:
    # A sanity floor: the fence/comment-stripping parser found every variant of
    # the algebra block, not an accidentally truncated subset.
    assert core_algebra_variants(_core_markdown()) == _EXPECTED_VARIANTS


def test_descriptor_spellings_are_the_full_thirteen_variant_set() -> None:
    assert descriptor_spelling_variants(_descriptor_markdown()) == _EXPECTED_VARIANTS


def test_schema_pattern_is_the_full_thirteen_variant_set() -> None:
    assert schema_pattern_variants(_schema()) == _EXPECTED_VARIANTS


def test_variant_dropped_from_the_schema_pattern_is_reported() -> None:
    # A schema refactor drops one alternation branch the spec homes still declare.
    schema = _schema()
    defs = cast("dict[str, Any]", schema["$defs"])
    neutral_type = cast("dict[str, str]", defs["neutralType"])
    neutral_type["pattern"] = neutral_type["pattern"].replace("boolean|", "")
    errors = check(_core_markdown(), _descriptor_markdown(), schema)
    assert len(errors) == 1
    assert "'boolean'" in errors[0]
    assert "neutralType pattern" in errors[0]


def test_schema_pattern_extractor_rejects_a_non_object_document_root() -> None:
    # A schema file can hold valid JSON whose root is an array: the extractor
    # must report the malformed home as VocabMismatch, not raise AttributeError.
    with pytest.raises(VocabMismatch, match="root is not a JSON object"):
        schema_pattern_variants([])


def test_schema_pattern_extractor_rejects_non_mapping_intermediate_nodes() -> None:
    # `$defs` or `neutralType` nodes of unexpected type collapse to the
    # missing-pattern mismatch instead of escaping as AttributeError/TypeError.
    malformed: tuple[object, ...] = (
        {},
        {"$defs": []},
        {"$defs": {"neutralType": "text"}},
        {"$defs": {"neutralType": {"pattern": 3}}},
    )
    for schema in malformed:
        with pytest.raises(VocabMismatch, match="declares no"):
            schema_pattern_variants(schema)


def test_variant_renamed_in_the_core_algebra_is_reported() -> None:
    # A rename shows up as two one-home variants: the new name exists only in
    # the algebra block, and the old name is now missing from it.
    markdown = _core_markdown().replace("| String | Bytes", "| Str | Bytes", 1)
    errors = check(markdown, _descriptor_markdown(), _schema())
    assert len(errors) == 2
    (str_error,) = [error for error in errors if "'str'" in error]
    assert "Type spellings table" in str_error
    assert "neutralType pattern" in str_error
    (string_error,) = [error for error in errors if "'string'" in error]
    assert "m-core NeutralType algebra block" in string_error


def _algebra_fence(markdown: str) -> str:
    """The full fenced NeutralType algebra block, delimiters included."""
    for fence in re.finditer(r"```text\n.*?```", markdown, re.DOTALL):
        if "NeutralType" in fence.group(0):
            return fence.group(0)
    raise AssertionError("m-core.md carries no fenced NeutralType block")


def test_algebra_fence_moved_out_of_its_owning_section_is_rejected() -> None:
    # The whole fence relocates to the end of the document (another section):
    # the extractor must fail loudly instead of silently accepting the moved fence.
    markdown = _core_markdown()
    fence = _algebra_fence(markdown)
    moved = markdown.replace(fence, "", 1).rstrip() + "\n\n" + fence + "\n"
    with pytest.raises(VocabMismatch, match="no fenced NeutralType algebra block"):
        core_algebra_variants(moved)


def test_duplicate_stale_algebra_fence_is_rejected() -> None:
    # A stale copy (one variant dropped) lands beside the real fence in the owning
    # section: the extractor must refuse to pick one rather than silently prefer
    # whichever comes first.
    markdown = _core_markdown()
    fence = _algebra_fence(markdown)
    stale = fence.replace("Boolean | ", "")
    assert stale != fence
    duplicated = markdown.replace(fence, fence + "\n\n" + stale, 1)
    with pytest.raises(VocabMismatch, match="2 fenced NeutralType blocks"):
        core_algebra_variants(duplicated)


def test_spelling_row_removed_from_the_descriptor_table_is_reported() -> None:
    markdown = _descriptor_markdown().replace("| `Uuid` | `uuid` |\n", "")
    assert "uuid" not in descriptor_spelling_variants(markdown)
    errors = check(_core_markdown(), markdown, _schema())
    assert len(errors) == 1
    assert "'uuid'" in errors[0]
    assert "Type spellings table" in errors[0]


def test_main_reports_success_on_the_real_corpus() -> None:
    assert main([str(_SPEC_DIR)]) == 0


def test_main_rejects_bad_argument_counts() -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2


def test_main_rejects_a_spec_dir_missing_the_owner_specs(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2


def _spec_tree(tmp_path: Path) -> Path:
    """A minimal ``core/`` tree: real spec copies under ``core/spec`` and an
    empty ``core/schemas`` directory (no ``metamodel.schema.json``); returns
    the spec directory."""
    spec_dir = tmp_path / "core" / "spec"
    spec_dir.mkdir(parents=True)
    (spec_dir / "m-core.md").write_text(_core_markdown(), encoding="utf-8")
    (spec_dir / "m-descriptor.md").write_text(_descriptor_markdown(), encoding="utf-8")
    (tmp_path / "core" / "schemas").mkdir()
    return spec_dir


def test_main_reports_an_undecodable_spec_file_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A spec file that exists but is not UTF-8 must exit 2 with the offending
    # path named, not escape as a UnicodeDecodeError traceback.
    spec_dir = _spec_tree(tmp_path)
    (spec_dir / "m-core.md").write_bytes(b"\xff\xfe not utf-8")
    assert main([str(spec_dir)]) == 2
    assert str(spec_dir / "m-core.md") in capsys.readouterr().err


def test_main_reports_a_missing_schema_file_as_a_path_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The schemas directory exists but metamodel.schema.json does not: exit 2
    # with the schema named, not a FileNotFoundError traceback.
    spec_dir = _spec_tree(tmp_path)
    assert main([str(spec_dir)]) == 2
    assert "metamodel.schema.json" in capsys.readouterr().err


def test_main_reports_malformed_schema_json_as_a_malformed_home(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Unparseable schema JSON is a malformed home (exit 1, like VocabMismatch),
    # reported with the schema named, not a json.JSONDecodeError traceback.
    spec_dir = _spec_tree(tmp_path)
    schema_path = tmp_path / "core" / "schemas" / "metamodel.schema.json"
    schema_path.write_text("{ not json", encoding="utf-8")
    assert main([str(spec_dir)]) == 1
    error = capsys.readouterr().err
    assert "malformed schema JSON" in error
    assert "metamodel.schema.json" in error


def test_main_reports_a_non_object_schema_root_as_a_malformed_home(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Valid JSON whose root is an array, not an object, is a malformed home
    # (exit 1) reported with the schema named, not an AttributeError traceback.
    spec_dir = _spec_tree(tmp_path)
    schema_path = tmp_path / "core" / "schemas" / "metamodel.schema.json"
    schema_path.write_text("[]", encoding="utf-8")
    assert main([str(spec_dir)]) == 1
    error = capsys.readouterr().err
    assert "malformed schema JSON" in error
    assert "metamodel.schema.json" in error
    assert "not a JSON object" in error
