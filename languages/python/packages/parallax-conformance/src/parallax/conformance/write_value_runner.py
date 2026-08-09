"""``parallax.conformance.write_value_runner`` — the case-driven write-value runner.

A keyed write action step (`m-case-format` *Keyed write action steps*) hands a
keyed write verb a **value** whose provenance the case states, and observes which
verbs accept it (`m-unit-work` *Write value provenance*). What such a step
observes is a property of a live client-held value rather than of any statement,
which is why it is `lane: api-conformance` and why the compile/run lanes classify
it out: the engine's snapshot lane assembles neutral row-shaped nodes and drives
the neutral buffer seam, so it holds no value to hand a verb at all. This module
hosts the machinery ONE parametrized runner drives against EVERY reachable
write-value case, exactly as :mod:`~parallax.conformance.boundary_runner` does
for the loop-mechanics branches.

- :func:`write_value_steps` parses a case's own steps into the verb, the stated
  provenance, and the declared `expectError`.
- :func:`value_of` is the ONE provenance -> value mapping every case shares. It
  arranges a value of the stated provenance rather than being told how: the
  spec fixes which sources a value can come from, never how an implementation
  retains that fact.
- :func:`grade_step` drives the REAL developer verb and compares what it raised
  against what the step declared, in the loud-mismatch discipline the engine's
  own `mutate` grading uses — an undeclared refusal and a declared expectation
  the verb never raised are both failures, never silently dropped observations.
- :func:`declared_round_trips` is the case's own round-trip oracle, which this
  suite is the only place to grade: the compatibility harness never executes an
  `api-conformance` case, so nothing else reads it.

Every function here drives the live :class:`~parallax.snapshot.handle.Transaction`
and the second source (:class:`~parallax.conformance.another_source.AnotherSource`)
it is handed, and opens no connection of its own, so the same runner grades a case
against a real database and against a fake port alike.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, cast

from parallax.conformance import case_format
from parallax.conformance.another_source import AnotherSource
from parallax.conformance.story_models import Account
from parallax.snapshot.handle import KeyedWriteValueError, Transaction

__all__ = [
    "TARGET_ID",
    "UNMANAGED_ID",
    "WriteValueStep",
    "declared_round_trips",
    "grade_step",
    "graded_outcomes",
    "reachable_write_value_cases",
    "value_of",
    "write_value_steps",
]

# The keyed write verbs a case can name. Every other action verb belongs to a
# lane this runner does not drive.
_WRITE_VALUE_ACTIONS: Final[frozenset[str]] = frozenset({"insert", "update"})

# The fixture row every reachable write-value case reads through: every one
# targets `models/account.yaml` (fixtures: id 2, Linus, balance 250.00,
# version 1), the same row the boundary runner drives.
TARGET_ID: Final[int] = 2

# Outside the fixture range, so a value no managed read produced cannot be
# mistaken for one that was.
UNMANAGED_ID: Final[int] = 91


@dataclass(frozen=True, slots=True)
class WriteValueStep:
    """One keyed write action step: the verb, its value's stated provenance, and
    the refusal the case declares — ``None`` where the case declares the value
    accepted."""

    action: str
    provenance: str
    expect_error: str | None


def reachable_write_value_cases(
    cases: list[case_format.Case] | None = None,
) -> list[case_format.Case]:
    """Every corpus case carrying keyed write action steps (parametrized at
    runtime, never a hand list).

    Selection is by what a case CONTAINS rather than by what it is made of, so a
    keyed write action step cannot leave the graded set by acquiring a neighbour:
    a case mixing one with a step this runner does not drive is loud here rather
    than silently unreachable.
    """
    corpus = cases if cases is not None else case_format.load_cases()
    return [case for case in corpus if case.shape == "scenario" and _is_write_value_case(case)]


def _is_write_value_case(case: case_format.Case) -> bool:
    """Whether this runner grades ``case``, raising where nothing could.

    A scenario carrying a keyed write action step carries only keyed write action
    steps, and the case schema requires it (`m-case-format` *Keyed write action
    steps*): the case is `api-conformance` throughout, so this suite is the only
    executor of every step in it, and a neighbour this runner cannot drive would
    leave the case gradeable neither whole — nothing here runs a `find` — nor in
    part, since a partial grade would report a pass for steps no executor ran.
    The raise backstops that rule for a document the schema never admitted, so a
    keyed write step cannot leave the graded set silently by acquiring a
    neighbour.
    """
    steps = _scenario_steps(case)
    keyed = [step for step in steps if step.get("action") in _WRITE_VALUE_ACTIONS]
    if not keyed:
        return False
    if len(keyed) != len(steps):
        raise ValueError(
            f"{case.case_id}: a keyed write action step shares this scenario with a step no "
            "keyed-write-value runner drives; the case is api-conformance throughout, so no "
            "other executor grades the rest and it can be graded neither whole nor in part"
        )
    return True


def _scenario_steps(case: case_format.Case) -> list[dict[str, Any]]:
    """The case's own `when.scenario` steps, read the way every other case-driven
    runner reads its own block: the schema already fixed the shape."""
    when = cast("dict[str, Any]", case.document.get("when") or {})
    return cast("list[dict[str, Any]]", when.get("scenario") or [])


def write_value_steps(case: case_format.Case) -> list[WriteValueStep]:
    """The case's own ordered steps, in the runner's shape.

    Reads EVERY step of the scenario, which is sound for exactly the cases
    :func:`reachable_write_value_cases` selects: a selected case has already been
    established to carry keyed write action steps and nothing else. A scenario
    mixing one with a step this runner cannot drive never reaches here — it is
    refused at selection rather than partly parsed here, because grading such a
    case in part would report a pass for steps that never ran.
    """
    return [
        WriteValueStep(
            action=cast("str", step["action"]),
            provenance=cast("str", step["value"]),
            expect_error=cast("str | None", step.get("expectError")),
        )
        for step in _scenario_steps(case)
    ]


def declared_round_trips(case: case_format.Case) -> int:
    """The statements the case declares it costs, from its own oracle.

    A scenario's `then.roundTrips` is the SUM of its steps' own counts
    (`m-case-format`), so the two are read together and a case whose total
    disagrees with its steps is loud here — the compatibility harness executes no
    `api-conformance` case, so this is where that consistency is checked at all.
    An absent total is that sum, which is what the steps already declare.

    The count is the statements the steps' own verbs cost. Reads that arrange a
    value of the stated provenance are the adapter's own affair and are not the
    case's cost.
    """
    steps = _scenario_steps(case)
    total = sum(cast("int", step["roundTrips"]) for step in steps)
    then = cast("dict[str, Any]", case.document.get("then") or {})
    declared = cast("int", then.get("roundTrips", total))
    if declared != total:
        raise ValueError(
            f"{case.case_id}: then.roundTrips is {declared} but its steps declare {total} "
            "between them; a scenario's total is the sum of its steps' own counts"
        )
    return total


def value_of(provenance: str, tx: Transaction, another: AnotherSource) -> Account:
    """A value of the stated provenance, arranged through the source that
    produces it (`m-case-format` *Keyed write action steps*).

    ``unmanaged`` is a plainly constructed instance — the one token no managed
    read produced. ``thisSource`` is read through ``tx`` itself, the very source
    the verb under test writes through. ``anotherSource`` is read through
    ``another``, a second framework-managed source with its own materialization
    and its own lifecycle state
    (:mod:`~parallax.conformance.another_source`), because the Snapshot runtime
    is one source and no read of it produces a foreign value (ADR 0010).

    Nothing here decides what any of it means: the production validator does.
    """
    if provenance == "unmanaged":
        return Account(id=UNMANAGED_ID, owner="Unmanaged", balance=Decimal("0.00"))
    if provenance == "thisSource":
        return tx.find(Account.where(Account.id == TARGET_ID)).result()
    if provenance == "anotherSource":
        (value,) = another.find(Account.where(Account.id == TARGET_ID))
        return value
    raise ValueError(f"unrecognized value provenance {provenance!r}")


def grade_step(tx: Transaction, step: WriteValueStep, another: AnotherSource) -> str | None:
    """Drive ``step``'s verb over a value of its stated provenance and grade what
    the verb answered.

    Returns the raised refusal's code when the step declared it, and ``None`` for
    an accepted value. A mismatch in either direction — an undeclared refusal, or
    a declared expectation the verb never raised — is loud, never a silently
    dropped observation.
    """
    value = value_of(step.provenance, tx, another)
    try:
        _apply(tx, step.action, value)
    except KeyedWriteValueError as refusal:
        if step.expect_error != refusal.code:
            declared = (
                f"expectError {step.expect_error!r}"
                if step.expect_error is not None
                else "no expectError"
            )
            raise AssertionError(
                f"the {step.action!r} verb raised {refusal.code!r} but the step declares {declared}"
            ) from refusal
        return refusal.code
    if step.expect_error is not None:
        raise AssertionError(
            f"the step declares expectError {step.expect_error!r} but the {step.action!r} "
            "verb accepted the value"
        )
    return None


def _apply(tx: Transaction, action: str, value: Account) -> None:
    if action == "insert":
        tx.insert(value)
    else:
        tx.update(value)


def graded_outcomes(
    tx: Transaction, steps: Sequence[WriteValueStep], another: AnotherSource
) -> list[str | None]:
    """Every step's graded outcome, in authored order — the observation a case
    run reports."""
    return [grade_step(tx, step, another) for step in steps]
