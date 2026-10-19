from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, cast

from parallax.conformance import case_format
from parallax.conformance.another_source import AnotherSource
from parallax.conformance.story_models import Account
from parallax.core.entity import Entity
from parallax.core.execution import KeyedWriteValueError
from parallax.core.unit_work import WriteEvidenceError
from parallax.snapshot import ReadOnlyTxnContext, ScopedDatabase, TxnContext, WireEntity

__all__ = [
    "TARGET_ID",
    "UNMANAGED_ID",
    "OutsideReads",
    "WriteValueStep",
    "declared_database_calls",
    "grade_step",
    "graded_outcomes",
    "reachable_write_value_cases",
    "read_outside_the_attempt",
    "value_of",
    "write_value_steps",
]

# The keyed write verbs a case can name. Every other action verb belongs to a
# lane this runner does not drive.
_WRITE_VALUE_ACTIONS: Final[frozenset[str]] = frozenset({"insert", "amend"})

# The fixture row every reachable write-value case reads through: every one
# targets `models/account.yaml` (fixtures: id 2, Linus, balance 250.00,
# version 1), the same row the boundary runner drives.
TARGET_ID: Final[int] = 2

# Outside the fixture range, so a value no managed read produced cannot be
# mistaken for one that was.
UNMANAGED_ID: Final[int] = 91


@dataclass(frozen=True, slots=True)
class WriteValueStep:
    """One keyed write action step: the verb, its value's stated provenance, the
    read outside the writing attempt that published it — ``None`` where the
    writing attempt read it — and the refusal the case declares — ``None`` where
    the case declares the value accepted."""

    action: str
    provenance: str
    expect_error: str | None
    source_read: str | None = None


type OutsideReads = dict[int, tuple[Entity, WireEntity]]
"""The Typed value and Wire node each ``sourceRead`` step is handed, by step
index."""


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
            source_read=cast("str | None", step.get("sourceRead")),
        )
        for step in _scenario_steps(case)
    ]


def read_outside_the_attempt(db: ScopedDatabase, steps: Sequence[WriteValueStep]) -> OutsideReads:
    """Arrange, before the writing transaction opens, the value each step stating
    ``sourceRead`` is handed (`m-case-format` *Keyed write action steps*).

    Each read runs where its token says — standalone, in a read-only
    transaction, or in an earlier writable transaction that commits without
    writing — through the source the verb writes through, once per
    representation, so the step is graded through the Typed and the Wire verb
    alike.
    """
    arranged: OutsideReads = {}
    for index, step in enumerate(steps):
        if step.source_read == "standalone":
            arranged[index] = _both(db)
        elif step.source_read == "readOnlyTransaction":
            arranged[index] = db.read_only(_both)
        elif step.source_read == "earlierAttempt":
            arranged[index] = db.transact(_both)
        elif step.source_read is not None:
            raise ValueError(f"unrecognized source read {step.source_read!r}")
    return arranged


def _both(reader: ScopedDatabase | ReadOnlyTxnContext | TxnContext) -> tuple[Entity, WireEntity]:
    typed = reader.find(Account.where(Account.id == TARGET_ID)).result()
    wire = reader.wire.find(Account.where(Account.id == TARGET_ID)).result()
    return typed, wire


def declared_database_calls(case: case_format.Case) -> int:
    """The statements the case declares it costs, from its own oracle.

    A scenario's `then.databaseCalls` is the SUM of its steps' own counts
    (`m-case-format`), so the two are read together and a case whose total
    disagrees with its steps is loud here — the compatibility harness executes no
    `api-conformance` case, so this is where that consistency is checked at all.
    An absent total is that sum, which is what the steps already declare.

    The count is the statements the steps' own verbs cost. Reads that arrange a
    value of the stated provenance are the adapter's own affair and are not the
    case's cost.
    """
    steps = _scenario_steps(case)
    total = sum(cast("int", step["databaseCalls"]) for step in steps)
    then = cast("dict[str, Any]", case.document.get("then") or {})
    declared = cast("int", then.get("databaseCalls", total))
    if declared != total:
        raise ValueError(
            f"{case.case_id}: then.databaseCalls is {declared} but its steps declare {total} "
            "between them; a scenario's total is the sum of its steps' own counts"
        )
    return total


def value_of(
    provenance: str,
    tx: TxnContext,
    another: AnotherSource,
    invalid_root: Callable[[], Entity] | None = None,
) -> Entity:
    """A value of the stated provenance, arranged through the source that
    produces it (`m-case-format` *Keyed write action steps*).

    ``unmanaged`` is a plainly constructed instance — the one token no managed
    read produced. ``thisSource`` is read through ``tx`` itself, the very source
    the verb under test writes through. ``anotherSource`` is read through
    ``another``, a second framework-managed source with its own materialization
    and its own lifecycle state
    (:mod:`~parallax.conformance.another_source`), because the Snapshot runtime
    is one source and no read of it produces a foreign value (ADR 0010).
    ``invalidRoot`` is supplied by the conformance adapter after it performs a
    checked read that exposes hydratable diagnostic data; the runner consumes the
    resulting value but does not prescribe how the adapter staged invalid storage.

    Nothing here decides what any of it means: the production validator does.
    """
    if provenance == "unmanaged":
        return Account(id=UNMANAGED_ID, owner="Unmanaged", balance=Decimal("0.00"))
    if provenance == "thisSource":
        return tx.find(Account.where(Account.id == TARGET_ID)).result()
    if provenance == "anotherSource":
        (value,) = another.find(Account.where(Account.id == TARGET_ID))
        return value
    if provenance == "invalidRoot":
        if invalid_root is None:
            raise ValueError("invalidRoot provenance requires a diagnostic-data arranger")
        return invalid_root()
    raise ValueError(f"unrecognized value provenance {provenance!r}")


def grade_step(
    tx: TxnContext,
    step: WriteValueStep,
    another: AnotherSource,
    invalid_root: Callable[[], Entity] | None = None,
    outside: tuple[Entity, WireEntity] | None = None,
) -> str | None:
    """Drive ``step``'s verb over a value of its stated provenance and grade what
    the verb answered.

    A step stating ``sourceRead`` is handed ``outside``, the values a read
    outside this attempt published, and its verb is driven through the Typed and
    the Wire ingress in turn: both must answer what the case declares.

    Returns the raised refusal's code when the step declared it, and ``None`` for
    an accepted value. A mismatch in either direction — an undeclared refusal, or
    a declared expectation the verb never raised — is loud, never a silently
    dropped observation.
    """
    if step.source_read is not None:
        if outside is None:
            raise ValueError(f"a {step.source_read!r} step needs its outside read arranged")
        typed, wire = outside
        _graded(step, lambda: _apply(tx, step.action, typed))
        return _graded(step, lambda: tx.wire.amend(wire, {}))
    value = value_of(step.provenance, tx, another, invalid_root)
    return _graded(step, lambda: _apply(tx, step.action, value))


def _graded(step: WriteValueStep, verb: Callable[[], object]) -> str | None:
    try:
        verb()
    except (KeyedWriteValueError, WriteEvidenceError) as refusal:
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


def _apply(tx: TxnContext, action: str, value: Entity) -> None:
    if action == "insert":
        tx.insert(value)
    else:
        tx.amend(value)


def graded_outcomes(
    tx: TxnContext,
    steps: Sequence[WriteValueStep],
    another: AnotherSource,
    invalid_root: Callable[[], Entity] | None = None,
    outside: OutsideReads | None = None,
) -> list[str | None]:
    """Every step's graded outcome, in authored order — the observation a case
    run reports. ``outside`` is what :func:`read_outside_the_attempt` arranged
    for the same steps before this transaction opened."""
    arranged = outside or {}
    return [
        grade_step(tx, step, another, invalid_root, arranged.get(index))
        for index, step in enumerate(steps)
    ]
