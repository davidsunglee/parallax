"""What a failing read reports, and what it does not touch on the way there.

Two contracts meet here. An authored failure is a ``CaseFailure`` naming the case
file — and, at a Scenario step, the index of the step — so the person who wrote
the case can find it. An infrastructure failure is the driver's own exception,
unwrapped, so a dead connection is never reported as a semantic mismatch. And a
failure knowable before execution costs no database work at all, which is only
observable as an empty call log.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.object_query_oracle import ScenarioReads, assert_case_read
from reference_harness.object_query_oracle import execute as oracle_execute

from .conftest import ScriptedReads

CaseLoader = Callable[[str], Case]

_ORDER_BY_LIMIT = "m-object-query-001-order-by-limit.yaml"
_TPH_DOCUMENT_UNION = "m-inheritance-124-document-layout-tph-sibling-path-reuse.yaml"
_TPCS_TEMPORAL_UNION = "m-inheritance-093-tpcs-temporal-union-read.yaml"
_ONE_OBJECT_TWO_FINDS = "m-identity-map-001-same-transaction-identity.yaml"
_STREAMED_EVIDENCE = "m-unit-work-030-a-streamed-roots-evidence-licenses-a-later-write.yaml"
_EDIT_KEEPS_ITEMS = "m-snapshot-read-016-edit-keeps-loaded-items.yaml"


class _DriverError(Exception):
    """Stands for a psycopg / pymysql error: not an ``AssertionError`` subclass."""


def _refusing_reads() -> ScriptedReads:
    """An executor whose every call is a test failure rather than a case failure."""
    return ScriptedReads(results=[])


def test_an_unguarded_partition_branch_is_refused_before_any_statement_runs(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_TPH_DOCUMENT_UNION)
    entry = case.then["statements"][0]
    entry["sql"]["postgres"] = entry["sql"]["postgres"].replace(
        "where t0.kind = ?", "where t0.id = ?", 1
    )
    reads = _refusing_reads()

    with pytest.raises(CaseFailure, match="no equality guard on discriminator"):
        assert_case_read(case, reads)

    assert reads.calls == []


def test_a_wrong_temporal_bind_vector_is_refused_before_any_statement_runs(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_TPCS_TEMPORAL_UNION)
    entry = case.then["statements"][0]
    entry["binds"] = list(entry["binds"])[:-1]
    reads = _refusing_reads()

    with pytest.raises(CaseFailure, match="temporal contributions"):
        assert_case_read(case, reads)

    assert reads.calls == []


def test_a_driver_exception_from_the_golden_read_propagates_unchanged(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    failure = _DriverError("server closed the connection unexpectedly")
    reads = ScriptedReads(results=[failure])

    with pytest.raises(_DriverError) as raised:
        assert_case_read(case, reads)

    assert raised.value is failure


def test_a_driver_exception_from_the_reference_oracle_propagates_unchanged(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    failure = _DriverError("deadlock detected")
    reads = ScriptedReads(results=[_authored_rows(corpus_case(_ORDER_BY_LIMIT)), failure])

    with pytest.raises(_DriverError) as raised:
        assert_case_read(case, reads)

    assert raised.value is failure


def _authored_rows(case: Case) -> list[dict[str, Any]]:
    """The case's own ``then.rows``, which for this model is also its physical row."""
    return [dict(row) for row in case.expected_rows]


@pytest.mark.parametrize(
    ("case_name", "results"),
    [
        (_ORDER_BY_LIMIT, [[]]),
        (_ORDER_BY_LIMIT, [None, []]),
    ],
    ids=["golden mismatch", "reference mismatch"],
)
def test_every_authored_failure_names_the_case_file(
    corpus_case: CaseLoader, case_name: str, results: list[Any]
) -> None:
    case = corpus_case(case_name)
    scripted = [_authored_rows(case) if entry is None else entry for entry in results]
    reads = ScriptedReads(results=scripted)

    with pytest.raises(CaseFailure) as raised:
        assert_case_read(case, reads)

    assert str(raised.value).startswith(f"{case.path.name}: ")


def test_a_case_failure_is_an_assertion_error_so_a_runner_reports_it_as_one(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    reads = ScriptedReads(results=[[]])

    with pytest.raises(AssertionError):
        assert_case_read(case, reads)


# --- the Scenario half: a step failure also names the step --------------------


def _account(id_: int, owner: str, balance: str, version: int) -> dict[str, Any]:
    return {"id": id_, "owner": owner, "balance": Decimal(balance), "version": version}


_LINUS = [_account(2, "Linus", "250.00", 1)]
_ORDER_ONE = [
    {
        "id": 1,
        "name": "Ada",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": "2024-01-05",
    }
]
# `Order.items` declares `id desc`, so a child level must return 12 before 11.
_ORDER_ONE_ITEMS = [
    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": "2024-02-15"},
    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
]
_DELIVERY = [
    [_account(1, "Ada", "100.00", 1), _account(2, "Linus", "250.00", 1)],
    [_account(3, "Grace", "10.00", 1)],
    [
        _account(1, "Ada", "100.00", 1),
        _account(2, "Linus", "250.00", 1),
        _account(3, "Grace", "10.00", 1),
    ],
]


def _wrong_rows(case: Case) -> tuple[int, list[int], list[Any]]:
    """A find whose published rows disagree with the rows the step states."""
    case.when["scenario"][0]["expectRows"][0]["owner"] = "Someone else"
    return 0, [], [_LINUS]


def _broken_identity(case: Case) -> tuple[int, list[int], list[Any]]:
    """Two finds declared to be one object, reaching two different accounts."""
    case.when["scenario"][1]["expectRows"] = [
        {"id": 3, "owner": "Linus", "balance": 10.00, "version": 1}
    ]
    return 1, [0], [_LINUS, [_account(3, "Linus", "10.00", 1)]]


def _identity_column_the_source_never_projected(case: Case) -> tuple[int, list[int], list[Any]]:
    """An identity claim graded on a column NEITHER find published.

    The rows that cannot answer it are the SOURCE step's, so this is the one
    identity route whose subject is a step other than the failing one.
    """
    case.when["scenario"][1]["identityAttr"] = "account_number"
    return 1, [0], [_LINUS, _LINUS]


def _drifting_page(case: Case) -> tuple[int, list[int], list[Any]]:
    """A continuing page of a streamed step seeking a different way."""
    sql = case.when["scenario"][0]["statements"][1]["sql"]
    for dialect, text in sql.items():
        sql[dialect] = text.replace("t0.id > ?", "t0.id >= ?")
    return 0, [], list(_DELIVERY)


def _an_extra_page(case: Case) -> tuple[int, list[int], list[Any]]:
    """A statement after the short page that ended the delivery."""
    statements = case.when["scenario"][0]["statements"]
    statements.append(copy.deepcopy(statements[-1]))
    return 0, [], list(_DELIVERY)


def _a_level_the_query_declares_no_include_for(case: Case) -> tuple[int, list[int], list[Any]]:
    """A second golden statement on a step whose Object Query has no Include Paths."""
    statements = case.when["scenario"][0]["statements"]
    statements.append(copy.deepcopy(statements[0]))
    return 0, [], [_LINUS]


def _an_access_over_a_relationship_the_read_never_included(
    case: Case,
) -> tuple[int, list[int], list[Any]]:
    """An access navigating a hop the source read did not materialize."""
    case.when["scenario"][2]["path"] = "statuses"
    return 2, [0], [_ORDER_ONE, _ORDER_ONE_ITEMS]


@pytest.mark.parametrize(
    ("case_name", "damage"),
    [
        (_ONE_OBJECT_TWO_FINDS, _wrong_rows),
        (_ONE_OBJECT_TWO_FINDS, _broken_identity),
        (_ONE_OBJECT_TWO_FINDS, _identity_column_the_source_never_projected),
        (_ONE_OBJECT_TWO_FINDS, _a_level_the_query_declares_no_include_for),
        (_STREAMED_EVIDENCE, _drifting_page),
        (_STREAMED_EVIDENCE, _an_extra_page),
        (_EDIT_KEEPS_ITEMS, _an_access_over_a_relationship_the_read_never_included),
    ],
    ids=[
        "rows",
        "identity",
        "identity source",
        "unused level",
        "page drift",
        "trailing page",
        "access",
    ],
)
def test_every_step_failure_names_the_case_file_and_the_step(
    damaged_case: CaseLoader,
    case_name: str,
    damage: Callable[[Case], tuple[int, list[int], list[Any]]],
) -> None:
    case = damaged_case(case_name)
    failing, prior, results = damage(case)
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=results)
    for index in prior:
        reads.assert_step(index, reader)

    with pytest.raises(CaseFailure) as raised:
        reads.assert_step(failing, reader)

    assert str(raised.value).startswith(f"{case.path.name}: scenario[{failing}]")


@pytest.mark.parametrize(
    "raised",
    [
        "the storage layout resolves no position for the effective concrete set",
        "m-identity-map-001-same-transaction-identity.yaml: the Continuation Order names "
        "a member this read resolves to no single Structured Column",
    ],
    ids=["names neither", "names the case only"],
)
def test_a_subordinate_refusal_is_reported_against_the_step_that_reached_it(
    corpus_case: CaseLoader, monkeypatch: pytest.MonkeyPatch, raised: str
) -> None:
    """The step boundary is unconditional, so no route has to be remembered.

    Every oracle a step reaches — delivery, seek derivation, materialization,
    Include levels, graph assembly — speaks of the READ it was handed rather than
    the Scenario position that handed it over, so a refusal from any of them
    arrives naming at most the case. Standing in for all of them is a refusal
    raised from the statement execution every SQL-issuing workflow shares.
    """
    case = corpus_case(_ONE_OBJECT_TWO_FINDS)

    def refuse(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise CaseFailure(raised)

    monkeypatch.setattr(oracle_execute, "query_rows", refuse)
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure) as caught:
        reads.assert_step(0, ScriptedReads())

    detail = raised.removeprefix(f"{case.path.name}: ")
    assert str(caught.value) == f"{case.path.name}: scenario[0] {detail}"


def test_a_driver_exception_from_a_step_is_not_reported_as_a_mismatch(
    corpus_case: CaseLoader,
) -> None:
    failure = _DriverError("server closed the connection unexpectedly")
    reads = ScenarioReads(corpus_case(_ONE_OBJECT_TWO_FINDS))

    with pytest.raises(_DriverError) as raised:
        reads.assert_step(0, ScriptedReads(results=[failure]))

    assert raised.value is failure
