"""m-case-format (`parallax.conformance.case_format`) loading + selection tests."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import cast

import pytest
import yaml

from parallax.conformance import case_format
from parallax.conformance.case_format import Case, SelectionFilter
from parallax.core.base import FLOAT32, FLOAT64, INT32, INT64, ManagedValue, matches_neutral_type
from parallax.core.wire import (
    WireDecodingError,
    WireEncodingError,
    WireValue,
    decode_canonical_wire,
    decode_wire,
    encode_wire,
)
from parallax.snapshot import DatabaseOptions


def _case(
    *,
    case_id: str = "m-predicate-001",
    shape: str = "read",
    tags: tuple[str, ...] = ("m-predicate", "slice-snapshot-1"),
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


def _isolation_case(document: dict[str, object]) -> Case:
    return Case(
        path=Path("m-db-error-009-example.yaml"),
        case_id="m-db-error-009",
        shape="error",
        tags=("m-db-error", "isolation"),
        model="models/error-cases.yaml",
        document=document,
    )


@pytest.mark.parametrize(
    ("serialized", "literal"),
    [
        ("read-committed", "read_committed"),
        ("repeatable-read", "repeatable_read"),
        ("serializable", "serializable"),
    ],
)
def test_a_core_serialized_level_converts_to_its_python_literal(
    serialized: str, literal: str
) -> None:
    assert case_format.isolation_literal(serialized) == literal


@pytest.mark.parametrize("declared", ["read-uncommitted", "read_committed", "repeatable_read", ""])
def test_a_token_outside_the_core_vocabulary_is_refused_at_ingress(declared: str) -> None:
    # `when.uow.isolation` is closed to the three core serialized tokens, so a
    # value reaching here that the corpus does not spell is a corpus defect,
    # reported where it is read rather than carried into a runner as a string.
    # A Python level's own spelling is refused with the rest: accepting it would
    # make the language's identifier a second name for a core-authored token.
    with pytest.raises(ValueError, match="isolation must be one of"):
        case_format.isolation_literal(declared)


# --------------------------------------------------------------------------- #
# The sparse `db.transact` projection: only what the case authored travels.   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "document",
    [
        {},
        {"when": {}},
        {"when": {"uow": {}}},
    ],
)
def test_an_undeclared_request_projects_no_keyword(document: dict[str, object]) -> None:
    assert case_format.transaction_keywords(_isolation_case(document)) == {}


def test_every_authored_field_projects_under_its_python_name() -> None:
    case = _isolation_case(
        {
            "when": {
                "uow": {
                    "maxRetries": 2,
                    "concurrency": "locking",
                    "retryOptimisticConflicts": True,
                    "isolation": "repeatable-read",
                }
            }
        }
    )
    assert case_format.transaction_keywords(case) == {
        "max_retries": 2,
        "concurrency": "locking",
        "retry_optimistic_conflicts": True,
        "isolation": "repeatable_read",
    }


def test_authored_zero_and_false_survive_and_absent_keys_stay_absent() -> None:
    # `0` and `false` are values the case wrote, distinguishable from omission
    # by presence alone: neither is dropped as falsy, and the two fields the
    # case did not write are not filled from any default.
    case = _isolation_case({"when": {"uow": {"maxRetries": 0, "retryOptimisticConflicts": False}}})
    keywords = case_format.transaction_keywords(case)
    assert keywords == {"max_retries": 0, "retry_optimistic_conflicts": False}
    assert "concurrency" not in keywords
    assert "isolation" not in keywords


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maxRetries", None),
        ("concurrency", None),
        ("retryOptimisticConflicts", None),
        ("isolation", None),
        ("maxRetries", True),
        ("maxRetries", -1),
        ("maxRetries", "2"),
        ("concurrency", "pessimistic"),
        ("retryOptimisticConflicts", 1),
        ("isolation", "read_committed"),
    ],
)
def test_a_null_or_malformed_request_field_is_refused_at_ingress(field: str, value: object) -> None:
    # Authored `null` is neither omission nor a value production admits, so the
    # case is reported where it is read; the same refusal covers a value outside
    # the field's type or vocabulary, and every refusal names the placement the
    # field was authored at.
    case = _isolation_case({"when": {"uow": {field: value}}})
    with pytest.raises(ValueError, match=rf"when\.uow\.{field}"):
        case_format.transaction_keywords(case)


def test_the_retired_retries_request_key_is_refused() -> None:
    case = _isolation_case({"when": {"uow": {"retries": 2}}})
    with pytest.raises(ValueError, match="retries"):
        case_format.transaction_keywords(case)


def test_a_non_mapping_uow_is_refused_by_name() -> None:
    case = _isolation_case({"when": {"uow": "locking"}})
    with pytest.raises(ValueError, match=r"when\.uow must be a mapping"):
        case_format.transaction_keywords(case)


def test_a_join_steps_vocabulary_refusal_names_the_join_placement() -> None:
    with pytest.raises(
        ValueError, match=r"when\.boundary\[1\]\.isolation: isolation must be one of"
    ):
        case_format.request_keywords(
            {"action": "join", "isolation": "read_committed"}, where="when.boundary[1]"
        )


def test_a_join_step_projects_through_the_same_decoder() -> None:
    step = {
        "action": "join",
        "isolation": "serializable",
        "maxRetries": 0,
        "concurrency": "locking",
        "retryOptimisticConflicts": False,
        "note": "x",
    }
    assert case_format.request_keywords(step, where="join") == {
        "isolation": "serializable",
        "max_retries": 0,
        "concurrency": "locking",
        "retry_optimistic_conflicts": False,
    }


# --------------------------------------------------------------------------- #
# The root record: `given.databaseOptions` alone, built-ins for the rest.      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "document",
    [
        {},
        {"given": {}},
        {"given": {"fixtures": True}},
        {"given": {"databaseOptions": {}}},
        {"when": {"uow": {"isolation": "serializable", "maxRetries": 0}}},
    ],
)
def test_an_unconfigured_root_is_the_records_own_defaults(document: dict[str, object]) -> None:
    # A request under `when.uow` is not configuration: the root a case connects
    # is built from `given.databaseOptions` alone, so an authored request never
    # leaks into the record production resolves it against.
    assert case_format.database_options(_isolation_case(document)) == DatabaseOptions()


def test_every_configured_root_field_reaches_the_record_and_the_rest_stay_built_in() -> None:
    case = _isolation_case(
        {"given": {"databaseOptions": {"maxRetries": 0, "isolation": "repeatable-read"}}}
    )
    assert case_format.database_options(case) == DatabaseOptions(
        max_retries=0, isolation="repeatable_read"
    )
    fully = _isolation_case(
        {
            "given": {
                "databaseOptions": {
                    "maxRetries": 2,
                    "concurrency": "locking",
                    "retryOptimisticConflicts": True,
                    "isolation": "serializable",
                }
            }
        }
    )
    assert case_format.database_options(fully) == DatabaseOptions(
        max_retries=2,
        concurrency="locking",
        retry_optimistic_conflicts=True,
        isolation="serializable",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maxRetries", None),
        ("concurrency", None),
        ("retryOptimisticConflicts", None),
        ("isolation", None),
        ("maxRetries", -1),
        ("maxRetries", True),
        ("concurrency", "pessimistic"),
        ("retryOptimisticConflicts", "yes"),
        ("isolation", "read-uncommitted"),
    ],
)
def test_a_null_or_malformed_root_field_is_refused_at_ingress(field: str, value: object) -> None:
    # The root block is decoded by the same field rules as a request, and the
    # refusal names the ROOT placement: a malformed root field is a defect in
    # `given.databaseOptions`, never reported as though `when.uow` spelled it.
    case = _isolation_case({"given": {"databaseOptions": {field: value}}})
    with pytest.raises(ValueError, match=rf"given\.databaseOptions\.{field}") as refused:
        case_format.database_options(case)
    assert "when.uow" not in str(refused.value)


def test_a_root_naming_the_retired_retries_key_or_no_mapping_is_refused() -> None:
    with pytest.raises(ValueError, match="retries"):
        case_format.database_options(
            _isolation_case({"given": {"databaseOptions": {"retries": 2}}})
        )
    with pytest.raises(ValueError, match=r"given\.databaseOptions must be a mapping"):
        case_format.database_options(_isolation_case({"given": {"databaseOptions": "locking"}}))


def test_effective_options_lay_the_authored_request_over_the_root() -> None:
    # The grading-side resolution: explicit over root over built-in, one field
    # at a time. Neither input is changed by it — the root record still holds
    # only what the case configured, and the request only what it authored.
    case = _isolation_case(
        {
            "given": {"databaseOptions": {"maxRetries": 2, "concurrency": "locking"}},
            "when": {"uow": {"maxRetries": 5, "isolation": "serializable"}},
        }
    )
    assert case_format.effective_options(case) == DatabaseOptions(
        max_retries=5, concurrency="locking", isolation="serializable"
    )
    assert case_format.database_options(case) == DatabaseOptions(
        max_retries=2, concurrency="locking"
    )
    assert case_format.transaction_keywords(case) == {
        "max_retries": 5,
        "isolation": "serializable",
    }


def test_an_authored_zero_or_false_overrides_a_configured_root() -> None:
    case = _isolation_case(
        {
            "given": {"databaseOptions": {"maxRetries": 3, "retryOptimisticConflicts": True}},
            "when": {"uow": {"maxRetries": 0, "retryOptimisticConflicts": False}},
        }
    )
    assert case_format.effective_options(case) == DatabaseOptions(
        max_retries=0, retry_optimistic_conflicts=False
    )


def test_effective_options_of_an_unconfigured_unrequesting_case_are_the_built_ins() -> None:
    assert case_format.effective_options(_isolation_case({})) == DatabaseOptions()


def test_is_module_tag_grammar() -> None:
    assert case_format.is_module_tag("m-predicate")
    assert case_format.is_module_tag("m-predicate-002")  # a case ID also matches
    assert not case_format.is_module_tag("slice-snapshot-1")
    assert not case_format.is_module_tag("eq")


def test_case_module_tags_and_primary_module() -> None:
    case = _case(tags=("m-predicate", "eq", "m-conformance-adapter", "slice-snapshot-1"))
    assert case.module_tags == {"m-predicate", "m-conformance-adapter"}
    assert case.primary_module == "m-predicate"


def test_primary_module_raises_without_a_module_tag() -> None:
    case = _case(tags=("eq", "slice-snapshot-1"))
    with pytest.raises(ValueError, match="no module tag"):
        _ = case.primary_module


def test_load_case_parses_a_real_corpus_case() -> None:
    path = case_format.default_cases_dir() / "m-predicate-002-eq.yaml"
    case = case_format.load_case(path)
    assert case.case_id == "m-predicate-002"
    assert case.shape == "read"
    assert case.model == "models/orders.yaml"
    assert "slice-snapshot-1" in case.tags
    assert "m-predicate" in case.module_tags
    assert case.primary_module == "m-predicate"


def test_authority_cases_decode_to_closed_ingress_values() -> None:
    subject = case_format.load_case(
        case_format.default_cases_dir()
        / "m-execution-authority-001-equal-subject-authority-joins.yaml"
    )
    assert case_format.actor_selection(subject) == case_format.SubjectSelection("alice", "role-a")
    subject_when = cast("dict[str, object]", subject.document["when"])
    boundary = cast("list[dict[str, object]]", subject_when["boundary"])
    assert case_format.step_actor_selection(boundary[1], where="when.boundary[1]") is None
    assert case_format.step_actor_selection(
        boundary[2], where="when.boundary[2]"
    ) == case_format.SubjectSelection("alice", "role-a")

    login = case_format.load_case(
        case_format.default_cases_dir()
        / "m-execution-authority-005-equal-login-authority-joins.yaml"
    )
    assert case_format.actor_selection(login) == case_format.DatabaseLoginSelection()
    login_when = cast("dict[str, object]", login.document["when"])
    login_boundary = cast("list[dict[str, object]]", login_when["boundary"])
    assert (
        case_format.step_actor_selection(login_boundary[1], where="when.boundary[1]")
        == case_format.DatabaseLoginSelection()
    )


@pytest.mark.parametrize(
    "selection",
    [
        {"actorIdentity": {"kind": "subject", "value": "alice"}},
        {"databaseAuthorization": "role-a"},
        {"actorIdentity": None},
        {"databaseAuthorization": None},
        {"actorIdentity": {"kind": "service"}},
        {"actorIdentity": {"kind": "subject"}, "databaseAuthorization": "role-a"},
        {
            "actorIdentity": {"kind": "subject", "value": "alice", "extra": True},
            "databaseAuthorization": "role-a",
        },
        {"actorIdentity": {"kind": "database-login", "value": "runner"}},
        {
            "actorIdentity": {"kind": "database-login"},
            "databaseAuthorization": "role-a",
        },
        {
            "actorIdentity": {"kind": "database-login"},
            "databaseAuthorization": None,
        },
        {
            "actorIdentity": {"kind": "subject", "value": "db-login:runner"},
            "databaseAuthorization": "role-a",
        },
    ],
)
def test_authority_reader_rejects_malformed_combinations(
    selection: dict[str, object],
) -> None:
    case = Case(
        path=Path("m-execution-authority-999-invalid.yaml"),
        case_id="m-execution-authority-999",
        shape="boundary",
        tags=("m-execution-authority",),
        model="models/account.yaml",
        document={"when": selection},
    )
    with pytest.raises(ValueError, match=r"actorIdentity|databaseAuthorization"):
        case_format.actor_selection(case)


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
    modules=frozenset({"m-predicate", "m-conformance-adapter"}),
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
    assert not case_format.is_selected(_case(tags=("m-predicate",)), _FILTER)


def test_is_selected_rejects_excluded_tag() -> None:
    flt = SelectionFilter(
        modules=frozenset({"m-predicate"}),
        case_shapes=frozenset({"read"}),
        include=frozenset({"slice-snapshot-1"}),
        exclude=frozenset({"aggregation"}),
    )
    case = _case(tags=("m-predicate", "slice-snapshot-1", "aggregation"))
    assert not case_format.is_selected(case, flt)


def test_is_selected_milestone_tags_intersection() -> None:
    case = _case(tags=("m-predicate", "slice-snapshot-1"))
    assert case_format.is_selected(case, _FILTER, milestone_tags=["m-predicate"])
    assert not case_format.is_selected(case, _FILTER, milestone_tags=["m-sql"])


def test_is_selected_implemented_modules_gate() -> None:
    case = _case(tags=("m-predicate", "m-conformance-adapter", "slice-snapshot-1"))
    assert case_format.is_selected(
        case, _FILTER, implemented_modules=frozenset({"m-predicate", "m-conformance-adapter"})
    )
    assert not case_format.is_selected(
        case, _FILTER, implemented_modules=frozenset({"m-predicate"})
    )


def test_select_preserves_order_and_filters() -> None:
    cases = [
        _case(case_id="m-predicate-001"),
        _case(case_id="m-predicate-002", shape="conflict"),
        _case(case_id="m-predicate-003"),
    ]
    selected = case_format.select(cases, _FILTER, milestone_tags=["m-predicate"])
    assert [case.case_id for case in selected] == ["m-predicate-001", "m-predicate-003"]


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


def test_the_corpus_reads_the_same_under_either_yaml_parser() -> None:
    # The core schema is applied after parsing, in the resolver and constructor
    # tables, so the parser the installed PyYAML wheel carries — libyaml's or its
    # own — must leave every corpus document unchanged; a machine without libyaml
    # reads the corpus through the fallback this pins against.
    shipped = case_format._Yaml12CoreLoader  # pyright: ignore[reportPrivateUsage] - the twin below is built from the shipped loader's own tables

    class PurePython(yaml.SafeLoader):
        pass

    PurePython.yaml_implicit_resolvers = dict(shipped.yaml_implicit_resolvers)
    PurePython.yaml_constructors = dict(shipped.yaml_constructors)
    documents = sorted(case_format.default_cases_dir().rglob("*.yaml"))
    assert documents
    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert case_format.safe_load_yaml(text) == yaml.load(text, Loader=PurePython), path


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


def test_an_empty_plain_scalar_is_null() -> None:
    # The core schema's null vocabulary is `null` / `Null` / `NULL` / `~` / the EMPTY
    # scalar, and the empty one is the alternative a resolver table keyed by first
    # character cannot express: an empty scalar has no first character, so a table
    # that spells the entry as one registers a bucket nothing reaches and `key:`
    # silently becomes the empty STRING — a different document, and one that reads as
    # a present value where the corpus wrote an absent one.
    assert case_format.safe_load_yaml("key:\n") == {"key": None}
    assert case_format.safe_load_yaml("key:\n") == case_format.safe_load_yaml("key: null\n")
    assert case_format.safe_load_yaml("outer:\n  inner:\n") == {"outer": {"inner": None}}


def test_a_number_carries_the_digits_it_was_authored_with() -> None:
    # Which float a number names depends on the declared width. The observable
    # proof is direct-from-token decoding, never the private provenance carrier.
    loaded = cast("dict[str, object]", case_format.safe_load_yaml("ratio: 1.0000000596046448\n"))
    authored = cast("WireValue", loaded["ratio"])
    assert authored == float("1.0000000596046448")
    assert decode_wire(FLOAT32, authored) == 1.0 + 2.0**-23


def test_a_float32_rounds_from_the_authored_digits_not_from_the_carrier() -> None:
    # `1.0000000596046448` lies ABOVE the midpoint between binary32 `1.0` and its
    # successor, so one rounding at binary32 names the successor. Its nearest binary64
    # IS that midpoint, so a consumer that narrows the carrier ties to even and answers
    # `1.0` — two roundings, both round-to-nearest-even, and a different value.
    loaded = cast("dict[str, object]", case_format.safe_load_yaml("ratio: 1.0000000596046448\n"))
    authored = cast("WireValue", loaded["ratio"])
    assert decode_wire(FLOAT32, authored) == 1.0 + 2.0**-23
    assert decode_wire(FLOAT32, float(cast("float", authored))) == 1.0
    assert decode_wire(FLOAT64, authored) == float("1.0000000596046448")


def test_a_yaml_integer_keeps_source_negative_zero_for_canonical_float_decoding() -> None:
    loaded = cast("dict[str, object]", case_format.safe_load_yaml("ratio: -0\n"))
    authored = cast("int", loaded["ratio"])
    assert decode_wire(FLOAT64, authored) == 0.0
    with pytest.raises(WireDecodingError) as exc_info:
        decode_canonical_wire(FLOAT64, authored)
    assert exc_info.value.reason == "noncanonical"


def test_out_of_space_yaml_numbers_are_not_managed_scalar_members() -> None:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("the interpreter has no integer string-conversion limit")
    for source, scalar_types in (
        ("9" * (limit + 1), (INT32, INT64)),
        ("1e9999", (FLOAT32, FLOAT64)),
    ):
        loaded = cast("dict[str, object]", case_format.safe_load_yaml(f"value: {source}\n"))
        value = loaded["value"]
        for neutral_type in scalar_types:
            assert matches_neutral_type(value, neutral_type) is False
            with pytest.raises(WireEncodingError):
                encode_wire(neutral_type, cast("ManagedValue", value))
