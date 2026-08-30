"""What a failing read reports, and what it does not touch on the way there.

Two contracts meet here. An authored failure is a ``CaseFailure`` naming the case
file, so the person who wrote the case can find it. An infrastructure failure is
the driver's own exception, unwrapped, so a dead connection is never reported as a
semantic mismatch. And a failure knowable before execution costs no database work
at all, which is only observable as an empty call log.

A Scenario step's failure names its step as well, which is
:mod:`~reference_harness.unit_work_scenario`'s boundary to add and its own suite's
to grade.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.object_query_oracle import assert_case_read

from .conftest import ScriptedReads

CaseLoader = Callable[[str], Case]

_ORDER_BY_LIMIT = "m-object-query-001-order-by-limit.yaml"
_TPH_DOCUMENT_UNION = "m-inheritance-124-document-layout-tph-sibling-path-reuse.yaml"
_TPCS_TEMPORAL_UNION = "m-inheritance-093-tpcs-temporal-union-read.yaml"


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
