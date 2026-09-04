"""DB-free fidelity tests for the grouped compatibility-case schema.

Pinned fixture documents against the new ``compatibility-case.schema.json``: a
minimal well-formed document for each of the eight shapes is ACCEPTED, and a
curated set of malformed documents — the legacy flat layout, a mislabeled
``shape``, a plain-string ``sql`` at a golden location, an empty ``sql`` map, an
extra key inside a closed group, and ``binds`` authored outside a statement
entry — is REJECTED.

This fixture set is the regression gate for the grouped layout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reference_harness.schemas import build_registry, load_schemas

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "schemas" / "compatibility-case.schema.json"
)
_REGISTRY = build_registry(load_schemas(_SCHEMA_PATH.parents[1]))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")), registry=_REGISTRY
    )


def test_subtype_selection_schema_is_registered_under_its_own_id() -> None:
    schemas = load_schemas(_SCHEMA_PATH.parents[1])
    subtype_selection = schemas["subtype-selection.schema.json"]
    assert subtype_selection["$id"].endswith("/subtype-selection.schema.json")


def test_predicate_schema_resolves_the_shared_subtype_selection_reference() -> None:
    predicate = load_schemas(_SCHEMA_PATH.parents[1])["predicate.schema.json"]
    validator = Draft202012Validator(predicate, registry=_REGISTRY)
    assert validator.is_valid({"narrow": {"to": ["Animal"], "operand": {"all": {}}}})


def _is_valid(doc: dict[str, Any]) -> bool:
    return next(_validator().iter_errors(doc), None) is None


# --- minimal well-formed documents, one per shape --------------------------


def _read_case() -> dict[str, Any]:
    return {
        "model": "models/orders.yaml",
        "tags": ["m-agg"],
        "shape": "read",
        "when": {"objectQuery": {"target": "Order", "predicate": {"all": {}}}},
        "then": {
            "statements": [{"sql": {"postgres": "select t0.id from orders t0"}, "binds": []}],
            "rows": [{"id": 1}],
            "roundTrips": 1,
        },
    }


def _write_sequence_case() -> dict[str, Any]:
    return {
        "model": "models/balance.yaml",
        "tags": ["m-txtime-write"],
        "shape": "writeSequence",
        "when": {
            "writeSequence": [
                {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1, "acctNum": "A"}]}
            ]
        },
        "then": {
            "statements": [
                {"sql": {"postgres": "insert into balance(bal_id) values (?)"}, "binds": [1]}
            ],
            "tableState": {"balance": [{"bal_id": 1}]},
        },
    }


def _scenario_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "objectQuery": {
                        "target": "Account",
                        "predicate": {"eq": {"attr": "Account.id", "value": 7}},
                    },
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "select t0.id from account t0 where t0.id = ?"},
                            "binds": [7],
                        }
                    ],
                    "expectRows": [{"id": 7}],
                }
            ]
        },
        "then": {"roundTrips": 1},
    }


def _settled_write_scenario_case() -> dict[str, Any]:
    """A scenario whose grouped BUFFERED KEYED write names the find it settles against.

    The `on` reference is legal on this form alone: a `uow`-grouped step, a single
    index, and a buffered keyed `write` — the only form carrying an instruction an
    observation can reach.
    """
    return {
        "model": "models/position.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "compileEligibility": {"mode": "run-only", "reason": "query-result-dependent"},
        "when": {
            "scenario": [
                {
                    "uow": "g",
                    "objectQuery": {
                        "target": "Position",
                        "predicate": {"eq": {"attr": "Position.id", "value": 1}},
                    },
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "select t0.pos_id from position t0"},
                            "binds": [1],
                        }
                    ],
                    "expectRows": [{"pos_id": 1}],
                },
                {
                    "uow": "g",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Position",
                            "rows": [{"id": 1, "value": 150.00}],
                            "validFrom": "2024-03-01T00:00:00+00:00",
                        }
                    ],
                    "roundTrips": 1,
                    "statements": [
                        {"sql": {"postgres": "update position set out_z = ?"}, "binds": ["x"]}
                    ],
                },
            ]
        },
        "then": {"roundTrips": 2},
    }


def _action_scenario_case() -> dict[str, Any]:
    """A scenario with lifecycle ACTION steps.

    Exercises the new action-step vocabulary end to end: `action` verbs, `on`,
    `path`, `set` (mutate-only), and the per-step observables `expectState` and
    `sameObjectAs` on an action step.
    """
    return {
        "model": "models/orders.yaml",
        "tags": ["m-deep-fetch", "m-op-list"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "objectQuery": {
                        "target": "Order",
                        "predicate": {"in": {"attr": "Order.id", "values": [1, 2]}},
                    },
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "select t0.id from orders t0 where t0.id in (?, ?)"
                            },
                            "binds": [1, 2],
                        }
                    ],
                    "expectRows": [{"id": 1}, {"id": 2}],
                },
                {
                    "action": "load",
                    "on": 0,
                    "path": "items",
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "select t0.id, t0.order_id from order_item t0 "
                                "where t0.order_id in (?, ?)"
                            },
                            "binds": [1, 2],
                        }
                    ],
                    "expectRows": [{"id": 11, "order_id": 1}],
                },
                {
                    "action": "access",
                    "on": 0,
                    "path": "items",
                    "roundTrips": 0,
                    "sameObjectAs": 1,
                },
                {
                    "action": "mutate",
                    "on": 0,
                    "set": {"name": "Ada2"},
                    "roundTrips": 0,
                    "expectState": "persisted",
                },
            ]
        },
        "then": {"roundTrips": 2},
    }


def _action_expect_graph_case() -> dict[str, Any]:
    """An `access` step asserting the relationship contents its source read loaded.

    `expectGraph` is the step-level analogue of `then.graph`, keyed by the target
    Entity of the relationship the step's `path` navigates to.
    """
    doc = _action_scenario_case()
    doc["when"]["scenario"][2]["expectGraph"] = {
        "OrderItem": [{"id": 11, "orderId": 1}, {"id": 12, "orderId": 1}]
    }
    return doc


def _read_expect_graph_case() -> dict[str, Any]:
    """A grouped read step asserting the graph it materialized.

    The observable's other placement: keyed by the read's OWN target, each root
    carrying the relationship its Include Path populated. Inside a `uow` group
    those contents are what that transaction observes mid-flight, which is
    read-your-own-writes stated over a relationship.
    """
    return {
        "model": "models/orders.yaml",
        "tags": ["m-unit-work", "m-deep-fetch"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "uow": "ryow",
                    "objectQuery": {
                        "target": "Order",
                        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                        "includes": [{"segments": [{"rel": "Order.items"}]}],
                    },
                    "roundTrips": 2,
                    "statements": [
                        {
                            "sql": {"postgres": "select t0.id from orders t0 where t0.id = ?"},
                            "binds": [1],
                        },
                        {
                            "sql": {
                                "postgres": "select t0.id, t0.order_id from order_item t0 "
                                "where t0.order_id in (?)"
                            },
                            "binds": [1],
                        },
                    ],
                    "expectGraph": {"Order": [{"id": 1, "items": [{"id": 11, "orderId": 1}]}]},
                }
            ]
        },
        "then": {"roundTrips": 2},
    }


def _action_identity_error_case() -> dict[str, Any]:
    """A scenario action case exercising `differentObjectFrom`, `on` array, `expectError`."""
    return {
        "model": "models/orders.yaml",
        "tags": ["m-detach"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "objectQuery": {
                        "target": "Order",
                        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                    },
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "select t0.id from orders t0 where t0.id = ?"},
                            "binds": [1],
                        }
                    ],
                    "expectRows": [{"id": 1}],
                },
                {
                    "action": "detachCopy",
                    "on": 0,
                    "roundTrips": 0,
                    "expectState": "detached",
                    "differentObjectFrom": 0,
                },
                {
                    "action": "load",
                    "on": [0, 1],
                    "path": "items",
                    "roundTrips": 0,
                    "expectError": "detached-relationship-load",
                },
            ]
        },
        "then": {"roundTrips": 1},
    }


def _write_value_scenario_case() -> dict[str, Any]:
    """A scenario of KEYED WRITE ACTION steps (m-case-format *Keyed write action
    steps*).

    Each step hands a keyed write verb a value whose provenance the sibling
    `value` states, names no `on`, carries no golden SQL, and declares
    `roundTrips: 0` — so the whole scenario's declared total is legitimately 0,
    the one shape where that floor is relaxed.

    The three steps are the three shapes this grammar admits: a refused `update`,
    the one ACCEPTED write whose zero is honest (an `update` of a value no author
    changed materializes nothing), and a refused `insert` — the only `insert`
    there is here, since an accepted one would open a row.
    """
    return {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "lane": "api-conformance",
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "action": "update",
                    "value": "unmanaged",
                    "roundTrips": 0,
                    "expectError": "write-value-not-stored",
                },
                {"action": "update", "value": "thisSource", "roundTrips": 0},
                {
                    "action": "insert",
                    "value": "thisSource",
                    "roundTrips": 0,
                    "expectError": "write-value-already-stored",
                },
            ]
        },
        "then": {"roundTrips": 0},
    }


def _conflict_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "conflict",
        "given": {"apply": [{"sql": "update account set version = 2 where id = 2"}]},
        "when": {"uow": {"concurrency": "optimistic"}, "write": {"id": 2, "observedVersion": 1}},
        "then": {
            "statements": [
                {
                    "sql": {
                        "postgres": "update account set balance = ? where id = ? and version = ?"
                    },
                    "binds": [250.0, 2, 1],
                }
            ],
            "affectedRows": 0,
            "tableState": {"account": [{"id": 2, "version": 2}]},
        },
    }


def _coherence_case() -> dict[str, Any]:
    step_sql = [{"sql": {"postgres": "select t0.id from account t0 where t0.id = ?"}, "binds": [2]}]
    return {
        "model": "models/account.yaml",
        "tags": ["m-coherence"],
        "shape": "coherence",
        "when": {
            "coherence": [
                {
                    "node": "B",
                    "kind": "read",
                    "objectQuery": {"target": "Account", "predicate": {"all": {}}},
                    "statements": step_sql,
                    "observeRows": [{"id": 2}],
                },
                {
                    "node": "A",
                    "kind": "write",
                    "statements": [
                        {
                            "sql": {"postgres": "update account set balance = ? where id = ?"},
                            "binds": [9, 2],
                        }
                    ],
                },
            ]
        },
    }


def _error_case() -> dict[str, Any]:
    stmt = {"sql": {"postgres": "insert into widget(id) values (?)"}, "binds": [1]}
    return {
        "model": "models/error-cases.yaml",
        "tags": ["m-db-error"],
        "shape": "error",
        "then": {
            "statements": [stmt, stmt],
            "errorClass": "uniqueViolation",
            "nativeCode": {"postgres": "23505", "mariadb": 1062},
        },
    }


def _error_concurrency_case() -> dict[str, Any]:
    """The two-connection error trigger: barrier-separated rounds on two held
    sessions, whose only assertion is the classified error.

    Its steps are the shape's two legal forms — a `kind`-less statement step and a
    `kind: commit` step ending that node's held transaction."""
    return {
        "model": "models/error-cases.yaml",
        "tags": ["m-db-error"],
        "shape": "error",
        "given": {"fixtures": True},
        "when": {
            "uow": {"isolation": "serializable"},
            "concurrency": {
                "rounds": [
                    {
                        "A": {
                            "statements": [
                                {
                                    "sql": {"postgres": "update gauge set v = ? where id = ?"},
                                    "binds": [9, 1],
                                }
                            ]
                        },
                        "B": {"kind": "commit"},
                    }
                ]
            },
        },
        "then": {
            "errorClass": "deadlock",
            "nativeCode": {"postgres": "40001", "mariadb": 1213},
        },
    }


def _concurrency_success_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-read-lock"],
        "shape": "concurrencySuccess",
        "given": {"fixtures": True},
        "when": {
            "concurrency": {
                "rounds": [
                    {
                        "A": {
                            "kind": "read",
                            "statements": [
                                {
                                    "sql": {
                                        "postgres": "select t0.id from account t0 where t0.id = ?"
                                    },
                                    "binds": [2],
                                }
                            ],
                            "expectRows": [{"id": 2}],
                        }
                    }
                ]
            }
        },
    }


def _conflict_retry_case() -> dict[str, Any]:
    """The conflict RETRY form (`when.attempts`): each attempt asserts `affectedRows`.

    Distinct from `_conflict_case` (the single-attempt `when.write` + `then.affectedRows`
    form); this pins the retry attempts def, whose per-attempt affected-row count carries
    the assertion-group name `affectedRows`, NOT the legacy `expectedAffectedRows`.
    """
    return {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "conflict",
        "given": {"apply": [{"sql": "update account set version = 2 where id = 2"}]},
        "when": {
            "uow": {"concurrency": "optimistic"},
            "attempts": [
                {
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update account set balance = ? "
                                "where id = ? and version = ?"
                            },
                            "binds": [250.0, 2, 1],
                        }
                    ],
                    "write": {"id": 2, "balance": 250.0, "observedVersion": 1},
                    "affectedRows": 0,
                },
                {
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update account set balance = ? "
                                "where id = ? and version = ?"
                            },
                            "binds": [250.0, 2, 2],
                        }
                    ],
                    "write": {"id": 2, "balance": 250.0, "observedVersion": 2},
                    "affectedRows": 1,
                },
            ],
        },
        "then": {"tableState": {"account": [{"id": 2, "version": 3}]}},
    }


def _boundary_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-auto-retry"],
        "shape": "boundary",
        "lane": "api-conformance",
        "given": {"fault": "serialization-failure"},
        "when": {
            "uow": {"concurrency": "optimistic"},
            "boundary": [{"action": "read"}, {"action": "update"}],
        },
        "then": {"outcome": "committed"},
    }


def _rejected_query_case() -> dict[str, Any]:
    """A rejected case carrying an invalid QUERY and the violated rule."""
    return {
        "model": "models/customer.yaml",
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": {
            "objectQuery": {
                "target": "Customer",
                "predicate": {"nestedEq": {"path": "Customer.contact.city", "value": "Oslo"}},
            }
        },
        "then": {"rejectedRule": "nested-path-first-segment-not-value-object"},
    }


def _rejected_case_declaring_zero_round_trips() -> dict[str, Any]:
    """A rejected case declaring the zero round trips it actually costs.

    The count a pre-SQL refusal can accurately state, which the property's own
    default of one — written for the shapes that reach the database — cannot."""
    doc = _rejected_query_case()
    doc["then"]["roundTrips"] = 0
    return doc


def _rejected_write_case() -> dict[str, Any]:
    """A rejected case carrying an invalid WRITE input and the violated rule."""
    return {
        "model": "models/contact.yaml",
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": {"write": {"id": 1, "name": "Acme", "address": {"city": "Oslo"}}},
        "then": {"rejectedRule": "write-required-attribute-missing"},
    }


def _rejected_keyed_write_case() -> dict[str, Any]:
    """A rejected case whose `when.write` is a whole KEYED INSTRUCTION.

    The third `when.write` form: `rows` names it, and the entity handle rides on
    the instruction rather than being resolved from the model.
    """
    return {
        "model": "models/position.yaml",
        "tags": ["m-unit-work"],
        "shape": "rejected",
        "when": {
            "write": {
                "mutation": "update",
                "entity": "Position",
                "rows": [{"id": 1, "value": 150.00}, {"id": 2, "value": 250.00}],
            }
        },
        "then": {"rejectedRule": "temporal-keyed-write-multi-row"},
    }


def _action_boundary_no_on_case() -> dict[str, Any]:
    """A scenario whose BOUNDARY action verbs (`flush` / `commit`) omit `on`.

    The boundary / unit-of-work verbs operate on the whole unit of work, not a
    specific prior object, so `on` is inapplicable and MAY be omitted — the per-verb
    conditional makes `on` required ONLY for the object-targeting verbs. This fixture
    pins that a boundary step without `on` still validates.
    """
    return {
        "model": "models/orders.yaml",
        "tags": ["m-deep-fetch", "m-unit-work"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "objectQuery": {
                        "target": "Order",
                        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                    },
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "select t0.id from orders t0 where t0.id = ?"},
                            "binds": [1],
                        }
                    ],
                    "expectRows": [{"id": 1}],
                },
                {
                    "action": "flush",
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "insert into order_item(id, order_id) values (?, ?)"
                            },
                            "binds": [13, 1],
                        }
                    ],
                },
                {"action": "commit", "roundTrips": 0},
            ]
        },
        "then": {"roundTrips": 2},
    }


def _graphs_read_case() -> dict[str, Any]:
    """A read case carrying per-milestone `then.graphs`.

    A `history` snapshot read materializes one edge-pinned graph per milestone: the
    `then.graphs` array pairs each milestone's `pin` (its own from-instant, keyed by
    the as-of attribute) with the graph materialized at it, coexisting with the
    single-graph `then.graph` exactly as `then.rows` does.
    """
    return {
        "model": "models/invoice.yaml",
        "tags": ["m-snapshot-read", "m-deep-fetch"],
        "shape": "read",
        "when": {
            "objectQuery": {
                "target": "InvoiceLine",
                "predicate": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
                "temporal": {"transaction-time": {"history": {}}},
            },
        },
        "then": {
            "statements": [
                {
                    "sql": {
                        "postgres": "select t0.id, t0.in_z from invoice_line t0 where t0.id = ?"
                    },
                    "binds": [1000],
                }
            ],
            "graphs": [
                {
                    "pin": {"transaction-time": "2024-01-01T00:00:00+00:00"},
                    "graph": {"InvoiceLine": [{"id": 1000, "amount": 50.00}]},
                },
                {
                    "pin": {"transaction-time": "2024-04-01T00:00:00+00:00"},
                    "graph": {"InvoiceLine": [{"id": 1000, "amount": 75.00}]},
                },
            ],
            "roundTrips": 1,
        },
    }


def _stored_data_issues_read_case() -> dict[str, Any]:
    """A read case carrying `then.storedDataIssues`.

    A result position whose stored state contradicted the model carries `null` in
    `then.graph` when nothing could be hydrated, and its diagnoses ride
    `then.storedDataIssues` — one `{ordinal, hydrated, issues}` entry per invalid
    position, each issue naming its closed code, entity, member, and object key.
    """
    return {
        "model": "models/orders.yaml",
        "tags": ["m-snapshot-read", "m-deep-fetch"],
        "shape": "read",
        "when": {
            "objectQuery": {
                "target": "Order",
                "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
            },
        },
        "then": {
            "statements": [
                {"sql": {"postgres": "select t0.id from orders t0 where t0.id = ?"}, "binds": [1]}
            ],
            "referenceSql": "select id from orders where id = 1",
            "graph": {"Order": [None]},
            "storedDataIssues": [
                {
                    "ordinal": 0,
                    "hydrated": False,
                    "issues": [
                        {
                            "code": "stored-data-leaf-undecodable",
                            "entity": "parallax.compatibility.Order",
                            "member": "parallax.compatibility.Order.name",
                            "objectKey": {
                                "entity": "parallax.compatibility.Order",
                                "key": {"id": 1},
                            },
                        }
                    ],
                }
            ],
            "roundTrips": 1,
        },
    }


def _streamed_milestone_graphs_case() -> dict[str, Any]:
    """A streamed milestone-set read: `when.stream` beside `then.graphs`.

    A milestone-set read is delivered one root at a time exactly as any other
    read is — its Continuation Order carries the milestone edge after the key —
    and its result is the same per-milestone partition its eager peer states.
    """
    doc = _streamed_read_case()
    doc["when"]["objectQuery"]["temporal"] = {"transaction-time": {"history": {}}}
    doc["then"].pop("graph")
    doc["then"]["graphs"] = [
        {
            "pin": {"transaction-time": "2024-01-01T00:00:00Z"},
            "graph": {"Order": [{"id": 1}]},
        }
    ]
    return doc


VALID_CASES = {
    "read": _read_case,
    "writeSequence": _write_sequence_case,
    "scenario": _scenario_case,
    "scenario-settled-write": _settled_write_scenario_case,
    "scenario-action": _action_scenario_case,
    "scenario-action-expect-graph": _action_expect_graph_case,
    "scenario-read-expect-graph": _read_expect_graph_case,
    "scenario-action-identity-error": _action_identity_error_case,
    "scenario-action-boundary-no-on": _action_boundary_no_on_case,
    "scenario-keyed-write-value": _write_value_scenario_case,
    "conflict": _conflict_case,
    "conflict-retry": _conflict_retry_case,
    "coherence": _coherence_case,
    "error": _error_case,
    "error-concurrency": _error_concurrency_case,
    "concurrencySuccess": _concurrency_success_case,
    "boundary": _boundary_case,
    "read-graphs": _graphs_read_case,
    "read-streamed-graphs": _streamed_milestone_graphs_case,
    "read-stored-data-issues": _stored_data_issues_read_case,
    "rejected-query": _rejected_query_case,
    "rejected-declaring-its-zero-cost": _rejected_case_declaring_zero_round_trips,
    "rejected-write": _rejected_write_case,
    "rejected-keyed-write": _rejected_keyed_write_case,
}


@pytest.mark.parametrize("shape", sorted(VALID_CASES))
def test_schema_accepts_minimal_case_for_every_shape(shape: str) -> None:
    doc = VALID_CASES[shape]()
    errors = list(_validator().iter_errors(doc))
    assert errors == [], f"{shape} case should validate, got: {[e.message for e in errors]}"


@pytest.mark.parametrize(
    "code",
    [
        "detached-relationship-load",
        "transaction-time-pin-read-only",
        "write-value-not-stored",
        "write-value-already-stored",
        "write-value-foreign-lifecycle",
    ],
)
def test_schema_accepts_every_expect_error_code(code: str) -> None:
    # The closed application-lifecycle vocabulary: the m-detach / m-identity-map
    # pair plus m-unit-work's three write-value provenance refusals. The
    # `action-unknown-expect-error` rejection fixture pins the other direction.
    doc = _action_identity_error_case()
    doc["when"]["scenario"][2]["expectError"] = code
    assert _is_valid(doc)


# --- value-object document whose content is marker-SHAPED -------------------
#
# A DB-computed marker (`{computed}` / `{increment}`) vs a value-object document is
# a MODEL-ROLE decision the model-agnostic schema cannot make, so the write-value
# branches are NON-exclusive: a value-object column's value is ALWAYS literal
# document content, even when the authored document happens to be shaped like a
# marker. These documents MUST validate as a value-object write row.


def _value_object_document_case(document: Any) -> dict[str, Any]:
    """A writeSequence insert whose `address` value object carries *document*.

    `address` is a top-level value object on the customer model, so its value is
    the WHOLE literal document bound as one atomic document bind — the marker-shaped
    payload rides through as document content, never a DB-computed marker."""
    return {
        "model": "models/customer.yaml",
        "tags": ["m-value-object"],
        "shape": "writeSequence",
        "when": {
            "writeSequence": [
                {
                    "mutation": "insert",
                    "entity": "Customer",
                    "rows": [{"id": 1, "name": "Ada", "address": document}],
                }
            ]
        },
        "then": {
            "statements": [
                {
                    "sql": {"postgres": "insert into customer(id, name, address) values (?, ?, ?)"},
                    "binds": [1, "Ada", document],
                }
            ],
            "tableState": {"customer": [{"id": 1, "name": "Ada", "address": document}]},
        },
    }


MARKER_SHAPED_DOCUMENTS = {
    "computed-maxPlusOne": {"computed": "maxPlusOne"},
    "increment": {"increment": 1},
    "computed-plus-street": {"computed": "x", "street": "Main"},
}


@pytest.mark.parametrize("label", sorted(MARKER_SHAPED_DOCUMENTS))
def test_schema_accepts_marker_shaped_value_object_document(label: str) -> None:
    doc = _value_object_document_case(MARKER_SHAPED_DOCUMENTS[label])
    errors = list(_validator().iter_errors(doc))
    assert errors == [], (
        f"marker-shaped value-object document {label!r} should validate as document "
        f"content, got: {[e.message for e in errors]}"
    )


# --- rejected malformed documents ------------------------------------------


def _legacy_layout() -> dict[str, Any]:
    """The pre-migration flat layout: no shape, positional goldenSql/binds."""
    return {
        "model": "models/orders.yaml",
        "tags": ["m-agg"],
        "objectQuery": {"target": "Order", "predicate": {"all": {}}},
        "goldenSql": {"postgres": "select t0.id from orders t0"},
        "binds": [],
        "expectedRows": [{"id": 1}],
    }


def _mislabeled_shape() -> dict[str, Any]:
    """A well-formed writeSequence document mislabeled as a read."""
    doc = _write_sequence_case()
    doc["shape"] = "read"
    return doc


def _string_sql_at_golden_location() -> dict[str, Any]:
    """A golden statement whose sql is a plain string instead of a dialect map."""
    doc = _read_case()
    doc["then"]["statements"][0]["sql"] = "select t0.id from orders t0"
    return doc


def _empty_sql_map() -> dict[str, Any]:
    """A golden statement whose sql map declares no dialect."""
    doc = _read_case()
    doc["then"]["statements"][0]["sql"] = {}
    return doc


def _extra_key_in_closed_group() -> dict[str, Any]:
    """A stray legacy key inside the closed `then` group."""
    doc = _read_case()
    doc["then"]["expectedRows"] = [{"id": 1}]
    return doc


def _binds_outside_statement_entry() -> dict[str, Any]:
    """`binds` authored at the root instead of inside a statement entry."""
    doc = _read_case()
    doc["binds"] = [1]
    return doc


def _attempt_legacy_affected_rows() -> dict[str, Any]:
    """A retry attempt carrying the legacy `expectedAffectedRows` name (finding 1).

    The attempts def requires `affectedRows` and is closed, so the legacy
    `expected*` spelling is rejected two ways: `affectedRows` is now missing and
    `expectedAffectedRows` is an extra key. No legacy executable vocabulary may
    validate inside a migrated case body.
    """
    doc = _conflict_retry_case()
    attempt = doc["when"]["attempts"][0]
    attempt["expectedAffectedRows"] = attempt.pop("affectedRows")
    return doc


def _cross_shape_when_member() -> dict[str, Any]:
    """A read case carrying a stray cross-shape `when.boundary` block (finding 2).

    The read branch now constrains `when` to only that shape's members
    (`objectQuery` / `uow` / `equivalentEncodings`), so a
    mislabeled/mixed document that also carries an unrelated action member fails its
    shape branch and no other branch matches — the `oneOf` rejects it.
    """
    doc = _read_case()
    doc["when"]["boundary"] = [{"action": "read"}]
    return doc


def _read_missing_target() -> dict[str, Any]:
    """A read case whose query omits its own `target` (m-case-format Q1)."""
    doc = _read_case()
    del doc["when"]["objectQuery"]["target"]
    return doc


def _scenario_find_missing_query() -> dict[str, Any]:
    """A scenario read step carrying no `objectQuery` (Q1): the branch requires it."""
    doc = _scenario_case()
    del doc["when"]["scenario"][0]["objectQuery"]
    return doc


def _coherence_read_missing_query() -> dict[str, Any]:
    """A coherence read step carrying no `objectQuery` (Q1): the read conditional
    requires it."""
    doc = _coherence_case()
    del doc["when"]["coherence"][0]["objectQuery"]
    return doc


def _rejected_without_rule() -> dict[str, Any]:
    """A rejected case missing `then.rejectedRule`: the branch requires it."""
    doc = _rejected_query_case()
    del doc["then"]["rejectedRule"]
    return doc


def _rejected_unknown_rule() -> dict[str, Any]:
    """A rejected case naming a rule outside the closed vocabulary — the enum rejects it."""
    doc = _rejected_query_case()
    doc["then"]["rejectedRule"] = "not-a-real-rule"
    return doc


def _rejected_with_golden_statements() -> dict[str, Any]:
    """A rejected case carrying golden `then.statements` — disallowed (rejection is pre-SQL)."""
    doc = _rejected_query_case()
    doc["then"]["statements"] = [{"sql": {"postgres": "select t0.id from customer t0"}}]
    return doc


def _rejected_cross_shape_when_member() -> dict[str, Any]:
    """A rejected case carrying a stray `when.boundary` (its `when` allows only
    objectQuery/write)."""
    doc = _rejected_query_case()
    doc["when"]["boundary"] = [{"action": "read"}]
    return doc


def _rejected_both_query_and_write() -> dict[str, Any]:
    """A rejected case carrying BOTH `objectQuery` and `write`.

    A rejected case pins a SINGLE invalid input, so its `when` MUST carry EXACTLY ONE
    of objectQuery/write. The schema `oneOf` (each alternative requiring one member)
    matches BOTH alternatives when both are present, so `oneOf` fails — closing the
    gap the earlier `anyOf` (>= 1, not exactly 1) left open.
    """
    doc = _rejected_query_case()
    doc["when"]["write"] = {"id": 1, "name": "Acme", "address": {"city": "Oslo"}}
    return doc


def _rejected_neither_query_nor_write() -> dict[str, Any]:
    """A rejected case carrying NEITHER `objectQuery` nor `write`.

    An empty `when` matches no `oneOf` alternative, so the rejected branch fails and
    no other top-level branch matches (the `shape` const gates them) — the document
    is rejected.
    """
    doc = _rejected_query_case()
    del doc["when"]["objectQuery"]
    return doc


def _conflict_keyed_write() -> dict[str, Any]:
    """A CONFLICT case whose `when.write` is a keyed instruction.

    The keyed form belongs to the `rejected` shape alone: every executing shape
    reaches its keyed instructions through `writeSequence` or a scenario step's own
    buffer, where the golden SQL grades them. Admitting one here would let a
    conflict case author an instruction nothing lowers.
    """
    doc = _conflict_case()
    doc["when"]["write"] = {
        "mutation": "update",
        "entity": "Balance",
        "rows": [{"id": 1, "value": 150.00}],
    }
    return doc


def _keyed_write_with_a_stray_member() -> dict[str, Any]:
    """A keyed instruction carrying a member its own definition does not declare.

    The witness that the keyed branch DECIDES the document rather than being
    shadowed by the row branch: `$defs/keyedWrite` is closed, so a stray member
    fails it — and, with `target` / `rows` reserved from `$defs/bareWriteRow`, no
    other branch admits the document either. Drop that reservation and every
    instruction is also a row, so this document validates and the keyed branch
    adds no validity at all.
    """
    doc = _rejected_keyed_write_case()
    doc["when"]["write"]["bogus"] = 1
    return doc


def _rejected_write_multi_key_array() -> dict[str, Any]:
    """A rejected case whose `when.write` is the conflict lane's multi-key ARRAY.

    All three rejected write forms are objects whose members say which one they
    are; the shared `when.write` vocabulary also carries the array, whose meaning
    is an aggregate affected-row count no rejected case emits SQL to produce. It
    reaches every dispatcher with no member to dispatch on, so the rejected branch
    requires an object.
    """
    doc = _rejected_write_case()
    doc["when"]["write"] = [{"id": 1, "name": "Acme", "address": {"city": "Oslo"}}]
    return doc


def _bare_write_row_naming_rows() -> dict[str, Any]:
    """A bare neutral write row whose entity declares a `many` value object `rows`.

    `rows` is reserved at `when.write`, so the row is refused outright instead of
    being silently re-read as a keyed instruction by every dispatcher.
    """
    doc = _conflict_case()
    doc["when"]["write"] = {"id": 2, "rows": [{"line": 1}], "observedVersion": 1}
    return doc


def _bare_write_row_naming_target() -> dict[str, Any]:
    """A bare neutral write row whose entity declares a value object `target`.

    The other reserved discriminator: `target` names the predicate-selected
    instruction, so a row may not author one either.
    """
    doc = _conflict_case()
    doc["when"]["write"] = {"id": 2, "target": {"kind": "x"}, "observedVersion": 1}
    return doc


def _settled_write_ungrouped() -> dict[str, Any]:
    """A write step naming a source find without declaring a `uow` group.

    Evidence is transaction-scoped: an ungrouped write shares a unit of work with
    no find, so there is no observation for the reference to reach.
    """
    doc = _settled_write_scenario_case()
    del doc["when"]["scenario"][1]["uow"]
    return doc


def _settled_write_on_array() -> dict[str, Any]:
    """A write step naming a SET of source finds.

    A keyed write settles against the one milestone the value it was handed came
    from, so a set of sources names no single one — the array `on` stays the
    action step's spelling alone.
    """
    doc = _settled_write_scenario_case()
    doc["when"]["scenario"][1]["on"] = [0]
    return doc


def _settled_write_legacy_string() -> dict[str, Any]:
    """A LEGACY STRING write step naming a source find.

    The label carries no instruction, so nothing in that step can consume the
    observation the reference names.
    """
    doc = _settled_write_scenario_case()
    doc["when"]["scenario"][1]["write"] = "correct the position"
    return doc


def _settled_write_predicate_selected() -> dict[str, Any]:
    """A PREDICATE-SELECTED write step naming a source find.

    A predicate-selected write selects its own rows by predicate; it consumes no
    single milestone a find handed over, so the reference names evidence nothing
    reads.
    """
    doc = _settled_write_scenario_case()
    doc["when"]["scenario"][1]["write"] = {
        "mutation": "update",
        "target": {
            "entity": "Position",
            "predicate": {"eq": {"attr": "Position.id", "value": 1}},
        },
        "assignments": [{"attr": "Position.value", "value": 150.00}],
    }
    return doc


def _action_unknown_verb() -> dict[str, Any]:
    """An action step naming a verb outside the closed enum."""
    doc = _action_scenario_case()
    doc["when"]["scenario"][1]["action"] = "teleport"
    return doc


def _action_stray_key() -> dict[str, Any]:
    """An action step carrying a stray key — the step is `additionalProperties: false`."""
    doc = _action_scenario_case()
    doc["when"]["scenario"][1]["bogus"] = True
    return doc


def _action_unknown_expect_error() -> dict[str, Any]:
    """An action step naming an `expectError` outside the closed enum."""
    doc = _action_identity_error_case()
    doc["when"]["scenario"][2]["expectError"] = "not-a-real-error"
    return doc


def _action_same_and_different_object() -> dict[str, Any]:
    """One step declares BOTH `sameObjectAs` and `differentObjectFrom` (at the same step).

    A single step's identity relationship to an anchor is sameness OR difference,
    never both — the sibling `not: required[sameObjectAs, differentObjectFrom]`
    rejects a step carrying the two together.
    """
    doc = _action_scenario_case()
    doc["when"]["scenario"][2]["differentObjectFrom"] = 1
    return doc


def _action_set_on_non_mutate() -> dict[str, Any]:
    """`set` on a non-`mutate` action (step 1 is a `load`) — the mutate-only `allOf` rejects it."""
    doc = _action_scenario_case()
    doc["when"]["scenario"][1]["set"] = {"name": "x"}
    return doc


def _action_object_verb_missing_on() -> dict[str, Any]:
    """An OBJECT-TARGETING action (step 1 is a `load`) missing `on`.

    The per-verb conditional makes `on` REQUIRED for `mutate` / `detachCopy` /
    `load` / `access` / `mergeBack` — each acts on a prior step's result — so a
    `load` without `on` is rejected (unlike a boundary `flush` / `commit` / `abort`,
    where `on` is optional)."""
    doc = _action_scenario_case()
    del doc["when"]["scenario"][1]["on"]
    return doc


def _action_on_duplicate_index() -> dict[str, Any]:
    """An array-form `on` naming the SAME source twice.

    The array form is `uniqueItems`: a coordinate-grouped action references each
    source at most once, so `on: [0, 0]` is rejected."""
    doc = _action_identity_error_case()
    doc["when"]["scenario"][2]["on"] = [0, 0]
    return doc


def _expect_graph_on_an_includeless_read_step() -> dict[str, Any]:
    """`expectGraph` on a read step declaring no `objectQuery.includes`.

    The read placement states the relationships that read materialized, and a
    read declaring no Include Path materializes none — its roots are what
    `expectRows` already states.
    """
    doc = _action_scenario_case()
    step = doc["when"]["scenario"][0]
    del step["expectRows"]
    step["expectGraph"] = {"Order": [{"id": 1}, {"id": 2}]}
    return doc


def _expect_graph_on_a_write_step() -> dict[str, Any]:
    """`expectGraph` on a write step, which navigates no relationship at all."""
    doc = _settled_write_scenario_case()
    doc["when"]["scenario"][1]["expectGraph"] = {"Position": [{"pos_id": 1}]}
    return doc


def _expect_graph_on_a_non_access_action() -> dict[str, Any]:
    """`expectGraph` on a `load` — a step that RESOLVES the relationship rather
    than reading an already-materialized one, so it grades a fresh fetch."""
    doc = _action_scenario_case()
    doc["when"]["scenario"][1]["expectGraph"] = {"OrderItem": [{"id": 11}]}
    return doc


def _expect_graph_on_a_multi_source_access() -> dict[str, Any]:
    """`expectGraph` on an access naming the `on` ARRAY form.

    The array spans sources at different lowered coordinates, so contents gathered
    across them are a graph no single materialized view holds; an access stating
    contents names the one read whose Include Paths materialized them.
    """
    doc = _action_expect_graph_case()
    doc["when"]["scenario"][2]["on"] = [0]
    return doc


def _expect_graph_without_a_navigated_path() -> dict[str, Any]:
    """`expectGraph` on an access naming no `path`.

    The path-less `access` form resolves a query-backed list's own source entity
    and navigates no relationship, so it reaches no relationship contents to state
    and no accessed path the source read's `objectQuery.includes` could cover.
    """
    doc = _action_expect_graph_case()
    del doc["when"]["scenario"][2]["path"]
    return doc


def _expect_graph_beside_expect_rows() -> dict[str, Any]:
    """One step declaring BOTH `expectRows` and `expectGraph`.

    `expectRows` states the step's own source rows and `expectGraph` the contents
    of the relationship it navigated TO, so the two describe different entities.
    """
    doc = _action_expect_graph_case()
    doc["when"]["scenario"][2]["expectRows"] = [{"id": 1}]
    return doc


def _expect_graph_stating_no_entity() -> dict[str, Any]:
    """`expectGraph` as an EMPTY map.

    An empty to-many view is authored as the path's target entity keyed to an
    empty list — the contents a loaded relationship answered — not as a graph
    naming no entity, which would state nothing and pass against anything.
    """
    doc = _action_expect_graph_case()
    doc["when"]["scenario"][2]["expectGraph"] = {}
    return doc


def _graphs_entry_missing_pin() -> dict[str, Any]:
    """A `then.graphs` entry missing `pin` — the entry requires it.

    Each per-milestone graph MUST declare the edge coordinate it is pinned at, so an
    entry carrying only `graph` is rejected."""
    doc = _graphs_read_case()
    del doc["then"]["graphs"][0]["pin"]
    return doc


def _graphs_entry_stray_key() -> dict[str, Any]:
    """A `then.graphs` entry with a stray key — the entry is `additionalProperties: false`."""
    doc = _graphs_read_case()
    doc["then"]["graphs"][0]["bogus"] = True
    return doc


def _stored_data_record_missing_hydration() -> dict[str, Any]:
    """A `then.storedDataIssues` entry missing `hydrated` — the entry requires it.

    Whether the collapse produced a value is the one fact the graph position cannot
    state on its own, so a record that omits it is rejected."""
    doc = _stored_data_issues_read_case()
    del doc["then"]["storedDataIssues"][0]["hydrated"]
    return doc


def _stored_data_issue_unknown_code() -> dict[str, Any]:
    """A `then.storedDataIssues` diagnosis outside the closed code vocabulary.

    The stored-data codes are a closed set (`m-snapshot-read`); a code no seam can
    ever publish would assert an outcome no implementation could produce."""
    doc = _stored_data_issues_read_case()
    doc["then"]["storedDataIssues"][0]["issues"][0]["code"] = "stored-data-made-up"
    return doc


def _write_value_step_with_golden_statements() -> dict[str, Any]:
    """A keyed write action step listing golden SQL.

    Such a step carries NONE: a refusal stops the verb before it buffers
    anything, and the only acceptance this shape admits buffers nothing either,
    so any `statements` there claims an emission the step cannot have."""
    doc = _write_value_scenario_case()
    doc["when"]["scenario"][0]["statements"] = [
        {"sql": {"postgres": "update account set balance = ? where id = ?"}, "binds": [1, 2]}
    ]
    return doc


def _write_value_step_costing_a_round_trip() -> dict[str, Any]:
    """A keyed write action step declaring a nonzero `roundTrips`.

    The step's whole observable is which verb accepted the value, so it costs
    zero round trips by construction."""
    doc = _write_value_scenario_case()
    doc["when"]["scenario"][0]["roundTrips"] = 1
    return doc


def _write_value_step_accepting_an_insert() -> dict[str, Any]:
    """A keyed write action step declaring an ACCEPTED `insert`.

    An accepted `insert` opens a row: the verb buffers a write the committing
    unit of work flushes, so the step emits DML while its `roundTrips: 0` denies
    it — and no executor could catch the contradiction, since the suite that runs
    this lane asserts no golden SQL and grades the declared zero as the absence of
    exactly the durable effect the acceptance produces. The only accepted keyed
    write this shape carries is the `update` of a value no author changed."""
    doc = _write_value_scenario_case()
    doc["when"]["scenario"][2] = {"action": "insert", "value": "unmanaged", "roundTrips": 0}
    return doc


def _write_value_scenario_on_the_harness_lane() -> dict[str, Any]:
    """A keyed-write-value scenario declaring `lane: harness`.

    The wire harness holds no client value to hand a verb, so it can neither
    arrange the step's provenance nor execute the step — and a scenario is one
    ordered execution rather than a set of steps to divide between executors, so
    the whole case is `api-conformance` or it is gradeable by nobody."""
    doc = _write_value_scenario_case()
    doc["lane"] = "harness"
    return doc


def _write_value_scenario_without_a_lane() -> dict[str, Any]:
    """A keyed-write-value scenario declaring no lane at all.

    The lane default is `harness`, which this case cannot be, so the routing is
    REQUIRED here rather than left to a default that would misroute it."""
    doc = _write_value_scenario_case()
    del doc["lane"]
    return doc


def _write_value_scenario_mixing_another_step() -> dict[str, Any]:
    """A keyed-write-value scenario carrying a find step beside its keyed steps.

    The case is api-conformance throughout, so the API Conformance Suite is its
    only executor — and that suite asserts no golden SQL, while a scenario
    asserts no `then.tableState`. The neighbour's oracle is therefore gradeable
    by nobody, which is why the mixture is refused here rather than left to an
    executor to discover."""
    doc = _write_value_scenario_case()
    doc["when"]["scenario"].append(
        {
            "objectQuery": {
                "target": "parallax.compatibility.Account",
                "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 2}},
            },
            "roundTrips": 1,
            "statements": [
                {
                    "sql": {"postgres": "select t0.id from account t0 where t0.id = ?"},
                    "binds": [2],
                }
            ],
        }
    )
    doc["then"]["roundTrips"] = 1
    return doc


def _read_case_with_zero_round_trips() -> dict[str, Any]:
    """A read case declaring `then.roundTrips: 0`.

    Zero is legal only for the two shapes that can cost nothing — a scenario
    whose steps all cost none, and a pre-SQL `rejected` refusal; a read executes
    the golden SQL it asserts, so an all-zero total is impossible and is refused
    here rather than in a later harness check."""
    doc = _read_case()
    doc["then"]["roundTrips"] = 0
    return doc


def _rejected_case_costing_a_round_trip() -> dict[str, Any]:
    """A rejected case declaring `then.roundTrips: 1`.

    A rejected case's input is refused before any statement is composed, so one
    round trip is not merely unasserted but impossible."""
    doc = _rejected_query_case()
    doc["then"]["roundTrips"] = 1
    return doc


def _streamed_read_case(**stream: Any) -> dict[str, Any]:
    return {
        "model": "models/orders.yaml",
        "tags": ["m-snapshot-read"],
        "shape": "read",
        "compileEligibility": {"mode": "run-only", "reason": "query-result-dependent"},
        "when": {
            "objectQuery": {"target": "Order", "predicate": {"all": {}}},
            "stream": {"batchSize": 2, **stream},
        },
        "then": {
            "statements": [
                {
                    "sql": {"postgres": "select t0.id from orders t0 order by t0.id asc limit ?"},
                    "binds": [2],
                }
            ],
            "graph": {"Order": [{"id": 1}]},
            "roundTrips": 1,
        },
    }


def test_schema_accepts_a_streamed_read_case() -> None:
    assert _is_valid(_streamed_read_case())


def _corruption() -> dict[str, Any]:
    return {"entity": "Order", "key": 1, "member": ["profile", "city"], "value": 7}


def test_schema_accepts_a_read_case_corrupting_its_stored_state() -> None:
    doc = _read_case()
    doc["given"] = {"corrupt": [_corruption()]}
    assert _is_valid(doc)


def _corrupt_on_a_write_sequence() -> dict[str, Any]:
    # Only a read lane applies `given.corrupt`, so every other shape declaring it
    # asserts a verdict about storage its own execution never produced.
    doc = _write_sequence_case()
    doc["given"] = {"corrupt": [_corruption()]}
    return doc


def _corrupt_on_a_scenario() -> dict[str, Any]:
    doc = _scenario_case()
    doc["given"] = {"corrupt": [_corruption()]}
    return doc


def _commit_step_on_a_scenario() -> dict[str, Any]:
    # A `kind: commit` step commits a node's own held session, which only the two
    # shapes carrying `when.concurrency` have. A scenario commits each `uow` group
    # after its last step, so a choreography member here names machinery the shape
    # does not run.
    doc = _scenario_case()
    doc["when"]["concurrency"] = {"rounds": [{"A": {"kind": "commit"}}]}
    return doc


def _error_step_declaring_a_write_kind() -> dict[str, Any]:
    # An error choreography's statement step declares no `kind` at all: `read` and
    # `write` are the concurrency-success form's grading vocabulary, and an error
    # case grades only the classified error. A step naming one would run
    # differently per runner while nothing on the shape observes the difference.
    doc = _error_concurrency_case()
    doc["when"]["concurrency"]["rounds"][0]["A"]["kind"] = "write"
    return doc


def _error_step_declaring_a_read_kind() -> dict[str, Any]:
    # The same refusal for the graded half of that vocabulary, carrying the
    # `expectRows` a read step requires — so what refuses it is the error branch's
    # own narrowing rather than the step def's read/`expectRows` pairing.
    doc = _error_concurrency_case()
    doc["when"]["concurrency"]["rounds"][0]["A"]["kind"] = "read"
    doc["when"]["concurrency"]["rounds"][0]["A"]["expectRows"] = [{"id": 1}]
    return doc


def _error_statement_step_grading_rows() -> dict[str, Any]:
    # The `kind`-less statement step is the error shape's own form, so nothing about
    # its kind refuses it — yet an error case asserts only the classified error, and
    # both runners would ignore rows authored here. The branch refuses `expectRows`
    # on every step rather than let a case state an assertion nothing grades.
    doc = _error_concurrency_case()
    doc["when"]["concurrency"]["rounds"][0]["A"]["expectRows"] = [{"id": 1}]
    return doc


def _isolation_on_a_scenario_step() -> dict[str, Any]:
    # A level is the whole case's, declared once under `when.uow`; a step naming its
    # own would leave one scenario's groups running at levels nothing states together.
    doc = _scenario_case()
    doc["when"]["scenario"][0]["isolation"] = "serializable"
    return doc


def _streamed_without_page_size() -> dict[str, Any]:
    doc = _streamed_read_case()
    doc["when"]["stream"] = {}
    return doc


def _streamed_zero_page_size() -> dict[str, Any]:
    return _streamed_read_case(batchSize=0)


def _streamed_negative_page_size() -> dict[str, Any]:
    return _streamed_read_case(batchSize=-1)


def _streamed_fractional_page_size() -> dict[str, Any]:
    return _streamed_read_case(batchSize=1.5)


def _streamed_naming_a_representation() -> dict[str, Any]:
    # `when.stream` names the delivery and never a representation: a member no
    # adapter could honor is refused rather than ignored (m-case-format).
    return _streamed_read_case(interface="typed")


def _streamed_beside_rows() -> dict[str, Any]:
    doc = _streamed_read_case()
    doc["then"].pop("graph")
    doc["then"]["rows"] = [{"id": 1}]
    return doc


def _streamed_write_sequence() -> dict[str, Any]:
    doc = _write_sequence_case()
    doc["when"]["stream"] = {"batchSize": 2}
    return doc


def _streamed_scenario_step_case() -> dict[str, Any]:
    """A scenario whose grouped find is delivered as a stream, and the write it
    licenses (`m-case-format` *Streamed read steps*)."""
    doc = _settled_write_scenario_case()
    doc["when"]["scenario"][0]["stream"] = {"batchSize": 2}
    doc["when"]["scenario"][0]["roundTrips"] = 2
    doc["when"]["scenario"][0]["statements"].append(
        {
            "sql": {"postgres": "select t0.pos_id from position t0 where t0.pos_id > ?"},
            "binds": [1, 2],
        }
    )
    doc["then"]["roundTrips"] = 3
    return doc


def test_schema_accepts_a_streamed_scenario_read_step() -> None:
    assert _is_valid(_streamed_scenario_step_case())


def _streamed_step_without_a_group() -> dict[str, Any]:
    # A delivery's evidence is transaction-scoped, so a streamed step outside a
    # `uow` group has nothing to hand a later write.
    doc = _streamed_scenario_step_case()
    del doc["when"]["scenario"][0]["uow"]
    return doc


def _streamed_write_step() -> dict[str, Any]:
    # Delivery is how a READ is consumed; a write step consumes no result.
    doc = _streamed_scenario_step_case()
    doc["when"]["scenario"][1]["stream"] = {"batchSize": 2}
    return doc


def _streamed_step_including_a_level() -> dict[str, Any]:
    # A streamed step states its roots and nothing under them: `expectRows` is its
    # own content oracle, and a level below the roots reaches no step-level oracle
    # at all — the include is refused on its own, before any observable is stated.
    doc = _streamed_scenario_step_case()
    doc["when"]["scenario"][0]["objectQuery"]["includes"] = [
        {"segments": [{"rel": "Position.legs"}]}
    ]
    return doc


def _streamed_step_stating_relationship_contents() -> dict[str, Any]:
    # The same refusal reached from the observable's side.
    doc = _streamed_scenario_step_case()
    doc["when"]["scenario"][0]["objectQuery"]["includes"] = [
        {"segments": [{"rel": "Position.legs"}]}
    ]
    doc["when"]["scenario"][0].pop("expectRows")
    doc["when"]["scenario"][0]["expectGraph"] = {"Position": [{"id": 1}]}
    return doc


def _streamed_step_zero_page_size() -> dict[str, Any]:
    doc = _streamed_scenario_step_case()
    doc["when"]["scenario"][0]["stream"] = {"batchSize": 0}
    return doc


def _streamed_step_naming_a_representation() -> dict[str, Any]:
    # The second placement is the same closed member: it names no representation
    # there either.
    doc = _streamed_scenario_step_case()
    doc["when"]["scenario"][0]["stream"] = {"batchSize": 2, "interface": "typed"}
    return doc


REJECTED_CASES = {
    "write-value-step-with-golden-statements": _write_value_step_with_golden_statements,
    "write-value-step-costing-a-round-trip": _write_value_step_costing_a_round_trip,
    "write-value-step-accepting-an-insert": _write_value_step_accepting_an_insert,
    "write-value-scenario-on-the-harness-lane": _write_value_scenario_on_the_harness_lane,
    "write-value-scenario-without-a-lane": _write_value_scenario_without_a_lane,
    "write-value-scenario-mixing-another-step": _write_value_scenario_mixing_another_step,
    "read-with-zero-round-trips": _read_case_with_zero_round_trips,
    "rejected-costing-a-round-trip": _rejected_case_costing_a_round_trip,
    "legacy-layout": _legacy_layout,
    "mislabeled-shape": _mislabeled_shape,
    "string-sql-at-golden-location": _string_sql_at_golden_location,
    "empty-sql-map": _empty_sql_map,
    "extra-key-in-closed-group": _extra_key_in_closed_group,
    "binds-outside-statement-entry": _binds_outside_statement_entry,
    "attempt-legacy-affected-rows": _attempt_legacy_affected_rows,
    "cross-shape-when-member": _cross_shape_when_member,
    "read-missing-target": _read_missing_target,
    "scenario-find-missing-query": _scenario_find_missing_query,
    "coherence-read-missing-query": _coherence_read_missing_query,
    "rejected-without-rule": _rejected_without_rule,
    "rejected-unknown-rule": _rejected_unknown_rule,
    "rejected-with-golden-statements": _rejected_with_golden_statements,
    "rejected-cross-shape-when-member": _rejected_cross_shape_when_member,
    "rejected-both-query-and-write": _rejected_both_query_and_write,
    "rejected-neither-query-nor-write": _rejected_neither_query_nor_write,
    "conflict-keyed-write": _conflict_keyed_write,
    "keyed-write-stray-member": _keyed_write_with_a_stray_member,
    "rejected-write-multi-key-array": _rejected_write_multi_key_array,
    "bare-write-row-naming-rows": _bare_write_row_naming_rows,
    "bare-write-row-naming-target": _bare_write_row_naming_target,
    "settled-write-ungrouped": _settled_write_ungrouped,
    "settled-write-on-array": _settled_write_on_array,
    "settled-write-legacy-string": _settled_write_legacy_string,
    "settled-write-predicate-selected": _settled_write_predicate_selected,
    "action-unknown-verb": _action_unknown_verb,
    "action-stray-key": _action_stray_key,
    "action-unknown-expect-error": _action_unknown_expect_error,
    "action-same-and-different-object": _action_same_and_different_object,
    "action-set-on-non-mutate": _action_set_on_non_mutate,
    "action-object-verb-missing-on": _action_object_verb_missing_on,
    "action-on-duplicate-index": _action_on_duplicate_index,
    "expect-graph-on-an-includeless-read-step": _expect_graph_on_an_includeless_read_step,
    "expect-graph-on-a-write-step": _expect_graph_on_a_write_step,
    "expect-graph-on-a-non-access-action": _expect_graph_on_a_non_access_action,
    "expect-graph-on-a-multi-source-access": _expect_graph_on_a_multi_source_access,
    "expect-graph-without-a-navigated-path": _expect_graph_without_a_navigated_path,
    "expect-graph-beside-expect-rows": _expect_graph_beside_expect_rows,
    "expect-graph-stating-no-entity": _expect_graph_stating_no_entity,
    "graphs-entry-missing-pin": _graphs_entry_missing_pin,
    "graphs-entry-stray-key": _graphs_entry_stray_key,
    "stored-data-record-missing-hydration": _stored_data_record_missing_hydration,
    "stored-data-issue-unknown-code": _stored_data_issue_unknown_code,
    "streamed-without-page-size": _streamed_without_page_size,
    "streamed-zero-page-size": _streamed_zero_page_size,
    "streamed-negative-page-size": _streamed_negative_page_size,
    "streamed-fractional-page-size": _streamed_fractional_page_size,
    "streamed-naming-a-representation": _streamed_naming_a_representation,
    "streamed-beside-rows": _streamed_beside_rows,
    "streamed-write-sequence": _streamed_write_sequence,
    "streamed-step-without-a-group": _streamed_step_without_a_group,
    "streamed-write-step": _streamed_write_step,
    "streamed-step-including-a-level": _streamed_step_including_a_level,
    "streamed-step-stating-relationship-contents": _streamed_step_stating_relationship_contents,
    "streamed-step-zero-page-size": _streamed_step_zero_page_size,
    "streamed-step-naming-a-representation": _streamed_step_naming_a_representation,
    "corrupt-on-a-write-sequence": _corrupt_on_a_write_sequence,
    "corrupt-on-a-scenario": _corrupt_on_a_scenario,
    "commit-step-on-a-scenario": _commit_step_on_a_scenario,
    "isolation-on-a-scenario-step": _isolation_on_a_scenario_step,
    "error-step-declaring-a-write-kind": _error_step_declaring_a_write_kind,
    "error-step-declaring-a-read-kind": _error_step_declaring_a_read_kind,
    "error-statement-step-grading-rows": _error_statement_step_grading_rows,
}


@pytest.mark.parametrize("label", sorted(REJECTED_CASES))
def test_schema_rejects_malformed_case(label: str) -> None:
    doc = REJECTED_CASES[label]()
    assert not _is_valid(doc), f"{label} document should be rejected by the schema"
