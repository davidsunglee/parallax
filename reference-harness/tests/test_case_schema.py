"""DB-free fidelity tests for the grouped compatibility-case schema (COR-23).

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


def _is_valid(doc: dict[str, Any]) -> bool:
    return next(_validator().iter_errors(doc), None) is None


# --- minimal well-formed documents, one per shape --------------------------


def _read_case() -> dict[str, Any]:
    return {
        "model": "models/orders.yaml",
        "tags": ["m-agg"],
        "shape": "read",
        "when": {"targetEntity": "Order", "operation": {"all": {}}},
        "then": {
            "statements": [{"sql": {"postgres": "select t0.id from orders t0"}, "binds": []}],
            "rows": [{"id": 1}],
            "roundTrips": 1,
        },
    }


def _write_sequence_case() -> dict[str, Any]:
    return {
        "model": "models/balance.yaml",
        "tags": ["m-audit-write"],
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
                    "targetEntity": "Account",
                    "find": {"eq": {"attr": "Account.id", "value": 7}},
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


def _action_scenario_case() -> dict[str, Any]:
    """A scenario with lifecycle ACTION steps (m-case-format, COR-30).

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
                    "targetEntity": "Order",
                    "find": {"in": {"attr": "Order.id", "values": [1, 2]}},
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


def _action_identity_error_case() -> dict[str, Any]:
    """A scenario action case exercising `differentObjectFrom`, `on` array, `expectError`."""
    return {
        "model": "models/orders.yaml",
        "tags": ["m-detach"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "targetEntity": "Order",
                    "find": {"eq": {"attr": "Order.id", "value": 1}},
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
                    "targetEntity": "Account",
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


def _rejected_operation_case() -> dict[str, Any]:
    """A rejected case carrying an invalid OPERATION + the violated rule (COR-10, Q7)."""
    return {
        "model": "models/customer.yaml",
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": {"operation": {"nestedEq": {"path": "Customer.contact.city", "value": "Oslo"}}},
        "then": {"rejectedRule": "nested-path-first-segment-not-value-object"},
    }


def _rejected_write_case() -> dict[str, Any]:
    """A rejected case carrying an invalid WRITE input + the violated rule (COR-10, Q7)."""
    return {
        "model": "models/contact.yaml",
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": {"write": {"id": 1, "name": "Acme", "address": {"city": "Oslo"}}},
        "then": {"rejectedRule": "write-required-attribute-missing"},
    }


def _action_boundary_no_on_case() -> dict[str, Any]:
    """A scenario whose BOUNDARY action verbs (`flush` / `commit`) omit `on` (COR-30).

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
                    "targetEntity": "Order",
                    "find": {"eq": {"attr": "Order.id", "value": 1}},
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
    """A read case carrying per-milestone `then.graphs` (m-snapshot-read, COR-30 Q5a).

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
            "targetEntity": "InvoiceLine",
            "operation": {
                "history": {
                    "operand": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
                    "dimension": "InvoiceLine.transactionTime",
                }
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
                    "pin": {"transactionTime": "2024-01-01T00:00:00+00:00"},
                    "graph": {"InvoiceLine": [{"id": 1000, "amount": 50.00}]},
                },
                {
                    "pin": {"transactionTime": "2024-04-01T00:00:00+00:00"},
                    "graph": {"InvoiceLine": [{"id": 1000, "amount": 75.00}]},
                },
            ],
            "roundTrips": 1,
        },
    }


def _identity_checks_read_case() -> dict[str, Any]:
    """A read case carrying a `then.identityChecks` back-reference cycle (COR-30 Q5b).

    A back-reference cycle (`[items, items.order]`) serializes the cycle point as a
    PK-only stub; the same-node claim rides `then.identityChecks`, an array of
    `{left, right, same}` entries with JSON-Pointer `left` / `right`.
    """
    return {
        "model": "models/orders.yaml",
        "tags": ["m-snapshot-read", "m-deep-fetch"],
        "shape": "read",
        "when": {
            "targetEntity": "Order",
            "operation": {
                "deepFetch": {
                    "operand": {"eq": {"attr": "Order.id", "value": 1}},
                    "paths": [[{"rel": "Order.items"}, {"rel": "OrderItem.order"}]],
                }
            },
        },
        "then": {
            "statements": [
                {"sql": {"postgres": "select t0.id from orders t0 where t0.id = ?"}, "binds": [1]}
            ],
            "graph": {"Order": [{"id": 1, "items": [{"id": 11, "order": {"id": 1}}]}]},
            "identityChecks": [
                {
                    "left": "/then/graph/Order/0",
                    "right": "/then/graph/Order/0/items/0/order",
                    "same": True,
                }
            ],
            "roundTrips": 1,
        },
    }


VALID_CASES = {
    "read": _read_case,
    "writeSequence": _write_sequence_case,
    "scenario": _scenario_case,
    "scenario-action": _action_scenario_case,
    "scenario-action-identity-error": _action_identity_error_case,
    "scenario-action-boundary-no-on": _action_boundary_no_on_case,
    "conflict": _conflict_case,
    "conflict-retry": _conflict_retry_case,
    "coherence": _coherence_case,
    "error": _error_case,
    "concurrencySuccess": _concurrency_success_case,
    "boundary": _boundary_case,
    "read-graphs": _graphs_read_case,
    "read-identity-checks": _identity_checks_read_case,
    "rejected-operation": _rejected_operation_case,
    "rejected-write": _rejected_write_case,
}


@pytest.mark.parametrize("shape", sorted(VALID_CASES))
def test_schema_accepts_minimal_case_for_every_shape(shape: str) -> None:
    doc = VALID_CASES[shape]()
    errors = list(_validator().iter_errors(doc))
    assert errors == [], f"{shape} case should validate, got: {[e.message for e in errors]}"


# --- value-object document whose content is marker-SHAPED (COR-10) ---------
#
# A DB-computed marker (`{computed}` / `{increment}`) vs a value-object document is
# a MODEL-ROLE decision the model-agnostic schema cannot make, so the write-value
# branches are NON-exclusive: a value-object column's value is ALWAYS literal
# document content, even when the authored document happens to be shaped like a
# marker. These documents MUST validate as a value-object write row.


def _value_object_document_case(document: Any) -> dict[str, Any]:
    """A writeSequence insert whose `address` value object carries *document*.

    `address` is a top-level value object on the customer model, so its value is
    the WHOLE literal document bound in columnOrder position — the marker-shaped
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
        "operation": {"all": {}},
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
    (`operation` / `targetEntity` / `uow` / `equivalentEncodings`), so a
    mislabeled/mixed document that also carries an unrelated action member fails its
    shape branch and no other branch matches — the `oneOf` rejects it.
    """
    doc = _read_case()
    doc["when"]["boundary"] = [{"action": "read"}]
    return doc


def _read_missing_target_entity() -> dict[str, Any]:
    """A read case missing `when.targetEntity` (m-case-format Q1): the branch requires it."""
    doc = _read_case()
    del doc["when"]["targetEntity"]
    return doc


def _scenario_find_missing_target_entity() -> dict[str, Any]:
    """A scenario read step missing `targetEntity` (Q1): the read-step branch requires it."""
    doc = _scenario_case()
    del doc["when"]["scenario"][0]["targetEntity"]
    return doc


def _coherence_read_missing_target_entity() -> dict[str, Any]:
    """A coherence read step missing `targetEntity` (Q1): the read conditional requires it."""
    doc = _coherence_case()
    del doc["when"]["coherence"][0]["targetEntity"]
    return doc


def _rejected_without_rule() -> dict[str, Any]:
    """A rejected case missing `then.rejectedRule` (COR-10, Q7): the branch requires it."""
    doc = _rejected_operation_case()
    del doc["then"]["rejectedRule"]
    return doc


def _rejected_unknown_rule() -> dict[str, Any]:
    """A rejected case naming a rule outside the closed vocabulary — the enum rejects it."""
    doc = _rejected_operation_case()
    doc["then"]["rejectedRule"] = "not-a-real-rule"
    return doc


def _rejected_with_golden_statements() -> dict[str, Any]:
    """A rejected case carrying golden `then.statements` — disallowed (rejection is pre-SQL)."""
    doc = _rejected_operation_case()
    doc["then"]["statements"] = [{"sql": {"postgres": "select t0.id from customer t0"}}]
    return doc


def _rejected_cross_shape_when_member() -> dict[str, Any]:
    """A rejected case carrying a stray `when.boundary` (its `when` allows only operation/write)."""
    doc = _rejected_operation_case()
    doc["when"]["boundary"] = [{"action": "read"}]
    return doc


def _rejected_both_operation_and_write() -> dict[str, Any]:
    """A rejected case carrying BOTH `operation` and `write` (COR-10, Q7).

    A rejected case pins a SINGLE invalid input, so its `when` MUST carry EXACTLY ONE
    of operation/write. The schema `oneOf` (each alternative requiring one member)
    matches BOTH alternatives when both are present, so `oneOf` fails — closing the
    gap the earlier `anyOf` (>= 1, not exactly 1) left open.
    """
    doc = _rejected_operation_case()
    doc["when"]["write"] = {"id": 1, "name": "Acme", "address": {"city": "Oslo"}}
    return doc


def _rejected_neither_operation_nor_write() -> dict[str, Any]:
    """A rejected case carrying NEITHER `operation` nor `write` (COR-10, Q7).

    An empty `when` matches no `oneOf` alternative, so the rejected branch fails and
    no other top-level branch matches (the `shape` const gates them) — the document
    is rejected.
    """
    doc = _rejected_operation_case()
    del doc["when"]["operation"]
    return doc


def _action_unknown_verb() -> dict[str, Any]:
    """An action step naming a verb outside the closed enum (COR-30)."""
    doc = _action_scenario_case()
    doc["when"]["scenario"][1]["action"] = "teleport"
    return doc


def _action_stray_key() -> dict[str, Any]:
    """An action step carrying a stray key — the step is `additionalProperties: false`."""
    doc = _action_scenario_case()
    doc["when"]["scenario"][1]["bogus"] = True
    return doc


def _action_unknown_expect_error() -> dict[str, Any]:
    """An action step naming an `expectError` outside the closed enum (COR-30)."""
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
    """An OBJECT-TARGETING action (step 1 is a `load`) missing `on` (COR-30).

    The per-verb conditional makes `on` REQUIRED for `mutate` / `detachCopy` /
    `load` / `access` / `mergeBack` — each acts on a prior step's result — so a
    `load` without `on` is rejected (unlike a boundary `flush` / `commit` / `abort`,
    where `on` is optional)."""
    doc = _action_scenario_case()
    del doc["when"]["scenario"][1]["on"]
    return doc


def _action_on_duplicate_index() -> dict[str, Any]:
    """An array-form `on` naming the SAME source twice (COR-30).

    The array form is `uniqueItems`: a coordinate-grouped action references each
    source at most once, so `on: [0, 0]` is rejected."""
    doc = _action_identity_error_case()
    doc["when"]["scenario"][2]["on"] = [0, 0]
    return doc


def _graphs_entry_missing_pin() -> dict[str, Any]:
    """A `then.graphs` entry missing `pin` (COR-30 Q5a) — the entry requires it.

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


def _identity_check_missing_same() -> dict[str, Any]:
    """A `then.identityChecks` entry missing `same` (COR-30 Q5b) — the entry requires it.

    An identity check without its reference verdict asserts nothing, so it is rejected."""
    doc = _identity_checks_read_case()
    del doc["then"]["identityChecks"][0]["same"]
    return doc


def _identity_check_stray_key() -> dict[str, Any]:
    """A `then.identityChecks` entry with a stray key — the entry is `additionalProperties: false`.

    The compatibility `identityCheck` carries only `{left, right, same}` — no optional
    `identity` witness (that is the adapter-side observation), so a stray key is rejected."""
    doc = _identity_checks_read_case()
    doc["then"]["identityChecks"][0]["identity"] = {"pk": 1}
    return doc


REJECTED_CASES = {
    "legacy-layout": _legacy_layout,
    "mislabeled-shape": _mislabeled_shape,
    "string-sql-at-golden-location": _string_sql_at_golden_location,
    "empty-sql-map": _empty_sql_map,
    "extra-key-in-closed-group": _extra_key_in_closed_group,
    "binds-outside-statement-entry": _binds_outside_statement_entry,
    "attempt-legacy-affected-rows": _attempt_legacy_affected_rows,
    "cross-shape-when-member": _cross_shape_when_member,
    "read-missing-target-entity": _read_missing_target_entity,
    "scenario-find-missing-target-entity": _scenario_find_missing_target_entity,
    "coherence-read-missing-target-entity": _coherence_read_missing_target_entity,
    "rejected-without-rule": _rejected_without_rule,
    "rejected-unknown-rule": _rejected_unknown_rule,
    "rejected-with-golden-statements": _rejected_with_golden_statements,
    "rejected-cross-shape-when-member": _rejected_cross_shape_when_member,
    "rejected-both-operation-and-write": _rejected_both_operation_and_write,
    "rejected-neither-operation-nor-write": _rejected_neither_operation_nor_write,
    "action-unknown-verb": _action_unknown_verb,
    "action-stray-key": _action_stray_key,
    "action-unknown-expect-error": _action_unknown_expect_error,
    "action-same-and-different-object": _action_same_and_different_object,
    "action-set-on-non-mutate": _action_set_on_non_mutate,
    "action-object-verb-missing-on": _action_object_verb_missing_on,
    "action-on-duplicate-index": _action_on_duplicate_index,
    "graphs-entry-missing-pin": _graphs_entry_missing_pin,
    "graphs-entry-stray-key": _graphs_entry_stray_key,
    "identity-check-missing-same": _identity_check_missing_same,
    "identity-check-stray-key": _identity_check_stray_key,
}


@pytest.mark.parametrize("label", sorted(REJECTED_CASES))
def test_schema_rejects_malformed_case(label: str) -> None:
    doc = REJECTED_CASES[label]()
    assert not _is_valid(doc), f"{label} document should be rejected by the schema"
