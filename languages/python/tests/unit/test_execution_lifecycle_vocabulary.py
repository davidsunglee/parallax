"""The five runtime classifications, and that the corpus keeps its own tokens
(m-execution-lifecycle, Docker-free).

Two vocabularies describe the same distinctions: the `Literal` members a Handler
receives and the built-in Logger writes, which are Python's own and spelled the
way `python.md` §2 spells such a value; and the tokens the core spec authors,
which the compatibility corpus is graded against. Neither is derived from the
other, so what is graded here is that BOTH are enumerated — the member sets
below, and a projection driven off those same sets rather than off a hand-written
list that a new member would quietly fall outside of.
"""

from __future__ import annotations

import re
from typing import Any, Final, cast, get_args
from uuid import uuid4

from parallax.conformance._lifecycle_observation import execution_lifecycle_observation
from parallax.core.execution_lifecycle import (
    AttemptFailure,
    AttemptPhase,
    AttemptRolledBack,
    DatabaseCallKind,
    DatabaseCallStarted,
    DirectFailure,
    ExecutionEvent,
    FailureDiagnostic,
    LifecycleLogDetail,
    ReadInterface,
    ReadStarted,
    RootExecution,
    RootExecutionKind,
    TransactionAttemptFinished,
)
from parallax.core.execution_lifecycle.testing import RecordedRoot
from parallax.core.sql_gen import LoweredStatement

_RUNTIME_SPELLING: Final = re.compile(r"[a-z]+(?:_[a-z]+)*\Z")

_FAMILIES: Final[dict[str, tuple[Any, tuple[str, ...]]]] = {
    "RootExecutionKind": (RootExecutionKind, ("read", "transaction_invocation", "snapshot_stream")),
    "ReadInterface": (ReadInterface, ("typed", "wire", "rows")),
    "DatabaseCallKind": (DatabaseCallKind, ("read", "write")),
    "AttemptPhase": (AttemptPhase, ("callback", "pre_commit", "commit")),
    "LifecycleLogDetail": (LifecycleLogDetail, ("safe", "diagnostic")),
}

_EXECUTION: Final = RootExecution(uuid4(), "read")
_STATEMENT: Final = LoweredStatement("select 1 from account", ())
_DIAGNOSTIC: Final = FailureDiagnostic(
    qualified_type="builtins.ValueError",
    message="boom",
    code=None,
    stack="",
    message_truncated=False,
    stack_truncated=False,
)


def _members(name: str) -> tuple[Any, ...]:
    """One family's declared members, read off the alias rather than restated.

    Typed as ``Any`` so each member can be handed back to the producer whose
    Literal it came from: the point of reading them at runtime is that a member
    added to the alias reaches every case below without being written down again.
    """
    return get_args(_FAMILIES[name][0].__value__)


def _projected(*roots: RecordedRoot) -> list[dict[str, Any]]:
    observation = execution_lifecycle_observation(list(roots), [])
    return cast("list[dict[str, Any]]", observation["roots"])


def _root(kind: str, *events: ExecutionEvent) -> RecordedRoot:
    return RecordedRoot(RootExecution(_EXECUTION.id, kind), tuple(events))  # pyright: ignore[reportArgumentType] - the kind is the caller's literal


def _transitions(*events: ExecutionEvent) -> list[dict[str, Any]]:
    (root,) = _projected(_root("read", *events))
    return cast("list[dict[str, Any]]", root["events"])


def test_every_family_declares_exactly_its_migrated_members() -> None:
    for name, (_, expected) in _FAMILIES.items():
        assert _members(name) == expected, name


def test_every_member_is_spelled_the_way_python_spells_a_runtime_value() -> None:
    for name in _FAMILIES:
        for member in _members(name):
            assert _RUNTIME_SPELLING.fullmatch(member), (name, member)


def test_the_projection_answers_every_root_kind_with_the_token_the_corpus_authors() -> None:
    roots = _projected(
        *(
            _root(kind, ReadStarted(_EXECUTION.id, 1, 1, None, "Account", "typed", "account"))
            for kind in _members("RootExecutionKind")
        )
    )
    assert [root["kind"] for root in roots] == ["read", "transaction-invocation", "snapshot-stream"]


def test_the_projection_answers_every_read_interface() -> None:
    events = _transitions(
        *(
            ReadStarted(_EXECUTION.id, index, index, None, "Account", interface, None)
            for index, interface in enumerate(_members("ReadInterface"), start=1)
        )
    )
    assert [event["readStarted"]["interface"] for event in events] == ["typed", "wire", "rows"]


def test_the_projection_answers_every_database_call_kind() -> None:
    events = _transitions(
        *(
            DatabaseCallStarted(_EXECUTION.id, index, index, None, "Account", kind, _STATEMENT)
            for index, kind in enumerate(_members("DatabaseCallKind"), start=1)
        )
    )
    assert [event["databaseCallStarted"]["kind"] for event in events] == ["read", "write"]


def test_the_projection_answers_every_attempt_phase() -> None:
    events = _transitions(
        *(
            TransactionAttemptFinished(
                _EXECUTION.id,
                index,
                index,
                None,
                AttemptRolledBack(
                    AttemptFailure(phase, DirectFailure(_DIAGNOSTIC), retry_eligible=False)
                ),
            )
            for index, phase in enumerate(_members("AttemptPhase"), start=1)
        )
    )
    assert [event["transactionAttemptFinished"]["phase"] for event in events] == [
        "callback",
        "pre-commit",
        "commit",
    ]
