"""Typed literals are refused before a compatibility case reaches provisioning."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from reference_harness._case_execution import CaseExecution
from reference_harness.case import Case, Model, load_case, load_model
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_preflight import preflight_case_literals

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"
_DIALECTS = ("postgres", "mariadb")


def _case(
    *,
    predicate: object | None = None,
    predicate_value: object = "2026-01-15",
    fixture_value: object = "10.50",
) -> Case:
    descriptor = {
        "entities": [
            {
                "name": "Reading",
                "namespace": "example",
                "table": "reading",
                "attributes": [
                    {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                    {"name": "amount", "type": "decimal(12,2)", "column": "amount"},
                    {"name": "day", "type": "date", "column": "day"},
                ],
                "valueObjects": [
                    {
                        "name": "profile",
                        "attributes": [{"name": "expires", "type": "date"}],
                    }
                ],
                "relationships": [
                    {
                        "name": "samples",
                        "cardinality": "one-to-many",
                        "join": {
                            "source": "id",
                            "target": {"entity": "example.Sample", "attribute": "readingId"},
                        },
                    }
                ],
            },
            {
                "name": "Sample",
                "namespace": "example",
                "table": "sample",
                "attributes": [
                    {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                    {"name": "readingId", "type": "int64", "column": "reading_id"},
                    {"name": "quantity", "type": "int32", "column": "quantity"},
                ],
            },
        ]
    }
    model = Model(
        Path("reading.yaml"),
        descriptor,
        {
            "example.Reading": [
                {
                    "id": 1,
                    "amount": fixture_value,
                    "day": "2026-01-15",
                    "profile": {"expires": "2026-01-15"},
                }
            ]
        },
    )
    document = {
        "shape": "read",
        "when": {
            "objectQuery": {
                "target": "example.Reading",
                "predicate": predicate
                or {"eq": {"attr": "example.Reading.day", "value": predicate_value}},
            }
        },
        "then": {
            "rows": [
                {
                    "id": 1,
                    "amount": "10.50",
                    "day": "2026-01-15",
                }
            ]
        },
    }
    return Case(Path("synthetic.yaml"), document, model)


def test_preflight_accepts_canonical_fixture_predicate_and_expected_literals() -> None:
    preflight_case_literals(_case())


def test_preflight_refuses_a_predicate_literal_at_its_authored_coordinate() -> None:
    with pytest.raises(CaseFailure, match=r"when\.objectQuery\.predicate.*type-mismatch for date"):
        preflight_case_literals(_case(predicate_value="15 January 2026"))


def test_preflight_refuses_a_fixture_before_any_lane_can_provision_it() -> None:
    with pytest.raises(CaseFailure, match=r"fixtures\.example\.Reading\[0\]\.amount"):
        preflight_case_literals(_case(fixture_value=10.555))


def test_preflight_requires_canonical_fixture_literals() -> None:
    with pytest.raises(CaseFailure, match=r"fixtures\.example\.Reading\[0\]\.amount.*noncanonical"):
        preflight_case_literals(_case(fixture_value="10.5"))


def test_preflight_requires_canonical_expected_rows() -> None:
    case = _case()
    case.then["rows"][0]["amount"] = "10.5"

    with pytest.raises(CaseFailure, match=r"then\.rows\[0\]\.amount.*noncanonical"):
        preflight_case_literals(case)


def test_preflight_requires_canonical_expected_graph_pins() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "read",
            "when": {"objectQuery": {"target": "example.Reading", "predicate": {"all": {}}}},
            "then": {
                "graph": {
                    "pin": {"transaction-time": "2026-01-15T09:30:00Z"},
                    "Reading": [{"id": 1, "amount": "10.50", "day": "2026-01-15"}],
                }
            },
        },
        source.model,
    )

    with pytest.raises(CaseFailure, match=r"then\.graph\.pin\.transaction-time.*not canonical"):
        preflight_case_literals(case)


def test_preflight_requires_canonical_expected_table_state() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "writeSequence",
            "when": {},
            "then": {
                "tableState": {
                    "reading": [
                        {
                            "id": 1,
                            "amount": "10.5",
                            "day": "2026-01-15",
                            "profile": {"expires": "2026-01-15"},
                        }
                    ]
                }
            },
        },
        source.model,
    )

    with pytest.raises(CaseFailure, match=r"then\.tableState\.reading\[0\]\.amount.*noncanonical"):
        preflight_case_literals(case)


def test_preflight_requires_canonical_top_level_statement_binds() -> None:
    case = _case()
    case.then["statements"] = [
        {
            "sql": {"postgres": "insert into reading (amount) values (?)"},
            "binds": ["10.5"],
        }
    ]

    with pytest.raises(CaseFailure, match=r"then\.statements\[0\]\.binds\[0\].*noncanonical"):
        preflight_case_literals(case)


def test_preflight_requires_canonical_per_step_statement_binds() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "scenario",
            "when": {
                "scenario": [
                    {
                        "statements": [
                            {
                                "sql": {"postgres": "update reading set amount = ? where id = ?"},
                                "binds": ["10.5", 1],
                            }
                        ]
                    }
                ]
            },
            "then": {},
        },
        source.model,
    )

    with pytest.raises(
        CaseFailure,
        match=r"when\.scenario\[0\]\.statements\[0\]\.binds\[0\].*noncanonical",
    ):
        preflight_case_literals(case)


def test_preflight_requires_canonical_document_leaf_statement_binds() -> None:
    case = _case()
    case.then["statements"] = [
        {
            "sql": {
                "postgres": ("select id from reading where jsonb_extract_path_text(profile, ?) = ?")
            },
            "binds": ["expires", "2026-1-15"],
        }
    ]

    with pytest.raises(CaseFailure, match=r"then\.statements\[0\]\.binds\[1\].*noncanonical"):
        preflight_case_literals(case)


def test_preflight_excludes_untyped_statement_control_binds() -> None:
    case = _case()
    case.then["statements"] = [
        {
            "sql": {
                "postgres": ("select id from reading where jsonb_extract_path_text(profile, ?) = ?")
            },
            "binds": [7, "2026-01-15"],
        }
    ]

    preflight_case_literals(case)


def test_preflight_descends_through_boolean_operand_wrappers() -> None:
    predicate = {
        "and": {
            "operands": [
                {"all": {}},
                {"eq": {"attr": "example.Reading.day", "value": "15 January 2026"}},
            ]
        }
    }
    with pytest.raises(CaseFailure, match=r"and\.operands\[1\].*type-mismatch for date"):
        preflight_case_literals(_case(predicate=predicate))


def test_preflight_resolves_nested_predicate_paths() -> None:
    predicate = {
        "nestedEq": {
            "path": "example.Reading.profile.expires",
            "value": "15 January 2026",
        }
    }
    with pytest.raises(CaseFailure, match=r"nestedEq\.value.*type-mismatch for date"):
        preflight_case_literals(_case(predicate=predicate))


def test_preflight_uses_the_same_recursive_walk_for_element_predicates() -> None:
    predicate = {
        "nestedExists": {
            "path": "example.Reading.profile",
            "where": {
                "not": {
                    "operand": {
                        "nestedEq": {
                            "path": "expires",
                            "value": "15 January 2026",
                        }
                    }
                }
            },
        }
    }

    with pytest.raises(
        CaseFailure,
        match=r"nestedExists\.where\.not\.operand\.nestedEq\.value.*type-mismatch for date",
    ):
        preflight_case_literals(_case(predicate=predicate))


def test_preflight_checks_predicate_write_assignments() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "scenario",
            "when": {
                "scenario": [
                    {
                        "write": {
                            "mutation": "update",
                            "target": {
                                "entity": "example.Reading",
                                "predicate": {"eq": {"attr": "example.Reading.id", "value": 1}},
                            },
                            "assignments": [{"attr": "example.Reading.day", "value": "not-a-date"}],
                        }
                    }
                ]
            },
            "then": {},
        },
        source.model,
    )

    with pytest.raises(CaseFailure, match=r"assignments\[0\]\.value"):
        preflight_case_literals(case)


def test_preflight_checks_predicate_write_selection_literals() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "scenario",
            "when": {
                "scenario": [
                    {
                        "write": {
                            "mutation": "update",
                            "target": {
                                "entity": "example.Reading",
                                "predicate": {
                                    "eq": {
                                        "attr": "example.Reading.day",
                                        "value": "not-a-date",
                                    }
                                },
                            },
                            "assignments": [{"attr": "example.Reading.amount", "value": "10.50"}],
                        }
                    }
                ]
            },
            "then": {},
        },
        source.model,
    )

    with pytest.raises(CaseFailure, match=r"target\.predicate.*type-mismatch for date"):
        preflight_case_literals(case)


def test_preflight_checks_retry_attempt_write_rows() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "conflict",
            "when": {"attempts": [{"write": {"id": 1, "day": "not-a-date", "observedVersion": 1}}]},
            "then": {},
        },
        source.model,
    )

    with pytest.raises(CaseFailure, match=r"when\.attempts\[0\]\.write\.day"):
        preflight_case_literals(case)


def test_preflight_checks_expected_graph_relationship_children() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "read",
            "when": {
                "objectQuery": {
                    "target": "example.Reading",
                    "predicate": {"all": {}},
                }
            },
            "then": {
                "graph": {
                    "Reading": [
                        {
                            "id": 1,
                            "samples": [{"id": 2, "readingId": 1, "quantity": "not-an-int"}],
                        }
                    ]
                }
            },
        },
        source.model,
    )

    with pytest.raises(CaseFailure, match=r"samples\[0\]\.quantity.*type-mismatch for int32"):
        preflight_case_literals(case)


def _polymorphic_case(*, scenario: bool) -> Case:
    model = Model(
        Path("payment.yaml"),
        {
            "entities": [
                {
                    "name": "Payment",
                    "namespace": "example",
                    "table": "payment",
                    "inheritance": {
                        "role": "root",
                        "strategy": "table-per-hierarchy",
                        "tag": {"column": "kind"},
                    },
                    "attributes": [
                        {"name": "id", "type": "int64", "column": "id", "primaryKey": True}
                    ],
                },
                {
                    "name": "CardPayment",
                    "namespace": "example",
                    "inheritance": {
                        "role": "concrete-subtype",
                        "parent": "example.Payment",
                        "tagValue": "card",
                    },
                    "attributes": [{"name": "detail", "type": "string", "column": "detail"}],
                },
                {
                    "name": "CashPayment",
                    "namespace": "example",
                    "inheritance": {
                        "role": "concrete-subtype",
                        "parent": "example.Payment",
                        "tagValue": "cash",
                    },
                    "attributes": [{"name": "detail", "type": "decimal(18,2)", "column": "detail"}],
                },
            ]
        },
        {},
    )
    query = {"target": "example.Payment", "predicate": {"all": {}}}
    row = {"id": 1, "detail": "not-a-decimal", "familyVariant": "CashPayment"}
    document = (
        {
            "shape": "scenario",
            "when": {"scenario": [{"objectQuery": query, "expectRows": [row]}]},
            "then": {},
        }
        if scenario
        else {"shape": "read", "when": {"objectQuery": query}, "then": {"rows": [row]}}
    )
    return Case(Path("synthetic-polymorphic.yaml"), document, model)


def test_preflight_checks_top_level_expected_rows_against_their_family_variant() -> None:
    with pytest.raises(CaseFailure, match=r"then\.rows\[0\]\.detail.*type-mismatch for decimal"):
        preflight_case_literals(_polymorphic_case(scenario=False))


def test_preflight_checks_scenario_expected_rows_against_their_family_variant() -> None:
    with pytest.raises(CaseFailure, match=r"expectRows\[0\]\.detail.*type-mismatch for decimal"):
        preflight_case_literals(_polymorphic_case(scenario=True))


@pytest.mark.parametrize("session", ["A", "B"])
def test_preflight_requires_canonical_concurrency_expected_rows(session: str) -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "concurrencySuccess",
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            session: {
                                "kind": "read",
                                "expectRows": [
                                    {
                                        "id": 1,
                                        "amount": "10.5",
                                        "physicalSqlOnly": "not-a-modeled-literal",
                                    }
                                ],
                            }
                        }
                    ]
                }
            },
            "then": {},
        },
        source.model,
    )

    with pytest.raises(
        CaseFailure,
        match=rf"when\.concurrency\.rounds\[0\]\.{session}\.expectRows\[0\]\.amount.*noncanonical",
    ):
        preflight_case_literals(case)


def test_preflight_leaves_physical_sql_only_concurrency_values_untyped() -> None:
    source = _case()
    case = Case(
        source.path,
        {
            "shape": "concurrencySuccess",
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            "A": {
                                "kind": "read",
                                "expectRows": [
                                    {
                                        "id": 1,
                                        "amount": "10.50",
                                        "physicalSqlOnly": "not-a-modeled-literal",
                                    }
                                ],
                            }
                        }
                    ]
                }
            },
            "then": {},
        },
        source.model,
    )

    preflight_case_literals(case)


_PATH_UPDATE_CASES = (
    "m-opt-lock-018-document-layout-version-advance",
    "m-opt-lock-019-document-layout-no-op-collapse",
    "m-storage-layout-023-document-layout-patch-update",
    "m-storage-layout-024-document-layout-occurrence-parent-states",
    "m-storage-layout-032-assigned-occurrence-replacement-layout-twin-document",
    "m-storage-layout-034-chained-occurrence-edits-layout-twin-document",
    "m-value-object-067-document-layout-nested-occurrence",
)


def _corpus_case(stem: str) -> Case:
    return load_case(_COMPATIBILITY_ROOT, _COMPATIBILITY_ROOT / "cases" / f"{stem}.yaml")


def _damaged(stem: str) -> Case:
    return copy.deepcopy(_corpus_case(stem))


def _document_path(dialect: str, member: str) -> str:
    return "{" + member + "}" if dialect == "postgres" else f"$.{member}"


def _node_path_update(dialect: str, member: str, value: object) -> Case:
    model = load_model(_COMPATIBILITY_ROOT, "models/materialization-stress-document.yaml")
    mutation = {
        "postgres": "jsonb_set(payload, ?, cast(? as jsonb))",
        "mariadb": "json_set(payload, ?, json_extract(?, '$'))",
    }[dialect]
    statement = {
        "sql": {dialect: f"update materialization_node set payload = {mutation} where id = ?"},
        "binds": {dialect: [_document_path(dialect, member), value, 1]},
    }
    return Case(
        Path("synthetic-node-path-update.yaml"),
        {"shape": "scenario", "when": {"scenario": [{"statements": [statement]}]}, "then": {}},
        model,
    )


@pytest.mark.parametrize("stem", _PATH_UPDATE_CASES)
def test_preflight_accepts_every_corpus_document_path_update(stem: str) -> None:
    preflight_case_literals(_corpus_case(stem))


@pytest.mark.parametrize("dialect", _DIALECTS)
@pytest.mark.parametrize(
    ("member", "value"),
    [
        ("ratio", -0.0),
        ("ratio", -1e-50),
        ("measure", -0.0),
        ("weight", -0.0),
    ],
)
def test_preflight_refuses_a_negative_float_zero_at_a_document_path_leaf(
    dialect: str, member: str, value: float
) -> None:
    preflight_case_literals(_node_path_update(dialect, member, 0.0))
    with pytest.raises(
        CaseFailure,
        match=rf"when\.scenario\[0\]\.statements\[0\]\.binds\.{dialect}\[1\]: .* not canonical",
    ):
        preflight_case_literals(_node_path_update(dialect, member, value))


@pytest.mark.parametrize("dialect", _DIALECTS)
@pytest.mark.parametrize(
    ("member", "value", "location"),
    [
        ("primaryTag", {"ratio": -0.0}, r"\.ratio"),
        ("tags", [{"measure": 1.5}, {"measure": -1e-400}], r"\[1\]\.measure"),
    ],
)
def test_preflight_checks_a_document_path_occurrence_through_its_declaration(
    dialect: str, member: str, value: object, location: str
) -> None:
    with pytest.raises(CaseFailure, match=rf"binds\.{dialect}\[1\]{location}: .* not canonical"):
        preflight_case_literals(_node_path_update(dialect, member, value))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_preflight_types_the_scenario_occurrence_path_values_of_a_corpus_case(
    dialect: str,
) -> None:
    case = _damaged("m-storage-layout-034-chained-occurrence-edits-layout-twin-document")
    statement = case.when["scenario"][0]["statements"][0]
    statement["binds"][dialect][1]["stops"][1]["port"] = 42
    with pytest.raises(
        CaseFailure,
        match=rf"when\.scenario\[0\]\.statements\[0\]\.binds\.{dialect}\[1\]"
        r"\.stops\[1\]\.port: 42 is type-mismatch for string",
    ):
        preflight_case_literals(case)


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_preflight_types_every_write_sequence_path_value_of_a_nested_mutation(
    dialect: str,
) -> None:
    case = _damaged("m-storage-layout-023-document-layout-patch-update")
    case.then["statements"][-1]["binds"][dialect][3] = "21"
    with pytest.raises(
        CaseFailure, match=rf"binds\.{dialect}\[3\]: '21' is type-mismatch for int64"
    ):
        preflight_case_literals(case)


class _RecordingExecutor:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.binds: tuple[Any, ...] = ()

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        raise AssertionError(sql)

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        self.binds = tuple(binds)
        return 1


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_execution_passes_document_path_binds_through_unadapted(dialect: str) -> None:
    case = _corpus_case("m-storage-layout-032-assigned-occurrence-replacement-layout-twin-document")
    statement = case.when["scenario"][0]["statements"][0]
    binds = statement["binds"][dialect]
    executor = _RecordingExecutor(dialect)
    CaseExecution(case, executor).execute(statement["sql"][dialect], binds)
    assert all(
        sent is authored for sent, authored in zip(executor.binds[:4], binds[:4], strict=True)
    )
