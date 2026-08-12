"""Docker-free tests for the retired-vocabulary deny-list gate.

Guards the closure property `retired_vocab_check` exists to prove, over both
retired families: after the Valid Time / Transaction Time adoption no retired
business/processing temporal phrase or camelCase dimension spelling reappears,
and after the Predicate / Object Query split no spelling that names a query or
its grammar an *operation* reappears — on any active surface, while the labeled
historical / prior-art / rejection-fixture text keeps its original spellings.

Each family's deny-list is a compound rule over an ordinary English stem, so
both directions matter: the retired compound is caught, and the ordinary use of
the same stem stays legal.
"""

from __future__ import annotations

from pathlib import Path

from reference_harness.retired_vocab_check import check_text, main, scanned_files

_REPO_ROOT = Path(__file__).resolve().parents[3]


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


def test_retired_dimension_spellings_are_detected() -> None:
    flagged = [
        '"dimension": { "enum": ["validTime", "transactionTime"] }',
        "pin: { transactionTime: '2024-01-01T00:00:00+00:00' }",
        "- dimension: validTime",
    ]
    for line in flagged:
        assert check_text("f.yaml", line), line


def test_core_dimension_variant_names_stay_legal() -> None:
    legal = [
        "TemporalDimension = ValidTime | TransactionTime",
        "the valid-time axis precedes the transaction-time axis",
        "TemporalDimension.VALID_TIME",
        "validTimestamp = clock()",
    ]
    for line in legal:
        assert check_text("f.py", line) == [], line


def test_camel_compounds_cover_every_noun_family() -> None:
    flagged = [
        "businessInterval = window",
        "processingPins = held_views",
        "obj.businessValidity",
        "a processingDiscriminator column",
        "businessCorrection entries",
        "businessBinds.extend(binds)",
        "processingMilestones[0]",
        "businessTimes list",
    ]
    for line in flagged:
        assert check_text("f.py", line), line


def test_camel_compound_matches_at_string_edges() -> None:
    assert check_text("f.py", "businessInterval")
    assert check_text("f.py", "x = processingPin")


def test_camel_compound_followed_by_an_uppercase_hump_is_detected() -> None:
    assert check_text("f.py", "businessFromValue = 1")


def test_digit_and_lowercase_continuations_are_different_identifiers() -> None:
    legal = [
        "businessTime2 = clock()",
        "business_time2 = clock()",
        "businessTimeout = 30",
    ]
    for line in legal:
        assert check_text("f.py", line) == [], line


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


def test_retired_query_phrases_are_detected() -> None:
    flagged = [
        "peel the operation tree before compiling",
        "every operation node carries one tag",
        "validates against the operation schema",
        "the operation wrapper spine is rebuilt per hop",
        "an operation document round-trips through serde",
        "the operation grammar is recursive",
        "the read envelope's operation field",
        "operation lowering happens once",
        "a query operation reaching the database",
        "the find operation is refused before I/O",
        "an operation-backed lazy list",
    ]
    for line in flagged:
        assert check_text("f.md", line), line


def test_retired_query_identifier_spellings_are_detected() -> None:
    flagged = [
        "from parallax.core.op_algebra import All",
        "the m-op-algebra catalogue row",
        "core/schemas/operation.schema.json",
        "from .operation_references import collect_reference_classes",
        "import op_validate",
        "class OperationNode: ...",
        "class OperationError(ValueError): ...",
        "class OperationRejectedError(ValueError): ...",
        "def build_opAlgebra() -> None:",
        "def validate_operation(root, op, model) -> None:",
        "malformed_operation: dict[str, object] = {}",
        "query = FindQuery(target, predicate)",
        "lowered = LoweredFindQuery(target, operation)",
        "find_query = _step_query(step)",
        'ids=["predicate", "find-query"]',
        'case["targetEntity"] = "sales.Order"',
        "target_entity = query.get('target')",
        "class QueryOperation: ...",
    ]
    for line in flagged:
        assert check_text("f.py", line), line


def test_ordinary_operation_uses_stay_legal() -> None:
    # The stem is ordinary English and names real, live concepts: a database
    # write, the command grammar's own operation vocabulary, and `m-op-list`.
    legal = [
        "each write operation is buffered until flush",
        "captured once at an outer database operation boundary",
        "operation processing, SQL and database execution",
        "`m-op-list` — query-backed list results",
        "a recipe whose operation slot holds no vocabulary entry",
        "the document operations that build, read, and patch",
        "a mixed-op flush coalesces both instructions",
        "a no-op update emits no DML",
        "the write operation rejected the row",
        "BLOCKING_OPERATIONS holds every verdict-bearing entry",
        "`non-canonical-operation` names the command grammar's own diagnostic",
        "a writer-operation failure is eager",
        "the trailing find queries the open current-to-infinity set",
        "the repeated-find / query-cache claim moved to m-process-cache",
        "the relationship's target entity is the far side",
        "top-level rows are compared order-insensitively",
        "the loop_body is a pure function",
        "Optional[str] is the annotation",
    ]
    for line in legal:
        assert check_text("f.md", line) == [], line


def test_query_violation_names_its_own_family() -> None:
    violations = check_text("docs/x.md", "one\nthe operation tree\n")
    assert violations == ["docs/x.md:2: retired query vocabulary 'operation tree'"]


def test_a_urls_own_path_is_not_repository_vocabulary() -> None:
    # An issue slug is fixed by the system that issued it: no edit here can
    # change it, so it must not fail a gate over this repository's own prose.
    line = (
        "closed by [COR-89](https://linear.app/x/issue/COR-89/let-an-operation-reference-name-it)."
    )
    assert check_text("docs/x.md", line) == []
    # The same retired compound OUTSIDE a URL on the same line still fails.
    assert check_text("docs/x.md", f"the operation reference — {line}")


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


def test_non_reladomo_research_docs_are_not_exempt(tmp_path: Path) -> None:
    reladomo = tmp_path / "docs" / "research" / "reladomo"
    session = tmp_path / "docs" / "research" / "session"
    reladomo.mkdir(parents=True)
    session.mkdir(parents=True)
    retired = "the business date / processing date pair\n"
    (reladomo / "notes.md").write_text(retired)
    assert main([str(tmp_path)]) == 0

    (session / "orm-notes.md").write_text(retired)
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
