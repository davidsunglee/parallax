"""The conditional-write order, stated once and asserted of both representations.

Every ``_if`` verb, Typed or Wire, enters one ingress: lifecycle re-entry, then
the stated start, then the representation's own capture of what it addresses,
then the one preparation that judges the target, the verb, the window, the
revision, and only then the payload, and finally the buffering that drops an
amendment of nothing, refuses an object this attempt inserted, and under Locking
acquires the stored row at the call. What a row fixes is the ANSWER that order
gives — the refusal's class, code, message, the point it landed at, and the DML
emitted — beside the whole port chronology, so a refusal that read or flushed
anything, and an Optimistic write that read at the call, are different answers
rather than agreeing ones.

Each row states one expectation per representation that can express it and
asserts it of each in turn; nothing here compares one representation to the
other. A shape only one representation has a spelling for — a Typed mapping key,
or a Wire document no Typed call can state — is that representation's row alone.

Detailed revision rules, Wire document-shape diagnostics, Locking acquisition
reuse, temporal coverage and retry, and lifecycle re-entry stay with their
owners: core preparation's suite, the conditional and target-write suites, and
the execution-lifecycle re-entry suite.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import pytest

from parallax.core.base import InstantError
from parallax.core.unit_work import (
    WriteEvidenceError,
    WriteInstructionError,
    WritePreconditionError,
    WriteRejectedError,
)
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    PortCall,
    ReadCall,
    RollbackCall,
    WriteCall,
)
from tests.unit.snapshot._handle._write_order_drivers import (
    ACCOUNT_CONDITIONAL,
    BALANCE_CONDITIONAL,
    PERSON_CONDITIONAL,
    POSITION_CONDITIONAL,
    REPRESENTATIONS,
    UNDECLARED_CONDITIONAL,
    Answer,
    Phase,
    Representation,
    TargetWriteScenario,
    answered,
    outcome,
    reachable,
)

type _Chronology = tuple[type[PortCall], ...]


@dataclass(frozen=True, slots=True)
class _Expected:
    """One representation's answer and the kinds of every port call behind it."""

    answer: Answer
    calls: _Chronology


def _wrote(*between: type[PortCall], published: bool = False) -> _Expected:
    """An admitted write whose transaction ran ``between`` inside its boundary,
    after the standalone read a ``published`` value came from."""
    statements = sum(1 for call in between if call is WriteCall)
    ahead: _Chronology = (ReadCall,) if published else ()
    return _Expected(
        Answer(None, None, None, None, statements), (*ahead, BeginCall, *between, CommitCall)
    )


def _refused(
    error: type[Exception],
    message: str,
    *,
    code: str | None = None,
    phase: Phase = "verb",
    read: bool = False,
    published: bool = False,
) -> _Expected:
    """A refusal, by default one the VERB raised before the transaction asked
    the database for anything; ``read`` is the one read of the object it made
    first, and ``published`` the standalone read ahead of the transaction."""
    ahead: _Chronology = (ReadCall,) if published else ()
    inside: _Chronology = (ReadCall,) if read else ()
    return _Expected(
        Answer(error, code, message, phase, 0), (*ahead, BeginCall, *inside, RollbackCall)
    )


def _both(expected: _Expected) -> Mapping[Representation, _Expected]:
    return dict.fromkeys(REPRESENTATIONS, expected)


def _typed(expected: _Expected) -> Mapping[Representation, _Expected]:
    return {"typed": expected}


def _wire(expected: _Expected) -> Mapping[Representation, _Expected]:
    return {"wire": expected}


@dataclass(frozen=True, slots=True)
class _Row:
    scenario: TargetWriteScenario
    expected: Mapping[Representation, _Expected]

    def __str__(self) -> str:
        return str(self.scenario)


def _assert_row(row: _Row) -> None:
    """Assert every representation that can issue ``row``'s scenario answers
    with the expectation stated for it, and that one is stated for each."""
    scenario = row.scenario
    assert set(row.expected) == {
        representation for representation in REPRESENTATIONS if reachable(scenario, representation)
    }
    for representation, expected in row.expected.items():
        result = outcome(scenario, representation)
        observed = _Expected(answered(result), tuple(type(call) for call in result.calls))
        assert observed == expected, representation


_ACCOUNT, _BALANCE, _PERSON, _POSITION = (
    ACCOUNT_CONDITIONAL,
    BALANCE_CONDITIONAL,
    PERSON_CONDITIONAL,
    POSITION_CONDITIONAL,
)

_START_REFUSAL: Final = "valid_from=None states no start; omit valid_from rather than stating None"
_POSITION_REQUIRES_START: Final = (
    "WherePosition: a bitemporal 'amend' requires valid_from (the mutation's own Valid-Time "
    "instant)"
)
_NAIVE: Final = "a naive datetime is not a valid `timestamp`; attach a tzinfo"
_INSERTED: Final = (
    "write-evidence-inserted: parallax.compatibility.Account: this transaction inserted the "
    "object this write addresses, so no caller's revision describes it; until the transaction "
    "commits, write it through the value the insert took or a read of it"
)
_UNDECLARED_MODEL_TYPED: Final = "Account is not an Entity Class of this model"
_UNDECLARED_MODEL_WIRE: Final = (
    "the connected model declares no entity 'parallax.compatibility.Account' for this write"
)


def _no_valid_time(entity: str, profile: str, verb: str, keyword: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"{entity}: a {profile} '{verb}' takes no {keyword} ('{entity}' declares no Valid-Time "
        "dimension to bound)",
    )


def _bounded_pair(verb: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"WherePosition: a bounded '{verb}' states its window as a pair, and until is absent "
        "— an unbounded write omits until rather than stating none",
    )


def _temporal_delete(entity: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"Temporal objects like {entity!r} do not support 'delete_if', which physically "
        "removes rows. Use 'terminate_if' instead.",
    )


def _requires_version(entity: str, verb: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"{entity}: '{verb}' requires version, the version of the state the write starts from "
        "as its caller last observed it",
    )


def _requires_tx_start(entity: str, verb: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"{entity}: '{verb}' requires tx_start, the Transaction-Time start of the milestone the "
        "write starts from as its caller last observed it",
    )


def _version_not_tx_start(verb: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"Account: '{verb}' takes version, not tx_start — 'Account' is versioned, so its "
        "revision is its version",
    )


def _tx_start_not_version(entity: str, verb: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"{entity}: '{verb}' takes tx_start, not version — '{entity}' is temporal, so its "
        "revision is its milestone's Transaction-Time start",
    )


def _undeclared(entity: str) -> Mapping[Representation, _Expected]:
    """Each representation's own refusal of an undeclared member: a Typed
    assignment's reference, and a Wire row member."""
    return {
        "typed": _refused(
            WriteInstructionError,
            f"{entity}: assignment 'parallax.compatibility.{entity}.nickname' does not name a "
            f"member parallax.compatibility.{entity} declares or inherits",
        ),
        "wire": _undeclared_member(entity),
    }


def _undeclared_member(entity: str) -> _Expected:
    return _refused(
        WriteInstructionError, f"{entity}: target write row names undeclared member(s) ['nickname']"
    )


def _key_alone(entity: str, verb: str, member: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"{entity}: a caller-addressed '{verb}' names its object by its primary key alone, and "
        f"this row also states ['{member}']",
    )


def _not_scalar(verb_key: str = "dict") -> _Expected:
    return _refused(
        WriteInstructionError,
        f"Account: key is the object's one scalar primary-key value, and a {verb_key} is no "
        "such value",
    )


# --------------------------------------------------------------------------- #
# An admitted write reaches the buffering its target and strategy route it    #
# to: an Optimistic Non-Temporal write reads nothing and gates at the flush, a #
# Locking one acquires its row at the call, and an Optimistic temporal one     #
# reads its coverage at the flush — through every public input form.          #
# --------------------------------------------------------------------------- #
_GATED: Final = _wrote(WriteCall)
_ACQUIRED: Final = _wrote(ReadCall, WriteCall)
_SUCCESSOR: Final = _wrote(ReadCall, WriteCall, WriteCall)

_ADMITTED: Final[tuple[_Row, ...]] = (
    _Row(TargetWriteScenario(_ACCOUNT, "amend"), _both(_GATED)),
    _Row(TargetWriteScenario(_ACCOUNT, "amend", concurrency="locking"), _both(_ACQUIRED)),
    _Row(TargetWriteScenario(_ACCOUNT, "replace"), _both(_GATED)),
    _Row(TargetWriteScenario(_ACCOUNT, "replace", concurrency="locking"), _both(_ACQUIRED)),
    # A value a standalone read published is a replacement's state, and neither
    # its evidence nor its provenance is asked: nothing more is read for it.
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", address="published"),
        _both(_wrote(WriteCall, published=True)),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", address="published", concurrency="locking"),
        _both(_wrote(ReadCall, WriteCall, published=True)),
    ),
    _Row(TargetWriteScenario(_ACCOUNT, "delete"), _both(_GATED)),
    _Row(TargetWriteScenario(_ACCOUNT, "delete", concurrency="locking"), _both(_ACQUIRED)),
    _Row(TargetWriteScenario(_BALANCE, "amend"), _both(_SUCCESSOR)),
    _Row(TargetWriteScenario(_BALANCE, "amend", concurrency="locking"), _both(_SUCCESSOR)),
    _Row(TargetWriteScenario(_BALANCE, "replace"), _both(_SUCCESSOR)),
    _Row(TargetWriteScenario(_BALANCE, "terminate"), _both(_ACQUIRED)),
    _Row(TargetWriteScenario(_BALANCE, "terminate", concurrency="locking"), _both(_ACQUIRED)),
    _Row(TargetWriteScenario(_POSITION, "amend", valid_from="stated"), _both(_SUCCESSOR)),
    _Row(
        TargetWriteScenario(_POSITION, "amend", valid_from="stated", until="stated"),
        _both(_SUCCESSOR),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", valid_from="stated", concurrency="locking"),
        _both(_SUCCESSOR),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "replace", valid_from="stated", until="stated"),
        _both(_SUCCESSOR),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION, "replace", valid_from="stated", until="stated", concurrency="locking"
        ),
        _both(_SUCCESSOR),
    ),
    # The published state equals the stored state, so the start keeps its
    # milestone under a guard and no successor opens.
    _Row(
        TargetWriteScenario(_POSITION, "replace", valid_from="stated", address="published"),
        _both(_wrote(ReadCall, WriteCall, published=True)),
    ),
    _Row(TargetWriteScenario(_POSITION, "terminate", valid_from="stated"), _both(_SUCCESSOR)),
    _Row(
        TargetWriteScenario(
            _POSITION, "terminate", valid_from="stated", until="stated", concurrency="locking"
        ),
        _both(_SUCCESSOR),
    ),
)


@pytest.mark.parametrize("row", _ADMITTED, ids=str)
def test_an_admitted_conditional_write_is_buffered_as_its_target_routes_it(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# A pending write stays pending: an Optimistic call buffers beside it, a      #
# Locking call acquires its row at the call without flushing it, and the       #
# commit flushes both in order.                                               #
# --------------------------------------------------------------------------- #
_PENDING_ADMITTED: Final[tuple[_Row, ...]] = (
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", pending="unrelated"),
        _both(_wrote(WriteCall, WriteCall)),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", pending="unrelated", concurrency="locking"),
        _both(_wrote(ReadCall, WriteCall, WriteCall)),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", valid_from="stated", pending="unrelated"),
        _both(_wrote(WriteCall, ReadCall, WriteCall, WriteCall)),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION, "amend", valid_from="stated", pending="unrelated", concurrency="locking"
        ),
        _both(_wrote(ReadCall, WriteCall, WriteCall, WriteCall)),
    ),
)


@pytest.mark.parametrize("row", _PENDING_ADMITTED, ids=str)
def test_a_conditional_write_leaves_earlier_pending_work_to_the_commit(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# An amendment of nothing is judged — target, window, and revision — and then #
# dropped before admission: no acquisition, no claim, no insertion refusal,   #
# and no comparison against the stored revision.                              #
# --------------------------------------------------------------------------- #
_NOTHING: Final = _wrote()

_EMPTY_AMENDMENT: Final[tuple[_Row, ...]] = (
    _Row(TargetWriteScenario(_ACCOUNT, "amend", payload="empty"), _both(_NOTHING)),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", payload="empty", concurrency="locking"),
        _both(_NOTHING),
    ),
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", payload="empty", revision="stale", concurrency="locking"
        ),
        _both(_NOTHING),
    ),
    _Row(TargetWriteScenario(_BALANCE, "amend", payload="empty"), _both(_NOTHING)),
    _Row(
        TargetWriteScenario(_BALANCE, "amend", payload="empty", concurrency="locking"),
        _both(_NOTHING),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", payload="empty", valid_from="stated"),
        _both(_NOTHING),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION, "amend", payload="empty", valid_from="stated", concurrency="locking"
        ),
        _both(_NOTHING),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", payload="empty", pending="addressed"),
        _both(_wrote(WriteCall)),
    ),
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", payload="empty", pending="unrelated", concurrency="locking"
        ),
        _both(_wrote(WriteCall)),
    ),
    # Judged before it is dropped: the window, then the revision.
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", payload="empty", until="stated"),
        _both(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", payload="empty", until="none"),
        _both(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", payload="empty", revision="omitted"),
        _both(_requires_version("Account", "amend")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", payload="empty", revision="misstated"),
        _both(_version_not_tx_start("amend")),
    ),
    _Row(
        TargetWriteScenario(
            _BALANCE, "amend", payload="empty", until="stated", concurrency="locking"
        ),
        _both(_no_valid_time("Balance", "Transaction-Time-Only", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(
            _BALANCE, "amend", payload="empty", valid_from="stated", concurrency="locking"
        ),
        _both(_no_valid_time("Balance", "Transaction-Time-Only", "amend", "valid_from")),
    ),
    _Row(
        TargetWriteScenario(
            _BALANCE, "amend", payload="empty", revision="misstated", concurrency="locking"
        ),
        _both(_tx_start_not_version("Balance", "amend")),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", payload="empty", concurrency="locking"),
        _both(_refused(WriteInstructionError, _POSITION_REQUIRES_START)),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION,
            "amend",
            payload="empty",
            valid_from="stated",
            until="none",
            concurrency="locking",
        ),
        _both(_bounded_pair("amendUntil")),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION,
            "amend",
            payload="empty",
            valid_from="stated",
            revision="omitted",
            concurrency="locking",
        ),
        _both(_requires_tx_start("WherePosition", "amend")),
    ),
)


@pytest.mark.parametrize("row", _EMPTY_AMENDMENT, ids=str)
def test_an_amendment_of_nothing_is_judged_then_dropped_before_admission(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# The stated start is judged first: a stated `valid_from=None` is refused      #
# ahead of every fault the address, the target, the revision, or the payload  #
# carries.                                                                     #
# --------------------------------------------------------------------------- #
_STATED_NONE_START: Final[tuple[_Row, ...]] = (
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", valid_from="none", revision="omitted", payload="undeclared"
        ),
        _both(_refused(WriteInstructionError, _START_REFUSAL)),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", valid_from="none", address="unaddressable"),
        _both(_refused(WriteInstructionError, _START_REFUSAL)),
    ),
    _Row(
        TargetWriteScenario(UNDECLARED_CONDITIONAL, "replace", valid_from="none"),
        _both(_refused(WriteInstructionError, _START_REFUSAL)),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "terminate", valid_from="none", revision="omitted"),
        _both(_refused(WriteInstructionError, _START_REFUSAL)),
    ),
)


@pytest.mark.parametrize("row", _STATED_NONE_START, ids=str)
def test_a_stated_none_start_is_refused_before_anything_else_is_judged(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# What each representation captures ahead of preparation keeps its earlier   #
# place: an address that names no Entity, a Typed class of another model, a   #
# Wire document that is no mapping, a published node beside data or handed a   #
# verb other than a replacement, and a reserved observation key all outrank a #
# window fault.                                                               #
# --------------------------------------------------------------------------- #
_REPRESENTATION_SHAPE: Final[tuple[_Row, ...]] = (
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", until="stated", address="unaddressable"),
        {
            "typed": _refused(TypeError, "<class 'int'> is not an Entity Class"),
            "wire": _refused(
                WriteInstructionError,
                "a Wire `amendUntil` addresses an Entity spelling, and int is neither",
            ),
        },
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", until="stated", address="unaddressable"),
        _wire(
            _refused(
                WriteInstructionError,
                "a Wire `replaceUntil` addresses an Entity spelling or a node Parallax "
                "published, and int is neither",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(UNDECLARED_CONDITIONAL, "amend", until="stated"),
        {
            "typed": _refused(TypeError, _UNDECLARED_MODEL_TYPED),
            "wire": _refused(WriteInstructionError, _UNDECLARED_MODEL_WIRE),
        },
    ),
    _Row(
        TargetWriteScenario(UNDECLARED_CONDITIONAL, "replace", until="stated"),
        {
            "typed": _refused(TypeError, _UNDECLARED_MODEL_TYPED),
            "wire": _refused(WriteInstructionError, _UNDECLARED_MODEL_WIRE),
        },
    ),
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", until="stated", revision="omitted", payload="unshaped"
        ),
        _wire(
            _refused(
                WriteInstructionError,
                "a Wire `amendUntil`'s change set must be a document of names to values, got list",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "delete", revision="omitted", payload="unshaped"),
        _wire(
            _refused(
                WriteInstructionError,
                "a Wire `delete`'s key must be a document of names to values, got list",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", until="stated", address="published_with_data"),
        _wire(
            _refused(
                WriteInstructionError,
                "a Wire `replaceUntil` of a published node writes the state that node "
                "published, so it takes no data beside it; to state other data, name the Entity "
                "instead",
                published=True,
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", until="stated", address="published"),
        _wire(
            _refused(
                WriteInstructionError,
                "a Wire `amendUntil` addresses an Entity spelling, and _WireEntityNode is neither",
                published=True,
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", until="stated", payload="observation_key"),
        _wire(
            _refused(
                WriteInstructionError,
                "target write: row carries forbidden observation control key(s) "
                "['observedVersion'] (a target write's condition is its own revision argument, "
                "never a row member)",
            )
        ),
    ),
)


@pytest.mark.parametrize("row", _REPRESENTATION_SHAPE, ids=str)
def test_what_a_representation_captures_is_judged_before_the_window(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# The target's own rules: a temporal target spells removal `terminate_if`     #
# before its window, a Non-Temporal one has no history to terminate after its #
# window, and each profile admits only the window its As-Of Axes can bound —  #
# with a stated `until`, `None` included, selecting the bounded verb.          #
# --------------------------------------------------------------------------- #
_TARGET_RULES: Final[tuple[_Row, ...]] = (
    _Row(TargetWriteScenario(_BALANCE, "delete"), _both(_temporal_delete("Balance"))),
    _Row(
        TargetWriteScenario(_BALANCE, "delete", revision="omitted"),
        _both(_temporal_delete("Balance")),
    ),
    _Row(TargetWriteScenario(_POSITION, "delete"), _both(_temporal_delete("WherePosition"))),
    _Row(
        TargetWriteScenario(_ACCOUNT, "terminate", until="stated"),
        _both(_no_valid_time("Account", "non-temporal", "terminateUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "terminate"),
        _both(
            _refused(
                WriteInstructionError,
                "Non-temporal objects like 'Account' do not support 'terminate_if', which closes "
                "a row's history instead of removing it. Use 'delete_if' instead.",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", until="stated"),
        _both(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", until="none"),
        _both(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", until="none"),
        _both(_no_valid_time("Account", "non-temporal", "replaceUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", until="stated", revision="omitted"),
        _both(_no_valid_time("Account", "non-temporal", "replaceUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", until="none", revision="omitted"),
        _both(_no_valid_time("Account", "non-temporal", "replaceUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_PERSON, "amend", until="stated"),
        _both(_no_valid_time("Person", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_BALANCE, "amend", valid_from="stated"),
        _both(_no_valid_time("Balance", "Transaction-Time-Only", "amend", "valid_from")),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend"),
        _both(_refused(WriteInstructionError, _POSITION_REQUIRES_START)),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", valid_from="stated", until="none"),
        _both(_bounded_pair("amendUntil")),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION, "replace", valid_from="stated", until="reversed", concurrency="locking"
        ),
        _both(
            _refused(
                WriteInstructionError,
                "WherePosition: 'replaceUntil' requires valid_from < until — got "
                "valid_from=datetime.datetime(2024, 7, 1, 0, 0, tzinfo=datetime.timezone.utc), "
                "until=datetime.datetime(2024, 4, 1, 0, 0, tzinfo=datetime.timezone.utc)",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION, "replace", valid_from="stated", until="equal", concurrency="locking"
        ),
        _both(
            _refused(
                WriteInstructionError,
                "WherePosition: 'replaceUntil' requires valid_from < until — got "
                "valid_from=datetime.datetime(2024, 7, 1, 0, 0, tzinfo=datetime.timezone.utc), "
                "until=datetime.datetime(2024, 7, 1, 0, 0, tzinfo=datetime.timezone.utc)",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "terminate", valid_from="naive"),
        _both(_refused(InstantError, _NAIVE)),
    ),
)


@pytest.mark.parametrize("row", _TARGET_RULES, ids=str)
def test_the_target_admits_the_verb_and_window_before_its_revision(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# Then the revision: its presence is counted before any value is judged, the  #
# applicable kind follows the target's, and an unversioned Non-Temporal       #
# target has none to state. Under Locking a stated revision the stored row no #
# longer holds fails at the call; an Optimistic temporal write hears it at    #
# its flush.                                                                  #
# --------------------------------------------------------------------------- #
_REVISION: Final[tuple[_Row, ...]] = (
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="omitted"),
        _both(_requires_version("Account", "amend")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="none"),
        _both(
            _refused(
                WriteInstructionError,
                "Account: 'amend' states version=None, which names no revision; state the "
                "version its caller observed",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="both"),
        _both(
            _refused(
                WriteInstructionError,
                "Account: 'amend' states ['version', 'tx_start'], and a target has one "
                "condition to state",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="both_none"),
        _both(
            _refused(
                WriteInstructionError,
                "Account: 'amend' states ['version', 'tx_start'], and a target has one "
                "condition to state",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="misstated"),
        _both(_version_not_tx_start("amend")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="ill_typed"),
        _both(
            _refused(
                WriteInstructionError,
                "Account: 'amend' takes an integer version, and bool is no version",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_BALANCE, "replace", revision="omitted"),
        _both(_requires_tx_start("Balance", "replace")),
    ),
    _Row(
        TargetWriteScenario(_BALANCE, "replace", revision="omitted", concurrency="locking"),
        _both(_requires_tx_start("Balance", "replace")),
    ),
    _Row(
        TargetWriteScenario(_BALANCE, "amend", revision="ill_typed"),
        _both(
            _refused(
                InstantError,
                "Balance: 'amend' takes an aware datetime for tx_start, and str is no `timestamp`",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", valid_from="stated", revision="misstated"),
        _both(_tx_start_not_version("WherePosition", "amend")),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "terminate", valid_from="stated", revision="misstated"),
        _both(_tx_start_not_version("WherePosition", "terminate")),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "terminate", valid_from="stated", revision="omitted"),
        _both(_requires_tx_start("WherePosition", "terminate")),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", valid_from="stated", revision="none"),
        _both(
            _refused(
                WriteInstructionError,
                "WherePosition: 'amend' states tx_start=None, which names no revision; state the "
                "tx_start its caller observed",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_PERSON, "amend"),
        _both(
            _refused(
                WriteInstructionError,
                "Person: 'amend' states a revision its caller observed, and 'Person' is "
                "unversioned and non-temporal, so it has none to state and no write could detect "
                "a change since that observation; read it in the writing transaction and write "
                "through that read instead",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_PERSON, "delete", revision="omitted"),
        _both(
            _refused(
                WriteInstructionError,
                "Person: 'delete' states a revision its caller observed, and 'Person' is "
                "unversioned and non-temporal, so it has none to state and no write could detect "
                "a change since that observation; read it in the writing transaction and write "
                "through that read instead",
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="stale", concurrency="locking"),
        _both(
            _refused(
                WritePreconditionError,
                "Account: the state this write starts from no longer matches its precondition — "
                "key={'id': 1}, expected revision 3",
                read=True,
            )
        ),
    ),
    _Row(
        TargetWriteScenario(_BALANCE, "amend", revision="stale"),
        _both(
            _refused(
                WritePreconditionError,
                "Balance: the state this write starts from no longer matches its precondition — "
                "key={'id': 1}, expected revision datetime.datetime(2023, 12, 1, 0, 0, "
                "tzinfo=datetime.timezone.utc)",
                phase="flush",
                read=True,
            )
        ),
    ),
)


@pytest.mark.parametrize("row", _REVISION, ids=str)
def test_the_revision_is_judged_after_the_window_and_before_the_payload(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# The payload last: a window fault, then a revision fault, outranks it, and   #
# once both admit the write its fault is heard rather than the write dropped. #
# A Typed key and assignments are judged there through the deferred members,  #
# however eagerly the Wire document's shape was captured.                     #
# --------------------------------------------------------------------------- #
_PAYLOAD: Final[tuple[_Row, ...]] = (
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", until="stated", revision="omitted", payload="undeclared"
        ),
        _both(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", valid_from="stated", revision="omitted", payload="undeclared"
        ),
        _both(_no_valid_time("Account", "non-temporal", "amend", "valid_from")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="omitted", payload="undeclared"),
        _both(_requires_version("Account", "amend")),
    ),
    _Row(TargetWriteScenario(_ACCOUNT, "amend", payload="undeclared"), _undeclared("Account")),
    _Row(
        TargetWriteScenario(
            _POSITION, "amend", valid_from="stated", revision="omitted", payload="undeclared"
        ),
        _both(_requires_tx_start("WherePosition", "amend")),
    ),
    _Row(
        TargetWriteScenario(_POSITION, "amend", valid_from="stated", payload="undeclared"),
        _undeclared("WherePosition"),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", until="stated", payload="mapping_key"),
        _typed(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", revision="omitted", payload="mapping_key"),
        _typed(_requires_version("Account", "amend")),
    ),
    _Row(TargetWriteScenario(_ACCOUNT, "amend", payload="mapping_key"), _typed(_not_scalar())),
    _Row(
        TargetWriteScenario(_ACCOUNT, "delete", revision="omitted", payload="mapping_key"),
        _typed(_requires_version("Account", "delete")),
    ),
    _Row(TargetWriteScenario(_ACCOUNT, "delete", payload="mapping_key"), _typed(_not_scalar())),
    _Row(
        TargetWriteScenario(_ACCOUNT, "delete", revision="omitted", payload="extra_member"),
        _wire(_requires_version("Account", "delete")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "delete", payload="extra_member"),
        _wire(_key_alone("Account", "delete", "balance")),
    ),
    _Row(
        TargetWriteScenario(_BALANCE, "terminate", payload="extra_member"),
        _wire(_key_alone("Balance", "terminate", "value")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "delete", payload="undeclared"),
        _wire(_undeclared_member("Account")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", payload="undeclared"),
        _wire(_undeclared_member("Account")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", revision="omitted", payload="incomplete"),
        _wire(_requires_version("Account", "replace")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "replace", payload="incomplete"),
        _wire(
            _refused(
                WriteRejectedError,
                "Account.owner: a replacement states every required member, and this one is absent",
            )
        ),
    ),
)


@pytest.mark.parametrize("row", _PAYLOAD, ids=str)
def test_the_payload_is_judged_once_the_window_and_revision_admit_the_write(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# A refused call buffers nothing and flushes nothing: an earlier pending       #
# insert is neither executed by the refusal nor by a Locking acquisition that  #
# precedes it, and an object this attempt inserted is refused at the call.    #
# --------------------------------------------------------------------------- #
_PENDING_REFUSED: Final[tuple[_Row, ...]] = (
    _Row(
        TargetWriteScenario(_ACCOUNT, "amend", pending="addressed"),
        _both(_refused(WriteEvidenceError, _INSERTED, code="write-evidence-inserted")),
    ),
    _Row(
        TargetWriteScenario(_ACCOUNT, "delete", pending="addressed"),
        _both(_refused(WriteEvidenceError, _INSERTED, code="write-evidence-inserted")),
    ),
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", payload="undeclared", pending="unrelated", concurrency="locking"
        ),
        _undeclared("Account"),
    ),
    _Row(
        TargetWriteScenario(
            _POSITION,
            "amend",
            valid_from="stated",
            until="none",
            pending="unrelated",
            concurrency="locking",
        ),
        _both(_bounded_pair("amendUntil")),
    ),
    _Row(
        TargetWriteScenario(
            _ACCOUNT, "amend", revision="stale", pending="unrelated", concurrency="locking"
        ),
        _both(
            _refused(
                WritePreconditionError,
                "Account: the state this write starts from no longer matches its precondition — "
                "key={'id': 1}, expected revision 3",
                read=True,
            )
        ),
    ),
)


@pytest.mark.parametrize("row", _PENDING_REFUSED, ids=str)
def test_a_refused_conditional_write_flushes_no_pending_write(row: _Row) -> None:
    _assert_row(row)
