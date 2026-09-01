"""Typed literals are refused before a compatibility case reaches provisioning."""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Case, Model
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_preflight import preflight_case_literals


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
