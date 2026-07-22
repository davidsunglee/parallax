"""Docker-free tests for the case comment-placement gate.

Guards the `m-case-format.md` house rule `case_comment_check` mechanizes:
every compatibility case opens with a header comment block — the only
comments it carries — and after that block the body contains no full-line and
no inline comment. Quoted ``#`` characters and block-scalar content (golden
SQL) are data, never comments.
"""

from __future__ import annotations

from pathlib import Path

from reference_harness.case_comment_check import case_comment_violations, main

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPAT_DIR = _REPO_ROOT / "core" / "compatibility"

_HEADER = "# What the case proves.\n#\n# Why it holds.\n"


def test_real_corpus_is_header_comment_only() -> None:
    assert main([str(_COMPAT_DIR)]) == 0


def test_header_only_case_is_conforming() -> None:
    text = _HEADER + "model: models/balance.yaml\nshape: read\n"
    assert case_comment_violations(text) == []


def test_full_line_body_comment_is_flagged_with_its_line() -> None:
    text = _HEADER + "model: models/balance.yaml\n  # narrates a step\nshape: read\n"
    assert case_comment_violations(text) == [(5, "full-line comment after the case header")]


def test_comment_after_a_blank_line_below_the_header_is_flagged() -> None:
    text = _HEADER + "\n# a second comment block\nmodel: models/balance.yaml\n"
    assert case_comment_violations(text) == [(5, "full-line comment after the case header")]


def test_inline_comment_is_flagged() -> None:
    text = _HEADER + "shape: read  # trailing narration\n"
    assert case_comment_violations(text) == [(4, "inline comment after the case header")]


def test_hash_inside_a_quoted_scalar_is_data() -> None:
    text = _HEADER + "note: \"issue #42 stays quoted\"\ntag: 'x # y'\n"
    assert case_comment_violations(text) == []


def test_hash_without_preceding_whitespace_is_data() -> None:
    text = _HEADER + "column: acct#num\n"
    assert case_comment_violations(text) == []


def test_block_scalar_content_is_never_inspected() -> None:
    text = _HEADER + (
        "then:\n"
        "  statements:\n"
        "    - sql:\n"
        "        pg: |\n"
        "          select 1 # a MariaDB-style SQL comment is data here\n"
        "          from t\n"
        "  affectedRows: 1\n"
    )
    assert case_comment_violations(text) == []


def test_comment_after_a_block_scalar_ends_is_flagged() -> None:
    text = _HEADER + ("sql:\n  pg: |\n    select 1\n# back at document level\n")
    assert case_comment_violations(text) == [(7, "full-line comment after the case header")]


def test_missing_header_is_flagged() -> None:
    assert case_comment_violations("model: models/balance.yaml\n") == [
        (1, "missing the required leading header comment")
    ]


def test_main_reports_a_violating_case(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "m-x-001-ok.yaml").write_text(_HEADER + "shape: read\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 0
    (cases / "m-x-002-bad.yaml").write_text(
        _HEADER + "shape: read\n# stray body comment\n", encoding="utf-8"
    )
    assert main([str(tmp_path)]) == 1


def test_main_rejects_bad_usage(tmp_path: Path) -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2
    assert main([str(tmp_path)]) == 2  # no cases/ child
