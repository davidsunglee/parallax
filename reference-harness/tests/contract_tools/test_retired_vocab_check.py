"""Docker-free tests for the retired-vocabulary deny-list gate.

Guards the closure property `retired_vocab_check` exists to prove, over both
retired families: after the Valid Time / Transaction Time adoption no retired
business/processing temporal phrase or camelCase dimension spelling reappears,
and after the Predicate / Object Query split no spelling that names a query or
its grammar an *operation* reappears — on any active surface, while the labeled
historical / prior-art / rejection-fixture text keeps its original spellings.

Each family's deny-list is a compound rule over an ordinary English stem, so
both directions matter: the retired compound is caught, and the ordinary use of
the same stem stays legal. A compound counts wherever it is written — prose,
camelCase, SCREAMING_SNAKE, a wrapped line, a path component — over every source
git knows about, which is what makes the deny-list an enumerator rather than a
sample.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from reference_harness.retired_vocab_check import check_path, check_text, main, scanned_files

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _initialize_working_tree(root: Path) -> None:
    """Make *root* a git working tree, which is the surface the gate scans.

    The gate asks git for its active sources, so a temporary directory is
    invisible to it until it is initialized.
    """
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)


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


def test_retired_query_compounds_are_detected_in_every_casing_and_number() -> None:
    flagged = [
        "class OperationsTree: ...",
        "class OperationsSchema: ...",
        "OPERATION_SCHEMA_URL = _load()",
        "_OPERATION_URL = _SCHEMAS['predicate.schema.json']['$id']",
        "operation_url = url",
        "OPERATION_REJECTED_RULES: frozenset[str] = frozenset()",
        "rejected_operation = _classify(case)",
        "_REJECTED_OPERATION_CASE = cases / 'x.yaml'",
        "class OperationRejected(ValueError): ...",
        "class RejectedOperations: ...",
        "def test_run_rejected_case_operation_dispatch_classifies_the_rule() -> None:",
        "def test_operation_narrow_in_navigation_filter_accepts_valid() -> None:",
        "def test_concrete_target_root_operation_injects_a_pinned_axis() -> None:",
        "def test_navigate_with_no_inner_operation_accepts() -> None:",
        "def test_predicate_rejects_a_malformed_embedded_operation() -> None:",
        "the query no-drift guard was the operation no-drift guard",
        "operation-to-result query caching",
        "tags: [m-perf-bench, operation-mix]",
        "benchmark fixtures (datasets, op mixes, deep-fetch shapes)",
        "repeated equal operations need not be query-cache hits",
        "Aggregation result and operation spelling for `groupBy`",
        "the operation plan is built once per root",
        "served from the operation cache at zero round trips",
    ]
    for line in flagged:
        assert check_text("f.py", line), line


def test_a_camel_compound_counts_wherever_its_hump_sits() -> None:
    flagged = [
        "myOperationTree = _peel(root)",
        "def buildOperationsSchema() -> None:",
        "parseOperationDocument(payload)",
        "class OperationRuntime: ...",
        "OperationURL = _SCHEMAS['x']['$id']",
        "class OperationAST: ...",
        "class OperationIR: ...",
        "self.opTree = None",
        "def buildOpTree() -> None:",
        "case['caseTargetEntity'] = 'sales.Order'",
        "lowered = _asLoweredFindQuery(root)",
        "entityBusinessDate = clock()",
    ]
    for line in flagged:
        assert check_text("f.py", line), line


def test_an_identifier_the_stem_opens_needs_no_surface_noun() -> None:
    flagged = [
        "operation_model = _load()",
        "OPERATION_MODEL = _load()",
        "op_root = _peel(node)",
        "op_rejected = _classify(case)",
        "operations_shape: dict[str, object] = {}",
        "from .op_ir import lower",
        "core/op/nodes.py",
    ]
    for line in flagged:
        assert check_text("f.py", line), line


def test_the_stem_deeper_in_a_name_keeps_the_surface_noun_rule() -> None:
    # snake_case and kebab-case carry no signal for which word opens a compound,
    # so an occurrence one joiner deep is read as a continuation of the name
    # around it — which is what keeps these live spellings legal.
    legal = [
        "def test_names_decompose_into_scope_operation_and_qualifier() -> None:",
        "writes → operation-buffered mutation → flush-time dirty checking",
        "start/end Attributes are selected for their operation-specific roles",
        "the closed vocabulary in [§2](#2-operation-vocabulary)",
        "a mixed_op_flush coalesces both instructions",
        "matching Reladomo's operation-based list setters",
    ]
    for line in legal:
        assert check_text("f.md", line) == [], line


def test_a_live_spelling_is_masked_only_as_a_whole_identifier() -> None:
    # Each masked spelling is one live name with one casing: the command graph's
    # own operation vocabulary, the exception name session research cites, and
    # the `m-op-list` module's Python scope.
    legal = [
        "_OPERATION_TOKENS: tuple[tuple[str, ...], ...] = tuple(",
        "    for candidate in _OPERATION_TOKENS:",
        "an `InvalidOperationException` thrown by EF Core is unrecoverable",
        "reserved a `parallax.core.op_list` scope",
        "drops its `op_list` prerequisite and scope",
    ]
    for line in legal:
        assert check_text("f.md", line) == [], line
    # A longer name merely ENDING with one is a different name, and the mask must
    # not blank what the characters before it spell.
    flagged = [
        "query_op_list = _load()",
        "find_op_list = _load()",
        "operation_op_list = _load()",
        "_QUERY_OPERATION_TOKENS: tuple[str, ...] = ()",
        "raise query_InvalidOperationException()",
    ]
    for line in flagged:
        assert check_text("f.py", line), line


def test_a_repository_owned_url_is_repository_vocabulary() -> None:
    owned = '"$id": "https://{host}/schemas/{name}.schema.json"'
    assert check_text("core/schemas/x.json", owned.format(host="parallax.dev", name="operation"))
    assert check_text("core/schemas/x.json", owned.format(host="PARALLAX.DEV", name="operation"))
    assert check_text("core/schemas/x.json", owned.format(host="Parallax.Dev", name="operation"))
    clean = owned.format(host="parallax.dev", name="object-query")
    assert check_text("core/schemas/x.json", clean) == []


def test_prose_pressed_against_a_foreign_url_is_still_scanned() -> None:
    assert check_text("docs/x.md", "[external](https://linear.app/x)operation tree")


def test_a_compound_wrapped_across_a_line_is_still_one_phrase() -> None:
    violations = check_text(
        "core/spec/x.md", "the aggregation result and operation\nspelling rule\n"
    )
    assert violations == ["core/spec/x.md:1: retired query vocabulary 'operation spelling'"]
    assert check_text("f.md", "peel the operation\ntree before compiling\n")
    assert check_text("f.md", "pinned to a business\ndate\n")


def test_words_in_different_paragraphs_are_not_one_phrase() -> None:
    assert check_text("f.md", "closes the operation\n\nTree walking comes next.\n") == []
    assert check_text("f.md", "the unit of work is business\n\nDate handling follows.\n") == []


def test_a_list_bullet_opening_the_next_line_is_not_a_joiner() -> None:
    assert check_text("f.md", "each buffered write operation\n- trees are built per hop\n") == []


def test_the_navigation_filters_inner_operand_stays_legal() -> None:
    # `op` on the wire is the inner OPERAND of a navigation filter, mirrored by
    # `Navigate.op` / `Exists.op`. A word before it names that operand, not a
    # query, so only the abbreviation OPENING an identifier is retired.
    legal = [
        "def test_exists_with_no_inner_op_is_a_pure_correlation_check() -> None:",
        "def test_bare_hop_with_no_inner_op_gets_only_the_as_of_term() -> None:",
        "canonical = oa.Exists(rel='Order.items', op=inner_op)",
        "root_op = query.predicate.op",
        "rejected_op = _refused(hop)",
    ]
    for line in legal:
        assert check_text("f.py", line) == [], line


def test_position_words_stay_legal_in_their_spaced_sense() -> None:
    legal = [
        "application code reasons in transactions and operation results",
        "the write operation rejected the row",
        "the root operation of the buffered write tree",
        "the operation embedded in an outer transaction",
    ]
    for line in legal:
        assert check_text("f.md", line) == [], line


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


def test_the_retired_execution_log_module_is_denied_in_every_spelling() -> None:
    retired = [
        "the `m-execution-log` module owns the record",
        "`parallax.core.execution_log` is the scope",
        "core/spec/m-execution-log.md states it",
        "the retained Execution Log is handed back",
        "an ExecutionLogBuilder appends to it",
        "the execution logs it retained across retries",
    ]
    for line in retired:
        assert check_text("f.md", line), line


def test_the_live_execution_lifecycle_spelling_stays_legal() -> None:
    legal = [
        "the `m-execution-lifecycle` module owns the transient stream",
        "`parallax.core.execution_lifecycle` is the scope",
        "one Execution Lifecycle Provider is installed at composition",
        "the executor logs nothing at all",
        "core/compatibility/cases/m-execution-lifecycle-001-standalone-read.yaml",
    ]
    for line in legal:
        assert check_text("f.md", line) == [], line


def test_an_execution_log_violation_names_its_own_family() -> None:
    violations = check_text("docs/x.md", "one\nthe retained execution log\n")
    assert violations == ["docs/x.md:2: retired execution log vocabulary 'execution log'"]


def test_a_urls_own_text_is_not_repository_vocabulary() -> None:
    # A URL's text is fixed by whatever system issued it, so no edit in this
    # repository can change the vocabulary it spells.
    line = (
        "closed by [COR-89](https://linear.app/x/issue/COR-89/let-an-operation-reference-name-it)."
    )
    assert check_text("docs/x.md", line) == []
    # A host that merely opens with the repository's own is somebody else's.
    assert check_text("docs/x.md", "see [x](https://parallax.devil.example/operation-tree)") == []
    # The same retired compound OUTSIDE a URL on the same line still fails.
    assert check_text("docs/x.md", f"the operation reference — {line}")


def test_a_retired_spelling_in_the_path_itself_is_a_violation() -> None:
    flagged = [
        "core/compatibility/cases/m-op-algebra-001-equality.yaml",
        "reference-harness/src/reference_harness/operation_references.py",
        "reference-harness/src/reference_harness/op_validate.py",
        "languages/python/tests/api/test_operation_no_drift.py",
        "core/schemas/operation.schema.json",
        "languages/python/packages/parallax-core/src/parallax/core/op_algebra/__init__.py",
        "docs/business-date-semantics.md",
    ]
    for path in flagged:
        assert check_path(path), path


def test_a_retired_spelling_in_a_directory_component_is_a_violation() -> None:
    assert check_path("languages/python/.../core/op_algebra/nodes.py")
    assert check_path("core/spec/operation-schema/index.md")


def test_live_paths_stay_legal() -> None:
    legal = [
        "core/compatibility/cases/m-op-list-001-lazy-list-is-not-materialized.yaml",
        "core/compatibility/cases/m-predicate-001-equality.yaml",
        "core/compatibility/cases/m-object-query-001-order-by.yaml",
        "core/schemas/predicate.schema.json",
        "languages/python/tests/api/test_object_query_no_drift.py",
        "core/spec/m-document-codec.md",
        "reference-harness/src/reference_harness/query_references.py",
    ]
    for path in legal:
        assert check_path(path) == [], path


def test_a_clean_file_under_a_retired_filename_fails_the_whole_tree_scan(tmp_path: Path) -> None:
    _initialize_working_tree(tmp_path)
    cases = tmp_path / "core" / "compatibility" / "cases"
    cases.mkdir(parents=True)
    clean = "tags: [m-predicate]\n"
    (cases / "m-predicate-001-equality.yaml").write_text(clean)
    assert main([str(tmp_path)]) == 0

    (cases / "m-op-algebra-001-equality.yaml").write_text(clean)
    assert main([str(tmp_path)]) == 1


def test_historical_and_fixture_trees_are_pruned(tmp_path: Path) -> None:
    _initialize_working_tree(tmp_path)
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


def test_a_decision_record_is_exempt_only_from_the_superseded_families() -> None:
    temporal = "the business date this decision fixed\n"
    execution_log = "the retained Execution Log this decision supersedes\n"
    query = "prevented by the operation no-drift guard\n"
    assert check_text("docs/adr/0009-x.md", temporal) == []
    assert check_text("docs/adr/0009-x.md", execution_log) == []
    assert check_text("docs/adr/0009-x.md", query)
    assert check_text("core/spec/m-x.md", temporal)
    assert check_text("core/spec/m-x.md", execution_log)


def test_a_decision_records_retirement_table_names_the_spellings_it_retires() -> None:
    text = (
        "The retirements, one for one:\n"
        "\n"
        "| Retired | What answers now |\n"
        "|---|---|\n"
        "| `FindQuery[T]` | `ObjectQuery[E, S]` |\n"
        "| the operation tree | the Predicate |\n"
        "\n"
        "The operation tree outside the table still fails.\n"
    )
    violations = check_text("docs/adr/0007-x.md", text)
    assert len(violations) == 1
    assert "docs/adr/0007-x.md:8" in violations[0]


def test_non_reladomo_research_docs_are_not_exempt(tmp_path: Path) -> None:
    _initialize_working_tree(tmp_path)
    reladomo = tmp_path / "docs" / "research" / "reladomo"
    session = tmp_path / "docs" / "research" / "session"
    reladomo.mkdir(parents=True)
    session.mkdir(parents=True)
    retired = "the business date / processing date pair\n"
    (reladomo / "notes.md").write_text(retired)
    assert main([str(tmp_path)]) == 0

    (session / "orm-notes.md").write_text(retired)
    assert main([str(tmp_path)]) == 1


def test_a_source_git_knows_is_scanned_whatever_its_directory_or_suffix(tmp_path: Path) -> None:
    _initialize_working_tree(tmp_path)
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("# rebuilds the operation tree\n")
    (tmp_path / "commitlint.config.js").write_text("// keyed to the operation schema\n")
    (tmp_path / "typings.pyi").write_text("class OperationNode: ...\n")
    (tmp_path / "lint.jsonc").write_text('{ "ignore": "op_algebra" }\n')
    scanned = {path.relative_to(tmp_path).as_posix() for path in scanned_files(tmp_path)}
    assert scanned == {
        ".github/workflows/ci.yml",
        "commitlint.config.js",
        "lint.jsonc",
        "typings.pyi",
    }
    assert main([str(tmp_path)]) == 1


def test_what_git_ignores_is_not_an_active_source(tmp_path: Path) -> None:
    _initialize_working_tree(tmp_path)
    (tmp_path / ".gitignore").write_text(".venv/\nreport.json\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "vendored.py").write_text("class OperationNode: ...\n")
    (tmp_path / "report.json").write_text('{"phrase": "the operation tree"}\n')
    assert main([str(tmp_path)]) == 0


def test_an_image_and_a_lockfile_are_not_vocabulary_surface(tmp_path: Path) -> None:
    _initialize_working_tree(tmp_path)
    (tmp_path / "notes.md").write_text("clean\n")
    (tmp_path / "image.png").write_bytes(b"business date")
    (tmp_path / "uv.lock").write_text('name = "operation-tree"\n')
    scanned = {path.name for path in scanned_files(tmp_path)}
    assert scanned == {"notes.md"}


def test_main_rejects_bad_usage(tmp_path: Path) -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2
    assert main([str(tmp_path / "missing")]) == 2


def test_a_root_outside_a_git_working_tree_is_a_usage_error(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2
