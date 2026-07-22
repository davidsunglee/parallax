"""Docker-free tests for the retired-vocabulary deny-list gate.

Guards the closure property `retired_vocab_check` exists to prove: after the
Valid Time / Transaction Time adoption, no retired business/processing
temporal phrase reappears on any active surface, while the labeled
historical / prior-art / rejection-fixture text keeps its original spellings.
"""

from __future__ import annotations

from pathlib import Path

from reference_harness.retired_vocab_check import check_text, main, scanned_files

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_real_tree_is_clean() -> None:
    assert main([str(_REPO_ROOT)]) == 0


def test_retired_phrases_are_detected() -> None:
    flagged = [
        "the business date of the change",
        "pinned to a Business Time instant",
        "the processing-time audit history",
        "an effective date column",
        "stamped with the system date",
        "the business/processing dimension pair",
        "the business-axis lower bound",
        "carries a processing as-of axis",
    ]
    for line in flagged:
        assert check_text("f.md", line), line


def test_retired_identifier_spellings_are_detected() -> None:
    flagged = [
        "business_binds.extend([binds[from_z_pos]])",
        "business_coords = [set_cols[column]]",
        "processing_history = business_history['operand']",
        "instruction['businessFrom'] = value",
        "processingDate is the retired spelling",
        "the business-from discriminator",
        "a processing-latest read",
        "def test_insert_then_update_keeps_the_business_bound() -> None:",
        "def test_requires_processing_temporal_update_payload() -> None:",
    ]
    for line in flagged:
        assert check_text("f.py", line), line


def test_non_temporal_business_and_processing_words_stay_legal() -> None:
    legal = [
        "the physical key is the business key plus each start column",
        "a business/developer name like `id`, not a physical column",
        "operation processing, SQL and database execution",
        "the business logic never sees physical columns",
        "processing continues with the next statement",
        "a unique business column earns a secondary index",
    ]
    for line in legal:
        assert check_text("f.md", line) == [], line


def test_avoid_lines_are_exempt() -> None:
    text = (
        "**Valid Time**:\nThe dimension.\n_Avoid_: business time, business date, effective date\n"
    )
    assert check_text("CONTEXT.md", text) == []


def test_prior_art_paragraph_is_exempt() -> None:
    text = (
        "### Temporal And Milestoning\n"
        "\n"
        "Prior art: the terms follow Snodgrass's vocabulary; Reladomo's\n"
        "business/processing dates are the same dimensions under retired names.\n"
        "\n"
        "**Temporal Dimension**:\n"
    )
    assert check_text("CONTEXT.md", text) == []


def test_a_paragraph_not_labeled_prior_art_is_not_exempt() -> None:
    text = "Some prose paragraph.\nIt mentions the business date here.\n"
    violations = check_text("f.md", text)
    assert len(violations) == 1
    assert "f.md:2" in violations[0]
    assert "business date" in violations[0]


def test_violation_reports_path_line_and_phrase() -> None:
    violations = check_text("docs/x.md", "one\ntwo\nthe processing instant\n")
    assert violations == ["docs/x.md:3: retired temporal vocabulary 'processing instant'"]


def test_historical_and_fixture_trees_are_pruned(tmp_path: Path) -> None:
    (tmp_path / "docs" / "research" / "reladomo").mkdir(parents=True)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "core" / "compatibility" / "descriptor-errors").mkdir(parents=True)
    (tmp_path / "core" / "spec").mkdir(parents=True)
    retired = "the business date / processing date pair\n"
    (tmp_path / "docs" / "research" / "reladomo" / "notes.md").write_text(retired)
    (tmp_path / "docs" / "adr" / "0001-x.md").write_text(retired)
    (tmp_path / "core" / "compatibility" / "descriptor-errors" / "x.yaml").write_text(retired)
    (tmp_path / "core" / "spec" / "clean.md").write_text("Valid Time / Transaction Time only\n")
    assert main([str(tmp_path)]) == 0

    (tmp_path / "core" / "spec" / "dirty.md").write_text(retired)
    assert main([str(tmp_path)]) == 1


def test_only_text_source_kinds_are_scanned(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("clean\n")
    (tmp_path / "image.png").write_bytes(b"business date")
    (tmp_path / ".hidden.md").write_text("business date\n")
    scanned = {path.name for path in scanned_files(tmp_path)}
    assert scanned == {"notes.md"}


def test_main_rejects_bad_usage(tmp_path: Path) -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2
    assert main([str(tmp_path / "missing")]) == 2
