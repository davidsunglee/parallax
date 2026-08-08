"""m-case-format (`parallax.conformance.case_format`) loading + selection tests."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import cast

import pytest

from parallax.conformance import case_format
from parallax.conformance.case_format import Case, SelectionFilter


def _case(
    *,
    case_id: str = "m-op-algebra-001",
    shape: str = "read",
    tags: tuple[str, ...] = ("m-op-algebra", "slice-snapshot-1"),
) -> Case:
    return Case(
        path=Path(f"{case_id}-example.yaml"),
        case_id=case_id,
        shape=shape,
        tags=tags,
        model="models/orders.yaml",
        document={},
    )


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_is_module_tag_grammar() -> None:
    assert case_format.is_module_tag("m-op-algebra")
    assert case_format.is_module_tag("m-op-algebra-002")  # a case ID also matches
    assert not case_format.is_module_tag("slice-snapshot-1")
    assert not case_format.is_module_tag("eq")


def test_case_module_tags_and_primary_module() -> None:
    case = _case(tags=("m-op-algebra", "eq", "m-conformance-adapter", "slice-snapshot-1"))
    assert case.module_tags == {"m-op-algebra", "m-conformance-adapter"}
    assert case.primary_module == "m-op-algebra"


def test_primary_module_raises_without_a_module_tag() -> None:
    case = _case(tags=("eq", "slice-snapshot-1"))
    with pytest.raises(ValueError, match="no module tag"):
        _ = case.primary_module


def test_load_case_parses_a_real_corpus_case() -> None:
    path = case_format.default_cases_dir() / "m-op-algebra-002-eq.yaml"
    case = case_format.load_case(path)
    assert case.case_id == "m-op-algebra-002"
    assert case.shape == "read"
    assert case.model == "models/orders.yaml"
    assert "slice-snapshot-1" in case.tags
    assert "m-op-algebra" in case.module_tags
    assert case.primary_module == "m-op-algebra"


def test_load_case_rejects_bad_filename(tmp_path: Path) -> None:
    path = _write(tmp_path, "not-a-case.yaml", "shape: read\ntags: [m-core]\n")
    with pytest.raises(ValueError, match="<module>-NNN"):
        case_format.load_case(path)


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("- just\n- a\n- list\n", "not a mapping"),
        ("tags: [m-core]\n", "`shape`"),
        ("shape: read\n", "`tags`"),
    ],
)
def test_load_case_rejects_malformed_documents(tmp_path: Path, body: str, match: str) -> None:
    path = _write(tmp_path, "m-core-001-bad.yaml", body)
    with pytest.raises(ValueError, match=match):
        case_format.load_case(path)


def test_find_repo_root_and_default_cases_dir() -> None:
    root = case_format.find_repo_root()
    assert (root / "core" / "compatibility" / "cases").is_dir()
    assert case_format.default_cases_dir() == root / "core" / "compatibility" / "cases"


def test_find_repo_root_raises_when_absent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        case_format.find_repo_root(tmp_path)


def test_load_cases_from_a_directory(tmp_path: Path) -> None:
    _write(tmp_path, "m-core-002-a.yaml", "shape: read\ntags: [m-core]\nmodel: m.yaml\n")
    _write(tmp_path, "m-core-001-b.yaml", "shape: read\ntags: [m-core]\nmodel: m.yaml\n")
    cases = case_format.load_cases(tmp_path)
    assert [case.case_id for case in cases] == ["m-core-001", "m-core-002"]


def test_load_cases_over_the_corpus_default() -> None:
    cases = case_format.load_cases()
    assert len(cases) > 300
    assert all(case.shape in case_format.CASE_SHAPES for case in cases)


_FILTER = SelectionFilter(
    modules=frozenset({"m-op-algebra", "m-conformance-adapter"}),
    case_shapes=frozenset({"read"}),
    include=frozenset({"slice-snapshot-1"}),
    exclude=frozenset(),
)


def test_is_selected_admits_an_in_claim_case() -> None:
    assert case_format.is_selected(_case(), _FILTER)


def test_is_selected_rejects_unclaimed_shape() -> None:
    assert not case_format.is_selected(_case(shape="writeSequence"), _FILTER)


def test_is_selected_rejects_module_outside_claim() -> None:
    assert not case_format.is_selected(_case(tags=("m-agg", "slice-snapshot-1")), _FILTER)


def test_is_selected_rejects_case_without_include_tag() -> None:
    assert not case_format.is_selected(_case(tags=("m-op-algebra",)), _FILTER)


def test_is_selected_rejects_excluded_tag() -> None:
    flt = SelectionFilter(
        modules=frozenset({"m-op-algebra"}),
        case_shapes=frozenset({"read"}),
        include=frozenset({"slice-snapshot-1"}),
        exclude=frozenset({"aggregation"}),
    )
    case = _case(tags=("m-op-algebra", "slice-snapshot-1", "aggregation"))
    assert not case_format.is_selected(case, flt)


def test_is_selected_milestone_tags_intersection() -> None:
    case = _case(tags=("m-op-algebra", "slice-snapshot-1"))
    assert case_format.is_selected(case, _FILTER, milestone_tags=["m-op-algebra"])
    assert not case_format.is_selected(case, _FILTER, milestone_tags=["m-sql"])


def test_is_selected_implemented_modules_gate() -> None:
    case = _case(tags=("m-op-algebra", "m-conformance-adapter", "slice-snapshot-1"))
    assert case_format.is_selected(
        case, _FILTER, implemented_modules=frozenset({"m-op-algebra", "m-conformance-adapter"})
    )
    assert not case_format.is_selected(
        case, _FILTER, implemented_modules=frozenset({"m-op-algebra"})
    )


def test_select_preserves_order_and_filters() -> None:
    cases = [
        _case(case_id="m-op-algebra-001"),
        _case(case_id="m-op-algebra-002", shape="conflict"),
        _case(case_id="m-op-algebra-003"),
    ]
    selected = case_format.select(cases, _FILTER, milestone_tags=["m-op-algebra"])
    assert [case.case_id for case in selected] == ["m-op-algebra-001", "m-op-algebra-003"]


# `m-case-format` fixes the corpus's YAML schema at YAML 1.2 core, so a plain
# scalar resolves to null / boolean / integer / float in the core schema's own
# spellings and to a string otherwise. Each case below is a scalar PyYAML's
# default YAML 1.1 resolvers read as a DIFFERENT value, which is how two readers
# of one corpus file come to grade two different documents.
@pytest.mark.parametrize(
    ("scalar", "value"),
    [
        ("on", "on"),
        ("off", "off"),
        ("yes", "yes"),
        ("no", "no"),
        ("NO", "NO"),
        ("True", True),
        ("false", False),
        ("1_000", "1_000"),
        ("1:30", "1:30"),
        ("017", 17),
        ("0o17", 15),
        ("0x1f", 31),
        ("2024-01-01", "2024-01-01"),
        ("2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        ("09:30:00", "09:30:00"),
        ("~", None),
        ("null", None),
        ("42", 42),
        ("4.5", 4.5),
        (".inf", float("inf")),
        ("-.inf", float("-inf")),
    ],
)
def test_a_plain_scalar_resolves_under_the_core_schema(scalar: str, value: object) -> None:
    assert case_format.safe_load_yaml(f"key: {scalar}\n") == {"key": value}


def test_a_temporal_scalar_stays_its_portable_literal() -> None:
    # The corollary that matters most: a corpus temporal value reaches this
    # implementation as the ISO text `m-document-codec` defines, decoded against
    # the declared type like any other portable literal — never as a host date
    # object the loader constructed, which a grader reading the same file through
    # a different loader would never see.
    loaded = case_format.safe_load_yaml("orderedOn: 2024-01-05\n")
    assert loaded == {"orderedOn": "2024-01-05"}
    assert not isinstance(cast("dict[str, object]", loaded)["orderedOn"], datetime.date)


def test_quoting_an_ambiguous_scalar_changes_nothing() -> None:
    assert case_format.safe_load_yaml("country: NO\n") == case_format.safe_load_yaml(
        'country: "NO"\n'
    )


def test_a_not_a_number_scalar_resolves_to_a_float() -> None:
    loaded = cast("dict[str, float]", case_format.safe_load_yaml("key: .nan\n"))
    assert loaded["key"] != loaded["key"]
