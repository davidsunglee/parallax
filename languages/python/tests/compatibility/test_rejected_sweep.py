"""Docker-free rejected-case run sweep (m-conformance-adapter `run`, m-case-format
`rejected` cases).

A rejected case executes no SQL and touches no database (m-case-format "Rejected
cases"): grading its `run` envelope needs no provisioner, so — unlike
`test_run_sweep.py`, whose every test function threads the Testcontainers
`provisioner` fixture — this sweep runs entirely in-process. `when.objectQuery` /
`when.model` / `when.write` inputs are all exercised end-to-end (the
`when.write` half via `validate_write`): the classified
`rejectedRule` observation is compared against the case's own
`then.rejectedRule`, and a :class:`_RefusingPort` proves the "no database"
contract structurally, the same way the compile lane's refusing port proves
query-result-independence.

Pure, Docker-free, in-process behaviour, so it classifies `dbfree` and
contributes to the database-free branch-coverage gate even though the rest of
`tests/compatibility/` needs a database.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

import jsonschema
import pytest

from _support.corpus import case_document
from _support.repo import adapter_schema
from parallax.conformance import adapter, case_format, sweep
from parallax.conformance.profile import profile_for
from parallax.core.db_port import DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect

_SCHEMA = adapter_schema()
# The declared profile a rejected `run` is requested under, resolved out of the one
# roster. Nothing here provisions it: the refusing port below stands in for the
# container the shape never needs, and the envelope still names the profile the
# request was made against.
_PROFILE = profile_for("pg-full")
_REACHABLE_REJECTED = [c for c in sweep.reachable_cases() if c.shape == "rejected"]


class _RefusingPort:
    """An `m-db-port` that fails loudly if the rejected lane ever touches it."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        raise AssertionError("a rejected-case run must not open a transaction")


def _when_kind(case: case_format.Case) -> str:
    when = cast("dict[str, Any]", case_document(case).get("when") or {})
    for kind in ("objectQuery", "model", "write"):
        if kind in when:
            return kind
    raise AssertionError(
        f"{case.case_id}: rejected case carries none of objectQuery/model/write"
    )  # pragma: no cover


@pytest.mark.parametrize("case", _REACHABLE_REJECTED, ids=[c.case_id for c in _REACHABLE_REJECTED])
def test_rejected_sweep(case: case_format.Case) -> None:
    envelope = adapter.run_case(case.path, _PROFILE, _RefusingPort())
    jsonschema.validate(envelope, _SCHEMA)

    assert envelope["status"] == "ok", envelope
    assert envelope["emissions"] == []
    observations = envelope["observations"]
    assert observations["roundTrips"] == 0
    assert observations["rejectedRule"] == case_document(case)["then"]["rejectedRule"]


def test_reachable_rejected_population_is_non_empty() -> None:
    assert _REACHABLE_REJECTED, "the reachable intersection lost its rejected-shape cases"


def test_reachable_rejected_population_spans_every_when_kind() -> None:
    # `objectQuery` / `model` / `write` inputs are all exercised above. All three
    # kinds should be present in the reachable set so no dispatch arm silently
    # goes untested.
    kinds = {_when_kind(case) for case in _REACHABLE_REJECTED}
    assert kinds == {"objectQuery", "model", "write"}, kinds


def test_reachable_rejected_population_spans_every_write_form() -> None:
    # `when.write` is itself three-formed, dispatched on the members the input
    # carries: `target` is a predicate-selected instruction, `rows` a whole keyed
    # instruction, anything else the bare neutral write row. Each arm resolves its
    # target differently, so each needs a reachable witness of its own.
    forms: set[str] = set()
    for case in _REACHABLE_REJECTED:
        write = cast("dict[str, Any]", case_document(case).get("when") or {}).get("write")
        if not isinstance(write, dict):
            continue
        forms.add("predicate" if "target" in write else "keyed" if "rows" in write else "row")
    assert forms == {"predicate", "keyed", "row"}, forms
