"""The error lane: an `error`-shape case's authored single-connection trigger
run verbatim at the port, and the raised failure's classification reported.

The trigger IS the case's ``then.statements`` — ordered DML whose final
statement raises — so there is no neutral instruction to translate and no
Handle to build: the lane executes at the port it is handed, opens no
Execution Activity, and reports the emissions it issued, the neutral category
and native code of the classified failure, and a round-trip count that is the
trigger's own length. A two-session ``when.concurrency`` trigger is refused
here unconditionally; the case-driven rounds runner grades it. Grading the
classification against ``then`` is the adapter's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.conformance import case_format
from parallax.conformance._mechanism import envelope
from parallax.conformance._mechanism.envelope import Emission, EngineError
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DatabaseConnection
from parallax.core.sql_gen import LoweredStatement

__all__ = ["run_error_case"]


def _error_trigger(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, tuple[object, ...]]]:
    """The authored single-connection trigger DML (`then.statements`) for ``dialect``."""
    then_raw = case.document.get("then")
    then: Mapping[str, object] = (
        cast("Mapping[str, object]", then_raw) if isinstance(then_raw, Mapping) else {}
    )
    raw = then.get("statements")
    if not isinstance(raw, list) or not raw:
        raise EngineError(f"{case.path.name}: error case has no `then.statements` trigger")
    trigger: list[tuple[str, tuple[object, ...]]] = []
    for entry in cast("list[Mapping[str, object]]", raw):
        sql = entry["sql"]
        text = cast("Mapping[str, str]", sql)[dialect_name] if isinstance(sql, Mapping) else sql
        binds = entry.get("binds", [])
        trigger.append((cast("str", text), tuple(cast("list[object]", binds))))
    return trigger


def run_error_case(
    case: case_format.Case, port: DatabaseConnection
) -> tuple[list[Emission], str, str | int, int]:
    """Run an error-shape case and report the raised failure's classification.

    The single-connection trigger IS the authored ``then.statements`` — ordered
    DML whose final statement raises (m-case-format); there is no neutral
    instruction to translate, so executing it verbatim is the case contract, not
    golden reverse-engineering. Every statement before the last must succeed;
    the last must raise a classified :class:`DatabaseError`, whose neutral
    category and preserved native code are the observations
    (``errorClass`` / ``nativeCode``). The trigger runs at the PORT rather than
    through a Handle — it is authored DML, not a write a verb buffers — so it
    opens no Execution Activity and its round trips are stated rather than
    observed: the lane reaches the final statement only by having issued every
    one before it, so the count is the trigger's own length. Every statement it
    issues counts, the failing one included, so what it reports is what reached
    the database rather than what it meant to emit. A
    ``when.concurrency`` trigger needs
    two barrier-synchronized sessions this single-connection lane cannot drive
    at all — it is refused here UNCONDITIONALLY, never dispatched to from a
    caller that owns two sessions (
    ``m-read-lock-006`` is graded by the CASE-DRIVEN two-session rounds
    runner instead, ``parallax.conformance.concurrency_runner`` — this
    module's own dispatcher (`tests/compatibility/test_run_sweep.py`) routes it
    there and never reaches this function for that case at all; the
    provider-contract deadlock proof remains the OTHER two-session witness,
    hand-authored rather than case-driven). The ``m-db-error`` two-connection
    choreography (deadlock / lock-wait) stays covered by the provider-contract
    proof alone this increment (see the module's own extensibility note).
    """
    when = case.document.get("when")
    if isinstance(when, Mapping) and "concurrency" in when:
        raise EngineError(
            f"{case.path.name}: two-connection when.concurrency choreography needs two "
            "barrier-synchronized sessions this single-connection lane cannot drive — "
            "the case-driven rounds runner (parallax.conformance.concurrency_runner) or "
            "the provider contract proof grades it instead, never this function"
        )
    dialect = port.dialect
    trigger = _error_trigger(case, dialect.name)
    emissions: list[Emission] = []
    final = len(trigger) - 1
    for index, (sql, binds) in enumerate(trigger):
        emissions.append(Emission(f"/then/statements/{index}", LoweredStatement(sql, binds)))
        try:
            port.execute_write(dialect.to_driver_sql(sql), envelope.driver_binds(binds))
        except DatabaseError as exc:
            if index != final:
                raise EngineError(
                    f"{case.path.name}: trigger statement {index} raised before the final "
                    f"statement: {exc}"
                ) from exc
            if exc.category is None or exc.native_code is None:
                raise EngineError(
                    f"{case.path.name}: the trigger raised an unclassified database error: {exc}"
                ) from exc
            return emissions, exc.category, exc.native_code, len(trigger)
    raise EngineError(f"{case.path.name}: the final trigger statement did not raise")
